# -*- coding: utf-8 -*-
"""T859 bloque 6: la tarjeta de huecos de reels en Bandejas (pegar / no merece la pena). Sin red."""
from __future__ import annotations

import json

import pytest

from extremidades import reels
from nucleo import reels_huecos as H


@pytest.fixture
def huecos(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "ALMACEN", tmp_path / "huecos.json")
    monkeypatch.setattr(reels, "CARPETA", tmp_path / "reels")
    ficha = {"codigo": "C1", "url": "https://www.instagram.com/reel/C1/", "autor": "autor", "tema": "repos",
             "llamada": {"hay": True, "tipo": "comenta", "palabra": "DECODE", "promete": "el repo"},
             "completitud": {"faltan": 2, "prometidos": 5}, "elementos": []}
    H.registrar([ficha])
    reels.guardar_bruto("C1", {"pie": "p"})
    return tmp_path


def _post(cliente, csrf, url, **datos):
    return cliente.post(url, data=datos, headers={"X-CSRF-Token": csrf})


def test_tarjeta_con_enlace_palabra_y_botones(cliente, csrf, huecos):
    html = cliente.get("/centro/reels_huecos").text
    assert "comentar «DECODE» en el reel de @autor" in html and 'href="https://www.instagram.com/reel/C1/"' in html
    assert 'value="pegado"' in html and 'value="no_merece"' in html and "faltan 2" in html
    assert 'hx-get="/centro/reels_huecos"' in cliente.get("/bandejas").text


def test_pegado_guarda_como_dato_y_quita_la_tarjeta(cliente, csrf, huecos):
    r = _post(cliente, csrf, "/reels/hueco", codigo="C1", accion="pegado", texto="morluto/rea <script>x</script>")
    assert "Guardado" in r.text and "DECODE" not in r.text
    bruto = json.loads((huecos / "reels" / "C1.json").read_text(encoding="utf-8"))
    assert bruto["reprocesar"] and bruto["pegado"][0]["confiable"] is False


def test_no_merece_y_errores(cliente, csrf, huecos):
    assert "no hay nada pegado" in _post(cliente, csrf, "/reels/hueco", codigo="C1", accion="pegado", texto=" ").text
    assert "Apartado" in _post(cliente, csrf, "/reels/hueco", codigo="C1", accion="no_merece").text
    assert "ya esta no_merece" in _post(cliente, csrf, "/reels/hueco", codigo="C1", accion="no_merece").text
    assert "acción desconocida" in _post(cliente, csrf, "/reels/hueco", codigo="C1", accion="borrar").text


def test_requiere_sesion(cliente, huecos):
    assert cliente.get("/centro/reels_huecos").status_code == 401
