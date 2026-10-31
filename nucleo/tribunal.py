# -*- coding: utf-8 -*-
"""T667 (F1 de la epica T664, Damian 03/10): tribunal de revision para revisar y autorizar SIN depender de Claude.

Damian no paga ninguna IA: los revisores son API gratuitas (NVIDIA, Groq, Gemini API) y, como extra con cupo
diario prudente, ChatGPT y Gemini web con cuenta gratuita. Plan: documentacion/PLAN_REVISION_APROBACION_IMPLEMENTACION.md
(seccion 3).

ESCALERA (un EXPEDIENTE = un borrador con todas sus propuestas):
  1. TRIBUNAL: los 3 primeros revisores DISPONIBLES de familias distintas (nunca la del autor), en el orden de
     TRIBUNAL (API primero, web al final). Si uno falla (caido, error, salida truncada sin FIN_DICTAMEN o
     acusacion FALSO desmentida), entra el siguiente de otra familia. Solo espera si no hay 3 familias; nunca
     decide con 2. Unanimidad (global, cada propuesta y, en investigaciones, el RESULTADO de T674) -> se aplica
     con revision.veredicto(quien="tribunal"). 3 de 3 RECHAZAR -> DESCARTADO.
  2. APELACION: si no hay unanimidad, otras 3 IAs gratuitas mas fuertes (APELACION, sin repetir ninguna del
     tribunal) reciben el DESACUERDO resumido. Unanimidad -> se aplica.
  3. BANDEJA DE DAMIAN (web, Centro): resumen de 3 lineas + Aprobar / Rechazar / Mandar a Claude.
  Claude solo recibe R3 (blindados, seguridad, secretos, dinero, cuentas: directo, sin gastar revisores), lo que
  Damian le mande y la siembra de calibracion. Su bandeja tiene tope MAX_BANDEJA_CLAUDE; la orden para pegarle
  esta en documentacion/prompts/CLAUDE_BANDEJA.md (boton "Copiar orden" en la web).

VERIFICACION DE HECHOS (T288 + T334): los FALLOS [FALSO: prueba] y [NO VERIFICABLE] con URL o repo de GitHub se
comprueban sin IA (nucleo.verificar_hechos). Un FALSO de "no existe" que resulta existir anula a ese revisor; una
URL que da 404 es un FALSO confirmado e impide la unanimidad de APROBAR. Lo que no se puede comprobar sigue NO
VERIFICABLE y nunca castiga: un dato de 2025-26 que el revisor no conoce no es falso.

CALIBRACION: con Claude solo la SIEMBRA (50 casos a ciegas: las investigaciones de T667 con borrador y, hasta 50,
veredictos historicos de Claude, que ya eran ciegos). Despues la calidad se mide por RESULTADOS
(registrar_resultado: suite de la puerta de fusion, reverts y vetos en F2/F3; coincidencia con Damian en su
bandeja). Por revisor: < UMBRAL_REVISOR en MIN_REVISOR casos -> sale de la lista. Por tipo de trabajo: < UMBRAL_TIPO
-> tarea para T321 y ese tipo pasa siempre por apelacion + bandeja de Damian hasta recuperar RECUPERA_TIPO.

RITMO: sin rafagas (PAUSA_API / PAUSA_WEB entre llamadas al mismo proveedor) y respetando nucleo.enfriamiento; el
cupo web diario enfria "tribunal:<proveedor>" hasta medianoche, sin bloquear el resto de usos de esa web.

Estado en memoria/tribunal/ (junto a tareas.json): expedientes.json, calibracion.jsonl, estado.json.

CLI:
  .venv\\Scripts\\python.exe -m nucleo.tribunal ciclo [--max 3] [--simular]
  .venv\\Scripts\\python.exe -m nucleo.tribunal estado
  .venv\\Scripts\\python.exe -m nucleo.tribunal bandeja_claude | bandeja_damian
  .venv\\Scripts\\python.exe -m nucleo.tribunal sembrar [--total 50] [T124 T135 ...]   (sin ids: los de T667)
  .venv\\Scripts\\python.exe -m nucleo.tribunal dictamen <borrador> APROBADO|DESCARTADO|REHACER "motivo" [--resultado ADOPTAR "motivo"]
  .venv\\Scripts\\python.exe -m nucleo.tribunal resultado <borrador> veto|revert|puerta_fusion correcto|incorrecto
  .venv\\Scripts\\python.exe -m nucleo.tribunal readmitir <revisor>
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from nucleo import ahora as reloj
from nucleo import enfriamiento, revision
from nucleo import tareas as T
from nucleo.candado import bloqueo

RAIZ = Path(__file__).resolve().parent.parent
ORDEN_CLAUDE = RAIZ / "documentacion" / "prompts" / "CLAUDE_BANDEJA.md"


class Candidato(NamedTuple):
    id: str
    proveedor: str
    modelo: str
    familia: str
    web: bool = False


# 04/10 (primer uso + banco herramientas_nube/_banco_tribunal_0410.py): FUERA mistral-nemotron (HTTP 410, retirado),
# groq qwen3-32b (HTTP 404, retirado) y glm-5.3-flash (sin respuesta en 120 s). kimi-k3 (se trunca 2 de 4) y
# deepseek-v4.1-flash (sin respuesta) no pasaron el banco; mistral-large-2-instruct no consta como Free Endpoint.
_QWEN = Candidato("groq:qwen3.8-27b", "groq", "qwen/qwen3.8-27b", "alibaba")
_GEM36 = Candidato("gemini_api:gemini-3.6-flash", "gemini_api", "gemini-3.6-flash", "google")
_GEM37 = Candidato("gemini_api:gemini-3.7-flash", "gemini_api", "gemini-3.7-flash", "google")


def _nvidia(i: int) -> Candidato:
    """T1039 (25/10): el i-esimo de config nvidia.modelos (ultra el primero), sin nombres fijos: super-120b daba 404 y
    seguia escrito a mano. Si uno deja de estar vivo (nucleo.modelos_estado), _disponible lo salta."""
    import proveedores as P
    lista = P.modelos_nvidia_config()
    m = lista[min(i, len(lista) - 1)]
    return Candidato(P.id_corto_nvidia(m), "nvidia", m, "nvidia")


_NVIDIA = _nvidia(0)
_GPTOSS = Candidato("groq:gpt-oss-120b", "groq", "openai/gpt-oss-120b", "openai")
# Un NVIDIA distinto del del tribunal (el segundo de la config) para la apelacion: sin el, los borradores de autor
# ChatGPT no reunian 3 familias en apelacion.
_NVIDIA_B = _nvidia(1)
# 04/10 (T162, banco herramientas_nube/_banco_openrouter_0410.py, 6 :free de familias nuevas): NINGUNO entra.
# cohere/north-mini-code:free paso el banco una vez (rechazo el caso con error) pero repetido 4 veces mas APROBO el error
# 4 de 4 (1 de 5 en total): no sirve de revisor. inkling (HTTP 403: solo para agentes), laguna-s-2.1 (429 e inestable,
# aprobo el caso con error), apodex (respuesta vacia) y dots-3 (aprobo el caso con error) tampoco. OpenRouterProvider
# queda disponible (cuenta con limite de 0 USD, solo :free) para cuando salga un modelo que pase el banco.
_CHATGPT = Candidato("chatgpt:web", "chatgpt", "", "openai", True)
_GEMWEB = Candidato("gemini:web", "gemini", "", "google", True)
# Claude web de NEXO (cuenta propia, plan Free): SOLO apelacion y al final (Damian 04/10). Nunca tribunal,
# calibracion ni R3.
_CLAUDEWEB = Candidato("claude_web:web", "claude_web", "", "anthropic", True)

# Orden de preferencia: API gratuitas primero (4 familias vivas el 04/10: alibaba, google, nvidia, openai) y la
# web al final. La apelacion empieza por las que el tribunal suele dejar libres (gpt-oss-120b, gemini-3.7).
TRIBUNAL = (_QWEN, _GEM36, _NVIDIA, _GPTOSS, _CHATGPT, _GEMWEB)
APELACION = (_NVIDIA_B, _GPTOSS, _GEM37, _NVIDIA, _QWEN, _GEM36, _CHATGPT, _GEMWEB, _CLAUDEWEB)
CANDIDATOS = {c.id: c for c in TRIBUNAL + APELACION}


def clave_banco(c) -> str:
    """'proveedor:modelo' como lo guarda el banco T320 (memoria/modelos/roles.json)."""
    return f"{c.proveedor}:{c.modelo}"

# Cupo diario de la web con cuenta GRATUITA (prudente; los limites reales no estan publicados: SIN VERIFICAR).
CUPO_WEB = {"chatgpt": 6, "gemini": 4, "claude_web": 3}
PAUSA_API = 20.0           # segundos minimos entre dos llamadas al mismo proveedor de API
PAUSA_WEB = 300.0          # y a la misma web
MAX_BANDEJA_CLAUDE = 20
LIMITE_BORRADOR = 9000     # caracteres del borrador que van en el prompt
MAX_VERIFICAR = 5          # fallos con URL que se comprueban por dictamen

UMBRAL_REVISOR, MIN_REVISOR = 0.70, 20
UMBRAL_TIPO, MIN_TIPO, RECUPERA_TIPO, VENTANA_TIPO = 0.85, 20, 0.90, 50

SIEMBRA_T667 = ("T124", "T135", "T146", "T148", "T150", "T152", "T153", "T164", "T166", "T177", "T191", "T200",
                "T202", "T232", "T261", "T264")
SIEMBRA_TOTAL = 50

VOTOS = ("APROBAR", "RECHAZAR", "DUDA")
FIN = "FIN_DICTAMEN"
VIVAS = ("tribunal", "apelacion")          # fases en las que trabaja el tribunal
EN_CLAUDE = ("claude",)

# R3 directo a Claude (Damian 04/10): SOLO blindados, secretos o dinero. La seguridad la revisa el tribunal y, si se
# aprueba, la propuesta lleva la marca riesgo:R3 para la implementacion (F2).
_R3 = re.compile(r"(?i)(nucleo/permisos\.py|nucleo/instancia\.py|nucleo/config\.py|\bmanos/|blindad|secretos?(\.toml)?\b|"
                 r"api[ _-]?key|contrase[ñn]as?|credencial|\bdinero\b|\bpagos?\b|\bcompras?\b|tarjeta|\bgastos?\b|"
                 r"cobr(ar|o)\b|factura)")
_SEGURIDAD = re.compile(r"(?i)(seguridad|permisos|sandbox|privilegio|telemetr|cifrad|autenticaci|\bmfa\b|"
                        r"exfiltra|inyecci)")
ET_R3 = "riesgo:R3"
_NIEGA = re.compile(r"(?i)(no existe|inexistente|inventad|no hay (tal|ningun)|404|falso que exista)")
_AUTOR = re.compile(r"(?i)autor\s+([a-z_]+)")
_MODELOS_AUTOR = re.compile(r"(?i)\|\s*modelo\s+([^|]+?)\s*(?:\||-->|$)")
_HIST = re.compile(r"Revision de Claude del borrador (\S+): (APROBADO|DESCARTADO|REHACER)\b")

PLANTILLAS = {
    "investigacion": "Es la INVESTIGACION de una herramienta, modelo o servicio externo. Comprueba la identidad "
                     "exacta, la URL oficial, la licencia y si encaja con NEXO (Windows, local-first, gratis). "
                     "Da RESULTADO: ADOPTAR (usarlo tal cual), ADAPTAR (usar una parte o la idea) o DESCARTAR.",
    "documento": "Es la revision de un DOCUMENTO INTERNO de NEXO (plan, informe, decision). NO pidas URL oficial "
                 "ni licencia: no aplican. Juzga coherencia, omisiones, riesgos y si las propuestas son aplicables. "
                 "Da RESULTADO: ADOPTAR (incorporarlo tal cual), ADAPTAR (con cambios) o DESCARTAR.",
    "codigo": "Es trabajo sobre el CODIGO de NEXO. Juzga si el diagnostico es correcto y si cada correccion es "
              "concreta (archivo y linea) y comprobable con un test. Tocar archivos blindados es RECHAZAR aqui.",
    "general": "Juzga si el trabajo es correcto, util para NEXO y no duplica algo ya hecho.",
    "reconsideracion": "No hay borrador: cada PROPUESTA es una idea DESCARTADA sin juzgarla (se tiro el borrador que la "
                       "traia, o el vigia la nombro y nadie la miro). Juzga SOLO la idea: APROBAR = merece volver a la "
                       "cola de propuestas; RECHAZAR = no aporta, no encaja con NEXO (Windows, local-first, gratis) o "
                       "ya esta hecha. GLOBAL: APROBAR si alguna merece volver; RECHAZAR si ninguna.",
}


class BandejaLlena(Exception):
    pass


# ------------------------------------------------------------------ almacen
def carpeta() -> Path:
    return T.ALMACEN.parent / "tribunal"


def _ruta(nombre: str) -> Path:
    return carpeta() / nombre


def _leer_json(ruta: Path, defecto):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return defecto


def _escribir_json(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ruta)


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def expedientes() -> dict:
    return _leer_json(_ruta("expedientes.json"), {})


def _estado() -> dict:
    e = _leer_json(_ruta("estado.json"), {})
    for k in ("excluidos", "vigilados", "ultimo", "cupo"):
        e.setdefault(k, {} if k != "excluidos" else [])
    return e


@contextmanager
def _editar(que: str = "expedientes.json"):
    carpeta().mkdir(parents=True, exist_ok=True)
    with bloqueo(_ruta(".candado_tribunal.lock")):
        datos = _estado() if que == "estado.json" else _leer_json(_ruta(que), {})
        yield datos
        _escribir_json(_ruta(que), datos)


def _guardar_exp(e: dict) -> None:
    e["actualizado"] = _ahora()
    with _editar() as d:
        d[e["nombre"]] = e


def _leer_calibracion() -> list[dict]:
    try:
        lineas = _ruta("calibracion.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [json.loads(x) for x in lineas if x.strip()]


# ------------------------------------------------------------------ familias y proveedores
def familia_modelo(modelo: str) -> str:
    m = (modelo or "").lower()
    for clave, fam in (("openai/", "openai"), ("gpt", "openai"), ("qwen", "alibaba"), ("mistral", "mistral"),
                       ("nvidia/", "nvidia"), ("nemotron", "nvidia"), ("z-ai/", "zai"), ("glm", "zai"),
                       ("gemini", "google"), ("gemma", "google"), ("deepseek", "deepseek"), ("kimi", "moonshot"),
                       ("llama", "meta"), ("claude", "anthropic"), ("cohere", "cohere")):
        if clave in m:
            return fam
    return m or "desconocida"


def familias_autor(proveedor: str) -> set[str]:
    """Familia del autor. El borrador solo guarda el proveedor: en Groq y NVIDIA se toma la de su PRIMER modelo
    configurado (el que se intenta primero y casi siempre escribe). Excluir las de todos sus modelos dejaba a los
    borradores de NVIDIA sin 3 familias (prueba en seco del 04/10)."""
    p = (proveedor or "").split(" ")[0].lower()
    fijas = {"chatgpt": {"openai"}, "gemini": {"google"}, "gemini_api": {"google"}, "claude": {"anthropic"},
             "claude_web": {"anthropic"}, "qwen": {"alibaba"}}
    if p in fijas:
        return fijas[p]
    if p in ("groq", "nvidia"):
        try:
            import proveedores
            cls = proveedores.GroqProvider if p == "groq" else proveedores.NvidiaProvider
            modelos = tuple(cls().modelos)
            return {familia_modelo(modelos[0])} if modelos else {"desconocida"}
        except Exception:
            return {"desconocida"}
    return set()


def _proveedor(c: Candidato):
    import proveedores as P
    if c.proveedor == "nvidia":
        return P.NvidiaProvider(modelos=(c.modelo,))
    if c.proveedor == "groq":
        return P.GroqProvider(modelos=(c.modelo,), rondas=1)
    if c.proveedor == "gemini_api":
        return P.GeminiAPIProvider(modelos=(c.modelo,), rondas=1)
    if c.proveedor == "openrouter":
        return P.OpenRouterProvider(modelos=(c.modelo,), rondas=1)
    if c.proveedor == "claude_web":
        return P.ClaudeWebProvider()
    return P.ChatGPTProvider() if c.proveedor == "chatgpt" else P.GeminiProvider()


def _verificar_item(texto: str) -> dict:
    from nucleo import verificar_hechos
    return verificar_hechos.verificar_item(texto)


def _hasta_medianoche() -> float:
    ahora = datetime.now()
    return ((ahora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0) - ahora).total_seconds()


def cupo_web() -> dict:
    hoy = datetime.now().strftime("%Y-%m-%d")
    usadas = _estado()["cupo"].get(hoy, {})
    return {p: {"usadas": usadas.get(p, 0), "cupo": n, "enfriado": enfriamiento.enfriado(f"tribunal:{p}")}
            for p, n in CUPO_WEB.items()}


def _contar_web(prov: str) -> None:
    hoy = datetime.now().strftime("%Y-%m-%d")
    with _editar("estado.json") as e:
        e["cupo"] = {hoy: e["cupo"].get(hoy, {})}
        e["cupo"][hoy][prov] = n = e["cupo"][hoy].get(prov, 0) + 1
    if n >= CUPO_WEB.get(prov, 0):
        enfriamiento.enfriar(f"tribunal:{prov}", "cupo_diario", f"cupo web del tribunal ({n}/{CUPO_WEB.get(prov)})",
                             segundos=_hasta_medianoche())


def _disponible(c: Candidato) -> bool:
    if c.id in _estado()["excluidos"]:
        return False
    if c.web and enfriamiento.enfriado(f"tribunal:{c.proveedor}"):
        return False
    try:
        return bool(_proveedor(c).disponible())
    except Exception:
        return False


def _esperar(c: Candidato, limite: float | None) -> bool:
    """Sin rafagas: espera lo que falte desde la ultima llamada a ese proveedor. False si no da tiempo."""
    pausa = PAUSA_WEB if c.web else PAUSA_API
    falta = _estado()["ultimo"].get(c.proveedor, 0) + pausa - time.time()
    if falta > 0:
        if limite and time.time() + falta > limite:
            return False
        time.sleep(min(falta, pausa))
    return True


def _marcar_uso(c: Candidato) -> None:
    with _editar("estado.json") as e:
        e["ultimo"][c.proveedor] = time.time()
    if c.web:
        _contar_web(c.proveedor)


# ------------------------------------------------------------------ dictamen
# El voto es la primera palabra; separador opcional (banco 04/10: qwen escribe 'GLOBAL: RECHAZAR El borrador ...').
_LINEA = re.compile(r"(?im)^[ \t>*_-]*(GLOBAL|P\d+|RESULTADO)[ \t*_]*:[ \t*_]*([A-Za-zÁÉÍÓÚáéíóú]+)[ \t*_]*"
                    r"[|:\-—]?[ \t]*(.*)$")


def parsear(texto: str, n_propuestas: int, es_inv: bool) -> dict:
    """Lee el bloque de dictamen. error != "" si esta truncado o le falta algo (el revisor no cuenta)."""
    limpio = re.sub(r"(?is)<think>.*?</think>", "", texto or "").replace("**", "").replace("__", "")
    # Gemini web pinta el bloque como un solo parrafo (ciclo 2, 04/10): cada clave vuelve a su linea.
    limpio = re.sub(r"[ \t]+(?=(?:GLOBAL|P\d+|RESULTADO|FALLOS)[ \t]*:)", "\n", limpio)
    limpio = re.sub(r"[ \t]+(?=" + FIN + r")", "\n", limpio)
    d = {"global": "", "motivo": "", "propuestas": [], "resultado": None, "fallos": [], "error": ""}
    if FIN not in limpio:
        d["error"] = f"salida truncada o incompleta (sin {FIN})"
        return d
    cuerpo = limpio[:limpio.rindex(FIN)]
    ini = list(re.finditer(r"(?im)^[ \t>*_-]*GLOBAL[ \t*_]*:", cuerpo))
    if not ini:
        d["error"] = "sin linea GLOBAL"
        return d
    cuerpo = cuerpo[ini[-1].start():]
    vistos: dict[str, tuple[str, str]] = {}
    for m in _LINEA.finditer(cuerpo):
        clave, voto, motivo = m.group(1).upper(), " ".join(m.group(2).upper().split()), m.group(3).strip()
        vistos.setdefault(clave, (voto, motivo))
    g = vistos.get("GLOBAL", ("", ""))
    if g[0] not in VOTOS:
        d["error"] = f"GLOBAL ilegible ({g[0] or 'vacio'})"
        return d
    d["global"], d["motivo"] = g
    for i in range(1, n_propuestas + 1):
        v = vistos.get(f"P{i}")
        if not v or v[0] not in VOTOS:
            d["error"] = f"falta el voto de P{i}"
            return d
        d["propuestas"].append(list(v))
    if es_inv:
        r = vistos.get("RESULTADO")
        if not r or r[0] not in ("ADOPTAR", "ADAPTAR", "DESCARTAR"):
            d["error"] = "falta RESULTADO (ADOPTAR/ADAPTAR/DESCARTAR) en una investigacion"
            return d
        d["resultado"] = [r[0], r[1] or "sin motivo"]
    sec = re.search(r"(?is)FALLOS\s*:(.*)$", cuerpo)
    for linea in (sec.group(1).splitlines() if sec else []):
        m = re.search(r"\[(FALSO|NO VERIFICABLE)\s*:?\s*([^\]]*)\]\s*(.*)", linea, re.I)
        if m:
            tipo = m.group(1).upper()
            if tipo == "FALSO" and not m.group(2).strip():
                tipo = "NO VERIFICABLE"              # FALSO sin prueba no es una acusacion valida
            d["fallos"].append([tipo, f"{m.group(2).strip()} {m.group(3).strip()}".strip()])
    return d


def _verificar(d: dict) -> tuple[list[str], str]:
    """(falsos confirmados, motivo si la acusacion del revisor queda desmentida)."""
    confirmados = []
    for tipo, texto in d["fallos"][:MAX_VERIFICAR]:
        if "http" not in texto.lower() and "github.com" not in texto.lower():
            continue
        r = _verificar_item(texto)
        if tipo == "FALSO" and r.get("confirmado") is True and _NIEGA.search(texto):
            return [], f"acusacion FALSO desmentida: {r.get('detalle', '')}"[:200]
        if r.get("confirmado") is False:
            confirmados.append(f"{texto[:120]} ({r.get('detalle', '')})")
    return confirmados, ""


def prompt(e: dict, fase: str) -> str:
    props = "\n".join(f"P{i}: {p}" for i, p in enumerate(e["textos_propuestas"], 1)) or "(ninguna)"
    formato = ["GLOBAL: APROBAR|RECHAZAR|DUDA | motivo en una frase"]
    formato += [f"P{i}: APROBAR|RECHAZAR|DUDA | motivo" for i in range(1, len(e["textos_propuestas"]) + 1)]
    if e["es_inv"]:
        formato.append("RESULTADO: ADOPTAR|ADAPTAR|DESCARTAR | motivo")
    formato += ["FALLOS:", "- [FALSO: prueba concreta] lo que es falso   o   - [NO VERIFICABLE] lo que no puedes "
                "comprobar   o   - ninguno", FIN]
    apel = ""
    if e.get("parcial"):
        apel += ("\nEXPEDIENTE PARCIAL: el resto de propuestas de este borrador ya estan decididas; vota SOLO las de "
                 "la lista PROPUESTAS de abajo.\n")
    if fase == "apelacion":
        apel += ("\nAPELACION. Un primer tribunal de tres IAs no se puso de acuerdo. DESACUERDO resumido:\n"
                f"{e.get('resumen') or '(sin resumen)'}\nDecide tu con criterio propio; no tienes que seguir a "
                "ninguno.\n")
    return reloj.con_fecha(
        "Eres revisor independiente de NEXO, el asistente personal local-first de Damian (Windows, IA gratis). "
        "Juzgas un BORRADOR que escribio otra IA (no sabes cual). " + PLANTILLAS.get(e["tipo"], PLANTILLAS["general"])
        + "\nTu conocimiento tiene fecha de corte: un dato de 2025-2026 que no conoces NO es falso; marcalo "
        "[NO VERIFICABLE]. Usa [FALSO: prueba] solo con una prueba concreta (URL, cita o razonamiento comprobable): "
        "una acusacion que resulte desmentida anula tu dictamen.\n"
        "Vota cada propuesta: APROBAR (correcta y merece hacerse), RECHAZAR (erronea, inutil o duplicada) o DUDA "
        "(falta informacion para decidir)." + apel +
        f"\nTAREA: {e.get('titulo', '')}\n\nBORRADOR:\n<<<\n{e['texto']}\n>>>\n\nPROPUESTAS:\n{props}\n\n"
        "Responde EXACTAMENTE con este bloque (una linea por punto) y nada despues de " + FIN + ":\n"
        + "\n".join(formato))


# ------------------------------------------------------------------ decision
def decidir(dicts: list[dict], es_inv: bool, n: int) -> dict:
    """APROBADO / DESCARTADO solo por unanimidad; si no, DESACUERDO con su resumen (para apelacion o Damian)."""
    g = [d["global"] for d in dicts]
    nom = [f"R{i}" for i in range(1, len(dicts) + 1)]
    falsos = [f for d in dicts for f in d.get("falsos") or []]
    if all(x == "RECHAZAR" for x in g):
        return {"decision": "DESCARTADO", "descartar": [], "resultado": None, "resumen": ""}
    ok, lineas, descartar = all(x == "APROBAR" for x in g), [], []
    aprobar_todos, divididas = [], []
    if not ok:
        lineas.append("GLOBAL: " + "; ".join(f"{r} {d['global']} ({d['motivo'][:110]})" for r, d in zip(nom, dicts)))
    for i in range(n):
        votos = [d["propuestas"][i][0] for d in dicts]
        if len(set(votos)) > 1 or "DUDA" in votos:
            ok = False
            divididas.append(i)
            lineas.append(f"P{i + 1}: " + "; ".join(f"{r} {d['propuestas'][i][0]} ({d['propuestas'][i][1][:80]})"
                                                    for r, d in zip(nom, dicts)))
        elif votos[0] == "RECHAZAR":
            descartar.append(i)
        else:
            aprobar_todos.append(i)
    resultado, resultado_unanime = None, True
    if es_inv:
        rs = [d["resultado"][0] for d in dicts]
        if len(set(rs)) > 1:
            resultado_unanime = False
            ok = False
            lineas.append("RESULTADO: " + "; ".join(f"{r} {x}" for r, x in zip(nom, rs)))
        else:
            resultado = list(dicts[0]["resultado"])
    if falsos:
        ok = False
        lineas.append("FALSO confirmado al verificar: " + "; ".join(falsos)[:400])
    # Expediente PARCIAL (Damian 04/10): global unanime a favor, sin FALSO confirmado y RESULTADO unanime; algunas
    # propuestas unanimes y otras divididas -> se aplican las unanimes y solo las divididas siguen la escalera.
    parcial = (not ok and all(x == "APROBAR" for x in g) and not falsos and resultado_unanime and bool(divididas)
               and bool(aprobar_todos or descartar))
    return {"decision": "APROBADO" if ok else "DESACUERDO", "descartar": descartar, "resultado": resultado,
            "resumen": "\n".join(lineas)[:1500], "aprobar": aprobar_todos, "divididas": divididas,
            "parcial": parcial}


def _mayoria(e: dict) -> tuple[list[int], str | None]:
    todos = e["dictamenes"]["tribunal"] + e["dictamenes"]["apelacion"]
    descartar = [i for i in range(len(e["textos_propuestas"]))
                 if sum(d["propuestas"][i][0] == "RECHAZAR" for d in todos)
                 > sum(d["propuestas"][i][0] == "APROBAR" for d in todos)]
    res = Counter(d["resultado"][0] for d in todos if d.get("resultado")).most_common(1)
    return descartar, (res[0][0] if res else None)


def _lineas_damian(e: dict) -> list[str]:
    def votos(lista):
        c = Counter(d["global"] for d in lista)
        return f"{c['APROBAR']} aprobar / {c['RECHAZAR']} rechazar / {c['DUDA']} duda"
    descartar, res = _mayoria(e)
    n = len(e["textos_propuestas"])
    entran = [f"P{i + 1}" for i in range(n) if i not in descartar]
    fuera = [f"P{i + 1}" for i in descartar]
    objecion = next((d["motivo"] for d in e["dictamenes"]["apelacion"] + e["dictamenes"]["tribunal"]
                     if d["global"] != "APROBAR"), "")
    ya = e.get("parcial") or {}
    hecho = (f" (parcial: ya aplicadas {len(ya.get('aprobadas', []))} aprobadas y "
             f"{len(ya.get('descartadas', []))} descartadas)") if ya else ""
    return [f"{e['origen']} · {e['tipo']} · {e.get('titulo', '')[:90]} · {n} propuesta(s){hecho}",
            f"Tribunal: {votos(e['dictamenes']['tribunal'])} · Apelacion: {votos(e['dictamenes']['apelacion'])}"
            + (" · tipo vigilado (calibracion baja)" if e.get("vigilado") else ""),
            f"Si apruebas: entran {', '.join(entran) or 'ninguna'}; se descartan {', '.join(fuera) or 'ninguna'}"
            + (f"; RESULTADO {res}" if e["es_inv"] and res else "") + (f". Objecion: {objecion[:140]}" if objecion else "")]


# ------------------------------------------------------------------ expedientes
def _tipo(origen: dict | None) -> tuple[str, bool]:
    from nucleo import investigacion
    if origen is None:
        return "general", False
    et = origen.get("etiquetas") or []
    if investigacion.es_investigacion(origen):
        return ("documento" if "material:interno" in et else "investigacion"), True
    if "cat:codigo" in et or "plantilla:revisar_codigo" in et or "plantilla:correcciones" in et:
        return "codigo", False
    return "general", False


def _texto_borrador(nombre: str) -> tuple[str, str, list[str]]:
    """(version final recortada, proveedor autor, modelos exactos del autor) del .md del borrador. Los borradores
    anteriores al 04/10 no guardan el modelo: lista vacia."""
    try:
        md = (revision.BORRADORES / nombre).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", "", []
    cabecera = md.split("\n", 1)[0]
    autor = _AUTOR.search(cabecera)
    m = _MODELOS_AUTOR.search(cabecera)
    modelos = [x.strip() for x in (m.group(1).split(",") if m else []) if x.strip() and x.strip() != "?"]
    texto = revision.version_final(md).strip()
    if len(texto) > LIMITE_BORRADOR:
        texto = texto[:LIMITE_BORRADOR] + "\n[... borrador recortado para el prompt ...]"
    return texto, (autor.group(1) if autor else ""), modelos


def _texto_propuesta(p: dict) -> str:
    lin = [x.strip() for x in (p.get("detalle") or "").splitlines()[:4] if x.strip()]
    return " | ".join(lin) or p.get("titulo", "")


def _nuevo(nombre: str, origen_id: str, revision_id: str = "", calibracion: dict | None = None) -> dict:
    origen = T.buscar(origen_id) if origen_id else None
    if origen is not None and origen["id"] != origen_id:
        origen = None
    tipo, es_inv = _tipo(origen)
    texto, autor, modelos_autor = _texto_borrador(nombre)
    if calibracion is None:
        props = sorted(revision.propuestas_de(nombre), key=lambda p: int(p["id"][1:]))
        ids, textos = [p["id"] for p in props], [_texto_propuesta(p) for p in props]
    else:
        ext = revision.extraer_propuestas(texto)
        ids = []
        textos = [f"QUE: {p['que']} | DONDE: {p['donde']} | VALOR: {p['valor']} | ESFUERZO: {p['esfuerzo']} | "
                  f"RIESGO: {p['riesgo']}" for p in ext["propuestas"]]
    return {"nombre": nombre, "origen": origen_id, "revision": revision_id,
            "titulo": (origen or {}).get("titulo", ""), "tipo": tipo, "es_inv": es_inv, "autor": autor,
            "modelos_autor": modelos_autor,
            "propuestas": ids, "textos_propuestas": textos, "texto": texto,
            "fase": "calibracion" if calibracion else "tribunal", "motivo": "", "dictamenes": {"tribunal": [],
                                                                                            "apelacion": []},
            "fallos": [], "resumen": "", "decision": None, "decision_tribunal": None, "quien": None,
            "vigilado": False, "calibracion": calibracion, "creado": _ahora(), "actualizado": _ahora()}


def _familias_prohibidas(e: dict) -> set[str]:
    """La familia REAL del autor (cabecera 'modelo ...'); en borradores antiguos, la del primer modelo de su proveedor."""
    if e.get("modelos_autor"):
        return {familia_modelo(m) for m in e["modelos_autor"]}
    return familias_autor(e.get("autor", ""))


def _en_bandeja_claude(exps: dict) -> int:
    return sum(1 for e in exps.values()
               if e["fase"] in EN_CLAUDE or (e["fase"] == "calibracion" and not (e.get("calibracion") or {}).get("referencia")))


def _cerrar_fuera(exps: dict) -> list[str]:
    """Expedientes cuya revision ya no esta viva (veredicto dado con revision.veredicto, p. ej. por Claude): resueltos."""
    fuera = []
    for e in exps.values():
        if e["fase"] in VIVAS + ("damian", "claude", "espera_claude") and not e.get("reconsiderar")                 and revision.revision_de(e["nombre"]) is None:
            e.update(fase="resuelto", quien="fuera", motivo="veredicto aplicado fuera del tribunal", actualizado=_ahora())
            fuera.append(e["nombre"])
    return fuera


def _sincronizar() -> dict:
    """Incorpora los borradores nuevos, cierra los resueltos por otra via y llena la bandeja de Claude (R3)."""
    cambios = {"nuevos": [], "fuera": [], "a_claude": []}
    from nucleo import reconsiderar   # E1/T686: descartes a reconsiderar, por lotes y bajo el freno F0
    cambios["reconsiderar"] = {**reconsiderar.soltar(), **reconsiderar.encolar()}
    vivas = [t for t in T.cargar()["tareas"]
             if revision.ET_REVISION in (t.get("etiquetas") or []) and t["estado"] in T.VIVOS]
    with _editar() as exps:
        for t in vivas:
            nombre = revision._et(t, revision.PRE_BORRADOR)
            if nombre and nombre not in exps:
                e = _nuevo(nombre, revision._et(t, revision.PRE_ORIGEN), t["id"])
                if any(es_r3(x) for x in e["textos_propuestas"]):
                    e["fase"], e["motivo"] = "espera_claude", MOTIVO_R3
                exps[nombre] = e
                cambios["nuevos"].append(nombre)
        cambios["fuera"] = _cerrar_fuera(exps)
        for e in sorted(exps.values(), key=lambda x: x["creado"]):
            if e["fase"] == "espera_claude" and _en_bandeja_claude(exps) < MAX_BANDEJA_CLAUDE:
                e["fase"] = "claude"
                cambios["a_claude"].append(e["nombre"])
    return cambios


def _reunir(e: dict, fase: str, limite: float | None) -> bool:
    """Completa hasta 3 dictamenes validos de familias distintas en `fase`. True si los hay."""
    lista = TRIBUNAL if fase == "tribunal" else APELACION
    from nucleo import banco_modelos   # T320: con evidencia clara del banco, su mejor revisor va delante
    lista = banco_modelos.ordenar("revisar", lista, clave_banco)
    ya = e["dictamenes"][fase]
    fams = {d["familia"] for d in ya}
    prohibidas = _familias_prohibidas(e)
    usados = {d["id"] for d in e["dictamenes"]["tribunal"]} if fase == "apelacion" else set()
    intentados: set[str] = set()
    texto_prompt = None
    for c in lista:
        if len(ya) >= 3:
            break
        if c.id in usados | intentados | {d["id"] for d in ya} or c.familia in fams or c.familia in prohibidas:
            continue
        if limite and time.time() > limite:
            break
        if not _disponible(c) or not _esperar(c, limite):
            continue
        intentados.add(c.id)
        texto_prompt = texto_prompt or prompt(e, fase)
        try:
            r = _proveedor(c).enviar(texto_prompt)
        except Exception as ex:
            r = None
            motivo = f"{type(ex).__name__}: {ex}"[:200]
        _marcar_uso(c)
        if r is None or not r.ok:
            e["fallos"].append({"id": c.id, "fase": fase, "motivo": motivo if r is None else
                                f"{r.estado}: {r.detalle}"[:200], "cuando": _ahora()})
            continue
        d = parsear(r.texto, len(e["textos_propuestas"]), e["es_inv"])
        if not d["error"]:
            falsos, desmentido = _verificar(d)
            d["error"] = desmentido
            d["falsos"] = falsos
        if d["error"]:
            e["fallos"].append({"id": c.id, "fase": fase, "motivo": d["error"], "cuando": _ahora()})
            continue
        ya.append({"id": c.id, "familia": c.familia, "global": d["global"], "motivo": d["motivo"],
                   "propuestas": d["propuestas"], "resultado": d["resultado"], "falsos": d["falsos"],
                   "cuando": _ahora()})
        fams.add(c.familia)
    return len(ya) >= 3


MOTIVO_R3 = "R3: toca blindados, secretos o dinero"


def es_r3(texto_propuesta: str) -> bool:
    """R3 por QUE y DONDE (el RIESGO puede decir "no toca secretos" sin serlo)."""
    return bool(_R3.search((texto_propuesta or "").split("RIESGO")[0]))


def _marcar_r3(e: dict, quien: str, pares: list[tuple[str, str]] | None = None) -> list[str]:
    """Propuestas APROBADAS de seguridad -> riesgo:R3 (su implementacion necesita a Claude y a Damian en F2)."""
    marcadas = []
    for pid, texto in (pares if pares is not None else zip(e["propuestas"], e["textos_propuestas"])):
        p = T.buscar(pid)
        if p is None or p["id"] != pid or p["estado"] != "pendiente" or not _SEGURIDAD.search(texto.split("RIESGO")[0]):
            continue
        T.actualizar(pid, etiquetas=list(dict.fromkeys(list(p.get("etiquetas") or []) + [ET_R3])))
        T.anotar(pid, f"Marca {ET_R3} ({quien}): propuesta de seguridad aprobada en revision; su implementacion es R3 "
                      "(Claude + Damian, matriz de riesgo de F2).")
        marcadas.append(pid)
    return marcadas


def reencolar_r3() -> dict:
    """Devuelve al tribunal las que se fueron a Claude como R3 con el criterio viejo (que incluia 'seguridad')."""
    r = {"reencolados": [], "siguen": []}
    with _editar() as exps:
        for e in sorted(exps.values(), key=lambda x: x["creado"]):
            if e["fase"] not in EN_CLAUDE + ("espera_claude",) or e.get("calibracion") \
                    or not str(e.get("motivo", "")).startswith("R3"):
                continue
            if any(es_r3(x) for x in e["textos_propuestas"]):
                e["motivo"] = MOTIVO_R3
                r["siguen"].append(e["nombre"])
            else:
                e.update(fase="tribunal", motivo="re-encolado: R3 acotado a blindados, secretos o dinero (04/10)",
                         actualizado=_ahora())
                r["reencolados"].append(e["nombre"])
        for e in sorted(exps.values(), key=lambda x: x["creado"]):
            if e["fase"] == "espera_claude" and _en_bandeja_claude(exps) < MAX_BANDEJA_CLAUDE:
                e["fase"] = "claude"
    return r


def _aplicar(e: dict, dec: dict, quien: str, fase: str) -> None:
    ids = ", ".join(d["id"] for d in e["dictamenes"][fase])
    motivo = (f"Tribunal unanime ({fase}: {ids}): "
              + (e["dictamenes"][fase][0]["motivo"] or "sin motivo")[:240])
    if e.get("reconsiderar"):
        from nucleo import reconsiderar
        no = set(range(len(e["propuestas"]))) if dec["decision"] == "DESCARTADO" else set(dec["descartar"])
        reconsiderar.aplicar(e, [p for i, p in enumerate(e["propuestas"]) if i not in no],
                             [p for i, p in enumerate(e["propuestas"]) if i in no], motivo, quien)
        e["decision"] = dec["decision"]
        return
    props = {e["propuestas"][i]: "descartar" for i in dec["descartar"] if i < len(e["propuestas"])}
    res = (dec["resultado"][0], dec["resultado"][1] if len(dec["resultado"][1]) >= 15 else
           f"{dec['resultado'][1]} (tribunal unanime)".strip()) if dec.get("resultado") else None
    try:
        revision.veredicto(e["nombre"], dec["decision"], motivo, propuestas=props,
                           resultado=res if dec["decision"] == "APROBADO" else None, quien=quien)
    except ValueError as ex:
        if revision.revision_de(e["nombre"]) is None:
            e.update(fase="resuelto", quien="fuera", motivo=f"ya resuelto fuera: {ex}"[:200])
            return
        raise
    e.update(fase="resuelto", decision=dec["decision"], quien=quien, motivo=f"aplicado por {quien} ({fase})")
    if dec["decision"] == "APROBADO":
        e["marcadas_r3"] = _marcar_r3(e, quien)


def _coincide(voto: str, referencia: str) -> bool:
    return (voto == "APROBAR") == (referencia == "APROBADO") and voto != "DUDA"


def _norm(decision: str) -> str:
    return "APROBADO" if decision == "APROBADO" else "DESCARTADO"


def _registrar(e: dict, fuente: str, referencia: str, tribunal: str | None) -> dict:
    ref = _norm(referencia)
    todos = e["dictamenes"]["tribunal"] + e["dictamenes"]["apelacion"]
    fila = {"cuando": _ahora(), "nombre": e["nombre"], "tipo": e["tipo"], "fuente": fuente, "referencia": ref,
            "tribunal": tribunal if tribunal in ("APROBADO", "DESCARTADO") else None,
            "revisores": {d["id"]: _coincide(d["global"], ref) for d in todos}}
    carpeta().mkdir(parents=True, exist_ok=True)
    with bloqueo(_ruta(".candado_tribunal.lock")):
        with _ruta("calibracion.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    _evaluar()
    return fila


def _evaluar() -> dict:
    """Saca de la lista a los revisores flojos y vigila los tipos por debajo del umbral (tarea para T321)."""
    filas = _leer_calibracion()
    por_rev: dict[str, list[bool]] = {}
    for f in filas:
        for cid, ok in (f.get("revisores") or {}).items():
            por_rev.setdefault(cid, []).append(bool(ok))
    nuevos_vigilados = []
    with _editar("estado.json") as est:
        for cid, l in por_rev.items():
            if len(l) >= MIN_REVISOR and sum(l) / len(l) < UMBRAL_REVISOR and cid not in est["excluidos"]:
                est["excluidos"].append(cid)
        for tipo in sorted({f["tipo"] for f in filas}):
            l = [f["tribunal"] == f["referencia"] for f in filas if f["tipo"] == tipo and f.get("tribunal")]
            l = l[-VENTANA_TIPO:]
            if len(l) < MIN_TIPO:
                continue
            tasa, reciente = sum(l) / len(l), sum(l[-MIN_TIPO:]) / MIN_TIPO
            if tipo not in est["vigilados"] and tasa < UMBRAL_TIPO:
                est["vigilados"][tipo] = {"desde": _ahora(), "tasa": round(tasa, 3)}
                nuevos_vigilados.append((tipo, tasa))
            elif tipo in est["vigilados"] and reciente >= RECUPERA_TIPO:
                est["vigilados"].pop(tipo)
    for tipo, tasa in nuevos_vigilados:
        etiqueta = f"tribunal:tipo:{tipo}"
        if not any(etiqueta in (t.get("etiquetas") or []) and t["estado"] in T.VIVOS for t in T.cargar()["tareas"]):
            T.anadir(f"Tribunal: mejorar el prompt de revision del tipo '{tipo}' (coincidencia {tasa:.0%})",
                     detalle=(f"T667: la coincidencia del tribunal en el tipo '{tipo}' bajo de {UMBRAL_TIPO:.0%} "
                              f"({tasa:.0%} en los ultimos casos). Mientras tanto ese tipo pasa siempre por apelacion "
                              "+ bandeja de Damian. Revisar la plantilla PLANTILLAS en nucleo/tribunal.py y los casos "
                              "fallidos de memoria/tribunal/calibracion.jsonl. Se coordina con T321 (revision de "
                              "todos los prompts)."),
                     importancia=4, urgencia=3, dificultad=2, coste=1, depende="ia",
                     etiquetas=["cat:arquitectura", "prov:claude", "tema:prompts", "epica:T664", etiqueta])
    return _estado()


def procesar(e: dict, limite: float | None = None) -> str:
    """Un paso de la escalera para un expediente. Devuelve la fase en la que queda (o 'espera')."""
    vigilados = _estado()["vigilados"]
    fase = "tribunal" if e["fase"] == "calibracion" else e["fase"]
    if not _quorum_posible(e, fase):
        return _escalar(e, f"sin quorum posible en {fase}: con la familia del autor "
                           f"({', '.join(sorted(_familias_prohibidas(e))) or '-'}) y los revisores ya usados no "
                           "quedan 3 familias distintas")
    if not _reunir(e, fase, limite):
        e["esperas"] = e.get("esperas", 0) + 1
        if fase == "apelacion" and e["esperas"] >= MAX_ESPERAS:
            return _escalar(e, f"{e['esperas']} pasadas sin reunir 3 familias en apelacion")
        e["motivo"] = (f"esperando: no hay 3 familias disponibles en {fase} "
                       f"({len(e['dictamenes'][fase])} dictamen(es) guardados; pasada {e['esperas']})")
        _guardar_exp(e)
        return "espera"
    e["esperas"] = 0
    parcial = e.get("parcial")
    dec = decidir(e["dictamenes"][fase], e["es_inv"] and not parcial, len(e["textos_propuestas"]))
    if parcial and fase == "apelacion":
        # lo que queda son propuestas sueltas de un borrador ya aprobado: el RESULTADO es el del tribunal y un
        # rechazo unanime descarta esas propuestas, no el borrador
        if dec["decision"] == "DESCARTADO":
            dec = dict(dec, decision="APROBADO", descartar=list(range(len(e["textos_propuestas"]))))
        dec["resultado"] = parcial.get("resultado")
    if e["fase"] == "calibracion":
        e["decision_tribunal"] = dec["decision"]
        cal = e["calibracion"]
        if cal.get("referencia"):
            _registrar(e, "siembra" if cal["fuente"] == "siembra" else cal["fuente"], cal["referencia"],
                       dec["decision"])
            e.update(fase="resuelto", motivo="calibracion registrada")
        _guardar_exp(e)
        return e["fase"]
    if fase == "tribunal":
        e["decision_tribunal"] = dec["decision"]
        if dec["decision"] != "DESACUERDO" and e["tipo"] not in vigilados:
            _aplicar(e, dec, "tribunal", "tribunal")
        elif dec["parcial"] and e["tipo"] not in vigilados:
            _aplicar_parcial(e, dec)
        else:
            e["vigilado"] = e["tipo"] in vigilados
            pre = (f"Tipo '{e['tipo']}' vigilado (coincidencia baja): el primer tribunal decidio {dec['decision']}.\n"
                   if e["vigilado"] and dec["decision"] != "DESACUERDO" else "")
            e.update(fase="apelacion", resumen=(pre + dec["resumen"]).strip(), motivo="desacuerdo: a apelacion")
    else:
        if dec["decision"] != "DESACUERDO" and not e.get("vigilado"):
            _aplicar(e, dec, "tribunal", "apelacion")
        else:
            if dec["resumen"]:
                e["resumen"] = (e.get("resumen", "") + "\nAPELACION: " + dec["resumen"])[:2500]
            if e.get("vigilado"):
                e["fase"], e["motivo"] = "damian", "tipo vigilado: decide Damian"
                e["lineas"] = _lineas_damian(e)
            else:      # 13/10 (Damian): el desacuerdo que sobrevive a la apelacion lo decide Claude, no Damian
                return _escalar(e, "la apelacion tampoco fue unanime")
    _guardar_exp(e)
    return e["fase"]


MAX_ESPERAS = 3   # pasadas de apelacion esperando revisores antes de escalar (13/10: atasco de T699/T798/T820)


def _quorum_posible(e: dict, fase: str) -> bool:
    """¿Quedan, en teoria, 3 familias distintas para `fase`? (sin mirar caidas ni cupos de hoy)"""
    lista = TRIBUNAL if fase == "tribunal" else APELACION
    ya = e["dictamenes"][fase]
    fams = {d["familia"] for d in ya}
    usados = {d["id"] for d in e["dictamenes"]["tribunal"]} if fase == "apelacion" else set()
    excluidos = set(_estado()["excluidos"])
    prohibidas = _familias_prohibidas(e)
    posibles = {c.familia for c in lista if c.id not in usados | excluidos | {d["id"] for d in ya}
                and c.familia not in prohibidas and c.familia not in fams}
    return len(fams) + len(posibles) >= 3


def _escalar(e: dict, motivo: str) -> str:
    """Escalada (13/10): a la bandeja de Claude; si esta llena, a la de Damian. Nunca se queda esperando para siempre."""
    if _en_bandeja_claude(expedientes()) < MAX_BANDEJA_CLAUDE:
        e.update(fase="claude", motivo=f"escalado a Claude: {motivo}")
    else:
        e.update(fase="damian", motivo=f"escalado (bandeja de Claude llena): {motivo}")
        e["lineas"] = _lineas_damian(e)
    e["actualizado"] = _ahora()
    _guardar_exp(e)
    return e["fase"]


def _aplicar_parcial(e: dict, dec: dict) -> None:
    """Aplica las propuestas unanimes y deja el expediente solo con las divididas, camino de la apelacion."""
    ids = ", ".join(d["id"] for d in e["dictamenes"]["tribunal"])
    aprobar = [e["propuestas"][i] for i in dec["aprobar"]]
    descartar = [e["propuestas"][i] for i in dec["descartar"]]
    if e.get("reconsiderar"):
        from nucleo import reconsiderar
        for c in descartar:
            reconsiderar._confirmar(e, c, f"Tribunal unanime en esta fila ({ids})", "tribunal")
        for c in aprobar:
            reconsiderar._reabrir(e, c, f"Tribunal unanime en esta fila ({ids})", "tribunal")
        marcadas = []
    else:
        revision.aplicar_parcial(e["nombre"], aprobar, descartar,
                                 f"Tribunal unanime en estas propuestas ({ids}); las divididas van a apelacion",
                                 quien="tribunal")
        marcadas = _marcar_r3(e, "tribunal", [(e["propuestas"][i], e["textos_propuestas"][i]) for i in dec["aprobar"]])
    quedan = dec["divididas"]
    e["parcial"] = {"aprobadas": aprobar, "descartadas": descartar, "marcadas_r3": marcadas,
                    "resultado": dec.get("resultado"), "cuando": _ahora()}
    e["propuestas"] = [e["propuestas"][i] for i in quedan]
    e["textos_propuestas"] = [e["textos_propuestas"][i] for i in quedan]
    for d in e["dictamenes"]["tribunal"]:
        d["propuestas"] = [d["propuestas"][i] for i in quedan]
    e.update(fase="apelacion", motivo="parcial: aplicadas las unanimes, a apelacion solo las divididas",
             resumen=decidir(e["dictamenes"]["tribunal"], False, len(quedan))["resumen"])


def ciclo(limite: float | None = None, simular: bool = False, max_expedientes: int = 3) -> dict:
    """Lo lanza el turno 'tribunal' (o la CLI). Trabaja hasta `max_expedientes` en orden: primero los que mas
    propuestas desbloquean (para soltar el freno F0), luego la calibracion."""
    if simular:
        vivas = [t for t in T.cargar()["tareas"]
                 if revision.ET_REVISION in (t.get("etiquetas") or []) and t["estado"] in T.VIVOS]
        return {"simulado": True, "borradores_vivos": len(vivas), "expedientes": len(expedientes()),
                "candidatas": candidatas()}
    sinc = _sincronizar()
    from nucleo import tribunal_r1   # T967: vetos R1 de "implementar" (primero: bloquean al implementador)
    r1 = tribunal_r1.ciclo(limite)
    trabajo = [e for e in expedientes().values()
               if e["fase"] in VIVAS or (e["fase"] == "calibracion" and not e.get("decision_tribunal"))]
    # primero lo que suelta el freno (borradores con muchas propuestas); las reconsideraciones (E1/T686) detras
    # 13/10: los que esperaron en la pasada anterior van detras (antes tapaban la cola: 17 sin tocar)
    trabajo.sort(key=lambda e: (e["fase"] == "calibracion", e.get("esperas", 0), bool(e.get("reconsiderar")),
                                -len(e["propuestas"]), e["creado"]))
    hechos, esperando = [], 0
    for e in trabajo[:max_expedientes]:
        if limite and time.time() > limite:
            break
        r = procesar(e, limite)
        while r == "apelacion" and not (limite and time.time() > limite):
            r = procesar(e, limite)
        esperando += r == "espera"
        hechos.append({"nombre": e["nombre"], "fase": r, "decision": e.get("decision")})
    return {"simulado": False, "sincronizado": sinc, "r1": r1, "hechos": hechos, "esperando": esperando,
            "a_damian": [h["nombre"] for h in hechos if h["fase"] == "damian"],
            "a_claude": list(sinc["a_claude"]) + [h["nombre"] for h in hechos if h["fase"] == "claude"]}


def candidatas() -> int:
    """Cuanto trabajo hay (puerta T156 del turno), sin llamar a nadie."""
    exps = expedientes()
    nuevos = sum(1 for t in T.cargar()["tareas"]
                 if revision.ET_REVISION in (t.get("etiquetas") or []) and t["estado"] in T.VIVOS
                 and revision._et(t, revision.PRE_BORRADOR) not in exps)
    from nucleo import reconsiderar
    from nucleo import tribunal_r1
    return nuevos + tribunal_r1.candidatas() + reconsiderar.candidatas(exps) + sum(
        1 for e in exps.values() if e["fase"] in VIVAS or (e["fase"] == "calibracion" and not e.get("decision_tribunal")))


# ------------------------------------------------------------------ bandejas
def bandeja_damian() -> list[dict]:
    return [{"nombre": e["nombre"], "origen": e["origen"], "titulo": e.get("titulo", ""), "es_inv": e["es_inv"],
             "lineas": e.get("lineas") or _lineas_damian(e), "resultado": _mayoria(e)[1]}
            for e in sorted(expedientes().values(), key=lambda x: x["creado"]) if e["fase"] == "damian"]


def decidir_damian(nombre: str, accion: str, resultado: str | None = None) -> dict:
    accion = (accion or "").strip().lower()
    e = expedientes().get(nombre)
    if e is None or e["fase"] != "damian":
        raise ValueError(f"{nombre} no esta en la bandeja de Damian")
    if accion == "claude":
        with _editar() as exps:
            if _en_bandeja_claude(exps) >= MAX_BANDEJA_CLAUDE:
                raise BandejaLlena(f"la bandeja de Claude esta llena ({MAX_BANDEJA_CLAUDE}): espera a que la vacie")
            exps[nombre].update(fase="claude", motivo="Damian lo manda a Claude", actualizado=_ahora())
        return expedientes()[nombre]
    if accion not in ("aprobar", "rechazar"):
        raise ValueError(f"accion desconocida {accion!r}: aprobar, rechazar o claude")
    lineas = e.get("lineas") or _lineas_damian(e)
    descartar, mayoria = _mayoria(e)
    if e.get("reconsiderar"):
        from nucleo import reconsiderar
        no = set(range(len(e["propuestas"]))) if accion == "rechazar" else set(descartar)
        reconsiderar.aplicar(e, [p for i, p in enumerate(e["propuestas"]) if i not in no],
                             [p for i, p in enumerate(e["propuestas"]) if i in no],
                             f"Damian en la bandeja del tribunal: {lineas[0]}", "damian")
        e["decision"] = "APROBADO" if accion == "aprobar" else "DESCARTADO"
        _guardar_exp(e)
        _registrar(e, "damian", e["decision"], e.get("decision_tribunal") if e.get("vigilado") else None)
        return e
    if accion == "aprobar":
        props = {e["propuestas"][i]: "descartar" for i in descartar if i < len(e["propuestas"])}
        res = None
        if e["es_inv"]:
            eleccion = (resultado or (e.get("parcial") or {}).get("resultado", [None])[0] or mayoria or "").upper()
            res = (eleccion, "mayoria del tribunal y la apelacion, aprobado por Damian en su bandeja")
        revision.veredicto(nombre, "APROBADO", f"Damian en la bandeja del tribunal: {lineas[2]}", propuestas=props,
                           resultado=res, quien="damian")
        decision = "APROBADO"
    elif e.get("parcial"):
        res = None
        if e["es_inv"]:
            r0 = (e["parcial"].get("resultado") or [mayoria or "ADAPTAR"])[0]
            res = (r0, "RESULTADO del tribunal en la parte unanime; Damian descarta las propuestas divididas")
        revision.veredicto(nombre, "APROBADO", f"Damian descarta en su bandeja las propuestas divididas: {lineas[0]}",
                           propuestas={p: "descartar" for p in e["propuestas"]}, resultado=res, quien="damian")
        decision = "DESCARTADO"
    else:
        revision.veredicto(nombre, "DESCARTADO", f"Damian rechaza en la bandeja del tribunal: {lineas[0]}",
                           quien="damian")
        decision = "DESCARTADO"
    e.update(fase="resuelto", decision=decision, quien="damian", motivo="decidido por Damian")
    if decision == "APROBADO":
        e["marcadas_r3"] = _marcar_r3(e, "damian")
    _guardar_exp(e)
    _registrar(e, "damian", decision, e.get("decision_tribunal") if e.get("vigilado") else None)
    return e


def bandeja_claude() -> dict:
    # T860: lo resuelto con revision.veredicto (sin pasar por el tribunal) sale de la bandeja al leerla
    with _editar() as exps:
        _cerrar_fuera(exps)
    exps = expedientes()
    casos = []
    for e in sorted(exps.values(), key=lambda x: (x["fase"] != "claude", x["creado"])):
        cal = e.get("calibracion") or {}
        if e["fase"] in EN_CLAUDE:
            casos.append({"nombre": e["nombre"], "origen": e["origen"], "titulo": e.get("titulo", ""),
                          "tipo": e["tipo"], "es_inv": e["es_inv"], "motivo": e.get("motivo", ""),
                          "accion": "veredicto"})
        elif e["fase"] == "calibracion" and not cal.get("referencia"):
            # A CIEGAS: nada del tribunal (ni decision ni resumen) sale de aqui.
            casos.append({"nombre": e["nombre"], "origen": e["origen"], "titulo": e.get("titulo", ""),
                          "tipo": e["tipo"], "es_inv": e["es_inv"], "motivo": "calibracion: dictamen a ciegas",
                          "accion": "dictamen"})
    espera = sum(1 for e in exps.values() if e["fase"] == "espera_claude")
    return {"casos": casos[:MAX_BANDEJA_CLAUDE], "pendientes": min(len(casos), MAX_BANDEJA_CLAUDE),
            "maximo": MAX_BANDEJA_CLAUDE, "llena": len(casos) >= MAX_BANDEJA_CLAUDE, "en_espera": espera}


def orden_claude() -> str:
    return ORDEN_CLAUDE.read_text(encoding="utf-8")


# ------------------------------------------------------------------ calibracion
def historicos() -> list[tuple[str, str, str]]:
    """(borrador, origen, veredicto) de los veredictos de Claude ya dados, con el .md aun en disco."""
    salida = []
    for t in T.cargar()["tareas"]:
        et = t.get("etiquetas") or []
        if revision.ET_REVISION not in et or t["estado"] != "hecha":
            continue
        nombre = revision._et(t, revision.PRE_BORRADOR)
        texto = " ".join(n.get("texto", "") for n in t.get("notas") or [])
        m = next((m for m in _HIST.finditer(texto) if m.group(1) == nombre), None)
        if m and (revision.BORRADORES / nombre).is_file():
            salida.append((nombre, revision._et(t, revision.PRE_ORIGEN), m.group(2)))
    return sorted(salida, key=lambda x: x[0], reverse=True)


def sembrar(ids: list[str] | tuple[str, ...] = SIEMBRA_T667, total: int = SIEMBRA_TOTAL) -> dict:
    """Casos de calibracion: las investigaciones `ids` (Claude dictamina a ciegas) y, hasta `total`, veredictos
    historicos de Claude (referencia ya conocida, sin gastar Claude). Equilibra aprobados y rechazados."""
    r = {"nuevos": [], "historicos": [], "sin_borrador": []}
    with _editar() as exps:
        for tid in ids:
            t = T.buscar(tid)
            md = sorted(revision.BORRADORES.glob(f"{tid}_*.md")) if t and t["id"] == tid else []
            if not md:
                r["sin_borrador"].append(tid)
                continue
            if md[-1].name not in exps:
                exps[md[-1].name] = _nuevo(md[-1].name, tid, calibracion={"fuente": "siembra", "referencia": None})
            r["nuevos"].append(md[-1].name)
        hueco = max(0, total - len(r["nuevos"]))
        hist = [h for h in historicos() if h[0] not in exps]
        si = [h for h in hist if h[2] == "APROBADO"]
        no = [h for h in hist if h[2] != "APROBADO"]
        mezcla = [x for par in zip(si, no) for x in par] + si[len(no):] + no[len(si):]
        for nombre, origen, ver in mezcla[:hueco]:
            exps[nombre] = _nuevo(nombre, origen, calibracion={"fuente": "historico", "referencia": _norm(ver)})
            r["historicos"].append(nombre)
    return r


def dictamen_claude(nombre: str, decision: str, motivo: str, resultado: tuple[str, str] | None = None) -> dict:
    """Dictamen de Claude A CIEGAS sobre un caso de calibracion. Solo registra: la tarea origen no se toca."""
    decision = (decision or "").strip().upper()
    if decision not in ("APROBADO", "DESCARTADO", "REHACER"):
        raise ValueError("dictamen: APROBADO, DESCARTADO o REHACER")
    if len(" ".join((motivo or "").split())) < 15:
        raise ValueError("el dictamen necesita un motivo de verdad (minimo 15 caracteres)")
    e = expedientes().get(nombre)
    if e is None or e["fase"] != "calibracion":
        raise ValueError(f"{nombre} no es un caso de calibracion pendiente")
    if e["es_inv"] and decision == "APROBADO":
        if not resultado:
            raise ValueError("investigacion: APROBADO necesita --resultado ADOPTAR|ADAPTAR|DESCARTAR \"motivo\"")
        from nucleo import investigacion
        resultado = investigacion._validar(*resultado)
    e["calibracion"].update(referencia=_norm(decision), dictamen=decision, motivo=" ".join(motivo.split()),
                            resultado=list(resultado) if resultado else None, cuando=_ahora())
    if e.get("decision_tribunal"):
        _registrar(e, "siembra", decision, e["decision_tribunal"])
        e.update(fase="resuelto", motivo="calibracion registrada")
    _guardar_exp(e)
    return e


def registrar_resultado(nombre: str, fuente: str, correcto: bool) -> dict:
    """Calidad por resultados (F2/F3): puerta de fusion, revert o veto sobre una decision del tribunal."""
    if fuente not in ("puerta_fusion", "revert", "veto"):
        raise ValueError("fuente: puerta_fusion, revert o veto")
    e = expedientes().get(nombre)
    if e is None or e.get("quien") != "tribunal" or not e.get("decision"):
        raise ValueError(f"{nombre} no tiene una decision aplicada por el tribunal")
    ref = e["decision"] if correcto else ("DESCARTADO" if e["decision"] == "APROBADO" else "APROBADO")
    return _registrar(e, fuente, ref, e["decision"])


def readmitir(cid: str) -> list[str]:
    with _editar("estado.json") as est:
        est["excluidos"] = [x for x in est["excluidos"] if x != cid]
        return list(est["excluidos"])


# ------------------------------------------------------------------ panel
def metricas() -> dict:
    exps = expedientes()
    filas = _leer_calibracion()
    est = _estado()
    rev: dict[str, list[bool]] = {}
    for f in filas:
        for cid, ok in (f.get("revisores") or {}).items():
            rev.setdefault(cid, []).append(bool(ok))
    tipos: dict[str, list[bool]] = {}
    for f in filas:
        if f.get("tribunal"):
            tipos.setdefault(f["tipo"], []).append(f["tribunal"] == f["referencia"])
    cal = [e for e in exps.values() if e.get("calibracion")]
    return {
        "fases": dict(Counter(e["fase"] for e in exps.values())),
        "aplicados": dict(Counter(e["quien"] for e in exps.values() if e["fase"] == "resuelto" and e.get("quien"))),
        "revisores": [{"id": c.id, "familia": c.familia, "web": c.web, "casos": len(rev.get(c.id, [])),
                       "tasa": (sum(rev[c.id]) / len(rev[c.id])) if rev.get(c.id) else None,
                       "excluido": c.id in est["excluidos"]} for c in CANDIDATOS.values()],
        "tipos": [{"tipo": t, "casos": len(l[-VENTANA_TIPO:]), "tasa": sum(l[-VENTANA_TIPO:]) / len(l[-VENTANA_TIPO:]),
                   "vigilado": t in est["vigilados"]} for t, l in sorted(tipos.items())],
        "cupo": cupo_web(), "damian": bandeja_damian(), "claude": bandeja_claude(),
        "siembra": {"casos": len(cal), "registrados": sum(1 for e in cal if e["fase"] == "resuelto"),
                    "objetivo": SIEMBRA_TOTAL},
    }


# ------------------------------------------------------------------ CLI
# ------------------------------------------------------------------ tasa de aprobacion por autor (T675 fase 3)
CAMBIO_ORDEN_AUTOR = "2026-10-04"   # desde este dia los borradores los escribe primero NVIDIA/Groq, con las webs de respaldo
_VEREDICTO_NOTA = re.compile(r"Revision de (Claude|el tribunal|Damian) del borrador (\S+): (APROBADO|DESCARTADO|REHACER|SUPERADO)\b")
_AUTOR_VIEJO = re.compile(r"(?i)BORRADOR de ([a-z_]+)")


def _autor_borrador(nombre: str) -> str:
    try:
        cab = (revision.BORRADORES / nombre).read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
    except OSError:
        return "?"
    m = _AUTOR.search(cab) or _AUTOR_VIEJO.search(cab)
    return m.group(1).lower() if m else "?"


def tasa_por_autor(desde: str = CAMBIO_ORDEN_AUTOR) -> dict:
    """Tasa de APROBACION de los borradores por proveedor autor, antes y desde `desde` (AAAA-MM-DD): aprobados /
    (aprobados + descartados + rehacer). SUPERADO no cuenta (el borrador no se juzgo por su calidad). Cuenta los
    veredictos de Claude, del tribunal y de Damian: lo que mide es si el borrador sirvio, no quien lo juzgo.
    Es la medida con la que se decide, el 18/10 (T675), si el orden API-primero se queda o se revierte."""
    cuenta: dict[str, dict[str, dict[str, int]]] = {}
    for t in T.cargar()["tareas"]:
        if revision.ET_REVISION not in (t.get("etiquetas") or []):
            continue
        for n in t.get("notas") or []:
            m = _VEREDICTO_NOTA.search(n.get("texto", ""))
            if not m or m.group(3) == "SUPERADO":
                continue
            autor = _autor_borrador(m.group(2))
            epoca = "desde" if (n.get("cuando") or "")[:10] >= desde else "antes"
            c = cuenta.setdefault(autor, {"antes": {"n": 0, "aprobado": 0}, "desde": {"n": 0, "aprobado": 0}})[epoca]
            c["n"] += 1
            c["aprobado"] += m.group(3) == "APROBADO"
    for porque in cuenta.values():
        for c in porque.values():
            c["tasa"] = round(c["aprobado"] / c["n"], 3) if c["n"] else None
    return {"desde": desde, "autores": dict(sorted(cuenta.items()))}


def guardar_tasa_por_autor() -> dict:
    """Foto fechada en memoria/tribunal/tasa_autor.jsonl (una linea por llamada)."""
    foto = dict(tasa_por_autor(), cuando=_ahora())
    ruta = carpeta() / "tasa_autor.jsonl"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as f:
        f.write(json.dumps(foto, ensure_ascii=False) + "\n")
    return foto


def _cli(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, resto = argv[0], argv[1:]

    def opcion(nombre: str, defecto=None, n: int = 1):
        if nombre in resto:
            i = resto.index(nombre)
            vals = resto[i + 1:i + 1 + n]
            del resto[i:i + 1 + n]
            return vals if n > 1 else vals[0]
        return defecto

    salida = None
    if cmd == "ciclo":
        maximo = int(opcion("--max", "3"))
        simular = "--simular" in resto
        salida = ciclo(simular=simular, max_expedientes=maximo)
    elif cmd == "estado":
        salida = metricas()
    elif cmd == "bandeja_claude":
        salida = bandeja_claude()
    elif cmd == "bandeja_damian":
        salida = bandeja_damian()
    elif cmd == "sembrar":
        total = int(opcion("--total", str(SIEMBRA_TOTAL)))
        salida = sembrar(tuple(resto) or SIEMBRA_T667, total=total)
    elif cmd == "dictamen" and len(resto) >= 3:
        res = opcion("--resultado", None, 2)
        salida = dictamen_claude(resto[0], resto[1], resto[2], resultado=tuple(res) if res else None)
        salida = {k: salida[k] for k in ("nombre", "fase", "calibracion")}
    elif cmd == "resultado" and len(resto) == 3:
        salida = registrar_resultado(resto[0], resto[1], resto[2] == "correcto")
    elif cmd == "tasa_autor":
        salida = guardar_tasa_por_autor() if "--guardar" in resto else tasa_por_autor()
    elif cmd == "reencolar_r3":
        salida = reencolar_r3()
    elif cmd == "readmitir" and resto:
        salida = {"excluidos": readmitir(resto[0])}
    else:
        print(__doc__)
        return 1
    print(json.dumps(salida, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(_cli(sys.argv[1:]))
