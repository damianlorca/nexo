# -*- coding: utf-8 -*-
"""Catalogo de herramientas (nucleo/catalogo.py). Sin red.

Reproduce el fallo del turno del 28/09 (registros/turno_nexo_20260928_034618.json):
el paso "catalogo" peto con KeyError 'aplica_a' porque memoria/catalogo.json tenia un
item (H078) mas viejo que ese campo del esquema, y render_md() lo daba por garantizado.
"""
from __future__ import annotations

import json

import pytest

from nucleo import catalogo as C


@pytest.fixture
def cat(tmp_path, monkeypatch):
    (tmp_path / "vault").mkdir()
    monkeypatch.setattr(C, "ALMACEN", tmp_path / "catalogo.json")
    monkeypatch.setattr(C, "VISTA", tmp_path / "vault" / "catalogo-herramientas.md")
    monkeypatch.setattr(C, "CANDADO", tmp_path / ".candado_catalogo.lock")
    return tmp_path


def _escribir(tmp_path, items):
    (tmp_path / "catalogo.json").write_text(
        json.dumps({"version": 1, "actualizado": "", "items": items}, ensure_ascii=False), encoding="utf-8"
    )


def test_item_sin_campos_del_esquema_no_revienta_cargar_ni_render_md(cat):
    """Item real (H078) con solo un puñado de campos, sin 'aplica_a' ni otros de CAMPOS_TEXTO."""
    _escribir(cat, [{
        "id": "H078", "nombre": "Kilo Code", "categoria": "herramientas_dev",
        "para_que_sirve": "agente de codigo", "veredicto": "PENDIENTE", "auditado": "primera_pasada",
        "instalado": "no", "testeado": "no", "orden_auditoria": 78,
    }])
    datos = C.cargar()
    it = datos["items"][0]
    assert it["aplica_a"] == "" and it["funcional"] == "-"
    md = C.render_md(datos)  # antes: KeyError: 'aplica_a'
    assert "Kilo Code" in md


def test_guardar_no_revienta_con_item_incompleto(cat):
    _escribir(cat, [{"id": "H001", "nombre": "X", "categoria": "c", "para_que_sirve": "y",
                      "veredicto": "PENDIENTE", "auditado": "no", "instalado": "no",
                      "testeado": "-", "orden_auditoria": 1}])
    datos = C.cargar()
    C.guardar(datos)  # antes: escribir_atomico(VISTA, render_md(datos)) reventaba
    assert C.VISTA.is_file()


def test_poner_sobre_otro_item_regenera_la_vista_pese_a_un_item_viejo_incompleto(cat):
    """El escenario exacto del turno: poner() en un item completo dispara guardar() -> render_md()
    sobre TODOS los items, incluido uno viejo sin 'aplica_a'."""
    _escribir(cat, [
        {"id": "H001", "nombre": "Completo", "categoria": "c", "para_que_sirve": "y", "aplica_a": "NEXO",
         "veredicto": "PENDIENTE", "auditado": "no", "instalado": "no", "testeado": "-", "orden_auditoria": 1},
        {"id": "H078", "nombre": "Kilo Code", "categoria": "herramientas_dev", "para_que_sirve": "agente de codigo",
         "veredicto": "PENDIENTE", "auditado": "primera_pasada", "instalado": "no", "testeado": "no",
         "orden_auditoria": 78},
    ])
    it = C.poner("H001", auditado="primera_pasada")
    assert it["auditado"] == "primera_pasada"
    assert "Kilo Code" in C.VISTA.read_text(encoding="utf-8")


def test_plantilla_sigue_trayendo_todos_los_campos_de_texto():
    d = C._plantilla("nueva")
    for c in C.CAMPOS_TEXTO:
        assert c in d
