# -*- coding: utf-8 -*-
"""Incremento 7: Proveedores (salud con enfriamiento/motivo y uso real a 1, 7 y 30 dias)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from interfaz import lecturas
from nucleo import enfriamiento, uso_proveedores


@pytest.fixture(autouse=True)
def registros_uso(tmp_path, monkeypatch):
    """uso_proveedores.jsonl y enfriamiento.json de prueba (nunca los reales)."""
    ruta = tmp_path / "registros" / "uso_proveedores.jsonl"
    monkeypatch.setattr(uso_proveedores, "REGISTRO", ruta)
    monkeypatch.setattr(enfriamiento, "ALMACEN", tmp_path / "memoria" / "enfriamiento.json")
    return ruta


def _linea(proveedor, hace_dias, estado="OK", entrada=400, salida=400, segundos=2.0):
    cuando = (datetime.now() - timedelta(days=hace_dias)).isoformat(timespec="seconds")
    return json.dumps({"cuando": cuando, "proveedor": proveedor, "estado": estado,
                       "entrada": entrada, "salida": salida, "segundos": segundos})


# ------------------------------------------------------------------ core: totales()
def test_totales_por_periodo_y_lineas_rotas_no_revientan(registros_uso):
    registros_uso.write_text("\n".join([
        _linea("groq", 0.1), _linea("groq", 0.2, estado="ERROR", salida=0),
        _linea("gemini", 3), _linea("chatgpt", 20),
        "{roto", json.dumps({"cuando": "no-es-fecha", "proveedor": "x"}), json.dumps({"proveedor": "y"}),
    ]) + "\n", encoding="utf-8")
    assert uso_proveedores.totales(1) == {"groq": {"n": 2, "ok": 1, "entrada": 800, "salida": 400, "seg": 4.0}}
    assert set(uso_proveedores.totales(7)) == {"groq", "gemini"}
    assert set(uso_proveedores.totales(30)) == {"groq", "gemini", "chatgpt"}
    # El texto de Telegram sigue igual y ya no revienta con la fecha rota.
    assert uso_proveedores.resumen(1).splitlines()[1].startswith("- groq: 2 llamadas (1 OK)")


def test_totales_sin_registro():
    assert uso_proveedores.totales(30) == {}
    assert uso_proveedores.resumen(30) == "Sin llamadas a proveedores registradas en ese periodo."


# ------------------------------------------------------------------ pagina
def test_pagina_pinta_paneles_periodos_y_disparadores(cliente, csrf):
    r = cliente.get("/proveedores")
    assert r.status_code == 200
    assert 'hx-get="/proveedores/salud"' in r.text and 'hx-get="/proveedores/uso"' in r.text
    assert 'hx-include="#periodo-uso"' in r.text and "nexo:log from:body throttle:5s" in r.text
    for d in (1, 7, 30):
        assert f'name="dias" value="{d}"' in r.text
    assert r.text.count('class="esqueleto"') == 2
    assert 'aria-current="page"' in r.text  # la pestaña Proveedores marcada


def test_requieren_sesion(cliente):
    for url in ("/proveedores/salud", "/proveedores/uso?dias=7"):
        assert cliente.get(url).status_code == 401


# ------------------------------------------------------------------ salud
def test_salud_muestra_enfriamiento_y_motivo(cliente, csrf, proveedores_falsos, monkeypatch):
    monkeypatch.setattr(proveedores_falsos, "respuesta", {"disponible": False, "motivo": "cuota agotada"})
    enfriamiento.enfriar("falso", "cuota", "429 de la API")
    r = cliente.get("/proveedores/salud").text
    assert "En enfriamiento" in r and "cuota hasta" in r and "429 de la API" in r and "cuota agotada" in r


def test_salud_error_al_comprobar_no_filtra_el_mensaje(cliente, csrf, proveedores_falsos, monkeypatch):
    monkeypatch.setattr(proveedores_falsos, "respuesta", RuntimeError("clave=SECRETA"))
    r = cliente.get("/proveedores/salud").text
    assert "Error al comprobar" in r and "RuntimeError" in r and "SECRETA" not in r


def test_salud_usa_cache_y_comprobar_ahora_la_renueva(cliente, csrf, proveedores_falsos, monkeypatch):
    cliente.get("/proveedores/salud")
    cliente.get("/proveedores/salud")
    assert proveedores_falsos.llamadas == 1
    # Con ?fresco=1 la cache solo vale FRESCO_MIN segundos: se simula que ya pasaron.
    lecturas._cache_proveedores["cuando"] -= 10
    cliente.get("/proveedores/salud", params={"fresco": 1})
    assert proveedores_falsos.llamadas == 2
    cliente.get("/proveedores/salud", params={"fresco": 1})  # otra vez al momento: no martillea
    assert proveedores_falsos.llamadas == 2


# ------------------------------------------------------------------ uso
def test_uso_vacio(cliente, csrf):
    r = cliente.get("/proveedores/uso", params={"dias": 7}).text
    assert "Sin llamadas a proveedores registradas en los últimos 7 días." in r


def test_uso_tabla_por_periodo(cliente, csrf, registros_uso):
    registros_uso.write_text("\n".join([
        _linea("falso", 0.1, entrada=4000, salida=4000, segundos=3.0),
        _linea("falso", 0.2, estado="ERROR", entrada=4000, salida=0, segundos=1.0),
        _linea("otro", 10),
    ]) + "\n", encoding="utf-8")
    r = cliente.get("/proveedores/uso", params={"dias": 1}).text
    assert "el último día" in r
    # falso: 2 llamadas, 1 OK, 1 fallo, 50 %, 12000 caracteres -> 3.000 tokens, 2.0 s de media
    fila = r[r.index(">falso<"):r.index("</tr>", r.index(">falso<"))]
    for trozo in (">2<", ">1<", "<strong>1</strong>", "50 %", "3.000", "2.0 s"):
        assert trozo in fila
    assert ">otro<" not in r  # su llamada es de hace 10 dias
    r30 = cliente.get("/proveedores/uso", params={"dias": 30}).text
    assert ">otro<" in r30 and "los últimos 30 días" in r30


def test_uso_periodo_invalido(cliente, csrf):
    assert cliente.get("/proveedores/uso", params={"dias": 3}).status_code == 400
    assert cliente.get("/proveedores/uso", params={"dias": "x"}).status_code == 422


def test_uso_fallo_de_lectura_da_panel_de_error(cliente, csrf, monkeypatch):
    def rompe(dias):
        raise OSError("disco")
    monkeypatch.setattr(uso_proveedores, "totales", rompe)
    r = cliente.get("/proveedores/uso", params={"dias": 1})
    assert r.status_code == 200 and 'role="alert"' in r.text and 'hx-get="/proveedores/uso"' in r.text
