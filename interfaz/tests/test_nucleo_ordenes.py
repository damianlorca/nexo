# -*- coding: utf-8 -*-
"""nucleo.ordenes.procesar con trabajar=False (arreglo aprobado por Damian el 25/09).

Antes, una orden delegable (resumen/redaccion/investigacion) con trabajar=False respondia
ESCALADO "necesita a Claude" aunque no se le ponia escalado:claude. Ahora responde ENCOLADA.
El clasificador (Qwen) se sustituye: aqui solo se prueba el reparto por categoria.
"""
from __future__ import annotations

import pytest

from nucleo import clasificador, ordenes, tareas


@pytest.mark.parametrize("cat", ordenes.DELEGABLE)
def test_delegable_sin_trabajar_queda_encolada_y_no_para_claude(monkeypatch, cat):
    monkeypatch.setattr(clasificador, "clasificar", lambda t: cat)
    r = ordenes.procesar("haz esto para luego", canal="web", trabajar=False)
    assert r["estado"] == "ENCOLADA" and "la trabajo en un turno" in r["respuesta"]
    assert "Claude" not in r["respuesta"]
    t = tareas.buscar(r["tarea"])
    assert "escalado:claude" not in t["etiquetas"] and f"cat:{cat}" in t["etiquetas"]


def test_codigo_sin_trabajar_sigue_escalado_a_claude(monkeypatch):
    monkeypatch.setattr(clasificador, "clasificar", lambda t: "codigo")
    r = ordenes.procesar("arregla el bug del bot", canal="web", trabajar=False)
    assert r["estado"] == "ESCALADO"
    assert "escalado:claude" in tareas.buscar(r["tarea"])["etiquetas"]


def test_personal_sin_trabajar_sigue_para_damian(monkeypatch):
    monkeypatch.setattr(clasificador, "clasificar", lambda t: "personal")
    assert ordenes.procesar("llama al dentista", canal="web", trabajar=False)["estado"] == "PARA_DAMIAN"
