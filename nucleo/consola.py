# -*- coding: utf-8 -*-
"""Salida de los CLI de NEXO en la consola de Windows (28/09).

La consola de Windows escribe en cp1252: un titulo con '→' tumbaba `python -m nucleo.revision cola` con
UnicodeEncodeError. Pasar a UTF-8 tampoco vale: las tildes salen como 'Vig�a'. Aqui se mantiene la
codificacion de la consola (las tildes se ven bien) y solo lo que no cabe se sustituye por '?'.
"""
from __future__ import annotations

import sys


def preparar() -> None:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
