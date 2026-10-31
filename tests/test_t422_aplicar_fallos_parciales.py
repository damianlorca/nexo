# -*- coding: utf-8 -*-
"""T422: contrato explicito de auto_etiquetado_router.aplicar() ante fallos parciales.

Piloto F3 (T669): estos tests los escribe Claude; el implementador solo cambia auto_etiquetado_router.py.
Contrato:
- aplicar(etiquetables, discrepancias=None) -> list[str]: ids realmente etiquetados.
- Si T.actualizar (o T.anotar) lanza Exception para una tarea, se sigue con las demas; esa tarea NO sale en la lista y,
  si se paso una lista `discrepancias`, se le anade (id, motivo_texto).
- _cli(): con discrepancias, imprime cada id con su motivo y devuelve 1 (sin ellas, 0 como hasta ahora).
"""
from __future__ import annotations

import pytest

import auto_etiquetado_router as A


def _lote():
    return [({"id": f"T920{i}", "titulo": "x", "etiquetas": []}, "resumen", None) for i in (1, 2, 3)]


@pytest.fixture
def tareas(monkeypatch):
    hechas = []

    def actualizar(tid, **kw):
        if tid == "T9202":
            raise OSError("disco lleno")
        hechas.append(tid)

    monkeypatch.setattr(A.T, "actualizar", actualizar)
    monkeypatch.setattr(A.T, "anotar", lambda *a, **k: None)
    return hechas


def test_un_fallo_parcial_no_corta_el_resto(tareas):
    assert A.aplicar(_lote()) == ["T9201", "T9203"]
    assert tareas == ["T9201", "T9203"]


def test_la_discrepancia_se_reporta_con_su_motivo(tareas):
    discrepancias = []
    assert A.aplicar(_lote(), discrepancias) == ["T9201", "T9203"]
    assert [(i, "disco lleno" in m) for i, m in discrepancias] == [("T9202", True)]


def test_sin_fallos_no_hay_discrepancias(monkeypatch):
    monkeypatch.setattr(A.T, "actualizar", lambda *a, **k: None)
    monkeypatch.setattr(A.T, "anotar", lambda *a, **k: None)
    discrepancias = []
    assert A.aplicar(_lote(), discrepancias) == ["T9201", "T9202", "T9203"] and discrepancias == []


def _cli_con(monkeypatch, capsys):
    monkeypatch.setattr(A, "evaluar_candidatas", lambda: {
        "total_vivas_sin_etiqueta": 3, "etiquetables": _lote(), "descartadas_estructura": [],
        "descartadas_clasificacion": [], "extraccion_sin_claves": [], "fallos_clasificacion": []})
    codigo = A._cli(["--aplicar"])
    return codigo, capsys.readouterr().out


def test_cli_con_discrepancias_las_muestra_y_devuelve_1(tareas, monkeypatch, capsys):
    codigo, salida = _cli_con(monkeypatch, capsys)
    assert codigo == 1 and "T9202" in salida and "disco lleno" in salida and "T9201" in salida


def test_cli_sin_discrepancias_devuelve_0(monkeypatch, capsys):
    monkeypatch.setattr(A.T, "actualizar", lambda *a, **k: None)
    monkeypatch.setattr(A.T, "anotar", lambda *a, **k: None)
    codigo, salida = _cli_con(monkeypatch, capsys)
    assert codigo == 0 and "APLICADO: 3" in salida
