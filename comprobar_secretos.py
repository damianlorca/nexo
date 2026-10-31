"""Busca los secretos de `secretos.toml` en claro por el proyecto, SIN imprimir nunca un valor.

Antes del primer commit hay que saber que archivos los llevan dentro, para asegurarse de que el .gitignore los tapa.
T624/T625 (propuestas de T613):
  - lo que no se pudo leer (archivo o subarbol inaccesible) sale como NO AUDITADO, no como limpio;
  - se miran tambien los valores en listas y los cortos (8 o mas caracteres);
  - de cada archivo con un secreto se dice si esta versionado (grave) o sin ignorar (aviso);
  - exposicion historica: commits (solo el hash corto) en cuyo diff aparece el valor, aunque el archivo ya no exista.
Solo se imprimen nombres de clave, rutas y hashes. (`git log -S` recibe el valor como argumento: es visible unos
segundos en la lista de procesos de este mismo PC; no sale de el.)
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).parent
MIN_VALOR = 8
SALTAR = {".venv", ".venv-implementador", "__pycache__", ".git"}
TOKEN_TELEGRAM = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")
BLOQUE = 1 << 20          # caracteres leidos de cada vez (T709: read_text cargaba el archivo entero y daba MemoryError)
SOLAPE_MIN = 64           # el token de Telegram mide >= 8+1+30; el solape real es max(esto, el valor mas largo)


def buscar(d, camino=""):
    """(clave, valor) de cada cadena de MIN_VALOR o mas caracteres, tambien dentro de listas (`lista[0]`)."""
    if isinstance(d, dict):
        for k, v in d.items():
            yield from buscar(v, f"{camino}{k}" if not isinstance(v, dict) else f"{camino}{k}.")
    elif isinstance(d, list):
        for i, v in enumerate(d):
            yield from buscar(v, f"{camino.rstrip('.')}[{i}]")
    elif isinstance(d, str) and len(d) >= MIN_VALOR:
        yield camino, d


def cargar_valores(ruta: Path) -> list[tuple[str, str]]:
    with open(ruta, "rb") as f:
        return list(buscar(tomllib.load(f)))


def _git(raiz: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["git", *args], cwd=str(raiz), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, r.stdout


def revisar_archivo(p: Path, valores: list[tuple[str, str]]) -> tuple[list[str], bool]:
    """(claves cuyo valor aparece, hay forma de token de Telegram) leyendo por bloques con solape.

    Entre un bloque y el siguiente se conservan los ultimos `solape-1` caracteres, asi un valor (o un token)
    cortado por la frontera se encuentra igual. Puede lanzar OSError o MemoryError: lo trata quien llama."""
    solape = max([SOLAPE_MIN, *(len(v) for _, v in valores)])
    claves: list[str] = []
    pendientes = {c: v for c, v in valores}
    telegram, cola = False, ""
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        while True:
            bloque = f.read(BLOQUE)
            if not bloque:
                break
            ventana = cola + bloque
            for c in [c for c, v in pendientes.items() if v in ventana]:
                claves.append(c)
                del pendientes[c]
            telegram = telegram or bool(TOKEN_TELEGRAM.search(ventana))
            cola = ventana[-(solape - 1):]
    return claves, telegram


def escanear(raiz: Path, valores: list[tuple[str, str]]) -> dict:
    """{"encontrados": {ruta: [claves]}, "no_auditados": [rutas], "telegram": [rutas con forma de token]}."""
    res = {"encontrados": {}, "no_auditados": [], "telegram": []}

    def rel(p: Path) -> str:
        return p.relative_to(raiz).as_posix()

    def recorrer(carpeta: Path):
        try:
            hijos = sorted(carpeta.iterdir())
        except OSError:
            res["no_auditados"].append(rel(carpeta) + "/")
            return
        for p in hijos:
            if p.name in SALTAR:
                continue
            try:
                es_dir = p.is_dir()
                es_arch = p.is_file()
            except OSError:
                res["no_auditados"].append(rel(p))
                continue
            if es_dir:
                recorrer(p)
            elif es_arch and not (p.name == "secretos.toml" and p.parent == raiz):
                try:
                    claves, telegram = revisar_archivo(p, valores)
                except (OSError, MemoryError):      # T709: cualquier fallo de lectura es NO AUDITADO, nunca limpio
                    res["no_auditados"].append(rel(p))
                    continue
                if claves:
                    res["encontrados"].setdefault(rel(p), []).extend(claves)
                if telegram:
                    res["telegram"].append(rel(p))

    recorrer(raiz)
    res["no_auditados"].sort()
    return res


def estado_git(raiz: Path, encontrados: dict) -> dict:
    """De los archivos con secreto: `versionados` (git ls-files; grave) y `sin_ignorar` (ni versionados ni en
    .gitignore: un `git add -A` los subiria)."""
    _, salida = _git(raiz, "ls-files")
    versionados = sorted(r for r in encontrados if r in set(salida.splitlines()))
    sin_ignorar = sorted(r for r in encontrados if r not in versionados
                         and _git(raiz, "check-ignore", "-q", "--", r)[0] != 0)
    return {"versionados": versionados, "sin_ignorar": sin_ignorar}


def historial(raiz: Path, valores: list[tuple[str, str]]) -> dict[str, list[str]]:
    """{clave: [hash corto de cada commit cuyo diff anade o quita el valor]}; solo las claves con commits."""
    salida = {}
    for clave, valor in valores:
        codigo, texto = _git(raiz, "log", "--all", "--format=%h", "-S", valor)
        if codigo == 0 and texto.split():
            salida[clave] = texto.split()
    return salida


def informe(raiz: Path = RAIZ) -> int:
    """Imprime el informe (nunca valores). Devuelve 1 si hay exposicion o algo sin auditar, 0 si todo esta limpio."""
    valores = cargar_valores(raiz / "secretos.toml")
    print(f"Secretos con pinta de credencial: {[c for c, _ in valores]}\n")
    res = escanear(raiz, valores)
    est = estado_git(raiz, res["encontrados"])
    hist = historial(raiz, valores)
    if res["encontrados"]:
        print("ARCHIVOS CON SECRETOS EN CLARO (no se imprime el valor):")
        for ruta, claves in sorted(res["encontrados"].items()):
            marca = "VERSIONADO" if ruta in est["versionados"] else "SIN IGNORAR" if ruta in est["sin_ignorar"] \
                else "ignorado"
            print(f"  {ruta:55} <- {', '.join(sorted(set(claves)))}  [{marca}]")
    else:
        print("Ningun archivo auditado lleva un secreto en claro.")
    if hist:
        print("\nEXPOSICION HISTORICA (commits cuyo diff toca el valor):")
        for clave, hashes in hist.items():
            print(f"  {clave}: {', '.join(hashes[:10])}{' ...' if len(hashes) > 10 else ''}")
    else:
        print("\nNingun commit del historial contiene un secreto.")
    if res["no_auditados"]:
        print("\nNO AUDITADOS (no se pudieron leer; no cuentan como limpios):")
        for ruta in res["no_auditados"]:
            print(f"  {ruta}")
    print("\nOtras cadenas con forma de token de Telegram (digitos:letras):")
    for ruta in sorted(res["telegram"]):
        print(f"  {ruta}")
    return int(bool(est["versionados"] or hist or res["no_auditados"]))


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    sys.exit(informe())
