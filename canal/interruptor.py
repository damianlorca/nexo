# -*- coding: utf-8 -*-
"""T751: interruptor del bot de Telegram (canal.bot_activo en config.toml; por defecto true).

Con canal.bot_activo = false el vigilante (canal/vigilante.py) no relanza el bot y el bot (canal/bot.py) no
arranca y, si ya esta en marcha, sale en la siguiente vuelta. No se borra codigo: volver a true lo enciende.

Se lee config.toml EN FRESCO en cada consulta (nucleo.config.config() va cacheado y el vigilante vive dias) y
solo config.toml: secretos.toml no se abre aqui.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

ARCHIVO = Path(__file__).resolve().parent.parent / "config.toml"


def bot_activo(archivo: Path | None = None) -> bool:
    try:
        with (archivo or ARCHIVO).open("rb") as f:
            datos = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return False   # config ilegible: apagado (Telegram esta congelado; el bot es la superficie de riesgo)
    v = (datos.get("canal") or {}).get("bot_activo", True)
    return v is not False
