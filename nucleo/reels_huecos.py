# -*- coding: utf-8 -*-
"""T859 bloque 6, paso 7: huecos que solo puede cubrir Damian (REELS.md, "Huecos que solo puede cubrir Damian").

Muchos reels piden "comenta PALABRA y te mando la guia/el repo/el prompt". Aqui, sin IA y sobre la ficha ya resuelta:
  1. evaluar(ficha)  hay llamada (comenta X / DM / link in bio / te lo mando por privado) y QUE promete enviar;
                     se intenta cubrir en publico: si todo lo prometido ya esta identificado (repo resuelto, URL
                     publica, la ficha completa), NO hace falta Damian ("cubierto en publico").
                     Solo si falta algo ESENCIAL (faltan elementos de la promesa, un repo sin identificar, el reel no
                     nombra lo que promete, o el valor esta en un prompt/plantilla/guia privada) sale un hueco.
  2. tanda(...)      UNA tarjeta por tanda con como mucho MAX_TANDA reels, ordenados por valor: enlace al reel,
                     palabra exacta, cuenta a la que comentar, que se espera y por que hace falta.
  3. pegar(...)      lo que Damian pegue se guarda en la capa bruta del reel como contenido NO confiable (solo dato:
                     nunca se ejecuta ni se instala nada de ahi sin N04) y el reel queda marcado para reprocesar
                     (lo recoge el lote; la ficha se rehace con lo pegado). "No merece la pena" lo cierra.
NEXO nunca comenta ni escribe desde la cuenta de Damian: la tarjeta solo le dice que hacer a el.

REGLA DE DAMIAN (T966, 17/10): solo se le pide comentar o mirar un reel cuando la informacion VALE LA PENA y NEXO no
la puede conseguir por su cuenta. Unos repos con nombre y descripcion NO son hueco (se buscan por nombre y descripcion
en GitHub). Cuando si lo es, sale una TAREA suya (tarea_hueco): el reel, que comentar y que informacion devolver.
Almacen privado: memoria/perfil_privado/reels/huecos.json.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from nucleo import reels_calidad as C
from nucleo.config import RAIZ

ALMACEN = RAIZ / "memoria" / "perfil_privado" / "reels" / "huecos.json"
MAX_TANDA = 10
MAX_PEGADO = 20000
ESTADOS = ("pendiente", "pegado", "no_merece")
VALOR_CAT = {"nexo": 5, "ia_prompts": 4, "herramientas": 4, "trading": 3, "carrera": 3, "diseno": 3, "negocio": 2,
             "contenido": 2, "sin_clasificar": 1}
# Lo que vale por si mismo y no se publica: un prompt, una plantilla... Una "guia para instalarlo" o "el enlace" de
# algo ya identificado NO cuenta (NEXO lee la documentacion oficial; bloque 6, caso Recordly).
_PRIVADO = re.compile(r"(?i)prompt|plantilla|template|notion|pdf|checklist|workflow|ebook|e-book|hoja de c[aá]lculo|"
                      r"spreadsheet|plugin propio|c[oó]digo fuente privado|base de datos propia")

# Bloque 10 (Damian 17/10): NO es hueco lo prometido que una IA puede reproducir con lo que el reel YA ensena (los prompts
# de unos mods que el reel explica uno por uno: Claude los crea). SI lo es lo que solo tiene el autor: datos,
# archivos propios, accesos. Las listas y enlaces de cosas que el reel nombra las cubre el resto de la evaluacion (faltan N de los
# prometidos, repos sin identificar, "el reel no nombra lo que promete").
_SOLO_AUTOR = re.compile(r"(?i)\bdatos\b|\bdata(set)?s?\b|cifras|"
                         r"hoja de c[aá]lculo|spreadsheet|excel|c[oó]digo fuente privado|base de datos propia|plugin propio|"
                         r"\bcurso\b|\bcourse\b|cup[oó]n|descuento|discount|\bacceso\b|\baccess\b|contrase")
_REPRODUCIBLE = re.compile(r"(?i)prompt|plantilla|template|workflow|checklist|paso a paso|step[- ]by[- ]step|"
                           r"\bgu[ií]a\b|\bguide\b")
_ENSENADOS = {"herramienta", "tecnica", "idea_proyecto", "repo", "modelo", "consejo", "web"}


from nucleo.reels_publico import ES_PAPER as _PAPER   # noqa: E402


INTERES_MIN = 3     # VALOR_CAT minimo para molestar a Damian (negocio, contenido y sin clasificar no llegan)
MIN_DESCRIPCION = 25  # caracteres de descripcion (pantalla o ficha) para poder buscar un repo por nombre + descripcion


def _describe(e: dict) -> bool:
    """El reel da nombre Y descripcion del elemento: NEXO lo puede buscar por su cuenta."""
    texto = (e.get("que_es") or "") + (e.get("descripcion_pantalla") or "") + (e.get("descripcion_pie") or "")
    return len(re.sub(r"\W+", "", texto)) >= MIN_DESCRIPCION


def _ensenado(elems: list[dict]) -> list[dict]:
    """Elementos que el reel ya explica con descripcion propia: lo que una IA necesita para reproducir un prompt."""
    return [e for e in elems if e.get("tipo") in _ENSENADOS and e.get("origen") not in ("citas", "busqueda", "afirmacion")
            and len(re.sub(r"\W+", "", (e.get("que_es") or "") + (e.get("descripcion_pantalla") or ""))) >= MIN_DESCRIPCION]


def privado_de(promete: str, elems: list[dict]) -> str:
    """'' (no es privado) | 'autor' (solo lo tiene el autor) | 'reproducible' (una IA lo crea con lo que ensena el reel)."""
    if not _PRIVADO.search(promete) and not _SOLO_AUTOR.search(promete):
        return ""
    if _SOLO_AUTOR.search(promete):
        return "autor"
    return "reproducible" if _REPRODUCIBLE.search(promete) and _ensenado(elems) else "autor"


def _resuelto(e: dict) -> bool:
    r = e.get("resolucion") or {}
    if e.get("tipo") == "repo" and r.get("existe") is not False and _describe(e):
        return True        # T966: nombre + descripcion = NEXO lo busca (aunque hoy no se haya resuelto)
    return bool(r.get("existe")) or bool(e.get("url") and r.get("existe") is not False)


def evaluar(ficha: dict) -> dict:
    """{"hay": False} | {"hay": True, "cubierto": True, "motivo"} | {"hay": True, "cubierto": False, "faltas", "valor"}"""
    ll = ficha.get("llamada") or {}
    if not ll.get("hay"):
        return {"hay": False}
    faltas = []
    c = ficha.get("completitud") or {}
    if c.get("faltan"):
        faltas.append(f"faltan {c['faltan']} de los {c.get('prometidos')} prometidos")
    elems = ficha.get("elementos") or []
    sin = [e["nombre"] for e in elems if e.get("tipo") == "repo" and e.get("origen") != "citas" and not _resuelto(e)]
    if sin:
        faltas.append("sin identificar en publico: " + ", ".join(sin[:8]))
    utiles = [e for e in elems if e.get("tipo") != "consejo" and e.get("origen") != "afirmacion"]
    promete = ll.get("promete") or ""
    if _PAPER.search(promete) and not ll.get("nombrado_en_publico"):
        # un paper no lo cubre un 'dato' suelto (un indice, un organismo, "un paper del NY Fed") ni una cuenta: hace
        # falta un localizador real (URL; la busqueda publica lo anade con origen 'busqueda')
        utiles = [e for e in utiles if e.get("origen") == "busqueda" or (e.get("url") and e.get("tipo") != "dato")]
    if not utiles:
        faltas.append("el reel no nombra lo que promete")
    privado = "" if ll.get("nombrado_en_publico") else privado_de(promete, elems)
    if utiles and privado == "autor":
        faltas.append(f"el valor esta en material privado ({C.recortar(promete, 80)})")
    if not faltas:
        nombres = ", ".join(e.get("nombre") for e in utiles[:5])
        if privado == "reproducible":
            return {"hay": True, "cubierto": True,
                    "motivo": f"lo prometido ({C.recortar(promete, 80)}) lo puede reproducir una IA con lo que el reel ya "
                              f"ensena ({nombres}): no hace falta pedirselo al autor"}
        return {"hay": True, "cubierto": True,
                "motivo": f"lo prometido ya esta identificado en publico ({nombres}); NEXO lee la documentacion oficial"}
    cats = {x for e in elems for x in e.get("categorias") or []} or {"sin_clasificar"}
    interes = max(VALOR_CAT.get(x, 1) for x in cats)
    if interes < INTERES_MIN and cats != {"sin_clasificar"}:          # T966: la informacion no vale la pena como para pedirsela a Damian
        return {"hay": True, "cubierto": True,
                "motivo": "lo que falta no merece molestar a Damian (tema de poco interes para NEXO)"}
    valor = interes * 2 + min(int(c.get("faltan") or 0), 5) + min(len(sin), 3)
    return {"hay": True, "cubierto": False, "faltas": faltas, "valor": valor}


def hueco(ficha: dict) -> dict | None:
    """La fila de la tarjeta (o None si no hace falta Damian)."""
    ev = evaluar(ficha)
    if not ev.get("hay") or ev.get("cubierto"):
        return None
    ll = ficha.get("llamada") or {}
    if ll.get("tipo") == "bio":
        accion = f"abrir el enlace de la bio de @{ficha.get('autor')}"
    elif ll.get("tipo") == "dm":
        accion = f"mandar un DM a @{ficha.get('autor')}" + (f" con «{ll['palabra']}»" if ll.get("palabra") else "")
    else:
        accion = f"comentar «{ll.get('palabra') or '?'}» en el reel de @{ficha.get('autor')}"
    fila = {"codigo": ficha.get("codigo"), "url": ficha.get("url"), "autor": ficha.get("autor"),
            "palabra": ll.get("palabra"), "tipo": ll.get("tipo"), "accion": accion,
            "espera": ll.get("promete") or "lo que promete el reel", "por_que": "; ".join(ev["faltas"]),
            "tema": ficha.get("tema"), "valor": ev["valor"],
            "devolver": ("la lista/enlace de lo prometido tal como te llegue: " + (ll.get("promete") or "lo prometido")
                         + " (pegarlo en el hueco del reel)")}
    bp = ficha.get("busqueda_publica") or {}
    if bp.get("candidatos") and not bp.get("aceptado"):     # T890: se busco en publico y no hubo nada fiable
        fila["candidatos"] = [f"{C.recortar(c['titulo'], 80)} ({c.get('anio') or 's/f'}) {c['url']}" for c in bp["candidatos"][:2]]
    return fila


def tarea_hueco(h: dict) -> dict:
    """T966: la tarea de Damian para un hueco real. Privacidad (T859): a tareas.json no va la URL ni el codigo del reel;
    el reel se abre desde su tarjeta en Bandejas (huecos.json, privado)."""
    autor = h.get("autor") or "?"
    detalle = [f"Reel de @{autor} (tema: {h.get('tema') or 'sin tema'}). El enlace esta en la tarjeta de huecos "
               f"de Bandejas (privada).",
               f"Que hacer: {h['accion']}.",
               f"Que comentar: {('«' + h['palabra'] + '»') if h.get('palabra') else 'segun el reel (' + str(h.get('tipo')) + ')'}.",
               f"Que informacion devolver: {h.get('devolver') or h.get('espera')}.",
               f"Por que hace falta (NEXO no lo consigue solo): {h.get('por_que')}."]
    if h.get("candidatos"):
        detalle.append("Lo mas cercano que encontro NEXO (sin verificar): " + "; ".join(h["candidatos"]))
    detalle.append("NEXO nunca comenta ni escribe desde tu cuenta; lo que pegues se guarda como dato no confiable.")
    return {"tipo": "hueco_damian", "titulo": C.recortar(f"Para Damian: {h['accion']}", 110), "detalle": "\n".join(detalle),
            "importancia": max(2, min(5, int(h.get("valor", 6)) // 3)),
            "etiquetas": ["cat:personal", "origen:reels", "hueco:reel"], "depende": "damian",
            "reel": h.get("codigo"), "tema": h.get("tema") or "", "elementos": []}


# ------------------------------------------------------------------ almacen y tarjeta
def cargar(ruta: Path | None = None) -> dict:
    ruta = ruta or ALMACEN
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"huecos": {}, "tandas": []}


def _guardar(datos: dict, ruta: Path | None = None) -> None:
    ruta = ruta or ALMACEN
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ruta)


def tanda(huecos: list[dict], maximo: int = MAX_TANDA) -> list[dict]:
    return sorted(huecos, key=lambda h: (-h["valor"], h.get("codigo") or ""))[:maximo]


def registrar(fichas: list[dict], ahora: datetime | None = None, ruta: Path | None = None,
              escribir: bool = True) -> dict:
    """Huecos nuevos de estas fichas -> UNA tarjeta (tanda) con los MAX_TANDA de mas valor. Lo ya decidido (pegado,
    no merece la pena) no vuelve a salir. Con escribir=False solo devuelve la tarjeta (supervision)."""
    ahora = ahora or datetime.now()
    datos = cargar(ruta)
    nuevos = [h for h in (hueco(f) for f in fichas) if h and h["codigo"] not in datos["huecos"]]
    elegidos = tanda(nuevos)
    tarjeta = {"id": f"H{ahora:%Y%m%d%H%M}", "cuando": ahora.isoformat(timespec="seconds"),
               "reels": [h["codigo"] for h in elegidos], "fuera_de_tanda": len(nuevos) - len(elegidos)}
    if escribir and elegidos:
        for h in elegidos:
            datos["huecos"][h["codigo"]] = dict(h, estado="pendiente", tanda=tarjeta["id"])
        datos["tandas"].append(tarjeta)
        _guardar(datos, ruta)
    return {"tarjeta": tarjeta, "filas": elegidos}


def pendientes(ruta: Path | None = None) -> list[dict]:
    """Lo que pinta la bandeja de Damian: los huecos pendientes de la tanda mas reciente primero."""
    datos = cargar(ruta)
    filas = [h for h in datos["huecos"].values() if h.get("estado") == "pendiente"]
    return sorted(filas, key=lambda h: (h.get("tanda") or "", h["valor"]), reverse=True)


def _decidir(codigo: str, estado: str, ruta: Path | None, **campos) -> dict:
    datos = cargar(ruta)
    h = datos["huecos"].get(codigo)
    if h is None:
        raise KeyError(codigo)
    if h.get("estado") != "pendiente":
        raise ValueError(f"{codigo} ya esta {h.get('estado')}")
    h.update(estado=estado, decidido=datetime.now().isoformat(timespec="seconds"), **campos)
    _guardar(datos, ruta)
    return h


def pegar(codigo: str, texto: str, ruta: Path | None = None, carpeta: Path | None = None) -> dict:
    """Guarda lo pegado en la capa bruta del reel (no confiable, solo dato) y lo marca para reprocesar."""
    from extremidades import reels
    limpio = (texto or "").replace("\x00", "").strip()[:MAX_PEGADO]
    if not limpio:
        raise ValueError("no hay nada pegado")
    carpeta = carpeta or reels.CARPETA
    ruta_bruto = carpeta / f"{codigo}.json"
    bruto = json.loads(ruta_bruto.read_text(encoding="utf-8")) if ruta_bruto.exists() else {}
    bruto.pop("anteriores", None)
    bruto.setdefault("pegado", []).append({"texto": limpio, "cuando": datetime.now().isoformat(timespec="seconds"),
                                           "fuente": "damian", "confiable": False})
    bruto["reprocesar"] = True
    bruto.pop("codigo", None)
    bruto.pop("guardado", None)
    reels.guardar_bruto(codigo, bruto, carpeta=carpeta)
    return _decidir(codigo, "pegado", ruta, caracteres=len(limpio))


def no_merece(codigo: str, motivo: str = "", ruta: Path | None = None) -> dict:
    return _decidir(codigo, "no_merece", ruta, motivo=motivo[:300])


def tarjeta_md(r: dict) -> str:
    filas = r["filas"]
    if not filas:
        return "Sin tarjeta: ningún reel necesita a Damián (todo lo prometido se cubre en público o no hay llamada)."
    lineas = [f"**Tarjeta {r['tarjeta']['id']}** — {len(filas)} reel(es), por valor"
              + (f" (+{r['tarjeta']['fuera_de_tanda']} para la siguiente)" if r["tarjeta"]["fuera_de_tanda"] else ""), ""]
    for i, h in enumerate(filas, 1):
        extra = (" · buscado en público sin acierto seguro; lo más cercano (sin verificar): " + "; ".join(h["candidatos"])
                 if h.get("candidatos") else "")
        lineas.append(f"{i}. [{h['autor']}]({h['url']}) · {h['accion']} · se espera: {h['espera']} · por qué: "
                      f"{h['por_que']}{extra} · valor {h['valor']}  → [campo para pegar] [Pegado] [No merece la pena]")
    return "\n".join(lineas)
