"""Instancia unica. Un candado para que no haya dos bots vivos.

El 10/09 hubo dos bots a la vez y Telegram devolvio 409 Conflict a
los dos. Ese fallo deja a Damian incomunicado sin que nadie se
entere, asi que el arreglo va en el codigo, no en la costumbre de
acordarse de mirar.

El cierre es un mutex con nombre de Windows. Si ya hay otro proceso
NUESTRO vivo, el segundo no arranca. El sistema suelta el mutex solo
cuando el proceso muere, asi que no deja candados zombis: no hay que
limpiar nada a mano despues de un corte de luz.

AVISO (11/09, hallazgo A3). Aqui ponia que habia un SEGUNDO cierre,
un sondeo a Telegram antes de arrancar para detectar bots viejos.
Ese sondeo se escribio y se tiro la misma noche: NO EXISTE y NO
FUNCIONABA. En Telegram el 409 se lo lleva el bot que YA estaba, no
el que llega, asi que al probarlo dijo "via libre" habiendo un bot
vivo y ademas le solto un conflicto al que estaba trabajando.

Lo que cubre el caso del bot viejo (lanzado antes de existir este
modulo, y que por tanto no coge el mutex) es lo otro: ante 409
sostenido, el bot cede el paso y se apaga (hallazgo A2, en
canal/bot.py). No hay sondeo previo, y no conviene volver a
intentarlo. El codigo descartado esta en
_archivo/20260911/prueba_409.py por si alguien duda.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from nucleo.config import RAIZ


ERROR_ALREADY_EXISTS = 183

# El handle se guarda aqui a proposito. Si se lo lleva el recolector
# de basura, Windows cierra el mutex y el candado se abre solo.
_handle = None

PIDS = RAIZ / "registros"


def _mutex_windows(nombre: str) -> bool:
    """True si hemos cogido el candado; False si ya lo tenia otro."""

    global _handle

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    kernel32.CreateMutexW.argtypes = [
        wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR,
    ]
    kernel32.CreateMutexW.restype = wintypes.HANDLE

    # "Global\\" choca en todo el equipo, no solo dentro de la sesion
    # de Windows en la que estemos. Importa porque el bot puede
    # acabar arrancando desde una tarea programada o desde WMI, que
    # no viven en la misma sesion que este proceso.
    for ambito in ("Global\\", "Local\\"):
        h = kernel32.CreateMutexW(None, True, f"{ambito}{nombre}")

        ultimo = ctypes.get_last_error()

        if not h:
            # Sin permiso para el ambito global: se prueba el local.
            continue

        if ultimo == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(h)
            return False

        _handle = h

        return True

    # No hemos podido crear el candado en ningun ambito. Mejor dejar
    # arrancar el bot que dejar a Damian sin canal por culpa de la
    # cerradura.
    return True


def _pid_vivo(pid: int) -> bool:
    if pid <= 0:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Existe, pero es de otro usuario.
        return True
    except OSError:
        return False

    return True


def _fichero_pid(nombre: str) -> bool:
    """Respaldo para cuando no estamos en Windows."""

    PIDS.mkdir(parents=True, exist_ok=True)

    marca = PIDS / f"{nombre}.pid"

    if marca.is_file():
        try:
            anterior = int(marca.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            anterior = 0

        if anterior and anterior != os.getpid() and _pid_vivo(anterior):
            return False

    marca.write_text(str(os.getpid()), encoding="utf-8")

    return True


def unico(nombre: str = "nexo_bot") -> bool:
    """Coge el candado. False significa: ya hay otro, no arranques.

    Deja siempre el PID escrito en registros/<nombre>.pid, aunque el
    candado real sea el mutex. Sirve para poder mirar desde fuera
    quien manda sin tener que adivinarlo.
    """

    if sys.platform == "win32":
        cogido = _mutex_windows(nombre)
    else:
        cogido = _fichero_pid(nombre)

    if cogido:
        try:
            PIDS.mkdir(parents=True, exist_ok=True)

            (PIDS / f"{nombre}.pid").write_text(
                str(os.getpid()), encoding="utf-8",
            )
        except OSError:
            pass

    return cogido


def pid_anotado(nombre: str = "nexo_bot") -> int:
    """El PID que dejo escrito el que tiene el candado. 0 si no hay."""

    marca = PIDS / f"{nombre}.pid"

    if not marca.is_file():
        return 0

    try:
        return int(marca.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return 0
