# -*- coding: utf-8 -*-
"""T708: la guardia de ejecucion (nucleo/guardia_python.py) escribe una linea en stderr por bloqueo; si algo reintenta
sin fin, el log crece sin limite (280 GB el 23-24/09). Con el parche documentacion/parches/T708_guardia_tope_stderr.patch
solo se escriben MAX_AVISOS lineas, una mas de "silenciados", y GuardiaBloqueo se lanza siempre.

Se prueba en un proceso aparte (el audit hook de Python no se puede quitar). Los intentos de escritura apuntan a un
archivo blindado y los corta el hook ANTES de abrirlo: no se escribe nada."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

SCRIPT = '''
import sys
from pathlib import Path
objetivo = Path(sys.argv[1])
bloqueos = 0
for _ in range(205):
    try:
        open(objetivo, "a")
    except RuntimeError as e:        # GuardiaBloqueo
        if "GUARDIA NEXO" in str(e):
            bloqueos += 1
print("BLOQUEOS", bloqueos)
'''


def test_tope_de_avisos_en_stderr_y_el_bloqueo_sigue(tmp_path):
    script = tmp_path / "intentos.py"
    script.write_text(SCRIPT, encoding="utf-8")
    objetivo = RAIZ / "nucleo" / "permisos.py"                 # blindado: el hook corta antes de abrir
    r = subprocess.run([sys.executable, str(RAIZ / "nucleo" / "guardia_python.py"), str(script), str(objetivo)],
                       capture_output=True, text=True, timeout=60, cwd=str(RAIZ))
    assert "BLOQUEOS 205" in r.stdout, r.stdout + r.stderr          # los 205 se cortan igual
    avisos = [l for l in r.stderr.splitlines() if l.startswith("GUARDIA NEXO")]
    assert len(avisos) == 201, len(avisos)                          # 200 avisos + 1 de "silenciados"
    assert "mas de 200 bloqueos" in avisos[-1]
