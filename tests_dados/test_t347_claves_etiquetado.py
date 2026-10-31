# -*- coding: utf-8 -*-
"""T347: auto_etiquetado_router solo etiqueta 'router:claves:...' con claves bien delimitadas y validadas.

Piloto F3 (T669): estos tests los escribe Claude; el implementador solo cambia auto_etiquetado_router.py.
Contrato: la lista de claves se toma de UNA linea ("claves: a, b" o "campos: a, b"); cada clave es una sola palabra
(letras -incluidas tildes y ñ-, digitos o guion bajo, sin empezar por digito). Si alguna no lo es, no hay claves (None) y la tarea no se
etiqueta: es mejor no etiquetar que etiquetar una extraccion mal definida.
"""
from __future__ import annotations

import pytest

import auto_etiquetado_router as A


def test_las_claves_se_limitan_a_su_linea():
    detalle = "Ficha del cliente.\nclaves: nombre, edad\nEl resto del documento sigue aqui, con otras cosas."
    assert A._claves_de_detalle(detalle) == ["nombre", "edad"]


def test_las_claves_terminan_en_el_punto_final():
    assert A._claves_de_detalle("Datos del pedido. Campos: importe, moneda. Gracias.") == ["importe", "moneda"]


def test_una_clave_con_espacios_invalida_todo_el_listado():
    assert A._claves_de_detalle("campos: nombre, fecha de nacimiento") is None


@pytest.mark.parametrize("claves", ["nombre, 2edad", "nombre, ed@d", "nombre, a-b", "nombre, (edad)"])
def test_una_clave_con_simbolos_o_que_empieza_por_digito_invalida_el_listado(claves):
    assert A._claves_de_detalle(f"claves: {claves}") is None


def test_las_claves_con_tildes_y_enie_se_aceptan():
    """Piloto F3, 1.a ronda: el diff del implementador rompia esto (la regex vieja si lo admitia)."""
    assert A._claves_de_detalle("claves: año, número, dirección") == ["año", "número", "dirección"]
    assert A._claves_de_detalle("campos: Ñandú, ción_2") == ["Ñandú", "ción_2"]


def test_listados_validos_siguen_funcionando():
    assert A._claves_de_detalle("claves: nombre, edad_anos, Ciudad2") == ["nombre", "edad_anos", "Ciudad2"]
    assert A._claves_de_detalle("sin patron alguno") is None
    assert A._claves_de_detalle("claves:") is None


DETALLE_BASE = ("Registro de la entrevista realizada ayer por la tarde con la persona candidata, con todos los datos "
                "personales y laborales que hay que extraer del texto: ")


def _tarea(detalle):
    return {"id": "T9000", "titulo": "Extraer datos", "detalle": detalle, "estado": "pendiente", "etiquetas": []}


def test_con_una_clave_invalida_la_candidata_no_se_etiqueta(monkeypatch):
    monkeypatch.setattr(A.T, "listar", lambda **kw: [_tarea(DETALLE_BASE + "claves: nombre, fecha de nacimiento")])
    monkeypatch.setattr("extremidades.qwen.clasificar", lambda *a, **k: "extraccion")
    r = A.evaluar_candidatas()
    assert r["etiquetables"] == []
    assert [t["id"] for t in r["extraccion_sin_claves"]] == ["T9000"]


def test_con_claves_validas_la_candidata_si_se_etiqueta(monkeypatch):
    monkeypatch.setattr(A.T, "listar", lambda **kw: [_tarea(DETALLE_BASE + "claves: nombre, edad")])
    monkeypatch.setattr("extremidades.qwen.clasificar", lambda *a, **k: "extraccion")
    r = A.evaluar_candidatas()
    assert [(t["id"], c, k) for t, c, k in r["etiquetables"]] == [("T9000", "extraccion", ["nombre", "edad"])]
