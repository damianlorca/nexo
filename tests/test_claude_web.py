# -*- coding: utf-8 -*-
"""Claude web de NEXO (cuenta propia de NEXO, plan Free, en el Chrome de NEXO): revisor EXTRA solo de apelacion.

Igual que ChatGPT/Gemini web: candado exclusivo del Chrome, modo y modelo comprobados en pantalla en fallo
cerrado (Sonnet 5.5 + esfuerzo Alto, leidos del aria-label del selector), lectura por turnos verificados. Ademas:
aviso de limite -> enfria hasta la hora de reinicio que muestra; captcha o verificacion -> para ese proveedor y
avisa a Damian (nunca se intenta resolver). Sin Chrome ni red: DOM con la estructura real de claude.ai (04/10).
"""
from __future__ import annotations

import time
from datetime import datetime

import pytest

import proveedores
from extremidades import navegador as nav
from nucleo import avisos, enfriamiento, tribunal

PROMPT = "Responde solo con la palabra: listo"


def dom_claude(prompt=PROMPT, respuesta="listo", streaming=False, etiqueta="Modelo: Sonnet 5.5 Alto",
               con_respuesta=True):
    ia = ""
    if con_respuesta:
        ia = (f'<div data-testid="transcript-row" data-index="1"><div data-testid="assistant-message" '
              f'data-is-streaming="{"true" if streaming else "false"}">'
              f'<h2 class="sr-only select-none">Claude ha respondido: {respuesta}</h2>'
              f'<div class="font-claude-response"><div class="standard-markdown"><p>{respuesta}</p></div></div>'
              f'<div data-testid="message-actions"><button data-testid="action-bar-copy">Copiar</button></div>'
              f'</div></div>')
    return (f'<nav data-testid="sidebar"><a href="/chat/x">Para que sirve un captcha</a></nav>'
            f'<div data-testid="chat-column"><div data-testid="transcript-row" data-index="0">'
            f'<div data-testid="user-message"><p class="whitespace-pre-wrap">{prompt}</p></div></div>{ia}</div>'
            f'<div contenteditable="true" role="textbox" data-testid="chat-input"></div>'
            f'<button data-testid="model-selector-dropdown" aria-label="{etiqueta}">Sonnet 5.5 Alto</button>'
            f'<button data-testid="chat-input-send" aria-label="Enviar mensaje">Enviar</button>')


# ------------------------------------------------------------------ lectura por turnos
def test_lee_los_turnos_de_claude_sin_la_cabecera_oculta_ni_botones():
    turnos = nav.leer_turnos(dom_claude(), "claude")
    assert [t["rol"] for t in turnos] == ["usuario", "ia"]
    assert turnos[0]["texto"] == PROMPT and turnos[1]["texto"] == "listo"
    assert nav.evaluar_turnos([], turnos, PROMPT) == ("ok", "listo")


def test_generando_mientras_hace_streaming():
    html = dom_claude(streaming=True)
    assert nav.generando(html, "claude") and not nav.generando(dom_claude(), "claude")


def test_otra_pregunta_en_pantalla_nunca_es_ok():
    turnos = nav.leer_turnos(dom_claude(prompt="otra cosa"), "claude")
    assert nav.evaluar_turnos([], turnos, PROMPT)[0] == "ajeno"


def test_pie_de_claude_se_corta():
    assert nav._limpiar_respuesta("listo\nClaude es una IA y puede cometer errores. Verifica las respuestas.") == "listo"


# ------------------------------------------------------------------ modo y modelo en pantalla
@pytest.mark.parametrize("etiqueta, ok", [("Modelo: Sonnet 5.5 Alto", True), ("Modelo: Sonnet 5.5 Medio", False),
                                          ("Modelo: Haiku 4.5 Alto", False), ("", False)])
def test_modo_en_pantalla_exige_modelo_y_esfuerzo(etiqueta, ok):
    r = nav.modo_en_pantalla(dom_claude(etiqueta=etiqueta), "claude")
    assert r["ok"] is ok and (etiqueta in r["detalle"] if etiqueta else "sin selector" in r["detalle"])


class LocClaude:
    def __init__(self, p, sel, has_text=None):
        self.p, self.sel, self.has_text = p, sel, has_text

    first = property(lambda self: self)

    def nth(self, i):
        return self

    def count(self):
        if "model-selector-dropdown" in self.sel:
            return 1 if self.p.hay_selector else 0
        if "chat-input" in self.sel or "contenteditable" in self.sel:
            return 1
        if "menu" in self.sel:
            return 1 if self.p.menu_abierto and self.has_text in self.p.opciones else 0
        return 0

    def get_attribute(self, nombre):
        return f"Modelo: {self.p.modelo} {self.p.esfuerzo}"

    def click(self, **k):
        self.p.clics.append((self.sel, self.has_text))
        if "model-selector-dropdown" in self.sel:
            self.p.menu_abierto = True
        elif self.has_text == "Sonnet 5.5" and self.p.cambia:
            self.p.modelo, self.p.menu_abierto = "Sonnet 5.5", False
        elif self.has_text == "Alto" and self.p.cambia:
            self.p.esfuerzo, self.p.menu_abierto = "Alto", False

    def hover(self, **k):
        self.p.clics.append(("hover", self.has_text))

    def is_visible(self):
        return True

    def fill(self, texto):
        self.p.escrito = texto

    def press(self, tecla):
        self.p.teclas_caja.append(tecla)


class PaginaClaude:
    url = "https://claude.ai/new"

    def __init__(self, modelo="Sonnet 5.5", esfuerzo="Medio", cambia=True, hay_selector=True, cuerpo=""):
        self.modelo, self.esfuerzo, self.cambia, self.hay_selector, self.cuerpo = modelo, esfuerzo, cambia, \
            hay_selector, cuerpo
        self.menu_abierto, self.opciones = False, {"Sonnet 5.5", "Esfuerzo", "Alto"}
        self.clics, self.teclas_caja, self.recargas, self.escrito = [], [], [], None
        self.keyboard = type("K", (), {"press": lambda s, t: setattr(self, "menu_abierto", False)})()

    def locator(self, sel, has_text=None):
        return LocClaude(self, sel, has_text)

    def wait_for_timeout(self, ms):
        pass

    def bring_to_front(self):
        pass

    def goto(self, url, **k):
        self.recargas.append(url)

    def reload(self, **k):
        self.recargas.append("reload")

    def evaluate(self, js):
        return dom_claude(etiqueta=f"Modelo: {self.modelo} {self.esfuerzo}", con_respuesta=False)

    def inner_text(self, sel):
        return self.cuerpo


@pytest.fixture
def chrome_claude(monkeypatch, tmp_path):
    def instalar(pagina):
        import playwright.sync_api as api

        class PW:
            def __enter__(self):
                ctx = type("C", (), {"pages": [pagina]})()
                nav_ = type("N", (), {"contexts": [ctx]})()
                return type("P", (), {"chromium": type("Ch", (), {"connect_over_cdp": lambda s, u: nav_})()})()

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(api, "sync_playwright", lambda: PW())
        monkeypatch.setattr(nav, "activo", lambda: True)
        monkeypatch.setattr(nav, "ruta_candado", lambda: tmp_path / "chrome.lock")
        monkeypatch.setattr(nav, "traza", lambda *a, **k: None)
        monkeypatch.setattr(nav, "_guardar_dom", lambda *a: "")
        monkeypatch.setattr(nav, "estado_ventana", lambda p: "normal")
        monkeypatch.setattr(nav, "ESPERA_CONTROLES", 0)
        monkeypatch.setattr(nav.time, "sleep", lambda s: None)
        return pagina
    return instalar


def test_fija_sonnet_y_esfuerzo_alto_y_lo_lee_en_pantalla(chrome_claude, monkeypatch):
    pagina = chrome_claude(PaginaClaude(modelo="Haiku 4.5", esfuerzo="Medio"))
    monkeypatch.setattr(nav, "_esperar_respuesta", lambda *a: ("listo", "dom", dom_claude()))
    assert nav.preguntar("claude", PROMPT, nueva=True) == "listo"
    ev = nav.ULTIMA_EVIDENCIA["claude"]
    assert ev["resultado"] == "OK" and "Sonnet 5.5 Alto" in ev["modo_antes"] and "Sonnet 5.5 Alto" in ev["modo_tras_enviar"]
    assert pagina.teclas_caja == ["Enter"] and pagina.recargas[0] == nav.URL_NUEVA["claude"]


def test_si_no_se_confirma_el_modo_no_se_envia(chrome_claude):
    pagina = chrome_claude(PaginaClaude(cambia=False))
    with pytest.raises(nav.ModoNoActivo, match="NO se envia"):
        nav.preguntar("claude", PROMPT, nueva=True)
    assert pagina.teclas_caja == [] and pagina.escrito is None


def test_sin_selector_de_modelo_es_fallo_cerrado(chrome_claude):
    pagina = chrome_claude(PaginaClaude(hay_selector=False))
    with pytest.raises(nav.ModoNoActivo, match="selector de modelo"):
        nav.preguntar("claude", PROMPT)
    assert pagina.teclas_caja == []


def test_tras_enviar_con_otro_modelo_en_pantalla_la_respuesta_no_vale(chrome_claude, monkeypatch):
    chrome_claude(PaginaClaude(esfuerzo="Alto"))
    monkeypatch.setattr(nav, "_esperar_respuesta",
                        lambda *a: ("listo", "dom", dom_claude(etiqueta="Modelo: Haiku 4.5 Alto")))
    with pytest.raises(nav.ModoNoActivo, match="tras enviar"):
        nav.preguntar("claude", PROMPT)


# ------------------------------------------------------------------ limite y verificacion
def test_limite_con_hora_de_reinicio():
    ahora = datetime(2026, 10, 4, 13, 0).timestamp()
    hasta = nav.limite_uso("Has alcanzado el límite de mensajes. Se restablecerá a las 18:00.", ahora)
    assert datetime.fromtimestamp(hasta) == datetime(2026, 10, 4, 18, 0)
    hasta = nav.limite_uso("You are out of free messages until 3 PM", ahora)
    assert datetime.fromtimestamp(hasta) == datetime(2026, 10, 4, 15, 0)
    hasta = nav.limite_uso("Has alcanzado tu límite de uso hasta las 9:30", ahora)       # ya paso: manana
    assert datetime.fromtimestamp(hasta) == datetime(2026, 10, 5, 9, 30)


def test_limite_sin_hora_enfria_un_rato_fijo_y_sin_aviso_no_hay_limite():
    ahora = time.time()
    assert nav.limite_uso("Has alcanzado el límite de mensajes", ahora) == pytest.approx(ahora + nav.LIMITE_SIN_HORA)
    assert nav.limite_uso("Hola, noctámbulo\nPlan Free", ahora) is None


def test_aviso_de_limite_antes_de_enviar_para_sin_escribir(chrome_claude):
    pagina = chrome_claude(PaginaClaude(esfuerzo="Alto",
                                        cuerpo="Has alcanzado el límite de mensajes. Se restablecerá a las 18:00."))
    with pytest.raises(nav.LimiteUso) as e:
        nav.preguntar("claude", PROMPT)
    assert e.value.hasta > time.time() and pagina.teclas_caja == []


def test_hablar_de_limites_en_la_conversacion_no_es_un_limite():
    conv = ("Has alcanzado el límite de mensajes a las 18:00 (lo dice el usuario)",)
    assert nav._revisar_limite("Has alcanzado el límite de mensajes a las 18:00 (lo dice el usuario)", conv) is None


def test_verificacion_humana_de_claude_es_bloqueo():
    for texto in ("Verifica que eres humano", "Just a moment...", "Verify your phone number"):
        with pytest.raises(nav.Bloqueo):
            nav._revisar_bloqueo(texto)


# ------------------------------------------------------------------ proveedor
@pytest.fixture
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(enfriamiento, "ALMACEN", tmp_path / "enfriamiento.json")
    monkeypatch.setattr(avisos, "CARPETA", tmp_path / "avisos")
    monkeypatch.setattr(nav, "activo", lambda: True)
    return tmp_path


def test_proveedor_limite_enfria_hasta_la_hora_de_reinicio(aislado, monkeypatch):
    hasta = time.time() + 3 * 3600

    def limite(*a, **k):
        raise nav.LimiteUso("claude: limite de uso", hasta=hasta)
    monkeypatch.setattr(nav, "preguntar", limite)
    p = proveedores.ClaudeWebProvider()
    r = p.enviar("hola")
    assert r.estado == "NOT_AVAILABLE" and "limite" in r.detalle.lower()
    datos = enfriamiento._leer()["claude_web"]
    assert abs(datos["hasta"] - hasta) < 5 and not p.disponible()


def test_proveedor_captcha_para_el_proveedor_y_avisa_a_damian(aislado, monkeypatch):
    def captcha(*a, **k):
        raise nav.Bloqueo("Detectado bloqueo o captcha (verifica que eres humano).")
    monkeypatch.setattr(nav, "preguntar", captcha)
    p = proveedores.ClaudeWebProvider()
    assert p.enviar("hola").estado == "BLOCKED"
    assert not p.disponible() and "bloqueo" in enfriamiento.enfriado("claude_web")
    aviso = avisos.recientes(1)[0]
    assert "Claude web" in aviso["titulo"] and "a mano" in aviso["cuerpo"]


def test_proveedor_modo_no_activo_nunca_es_ok(aislado, monkeypatch):
    def sin_modo(*a, **k):
        raise nav.ModoNoActivo("claude: no se confirma el modo")
    monkeypatch.setattr(nav, "preguntar", sin_modo)
    assert proveedores.ClaudeWebProvider().enviar("hola").estado == "ERROR"


def test_proveedor_ok_y_familia():
    from nucleo import auditor
    assert auditor.familia("claude_web") == "anthropic"
    assert proveedores.ClaudeWebProvider().sitio == "claude"


# ------------------------------------------------------------------ en el tribunal: solo apelacion, al final
def test_claude_web_solo_al_final_de_la_apelacion_con_cupo_3():
    cw = [c for c in tribunal.CANDIDATOS.values() if c.proveedor == "claude_web"]
    assert len(cw) == 1 and cw[0].familia == "anthropic" and cw[0].web
    assert cw[0] not in tribunal.TRIBUNAL and tribunal.APELACION[-1] == cw[0]
    assert tribunal.CUPO_WEB["claude_web"] == 3
