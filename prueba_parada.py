# -*- coding: utf-8 -*-
"""Prueba la parada de emergencia (nucleo/parada.py, /parar y /seguir del bot,
y que turno_nexo.py no arranca con la parada puesta). Sin Telegram real.

T234: redirige parada.BANDERA/CIERRE a un directorio temporal, no a la
bandera real, para no poder cortar un turno de verdad si esto se ejecuta
con los turnos activos.
"""
import tempfile
from pathlib import Path

from nucleo import registro  # noqa: E402
registro.aislar()  # T198: sus logs (401 simulados...) no van a registros/ reales

from nucleo import parada

_TMP = Path(tempfile.mkdtemp(prefix="prueba_parada_"))
parada.BANDERA = _TMP / "PARADA_NEXO_PRUEBA"
parada.CIERRE = _TMP / "CIERRE_TURNO_PRUEBA"
parada._descargar_ollama = lambda: []

ok = 0
fallos = []


def comprobar(cond, texto):
    global ok
    if cond:
        ok += 1
        print("OK ", texto)
    else:
        fallos.append(texto)
        print("MAL", texto)


comprobar(parada.activa() is None, "sin bandera -> no activa")

from canal import bot  # noqa: E402

r = bot._cmd_parar(" prueba automatica")
comprobar("PARADO" in r and parada.activa() == "prueba automatica", "/parar activa con motivo")

import turno_nexo  # noqa: E402

reg = turno_nexo.turno(simular=True, sin_web=True, avisar=False)
comprobar("PARADA" in (reg.get("abortado") or "") and not reg["pasos"], "turno no arranca con parada")
comprobar(not turno_nexo.CANDADO.exists(), "no deja candado colgado")

r = bot._cmd_seguir("")
comprobar("quitada" in r and parada.activa() is None, "/seguir quita la parada")
comprobar("No habia" in bot._cmd_seguir(""), "/seguir sin parada avisa")

comprobar(turno_nexo._tomar_candado() and not turno_nexo._tomar_candado(), "candado propio excluye un segundo turno")
turno_nexo._soltar_candado()
comprobar(not turno_nexo.CANDADO.exists(), "candado se suelta")

print(f"\n{ok}/{ok + len(fallos)} OK")
raise SystemExit(1 if fallos else 0)
