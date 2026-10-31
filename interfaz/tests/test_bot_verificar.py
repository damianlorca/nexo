# -*- coding: utf-8 -*-
"""T160 en el bot: /hecha pide la evidencia y /verificar solo marca con evidencia. Sin Telegram."""
from __future__ import annotations

import pytest

from nucleo import evidencias as E
from nucleo import tareas as T

bot = pytest.importorskip("canal.bot")  # necesita httpx (requisitos.txt)


def test_hecha_cierra_sin_testear_y_pide_la_evidencia():
    t = T.anadir("x")["id"]
    r = bot._cmd_hecha(f"{t} quedo asi")
    assert r.startswith("✅") and "HECHO SIN TESTEAR" in r and f"/verificar {t}" in r
    assert T.estado_real(T.buscar(t)) == "HECHO SIN TESTEAR"


def test_hecha_de_una_tarea_que_no_existe():
    assert "No encuentro" in bot._cmd_hecha("T999")


def test_verificar_con_evidencia_marca_y_la_guarda():
    t = T.anadir("x")["id"]
    bot._cmd_hecha(t)
    r = bot._cmd_verificar(f"{t} pytest interfaz/tests -q -> 308 passed")
    assert "HECHO Y TESTEADO" in r
    assert T.buscar(t)["testeado"] is True and E.validas(t)[0]["fuente"] == "tareas.verificar"


@pytest.mark.parametrize("evidencia", ["probada", "funciona bien", "ok"])
def test_verificar_con_un_tick_no_marca(evidencia):
    t = T.anadir("x")["id"]
    bot._cmd_hecha(t)
    r = bot._cmd_verificar(f"{t} {evidencia}")
    assert r.startswith("❌") and T.buscar(t)["testeado"] is False and E.de_tarea(t) == []


def test_verificar_sin_evidencia_da_el_uso():
    assert bot._cmd_verificar("T001").startswith("Uso:")
    assert bot._cmd_verificar("").startswith("Uso:")


def test_verificar_una_tarea_sin_cerrar_no_la_marca():
    t = T.anadir("x")["id"]
    r = bot._cmd_verificar(f"{t} pytest -q -> 3 passed")
    assert "no está hecha" in r and T.buscar(t)["testeado"] is False


def test_verificar_no_confunde_un_texto_con_un_id():
    T.anadir("T001 no es un id, es un titulo")
    assert "No encuentro" in bot._cmd_verificar("titulo pytest -q -> 3 passed")
