# -*- coding: utf-8 -*-
"""Una sola suite de NEXO a la vez (Bloque 21, 25/10).

Por que: el 25/10 la suite del implementador coincidio con otra (la de salud de una fusion anterior que se habia
pasado de tiempo y seguia viva, y la de Claude): las dos tardaron el doble, T844 se deshizo sola y T849 cayo por
"la suite tardo mas de 1200 s" sin que su codigo tuviera la culpa.

Como: candado del sistema operativo (nucleo.candado.exclusivo: si el proceso muere, se suelta solo) en un archivo
COMUN a principal y a todos los worktrees (carpeta temporal del usuario, no el repo: cada worktree tiene su RAIZ).
  - Toda sesion de pytest en un checkout de NEXO lo toma al empezar (conftest.py raiz) y espera si lo tiene otra.
  - El implementador, la puerta y la linea base lo toman en implementador._suite antes de lanzar pytest y se lo
    pasan al hijo con la variable ENV: el pytest hijo (y lo que lance) no lo vuelve a pedir (si no, se esperaria a
    si mismo). Los workers de pytest-xdist heredan la variable igual.
"""
from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from nucleo import candado

RUTA = Path(tempfile.gettempdir()) / "nexo_suite.lock"
ENV = "NEXO_SUITE_CERROJO"


class Ocupada(candado.Ocupado):
    """Otra suite de NEXO tiene el cerrojo y no lo solto a tiempo."""


def heredado() -> bool:
    """True si este proceso cuelga de quien ya tiene el cerrojo (no hay que pedirlo)."""
    return bool(os.environ.get(ENV))


def quien() -> str | None:
    """Quien tiene el cerrojo ahora ('pid N desde HH:MM:SS (motivo)') o None si esta libre."""
    return candado.quien_tiene(RUTA) if candado.ocupado(RUTA) else None


def env_hijo() -> dict[str, str]:
    """Variables para el pytest que se lanza con el cerrojo ya tomado."""
    return {ENV: str(os.getpid())}


@contextmanager
def tomar(espera: float, motivo: str = ""):
    """El cerrojo durante el bloque `with`. Espera hasta `espera` s; si sigue ocupado, Ocupada (con quien lo tiene).
    Si este proceso ya lo hereda de su padre, no hace nada."""
    if heredado():
        yield
        return
    try:
        cm = candado.exclusivo(RUTA, espera_maxima=espera, motivo=motivo)
        cm.__enter__()
    except candado.Ocupado as e:
        raise Ocupada(str(e)) from None
    try:
        yield
    finally:
        cm.__exit__(None, None, None)
