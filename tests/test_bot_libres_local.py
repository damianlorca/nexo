# -*- coding: utf-8 -*-
"""N01 (H11, decision 2 del 26/09): los mensajes sueltos de Telegram solo usan Qwen
local, de uno en uno, y nunca con la PARADA activa. Tests tomados de
documentacion/propuestas/N01_arreglos.patch. Solo dobles: ni Telegram ni Ollama."""
from __future__ import annotations

import pytest

from canal import bot

DAMIAN = 111


def test_con_parada_los_mensajes_sueltos_no_usan_modelos(monkeypatch):
    monkeypatch.setattr(bot, "_parado", lambda: True)
    usados = []
    monkeypatch.setattr(bot, "_texto_triaje", lambda t: usados.append("triaje"))
    monkeypatch.setattr(bot, "_texto_router", lambda t: usados.append("router"))
    bot._avisar_con_qwen(DAMIAN, "hola")
    bot._avisar_con_router(DAMIAN, "hola")
    assert usados == []


def test_el_router_de_mensajes_sueltos_es_solo_local(monkeypatch):
    import router
    pedidos = []
    monkeypatch.setattr(bot, "ROUTER_RESPONDE_LIBRES", True)
    monkeypatch.setattr(router, "procesar", lambda texto, **k: pedidos.append(k) or {"estado": "ESCALADO"})
    assert bot._texto_router("resume esto") is None
    assert pedidos == [{"solo_local": True}]


def test_los_hilos_de_mensajes_sueltos_van_de_uno_en_uno(monkeypatch):
    monkeypatch.setattr(bot, "_parado", lambda: False)
    dentro = []
    monkeypatch.setattr(bot, "_texto_triaje", lambda t: dentro.append(bot._UN_MODELO.locked()))
    bot._avisar_con_qwen(DAMIAN, "hola")
    assert dentro == [True]
