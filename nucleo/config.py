"""Carga de configuracion. Un unico sitio del que sale todo."""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any


RAIZ = Path(__file__).resolve().parent.parent

ARCHIVO_CONFIG = RAIZ / "config.toml"
ARCHIVO_SECRETOS = RAIZ / "secretos.toml"


def _leer_toml(ruta: Path) -> dict:
    if not ruta.is_file():
        return {}

    with ruta.open("rb") as f:
        return tomllib.load(f)


@lru_cache(maxsize=1)
def config() -> dict:
    """Configuracion combinada: config.toml + secretos.toml."""

    datos = _leer_toml(ARCHIVO_CONFIG)
    secretos = _leer_toml(ARCHIVO_SECRETOS)

    for seccion, valores in secretos.items():
        datos.setdefault(seccion, {}).update(valores)

    return datos


def valor(ruta: str, defecto: Any = None) -> Any:
    """Lee un valor con notacion de puntos: valor("qwen.url")."""

    actual: Any = config()

    for parte in ruta.split("."):
        if not isinstance(actual, dict) or parte not in actual:
            return defecto

        actual = actual[parte]

    return actual


def ruta(nombre: str, defecto: str | None = None) -> Path:
    """Devuelve una ruta de config, siempre absoluta."""

    bruto = valor(f"rutas.{nombre}", defecto)

    if not bruto:
        raise KeyError(f"Ruta no configurada: rutas.{nombre}")

    p = Path(bruto)

    return p if p.is_absolute() else (RAIZ / p).resolve()


def salidas() -> Path:
    """Carpeta donde el agente deja lo que produce."""

    destino = ruta("salidas", str(RAIZ / "salidas"))

    destino.mkdir(parents=True, exist_ok=True)

    return destino
