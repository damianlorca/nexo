# -*- coding: utf-8 -*-
"""Auditor de TODO el trabajo delegado a otras IAs (T189, Damian 26-27/09).

No es un modelo: es codigo determinista que mira la EVIDENCIA de cada delegacion (lo que se envio,
a quien, en que conversacion, con que modo comprobado en pantalla, que devolvio) y pasa un checklist
obligatorio. Si un punto falla, la delegacion queda BLOQUEADA: etiqueta en la tarea, JSON en
memoria/auditoria/, panel en la web y push al movil (nucleo/avisos.py). Nunca se da por buena.

Checklist (letras de T189):
  a) modo pedido (ChatGPT Pensar / Gemini Pro) ACTIVO de verdad en cada llamada web, y el autor no
     se degrado a una API porque la web fallo el modo;
  b) conversacion correcta: el autor trabaja la tarea en UNA conversacion (la guardada en la tarea si
     el tema es el mismo); otra solo si la anterior se estropea, y queda anotado;
  c) prompt minimo suficiente: sin texto de la interfaz, sin datos privados, sin codigos internos,
     dentro de su tamano; las revisiones se reenvian RESUMIDAS, no enteras;
  d) revision independiente (otra familia de modelo) con FALLOS/OMISIONES/MEJORAS/AÑADIR;
  e) protocolo OK absoluto (T183, protocolos.md): OK del autor JUSTIFICADO (COMPROBADO: >=3 puntos)
     y aprobacion del revisor independiente sobre ESA version, dentro del tope de iteraciones. El OK
     tiene que llegar en un mensaje POSTERIOR al del resultado, sin version nueva y sin que el resultado
     cambie despues (Damian 27/09: un OK en el mismo mensaje que el resultado cuenta como NO OK);
  f) lo que los revisores piden fuera del alcance de la tarea se descarta (y se registra);
  g) lectura limpia: nada de "ChatGPT dijo:", "Mostrar mas", "GitHub +1"... en lo guardado.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico

CARPETA = RAIZ / "memoria" / "auditoria"

# Familia del modelo que hay detras de cada proveedor: la revision solo es independiente si
# la familia es distinta (Gemini web y Gemini API son el mismo modelo; Groq sirve gpt-oss/qwen
# abiertos, otro modelo y otra casa que ChatGPT). NVIDIA (T227) sirve los MISMOS gpt-oss que Groq:
# misma familia, para que Groq y NVIDIA no se revisen entre si.
FAMILIA = {"chatgpt": "openai", "gemini": "google", "gemini_api": "google", "groq": "oss_abiertos",
           "nvidia": "oss_abiertos", "qwen": "local", "claude": "anthropic", "claude_web": "anthropic"}
WEB = ("chatgpt", "gemini")

TOPE_MEJORAS = 5            # pasadas del autor (mejora, revision critica o confirmacion); Damian 28/09: de 3 a 5
PARECIDO_MENORES = 0.85     # un cambio "solo menor" conserva al menos este parecido (palabras) con la version previa
MIN_COMPROBADO = 3          # puntos concretos que tiene que listar un OK absoluto
LIMITE_PROMPT = {"generar": 3500, "mejora": 4500, "mejora_api": 12500, "revision_seguimiento": 9500,
                 "revision": 11000}
# T242: estos tipos llevan el borrador dentro del prompt (nucleo.trabajo lo trunca con su propio tope,
# proporcional a la extension de la tarea); su limite escala con el mismo factor para no bloquear un
# borrador largo legitimo. "generar" no lleva borrador (es el primer encargo): no escala.
TIPOS_CON_BORRADOR = ("mejora", "mejora_api", "revision_seguimiento", "revision")
LIMITE_RESUMEN = 2600       # caracteres del resumen de revisiones que se reenvia al autor
MAX_ITEMS_SECCION = 5
MAX_CAR_ITEM = 260


def familia(proveedor: str) -> str:
    return FAMILIA.get((proveedor or "").split(" ")[0], proveedor or "?")


# ------------------------------------------------------------------ lectura limpia (g)
BASURA_INTERFAZ = [
    (re.compile(r"(?im)^\s*(chatgpt|gemini)\s+(dijo|ha dicho|said)\s*:?\s*$"), "etiqueta de turno de la web"),
    (re.compile(r"(?im)^\s*(t[uú] dijiste|has dicho|you said)\s*:\s*$"), "etiqueta de turno del usuario"),
    (re.compile(r"(?im)^\s*(mostrar m[aá]s|mostrar menos|show more|[uú]ltima respuesta)\s*$"), "boton de la web"),
    (re.compile(r"(?m)^\s*\+\d{1,2}\s*$"), "contador de cita ('+1')"),
    (re.compile(r"(?i)\b(github|wikipedia|reddit|medium|arxiv)\s*\+\d{1,2}\b"), "pildora de cita ('GitHub +1')"),
    (re.compile(r"(?im)^\s*(ha pensado durante|pens[oó] durante|thought for)\b"), "marca de razonamiento"),
    (re.compile(r"(?i)(chatgpt|gemini)[^\n]{0,40}puede cometer errores"), "pie de la web"),
    (re.compile(r"(?im)^\s*(anuncio|patrocinado|sponsored|opciones del anuncio|ad options)\s*$"),
     "anuncio de la web (T229)"),
]


def basura_interfaz(texto: str) -> list[str]:
    """Que texto de la interfaz web se ha colado (vacio = limpio)."""
    return [nombre for patron, nombre in BASURA_INTERFAZ if patron.search(texto or "")]


# ------------------------------------------------------------------ prompt minimo (c)
PRIVADO = [
    (re.compile(r"(?i)[a-z]:\\users\\"), "ruta privada del PC"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "correo electronico"),
    (re.compile(r"(?i)secretos\.toml"), "nombre del fichero de secretos"),
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|\d{8,10}:[A-Za-z0-9_-]{35}"),
     "algo con pinta de clave"),
]
# T750: la carpeta privada del perfil (CV, datos personales) y el perfil de los radares nunca van en un prompt:
# ni su ruta (patron de PRIVADO) ni su texto (perfil_privado(), que compara con lo que hay HOY en esos archivos).
PRIVADO.append((re.compile(r"(?i)perfil_privado|radares[\\/]perfil\.json"), "ruta del perfil privado"))
_RAIZ = Path(__file__).resolve().parent.parent
RUTAS_PERFIL = [_RAIZ / "memoria" / "perfil_privado", _RAIZ / "memoria" / "radares" / "perfil.json"]
MIN_FRAGMENTO = 25          # caracteres: por debajo, una linea suelta ("Formacion", "2024") no identifica nada
_cache_perfil: dict = {}


def _normal(texto: str) -> str:
    return " ".join(str(texto).lower().split())


def _cadenas(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [c for v in obj.values() for c in _cadenas(v)]
    if isinstance(obj, list):
        return [c for v in obj for c in _cadenas(v)]
    return []


def fragmentos_perfil() -> set[str]:
    """Lineas (y valores de texto del JSON) de los archivos del perfil privado, normalizadas. Solo en memoria."""
    archivos = []
    for r in RUTAS_PERFIL:
        if r.is_dir():
            archivos += [p for p in r.rglob("*") if p.is_file()]
        elif r.is_file():
            archivos.append(r)
    clave = tuple(sorted((str(p), p.stat().st_mtime_ns) for p in archivos))
    if _cache_perfil.get("clave") == clave:
        return _cache_perfil["fragmentos"]
    fragmentos = set()
    for p in archivos:
        try:
            texto = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue                          # PDF, imagen...: no es texto que se pueda colar tal cual
        lineas = texto.splitlines()
        if p.suffix.lower() == ".json":
            try:
                lineas = _cadenas(json.loads(texto))
            except ValueError:
                pass
        for linea in lineas:
            n = _normal(linea.strip(" \t#*-_>|"))
            if len(n) >= MIN_FRAGMENTO:
                fragmentos.add(n)
    _cache_perfil.update(clave=clave, fragmentos=fragmentos)
    return fragmentos


def perfil_privado(texto: str) -> bool:
    """True si el texto lleva algun fragmento del perfil privado (T750)."""
    n = _normal(texto or "")
    return bool(n) and any(f in n for f in fragmentos_perfil())


RUTA_USUARIO = re.compile(r"(?i)[a-z]:[\\/]users[\\/]\S*")


def tapar(texto: str, marca: str = "[privado]") -> str:
    r"""Tapa lo privado de un texto que va a salir del PC. PRIMERO la ruta del usuario entera (C:\Users\nombre\...):
    si se aplicara antes PRIVADO, su patron taparia solo 'C:\Users\' y dejaria el nombre de usuario y el resto
    (fallo visto el 05/10 en tareas.lista_para_ia_externa y plantillas_turno._tapar). Despues, los patrones de
    PRIVADO (correos, secretos.toml, claves, perfil privado)."""
    texto = RUTA_USUARIO.sub(marca, texto or "")
    for patron, _ in PRIVADO:
        texto = patron.sub(marca, texto)
    return texto


def motivos_privados(texto: str) -> list[str]:
    """Todos los motivos por los que este texto no puede salir del PC: patrones de PRIVADO + texto del perfil."""
    motivos = [n for p, n in PRIVADO if p.search(texto or "")]
    if perfil_privado(texto):
        motivos.append("texto del perfil privado")
    return motivos


INTERNO = [
    (re.compile(r"\b[TH]\d{3}\b"), "codigo interno de tarea/herramienta"),
    (re.compile(r"(?i)\bronda\s*\d+"), "referencia interna ('ronda N')"),
]


# T232 (27/09): tareas con la etiqueta material:interno analizan el PROPIO NEXO (su cola, su codigo): el
# material va entero y con sus ids. Solo para ellas se admiten ids T### y un prompt de hasta el tope del
# material (nucleo.trabajo.TOPE_MATERIAL) mas su tope normal. Datos privados y claves se bloquean igual.
TOPE_MATERIAL_INTERNO = 40000


# T561: NVIDIA Trial (build.nvidia.com) es una prueba para desarrolladores: lo que se le manda puede conservarse y
# usarse por su cuenta. El material interno de NEXO (su cola, su codigo) o privado no sale hacia alli, ni como autor
# ni como revisor ni en el tribunal. Los datos privados ya los frena `motivos_privados` para todos los proveedores.
SIN_MATERIAL_INTERNO = ("nvidia",)


def bloqueo_proveedor(proveedor: str, interno: bool = False, privado: bool = False) -> str:
    """Motivo si `proveedor` no puede recibir este material (interno o privado); '' si puede."""
    if proveedor in SIN_MATERIAL_INTERNO and (interno or privado):
        return f"material {'privado' if privado else 'interno'} no sale hacia NVIDIA Trial (T561)"
    return ""


def revisar_prompt(prompt: str, tipo: str, interno: bool = False, factor: float = 1.0,
                   proveedor: str = "") -> list[str]:
    """Problemas del prompt ANTES de enviarlo (vacio = minimo y limpio). tipo: generar|revision|mejora...

    interno=True (tarea con material:interno): sin tope de relleno ni de ids, tope de tamano ampliado.
    factor (T242): extension de la tarea (palabras objetivo / 600); escala el tope de los tipos que
    llevan el borrador dentro para no bloquear un borrador largo legitimo.
    """
    problemas = []
    limite = LIMITE_PROMPT.get(tipo)
    if limite and tipo in TIPOS_CON_BORRADOR and factor != 1.0:
        limite = round(limite * factor)
    if limite and interno:
        limite += TOPE_MATERIAL_INTERNO
    if limite and len(prompt) > limite:
        problemas.append(f"prompt de {len(prompt)} car. (tope {limite} para '{tipo}')")
    problemas += [f"texto de la interfaz: {b}" for b in basura_interfaz(prompt)]
    privados = motivos_privados(prompt)
    problemas += [f"dato privado: {n}" for n in privados]
    motivo = bloqueo_proveedor(proveedor, interno, bool(privados))
    if motivo:
        problemas.append(f"dato privado: {motivo}")   # con el prefijo, trabajo._llamar no lo envia
    if tipo in ("generar", "mejora") and not interno:
        problemas += [f"relleno: {n}" for p, n in INTERNO if p.search(prompt)]
    return problemas


# ------------------------------------------------------ revisiones: resumen y alcance (c, f)
SECCIONES = ("FALLOS", "OMISIONES", "MEJORAS", "AÑADIR")
_CABECERA = re.compile(r"^[ \t>#*_\-\d.)]*(FALLOS|OMISIONES|MEJORAS|A(?:Ñ|N)ADIR|GRAVEDAD|VEREDICTO)\b[ \t*_]*:?",
                       re.I | re.M)
_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*\S)")

# Peticiones de revisores que no aportan a un informe acotado (caso real T177, 27/09: un revisor
# pidio un tutorial Hello World y una comparativa con LangChain/AutoGPT). Se descartan y se anotan.
FUERA_ALCANCE = [
    (re.compile(r"(?i)tutorial|hello[ -]?world|paso a paso|gu[ií]a de instalaci[oó]n|instrucciones de instalaci[oó]n"),
     "tutorial o guia de instalacion"),
    (re.compile(r"(?i)comparativ|tabla compar|compar(a|ar|ación|acion)\b[^.]{0,40}\bcon\b|benchmark|versus|\bvs\.?\b"),
     "comparativa o benchmark no pedido"),
    (re.compile(r"(?i)ejemplos? de c[oó]digo|snippet|fragmento de c[oó]digo|script de ejemplo"), "codigo de ejemplo"),
    (re.compile(r"(?i)\bv[ií]deo|captura de pantalla|diagrama|gr[aá]fic[oa]s?\b|infograf"), "material audiovisual"),
    (re.compile(r"(?i)consumo (medio )?de (ram|cpu|memoria)|requisitos de recursos|medir (el )?rendimiento|"
                r"probar(lo)? en (el|tu) (pc|equipo)|instalar(lo)? y probar"), "pruebas que exigen ejecutar"),
    (re.compile(r"(?i)entrevista|encuesta|contactar (con )?(al|el) autor|preguntar en (el )?(foro|discord)"),
     "contacto con terceros"),
    (re.compile(r"(?i)(ampliar|alargar|extender) (el|todo el) informe|m[aá]s extens|m[aá]s de \d{3,} palabras"),
     "alargar por encima del limite"),
]


def fallos(texto: str) -> list[str]:
    """Items de la seccion FALLOS de una revision (T288: los clasifica trabajo._fallos_clasificados)."""
    return _items(texto).get("FALLOS", [])


def _items(texto: str) -> dict[str, list[str]]:
    """{seccion: [items]} de una revision con el formato de roles/revisor_borrador.md."""
    salida: dict[str, list[str]] = {s: [] for s in SECCIONES}
    actual = None
    for linea in (texto or "").splitlines():
        m = _CABECERA.match(linea)
        if m:
            nombre = m.group(1).upper().replace("ANADIR", "AÑADIR")
            actual = nombre if nombre in salida else None
            resto = linea[m.end():].strip(" *_-")
            if actual and resto and resto.lower() not in ("ninguno", "ninguna", "- ninguno"):
                salida[actual].append(resto)
            continue
        i = _ITEM.match(linea)
        if actual and i:
            item = i.group(1).strip()
            if item.lower().strip(".") not in ("ninguno", "ninguna", "nada"):
                salida[actual].append(item)
    return salida


def _clave(item: str) -> str:
    return re.sub(r"\W+", " ", item.lower()).strip()[:60]


def _sin_fallos(resumen: str) -> str:
    """El resumen sin su seccion FALLOS (donde el alcance no se filtra)."""
    return re.sub(r"^FALLOS:\n(?:- [^\n]*\n?)*", "", resumen or "")


def resumir_revisiones(revisiones: list[dict]) -> tuple[str, list[dict]]:
    """(resumen para reenviar al autor, descartes). Une las revisiones, quita repetidos, recorta cada
    punto, descarta lo fuera de alcance y acota el total (Damian 27/09: nada de pegar revisiones enteras)."""
    vistos: set[str] = set()
    por_seccion: dict[str, list[str]] = {s: [] for s in SECCIONES}
    descartes: list[dict] = []
    for r in revisiones:
        for seccion, items in _items(r.get("texto", "")).items():
            for item in items:
                # FALLOS corrige lo que YA dice el borrador (cita sus frases): ahi no se filtra alcance.
                motivo = None if seccion == "FALLOS" else next((n for p, n in FUERA_ALCANCE if p.search(item)), None)
                if motivo:
                    descartes.append({"revisor": r.get("revisor", "?"), "seccion": seccion, "punto": item[:200],
                                      "motivo": motivo})
                    continue
                k = _clave(item)
                if not k or k in vistos:
                    continue
                vistos.add(k)
                if len(por_seccion[seccion]) < MAX_ITEMS_SECCION:
                    por_seccion[seccion].append(item if len(item) <= MAX_CAR_ITEM else item[:MAX_CAR_ITEM] + "…")
    lineas = []
    for seccion in SECCIONES:
        if por_seccion[seccion]:
            lineas.append(f"{seccion}:")
            lineas += [f"- {i}" for i in por_seccion[seccion]]
    resumen = "\n".join(lineas)
    if len(resumen) > LIMITE_RESUMEN:
        resumen = resumen[:LIMITE_RESUMEN].rsplit("\n", 1)[0]
    return resumen, descartes


# ------------------------------------------------------------------ cierre OK absoluto (e)
_MARCA_AUTOAUDITORIA = re.compile(r"(?im)^[ \t#*_=>-]*AUTOAUDITOR[IÍ]A\b[ \t*_=:-]*$")
_CIERRE = re.compile(r"CIERRE\s*:?\s*\**\s*(OK ABSOLUTO|PENDIENTE)", re.I)


def partir_cierre(texto: str) -> tuple[str, str]:
    """(version, bloque de autoauditoria/cierre). Sin marca: corta en la linea del CIERRE."""
    m = None
    for m in _MARCA_AUTOAUDITORIA.finditer(texto or ""):
        pass
    if m is None:
        c = list(_CIERRE.finditer(texto or ""))
        if not c:
            return (texto or "").strip(), ""
        inicio = (texto or "").rfind("\n", 0, c[-1].start())
        corte = max(inicio, 0)
        return texto[:corte].strip(), texto[corte:].strip()
    return texto[:m.start()].strip(), texto[m.start():].strip()


def huella(texto: str) -> str:
    """Identidad de un resultado (espacios normalizados): si cambia, es otro resultado."""
    return hashlib.sha1(" ".join((texto or "").split()).encode("utf-8")).hexdigest()[:16]


def parecido(a: str, b: str) -> float:
    """0-1: cuanto se parecen dos versiones, palabra a palabra."""
    return difflib.SequenceMatcher(None, (a or "").split(), (b or "").split(), autojunk=False).ratio()


VERSION_MINIMA = 300        # caracteres a partir de los cuales un mensaje trae un resultado (no solo el cierre)


def ok_posterior(exp: dict) -> tuple[bool, str]:
    """El OK absoluto llego en un mensaje POSTERIOR al del resultado final, sin version nueva en ese
    mensaje y sin cambios en el resultado despues. Lo comprueba sobre la respuesta guardada, no se fia
    de lo que diga trabajo.py."""
    llamadas = exp.get("llamadas") or []
    ok, entregas = exp.get("ok_mensaje") or {}, exp.get("entregas") or []
    if not ok:
        extra = f" ({exp['ok_mismo_mensaje']} OK junto al resultado, no valen)" if exp.get("ok_mismo_mensaje") else ""
        return False, "ningun OK en un mensaje aparte del resultado" + extra
    i = ok.get("llamada")
    if not isinstance(i, int) or not 0 <= i < len(llamadas) or not entregas:
        return False, "sin evidencia del mensaje del OK o de la entrega del resultado"
    ll, ultima = llamadas[i], entregas[-1]
    version, bloque = partir_cierre(ll.get("respuesta") or "")
    if not leer_cierre(bloque)["ok"]:
        return False, f"el mensaje {i} no trae un OK justificado"
    if len(version) > VERSION_MINIMA:
        return False, f"el OK del mensaje {i} llega junto a un resultado (mismo mensaje): no vale"
    if ultima["llamada"] >= i:
        return False, f"el OK (mensaje {i}) no es posterior al resultado (mensaje {ultima['llamada']})"
    if ll.get("proveedor") != exp.get("autor"):
        return False, f"el OK lo da {ll.get('proveedor')}, no el autor {exp.get('autor')}"
    url_res = llamadas[ultima["llamada"]].get("url") if ultima["llamada"] < len(llamadas) else None
    if ll.get("url") and url_res and ll["url"] != url_res:
        return False, "el OK llega en otra conversacion que el resultado"
    if not (ok.get("huella") == ultima["huella"] == huella(exp.get("final") or "")):
        return False, "el resultado cambio despues del OK"
    # Damian 28/09: tras la ultima revision independiente solo caben retoques MENORES (y pequenos de verdad).
    revisado = max((j for j, x in enumerate(llamadas) if x.get("rol") == "revisor" and x.get("ok")), default=-1)
    menores = {m.get("llamada"): m for m in exp.get("menores") or []}
    sin_revisar = [e for e in entregas if e["llamada"] > revisado]
    for e in sin_revisar:
        m = menores.get(e["llamada"])
        if not (m and m.get("parecido", 0) >= PARECIDO_MENORES):
            return False, f"el resultado del mensaje {e['llamada']} cambio tras la ultima revision sin ser retoque menor"
    extra = f"; {len(sin_revisar)} retoque(s) menor(es) sin nueva revision" if sin_revisar else ""
    return True, f"OK en el mensaje {i}, posterior al resultado (mensaje {ultima['llamada']}) y sin cambios{extra}"


def leer_cierre(bloque: str) -> dict:
    """{'ok': bool, 'declarado': 'OK ABSOLUTO'|'PENDIENTE'|None, 'comprobado': [...], 'queda': [...]}.
    ok solo si declara OK ABSOLUTO Y lo justifica con al menos MIN_COMPROBADO puntos concretos."""
    c = list(_CIERRE.finditer(bloque or ""))
    declarado = c[-1].group(1).upper() if c else None

    def lista(nombre: str) -> list[str]:
        m = re.search(rf"(?im)^[ \t#*_]*{nombre}\b[ \t*_]*:?[ \t*_]*$|^[ \t#*_]*{nombre}\s*:", bloque or "")
        if not m:
            return []
        items = []
        for linea in bloque[m.end():].splitlines():
            i = _ITEM.match(linea)
            if i:
                items.append(i.group(1).strip())
            elif linea.strip() and items:
                break
            elif linea.strip() and re.match(r"^[ \t#*_]*[A-ZÁÉÍÓÚÑ ]{4,}\s*:", linea):
                break
        return items

    def reales(nombre: str) -> list[str]:
        return [x for x in lista(nombre) if not re.match(r"(?i)^\W*(ninguno|ninguna|nada)\b", x)]

    comprobado = [x for x in lista("COMPROBADO") if len(x) >= 12]
    fondo = reales("FONDO")
    # Un OK con fallos de FONDO declarados se contradice: no es un OK.
    return {"ok": declarado == "OK ABSOLUTO" and len(comprobado) >= MIN_COMPROBADO and not fondo,
            "declarado": declarado, "comprobado": comprobado, "queda": lista("QUEDA"),
            "fondo": fondo, "menores": reales("MENORES")}


# ------------------------------------------------------------------ checklist
def _punto(ok: bool, detalle: str) -> dict:
    return {"ok": bool(ok), "detalle": detalle}


def auditar(exp: dict) -> dict:
    """Pasa el checklist a-h sobre el expediente de una delegacion (lo arma nucleo/trabajo.py)."""
    llamadas = exp.get("llamadas") or []
    autor = exp.get("autor") or ""
    fam_autor = familia(autor)
    puntos: dict[str, dict] = {}

    # a) modo
    malos = []
    for ll in llamadas:
        if ll.get("proveedor") in WEB and ll.get("ok"):
            meta = ll.get("meta") or {}
            tras = str(meta.get("modo_tras_enviar", ""))
            if meta.get("modo_pedido") in (None, "ninguno") or not tras or "apagado" in tras.lower():
                malos.append(f"{ll.get('rol')}/{ll.get('proveedor')}: modo sin comprobar ({tras or 'sin evidencia'})")
    degradado = (exp.get("web_disponible") and autor not in WEB
                 and any(ll.get("rol") == "autor" and "ModoNoActivo" in str(ll.get("detalle", "")) for ll in llamadas))
    if degradado:
        malos.append(f"el autor paso a {autor} (sin modo) porque la web no consiguio Pensar/Pro")
    web_ok = [ll for ll in llamadas if ll.get("proveedor") in WEB and ll.get("ok")]
    puntos["a_modo"] = _punto(not malos, "; ".join(malos) or
                              (f"{len(web_ok)} llamadas web con el modo comprobado en pantalla" if web_ok
                               else "sin llamadas web (API: sin modo que comprobar)"))

    # b) conversacion
    conv = (exp.get("conversacion") or {}).get(exp.get("conversacion_autor") or "", {})
    urls = []
    for ll in llamadas:
        if ll.get("rol") in ("autor", "mejora") and ll.get("proveedor") in WEB and ll.get("ok") and ll.get("url"):
            if not urls or ll["url"] != urls[-1]:
                urls.append(ll["url"])
    cambios_justificados = len(conv.get("estropeadas") or [])
    problemas_b = []
    if len(urls) > 1 + cambios_justificados:
        problemas_b.append(f"el autor uso {len(urls)} conversaciones para la misma tarea")
    if conv.get("guardada") and conv.get("tema_igual") and not conv.get("retomada") and not conv.get("estropeadas"):
        problemas_b.append("habia una conversacion guardada del mismo tema y se abrio otra sin motivo")
    if autor in WEB and urls and not conv.get("url_guardada"):
        problemas_b.append("la URL de la conversacion no se guardo en la tarea")
    # Revisores web: tambien una conversacion por tarea (se cambia solo si la anterior se estropea).
    for clave, info in (exp.get("conversacion") or {}).items():
        sitio, _, rol = clave.partition(":")
        if rol != "revisor":
            continue
        urls_r = []
        for ll in llamadas:
            if ll.get("rol") == "revisor" and ll.get("proveedor") == sitio and ll.get("ok") and ll.get("url") \
                    and (not urls_r or ll["url"] != urls_r[-1]):
                urls_r.append(ll["url"])
        if len(urls_r) > 1 + len(info.get("estropeadas") or []):
            problemas_b.append(f"el revisor {sitio} uso {len(urls_r)} conversaciones para la misma tarea")
        if info.get("guardada") and info.get("tema_igual") and not info.get("retomada") and not info.get("estropeadas") \
                and urls_r:
            problemas_b.append(f"el revisor {sitio} tenia conversacion guardada del mismo tema y abrio otra sin motivo")
    puntos["b_conversacion"] = _punto(not problemas_b, "; ".join(problemas_b) or (
        f"una conversacion ({'retomada' if conv.get('retomada') else 'nueva'})"
        + (f", {cambios_justificados} estropeada(s) sustituida(s)" if cambios_justificados else "")
        if urls else "autor por API (sin conversacion web)"))

    # c) prompt minimo
    problemas_c = [f"{ll.get('rol')}->{ll.get('proveedor')}: {p}" for ll in llamadas for p in ll.get("prompt_problemas") or []]
    puntos["c_prompt"] = _punto(not problemas_c, "; ".join(problemas_c[:6]) or
                                f"{len(llamadas)} prompts dentro de tamano, sin interfaz ni datos privados; revisiones resumidas")

    # d) revision independiente
    rondas = exp.get("rondas") or []
    ultima = rondas[-1] if rondas else []
    indep = [r for r in ultima if familia(r.get("revisor", "")) != fam_autor]
    puntos["d_revision"] = _punto(bool(indep), (
        f"ultima ronda revisada por {', '.join(r['revisor'] for r in indep)} (otra familia que {autor})"
        if indep else "ninguna revision valida de otra familia de modelo (queda PENDIENTE_REVISION)"))

    # e) OK absoluto
    estado = exp.get("estado")
    cierre = exp.get("cierre") or {}
    mejoras = exp.get("mejoras", 0)
    posterior, detalle_post = ok_posterior(exp)
    ok_e = estado == "OK_ABSOLUTO" and cierre.get("ok") and posterior and mejoras <= TOPE_MEJORAS and indep and all(
        r.get("veredicto") == "APROBADO" for r in indep)
    puntos["e_ok_absoluto"] = _punto(ok_e, (
        f"OK absoluto del autor con {len(cierre.get('comprobado') or [])} comprobaciones y revisor independiente "
        f"conforme, en {mejoras} pasada(s) (tope {TOPE_MEJORAS}); {detalle_post}") if ok_e else
        f"sin OK absoluto: estado {estado}, cierre {cierre.get('declarado') or 'ninguno'} "
        f"({len(cierre.get('comprobado') or [])} comprobaciones), {mejoras} pasada(s); {detalle_post}")

    # f) alcance
    resumenes = exp.get("resumenes") or []
    colados = [n for r in resumenes for p, n in FUERA_ALCANCE if p.search(_sin_fallos(r))]
    descartes = exp.get("descartes") or []
    puntos["f_alcance"] = _punto(not colados, ("se reenvio al autor algo fuera de alcance: " + ", ".join(sorted(set(colados))))
                                 if colados else f"{len(descartes)} peticion(es) de revisores descartada(s) por fuera de alcance")

    # g) lectura limpia
    sucias = sorted({b for ll in llamadas for b in basura_interfaz(ll.get("respuesta", ""))}
                    | set(basura_interfaz(exp.get("final") or "")))
    puntos["g_lectura"] = _punto(not sucias, ("texto de la interfaz en las respuestas: " + ", ".join(sucias))
                                 if sucias else "respuestas sin texto de la interfaz web")

    # h) propuestas implementables (T192): toda investigacion termina con ellas o con 'NINGUNA: <por que>'.
    if exp.get("cat") == "investigacion" and estado != "USER_DECISION_REQUIRED":
        from nucleo import revision
        ok_h, detalle_h = revision.comprobar_seccion(exp.get("final") or "")
        puntos["h_propuestas"] = _punto(ok_h, detalle_h)

    fallos = [k for k, v in puntos.items() if not v["ok"]]
    if estado == "USER_DECISION_REQUIRED":
        resultado = "ESPERA_DECISION"
    else:
        resultado = "APROBADA" if not fallos else "BLOQUEADA"
    return {"resultado": resultado, "fallos": fallos, "puntos": puntos}


def registrar(exp: dict, auditoria: dict) -> Path:
    """Guarda el expediente + auditoria (sin prompts ni respuestas enteras) y avisa si hace falta."""
    CARPETA.mkdir(parents=True, exist_ok=True)
    ligero = {k: v for k, v in exp.items() if k not in ("llamadas", "final")}
    ligero["llamadas"] = [{k: (v[:300] if isinstance(v, str) and k in ("prompt", "respuesta") else v)
                           for k, v in ll.items()} for ll in exp.get("llamadas") or []]
    datos = {"cuando": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "tarea": exp.get("tarea"),
             "titulo": exp.get("titulo"), "borrador": exp.get("archivo"), **auditoria, "expediente": ligero}
    f = CARPETA / f"{exp.get('tarea', 'T')}_{datetime.now():%Y%m%d_%H%M%S}.json"
    escribir_atomico(f, json.dumps(datos, ensure_ascii=False, indent=1, default=str))
    if auditoria["resultado"] != "APROBADA":
        try:
            from nucleo import avisos
            if auditoria["resultado"] == "ESPERA_DECISION":
                titulo, cuerpo = (f"{exp.get('tarea')}: NEXO necesita una decisión tuya",
                                  str(exp.get("bloqueo") or "")[:300])
            else:
                titulo = f"{exp.get('tarea')}: delegación BLOQUEADA por el auditor"
                cuerpo = "; ".join(f"{k}: {auditoria['puntos'][k]['detalle']}" for k in auditoria["fallos"])
            avisos.emitir("auditoria", titulo, cuerpo, ruta=f"/borrador?f={exp.get('archivo', '').rsplit('/', 1)[-1]}",
                          clave=f"auditoria:{f.name}")
        except Exception:
            pass
    return f


def recientes(n: int = 12) -> list[dict]:
    """Ultimas auditorias (mas nueva primero) para la web: resultado, fallos y detalle de cada punto."""
    try:
        rutas = sorted(CARPETA.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    except OSError:
        return []
    salida = []
    for r in rutas:
        try:
            d = json.loads(r.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict):
            salida.append({"archivo": r.name, "cuando": d.get("cuando", ""), "tarea": d.get("tarea", ""),
                           "titulo": d.get("titulo", ""), "resultado": d.get("resultado", "?"),
                           "fallos": d.get("fallos") or [], "puntos": d.get("puntos") or {},
                           "borrador": str(d.get("borrador") or "").rsplit("/", 1)[-1],
                           "revisado": d.get("revisado") or None})
    return salida


def resolver(archivo: str, decision: str, motivo: str) -> dict:
    """Claude ya reviso esta delegacion BLOQUEADA / en espera: queda anotado en su auditoria y deja de
    contar como aviso en la web (el resultado original no se toca: sigue siendo la evidencia)."""
    motivo = " ".join((motivo or "").split())
    if len(motivo) < 15:
        raise ValueError("resolver un bloqueo necesita un motivo de verdad (minimo 15 caracteres)")
    ruta = CARPETA / Path(archivo).name
    d = json.loads(ruta.read_text(encoding="utf-8"))
    if d.get("resultado") == "APROBADA":
        raise ValueError(f"{ruta.name} esta APROBADA: no hay bloqueo que resolver")
    d["revisado"] = {"cuando": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "veredicto": decision.strip().upper(),
                     "motivo": motivo}
    escribir_atomico(ruta, json.dumps(d, ensure_ascii=False, indent=1, default=str))
    return d["revisado"]


def resolver_borrador(borrador: str, decision: str, motivo: str) -> list[str]:
    """Resuelve todas las auditorias no aprobadas y aun sin revisar del borrador (lo llama revision.veredicto)."""
    nombre = Path(str(borrador)).name
    hechas = []
    for a in recientes(500):
        if a["borrador"] == nombre and a["resultado"] != "APROBADA" and not a["revisado"]:
            resolver(a["archivo"], decision, motivo)
            hechas.append(a["archivo"])
    return hechas


def pendientes_de_revisar(lista: list[dict]) -> list[dict]:
    """Las BLOQUEADAS / en espera que Claude aun no ha revisado."""
    return [a for a in lista if a["resultado"] != "APROBADA" and not a.get("revisado")]


def de_borrador(nombre: str) -> dict | None:
    """La auditoria del borrador `nombre` (para pintarla junto al borrador en la web)."""
    for a in recientes(200):
        if a["borrador"] == nombre:
            return a
    return None


def _cli(argv: list[str]) -> int:
    """python -m nucleo.auditor pendientes | resolver <auditoria.json> <VEREDICTO> "motivo" """
    if not argv or argv[0] == "pendientes":
        for a in pendientes_de_revisar(recientes(500)):
            print(f"{a['archivo']}  {a['resultado']}  {a['tarea']}  {', '.join(a['fallos'])}  {a['borrador']}")
        return 0
    if argv[0] == "resolver" and len(argv) >= 4:
        print(resolver(argv[1], argv[2], argv[3]))
        return 0
    print(_cli.__doc__)
    return 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    from nucleo import consola
    consola.preparar()   # consola cp1252 de Windows: '?' en lo que no cabe, tildes intactas
    import sys
    raise SystemExit(_cli(sys.argv[1:]))
