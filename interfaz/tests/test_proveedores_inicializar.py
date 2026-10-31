# -*- coding: utf-8 -*-
"""Noche 05/10 (peticion de Damian): botones 'Inicializar' por proveedor web y 'Inicializar todos'; el proveedor
Claude (API) no sale en la vista (sigue en proveedores.py por si algo lo usa por dentro)."""
from __future__ import annotations

from extremidades import sesiones_web
from interfaz import lecturas


def _post(cliente, csrf, **datos):
    return cliente.post("/proveedores/inicializar", data=datos, headers={"X-CSRF-Token": csrf})


def test_pagina_tiene_inicializar_por_proveedor_web_y_todos(cliente, csrf):
    html = cliente.get("/proveedores").text
    assert "Inicializar todos" in html
    for sitio in ("chatgpt", "gemini", "claude"):
        assert f'name="sitio" value="{sitio}"' in html


def test_inicializar_uno_y_todos(cliente, csrf, monkeypatch):
    pedidos = []

    def falso(sitios):
        pedidos.append(list(sitios))
        return [{"sitio": s, "estado": "activa" if s != "claude" else "caducada", "url": f"https://{s}", "detalle": ""}
                for s in sitios]
    monkeypatch.setattr(sesiones_web, "inicializar", falso)
    r = _post(cliente, csrf, sitio="gemini")
    assert r.status_code == 200 and "Gemini (web)" in r.text and "Sesión activa" in r.text
    r = _post(cliente, csrf)
    assert pedidos[-1] == ["chatgpt", "gemini", "claude"]
    assert "Sesión caducada" in r.text and "Chrome de NEXO" in r.text
    assert _post(cliente, csrf, sitio="perplexity").status_code == 400


def test_inicializar_con_chrome_ocupado_lo_dice(cliente, csrf, monkeypatch):
    from extremidades import navegador

    def ocupado(sitios):
        raise navegador.ChromeOcupado("lo usa un turno")
    monkeypatch.setattr(sesiones_web, "inicializar", ocupado)
    assert "lo está usando un turno" in _post(cliente, csrf).text


def test_inicializar_exige_csrf(cliente, csrf):
    assert cliente.post("/proveedores/inicializar", data={}).status_code in (400, 401, 403)


def test_claude_api_no_sale_en_la_vista():
    import ast
    import inspect
    # el conftest de la interfaz cambia la tupla por un doble: se mira la del codigo
    arbol = ast.parse(inspect.getsource(lecturas))
    clases = next(ast.literal_eval(n.value) for n in arbol.body
                  if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "CLASES_PROVEEDORES")
    assert "ClaudeProvider" not in clases and "ClaudeWebProvider" in clases
    import proveedores
    assert hasattr(proveedores, "ClaudeProvider")      # sigue en el codigo: no se borra nada
