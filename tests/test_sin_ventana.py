"""20/10: ningun proceso hijo de NEXO abre una ventana de terminal (nucleo/sin_ventana.py)."""
from __future__ import annotations

import subprocess
import sys

import pytest

from nucleo import sin_ventana as sv


class _PopenFalso:
    def __init__(self, args, bufsize=-1, executable=None, stdin=None, stdout=None, stderr=None, preexec_fn=None,
                 close_fds=True, shell=False, cwd=None, env=None, universal_newlines=None, startupinfo=None,
                 creationflags=0, **resto):
        self.args = args
        self.creationflags = creationflags


def _clase():
    return type("PopenFalso", (_PopenFalso,), {"__init__": _PopenFalso.__init__})


def test_banderas_anade_sin_ventana_y_respeta_consola_propia_y_proceso_suelto():
    assert sv.banderas(0) == sv.CREATE_NO_WINDOW
    assert sv.banderas(None) == sv.CREATE_NO_WINDOW
    assert sv.banderas(0x200) == 0x200 | sv.CREATE_NO_WINDOW          # CREATE_NEW_PROCESS_GROUP se conserva
    assert sv.banderas(sv.CREATE_NEW_CONSOLE) == sv.CREATE_NEW_CONSOLE
    assert sv.banderas(sv.DETACHED_PROCESS | 0x200) == sv.DETACHED_PROCESS | 0x200


def test_aplicar_fuera_de_windows_no_hace_nada():
    c = _clase()
    assert sv.aplicar(c, plataforma="linux") is False
    assert c(["x"]).creationflags == 0


def test_aplicar_en_windows_pone_sin_ventana_por_defecto_y_por_nombre_y_por_posicion():
    c = _clase()
    assert sv.aplicar(c, plataforma="win32") is True
    assert c(["git", "log"]).creationflags == sv.CREATE_NO_WINDOW
    assert c(["git"], creationflags=0x200).creationflags == 0x200 | sv.CREATE_NO_WINDOW
    assert c(["cmd"], creationflags=sv.CREATE_NEW_CONSOLE).creationflags == sv.CREATE_NEW_CONSOLE
    posicional = c(["x"], -1, None, None, None, None, None, True, False, None, None, None, None, 0)
    assert posicional.creationflags == sv.CREATE_NO_WINDOW


def test_aplicar_dos_veces_no_envuelve_dos_veces():
    c = _clase()
    assert sv.aplicar(c, plataforma="win32") is True
    assert sv.aplicar(c, plataforma="win32") is False
    assert sv.aplicado(c)


@pytest.mark.skipif(sys.platform != "win32", reason="solo en Windows")
def test_importar_nucleo_lo_deja_aplicado_y_un_hijo_real_no_tiene_ventana():
    import nucleo  # noqa: F401
    assert sv.aplicado()
    r = subprocess.run([sys.executable, "-c", "import ctypes; print(ctypes.windll.kernel32.GetConsoleWindow())"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and r.stdout.strip() == "0"
