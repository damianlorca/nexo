# -*- coding: utf-8 -*-
"""T688 pieza 2: panel 'Descartadas' del Centro (solo lee descartes.registro)."""
from __future__ import annotations

from nucleo import investigacion
from nucleo import tareas as T


def test_panel_descartadas_muestra_motivo_y_filtra_por_causa(cliente, csrf):
    t = T.anadir("Investigar Blkit", etiquetas=["cat:investigacion"], estado="hecha")
    investigacion.fijar_resultado(t["id"], "DESCARTAR", "no aporta frente a la web propia de NEXO")
    html = cliente.get("/centro/descartadas").text
    assert t["id"] in html and "no aporta frente a la web propia" in html and "resultado (1)" in html
    assert t["id"] not in cliente.get("/centro/descartadas?causa=idea").text
    assert 'hx-get="/centro/descartadas"' in cliente.get("/tecnico").text


def test_panel_descartadas_vacio_y_con_sesion(cliente, csrf):
    assert "No hay descartes" in cliente.get("/centro/descartadas").text


def test_panel_descartadas_requiere_sesion(cliente):
    assert cliente.get("/centro/descartadas").status_code == 401
