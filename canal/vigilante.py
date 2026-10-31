"""Vigilante del bot. Lo levanta y lo mantiene vivo.

Por que existe: el bot se cae cada vez que Claude Desktop reinicia el
servidor MCP, porque lanzar() lo crea como hijo de ese servidor y
Windows mata a toda la descendencia al cerrarse el Job del padre.
Paso el 11/09 a las 03:15 y dejo tres mensajes sin entregar.

Por que no es una tarea programada: crear tareas en el Programador
pide administrador (Acceso denegado, 11/09). Un proceso de usuario en
la carpeta de Inicio no lo pide, y ademas reacciona en segundos en
vez de en diez minutos.

Como comprueba si el bot vive: ctypes + OpenProcess. NO os.kill.
En Windows os.kill(pid, 0) no consulta: llama a TerminateProcess y
MATA el proceso. Usarlo aqui habria matado al bot cada 30 segundos.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from canal.interruptor import bot_activo          # noqa: E402
from nucleo.instancia import pid_anotado, unico   # noqa: E402
from nucleo.registro import logger                # noqa: E402


log = logger("canal.vigilante")

BOT = RAIZ / "canal" / "bot.py"
PYTHONW = RAIZ / ".venv" / "Scripts" / "pythonw.exe"
PYTHON = RAIZ / ".venv" / "Scripts" / "python.exe"

INTERVALO = 30          # segundos entre comprobaciones
ESPERA_ARRANQUE = 8     # margen para que el bot coja su candado

PROCESS_QUERY_LIMITED = 0x1000
STILL_ACTIVE = 259


def _vivo(pid: int) -> bool:
    """True si el proceso existe. Solo consulta, no toca nada."""

    if pid <= 0:
        return False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    kernel32.OpenProcess.argtypes = [
        wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE

    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)

    if not h:
        return False

    try:
        codigo = wintypes.DWORD()

        if kernel32.GetExitCodeProcess(h, ctypes.byref(codigo)):
            return codigo.value == STILL_ACTIVE

        # Existe el handle: el proceso esta ahi aunque no podamos leer
        # su codigo de salida.
        return True

    finally:
        kernel32.CloseHandle(h)


def _interprete() -> Path:
    return PYTHONW if PYTHONW.is_file() else PYTHON


def _arrancar() -> int:
    """Lanza el bot fuera de nuestro arbol, para que nos sobreviva."""

    banderas = (
        subprocess.CREATE_NO_WINDOW
        | subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.CREATE_BREAKAWAY_FROM_JOB
    )

    try:
        proceso = subprocess.Popen(
            [str(_interprete()), str(BOT)],
            cwd=str(RAIZ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=banderas,
        )

    except OSError:
        # CREATE_BREAKAWAY_FROM_JOB falla si el Job no lo permite.
        # Sin el sigue funcionando, solo que atado a nosotros.
        proceso = subprocess.Popen(
            [str(_interprete()), str(BOT)],
            cwd=str(RAIZ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                | subprocess.CREATE_NEW_PROCESS_GROUP
            ),
        )

    return proceso.pid


def main() -> None:
    if not unico("nexo_vigilante"):
        log.info("ya hay otro vigilante, me retiro")
        return

    log.info("vigilante en marcha, comprobando cada %ds", INTERVALO)

    caidas = 0
    apagado_visto = False

    while True:
        # T751: con canal.bot_activo = false no se relanza (el bot sale solo en su siguiente vuelta).
        if not bot_activo():
            if not apagado_visto:
                log.info("canal.bot_activo = false: no relanzo el bot")
            apagado_visto = True
            time.sleep(INTERVALO)
            continue
        apagado_visto = False

        pid = pid_anotado("nexo_bot")

        if not _vivo(pid):
            caidas += 1

            log.warning(
                "el bot no responde (pid anotado %s). Levantandolo. "
                "Caidas desde que arranque: %d",
                pid or "ninguno", caidas,
            )

            _arrancar()

            time.sleep(ESPERA_ARRANQUE)

            nuevo = pid_anotado("nexo_bot")

            if _vivo(nuevo):
                log.info("bot arriba, pid %d", nuevo)
            else:
                log.error(
                    "no consigo levantar el bot. Reintento en %ds",
                    INTERVALO,
                )

        time.sleep(INTERVALO)


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    try:
        main()
    except KeyboardInterrupt:
        log.info("vigilante detenido a mano")
