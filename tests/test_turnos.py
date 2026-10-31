# -*- coding: utf-8 -*-
"""Interruptor de turnos (nucleo/turnos.py) y su efecto en turno_nexo.turno()."""
import pytest

from nucleo import turnos


@pytest.fixture
def bandera(tmp_path, monkeypatch):
    b = tmp_path / "TURNOS_DESACTIVADOS"
    monkeypatch.setattr(turnos, "BANDERA", b)
    return b


def test_por_defecto_activos(bandera):
    assert turnos.desactivados() is None
    assert turnos.estado() == "Turnos ACTIVADOS"


def test_desactivar_y_activar(bandera):
    turnos.desactivar("sin OK absoluto")
    assert turnos.desactivados() == "sin OK absoluto"
    assert "DESACTIVADOS" in turnos.estado()
    turnos.activar()
    assert turnos.desactivados() is None
    assert not bandera.exists()


def test_bandera_ilegible_cuenta_como_desactivados(bandera):
    bandera.write_text("{roto", encoding="utf-8")
    assert turnos.desactivados()


def test_turno_no_arranca_si_desactivados(bandera, monkeypatch):
    import turno_nexo
    turnos.desactivar("prueba")
    tomado = []
    monkeypatch.setattr(turno_nexo, "_tomar_candado", lambda: tomado.append(1) or True)
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: None)
    reg = turno_nexo.turno(simular=True, avisar=False)
    assert "TURNOS DESACTIVADOS" in reg["abortado"]
    assert not tomado  # ni siquiera toma el candado
