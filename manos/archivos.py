"""Manos: archivos. Leer, escribir, listar, archivar.

Borrar no existe en este modulo, y es intencionado: esta en rojo.
Lo que sobra se mueve a _archivo/, no se destruye.

Dos cosas que se arreglaron en la auditoria del 11/09 y conviene no
deshacer (hallazgos C2, C3 y C4 de memoria/auditoria.md):

- `escribir()` escribe de forma atomica. Un corte a mitad ya no
  deja el archivo truncado.
- `archivar()` tiene frenos. Mover la raiz del proyecto, la carpeta
  de respaldos o el propio _archivo dentro de _archivo no es
  "ordenar": es romperlo todo de una forma que ademas no avisa.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico
from nucleo.permisos import ARCHIVOS_BLINDADOS, Bloqueado, Nivel, exigir, nivel_de_ruta
from nucleo.registro import logger


log = logger("manos.archivos")

EXCLUIDOS = {
    "__pycache__", ".venv", "venv", ".git",
    "chrome-perfil", "registros", "salidas",
}

# Carpetas que no se archivan enteras. Los archivos sueltos de
# dentro, si; la carpeta entera, no.
INTOCABLES = {"_archivo", "_respaldos", "memoria", ".venv", ".git"}


def _resolver(ruta: str | Path) -> Path:
    p = Path(ruta)

    return p.resolve() if p.is_absolute() else (RAIZ / p).resolve()


def listar(subcarpeta: str = "", patron: str = "*", aprobado: bool = False) -> list[str]:
    """aprobado=True (T1025, como leer) solo lo pone servidor_mcp tras consumir una aprobacion ambar para ESTA carpeta
    (de Damian o del guardian): salta el ambar, NUNCA el rojo."""
    base = _resolver(subcarpeta) if subcarpeta else RAIZ

    nivel = nivel_de_ruta(base, escritura=False)
    if not (aprobado and nivel is Nivel.AMBAR):
        exigir(nivel, "listar", str(base))

    encontrados = []

    for p in base.rglob(patron):
        if not p.is_file():
            continue

        if EXCLUIDOS & set(p.parts):
            continue

        encontrados.append(str(p.relative_to(base)))

    return sorted(encontrados)


def leer(ruta: str | Path, max_bytes: int = 400_000, aprobado: bool = False) -> str:
    """aprobado=True (T1025) solo lo pone servidor_mcp tras consumir una aprobacion ambar para ESTA ruta (de Damian
    o del guardian): salta el ambar, NUNCA el rojo (secretos.toml sigue bloqueado). Mismo patron que escribir (T861)."""
    p = _resolver(ruta)

    nivel = nivel_de_ruta(p, escritura=False)
    if not (aprobado and nivel is Nivel.AMBAR):
        exigir(nivel, "leer", str(p))

    if not p.is_file():
        raise FileNotFoundError(str(p))

    if p.stat().st_size > max_bytes:
        raise ValueError(
            f"Archivo de {p.stat().st_size} bytes, por encima del limite "
            f"de {max_bytes}. Leelo por partes o resumelo con Qwen."
        )

    return p.read_text(encoding="utf-8", errors="replace")


def escribir(ruta: str | Path, contenido: str, sobrescribir: bool = True, aprobado: bool = False) -> str:
    """aprobado=True (T861) solo lo pone servidor_mcp tras consumir una aprobacion ambar de Damian para ESTA ruta y
    ESTE contenido: salta el ambar, NUNCA el rojo."""
    p = _resolver(ruta)

    nivel = nivel_de_ruta(p, escritura=True)
    if not (aprobado and nivel is Nivel.AMBAR):
        exigir(nivel, "escribir", str(p))

    if p.exists() and not sobrescribir:
        raise FileExistsError(str(p))

    if p.exists():
        respaldar(p)

    # Atomico: o entra entero o no entra. Ver nucleo/escritura.py.
    escribir_atomico(p, contenido)

    log.info("escrito %s (%d bytes)", p.name, len(contenido))

    return str(p)


def _nombre_de_respaldo(p: Path) -> str:
    """Nombre plano que no choca con el de otro archivo que se llame igual.

    Antes se usaba solo el nombre del archivo, asi que
    canal/entrada/x.json y canal/salida/x.json escritos en el mismo
    segundo se pisaban el respaldo el uno al otro. Ahora el nombre
    lleva la ruta dentro del proyecto.
    """

    try:
        relativa = p.relative_to(RAIZ)
        cuerpo = "__".join(relativa.parts[:-1] + (relativa.stem,))
    except ValueError:
        cuerpo = p.stem

    return f"{cuerpo}_{time.strftime('%H%M%S')}{p.suffix}"


def respaldar(ruta: str | Path) -> Path | None:
    """Copia el archivo a _respaldos/ antes de pisarlo."""

    p = _resolver(ruta)

    if not p.is_file():
        return None

    destino = RAIZ / "_respaldos" / time.strftime("%Y%m%d")
    destino.mkdir(parents=True, exist_ok=True)

    copia = destino / _nombre_de_respaldo(p)

    # Si en el mismo segundo se escribe dos veces el mismo archivo,
    # que la segunda no borre el respaldo de la primera.
    contador = 1

    while copia.exists():
        copia = destino / f"{copia.stem}_{contador}{copia.suffix}"
        contador += 1

    shutil.copy2(p, copia)

    return copia


def _comprobar_archivable(p: Path, destino: Path) -> None:
    """Frena los archivados que no se pueden deshacer.

    Esto no es paranoia de mas: `archivar` es lo unico de este modulo
    que MUEVE cosas, y un movimiento mal dirigido se parece mucho a un
    borrado sin serlo.
    """

    if p == RAIZ:
        raise Bloqueado(
            "Archivar la raiz del proyecto entera. Eso mueve el agente "
            "dentro de si mismo y deja de funcionar todo. Si de verdad "
            "hay que mover el proyecto, se hace a mano y con el equipo "
            "delante."
        )

    if p in RAIZ.parents:
        raise Bloqueado(
            f"Archivar {p}, que contiene la raiz del proyecto. No."
        )

    # Mover algo que contiene el destino se lleva el destino consigo.
    if p == destino or p in destino.parents:
        raise Bloqueado(
            f"Archivar {p} moveria la propia carpeta de destino "
            f"({destino}) dentro de si misma."
        )

    # N01 (H07): una carpeta que contiene un archivo blindado (nucleo/, manos/, .claude/) no se
    # archiva entera: se llevaria permisos.py & cia. sin pasar por el ambar de K2.
    if p.is_dir():
        for b in ARCHIVOS_BLINDADOS:
            if p in (RAIZ / b).parents:
                raise Bloqueado(
                    f"Archivar {p} se llevaria {b}, que esta blindado. Archiva los "
                    "archivos sueltos, o que Damian lo haga viendo el cambio."
                )

    if p.is_dir() and p.name in INTOCABLES and p.parent == RAIZ:
        raise Bloqueado(
            f"Archivar la carpeta '{p.name}' entera. Los archivos sueltos "
            "de dentro si se pueden archivar; la carpeta no, porque es "
            "parte de como el agente se acuerda de las cosas o se "
            "recupera de un fallo."
        )


def archivar(ruta: str | Path, motivo: str = "") -> str:
    """Mueve algo a _archivo/ en lugar de borrarlo."""

    p = _resolver(ruta)

    exigir(nivel_de_ruta(p, escritura=True), "archivar", str(p))

    if not p.exists():
        raise FileNotFoundError(str(p))

    destino = RAIZ / "_archivo" / time.strftime("%Y%m%d")

    _comprobar_archivable(p, destino)

    destino.mkdir(parents=True, exist_ok=True)

    final = destino / p.name

    contador = 1

    while final.exists():
        final = destino / f"{p.stem}_{contador}{p.suffix}"
        contador += 1

    shutil.move(str(p), str(final))

    log.info("archivado %s -> %s (%s)", p.name, final, motivo or "sin motivo")

    return str(final)
