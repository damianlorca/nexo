# -*- coding: utf-8 -*-
"""T697: boton "Cuéntamelo ahora" del Centro (POST con CSRF) y que los tests nunca arrancan el oyente del altavoz."""
from __future__ import annotations

from extremidades import altavoz


def test_boton_en_el_centro(cliente, csrf):
    html = cliente.get("/").text
    assert 'hx-post="/centro/brief"' in html and "Cuéntamelo ahora" in html


def test_post_lanza_el_brief_con_csrf(cliente, csrf, monkeypatch):
    lanzados = []
    monkeypatch.setattr(altavoz, "contar_en_hilo", lambda cc=None: lanzados.append(cc))
    r = cliente.post("/centro/brief", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and "Preparando el brief" in r.text
    assert lanzados == [None]


def test_post_sin_csrf_no_lanza_nada(cliente, csrf, monkeypatch):
    lanzados = []
    monkeypatch.setattr(altavoz, "contar_en_hilo", lambda cc=None: lanzados.append(cc))
    r = cliente.post("/centro/brief")
    assert r.status_code == 403 and lanzados == []


def test_la_web_de_los_tests_no_escucha_el_altavoz(cliente):
    assert altavoz.oyente_activo() is None
