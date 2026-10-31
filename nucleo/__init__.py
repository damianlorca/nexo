"""Paquete nucleo de NEXO.

20/10: al importarlo, ningun proceso hijo abre una ventana de terminal en Windows (ver nucleo/sin_ventana.py).
"""
from nucleo import sin_ventana as _sin_ventana

_sin_ventana.aplicar()
