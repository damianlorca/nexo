# -*- coding: utf-8 -*-
"""Noche 05/10 (peticion de Damian): 'Inicializar' los proveedores web. La decision activa/caducada se toma con la
URL y el HTML de la pagina (sin navegador en los tests)."""
from __future__ import annotations

import pytest

from extremidades import sesiones_web as S


@pytest.mark.parametrize("sitio, url, html, esperado", [
    ("chatgpt", "https://chatgpt.com/", '<form data-chatgpt-composer><div contenteditable="true"></div></form>', "activa"),
    ("chatgpt", "https://chatgpt.com/", '<form data-chatgpt-composer></form><button data-testid="login-button">Log in</button>',
     "caducada"),                                             # ChatGPT deja escribir sin sesion: manda el boton
    ("chatgpt", "https://auth.openai.com/log-in", "<html></html>", "caducada"),
    ("gemini", "https://gemini.google.com/app", "<rich-textarea><div contenteditable></div></rich-textarea>", "activa"),
    ("gemini", "https://gemini.google.com/app",
     '<rich-textarea></rich-textarea><a href="https://accounts.google.com/ServiceLogin?x=1">Iniciar sesión</a>', "caducada"),
    ("gemini", "https://accounts.google.com/v3/signin/identifier", "<html></html>", "caducada"),
    ("claude", "https://claude.ai/new", '<div data-testid="chat-input" contenteditable="true"></div>', "activa"),
    ("claude", "https://claude.ai/login", "<html></html>", "caducada"),
    ("claude", "https://claude.ai/new", "<div>cargando</div>", "desconocida"),
])
def test_estado_de_la_sesion(sitio, url, html, esperado):
    assert S.estado_sesion(sitio, url, html) == esperado


def test_sitio_desconocido():
    with pytest.raises(ValueError):
        S.estado_sesion("perplexity", "https://x", "")


class _Pagina:
    def __init__(self, url, html):
        self.url, self._html, self.recargada = url, html, False

    def reload(self, **k):
        self.recargada = True

    def wait_for_timeout(self, ms):
        pass

    def content(self):
        return self._html


def test_inicializar_reutiliza_la_pestana_abierta_y_abre_las_que_faltan(monkeypatch):
    """Una pestana por proveedor en la ventana del Chrome de NEXO: reutiliza la que hay y abre la que falta."""
    import contextlib
    import sys
    import types
    from extremidades import navegador
    abierta = _Pagina("https://chatgpt.com/c/1", '<form data-chatgpt-composer></form>')
    chrome = types.SimpleNamespace(contexts=[types.SimpleNamespace(pages=[abierta])])
    nuevas = []

    def abrir(ch, url):
        p = _Pagina("https://claude.ai/login", "")
        nuevas.append(url)
        return p

    pw = types.SimpleNamespace(chromium=types.SimpleNamespace(connect_over_cdp=lambda url: chrome))

    @contextlib.contextmanager
    def sync_playwright():
        yield pw
    monkeypatch.setitem(sys.modules, "playwright.sync_api", types.SimpleNamespace(sync_playwright=sync_playwright))
    monkeypatch.setattr(navegador, "activo", lambda: True)
    monkeypatch.setattr(navegador, "arrancar", lambda **k: pytest.fail("Chrome ya estaba"))
    monkeypatch.setattr(navegador, "en_exclusiva", lambda motivo, espera=None: contextlib.nullcontext())
    monkeypatch.setattr(navegador, "_abrir_pestana", abrir)
    monkeypatch.setattr(navegador, "_en_ventana_principal", lambda ch, p: p)
    r = S.inicializar(["chatgpt", "claude"], espera_ms=0)
    assert [(x["sitio"], x["estado"]) for x in r] == [("chatgpt", "activa"), ("claude", "caducada")]
    assert abierta.recargada and nuevas == ["https://claude.ai/new"]
