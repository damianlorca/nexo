# -*- coding: utf-8 -*-
"""Prueba de nucleo/catalogo.py con almacen y vista temporales."""
import json
import tempfile
from pathlib import Path

from nucleo import catalogo as C

fallos = []


def comprobar(nombre, cond, detalle=""):
    print(("  OK    " if cond else "  FALLO ") + nombre + ("" if cond else f"  -> {detalle}"))
    if not cond:
        fallos.append(nombre)


with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    C.ALMACEN, C.VISTA, C.CANDADO = d / "catalogo.json", d / "vista.md", d / ".lock"
    a = C.anadir("herramienta uno", categoria="memoria", para_que_sirve="prueba")
    b = C.anadir("herramienta dos", auditado="primera_pasada")
    comprobar("ids consecutivos", (a["id"], b["id"]) == ("H001", "H002"))
    comprobar("vista generada", C.VISTA.is_file() and "| H002 |" in C.VISTA.read_text(encoding="utf-8"))
    comprobar("siguiente = la primera pendiente", C.siguiente()["id"] == "H001")
    C.poner("H001", auditado="completo", veredicto="REFERENCIA")
    comprobar("completo sale de pendientes", C.siguiente()["id"] == "H002")
    comprobar("fecha de auditoria automatica", bool(C.buscar(C.cargar(), "H001")["fecha_auditoria"]))
    for campo, valor in (("veredicto", "QUIZAS"), ("auditado", "a medias"), ("inventado", "x")):
        try:
            C.poner("H002", **{campo: valor})
            fallos.append(f"acepto {campo}={valor}")
        except ValueError:
            pass
    comprobar("rechaza valores no permitidos y campos desconocidos", "acepto" not in " ".join(fallos))
    try:
        C.anadir("herramienta uno")
        fallos.append("acepto un duplicado")
    except ValueError:
        pass
    comprobar("no duplica nombres", "acepto un duplicado" not in fallos)
    C.ALMACEN.write_text("{roto", encoding="utf-8")
    try:
        C.cargar()
        fallos.append("un catalogo roto no revento")
    except json.JSONDecodeError:
        pass
    comprobar("un catalogo roto revienta en vez de vaciarse", "un catalogo roto no revento" not in fallos)

print("\nTODO VALE" if not fallos else f"\n{len(fallos)} FALLOS: {fallos}")
raise SystemExit(1 if fallos else 0)
