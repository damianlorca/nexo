# -*- coding: utf-8 -*-
"""T195: orden de llamada de proveedores editable en Ajustes y respetado por trabajo.py."""
from __future__ import annotations

import pytest

from nucleo import orden_proveedores as O
from nucleo import trabajo


class P:
    def __init__(self, nombre):
        self.nombre = nombre

    def __repr__(self):
        return self.nombre


def test_sin_preferencia_no_cambia_nada():
    ps = [P("chatgpt"), P("nvidia"), P("groq")]
    assert O.aplicar(ps) == ps and O.leer() == [] and O.actual() == list(O.ORDEN_BASE)


def test_guardar_completa_y_filtra():
    assert O.guardar(["groq", "xx", "groq", "nvidia"])[:2] == ["groq", "nvidia"]
    assert sorted(O.leer()) == sorted(O.ORDENABLES)


def test_aplicar_pone_primero_los_elegidos_y_los_demas_detras_en_su_orden():
    O.guardar(["groq", "gemini_api"])
    ps = [P("chatgpt"), P("nvidia"), P("gemini_api"), P("groq"), P("desconocido")]
    assert [p.nombre for p in O.aplicar(ps)][:2] == ["groq", "gemini_api"]


def test_mover_y_restablecer():
    assert O.mover("groq", -1)[O.ORDEN_BASE.index("groq") - 1] == "groq"
    assert O.mover("chatgpt", -5)[0] == "chatgpt"          # no se sale por arriba
    with pytest.raises(ValueError):
        O.mover("nadie", 1)
    O.restablecer()
    assert O.leer() == []


def test_trabajo_respeta_el_orden_en_generadores_y_revisores(monkeypatch):
    import proveedores as PR
    for c in (PR.ChatGPTProvider, PR.NvidiaProvider, PR.GeminiAPIProvider, PR.GeminiProvider, PR.GroqProvider,
              PR.QwenProvider):
        monkeypatch.setattr(c, "disponible", lambda self: True)
    monkeypatch.setattr(trabajo, "_web", lambda: True)
    monkeypatch.setattr(trabajo, "_por_rol_redactar", lambda lista: lista)
    from nucleo import cuota
    monkeypatch.setattr(cuota, "reordenar", lambda lista: lista)
    assert [p.nombre for p in trabajo._generadores("general")][0] == "chatgpt"
    O.guardar(["groq", "qwen"])
    assert [p.nombre for p in trabajo._generadores("general")][:2] == ["groq", "qwen"]
    assert [p.nombre for p in trabajo._revisores("chatgpt")][0] == "groq"
