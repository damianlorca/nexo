# -*- coding: utf-8 -*-
"""--help en nucleo/guardia_python.py, EJECUTANDOLA de verdad como script (05/10).

La primera version (`from nucleo import ayuda` a secas) paso la comprobacion estatica de test_ayuda_entradas pero
rompia la guardia: lanzada como `python nucleo/guardia_python.py ...`, sys.path[0] es nucleo/ y el import daba
ModuleNotFoundError, asi que fallaban todos los ejecutar_python. Aqui se lanza en un proceso aparte (el audit hook
no se puede quitar) con un script de prueba que no escribe nada.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
GUARDIA = RAIZ / "nucleo" / "guardia_python.py"

SCRIPT = '''
import os, sys
if "--help" in sys.argv[1:]:
    print("AYUDA DEL SCRIPT")
    raise SystemExit(0)
print("ARGS", sys.argv[1:])
print("PATH0_ES_SU_CARPETA", os.path.normcase(sys.path[0]) == os.path.normcase(os.path.dirname(os.path.abspath(__file__))))
print("NUCLEO_EN_PATH", any(os.path.normcase(p) == os.path.normcase(sys.argv[-1]) for p in sys.path))
print("OK")
'''


def _guardia(*args, tmp_path=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GUARDIA), *map(str, args)], capture_output=True, text=True,
                          timeout=60, cwd=str(tmp_path or RAIZ), env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def _script(tmp_path: Path) -> Path:
    s = tmp_path / "normal.py"
    s.write_text(SCRIPT, encoding="utf-8")
    return s


def test_help_de_la_guardia_imprime_su_ayuda_y_sale():
    r = _guardia("--help")
    assert r.returncode == 0, r.stderr
    assert "Guardia de ejecucion" in r.stdout


def test_script_normal_bajo_la_guardia_funciona(tmp_path):
    nucleo = RAIZ / "nucleo"
    r = _guardia(_script(tmp_path), "uno", nucleo, tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout
    assert f"ARGS {['uno', str(nucleo)]!r}" in r.stdout
    assert "PATH0_ES_SU_CARPETA True" in r.stdout      # como `python script.py`
    assert "NUCLEO_EN_PATH False" in r.stdout          # nucleo/ no se cuela en sys.path


def test_el_help_del_script_vigilado_es_del_script(tmp_path):
    r = _guardia(_script(tmp_path), "--help", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "AYUDA DEL SCRIPT" in r.stdout
    assert "Guardia de ejecucion" not in r.stdout


def test_sin_argumentos_da_el_uso():
    r = _guardia()
    assert r.returncode == 2
    assert "uso:" in r.stderr
