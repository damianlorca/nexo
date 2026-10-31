# -*- coding: utf-8 -*-
"""Vuelca en compacto TODAS las tareas y el catalogo para construir el mapa de ideas (Claude lo sintetiza)."""
import json
from pathlib import Path
from nucleo import catalogo as C
from nucleo import tareas as T

out = []
for t in T.cargar()["tareas"]:
    notas = t.get("notas") or []
    out.append({"id": t["id"], "e": t["estado"][:4], "t": t["titulo"][:110],
                "d": " ".join((t.get("detalle") or "").split())[:330],
                "n": " ".join((notas[-1]["texto"] if notas else "").split())[:260],
                "c": next((e[4:] for e in t.get("etiquetas") or [] if e.startswith("cat:")), "")})
cat = []
for x in C.cargar()["items"]:
    cat.append({"id": x["id"], "n": x["nombre"], "i": (x.get("identidad") or "")[:90], "p": (x.get("para_que_sirve") or x.get("primera_impresion") or "")[:200],
                "v": x.get("veredicto"), "a": x.get("auditado"), "o": " ".join((x.get("observaciones") or "").split())[:200]})
Path("registros/volcado_ideas.json").write_text(json.dumps({"tareas": out, "catalogo": cat}, ensure_ascii=False), encoding="utf-8")
print(len(out), "tareas;", len(cat), "herramientas")
