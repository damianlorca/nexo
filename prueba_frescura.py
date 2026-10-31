# -*- coding: utf-8 -*-
"""Prueba de nucleo/frescura.py con una carpeta temporal (no toca el repo)."""
import os
import tempfile
import time
from pathlib import Path

from nucleo import frescura

fallos = []


def comprobar(nombre, cond, detalle=""):
    print(("  OK    " if cond else "  FALLO ") + nombre + ("" if cond else f"  -> {detalle}"))
    if not cond:
        fallos.append(nombre)


with tempfile.TemporaryDirectory() as d:
    raiz = Path(d)
    (raiz / "canal").mkdir()
    (raiz / "nucleo").mkdir()
    viejo = time.time() - 3600
    for rel in ("router.py", "canal/bot.py", "nucleo/tareas.py", "prueba_x.py", "_tmp_y.py"):
        f = raiz / rel
        f.write_text("x = 1\n", encoding="utf-8")
        os.utime(f, (viejo, viejo))

    arranque = time.time() - 60  # el proceso "arranco" hace un minuto
    comprobar("nada cambiado desde el arranque -> lista vacia", frescura.desfasados(arranque, raiz) == [])

    ahora = time.time()
    for rel in ("router.py", "canal/bot.py", "prueba_x.py", "_tmp_y.py"):
        os.utime(raiz / rel, (ahora, ahora))
    r = frescura.desfasados(arranque, raiz)
    comprobar("detecta router.py y canal/bot.py", r == ["canal/bot.py", "router.py"], r)
    comprobar("ignora scripts de prueba y temporales de la raiz", "prueba_x.py" not in r and "_tmp_y.py" not in r, r)
    comprobar("no marca nucleo/tareas.py (no cambio)", "nucleo/tareas.py" not in r, r)

    casi = arranque + 1  # dentro del margen de 2 s
    os.utime(raiz / "nucleo/tareas.py", (casi, casi))
    comprobar("respeta el margen de arranque", "nucleo/tareas.py" not in frescura.desfasados(arranque, raiz))

comprobar("ARRANQUE se fija al importar", abs(frescura.ARRANQUE - time.time()) < 120)
print("\nTODO VALE" if not fallos else f"\n{len(fallos)} FALLOS")
raise SystemExit(1 if fallos else 0)
