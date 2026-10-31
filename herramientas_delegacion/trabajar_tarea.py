# -*- coding: utf-8 -*-
"""Trabaja UNA tarea concreta con el protocolo OK absoluto + auditor (T183/T189) y escribe el handoff.
Uso: python herramientas_delegacion/trabajar_tarea.py T150"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from nucleo import trabajo  # noqa: E402

ids = set(sys.argv[1:])
original = trabajo.candidatas
trabajo.candidatas = lambda: [t for t in original() if t["id"] in ids]
filas = trabajo.ciclo(max_tareas=len(ids))
for f in filas:
    print({k: f.get(k) for k in ("tarea", "autor", "revisor", "gravedades", "veredicto", "auditoria", "fallos_auditoria", "modo_final",
                            "archivo", "intentos")})
print("HANDOFF", trabajo.handoff(filas, origen="tarea_suelta"))
