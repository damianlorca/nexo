# -*- coding: utf-8 -*-
"""Vigia de novedades (T272, Damian 28/09): plantilla de turno que busca cada dia repos, modelos y herramientas
nuevas utiles para NEXO y las apunta como tareas 'propuesta' (via circuito T192).

Reglas de T272:
  1. Fuentes FIJAS y verificables (FUENTES): la busqueda de GitHub (repos creados hace poco), la biblioteca de
     Ollama (orden "newest"), los modelos gratis de OpenRouter, los modelos de NVIDIA build y de Groq (/models)
     y el changelog de la API de Gemini. Se leen con codigo, no con una IA: nada inventado.
  2. Deduplicar contra tareas.json, el catalogo de herramientas y lo ya visto (memoria/vigia/vistos.json).
     Las fuentes sin fecha (NVIDIA, Groq, Ollama) la primera vez solo guardan la linea base.
  3. Lo que queda va como material de UNA tarea-lote del dia; la IA (gratis/local, nunca Claude) elige como
     mucho 5 y cada una sale como PROPUESTA -> tarea 'propuesta' que Claude revisa antes de nada (T192).
  4. Tope: un lote al dia (hecho_hoy) y como mucho MAX_CANDIDATOS en el material.
  5. Resumen semanal: resumen_semanal() (lo pinta la web en /turnos).
La ChatGPT web no tiene un changelog legible sin navegador: queda fuera (dicho en el resumen).
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from nucleo import tareas as T

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "memoria" / "vigia"
MAX_CANDIDATOS = 40
DIAS_NUEVO = 14
TIMEOUT = 20
UA = {"User-Agent": "NEXO-vigia/1.0 (asistente personal; lectura publica)", "Accept": "application/json"}
CONSULTAS_GITHUB = ("ai agent framework", "llm orchestration", "agent memory", "claude code skills", "mcp server")
PAUSA_GITHUB = 7            # s entre consultas de busqueda (limite sin clave: 10 por minuto)


def _get(url: str, cabeceras: dict | None = None, params: dict | None = None):
    import httpx
    return httpx.get(url, headers={**UA, **(cabeceras or {})}, params=params, timeout=TIMEOUT, follow_redirects=True)


# ------------------------------------------------------------------ fuentes
def fuente_github(ahora: datetime) -> list[dict]:
    """Busqueda de GitHub sin clave (limite ~10/min): consultas espaciadas; si alguna cae se sigue con las demas
    (28/09: la 6.a consulta seguida dio 403 rate limit). Solo falla si caen todas."""
    desde = (ahora - timedelta(days=DIAS_NUEVO)).strftime("%Y-%m-%d")
    salida, errores = [], []
    for i, q in enumerate(CONSULTAS_GITHUB):
        if i:
            time.sleep(PAUSA_GITHUB)
        try:
            r = _get("https://api.github.com/search/repositories", {"Accept": "application/vnd.github+json"},
                     {"q": f"{q} created:>{desde}", "sort": "stars", "order": "desc", "per_page": 6})
            r.raise_for_status()
        except Exception as e:
            errores.append(f"{q}: {type(e).__name__}")
            continue
        for it in r.json().get("items", []):
            salida.append({"fuente": "github", "id": it["full_name"], "nombre": it["full_name"],
                           "url": it["html_url"], "fecha": (it.get("created_at") or "")[:10],
                           "descripcion": f"{(it.get('description') or '')[:200]} ({it.get('stargazers_count', 0)} estrellas)"})
    if errores and len(errores) == len(CONSULTAS_GITHUB):
        raise RuntimeError("todas las consultas fallaron: " + "; ".join(errores)[:150])
    return list({x["id"]: x for x in salida}.values())


def fuente_ollama(ahora: datetime) -> list[dict]:
    r = _get("https://ollama.com/library?sort=newest", {"Accept": "text/html"})
    r.raise_for_status()
    nombres = list(dict.fromkeys(re.findall(r'href="/library/([\w.\-]+)"', r.text)))[:25]
    return [{"fuente": "ollama", "id": n, "nombre": n, "url": f"https://ollama.com/library/{n}", "fecha": "",
             "descripcion": "modelo en la biblioteca de Ollama (orden: mas nuevos)"} for n in nombres]


def fuente_openrouter(ahora: datetime) -> list[dict]:
    r = _get("https://openrouter.ai/api/v1/models")
    r.raise_for_status()
    limite = (ahora - timedelta(days=DIAS_NUEVO)).timestamp()
    salida = []
    for m in r.json().get("data", []):
        if str(m.get("id", "")).endswith(":free") and float(m.get("created") or 0) >= limite:
            salida.append({"fuente": "openrouter", "id": m["id"], "nombre": m.get("name") or m["id"],
                           "url": f"https://openrouter.ai/{m['id']}",
                           "fecha": datetime.fromtimestamp(float(m["created"])).strftime("%Y-%m-%d"),
                           "descripcion": (m.get("description") or "")[:200]})
    return salida


def _modelos_openai(url: str, clave: str, fuente: str, web: str) -> list[dict]:
    if not clave:
        return []
    r = _get(url, {"Authorization": f"Bearer {clave}"})
    r.raise_for_status()
    return [{"fuente": fuente, "id": m["id"], "nombre": m["id"], "url": web.format(id=m["id"]),
             "fecha": datetime.fromtimestamp(m["created"]).strftime("%Y-%m-%d") if m.get("created") else "",
             "descripcion": f"modelo disponible en {fuente}"} for m in r.json().get("data", []) if m.get("id")]


def fuente_nvidia(ahora: datetime) -> list[dict]:
    from proveedores import NvidiaProvider
    return _modelos_openai("https://integrate.api.nvidia.com/v1/models", NvidiaProvider()._clave(), "nvidia",
                           "https://build.nvidia.com/{id}")


def fuente_groq(ahora: datetime) -> list[dict]:
    from proveedores import GroqProvider
    return _modelos_openai("https://api.groq.com/openai/v1/models", GroqProvider()._clave(), "groq",
                           "https://console.groq.com/docs/models#{id}")


def fuente_gemini_changelog(ahora: datetime) -> list[dict]:
    r = _get("https://ai.google.dev/gemini-api/docs/changelog", {"Accept": "text/html"})
    r.raise_for_status()
    salida = []
    for m in list(re.finditer(r"<h2[^>]*>(.*?)</h2>(.*?)(?=<h2|\Z)", r.text, re.S))[:4]:
        titulo = re.sub(r"<[^>]+>|\s+", " ", m.group(1)).strip()
        cuerpo = re.sub(r"<[^>]+>|\s+", " ", m.group(2)).strip()
        if titulo:
            salida.append({"fuente": "gemini_changelog", "id": titulo, "nombre": f"Gemini API: {titulo}",
                           "url": "https://ai.google.dev/gemini-api/docs/changelog", "fecha": titulo,
                           "descripcion": cuerpo[:300]})
    return salida


FUENTES = {"github": fuente_github, "ollama": fuente_ollama, "openrouter": fuente_openrouter,
           "nvidia": fuente_nvidia, "groq": fuente_groq, "gemini_changelog": fuente_gemini_changelog}
SIN_FECHA = ("ollama", "nvidia", "groq", "gemini_changelog")   # la primera vez: solo linea base


# ------------------------------------------------------------------ estado
def _leer(nombre: str, defecto):
    try:
        return json.loads((CARPETA / nombre).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def _escribir(nombre: str, datos) -> Path:
    from nucleo.escritura import escribir_atomico
    CARPETA.mkdir(parents=True, exist_ok=True)
    escribir_atomico(CARPETA / nombre, json.dumps(datos, ensure_ascii=False, indent=1))
    return CARPETA / nombre


def hecho_hoy(ahora: datetime | None = None) -> bool:
    ahora = ahora or datetime.now()
    return _leer("estado.json", {}).get("ultimo_dia") == ahora.strftime("%Y-%m-%d")


def _conocido() -> str:
    """Texto (minusculas) de tareas y catalogo para deduplicar."""
    partes = [f"{t.get('titulo', '')} {t.get('detalle', '')}" for t in T.cargar()["tareas"]]
    try:
        from nucleo import catalogo as C
        partes += [f"{x.get('nombre', '')} {x.get('identidad', '')}" for x in C.cargar().get("herramientas", [])]
    except Exception:
        pass
    return " ".join(partes).lower()


def _clave_corta(it: dict) -> str:
    """Nombre corto para deduplicar: 'org/repo' -> 'repo'; 'org/modelo:free' -> 'modelo'."""
    return it["id"].lower().split(":")[0].split("/")[-1]


def recoger(ahora: datetime | None = None, fuentes: dict | None = None) -> dict:
    """Lee las fuentes, deduplica y actualiza lo visto. {candidatos, por_fuente, errores, linea_base}."""
    ahora = ahora or datetime.now()
    vistos = _leer("vistos.json", {})
    conocido = _conocido()
    candidatos, por_fuente, errores, base = [], {}, {}, []
    for nombre, fn in (fuentes or FUENTES).items():
        try:
            items = fn(ahora)
        except Exception as e:   # una fuente caida no tumba el resto
            errores[nombre] = f"{type(e).__name__}: {e}"[:200]
            continue
        ya = set(vistos.get(nombre) or [])
        primera = nombre not in vistos and nombre in SIN_FECHA
        nuevos = [it for it in items if it["id"] not in ya]
        vistos[nombre] = sorted(ya | {it["id"] for it in items})[-2000:]
        if primera:
            base.append(nombre)
            por_fuente[nombre] = 0
            continue
        utiles = [it for it in nuevos if len(_clave_corta(it)) < 4 or _clave_corta(it) not in conocido]
        por_fuente[nombre] = len(utiles)
        candidatos += utiles
    _escribir("vistos.json", vistos)
    return {"candidatos": candidatos[:MAX_CANDIDATOS], "por_fuente": por_fuente, "errores": errores,
            "linea_base": base, "descartados_por_tope": max(0, len(candidatos) - MAX_CANDIDATOS)}


def crear_lote(ahora: datetime | None = None, fuentes: dict | None = None) -> dict | None:
    """Recoge y crea la tarea-lote de hoy (None si no hay nada nuevo). Marca el dia como hecho."""
    ahora = ahora or datetime.now()
    r = recoger(ahora, fuentes)
    terminos_hoy = _terminos(ahora) if fuentes is None else {}   # T550; con fuentes de prueba, nada de red
    dia = ahora.strftime("%Y-%m-%d")
    archivo = _escribir(f"lote_{ahora:%Y%m%d}.json", dict(r, dia=dia))
    estado = _leer("estado.json", {})
    estado.update(ultimo_dia=dia, ultimo=dict(por_fuente=r["por_fuente"], errores=r["errores"],
                                              linea_base=r["linea_base"], candidatos=len(r["candidatos"]),
                                              terminos=terminos_hoy))
    _escribir("estado.json", estado)
    if not r["candidatos"]:
        return None
    from nucleo.plantillas_turno import ET_LOTE, PRE_PLANTILLA
    lote = T.anadir(
        f"Vigia de novedades {ahora:%d/%m}: {len(r['candidatos'])} candidatos",
        detalle=(f"Tarea creada por el turno (plantilla vigia, T272). Fuentes: "
                 + ", ".join(f"{k} {v}" for k, v in r["por_fuente"].items())
                 + (f". Caidas: {', '.join(r['errores'])}" if r["errores"] else "")
                 + f".\nLOTE: {archivo.name}"),
        importancia=3, urgencia=2, dificultad=1, coste=1, depende="ia",
        etiquetas=["cat:investigacion", "material:interno", "extension:normal", f"{PRE_PLANTILLA}vigia", ET_LOTE])
    previos = _descartados(r["candidatos"])
    if previos:   # T688 pieza 3: solo avisa; el lote se valora igual
        from nucleo import descartes
        T.anotar(lote["id"], "Aviso T688: candidatos ya DESCARTADOS antes: " + " · ".join(
            f"{n} ~ {descartes.texto_aviso(p)}" for n, p in previos.items())[:1500])
    return lote


def _terminos(ahora: datetime) -> dict:
    """T550: terminos de uso de Gemini/Google y OpenAI (nucleo/terminos.py). Nunca tumba el lote."""
    try:
        from nucleo import terminos
        return terminos.comprobar(ahora)
    except Exception as e:   # noqa: BLE001
        return {"error": type(e).__name__}


def _descartados(candidatos: list[dict]) -> dict:
    try:
        from nucleo import descartes
        return descartes.avisos_candidatos(candidatos)
    except Exception as e:   # el aviso es accesorio: nunca tumba el lote
        import logging
        logging.getLogger(__name__).warning("aviso de descartes fallo: %s", type(e).__name__)
        return {}


def texto_lote(detalle: str) -> str:
    m = re.search(r"LOTE:\s*(lote_\d{8}\.json)", detalle or "")
    datos = _leer(m.group(1), {}) if m else {}
    cands = datos.get("candidatos", [])
    previos = _descartados(cands)
    lineas = [f"- [{c['fuente']}] {c['nombre']} | {c['url']} | {c.get('fecha') or 'sin fecha'} | {c.get('descripcion', '')}"
              + (f" | YA DESCARTADO ANTES: {previos[c['nombre']][0]['id']} ({previos[c['nombre']][0]['motivo'][:160]})"
                 if c["nombre"] in previos else "")
              for c in cands]
    return "\n".join(lineas) or "(lista vacia)"


def resumen_semanal(ahora: datetime | None = None) -> dict:
    """Lotes del vigia de los ultimos 7 dias con sus propuestas (para la web)."""
    ahora = ahora or datetime.now()
    desde = (ahora - timedelta(days=7)).strftime("%Y-%m-%d")
    todas = T.cargar()["tareas"]
    lotes = []
    for t in todas:
        if "plantilla:vigia" not in (t.get("etiquetas") or []) or (t.get("creada") or "")[:10] < desde:
            continue
        from nucleo import revision
        props = [p for p in todas if f"{revision.PRE_ORIGEN}{t['id']}" in (p.get("etiquetas") or [])
                 and revision.ET_PROPUESTA in (p.get("etiquetas") or [])]
        lotes.append({"id": t["id"], "titulo": t["titulo"], "creada": t.get("creada", ""), "estado": t["estado"],
                      "propuestas": [{"id": p["id"], "titulo": p["titulo"], "estado": p["estado"]} for p in props]})
    return {"desde": desde, "lotes": sorted(lotes, key=lambda x: x["creada"], reverse=True),
            "ultimo": _leer("estado.json", {}).get("ultimo")}
