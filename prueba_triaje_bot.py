"""Prueba end-to-end de _texto_triaje (canal.bot) contra el Ollama real.

Se lanza con lanzar() porque una llamada a Qwen puede tardar mas de
los 50 s que corta ejecutar(). El resultado se lee del log.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo import registro  # noqa: E402
registro.aislar()  # T198: sus logs (401 simulados...) no van a registros/ reales

from canal.bot import _texto_triaje  # noqa: E402

MENSAJES = [
    "Recuerda comprar pan cuando salgas, se me olvido esta manana",
    "URGENTE: se me ha caido el portatil por las escaleras, no arranca",
]

for m in MENSAJES:
    print("-" * 64)
    print(f"mensaje: {m}")

    inicio = time.time()
    resultado = _texto_triaje(m)
    print(f"tardo {time.time() - inicio:.1f}s")
    print(f"resultado: {resultado!r}")

print("-" * 64)
print("FIN_PRUEBA_TRIAJE")
