# -*- coding: utf-8 -*-
"""T348: un fallo de qwen.clasificar() en una tarea no tumba el lote de auto_etiquetado_router.

Piloto F3 (T669): estos tests los escribe Claude; el implementador solo cambia auto_etiquetado_router.py.
Contrato: evaluar_candidatas() captura la excepcion (Exception, no BaseException) de cada tarea, la anota en
resultado["fallos_clasificacion"] como lista de (tarea, motivo_texto) y sigue con las demas; _resumen_legible()
nombra esas tareas con su motivo.
"""
from __future__ import annotations

import pytest

import auto_etiquetado_router as A

CONTENIDO = ("Reunion de ayer por la tarde con el equipo comercial para repasar las ventas del trimestre, los clientes "
             "nuevos, las bajas y los pedidos pendientes de entrega en las tres sedes de la empresa.")


def _tarea(i):
    return {"id": f"T90{i}", "titulo": f"Resumir acta {i}", "detalle": CONTENIDO, "estado": "pendiente", "etiquetas": []}


@pytest.fixture
def lote(monkeypatch):
    monkeypatch.setattr(A.T, "listar", lambda **kw: [_tarea(1), _tarea(2), _tarea(3)])
    llamadas = []

    def clasificar(texto, categorias, por_defecto="otro"):
        llamadas.append(texto)
        if len(llamadas) == 2:
            raise RuntimeError("Ollama no responde")
        return "resumen"

    monkeypatch.setattr("extremidades.qwen.clasificar", clasificar)
    return llamadas


def test_un_fallo_no_tumba_el_lote(lote):
    r = A.evaluar_candidatas()
    assert len(lote) == 3                                                    # sigue tras el fallo
    assert [t["id"] for t, _, _ in r["etiquetables"]] == ["T901", "T903"]


def test_el_fallo_queda_registrado_con_su_motivo(lote):
    r = A.evaluar_candidatas()
    assert [(t["id"], "Ollama no responde" in m) for t, m in r["fallos_clasificacion"]] == [("T902", True)]


def test_sin_fallos_la_lista_existe_y_esta_vacia(monkeypatch):
    monkeypatch.setattr(A.T, "listar", lambda **kw: [_tarea(1)])
    monkeypatch.setattr("extremidades.qwen.clasificar", lambda *a, **k: "resumen")
    assert A.evaluar_candidatas()["fallos_clasificacion"] == []


def test_si_fallan_todas_no_revienta(monkeypatch):
    monkeypatch.setattr(A.T, "listar", lambda **kw: [_tarea(1), _tarea(2)])

    def siempre(*a, **k):
        raise ConnectionError("sin red")

    monkeypatch.setattr("extremidades.qwen.clasificar", siempre)
    r = A.evaluar_candidatas()
    assert r["etiquetables"] == [] and len(r["fallos_clasificacion"]) == 2


def test_el_resumen_legible_nombra_las_tareas_fallidas(lote):
    texto = A._resumen_legible(A.evaluar_candidatas())
    assert "T902" in texto and "Ollama no responde" in texto


def test_ctrl_c_no_se_traga(monkeypatch):
    monkeypatch.setattr(A.T, "listar", lambda **kw: [_tarea(1)])

    def interrumpe(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr("extremidades.qwen.clasificar", interrumpe)
    with pytest.raises(KeyboardInterrupt):
        A.evaluar_candidatas()
