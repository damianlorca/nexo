# -*- coding: utf-8 -*-
"""B3: primera ejecucion REAL y supervisada (por Claude) del bucle trabajador+revisor,
limitada a 2 tareas de investigacion elegidas: T135 (rtk/ccusage/caveman) y T142 (Hermes/OpenClaw)."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from nucleo import trabajo  # noqa: E402

elegidas = {"T135", "T142"}
original = trabajo.candidatas
trabajo.candidatas = lambda: [t for t in original() if t["id"] in elegidas]
filas = trabajo.ciclo(max_tareas=2)
f = trabajo.handoff(filas, origen="prueba_supervisada")
for x in filas:
    print(x["tarea"], x.get("autor"), x.get("revisor"), x.get("veredicto"), x.get("archivo"), x.get("intentos"))
print("HANDOFF", f)
