# -*- coding: utf-8 -*-
"""T687 parte A (epica T686): auditoria retroactiva de cierres, ampliada mas alla de las investigaciones (T674).

SOLO INFORME: no cambia ninguna tarea. Cada fila lleva una propuesta: reabrir / fijar resultado / descarte valido /
verificar / revisar a mano (y 'sin accion' cuando ya esta recogido). Cuatro secciones:

  1. propuestas_descartadas: cat:propuesta en 'descartada'. Distingue BORRADOR malo ("borrador descartado", "se
     rehace") de IDEA mala ("descartada por Claude al aprobar el borrador", superado, fundida, archivada). Si fue
     por borrador, mira si la idea volvio en otra propuesta (titulo parecido, sin IA): si volvio -> descarte valido;
     si no -> reabrir. Sin motivo registrado, o aprobada y descartada a la vez -> revisar a mano.
  2. aprobadas_sin_implementar: propuesta:aprobada que sigue viva. Dice cuantos dias lleva; si una nota la integra
     en otra tarea -> descarte valido; si no -> verificar (comprobar primero que hace hoy el codigo).
  3. hechas_sin_testear: estado 'hecha' sin testeado -> verificar (evidencia ejecutada o reabrir).
  4. candidatos_lotes: candidatos de los lotes del vigia (memoria/vigia/lote_*.json). Rastro = otra tarea o el
     borrador del lote que lo nombre. Sin rastro -> revisar a mano (puede haberse perdido).

CLI: .venv\\Scripts\\python.exe -m nucleo.auditoria_cierres
Informe en memoria/investigacion/auditoria_cierres_AAAAMMDD_HHMM.{md,json}.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

from nucleo import tareas as T

RAIZ = Path(__file__).resolve().parent.parent
INFORMES = RAIZ / "memoria" / "investigacion"
VIGIA = RAIZ / "memoria" / "vigia"
BORRADORES = RAIZ / "memoria" / "borradores"

ET_PROPUESTA = "cat:propuesta"
UMBRAL_PARECIDA = 0.5
MIN_PALABRA = 4
RE_INTEGRA = re.compile(r"(?:se integra|integrad[ao]|fundid[ao]|incluid[ao]|absorbid[ao])\s+(?:dentro\s+)?(?:de|en)\s+(T\d+)", re.I)
RE_LOTE = re.compile(r"LOTE:\s*(lote_\d{8}\.json)")


def _et(t: dict, prefijo: str) -> str:
    return next((e[len(prefijo):] for e in t.get("etiquetas") or [] if e.startswith(prefijo)), "")


def _es_propuesta(t: dict) -> bool:
    return ET_PROPUESTA in (t.get("etiquetas") or [])


def _palabras(titulo: str) -> set[str]:
    s = re.sub(r"^\[propuesta de t\d+\]\s*", "", (titulo or "").lower())
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return {w for w in re.findall(r"[a-z0-9]+", s) if len(w) >= MIN_PALABRA}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _ultima_nota_descarte(t: dict) -> str:
    return next((n["texto"] for n in reversed(t.get("notas") or []) if n["texto"].lower().startswith("descartada")), "")


def _motivo(nota: str) -> str:
    m = re.search(r"\):\s*(.*)", nota, re.S)
    return " ".join((m.group(1) if m else nota).split())[:300]


def _causa(t: dict) -> str:
    """idea | borrador | superado | fundida | archivada | sin_motivo."""
    et = t.get("etiquetas") or []
    nota = _ultima_nota_descarte(t).lower()
    if "al aprobar el borrador" in nota or "idea rechazada" in nota:   # la segunda: reconsideracion (E1/T686)
        return "idea"
    if "superado" in nota:
        return "superado"
    if "borrador descartado" in nota or "se rehace" in nota or "borrador" in nota:
        return "borrador"
    if any(e.startswith("fundida_en") for e in et):
        return "fundida"
    if any(e.startswith("archivada") for e in et):
        return "archivada"
    return "sin_motivo"


CAUSAS_VALIDAS = ("idea", "superado", "fundida", "archivada")


# ------------------------------------------------------------------ 1) propuestas descartadas
def _propuestas_descartadas(tareas: list[dict]) -> list[dict]:
    vivas = [(p, _palabras(p["titulo"])) for p in tareas if _es_propuesta(p) and p["estado"] != "descartada"]
    por_id = {t["id"]: t for t in tareas}
    filas = []
    for t in tareas:
        if not (_es_propuesta(t) and t["estado"] == "descartada"):
            continue
        causa = _causa(t)
        nota = _ultima_nota_descarte(t)
        volvio = []
        if causa == "borrador":
            pal = _palabras(t["titulo"])
            volvio = [p["id"] for p, pp in vivas if p["id"] != t["id"] and _jaccard(pal, pp) >= UMBRAL_PARECIDA]
        if "propuesta:aprobada" in (t.get("etiquetas") or []):
            prop, por = "revisar a mano", "estaba APROBADA y acaba descartada: hay que ver por que"
        elif causa in CAUSAS_VALIDAS:
            prop, por = "descarte valido", f"descartada por {causa}" + (f": {_motivo(nota)[:120]}" if nota else "")
        elif causa == "borrador" and volvio:
            prop, por = "descarte valido", f"se descarto el borrador, no la idea; la idea volvio en {', '.join(volvio)}"
        elif causa == "borrador" and (por_id.get(_et(t, "tarea_origen:")) or {}).get("estado") in T.VIVOS:
            prop, por = "descarte valido", ("se descarto el borrador, no la idea; la tarea origen "
                                            f"{_et(t, 'tarea_origen:')} sigue viva y volvera a proponer")
        elif causa == "borrador":
            prop, por = "reabrir", ("se descarto por borrador malo, la idea no ha vuelto en otra propuesta y su "
                                    "tarea origen esta cerrada: la idea se pierde")
        else:
            prop, por = "revisar a mano", "descartada sin motivo registrado"
        filas.append({"id": t["id"], "titulo": t["titulo"][:100], "origen": _et(t, "tarea_origen:"),
                      "origen_estado": (por_id.get(_et(t, "tarea_origen:")) or {}).get("estado", "?"), "causa": causa,
                      "motivo": _motivo(nota), "volvio_en": volvio, "propuesta": prop, "por_que": por,
                      "cerrada": t.get("cerrada") or ""})
    return filas


# ------------------------------------------------------------------ 2) aprobadas sin implementar
def _dias(t: dict, ahora: datetime) -> int:
    try:
        return (ahora - datetime.strptime((t.get("creada") or "")[:19], "%Y-%m-%d %H:%M:%S")).days
    except ValueError:
        return -1


def _aprobadas_sin_implementar(tareas: list[dict], ahora: datetime) -> list[dict]:
    filas = []
    for t in tareas:
        if not (_es_propuesta(t) and "propuesta:aprobada" in (t.get("etiquetas") or [])) or t["estado"] in T.CERRADOS:
            continue
        destino = next((m.group(1) for n in t.get("notas") or [] for m in [RE_INTEGRA.search(n["texto"])] if m), "")
        if destino and destino != t["id"]:
            prop, por = "descarte valido", f"una nota la integra en {destino}: comprobar que {destino} la cubre"
        else:
            prop, por = "verificar", "aprobada y sin implementar: comprobar primero que hace hoy el codigo"
        filas.append({"id": t["id"], "titulo": t["titulo"][:100], "estado": t["estado"], "dias": _dias(t, ahora),
                      "propuesta": prop, "por_que": por})
    return sorted(filas, key=lambda f: -f["dias"])


# ------------------------------------------------------------------ 3) hechas sin testear
def _hechas_sin_testear(tareas: list[dict]) -> list[dict]:
    filas = []
    for t in tareas:
        if t["estado"] != "hecha" or t.get("testeado"):
            continue
        cat = next((e for e in t.get("etiquetas") or [] if e.startswith("cat:")), "cat:?")
        filas.append({"id": t["id"], "titulo": t["titulo"][:100], "tipo": cat, "cerrada": t.get("cerrada") or "",
                      "propuesta": "verificar", "por_que": "HECHO SIN TESTEAR: falta evidencia ejecutada (o reabrir)"})
    return filas


# ------------------------------------------------------------------ 4) candidatos de los lotes del vigia
def _leer_lotes() -> dict:
    out = {}
    for f in sorted(VIGIA.glob("lote_*.json")):
        try:
            out[f.name] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return out


def _leer_borradores() -> dict:
    out = {}
    for f in sorted(BORRADORES.glob("*.md")):
        try:
            out[f.name] = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    return out


def _candidatos_lotes(tareas: list[dict], lotes: dict, borradores: dict) -> list[dict]:
    textos = {t["id"]: " ".join([t.get("titulo") or "", t.get("detalle") or ""] +
                                [n["texto"] for n in t.get("notas") or []]).lower() for t in tareas}
    por_id = {t["id"]: t for t in tareas}
    filas = []
    for lt in tareas:
        m = RE_LOTE.search(lt.get("detalle") or "")
        if not m or m.group(1) not in lotes:
            continue
        borr = [txt.lower() for nombre, txt in borradores.items() if nombre.startswith(lt["id"] + "_")]
        for c in lotes[m.group(1)].get("candidatos", []):
            clave = (c.get("id") or c.get("nombre") or "").lower()
            if not clave:
                continue
            rastro = sorted((tid for tid, tx in textos.items() if tid != lt["id"] and clave in tx), key=T.clave_id)
            en_borrador = any(clave in b for b in borr)
            vivas = [r for r in rastro if por_id[r]["estado"] != "descartada"]
            if vivas:
                prop, por = "sin accion", f"recogido en {', '.join(vivas)}"
            elif rastro and all(_causa(por_id[r]) in CAUSAS_VALIDAS for r in rastro):
                prop, por = "descarte valido", f"solo en tareas descartadas por idea ({', '.join(rastro)})"
            elif rastro:
                prop, por = "revisar a mano", f"solo rastro en descartadas por borrador o sin motivo ({', '.join(rastro)})"
            elif en_borrador:
                prop, por = "descarte valido", "nombrado en el borrador del lote (valorado ahi), sin tarea propia"
            else:
                prop, por = "revisar a mano", "sin rastro en ninguna tarea ni en el borrador: puede haberse perdido"
            filas.append({"lote": lt["id"], "archivo": m.group(1), "candidato": c.get("id") or c.get("nombre"),
                          "url": c.get("url", ""), "descripcion": (c.get("descripcion") or "")[:140],
                          "rastro": rastro, "propuesta": prop, "por_que": por})
    return filas


# ------------------------------------------------------------------ informe
SECCIONES = (
    ("propuestas_descartadas", "Propuestas descartadas", ("id", "titulo", "causa", "volvio_en", "propuesta", "por_que")),
    ("aprobadas_sin_implementar", "Propuestas aprobadas sin implementar", ("id", "titulo", "estado", "dias", "propuesta", "por_que")),
    ("hechas_sin_testear", "Hechas sin testear", ("id", "titulo", "tipo", "propuesta", "por_que")),
    ("candidatos_lotes", "Candidatos de los lotes del vigia", ("lote", "candidato", "rastro", "propuesta", "por_que")),
)


def _celda(v) -> str:
    return (", ".join(v) if isinstance(v, list) else str(v)).replace("|", "/").replace("\n", " ") or "-"


def _markdown(res: dict, ahora: datetime) -> str:
    md = [f"# Auditoria de cierres (T687) - {ahora:%d/%m/%Y %H:%M}", "",
          "SOLO INFORME: no se ha reabierto ni cambiado ninguna tarea. Cada fila trae una propuesta; "
          "las de 'revisar a mano' son para el tribunal o para Damian.", "",
          "| Seccion | Propuesta | Filas |", "|---|---|---|"]
    for k, v in res["resumen"].items():
        for prop, n in sorted(v.items()):
            md.append(f"| {k} | {prop} | {n} |")
    md.append("")
    for clave, titulo, cols in SECCIONES:
        filas = res[clave]
        md += [f"## {titulo} ({len(filas)})", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        md += ["| " + " | ".join(_celda(f.get(c, "")) for c in cols) + " |" for f in filas]
        md.append("")
    return "\n".join(md)


def auditar(ahora: datetime | None = None, tareas: list[dict] | None = None, lotes: dict | None = None,
            borradores: dict | None = None, escribir: bool = True, carpeta: Path | None = None) -> dict:
    from collections import Counter
    ahora = ahora or datetime.now()
    tareas = T.cargar()["tareas"] if tareas is None else tareas
    lotes = _leer_lotes() if lotes is None else lotes
    borradores = _leer_borradores() if borradores is None else borradores
    res = {"cuando": f"{ahora:%Y-%m-%d %H:%M}",
           "propuestas_descartadas": _propuestas_descartadas(tareas),
           "aprobadas_sin_implementar": _aprobadas_sin_implementar(tareas, ahora),
           "hechas_sin_testear": _hechas_sin_testear(tareas),
           "candidatos_lotes": _candidatos_lotes(tareas, lotes, borradores)}
    res["resumen"] = {k: dict(Counter(f["propuesta"] for f in res[k])) for k, _, _ in SECCIONES}
    if escribir:
        base = (carpeta or INFORMES)
        base.mkdir(parents=True, exist_ok=True)
        base = base / f"auditoria_cierres_{ahora:%Y%m%d_%H%M}"
        base.with_suffix(".md").write_text(_markdown(res, ahora), encoding="utf-8")
        base.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        res["informe"] = str(base.with_suffix(".md"))
    return res


def _cli(argv: list[str]) -> int:
    r = auditar()
    print("Informe:", r["informe"])
    for k, v in r["resumen"].items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    sys.exit(_cli(sys.argv[1:]))
