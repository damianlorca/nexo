# -*- coding: utf-8 -*-
"""--help / -h en los scripts de entrada sin ejecutar nada (incidente 05/10/2026, 17:01).

`python turno_nexo.py --help` ignoraba el argumento y arrancaba un turno REAL sobre T699; al cerrarlo
con taskkill /T cayo ademas un proceso hijo sin identificar. Desde entonces cada bloque
`if __name__ == "__main__":` de un script de entrada empieza por:

    from nucleo import ayuda; ayuda.atender(__doc__)

que, si en los argumentos hay -h, --help o /?, imprime el docstring del modulo y sale con 0 antes de
tocar nada. Lo comprueba tests/test_ayuda_entradas.py (de forma estatica: no ejecuta ningun script).
"""
from __future__ import annotations

import sys

PIDE_AYUDA = ("-h", "--help", "/?")


def pide_ayuda(argv: list[str] | None = None) -> bool:
    argv = sys.argv[1:] if argv is None else argv
    return any(a in PIDE_AYUDA for a in argv)


def atender(doc: str | None, argv: list[str] | None = None) -> None:
    """Si piden ayuda: imprime `doc` y sale (SystemExit 0). Si no, no hace nada."""
    if not pide_ayuda(argv):
        return
    try:
        from nucleo import consola
        consola.preparar()   # consola cp1252 de Windows
    except Exception:
        pass
    print((doc or "").strip() or "(este script no tiene ayuda escrita)")
    raise SystemExit(0)
