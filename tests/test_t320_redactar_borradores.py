# -*- coding: utf-8 -*-
"""T320 (11/10): el rol 'redactar' de memoria/modelos/roles.json, si esta APLICADO, ordena los modelos de Groq y
NVIDIA con los que trabajo.py redacta los borradores. El orden de PROVEEDORES (decision de Damian del 04/10, se revisa
el 18/10) no cambia. Sin rol aplicado, nada cambia."""
from __future__ import annotations

import pytest

from nucleo import banco_modelos as B
from nucleo import trabajo


@pytest.fixture(autouse=True)
def roles_aislados(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "CARPETA", tmp_path)
    monkeypatch.setattr(B, "ROLES", tmp_path / "roles.json")


class _Prov:
    def __init__(self, nombre, modelos=("x",)):
        self.nombre, self.modelos = nombre, tuple(modelos)


def _lista():
    return [_Prov("chatgpt", ("web",)), _Prov("nvidia", ("openai/gpt-oss-120b", "openai/gpt-oss-20b")),
            _Prov("gemini_api", ("gemini-3.5-flash",)),
            _Prov("groq", ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b")), _Prov("qwen")]


def test_rol_redactar_aplicado_pone_delante_su_modelo_dentro_de_groq_y_nvidia():
    B.guardar_roles({"redactar": {"mejor": "groq:openai/gpt-oss-20b", "reserva": "nvidia:openai/gpt-oss-20b",
                                  "aplicado": True}})
    lista = trabajo._por_rol_redactar(_lista())
    assert [p.nombre for p in lista] == ["chatgpt", "nvidia", "gemini_api", "groq", "qwen"]   # proveedores igual
    assert lista[3].modelos == ("openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b")
    assert lista[1].modelos == ("openai/gpt-oss-20b", "openai/gpt-oss-120b")


def test_rol_redactar_sin_aplicar_no_cambia_nada():
    B.guardar_roles({"redactar": {"mejor": "groq:openai/gpt-oss-20b", "aplicado": False}})
    lista = trabajo._por_rol_redactar(_lista())
    assert [p.nombre for p in lista] == ["chatgpt", "nvidia", "gemini_api", "groq", "qwen"]
    assert lista[3].modelos[0] == "openai/gpt-oss-120b"


def test_sin_roles_json_no_cambia_nada():
    assert [p.nombre for p in trabajo._por_rol_redactar(_lista())][0] == "chatgpt"


def test_generadores_reales_usan_el_rol(monkeypatch):
    """_generadores con los proveedores de verdad (sin red: disponible() y cuota se fuerzan)."""
    import proveedores
    from nucleo import cuota
    B.guardar_roles({"redactar": {"mejor": "groq:openai/gpt-oss-20b", "reserva": "nvidia:openai/gpt-oss-20b",
                                  "aplicado": True}})
    monkeypatch.setattr(trabajo, "_web", lambda: False)
    monkeypatch.setattr(cuota, "reordenar", lambda lista: lista)
    for cls in (proveedores.NvidiaProvider, proveedores.GeminiAPIProvider, proveedores.GroqProvider,
                proveedores.QwenProvider):
        monkeypatch.setattr(cls, "disponible", lambda self: True)
    lista = trabajo._generadores("otra")
    assert [p.nombre for p in lista][:3] == ["nvidia", "gemini_api", "groq"]      # sin web: orden de Damian
    groq = next(p for p in lista if p.nombre == "groq")
    assert groq.modelos[0] == "openai/gpt-oss-20b"
