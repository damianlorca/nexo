"""Comprueba si os.kill(pid, 0) mata el proceso en Windows.

En Linux, la senal 0 no hace nada: solo sirve para preguntar "existe
este proceso?". En Windows no hay senales, asi que CPython traduce
os.kill(pid, sig) a TerminateProcess(handle, sig) para cualquier sig
que no sea CTRL_C_EVENT ni CTRL_BREAK_EVENT.

Si eso es cierto, nucleo/instancia.py._pid_vivo() no comprueba que un
proceso este vivo: LO MATA.

Esta prueba lo resuelve mirando, no opinando. Levanta un proceso de
usar y tirar y le hace la pregunta.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

print(f"plataforma: {sys.platform}")

# Un proceso inofensivo que solo duerme. Nada que perder.
cobaya = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(30)"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
)

pid = cobaya.pid

print(f"cobaya lanzada, pid={pid}")

time.sleep(1.5)

print(f"antes de preguntar, viva: {cobaya.poll() is None}")

try:
    os.kill(pid, 0)
    print("os.kill(pid, 0) no ha lanzado excepcion")
except Exception as e:
    print(f"os.kill(pid, 0) lanzo {type(e).__name__}: {e}")

time.sleep(1.5)

sigue_viva = cobaya.poll() is None

print(f"despues de preguntar, viva: {sigue_viva}")
print(f"codigo de salida: {cobaya.poll()}")

print()

if sigue_viva:
    print("VEREDICTO: os.kill(pid, 0) solo pregunta. _pid_vivo() es seguro.")
else:
    print("VEREDICTO: os.kill(pid, 0) HA MATADO EL PROCESO.")
    print("           _pid_vivo() no comprueba: destruye lo que comprueba.")

# Y ahora el mismo caso a traves de la funcion de verdad.
print()
print("Lo mismo, pero llamando a nucleo.instancia._pid_vivo():")

cobaya2 = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(30)"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
)

time.sleep(1.5)

from nucleo.instancia import _pid_vivo  # noqa: E402

respuesta = _pid_vivo(cobaya2.pid)

time.sleep(1.5)

viva2 = cobaya2.poll() is None

print(f"  _pid_vivo({cobaya2.pid}) devuelve: {respuesta}")
print(f"  el proceso sigue vivo          : {viva2}")

if respuesta and not viva2:
    print("  O SEA: dice que esta vivo justo despues de haberlo matado.")

# Limpieza: que no queden cobayas sueltas.
for c in (cobaya, cobaya2):
    try:
        if c.poll() is None:
            c.terminate()
    except Exception:
        pass
