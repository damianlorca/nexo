# -*- coding: utf-8 -*-
"""Vigia de logs y disco (T708).

El 23-24/09 un reintento sin fin escribio un log de 280 GB en registros/ y nadie lo vio hasta el 05/10.
Aqui se mira, solo con stat (nunca se lee un log), si algun archivo de registros/ pasa de TOPE_LOG o si el
disco libre baja de UMBRAL_LIBRE, y se deja un aviso para el Centro (nucleo/avisos.py). Lo llama cada tick
del planificador; el fallo al mirar nunca rompe el tick.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from nucleo import avisos
from nucleo.config import RAIZ

TOPE_LOG = 512 * 1024 ** 2          # un log de registros/ por encima de esto es anormal (el mayor normal: ~2 MB)
UMBRAL_LIBRE = 20 * 1024 ** 3       # disco libre por debajo de esto, aviso
REPETIR_DISCO = 6 * 3600            # s entre avisos de disco bajo


def _gb(n: float) -> str:
    return f"{n / 1024 ** 3:.1f} GB"


def revisar(carpeta: Path | None = None, tope_log: int = TOPE_LOG, umbral_libre: int = UMBRAL_LIBRE,
            ahora: float | None = None) -> dict:
    carpeta = Path(carpeta) if carpeta else RAIZ / "registros"
    res: dict = {"logs_grandes": [], "libre": None, "disco_bajo": False}
    try:
        with os.scandir(carpeta) as it:
            entradas = list(it)
    except OSError:
        entradas = []
    for e in entradas:
        try:
            if not e.is_file(follow_symlinks=False):
                continue
            tam = Path(e.path).stat().st_size
        except OSError:
            continue
        if tam > tope_log:
            res["logs_grandes"].append((e.name, tam))
    try:
        res["libre"] = shutil.disk_usage(carpeta if carpeta.exists() else RAIZ).free
    except OSError:
        pass
    res["disco_bajo"] = res["libre"] is not None and res["libre"] < umbral_libre
    for nombre, tam in res["logs_grandes"]:
        avisos.emitir("log_enorme", f"Log enorme en registros/: {nombre}",
                      f"{nombre} ocupa {_gb(tam)} (tope {_gb(tope_log)}). Algo esta escribiendo sin freno; "
                      f"no lo abras, mira el final con 'Get-Content -Tail' y busca el proceso que lo escribe.",
                      clave=f"log_enorme:{nombre}", ahora=ahora)
    if res["disco_bajo"]:
        avisos.emitir("disco_bajo", "Poco espacio libre en disco",
                      f"Quedan {_gb(res['libre'])} libres (umbral {_gb(umbral_libre)}).",
                      clave="disco_bajo", ahora=ahora)
    return res
