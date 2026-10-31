# -*- coding: utf-8 -*-
"""--help / -h en los scripts de entrada sin ejecutar nada (incidente 05/10/2026, 17:01).

Prueba el helper nucleo.ayuda, comprueba con AST que el primer statement de cada bloque
`if __name__ == "__main__":` llama a ayuda.atender (o que el script usa argparse, que ya responde a -h sin
ejecutar nada) y EJECUTA de verdad unos cuantos scripts con --help en un subproceso: la comprobacion estatica
sola no vio que nucleo/guardia_python.py, lanzado como script, tiene nucleo/ en sys.path[0] y no puede hacer
`from nucleo import ayuda` (05/10: fallaban todos los ejecutar_python).
"""
from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import pytest

from nucleo import ayuda

RAIZ = Path(__file__).resolve().parents[1]
# Fuera: blindados (manos/), datos, tests y dos scripts que no pueden importar nucleo.
EXCLUIDOS_PREFIJO = ("manos/", "memoria/", "tests/", "interfaz/tests/", "_archivo/", "_respaldos/")
EXCLUIDOS = {"nucleo/ayuda.py", "extremidades/arrancar_comfyui.py", "documentacion/propuestas/aplicar_n01.py"}
PYTHON = RAIZ / ".venv" / "Scripts" / "python.exe"


def _entradas() -> list[str]:
    r = subprocess.run(["git", "ls-files", "*.py"], cwd=RAIZ, capture_output=True, text=True)
    salida = []
    for f in r.stdout.split():
        if f in EXCLUIDOS or f.startswith(EXCLUIDOS_PREFIJO):
            continue
        texto = (RAIZ / f).read_text(encoding="utf-8-sig")
        if "__main__" in texto and _bloque_main(ast.parse(texto)) is not None:
            salida.append(f)
    return salida


def _bloque_main(arbol: ast.Module) -> ast.If | None:
    for nodo in arbol.body:
        if (isinstance(nodo, ast.If) and isinstance(nodo.test, ast.Compare)
                and isinstance(nodo.test.left, ast.Name) and nodo.test.left.id == "__name__"):
            return nodo
    return None


def _atiende_ayuda(texto: str) -> bool:
    if "argparse" in texto or 'in ("-h", "--help")' in texto:
        return True
    primero = _bloque_main(ast.parse(texto)).body
    # "from nucleo import ayuda; ayuda.atender(__doc__)" son dos statements en la misma linea; delante puede ir
    # uno que prepare sys.path para poder importar nucleo (guardia_python.py: su sys.path[0] es nucleo/)
    codigo = "\n".join(ast.unparse(s) for s in primero[:3])
    return "ayuda.atender(__doc__" in codigo


def test_hay_entradas():
    assert "turno_nexo.py" in _entradas()


@pytest.mark.parametrize("ruta", _entradas())
def test_cada_entrada_responde_a_help_antes_de_nada(ruta):
    assert _atiende_ayuda((RAIZ / ruta).read_text(encoding="utf-8-sig")), (
        f"{ruta}: su bloque __main__ debe empezar por 'from nucleo import ayuda; ayuda.atender(__doc__)'")


@pytest.mark.parametrize("arg", ["-h", "--help", "/?"])
def test_atender_imprime_y_sale(arg, capsys):
    with pytest.raises(SystemExit) as e:
        ayuda.atender("Uso: prueba", [arg])
    assert e.value.code == 0
    assert "Uso: prueba" in capsys.readouterr().out


def test_atender_no_hace_nada_sin_ayuda(capsys):
    ayuda.atender("Uso: prueba", ["--simular", "--turno=noche"])
    assert capsys.readouterr().out == ""


def test_atender_sin_docstring(capsys):
    with pytest.raises(SystemExit):
        ayuda.atender(None, ["--help"])
    assert "no tiene ayuda" in capsys.readouterr().out


# Scripts que se lanzan por RUTA (sys.path[0] = su carpeta) o con -m; todos solo importan y definen a nivel de
# modulo, asi que con --help no tocan nada. Si alguno dejara de atender --help, el test lo veria por la salida.
EJECUTADOS = [
    (["turno_nexo.py"], "turno"),
    (["prueba_tareas.py"], ""),
    (["canal/vigilante.py"], ""),
    (["-m", "nucleo.tareas"], ""),
    (["-m", "nucleo.radar"], "motor comun de radares"),
]


def _primera_linea_doc(cmd: list[str]) -> str:
    ruta = RAIZ / (cmd[0] if cmd[0] != "-m" else cmd[1].replace(".", "/") + ".py")
    doc = ast.get_docstring(ast.parse(ruta.read_text(encoding="utf-8-sig"))) or ""
    return doc.strip().splitlines()[0] if doc.strip() else "no tiene ayuda"


@pytest.mark.skipif(not PYTHON.exists(), reason="sin .venv")
@pytest.mark.parametrize("cmd,esperado", EJECUTADOS, ids=[" ".join(c) for c, _ in EJECUTADOS])
def test_help_ejecutado_de_verdad(cmd, esperado):
    r = subprocess.run([str(PYTHON), *cmd, "--help"], cwd=RAIZ, capture_output=True, timeout=120,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    salida = r.stdout.decode("utf-8", "replace")
    assert r.returncode == 0, f"{cmd}: codigo {r.returncode}\n{r.stderr.decode('utf-8', 'replace')[-800:]}"
    assert _primera_linea_doc(cmd)[:40] in salida
    assert esperado.lower() in salida.lower()
