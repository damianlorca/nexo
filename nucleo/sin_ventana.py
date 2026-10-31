"""Que ningun proceso hijo de NEXO abra una ventana de terminal en la pantalla de Damian (20/10).

La web, el planificador y los turnos corren con pythonw.exe, que no tiene consola. Cuando un proceso asi lanza un
programa de consola (git, python, pytest, powershell, taskkill...) sin CREATE_NO_WINDOW, Windows le crea una consola
NUEVA y VISIBLE: es la ventana de terminal que salia sola cada pocos minutos y quitaba el foco a Damian (le hizo poner
la PARADA el 19/10). Habia ~20 llamadas asi repartidas por nucleo/ (implementador, banco de modelos, cierre
automatico, hechos...).

En vez de arreglarlas una a una (y que la siguiente que alguien escriba vuelva a abrir ventanas), `aplicar()` hace que
todo subprocess.Popen de un proceso de NEXO lleve CREATE_NO_WINDOW por defecto. Se llama al importar `nucleo`, asi que
vale para todos los procesos de NEXO. No toca:
- quien pide una consola propia a proposito (CREATE_NEW_CONSOLE) ni un proceso suelto (DETACHED_PROCESS);
- los programas con ventana (Chrome, ComfyUI...): CREATE_NO_WINDOW solo afecta a la consola;
- la salida: lo que se captura con capture_output/stdout sigue llegando igual.
Fuera de Windows no hace nada.
"""
from __future__ import annotations

import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010
DETACHED_PROCESS = 0x00000008
_POS_CREATIONFLAGS = 12          # posicion de creationflags en Popen(args, bufsize, ..., creationflags) sin contar args
_MARCA = "_nexo_sin_ventana"


def banderas(flags: int | None) -> int:
    """Las banderas con CREATE_NO_WINDOW, salvo que se haya pedido una consola propia o un proceso suelto."""
    flags = int(flags or 0)
    if flags & (CREATE_NEW_CONSOLE | DETACHED_PROCESS):
        return flags
    return flags | CREATE_NO_WINDOW


def aplicar(clase=None, plataforma: str = sys.platform) -> bool:
    """Envuelve clase.__init__ (por defecto subprocess.Popen). Devuelve True si lo ha hecho ahora."""
    if plataforma != "win32":
        return False
    clase = clase or subprocess.Popen
    original = clase.__init__
    if getattr(original, _MARCA, False):
        return False

    def __init__(self, args, *resto, **kwargs):
        if len(resto) > _POS_CREATIONFLAGS:
            resto = list(resto)
            resto[_POS_CREATIONFLAGS] = banderas(resto[_POS_CREATIONFLAGS])
        else:
            kwargs["creationflags"] = banderas(kwargs.get("creationflags", 0))
        original(self, args, *resto, **kwargs)

    setattr(__init__, _MARCA, True)
    __init__.__wrapped__ = original
    __init__.__doc__ = original.__doc__
    clase.__init__ = __init__
    return True


def aplicado(clase=None) -> bool:
    return bool(getattr((clase or subprocess.Popen).__init__, _MARCA, False))
