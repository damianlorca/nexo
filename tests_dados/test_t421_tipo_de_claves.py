# -*- coding: utf-8 -*-
"""T421: aplicar() valida el tipo de las claves antes de usar join().

Piloto F3 (T669): estos tests los escribe Claude; el implementador solo cambia auto_etiquetado_router.py.
Contrato: para 'extraccion', `claves` tiene que ser una lista o tupla NO vacia de str no vacios. Si es otra cosa (un
str suelto, elementos que no son str, None...), esa tarea NO se etiqueta, no se lanza ninguna excepcion y su id no sale
en la lista devuelta. Hoy un str "nombre,edad" se une letra a letra ("n,o,m,...") y una lista con enteros lanza
TypeError.
"""
from __future__ import annotations

import pytest

import auto_etiquetado_router as A


@pytest.fixture
def escrituras(monkeypatch):
    hechas = []
    monkeypatch.setattr(A.T, "actualizar", lambda tid, **kw: hechas.append((tid, kw)))
    monkeypatch.setattr(A.T, "anotar", lambda *a, **k: None)
    return hechas


def _t(i="T9100"):
    return {"id": i, "titulo": "x", "etiquetas": ["cat:otra"]}


def test_claves_validas_se_unen_con_comas(escrituras):
    assert A.aplicar([(_t(), "extraccion", ["nombre", "edad"])]) == ["T9100"]
    etiquetas = escrituras[0][1]["etiquetas"]
    assert etiquetas == ["cat:otra", "router:auto", "router:claves:nombre,edad"]


def test_un_str_suelto_no_se_une_letra_a_letra(escrituras):
    assert A.aplicar([(_t(), "extraccion", "nombre,edad")]) == []
    assert escrituras == []


@pytest.mark.parametrize("claves", [["nombre", 3], [None], [1, 2], ["a", ["b"]], {"a": 1}, 7, [""], []])
def test_claves_de_tipo_o_contenido_invalido_no_etiquetan_ni_lanzan(escrituras, claves):
    assert A.aplicar([(_t(), "extraccion", claves)]) == []
    assert escrituras == []


def test_una_invalida_no_impide_etiquetar_las_demas(escrituras):
    lote = [(_t("T9101"), "extraccion", [1]), (_t("T9102"), "extraccion", ["a"]), (_t("T9103"), "resumen", None)]
    assert A.aplicar(lote) == ["T9102", "T9103"]


def test_resumen_sin_claves_sigue_igual(escrituras):
    assert A.aplicar([(_t(), "resumen", None)]) == ["T9100"]
    assert escrituras[0][1]["etiquetas"] == ["cat:otra", "router:auto"]
