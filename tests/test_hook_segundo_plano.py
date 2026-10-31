# -*- coding: utf-8 -*-
"""Tests del hook que obliga a lanzar en segundo plano los comandos largos de Claude Code."""
import json
import subprocess
import sys
from pathlib import Path

from nucleo.hook_segundo_plano import motivo

HOOK = Path(__file__).resolve().parent.parent / "nucleo" / "hook_segundo_plano.py"


def _e(cmd, bg=False, tool="Bash"):
    ti = {"command": cmd}
    if bg:
        ti["run_in_background"] = True
    return {"tool_name": tool, "tool_input": ti}


def test_suite_completa_en_primer_plano_se_bloquea():
    assert motivo(_e(r".venv\Scripts\python.exe -m pytest tests interfaz\tests -q"))


def test_suite_en_segundo_plano_pasa():
    assert motivo(_e(r".venv\Scripts\python.exe -m pytest tests interfaz\tests -q", bg=True)) == ""


def test_un_archivo_de_test_pasa():
    assert motivo(_e(r".venv\Scripts\python.exe -m pytest tests\test_tareas.py -q")) == ""


def test_un_import_pytest_dentro_de_un_heredoc_no_es_la_suite():
    """13/10: el hook bloqueaba 'cat >> tests/x.py <<EOF ... import pytest ... EOF' seguido de un solo archivo."""
    cmd = ("cat >> tests/test_x.py <<'EOF'\nimport pytest\n@pytest.mark.parametrize('a', [1])\nEOF\n"
           r".venv\Scripts\python.exe -m pytest tests\test_x.py -q")
    assert motivo(_e(cmd)) == ""
    assert motivo(_e("echo hola && pytest tests -q"))
    assert motivo(_e("pytest"))
    assert motivo(_e("cd x; .venv/Scripts/python.exe -m pytest tests interfaz/tests -q"))


def test_espera_corta_pasa_y_larga_se_bloquea():
    assert motivo(_e("sleep 5")) == ""
    assert motivo(_e("sleep 120"))
    assert motivo(_e("Start-Sleep -Seconds 90", tool="PowerShell"))


def test_banco_turno_implementador_descargas():
    assert motivo(_e(r".venv\Scripts\python.exe -m nucleo.banco_modelos correr --roles revisar"))
    assert motivo(_e(r".venv\Scripts\python.exe turno_nexo.py --turno implpil2"))
    assert motivo(_e(r".venv\Scripts\python.exe -m nucleo.piloto_serie puerta"))
    assert motivo(_e("ollama pull qwen2.5vl:7b"))


def test_comandos_cortos_y_otras_herramientas_pasan():
    assert motivo(_e("git status")) == ""
    assert motivo(_e(r".venv\Scripts\python.exe -m nucleo.tareas buscar T837")) == ""
    assert motivo({"tool_name": "Read", "tool_input": {"file_path": "x"}}) == ""


def test_proceso_real_exit_codes_y_falla_en_abierto():
    def correr(texto):
        return subprocess.run([sys.executable, str(HOOK)], input=texto, capture_output=True, text=True,
                              encoding="utf-8", timeout=30)
    r = correr(json.dumps(_e("sleep 300")))
    assert r.returncode == 2 and "run_in_background" in r.stderr
    assert correr(json.dumps(_e("git status"))).returncode == 0
    assert correr("esto no es json").returncode == 0
