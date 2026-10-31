"""Extremidad: voz con Piper.

Piper va en CPU, no toca la grafica y es rapido. Sirve para narrar
los videos de divulgacion y para que el altavoz de casa diga algo.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from nucleo.config import RAIZ, salidas, valor
from nucleo.registro import logger


log = logger("extremidades.voz")


def _ruta(clave: str, defecto: str) -> Path:
    bruto = valor(f"voz.{clave}", defecto)

    p = Path(bruto)

    return p if p.is_absolute() else (RAIZ / p)


def disponible() -> bool:
    return _ruta("piper", "piper/piper.exe").is_file()


def narrar(texto: str, destino: str | Path | None = None) -> Path:
    """Convierte texto en un WAV."""

    piper = _ruta("piper", "piper/piper.exe")
    modelo = _ruta("modelo", "piper/es_ES-sharvard-medium.onnx")

    if not piper.is_file():
        raise FileNotFoundError(
            f"Piper no esta en {piper}. Descargalo de "
            "https://github.com/rhasspy/piper/releases"
        )

    if not modelo.is_file():
        raise FileNotFoundError(
            f"Falta la voz en {modelo}. Descarga una voz en espanol "
            "de https://huggingface.co/rhasspy/piper-voices"
        )

    salida = Path(destino) if destino else (
        salidas() / f"voz_{time.strftime('%Y%m%d_%H%M%S')}.wav"
    )

    salida.parent.mkdir(parents=True, exist_ok=True)

    proceso = subprocess.run(
        [str(piper), "--model", str(modelo), "--output_file", str(salida)],
        input=texto.encode("utf-8"),
        capture_output=True,
        timeout=180,
    )

    if proceso.returncode != 0:
        raise RuntimeError(
            f"Piper fallo: {proceso.stderr.decode('utf-8', 'replace')[:400]}"
        )

    log.info("voz generada: %s", salida.name)

    return salida
