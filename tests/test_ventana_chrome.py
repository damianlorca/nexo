# -*- coding: utf-8 -*-
"""T262: la ventana del Chrome de NEXO no vuelve al frente si Damian la ha minimizado. Sin Chrome."""
from __future__ import annotations

import pytest

from extremidades import navegador


class Cdp:
    def __init__(self, estado, falla=False):
        self.estado, self.falla, self.cerrada = estado, falla, False

    def send(self, metodo, params=None):
        if self.falla:
            raise RuntimeError("sin CDP")
        assert metodo == "Browser.getWindowForTarget"
        return {"windowId": 1, "bounds": {"windowState": self.estado}}

    def detach(self):
        self.cerrada = True


class Pagina:
    def __init__(self, estado, falla=False):
        self.cdp, self.al_frente = Cdp(estado, falla), 0
        self.context = self

    def new_cdp_session(self, pagina):
        return self.cdp

    def bring_to_front(self):
        self.al_frente += 1


def test_minimizada_no_se_trae_al_frente():
    p = Pagina("minimized")
    assert navegador.al_frente(p) == "minimized" and p.al_frente == 0 and p.cdp.cerrada


@pytest.mark.parametrize("estado", ["normal", "maximized"])
def test_visible_si_se_trae_al_frente(estado):
    p = Pagina(estado)
    assert navegador.al_frente(p) == estado and p.al_frente == 1


def test_sin_poder_leer_el_estado_se_comporta_como_antes():
    p = Pagina("normal", falla=True)
    assert navegador.al_frente(p) == "desconocido" and p.al_frente == 1


def test_chrome_se_lanza_sin_frenar_la_ventana_minimizada(monkeypatch):
    lanzado = {}
    estados = iter([False, True])
    monkeypatch.setattr(navegador, "activo", lambda: next(estados))
    monkeypatch.setattr(navegador.time, "sleep", lambda s: None)
    monkeypatch.setattr(navegador.shell, "lanzar", lambda comando, **k: lanzado.update(comando=comando) or {})
    navegador.arrancar()
    for flag in ("--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
                 "--disable-background-timer-throttling"):
        assert flag in lanzado["comando"]


def test_no_queda_ningun_bring_to_front_directo():
    fuente = navegador.__file__
    lineas = [l for l in open(fuente, encoding="utf-8") if ".bring_to_front()" in l]
    assert len(lineas) == 1, lineas      # solo el de al_frente()


# Prueba real de T262 (28/09): tras responder, ChatGPT anade el titulo del chat nuevo a "Recientes" entre la
# lectura de la pagina y la de la barra; el bloque entero ya no coincidia y los titulos viejos ("Uso del
# captcha") disparaban un Bloqueo falso.
NAV_ANTES = "Recientes\nResumen del protocolo HTTP\nCaptcha y robots\nUso del captcha"
PAGINA = "ChatGPT\nRecientes\nRespuesta OK ventana\nResumen del protocolo HTTP\nCaptcha y robots\nUso del captcha\nOK VENTANA"


def test_titulos_viejos_de_la_barra_no_son_captcha_aunque_la_lista_cambie():
    navegador._revisar_bloqueo(PAGINA, ("Responde solo con: OK VENTANA", "OK VENTANA", NAV_ANTES))


def test_un_captcha_de_verdad_sigue_parando():
    with pytest.raises(navegador.Bloqueo):
        navegador._revisar_bloqueo("Verify you are human\n" + PAGINA, (NAV_ANTES,))


def test_esperar_da_tiempo_a_que_la_web_pinte_el_control(reloj_falso):
    reloj = reloj_falso(navegador)
    respuestas = iter([None, None, "boton"])
    assert navegador._esperar(lambda: next(respuestas)) == "boton" and len(reloj.esperas) == 2
    assert navegador._esperar(lambda: None, segundos=2) is None      # no espera para siempre


class Pag:
    """Pestana falsa con ventana (id y estado) para _ventana_propia."""
    def __init__(self, ventana, estado, url="https://gemini.google.com/app"):
        self.ventana, self.estado, self.url, self.cerrada = ventana, estado, url, False
        self.context = self

    def new_cdp_session(self, pagina):
        yo = self

        class S:
            def send(self, metodo, params=None):
                return {"windowId": yo.ventana, "bounds": {"windowState": yo.estado}}

            def detach(self):
                pass
        return S()

    def close(self):
        self.cerrada = True


class Nav:
    def __init__(self, *paginas):
        self.contexts = [type("C", (), {"pages": list(paginas)})()]


# Damian 04/10: UNA sola ventana con pestanas (antes, T262, una ventana por web). Prueba real del 04/10: con la ventana
# minimizada y Gemini y ChatGPT en pestanas de FONDO, los dos fijan su modo y responden (flags de arrancar()).
def test_pagina_en_otra_ventana_vuelve_como_pestana_a_la_principal(monkeypatch):
    chatgpt, gemini = Pag(1, "minimized", "https://chatgpt.com/c/x"), Pag(2, "minimized")
    abiertas = []
    monkeypatch.setattr(navegador, "_abrir_pestana",
                        lambda nav, url: abiertas.append(url) or Pag(1, "minimized", url))
    nueva = navegador._en_ventana_principal(Nav(chatgpt, gemini), gemini)
    assert abiertas == ["https://gemini.google.com/app"] and gemini.cerrada and not chatgpt.cerrada
    assert nueva.ventana == 1


@pytest.mark.parametrize("estado", ["minimized", "normal"])
def test_en_la_principal_no_se_mueve(monkeypatch, estado):
    chatgpt, gemini = Pag(1, estado, "https://chatgpt.com/"), Pag(1, estado)
    monkeypatch.setattr(navegador, "_abrir_pestana", lambda *a: pytest.fail("no debe abrir nada"))
    assert navegador._en_ventana_principal(Nav(chatgpt, gemini), gemini) is gemini and not gemini.cerrada
    assert navegador._en_ventana_principal(Nav(gemini), gemini) is gemini


def test_abrir_pestana_de_fondo_en_la_misma_ventana():
    enviados = []

    class Sesion:
        def send(self, metodo, params=None):
            enviados.append((metodo, params))

    class Info:
        value = Pag(1, "minimized", "https://claude.ai/")

    class Ctx:
        pages = []

        def expect_page(self):
            import contextlib
            return contextlib.nullcontext(Info)

    Info.value.wait_for_load_state = lambda *a: None
    nav = type("N", (), {"contexts": [Ctx()], "new_browser_cdp_session": lambda self: Sesion()})()
    assert navegador._abrir_pestana(nav, "https://claude.ai/") is Info.value
    assert enviados == [("Target.createTarget", {"url": "https://claude.ai/", "newWindow": False, "background": True})]


def test_nada_abre_ventanas_nuevas():
    fuente = open(navegador.__file__, encoding="utf-8").read()
    assert '"newWindow": True' not in fuente and "_abrir_en_ventana" not in fuente
