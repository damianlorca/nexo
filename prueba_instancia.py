"""Prueba del candado de instancia unica.

El padre coge el candado y lanza un hijo que intenta cogerlo. Si el
candado sirve, el hijo tiene que rebotar.

    .venv\\Scripts\\python.exe prueba_instancia.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo.instancia import pid_anotado, unico  # noqa: E402


NOMBRE = "prueba_candado"


def hijo() -> int:
    print("HIJO: ocupado" if not unico(NOMBRE) else "HIJO: libre")

    return 0


def padre() -> int:
    if not unico(NOMBRE):
        print("FALLO: el padre no ha podido coger un candado libre")
        print("       (¿quedo colgado de una prueba anterior?)")
        return 1

    print(f"PADRE: candado cogido, pid={pid_anotado(NOMBRE)}")

    r = subprocess.run(
        [sys.executable, str(RAIZ / "prueba_instancia.py"), "hijo"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    salida = (r.stdout or "").strip()

    print(salida or "(el hijo no dijo nada)")

    if r.stderr.strip():
        print("ERROR DEL HIJO:", r.stderr.strip()[:500])

    if "HIJO: ocupado" in salida:
        print("\nOK: el segundo proceso reboto. El candado sirve.")
        return 0

    print("\nFALLO: el hijo ha cogido el candado tambien. No sirve.")

    return 1


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    sys.exit(hijo() if len(sys.argv) > 1 and sys.argv[1] == "hijo" else padre())
