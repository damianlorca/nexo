# -*- coding: utf-8 -*-
"""T198: defectos pequenos de las CLIs de tareas y aprobaciones y de las suites prueba_*."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from nucleo import aprobaciones as ap
from nucleo import registro
from nucleo import tareas as T

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def cola(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "x.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado")
    return T.anadir("Tarea de prueba")


# 1) 'estado' con un solo argumento no se cae: explica el uso y sale con 2.
def test_cli_estado_sin_valor_no_se_cae(cola, capsys):
    assert T._cli(["estado", cola["id"]]) == 2
    assert "estado" in capsys.readouterr().out.lower()
    assert T._cli(["estado"]) == 2


def test_cli_estado_invalido_no_se_guarda(cola, capsys):
    assert T._cli(["estado", cola["id"], "inventado"]) == 2
    assert T.buscar(cola["id"])["estado"] == "pendiente"
    assert T._cli(["estado", cola["id"], "en_curso"]) == 0
    assert T.buscar(cola["id"])["estado"] == "en_curso"


# 2) 'anadir --etiquetas' guarda una lista, no el texto.
def test_cli_anadir_etiquetas_es_lista(cola):
    assert T._cli(["anadir", "Otra", "--etiquetas", "bug, cat:codigo ,tema:x"]) == 0
    t = next(t for t in T.cargar()["tareas"] if t["titulo"] == "Otra")
    assert sorted(t["etiquetas"]) == ["bug", "cat:codigo", "tema:x"]


def test_anadir_por_api_con_texto_tambien_es_lista(cola):
    assert T.anadir("Api", etiquetas="a,b")["etiquetas"] == ["a", "b"]


# 3) La CLI de aprobaciones registra el autor real, no 'damian' fijo.
@pytest.fixture
def almacen(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "ALMACEN", tmp_path / "aprobaciones.json")
    monkeypatch.setattr(ap, "HISTORIAL", tmp_path / "aprobaciones_historial.jsonl")
    monkeypatch.setattr(ap, "CANDADO", tmp_path / ".candado.lock")


def test_cli_aprobaciones_con_quien_explicito(almacen):
    s = ap.solicitar("x", "y")
    assert ap.main(["aprobar", s["id"], "--quien", "damian", "vale"]) == 0
    e = ap.ver(s["id"])["eventos"][-1]
    assert e["quien"] == "damian" and e["motivo"] == "vale"


def test_cli_aprobaciones_desde_claude_code_no_firma_como_damian(almacen, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    s = ap.solicitar("x", "y")
    ap.main(["denegar", s["id"], "no"])
    assert ap.ver(s["id"])["eventos"][-1]["quien"] == "claude-code"


def test_cli_aprobaciones_sin_identificar(almacen, monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    s = ap.solicitar("x", "y")
    ap.main(["aprobar", s["id"]])
    assert ap.ver(s["id"])["eventos"][-1]["quien"] == "cli (sin identificar)"


# 4) Las suites prueba_* no escriben en registros/ reales.
def test_aislar_manda_el_log_a_otra_carpeta(tmp_path, monkeypatch):
    raiz = logging.getLogger()
    antes = list(raiz.handlers)
    for nombre in ("CARPETA", "EVIDENCIA", "CANDADO_EVIDENCIA", "_configurado"):
        monkeypatch.setattr(registro, nombre, getattr(registro, nombre))
    monkeypatch.setattr(registro, "_configurado", True)
    try:
        destino = registro.aislar(tmp_path / "logs")
        registro.logger("prueba.t198").critical("TOKEN INVALIDO (401, 1/5) simulado")
        assert registro.CARPETA == destino and registro.EVIDENCIA.parent == destino
        log = next(destino.glob("agente_*.log")).read_text(encoding="utf-8")
        assert "TOKEN INVALIDO" in log
    finally:
        for h in list(raiz.handlers):
            if h not in antes:
                raiz.removeHandler(h)
                h.close()
        for h in antes:
            if h not in raiz.handlers:
                raiz.addHandler(h)


def test_las_suites_que_cargan_el_bot_se_aislan_antes():
    import_bot = re.compile(r"^\s*(import canal\.bot|from canal(\.bot)? import)", re.M)
    for f in sorted(RAIZ.glob("prueba_*.py")):
        texto = f.read_text(encoding="utf-8")
        m = import_bot.search(texto)
        if not m:
            continue
        aislar = texto.find("registro.aislar()")
        assert aislar != -1 and aislar < m.start(), f"{f.name} carga canal.bot sin registro.aislar() antes"


# Nota de T198: los scripts sueltos que se conectan al Chrome de NEXO usan el candado de T193.
def test_scripts_sueltos_usan_el_candado_del_chrome():
    for carpeta in ("herramientas_delegacion", "herramientas_logo"):
        for f in sorted((RAIZ / carpeta).glob("*.py")):
            texto = f.read_text(encoding="utf-8")
            if "connect_over_cdp" in texto:
                assert "en_exclusiva(" in texto, f"{carpeta}/{f.name} usa el Chrome de NEXO sin candado"
