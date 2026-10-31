# -*- coding: utf-8 -*-
"""T251: el GRAFO de NEXO (tareas, propuestas, revisiones de Claude, borradores, turnos e IAs).

Solo LEE. Sale en formato node-link de NetworkX, el mismo del graph.json de Graphify (T250):
{"directed", "multigraph", "graph", "nodes", "links"}. La vista es rutas/grafo.py + estatico/grafo.js.

Aristas SOLO con relaciones que ya estan guardadas (T252); nada se deduce de textos libres:
  bloqueada_por = Txxx           tarea -> tarea         "espera a"
  tarea_origen:Txxx              origen -> propuesta/revision   "ha generado"
  de_borrador:<archivo>          borrador -> propuesta "propone"; revision -> borrador "revisa"
  nombre del borrador Txxx_...   tarea -> borrador      "tiene el borrador"
  cabecera del borrador          borrador -> IA         "escrito por" / "revisado por"
  conversaciones "ia:rol"        tarea -> IA            "delegada a"
  registros/turno_nexo_*.json    turno -> tarea         "trabajó en"
  junto_a:Txxx / bloque:Txxx     tarea -> tarea         "va junto a"
  depende = damian               tarea -> Tú            "te toca a ti"
Un bloqueada_por que no es un id, o un id que ya no existe, no crea arista.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from interfaz import humano as H
from nucleo import registro, revision, trabajo
from nucleo import tareas as T

MAX_TITULO_ETIQUETA = 38
MAX_TURNOS = 200            # registros de turno leidos (los mas nuevos)

TIPOS = {
    "tarea": "Tarea", "propuesta": "Propuesta", "revision": "Revisión de Claude",
    "borrador": "Borrador", "turno": "Turno", "ia": "IA o persona",
}
# tipo de arista -> (como se lee desde el origen, como se lee desde el destino)
RELACIONES = {
    "espera": ("espera a", "la está esperando"),
    "origen": ("ha generado", "nace de"),
    "propone": ("propone", "sale del borrador"),
    "revisa": ("revisa", "lo revisa"),
    "borrador": ("tiene el borrador", "es el borrador de"),
    "escrito": ("escrito por", "escribió"),
    "revisado": ("revisado por", "revisó"),
    "delegada": ("delegada a", "trabajó en"),
    "turno": ("trabajó en", "la trabajó el"),
    "junto": ("va junto a", "va junto a"),
    "damian": ("te toca a ti", "te toca"),
}
# Veredicto de Claude sobre un borrador -> (estado en palabras, frase, clase de color, grupo del filtro)
ESTADOS_BORRADOR = {
    "APROBADO": ("Aprobado por Claude", "Claude lo revisó y lo dio por bueno.", "comprobada", "hechas"),
    "DESCARTADO": ("Descartado por Claude", "Claude lo revisó y no vale.", "descartada", "descartadas"),
    "REHACER": ("Claude pidió rehacerlo", "Vuelve a NEXO con correcciones.", "atascada", "atascadas"),
    "SUPERADO": ("Superado", "El trabajo se hizo por otra vía.", "descartada", "descartadas"),
    "esperando": ("Esperando a Claude", "Claude todavía no lo ha revisado.", "sin-comprobar", "sin_comprobar"),
    "sustituido": ("Sustituido", "Llegó un borrador más nuevo de la misma tarea.", "descartada", "descartadas"),
    "sin": ("Sin revisión de Claude", "Es de antes del circuito de revisión (T192) o no pasó por él.",
            "sin-comprobar", "sin_comprobar"),
}

_ID = re.compile(r"^T\d+$")
_NOMBRE_BORRADOR = re.compile(r"^(T\d+)_(\d{8})_(\d{4})\.md$")
_VEREDICTO = re.compile(r"Revision de Claude del borrador (\S+?): (APROBADO|DESCARTADO|REHACER|SUPERADO)\b")
_AUTOR = re.compile(r"(?:BORRADOR de|autor)\s+([A-Za-z_]+)")
_REVISORES = re.compile(r"revisor(?:es)?\s+([^|]+)")


def _corto(texto: str, n: int = MAX_TITULO_ETIQUETA) -> str:
    texto = " ".join((texto or "").split())
    return texto if len(texto) <= n else texto[:n - 1].rstrip() + "…"


def clave_ia(texto: str) -> str:
    """'gemini (Pro)' -> 'gemini'; 'ninguno' o desconocida -> ''."""
    m = re.match(r"\s*([A-Za-z_]+)", texto or "")
    clave = m.group(1).lower() if m else ""
    return clave if clave in H.PROVEEDORES else ""


def _et(t: dict, prefijo: str) -> list[str]:
    return [e[len(prefijo):] for e in t.get("etiquetas") or [] if e.startswith(prefijo)]


def _tipo(t: dict) -> str:
    et = t.get("etiquetas") or []
    if revision.ET_REVISION in et:
        return "revision"
    return "propuesta" if revision.ET_PROPUESTA in et else "tarea"


def _fecha(texto: str | None) -> str:
    return (texto or "")[:10]


def _cabecera(ruta: Path) -> str:
    try:
        with ruta.open(encoding="utf-8", errors="replace") as f:
            return f.readline(600)
    except OSError:
        return ""


def ias_de_cabecera(linea: str) -> tuple[str, list[str]]:
    """(autor, [revisores]) de la primera linea de un borrador ('<!-- ... autor chatgpt | revisores gemini, groq -->')."""
    m = _AUTOR.search(linea)
    autor = clave_ia(m.group(1)) if m else ""
    revisores = []
    m = _REVISORES.search(linea)
    if m:
        for trozo in re.sub(r"\([^)]*\)?", "", m.group(1)).split(","):   # fuera "(Pro)", "(gravedad ...)"
            c = clave_ia(trozo)
            if c and c not in revisores:
                revisores.append(c)
    return autor, revisores


def _turnos(carpeta: Path) -> list[dict]:
    salida = []
    for p in sorted(carpeta.glob("turno_nexo_*.json"), reverse=True)[:MAX_TURNOS]:
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict):
            salida.append(dict(d, archivo=p.name))
    return salida


def construir() -> dict:
    """Grafo completo en node-link. Revienta si tareas.json esta roto (la ruta lo pinta como error)."""
    from nucleo import planificador

    todas = T.cargar(detalle=True)["tareas"]
    por_id = {t["id"]: t for t in todas}
    nodos: dict[str, dict] = {}
    aristas: dict[tuple, dict] = {}

    def arista(origen: str, destino: str, tipo: str) -> None:
        if origen in nodos and destino in nodos and origen != destino:
            aristas.setdefault((origen, destino, tipo), {"source": origen, "target": destino, "tipo": tipo})

    def nodo_ia(clave: str) -> str:
        nid = f"ia:{clave}"
        if nid not in nodos:
            nodos[nid] = {"id": nid, "tipo": "ia", "etiqueta": H.PROVEEDORES[clave], "titulo": H.PROVEEDORES[clave],
                          "estado": "", "frase": "", "clase": "ia", "grupo": "", "fecha": "", "tema": "",
                          "resumen": "", "ias": [clave], "url": "/proveedores" if clave != "damian" else ""}
        return nid

    # ---------------------------------------------------------------- tareas, propuestas y revisiones
    for t in todas:
        e = H.estado(T.estado_real(t))
        et = H.etiquetas(t.get("etiquetas"))
        ias = []
        for c in [clave_ia(x) for x in _et(t, "prov:")] + [clave_ia(k.split(":")[0]) for k in t.get("conversaciones") or {}]:
            if c and c not in ias:
                ias.append(c)
        nodos[t["id"]] = {
            "id": t["id"], "tipo": _tipo(t), "etiqueta": f"{t['id']} · {_corto(t['titulo'])}",
            "titulo": f"{t['id']} · {t['titulo']}", "estado": e["nombre"], "frase": e["frase"], "clase": e["clase"],
            "grupo": e["grupo"], "fecha": _fecha(t.get("actualizada") or t.get("creada")), "tema": et["tema"],
            "resumen": H.resumen(t)["texto"], "ias": ias, "url": f"/tareas/{t['id']}"}
    # Sin tema propio, el de la tarea de la que nace
    for t in todas:
        n = nodos[t["id"]]
        for o in _et(t, revision.PRE_ORIGEN):
            if not n["tema"] and o in nodos:
                n["tema"] = nodos[o]["tema"]

    # ---------------------------------------------------------------- borradores
    carpeta = trabajo.BORRADORES
    en_disco = {p.name: p for p in carpeta.glob("*.md") if p.is_file()} if carpeta.is_dir() else {}
    nombres = set(en_disco) | {b for t in todas for b in _et(t, revision.PRE_BORRADOR)}
    revisiones = {}
    for t in todas:
        if revision.ET_REVISION in (t.get("etiquetas") or []):
            for b in _et(t, revision.PRE_BORRADOR):
                revisiones.setdefault(b, []).append(t)
    for nombre in sorted(nombres):
        m = _NOMBRE_BORRADOR.match(nombre)
        tarea_id = m.group(1) if m else ""
        fecha = f"{m.group(2)[:4]}-{m.group(2)[4:6]}-{m.group(2)[6:]}" if m else ""
        hora = f"{m.group(3)[:2]}:{m.group(3)[2:]}" if m else ""
        if not fecha and nombre in en_disco:
            fecha = datetime.fromtimestamp(en_disco[nombre].stat().st_mtime).strftime("%Y-%m-%d")
        clave = "sin"
        for r in revisiones.get(nombre, []):
            if r["estado"] in T.VIVOS:
                clave = "esperando"
                break
            veredictos = [v for b, v in _VEREDICTO.findall(" ".join(n.get("texto", "") for n in r.get("notas") or []))
                          if b == nombre]
            clave = veredictos[-1] if veredictos else ("sustituido" if r["estado"] == "descartada" else clave)
        nombre_e, frase, clase, grupo = ESTADOS_BORRADOR[clave]
        origen = por_id.get(tarea_id)
        cuando = f"{fecha[8:10]}/{fecha[5:7]}" + (f" {hora}" if hora else "") if fecha else ""
        titulo_origen = f" · {origen['titulo']}" if origen else ""
        nodos[f"borrador:{nombre}"] = {
            "id": f"borrador:{nombre}", "tipo": "borrador",
            "etiqueta": f"Borrador {tarea_id or nombre} · {cuando}".rstrip(" ·"),
            "titulo": f"Borrador de {tarea_id or '?'} ({cuando or 'sin fecha'}){titulo_origen}",
            "estado": nombre_e, "frase": frase + ("" if nombre in en_disco else " El archivo ya no está en la carpeta."),
            "clase": clase, "grupo": grupo, "fecha": fecha, "tema": nodos[tarea_id]["tema"] if tarea_id in nodos else "",
            "resumen": f"Archivo memoria/borradores/{nombre}.", "ias": [],
            "url": f"/borrador?f={nombre}" if nombre in en_disco else ""}

    # ---------------------------------------------------------------- aristas entre tareas y borradores
    for t in todas:
        tid, et = t["id"], t.get("etiquetas") or []
        destino = (t.get("bloqueada_por") or "").strip()
        if _ID.match(destino):
            arista(tid, destino, "espera")
        for o in _et(t, revision.PRE_ORIGEN):
            arista(o, tid, "origen")
        for b in _et(t, revision.PRE_BORRADOR):
            if revision.ET_REVISION in et:
                arista(tid, f"borrador:{b}", "revisa")
            else:
                arista(f"borrador:{b}", tid, "propone")
        for x in _et(t, "junto_a:") + _et(t, "bloque:"):
            arista(tid, x, "junto")
        for k in t.get("conversaciones") or {}:
            c = clave_ia(k.split(":")[0])
            if c:
                arista(tid, nodo_ia(c), "delegada")
        if t.get("depende") == "damian":
            arista(tid, nodo_ia("damian"), "damian")
    for nombre in nombres:
        nid = f"borrador:{nombre}"
        m = _NOMBRE_BORRADOR.match(nombre)
        if m:
            arista(m.group(1), nid, "borrador")
        if nombre in en_disco:
            autor, revisores = ias_de_cabecera(_cabecera(en_disco[nombre]))
            nodos[nid]["ias"] = [c for c in [autor] + revisores if c]
            if autor:
                arista(nid, nodo_ia(autor), "escrito")
            for c in revisores:
                arista(nid, nodo_ia(c), "revisado")

    # ---------------------------------------------------------------- turnos
    for reg in _turnos(registro.CARPETA):
        filas = [f for f in ((reg.get("pasos") or {}).get("trabajo") or {}).get("filas") or [] if isinstance(f, dict)]
        ini = str(reg.get("inicio") or "")
        cuando = f"{ini[8:10]}/{ini[5:7]} {ini[11:16]}" if len(ini) >= 16 else ini
        nombre = reg.get("nombre_turno") or reg.get("nombre_plantilla") or "Turno"
        ias = []
        for f in filas:
            for c in [clave_ia(f.get("autor") or "")] + [clave_ia(x) for x in (f.get("revisor") or "").split(",")]:
                if c and c not in ias:
                    ias.append(c)
        nid = f"turno:{reg['archivo'][:-5]}"
        nodos[nid] = {
            "id": nid, "tipo": "turno", "etiqueta": f"Turno {cuando} · {_corto(nombre, 28)}",
            "titulo": f"Turno del {cuando} · {nombre}", "estado": "", "frase": planificador.resultado_corto(reg),
            "clase": "turno", "grupo": "", "fecha": ini[:10], "tema": "", "resumen": "", "ias": ias, "url": "/turnos"}
        for f in filas:
            arista(nid, str(f.get("tarea") or ""), "turno")

    return {"directed": True, "multigraph": False,
            "graph": {"nombre": "NEXO", "generado": datetime.now().isoformat(timespec="seconds"),
                      "tipos": TIPOS, "relaciones": RELACIONES, "grupos": dict(H.GRUPOS),
                      "temas": sorted({n["tema"] for n in nodos.values() if n["tema"]}),
                      "ias": {c: H.PROVEEDORES[c] for c in sorted({c for n in nodos.values() for c in n["ias"]})}},
            "nodes": list(nodos.values()), "links": list(aristas.values())}
