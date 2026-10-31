"""Niveles de permiso. Esto no es documentacion: es control.

verde  -> el agente actua solo
ambar  -> hace falta que Damian lo apruebe
rojo   -> no se hace, lo pida quien lo pida
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

from nucleo.config import RAIZ, valor


class Nivel(str, Enum):
    VERDE = "verde"
    AMBAR = "ambar"
    ROJO = "rojo"


class Bloqueado(PermissionError):
    """Accion en rojo. No se ejecuta nunca."""


class NecesitaAprobacion(PermissionError):
    """Accion en ambar. Requiere que Damian diga que si."""

    def __init__(self, accion: str, detalle: str = ""):
        self.accion = accion
        self.detalle = detalle

        super().__init__(
            f"Necesita aprobacion: {accion}"
            + (f" ({detalle})" if detalle else "")
        )


# Los patrones son expresiones regulares, no subcadenas. Buscando
# subcadenas, "log del bot" saltaba por "del ", "Get-Date -Format"
# por "format " y cualquier frase en espanol con "del" quedaba
# bloqueada. En espanol eso pasa cada dos por tres.

def _cualquiera(patrones: tuple[str, ...]) -> re.Pattern:
    return re.compile("|".join(patrones), re.IGNORECASE)


# Inicio de comando: principio de linea o tras ; | & (
_INI = r"(?:^|[;|&(]\s*)"


# Nunca, bajo ningun concepto.
ROJOS = _cualquiera((
    rf"{_INI}format\s+[a-z]:",      # format C:  — no "Get-Date -Format"
    r"\bdiskpart\b",
    r"\bcipher\s+/w\b",
    r"\bbcdedit\b",
    rf"{_INI}shutdown\b",
    r"\bvssadmin\s+delete\b",
    r"\breg\s+delete\s+hk(lm|ey_local)",
))


# Borrar. Damian decidio que lo viejo se archiva, no se destruye.
BORRADO = _cualquiera((
    r"\bremove-item\b",
    r"\bclear-recyclebin\b",
    rf"{_INI}del\s+[\"'./\\a-z*]",   # "del archivo", no "log del bot"
    rf"{_INI}erase\s",
    r"\brd\s+/s\b",
    r"\brmdir\s+/s\b",
    r"\brm\s+-[a-z]*[rf]",
))


# Cambia el sistema o descarga cosas. Damian decide.
#
# Hallazgos L2 y L3 del 11/09/2026: esta lista decia cubrir descargas y
# no cubria ninguna, y cubria `schtasks` pero no los cmdlets de
# PowerShell que hacen exactamente lo mismo con otro nombre. Un ambar
# que se esquiva reescribiendo el comando no protege: solo da la
# sensacion de que protege.
AMBAR = _cualquiera((
    # Gestores de paquetes
    r"\bpip\s+(install|uninstall)\b",
    r"\bnpm\s+install\b",
    r"\bwinget\b",
    r"\bchoco\s+install\b",
    r"\bscoop\s+install\b",

    # Sacar codigo de casa
    r"\bgit\s+push\b",

    # Traerse cosas de internet (L2). Bajar un .exe y dejarlo en disco
    # es exactamente "descarga cosas", que es lo que dice el titulo.
    r"\binvoke-webrequest\b",
    r"\binvoke-restmethod\b",
    rf"{_INI}iwr\s",
    rf"{_INI}irm\s",
    rf"{_INI}curl(\.exe)?\s",
    rf"{_INI}wget(\.exe)?\s",
    r"\bstart-bitstransfer\b",
    r"\bcertutil\b.*urlcache",
    r"\bdownloadfile\b",
    r"\bdownloadstring\b",

    # Quedarse a vivir en el arranque (L3). Todo esto es lo mismo que
    # schtasks con otro nombre.
    r"\bschtasks\b",
    r"\bregister-scheduledtask\b",
    r"\bnew-scheduledtask\b",
    r"\bnew-service\b",
    rf"{_INI}sc(\.exe)?\s+create\b",
    r"\bcurrentversion\\run\b",
    r"\bstartup\b.*\.(lnk|bat|cmd|ps1)\b",

    # Tocar la configuracion del sistema
    r"\bsetx\b",
    r"\bset-executionpolicy\b",
    r"\bset-mppreference\b",
    r"\bnew-localuser\b",
    r"\badd-localgroupmember\b",
))


# ---------------------------------------------------------------
# Archivos con trato especial (hallazgos K1 y K2, 11/09/2026)
# ---------------------------------------------------------------
#
# K1. Cualquier herramienta podia LEER secretos.toml y sacar el token
# de Telegram por el chat. Ya paso una vez con los registros el 10/09.
# Leerlo pasa a rojo. La aplicacion no se entera: nucleo/config.py lo
# lee directamente en Python, no a traves de estas herramientas.
#
# K2. El agente podia reescribir sus propios permisos. Un agente que
# edita sus barreras no tiene barreras, y el resto de este archivo
# seria teatro. Tocar los archivos que sostienen el control pasa a
# ambar: se puede mejorar, pero lo aprueba Damian viendo el cambio.
# Ambar y no rojo a proposito — si fuera rojo, arreglar un fallo de
# permisos exigiria editar a mano, y acabariamos desactivandolo.

ARCHIVOS_EN_ROJO = ("secretos.toml",)

ARCHIVOS_BLINDADOS = (
    Path("nucleo") / "permisos.py",
    Path("nucleo") / "instancia.py",
    Path("nucleo") / "config.py",
    Path("manos") / "shell.py",
    Path("manos") / "archivos.py",
    Path("manos") / "servidor_mcp.py",
)


def _es_blindado(p: Path) -> bool:
    try:
        relativa = p.relative_to(RAIZ)
    except ValueError:
        return False

    return relativa in ARCHIVOS_BLINDADOS


def zonas_verdes() -> list[Path]:
    brutas = valor("permisos.zona_verde", [str(RAIZ)]) or [str(RAIZ)]

    return [Path(b).resolve() for b in brutas]


def nivel_de_ruta(destino: str | Path, escritura: bool = True) -> Nivel:
    """Que nivel tiene tocar esta ruta."""

    p = Path(destino).resolve()

    # K1: hay archivos que no se leen ni de broma.
    if p.name.lower() in ARCHIVOS_EN_ROJO:
        return Nivel.ROJO

    # K2: los archivos que sostienen el control no se cambian solos.
    if escritura and _es_blindado(p):
        return Nivel.AMBAR

    for zona in zonas_verdes():
        if p == zona or zona in p.parents:
            return Nivel.VERDE

    # REQ-070: ni leer ni escribir fuera de la zona verde va solo.
    # Leer tampoco es inofensivo -- podria sacar cualquier archivo
    # del disco (fuera de zona_verde) por el chat.
    return Nivel.AMBAR


# ---------------------------------------------------------------
# T024 / L6: el texto de los argumentos (propuesta N05, 25/09/2026)
# ---------------------------------------------------------------
#
# Antes se buscaban los patrones en la linea ENTERA, asi que un
# 'git commit -m "instale winget"' salia ambar y un
# 'Get-Help Remove-Item' salia rojo. Arreglarlo "en general" es
# peligroso: afinar puede dejar pasar lo que hoy se para. Por eso el
# cambio es de lista blanca y va en una sola direccion:
#
#   - Solo se relaja una linea SIMPLE (sin bloques, subexpresiones,
#     redirecciones ni escapes) en la que TODAS las ordenes son de
#     argumentos inertes: ordenes que solo muestran o buscan texto y
#     no ejecutan nada de lo que reciben.
#   - Cualquier otra linea se mira exactamente igual que antes.
#   - Si hay duda al partir la linea (comillas sin cerrar...), se
#     mira igual que antes.
#
# K1 tambien por la shell: mencionar secretos.toml en un comando es
# rojo siempre, igual que leerlo con las herramientas de archivos.

SECRETOS_EN_COMANDO = re.compile(r"secretos\.toml", re.IGNORECASE)

# Ordenes cuyos argumentos son texto y nada mas.
ORDENES_INERTES = frozenset({
    "echo", "write-output", "write-host",
    "select-string", "sls", "findstr", "rg", "grep",
    "get-command", "gcm", "get-help", "help",
    "test-path",
})

# git solo con subordenes que no ejecutan nada de la linea. Fuera a
# proposito: grep (-O abre un programa), las que aceptan -c antes de
# la suborden y cualquier otra que no este aqui.
GIT_INERTES = frozenset({
    "commit", "log", "show", "diff", "status", "add", "blame",
})

# Algo de esto fuera de comillas simples y la linea deja de ser
# simple: bloques, subexpresiones, redirecciones, escapes, llamadas.
_NO_SIMPLE = re.compile(r"[{}()`<>&$@]")


def _partir_simple(comando: str) -> list[list[str]] | None:
    """Parte una linea simple en ordenes y palabras.

    Devuelve None si la linea no es simple o hay cualquier duda:
    entonces se mira la linea entera, como siempre.
    """

    ordenes: list[list[str]] = [[]]
    palabra: list[str] = []
    en_palabra = False
    i, n = 0, len(comando)

    def cerrar() -> None:
        nonlocal palabra, en_palabra
        if en_palabra:
            ordenes[-1].append("".join(palabra))
        palabra, en_palabra = [], False

    while i < n:
        c = comando[i]

        if c == "'":
            fin = comando.find("'", i + 1)
            if fin < 0:
                return None
            palabra.append(comando[i + 1:fin])
            en_palabra = True
            i = fin + 1
            continue

        if c == '"':
            fin = comando.find('"', i + 1)
            if fin < 0:
                return None
            dentro = comando[i + 1:fin]
            # En comillas dobles PowerShell expande $() y escapes.
            if _NO_SIMPLE.search(dentro):
                return None
            palabra.append(dentro)
            en_palabra = True
            i = fin + 1
            continue

        if _NO_SIMPLE.match(c):
            return None

        if c in ";|\n\r":
            cerrar()
            ordenes.append([])
            i += 1
            continue

        if c.isspace():
            cerrar()
            i += 1
            continue

        palabra.append(c)
        en_palabra = True
        i += 1

    cerrar()

    ordenes = [o for o in ordenes if o]

    return ordenes or None


def _es_inerte(palabras: list[str]) -> bool:
    nombre = palabras[0].lower()

    if nombre.endswith(".exe"):
        nombre = nombre[:-4]

    if nombre == "git":
        return len(palabras) > 1 and palabras[1].lower() in GIT_INERTES

    # rg --pre <programa> ejecuta ese programa con cada archivo.
    if nombre == "rg" and any(p.lower().startswith("--pre") for p in palabras):
        return False

    return nombre in ORDENES_INERTES


def _solo_ordenes_inertes(comando: str) -> bool:
    ordenes = _partir_simple(comando)

    return ordenes is not None and all(_es_inerte(o) for o in ordenes)


def _nivel_linea_entera(comando: str) -> Nivel:
    if ROJOS.search(comando) or BORRADO.search(comando):
        return Nivel.ROJO

    if AMBAR.search(comando):
        return Nivel.AMBAR

    return Nivel.VERDE


def nivel_de_comando(comando: str) -> Nivel:
    """Que nivel tiene este comando de shell."""

    if SECRETOS_EN_COMANDO.search(comando):
        return Nivel.ROJO

    # T024: una linea simple de ordenes inertes no ejecuta nada de lo
    # que lleva en los argumentos. Nada de lo demas cambia.
    if _solo_ordenes_inertes(comando):
        return Nivel.VERDE

    return _nivel_linea_entera(comando)


def exigir(nivel: Nivel, accion: str, detalle: str = "") -> None:
    """Corta la ejecucion si el nivel no permite seguir solo."""

    if nivel is Nivel.ROJO:
        raise Bloqueado(
            f"Accion en rojo, no se ejecuta: {accion}"
            + (f" ({detalle})" if detalle else "")
        )

    if nivel is Nivel.AMBAR:
        raise NecesitaAprobacion(accion, detalle)
