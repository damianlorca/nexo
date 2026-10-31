# -*- coding: utf-8 -*-
"""Aplica los parches de N01 aunque GitHub los haya guardado en LF.

Por que existe: los parches se subieron por la API de GitHub (git push esta en el deny de
.claude/settings.json), y GitHub los guarda en LF. Muchos archivos del repo son CRLF
(canal/bot.py, router.py...), asi que un `git apply` normal falla con "patch does not apply".

Que hace, para cada parche, en orden:
  1. `git apply --check`. Si pasa, `git apply` normal y listo.
  2. Si no pasa: apunta que archivos tocados eran CRLF, aplica con `--ignore-whitespace` y
     devuelve esos archivos a CRLF. El resultado queda igual que con el parche original.
No hace commit ni toca nada fuera de los archivos del parche. Si algo falla, para.

Uso (desde la raiz del repo):
    .venv\\Scripts\\python.exe documentacion\\propuestas\\aplicar_n01.py N01_arreglos.patch N01_archivar.patch
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True)


def tocados(parche: Path) -> list[tuple[str, str]]:
    """(ruta antes, ruta despues) de cada archivo del parche. Archivo nuevo: antes = ''."""
    pares, antes = [], None
    for linea in parche.read_text(encoding="utf-8").splitlines():
        m = re.match(r"diff --git a/(.+?) b/(.+)$", linea)
        if m:
            antes = m.group(1)
            pares.append([antes, m.group(2)])
        elif linea.startswith("new file mode") and pares:
            pares[-1][0] = ""
    return [tuple(p) for p in pares]


def es_crlf(ruta: str) -> bool:
    p = RAIZ / ruta
    return bool(ruta) and p.is_file() and b"\r\n" in p.read_bytes()


def aplicar(nombre: str) -> None:
    parche = Path(nombre)
    if not parche.is_absolute():
        parche = AQUI / nombre if (AQUI / nombre).is_file() else RAIZ / nombre
    if git("apply", "--check", str(parche)).returncode == 0:
        r = git("apply", str(parche))
        if r.returncode:
            sys.exit(f"{parche.name}: fallo al aplicar: {r.stderr.strip()}")
        print(f"OK  {parche.name} (aplicado tal cual)")
        return
    crlf = [despues for antes, despues in tocados(parche) if es_crlf(antes)]
    if not crlf:
        # T843: --ignore-whitespace solo para el problema previsto (parche en LF sobre archivos CRLF). Si ningun
        # archivo tocado es CRLF, el fallo es otro y aflojar los espacios podria aplicar un parche que no toca.
        sys.exit(f"{parche.name}: no aplica y ningun archivo tocado es CRLF: no es el problema previsto, "
                 f"no se afloja nada. {git('apply', '--check', str(parche)).stderr.strip()}")
    r = git("apply", "--ignore-whitespace", str(parche))
    if r.returncode:
        sys.exit(f"{parche.name}: no aplica ni ignorando espacios: {r.stderr.strip()}")
    devueltos = 0
    for ruta in crlf:
        p = RAIZ / ruta
        if not p.is_file():   # T842: el parche puede haberlo borrado o movido
            continue
        p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        devueltos += 1
    print(f"OK  {parche.name} (LF -> aplicado y {devueltos} archivos devueltos a CRLF)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for n in sys.argv[1:]:
        aplicar(n)
