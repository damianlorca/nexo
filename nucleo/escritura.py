"""Escritura atomica: o se escribe entero, o no se escribe.

Por que existe esto.

`Path.write_text()` hace dos cosas: primero vacia el archivo y
despues mete el contenido. Entre esas dos cosas el archivo esta a
cero bytes. Si el proceso muere justo ahi, el archivo queda
truncado o vacio para siempre.

Y morir ahi no es hipotetico en esta casa: esta COMPROBADO (ver
hallazgo B1 de memoria/auditoria.md) que Claude Desktop reinicia el
servidor MCP cuando le parece y se lleva por delante todo lo que
cuelga de el, sin avisar y sin darle tiempo a nadie a terminar.

Lo que hace este modulo es lo de siempre: escribir en un archivo
temporal al lado del bueno y, cuando ya esta entero en disco,
cambiarle el nombre. `os.replace` es atomico: el que lea, o ve el
archivo viejo entero, o ve el nuevo entero. Nunca un trozo.
"""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path

# T225: en Windows, os.replace falla con PermissionError (WinError 5)
# si otro proceso (la interfaz, un antivirus) tiene el destino abierto
# en ese instante. Suele durar milisegundos: se reintenta un poco antes
# de rendirse. Cualquier otro error sale a la primera.
REINTENTOS_REPLACE = 5
ESPERA_REPLACE_S = (0.05, 0.1, 0.15, 0.2)


# T708: tempfile.mkstemp() reintenta hasta 10.000 veces ante PermissionError en Windows; con la
# guardia bloqueando, eso mas un reintento de fuera escribio un log de 280 GB (23-24/09). Aqui el
# temporal se crea con tope propio y un permiso denegado sale a la primera.
INTENTOS_TEMPORAL = 8


def _crear_temporal(carpeta: Path, nombre: str) -> tuple[int, Path]:
    """Crea `.nombre.<azar>.tmp` en la carpeta (exclusivo, modo 0600). Solo reintenta si el nombre ya existe."""
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    for _ in range(INTENTOS_TEMPORAL):
        tmp = carpeta / f".{nombre}.{secrets.token_hex(4)}.tmp"
        try:
            return os.open(str(tmp), flags, 0o600), tmp
        except FileExistsError:
            continue
    raise FileExistsError(f"sin nombre libre para el temporal de {nombre} tras {INTENTOS_TEMPORAL} intentos")


def _es_bloqueo_de_guardia(e: BaseException) -> bool:
    """La guardia (nucleo/guardia_python.py) corta a proposito: reintentarlo nunca lo arregla."""
    return any(c.__name__ == "GuardiaBloqueo" for c in type(e).__mro__)


def _reemplazar(tmp: Path, destino: Path) -> None:
    for intento in range(REINTENTOS_REPLACE):
        try:
            os.replace(tmp, destino)
            return
        except PermissionError as e:
            if intento == REINTENTOS_REPLACE - 1 or _es_bloqueo_de_guardia(e):
                raise
            time.sleep(ESPERA_REPLACE_S[min(intento, len(ESPERA_REPLACE_S) - 1)])


def escribir_atomico(destino: str | Path, texto: str, encoding: str = "utf-8") -> Path:
    """Escribe texto en destino sin dejar nunca un archivo a medias.

    Devuelve la ruta escrita. Si algo falla a mitad, el archivo que
    ya hubiera en destino se queda intacto y el temporal se limpia.
    """

    p = Path(destino)

    p.parent.mkdir(parents=True, exist_ok=True)

    # El temporal va en la MISMA carpeta a proposito: os.replace solo
    # es atomico dentro del mismo volumen. Desde %TEMP% no lo seria.
    tmp_fd, tmp = _crear_temporal(p.parent, p.name)

    try:
        with os.fdopen(tmp_fd, "w", encoding=encoding, newline="") as f:
            f.write(texto)

            # Sin esto el contenido puede estar solo en el cache del
            # sistema operativo cuando hacemos el replace.
            f.flush()
            os.fsync(f.fileno())

        _reemplazar(tmp, p)

    except BaseException:
        # Que no quede basura si esto revienta. Aqui si se borra,
        # porque es un temporal nuestro que nunca tuvo datos buenos.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass

        raise

    return p


def limpiar_temporales(carpeta: str | Path) -> int:
    """Barre temporales huerfanos de un corte anterior. Devuelve cuantos."""

    base = Path(carpeta)

    if not base.is_dir():
        return 0

    n = 0

    for t in base.glob(".*.tmp"):
        try:
            t.unlink()
            n += 1
        except OSError:
            pass

    return n
