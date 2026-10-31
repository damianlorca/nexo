"""Extremidad: montaje de video con FFmpeg.

Para divulgacion, que es lo que haces, esto cubre casi todo: imagenes
mas narracion mas subtitulos. La generacion de video por IA es otra
cosa y en tu equipo no sale a cuenta.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from nucleo.config import salidas, valor
from nucleo.registro import logger


log = logger("extremidades.video")


def disponible() -> bool:
    return shutil.which("ffmpeg") is not None


def _ffmpeg(argumentos: list[str], timeout: int = 900) -> None:
    if not disponible():
        raise FileNotFoundError(
            "FFmpeg no esta instalado. winget install Gyan.FFmpeg"
        )

    proceso = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *argumentos],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if proceso.returncode != 0:
        raise RuntimeError(f"FFmpeg fallo: {proceso.stderr[:500]}")


def duracion(ruta: str | Path) -> float:
    proceso = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(ruta),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    try:
        return float(proceso.stdout.strip())
    except ValueError:
        return 0.0


def lienzo() -> tuple[int, int]:
    """El tamano en el que se monta, sacado de config.toml.

    Damian publica en vertical (reels). Montar en horizontal y
    recortar despues destroza la imagen, asi que se monta ya en el
    formato final.
    """

    if valor("video.vertical", True):
        return int(valor("video.ancho", 1080)), int(valor("video.alto", 1920))

    return 1920, 1080


def _encajar(ancho: int, alto: int) -> str:
    """Filtro de FFmpeg: mete la imagen entera dentro del lienzo.

    Sin recortar nada. Lo que sobra se rellena, que para un plano
    fijo es preferible a perder parte del encuadre.
    """

    return (
        f"scale={ancho}:{alto}:force_original_aspect_ratio=decrease,"
        f"pad={ancho}:{alto}:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1"
    )


def imagen_con_voz(
    imagen: str | Path,
    audio: str | Path,
    destino: str | Path | None = None,
) -> Path:
    """Un plano fijo con narracion encima. La pieza basica."""

    salida = Path(destino) if destino else (
        salidas() / f"video_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    )

    ancho, alto = lienzo()

    _ffmpeg([
        "-loop", "1", "-i", str(imagen),
        "-i", str(audio),
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-vf", _encajar(ancho, alto),
        "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        str(salida),
    ])

    log.info("video montado: %s", salida.name)

    return salida


def secuencia(
    pares: list[tuple[str | Path, str | Path]],
    destino: str | Path | None = None,
) -> Path:
    """Varias parejas de imagen y narracion, una detras de otra."""

    if not pares:
        raise ValueError("No hay nada que montar.")

    trozos = []

    temporal = salidas() / f"_trozos_{int(time.time())}"
    temporal.mkdir(parents=True, exist_ok=True)

    for i, (imagen, audio) in enumerate(pares):
        trozos.append(
            imagen_con_voz(imagen, audio, temporal / f"{i:03d}.mp4")
        )

    lista = temporal / "lista.txt"

    lista.write_text(
        "\n".join(f"file '{t.as_posix()}'" for t in trozos),
        encoding="utf-8",
    )

    salida = Path(destino) if destino else (
        salidas() / f"video_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    )

    _ffmpeg([
        "-f", "concat", "-safe", "0", "-i", str(lista),
        "-c", "copy", str(salida),
    ])

    log.info("secuencia de %d trozos: %s", len(trozos), salida.name)

    return salida


def vertical(entrada: str | Path, destino: str | Path | None = None) -> Path:
    """Recorta un video que YA ESTA en horizontal a 9:16.

    Ojo: desde el arreglo del fallo I1 esto casi nunca hace falta.
    imagen_con_voz() y secuencia() ya montan en vertical si
    config.toml lo dice, y pasar por aqui despues solo sirve para
    recortar y perder calidad. Usalo solo con material ajeno que
    venga en horizontal.
    """

    salida = Path(destino) if destino else (
        salidas() / f"vertical_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    )

    _ffmpeg([
        "-i", str(entrada),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,"
               "crop=1080:1920",
        "-c:a", "copy", str(salida),
    ])

    return salida
