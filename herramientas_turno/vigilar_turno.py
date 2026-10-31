# -*- coding: utf-8 -*-
"""Vigilante del turno (04:20). Damian 23/09: el aviso NO es para el, es para el modelo que trabaja:
pide al turno que vaya acabando (termina lo actual, no empieza nada nuevo, escribe el handoff) para
que no se corte de golpe a las 04:30. Sin mensajes a Telegram."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from nucleo import parada  # noqa: E402

if (RAIZ / "memoria" / ".candado_turno_nexo.lock").exists():
    parada.pedir_cierre("vigilante 04:20: ir acabando")
    print("cierre suave pedido al turno")
else:
    print("no hay turno en marcha")
