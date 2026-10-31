# -*- coding: utf-8 -*-
"""T750: la carpeta privada del perfil (memoria/perfil_privado/) y memoria/radares/perfil.json no van a git, ni al
espejo de la nube, ni en un prompt (auditor de prompts y chat de cada tarea). El texto es INVENTADO: el test nunca
lee los archivos reales."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from nucleo import auditor, chat_tarea

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "herramientas_nube"))
import publicar_nube  # noqa: E402

FRASE = "Trabaje tres veranos cuidando faros abandonados en la costa de Islandia"


@pytest.fixture
def perfil_falso(tmp_path, monkeypatch):
    carpeta = tmp_path / "perfil_privado"
    carpeta.mkdir()
    (carpeta / "perfil.md").write_text(f"# Perfil\n\n- {FRASE}\n- 2024\n", encoding="utf-8")
    radares = tmp_path / "perfil.json"
    radares.write_text(json.dumps({"intereses": ["coleccion de relojes de arena del siglo XIX"]}), encoding="utf-8")
    monkeypatch.setattr(auditor, "RUTAS_PERFIL", [carpeta, radares])
    auditor._cache_perfil.clear()
    yield
    auditor._cache_perfil.clear()


@pytest.mark.parametrize("ruta", ["memoria/perfil_privado/perfil.md", "memoria/perfil_privado/cv/x.pdf",
                                  "memoria/radares/perfil.json"])
def test_git_los_ignora(ruta):
    r = subprocess.run(["git", "check-ignore", "--no-index", "-v", ruta], cwd=RAIZ, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith(".gitignore:"), r.stdout + r.stderr


@pytest.mark.parametrize("ruta", ["memoria/perfil_privado/perfil.md", "memoria/radares/perfil.json"])
def test_el_espejo_los_excluye(ruta):
    assert publicar_nube.excluida(ruta)
    assert not publicar_nube.excluida("memoria/radares/otro.json")


def test_prompt_con_texto_del_perfil_se_bloquea(perfil_falso):
    prompt = f"Redacta una carta de presentacion. Dato: {FRASE.lower()}  y poco mas."
    problemas = auditor.revisar_prompt(prompt, "generar")
    assert "texto del perfil privado" in auditor.motivos_privados(prompt)
    assert "texto del perfil privado" in chat_tarea.privado({"id": "T1", "etiquetas": []}, prompt)
    assert any("perfil privado" in p for p in problemas)


def test_valor_del_json_de_radares_tambien(perfil_falso):
    assert auditor.perfil_privado("Busca ofertas sobre coleccion de relojes de arena del siglo XIX, por favor")


def test_lineas_cortas_y_texto_ajeno_no_bloquean(perfil_falso):
    assert auditor.motivos_privados("Resume el informe de 2024 sobre el perfil de los modelos") == []


def test_la_ruta_tambien_se_bloquea():
    assert "ruta del perfil privado" in auditor.motivos_privados("lee memoria/perfil_privado/perfil.md")
    assert "ruta del perfil privado" in auditor.motivos_privados(r"memoria\radares\perfil.json")
