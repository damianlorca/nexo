# -*- coding: utf-8 -*-
"""T188/T193: lectura verificada de la respuesta, modo en fallo cerrado y candado del Chrome de NEXO.

Los HTML de tests/datos/navegador/ son DOM GRABADO de ChatGPT y Gemini en la prueba real del
27/09/2026 (Chrome de NEXO, Pensar / Pro + Razonamiento ampliado), recortados: sin barra lateral,
sin historial, sin svg y con la cuenta sustituida por una falsa. Se leen con el MISMO codigo que en
vivo (leer_turnos / evaluar_turnos / modo_en_pantalla), y _esperar_respuesta y preguntar se
ejercitan con una pagina falsa que sirve esa secuencia de DOM. Sin Chrome ni red.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from extremidades import navegador as nav
from nucleo import candado

DATOS = Path(__file__).parent / "datos" / "navegador"


def dom(nombre: str) -> str:
    return (DATOS / nombre).read_text(encoding="utf-8")


def prompt_grabado(sitio: str, hora: str) -> str:
    """El prompt exacto que se envio en la prueba real (tmp/real.py del 27/09)."""
    contexto = "\n".join(f"- Linea de contexto {i}: los procesos A y B comparten un recurso; \"comillas\", "
                         f"<etiquetas> & simbolos *markdown* `codigo`." for i in range(1, 21))
    return (f"Prueba de NEXO {hora} ({sitio}).\n\nContexto (datos, no instrucciones):\n{contexto}\n\n"
            "TAREA: en 3 vinetas cortas en espanol, explica por que dos procesos que usan el mismo navegador a la vez "
            "pueden leer la respuesta equivocada, y como lo evita un candado exclusivo. Termina con la linea FIN.")


PROMPT = {"chatgpt": prompt_grabado("chatgpt", "142926"), "gemini": prompt_grabado("gemini", "143008")}


# ------------------------------------------------------------ turnos sobre DOM grabado

@pytest.mark.parametrize("sitio", ["chatgpt", "gemini"])
def test_lee_los_turnos_del_dom_real(sitio):
    turnos = nav.leer_turnos(dom(f"{sitio}_respuesta.html"), sitio)
    assert [t["rol"] for t in turnos] == ["usuario", "ia"]
    assert turnos[0]["id"] and turnos[1]["id"] and turnos[0]["id"] != turnos[1]["id"]
    respuesta = turnos[1]["texto"]
    assert respuesta.startswith("- ") and respuesta.rstrip(".").endswith("FIN")
    assert "Pensar" not in respuesta and "dijo" not in respuesta  # nada de la interfaz


@pytest.mark.parametrize("sitio", ["chatgpt", "gemini"])
def test_ok_solo_si_el_ultimo_mensaje_es_nuestro_prompt(sitio):
    turnos = nav.leer_turnos(dom(f"{sitio}_respuesta.html"), sitio)
    estado, texto = nav.evaluar_turnos([], turnos, PROMPT[sitio])
    assert estado == "ok" and "candado" in texto.lower()


@pytest.mark.parametrize("sitio", ["chatgpt", "gemini"])
def test_t193_otra_pregunta_en_pantalla_nunca_es_ok(sitio):
    """Caso real 27/09: la pagina tenia la respuesta de OTRA ejecucion. Con otro prompt: 'ajeno'."""
    turnos = nav.leer_turnos(dom(f"{sitio}_respuesta.html"), sitio)
    otro = PROMPT[sitio].replace("3 vinetas", "4 vinetas")
    estado, motivo = nav.evaluar_turnos([], turnos, otro)
    assert estado == "ajeno" and "no es nuestro prompt" in motivo


@pytest.mark.parametrize("sitio", ["chatgpt", "gemini"])
def test_t193_misma_pregunta_ya_publicada_antes_no_cuenta(sitio):
    """El prompt no llego a publicarse y en pantalla sigue la MISMA pregunta de antes: 'viejo'."""
    turnos = nav.leer_turnos(dom(f"{sitio}_respuesta.html"), sitio)
    assert nav.evaluar_turnos(turnos, turnos, PROMPT[sitio])[0] == "viejo"


def test_respuesta_vieja_tras_un_prompt_nuevo_no_cuenta():
    turnos = nav.leer_turnos(dom("chatgpt_respuesta.html"), "chatgpt")
    antes = [dict(turnos[1])]  # la respuesta ya estaba (mismo id), el mensaje del usuario no
    assert nav.evaluar_turnos(antes, turnos, PROMPT["chatgpt"])[0] == "viejo"


def test_gemini_pensando_espera_y_no_da_texto():
    turnos = nav.leer_turnos(dom("gemini_pensando.html"), "gemini")
    assert nav.evaluar_turnos([], turnos, PROMPT["gemini"]) == ("esperando", "")
    assert nav.generando(dom("gemini_pensando.html"), "gemini")


@pytest.mark.parametrize("sitio,nombre,esperado", [
    ("chatgpt", "chatgpt_enviado.html", False), ("chatgpt", "chatgpt_generando.html", True),
    ("chatgpt", "chatgpt_respuesta.html", False), ("gemini", "gemini_generando.html", True),
    ("gemini", "gemini_respuesta.html", False)])
def test_generando_en_dom_grabado(sitio, nombre, esperado):
    assert nav.generando(dom(nombre), sitio) is esperado


def test_gemini_no_mete_la_etiqueta_oculta_has_dicho():
    usuario = nav.leer_turnos(dom("gemini_respuesta.html"), "gemini")[0]["texto"]
    assert usuario.startswith("Prueba de NEXO") and "Has dicho" not in usuario


def test_comparacion_exacta_ignora_formato_markdown_pero_no_palabras():
    assert nav._exacto("usa `codigo` y **negrita**\n\n- punto") == nav._exacto("usa codigo y negrita punto")
    assert nav._exacto("ver [la guia](https://x.test/a)") == nav._exacto("ver la guia")
    assert nav._exacto("responde en 3 vinetas") != nav._exacto("responde en 4 vinetas")
    assert nav._exacto("hola") != nav._exacto("hola, que tal")


# T682 (11/10): pildoras de enlace de ChatGPT en el mensaje del usuario (DOM real del 05-06/10, recortado: sin svg).
def _burbuja_con_pildoras(*trozos: str) -> str:
    def pildora(href: str, etiqueta: str) -> str:
        return (f'<a data-inline-mention-interactive="" class="ExternalMarkdownLink-WWBYg9" href="{href}" '
                'inert="" aria-hidden="true"><span class="Mention-hIgCkC" data-appearance="inline-mention">'
                '<span data-markdown-copy="exclude" class="IconContainer-K62H88"></span>'
                f'<span class="Label-arpLwJ"><span>{etiqueta}</span></span></span></a>')
    cuerpo = "".join(pildora(*t) if isinstance(t, tuple) else f"<span>{t}</span>" for t in trozos)
    return (f'<main><div data-message-author-role="user" data-message-id="u1"><div data-user-message-bubble="">'
            f'<div class="whitespace-pre-wrap">{cuerpo}</div></div></div>'
            '<div data-message-author-role="assistant" data-message-id="a1"><div class="markdown"><p>Hecho</p>'
            '</div></div></main>')


def test_t682_las_pildoras_de_enlace_del_usuario_cuentan_como_nuestro_prompt():
    prompt = ('OMISIONES: No se indica la URL oficial del repositorio (https://github.com/openjarvis/OpenJarvis).\n'
              '- "Remotion no es open-source." [FALSO: La licencia es MIT: https://github.com/remotion-dev/remotion]\n'
              'URL oficial: “https://github.com/anthropics/skills”, sin verificar.')
    html = _burbuja_con_pildoras(
        "OMISIONES: No se indica la URL oficial del repositorio (",
        ("https://github.com/open-jarvis/OpenJarvis", "https://github.com/open-jarvis/OpenJarvis"), ").",
        '- "Remotion no es open-source." ',
        ("https://github.com/remotion-dev/remotion", "FALSO: La licencia es MIT: [https://github.com/remotion-dev/remotion"),
        "]", "URL oficial: “", ("https://github.com/anthropics/skills”", "https://github.com/anthropics/skills”,"),
        " sin verificar.")
    turnos = nav.leer_turnos(html, "chatgpt")
    assert "FALSO: La licencia es MIT" in turnos[0]["texto"]          # la pildora se lee (antes se perdia entera)
    assert nav.evaluar_turnos([], turnos, prompt) == ("ok", "Hecho")
    # sigue sin valer otro prompt: cambia una palabra
    assert nav.evaluar_turnos([], turnos, prompt.replace("MIT", "GPL"))[0] == "ajeno"


def test_t682_comparacion_sin_urls_ni_puntuacion_pegada():
    assert nav._exacto("ver (https://x.test/a). y [https://y.test/b”]") == nav._exacto("ver () y")
    assert nav._exacto("clef (https://ollama.com/x, sin fecha)") == nav._exacto("clef (, sin fecha)")
    assert nav._exacto("usa la url https://x.test/a") != nav._exacto("usa otra url https://x.test/a")


def test_t682_las_pildoras_no_entran_en_la_respuesta_de_la_ia():
    html = ('<main><div data-message-author-role="assistant" data-message-id="a1"><div class="markdown"><p>Mira '
            '<a data-inline-mention-interactive="" href="https://x.test" aria-hidden="true"><span>x.test</span></a>'
            ' ya</p></div></div></main>')
    assert "x.test" not in nav.leer_turnos(html, "chatgpt")[0]["texto"]           # igual que antes del arreglo


def test_selectores_viejos_de_chatgpt_siguen_valiendo():
    html = ('<main><div data-message-author-role="user" data-message-id="u1"><div>hola</div></div>'
            '<div data-message-author-role="assistant" data-message-id="a1"><div class="markdown"><p>Buenas</p>'
            '</div></div></main>')
    assert nav.evaluar_turnos([], nav.leer_turnos(html, "chatgpt"), "hola") == ("ok", "Buenas")


def test_texto_de_listas_y_codigo():
    html = ('<div data-chatgpt-search-unit-key="t:1:assistant" data-chatgpt-search-message-ids="a">'
            '<div data-markdown-text-style="assistant-message"><ol><li><p>uno</p></li><li><p>dos</p></li></ol>'
            '<pre><code>def f():\n    return 1</code></pre><p>a &amp; b</p></div></div>')
    texto = nav.leer_turnos(html, "chatgpt")[0]["texto"]
    assert "1. uno" in texto and "2. dos" in texto
    assert "def f():\n    return 1" in texto and "a & b" in texto


# ------------------------------------------------------------ modo en pantalla

def test_modo_chatgpt_pensar_apagado_y_activo():
    assert nav.modo_en_pantalla(dom("chatgpt_inicio_pensar_apagado.html"), "chatgpt")["ok"] is False
    tras = nav.modo_en_pantalla(dom("chatgpt_respuesta.html"), "chatgpt")
    assert tras["ok"] is True and tras["pensar"] is True


def test_modo_chatgpt_sin_boton_no_es_ok():
    assert nav.modo_en_pantalla("<main><form data-chatgpt-composer></form></main>", "chatgpt")["ok"] is False


def test_modo_gemini_pro_y_razonamiento():
    m = nav.modo_en_pantalla(dom("gemini_respuesta.html"), "gemini")
    assert m["ok"] and m["pro"] and m["razono"] and "Pro" in m["etiqueta"]
    rapido = dom("gemini_respuesta.html").replace("actualmente Pro Avanzado", "actualmente Rapido")
    assert nav.modo_en_pantalla(rapido, "gemini")["ok"] is False


# ------------------------------------------------------------ espera de la respuesta con una pagina falsa

class PaginaFalsa:
    """Sirve una secuencia de DOM grabado: cada lectura avanza uno (el ultimo se repite)."""

    def __init__(self, reloj, htmls, cuerpo=None):
        self.reloj, self.htmls, self.i = reloj, list(htmls), -1
        self.cuerpo = cuerpo or (lambda: "")

    def wait_for_timeout(self, ms):
        self.reloj.sleep(ms / 1000)

    def evaluate(self, js):
        self.i = min(self.i + 1, len(self.htmls) - 1)
        return self.htmls[self.i]

    def inner_text(self, sel):
        return self.cuerpo()


@pytest.mark.parametrize("sitio,secuencia", [
    ("chatgpt", ["chatgpt_enviado.html", "chatgpt_generando.html"] + ["chatgpt_respuesta.html"] * 4),
    ("gemini", ["gemini_enviado.html", "gemini_pensando.html", "gemini_generando.html"]
     + ["gemini_respuesta.html"] * 4)])
def test_espera_la_respuesta_completa_y_verificada(reloj_falso, sitio, secuencia):
    reloj = reloj_falso(nav)
    pagina = PaginaFalsa(reloj, [dom(x) for x in secuencia])
    texto, metodo, _ = nav._esperar_respuesta(pagina, sitio, PROMPT[sitio], 420, [], "")
    assert metodo == "dom" and texto.rstrip(".").endswith("FIN")
    assert pagina.i >= secuencia.index(f"{sitio}_respuesta.html") + 2  # espero a que dejara de cambiar


def test_t193_con_la_respuesta_de_otra_ejecucion_en_pantalla_falla_y_no_usa_respaldo(reloj_falso):
    """Lo del 27/09: nuestra pregunta nunca se publico y la pagina tiene una respuesta completa de otro
    proceso. Antes el respaldo devolvia OK con ese texto; ahora FALLA en ARRANQUE_DOM."""
    reloj = reloj_falso(nav)
    llamadas_cuerpo = []
    pagina = PaginaFalsa(reloj, [dom("chatgpt_respuesta.html")],
                         cuerpo=lambda: llamadas_cuerpo.append(1) or "texto viejo de la pagina")
    otro = PROMPT["chatgpt"].replace("Prueba de NEXO", "Revision de groq")
    with pytest.raises(nav.RespuestaNoVerificada, match="no aparece como ultimo mensaje"):
        nav._esperar_respuesta(pagina, "chatgpt", otro, 420, [], "")
    assert not llamadas_cuerpo  # el respaldo (texto de pagina) ni se miro
    assert sum(reloj.esperas) < nav.ARRANQUE_DOM + 5


def test_si_otro_proceso_escribe_despues_de_nuestra_pregunta_falla(reloj_falso):
    reloj = reloj_falso(nav)
    otro_dom = dom("chatgpt_respuesta.html").replace("Prueba de NEXO 142926", "Pregunta de otro proceso")
    pagina = PaginaFalsa(reloj, [dom("chatgpt_generando.html"), otro_dom])
    with pytest.raises(nav.RespuestaNoVerificada, match="ya no es la ultima"):
        nav._esperar_respuesta(pagina, "chatgpt", PROMPT["chatgpt"], 420, [], "")


def test_respuesta_a_medias_al_agotar_la_espera_no_vale(reloj_falso):
    reloj = reloj_falso(nav)
    pagina = PaginaFalsa(reloj, [dom("chatgpt_generando.html")])
    with pytest.raises(nav.RespuestaNoVerificada, match="a medias"):
        nav._esperar_respuesta(pagina, "chatgpt", PROMPT["chatgpt"], 60, [], "")


def test_respaldo_solo_con_el_turno_de_usuario_verificado(reloj_falso, monkeypatch):
    """Si la web cambia el turno de la IA pero el del usuario se sigue verificando, el respaldo
    (texto de la pagina) puede dar la respuesta; nunca antes de RESPALDO_TRAS."""
    reloj = reloj_falso(nav)
    cfg = dict(nav.TURNOS["chatgpt"], ia="[data-no-existe]")
    monkeypatch.setitem(nav.TURNOS, "chatgpt", cfg)
    antes = "Menu\nNuevo chat"
    cuerpo = f"{antes}\n{PROMPT['chatgpt']}\nChatGPT dijo:\nRespuesta nueva.\nFIN"
    pagina = PaginaFalsa(reloj, [dom("chatgpt_respuesta.html")], cuerpo=lambda: cuerpo)
    texto, metodo, _ = nav._esperar_respuesta(pagina, "chatgpt", PROMPT["chatgpt"], 420, [], antes)
    assert metodo.startswith("respaldo") and texto == "Respuesta nueva.\nFIN"
    assert sum(reloj.esperas) > nav.RESPALDO_TRAS


# ------------------------------------------------------------ preguntar(): fallo cerrado del modo

class Loc:
    def __init__(self, pagina, sel, has_text=None):
        self.p, self.sel, self.has_text = pagina, sel, has_text

    @property
    def first(self):
        return self

    def nth(self, i):
        return self

    def count(self):
        if "Pensar" == self.has_text:
            return 1 if self.p.hay_pensar else 0
        if "contenteditable" in self.sel:
            return 1
        return 0

    def get_attribute(self, nombre):
        return "true" if self.p.pensar else "false"

    def click(self, **k):
        self.p.clics.append(self.sel)
        if self.has_text == "Pensar" and self.p.pensar_se_activa:
            self.p.pensar = True

    def is_visible(self):
        return True

    def fill(self, texto):
        self.p.escrito = texto

    def press(self, tecla):
        self.p.teclas_caja.append(tecla)


class PaginaModo:
    url = "https://chatgpt.com/"

    def __init__(self, pensar_se_activa=False, hay_pensar=True):
        self.pensar, self.pensar_se_activa, self.hay_pensar = False, pensar_se_activa, hay_pensar
        self.clics, self.teclas_caja, self.recargas, self.escrito = [], [], [], None
        self.keyboard = type("K", (), {"press": lambda s, t: None})()

    def locator(self, sel, has_text=None):
        return Loc(self, sel, has_text)

    def wait_for_timeout(self, ms):
        pass

    def bring_to_front(self):
        pass

    def goto(self, url, **k):
        self.recargas.append(url)

    def reload(self, **k):
        self.recargas.append("reload")

    def evaluate(self, js):
        return dom("chatgpt_inicio_pensar_apagado.html")

    def inner_text(self, sel):
        return ""


@pytest.fixture
def chrome_falso(monkeypatch, tmp_path):
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
        return pagina
    return instalar


def test_t188_sin_pensar_no_se_envia_y_se_reintenta_con_la_pagina_recargada(chrome_falso):
    pagina = chrome_falso(PaginaModo(pensar_se_activa=False))
    with pytest.raises(nav.ModoNoActivo, match="NO se envia"):
        nav.preguntar("chatgpt", "hola", nueva=True)
    assert pagina.teclas_caja == [] and pagina.escrito is None  # ni se escribio ni se pulso Enter
    assert pagina.recargas.count(nav.URL_NUEVA["chatgpt"]) == 2  # nueva conversacion + reintento
    assert nav.ULTIMA_EVIDENCIA["chatgpt"]["resultado"] == "FALLO"


def test_t188_boton_pensar_desaparecido_tambien_es_fallo_cerrado(chrome_falso, monkeypatch):
    monkeypatch.setattr(nav, "ESPERA_CONTROLES", 0)      # T262: sin esperar a que la web lo pinte
    pagina = chrome_falso(PaginaModo(hay_pensar=False))
    with pytest.raises(nav.ModoNoActivo, match="no encuentro el boton Pensar"):
        nav.preguntar("chatgpt", "hola")
    assert pagina.teclas_caja == []


def test_t188_tras_enviar_sin_pensar_en_pantalla_la_respuesta_no_vale(chrome_falso, monkeypatch):
    pagina = chrome_falso(PaginaModo(pensar_se_activa=True))
    monkeypatch.setattr(nav, "_esperar_respuesta",
                        lambda *a: ("Paris", "dom", dom("chatgpt_inicio_pensar_apagado.html")))
    with pytest.raises(nav.ModoNoActivo, match="tras enviar"):
        nav.preguntar("chatgpt", "hola")
    assert pagina.teclas_caja == ["Enter"]


def test_con_pensar_confirmado_devuelve_la_respuesta_y_la_evidencia(chrome_falso, monkeypatch):
    chrome_falso(PaginaModo(pensar_se_activa=True))
    monkeypatch.setattr(nav, "_esperar_respuesta", lambda *a: ("Paris", "dom", dom("chatgpt_respuesta.html")))
    monkeypatch.setattr(nav.time, "sleep", lambda s: None)
    assert nav.preguntar("chatgpt", "hola") == "Paris"
    ev = nav.ULTIMA_EVIDENCIA["chatgpt"]
    assert ev["resultado"] == "OK" and "ACTIVO" in ev["modo_antes"] and "ACTIVO" in ev["modo_tras_enviar"]


def test_proveedor_convierte_los_fallos_del_navegador_en_error_nunca_ok(monkeypatch):
    import proveedores

    monkeypatch.setattr(nav, "activo", lambda: True)

    def falla(*a, **k):
        nav.ULTIMA_EVIDENCIA["chatgpt"] = {"sitio": "chatgpt", "modo_pedido": "ampliado", "resultado": "FALLO"}
        raise nav.RespuestaNoVerificada("no es nuestro prompt")

    monkeypatch.setattr(nav, "preguntar", falla)
    r = proveedores.ChatGPTProvider().enviar("hola")
    assert r.estado == "ERROR" and "RespuestaNoVerificada" in r.detalle and r.meta["resultado"] == "FALLO"


# ------------------------------------------------------------ candado exclusivo

def test_candado_exclusivo_el_segundo_espera_y_luego_entra(tmp_path):
    ruta = tmp_path / "chrome.lock"
    dentro, orden = threading.Event(), []

    def primero():
        with candado.exclusivo(ruta, motivo="primero"):
            dentro.set()
            time.sleep(0.8)
            orden.append("primero sale")

    h = threading.Thread(target=primero)
    h.start()
    dentro.wait(5)
    with candado.exclusivo(ruta, espera_maxima=10, motivo="segundo"):
        orden.append("segundo entra")
    h.join()
    assert orden == ["primero sale", "segundo entra"]


def test_candado_exclusivo_falla_con_mensaje_claro_si_no_se_suelta(tmp_path):
    ruta = tmp_path / "chrome.lock"
    with candado.exclusivo(ruta, motivo="preguntar a chatgpt"):
        with pytest.raises(candado.Ocupado, match="preguntar a chatgpt"):
            with candado.exclusivo(ruta, espera_maxima=0.3):
                pass


def test_candado_de_otro_proceso_y_se_libera_si_ese_proceso_muere(tmp_path):
    """Otro proceso toma el candado y termina SIN soltarlo (os._exit): el sistema lo libera solo."""
    ruta = tmp_path / "chrome.lock"
    listo = tmp_path / "listo"
    codigo = textwrap.dedent(f"""
        import os, sys, time
        sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})
        from nucleo import candado
        cm = candado.exclusivo({str(ruta)!r}, motivo="otro proceso")
        cm.__enter__()
        open({str(listo)!r}, "w").close()
        time.sleep(1.5)
        os._exit(0)
    """)
    hijo = subprocess.Popen([sys.executable, "-c", codigo])
    try:
        for _ in range(100):
            if listo.exists():
                break
            time.sleep(0.05)
        with pytest.raises(candado.Ocupado, match="otro proceso"):
            with candado.exclusivo(ruta, espera_maxima=0.3):
                pass
        with candado.exclusivo(ruta, espera_maxima=15):
            pass
    finally:
        hijo.wait(timeout=20)


def test_en_exclusiva_traduce_a_chrome_ocupado(tmp_path, monkeypatch):
    monkeypatch.setattr(nav, "ruta_candado", lambda: tmp_path / "chrome.lock")
    with nav.en_exclusiva("primero"):
        with pytest.raises(nav.ChromeOcupado, match="otro proceso"):
            with nav.en_exclusiva("segundo", espera=0.2):
                pass


# ------------------------------------------------------------ T189: lectura limpia
# Pildora de cita de ChatGPT tal como la pinta la web (estructura de data-testid y spans).
PILDORA = ('<span data-state="closed"><span data-testid="webpage-citation-pill" class="ms-1 inline-flex">'
           '<a href="https://github.com/garrytan/gstack?utm_source=chatgpt.com" target="_blank"><span class="flex">'
           '<span class="truncate">GitHub</span><span class="px-1">+1</span></span></a></span></span>')
HTML_CITAS = ('<main><div data-message-author-role="user" data-message-id="u1"><div data-user-message-bubble>'
              'hola</div></div><div data-message-author-role="assistant" data-message-id="a1"><div class="markdown">'
              f'<p>gstack es un repositorio de Garry Tan. {PILDORA}</p><p>Requiere Bun. {PILDORA}</p>'
              '</div></div></main>')


def test_las_pildoras_de_cita_no_entran_en_el_texto_y_sus_enlaces_quedan_como_fuentes():
    texto = nav.leer_turnos(HTML_CITAS, "chatgpt")[-1]["texto"]
    assert "GitHub" not in texto.split(nav.CABECERA_FUENTES)[0] and "+1" not in texto
    assert "gstack es un repositorio de Garry Tan." in texto and "Requiere Bun." in texto
    assert texto.endswith(nav.CABECERA_FUENTES + "\n- https://github.com/garrytan/gstack")   # sin repetir


def test_limpiar_respuesta_quita_la_basura_leida_del_body():
    # Caso real del borrador T177 (27/09), leido del body por el metodo antiguo / el respaldo.
    sucio = ("Mostrar más\nChatGPT dijo:\n1) Qué es\ngstack es de Garry Tan. \nGitHub\n+1\n"
             "Requiere Bun y Node.js.\nGitHub\nÚltima respuesta")
    limpio = nav._limpiar_respuesta(sucio)
    assert limpio.splitlines() == ["1) Qué es", "gstack es de Garry Tan. ", "Requiere Bun y Node.js.", "GitHub"]


def test_limpiar_respuesta_no_toca_frases_normales():
    texto = "Resultado:\n+1 para la opcion A.\nC++ 17 es necesario."
    assert nav._limpiar_respuesta(texto) == texto


# T229: anuncios de ChatGPT web colados al final de la respuesta (borrador T166_20260927_0346.md).
ANUNCIO_T166 = ("Se añadieron referencias reales de frameworks y licencias.\n\n"
                "Reconciliar URLs y marcadores de verificación\n\n"
                "Webalize sp. z o.o.\n\nNext.js Development\n\nCustom Next.js apps, built to scale.\n\n"
                "Anuncio\nOpciones del anuncio")
ANUNCIO_T166_B = ("[SIN VERIFICAR] Qué APIs de Windows estarán disponibles.\n\n"
                  "Coursera\n\nBuild With AI\n\nCreate workplace solutions with AI\n\n"
                  "Anuncio\nOpciones del anuncio\n\nSigue el texto real.")


def test_limpiar_respuesta_corta_el_anuncio_de_chatgpt():
    limpio = nav._limpiar_respuesta(ANUNCIO_T166)
    assert limpio.endswith("Reconciliar URLs y marcadores de verificación")
    assert "Webalize" not in limpio and "Anuncio" not in limpio and "built to scale" not in limpio


def test_limpiar_respuesta_corta_el_anuncio_en_medio_y_conserva_lo_de_despues():
    limpio = nav._limpiar_respuesta(ANUNCIO_T166_B)
    assert "Coursera" not in limpio and "Build With AI" not in limpio and "anuncio" not in limpio.lower()
    assert "[SIN VERIFICAR] Qué APIs de Windows estarán disponibles." in limpio
    assert limpio.endswith("Sigue el texto real.")


def test_limpiar_respuesta_no_toca_la_palabra_anuncio_dentro_de_una_frase():
    texto = "El Anuncio del BOE sale el lunes.\nOtra linea."
    assert nav._limpiar_respuesta(texto) == texto


def test_auditor_marca_el_anuncio_como_basura_de_interfaz():
    from nucleo import auditor
    assert auditor.basura_interfaz(ANUNCIO_T166)
    assert auditor.basura_interfaz("x\nSponsored\ny")
    assert not auditor.basura_interfaz("El Anuncio del BOE sale el lunes.")


# ------------------------------------------------------------ T265: cabeceras h1-h6 (DOM real del 28/09)

@pytest.mark.parametrize("sitio", ["chatgpt", "gemini"])
def test_t265_las_cabeceras_de_la_web_conservan_sus_almohadillas(sitio):
    turnos = nav.leer_turnos(dom(f"{sitio}_cabeceras.html"), sitio)
    respuesta = turnos[-1]["texto"]
    assert turnos[-1]["rol"] == "ia"
    assert respuesta.startswith("### PROPUESTAS IMPLEMENTABLES\n")
    assert "\n#### Nota\n" in respuesta
    # Lo que leen despues el auditor y la revision sigue funcionando con las marcas.
    from nucleo import auditor, revision
    assert revision.comprobar_seccion(respuesta)[0]
    assert auditor.partir_cierre(respuesta)[0] == respuesta


def test_t265_cabecera_vacia_u_oculta_no_deja_almohadillas_sueltas():
    html = ('<div class="markdown"><h2></h2><h3>  Titulo  </h3><p>x</p>'
            '<h6 class="sr-only">Gemini ha dicho</h6></div>')
    assert nav._texto(nav._parsear(html)) == "### Titulo\n\nx"


def test_t667_texto_citado_de_gemini_se_conserva_y_solo_cae_la_pildora():
    """04/10 (tribunal): Gemini envuelve la frase citada en span.citation-N; se borraba ENTERA (se perdio 'P4: ...')."""
    html = ('<model-response id="r1"><message-content><p>P3: APROBAR | bien. <span class="citation-4 citation-end-4">'
            'P4: APROBAR | Verificar el hash asegura la inmutabilidad.<source-footnote><sup class="superscript" '
            'data-turn-source-index="1"></sup></source-footnote></span> P5: APROBAR | vale.</p>'
            '<sources-carousel-inline><a href="https://ejemplo.org/x">ejemplo</a></sources-carousel-inline>'
            '</message-content></model-response>')
    texto = nav.leer_turnos(html, "gemini")[0]["texto"]
    assert "P4: APROBAR | Verificar el hash asegura la inmutabilidad." in texto and "P5: APROBAR" in texto
    assert "ejemplo.org" in texto and texto.count("ejemplo") == 1          # la pildora va a fuentes, no al texto


# ------------------------------------------------------------------ T333: prompt largo mostrado recortado
def _turno(rol, texto, id_=""):
    return {"rol": rol, "texto": texto, "id": id_, "ocupado": False, "razono": False}


def test_t333_prompt_largo_recortado_por_la_web_cuenta_como_nuestro():
    largo = "Ayudas a un proyecto personal. " + "palabra de relleno util " * 400   # ~9.600 car.
    visto = largo[:3000] + " Mostrar más"
    despues = [_turno("usuario", visto, "u1"), _turno("ia", "respuesta", "a1")]
    assert nav.evaluar_turnos([], despues, largo)[0] == "ok"


def test_t333_prompt_largo_recortado_sin_marca_tambien():
    largo = "Ayudas a un proyecto personal. " + "palabra de relleno util " * 400
    despues = [_turno("usuario", largo[:2500], "u1"), _turno("ia", "respuesta", "a1")]
    assert nav.evaluar_turnos([], despues, largo)[0] == "ok"


def test_t333_un_prefijo_corto_o_de_otro_prompt_sigue_siendo_ajeno():
    largo = "Ayudas a un proyecto personal. " + "palabra de relleno util " * 400
    corto = [_turno("usuario", largo[:300], "u1"), _turno("ia", "respuesta", "a1")]
    assert nav.evaluar_turnos([], corto, largo)[0] == "ajeno"           # prefijo < 1000 car.
    otro = [_turno("usuario", "Otra cosa distinta. " + "xyz " * 600, "u1"), _turno("ia", "r", "a1")]
    assert nav.evaluar_turnos([], otro, largo)[0] == "ajeno"             # no es prefijo


def test_t333_un_prompt_corto_exige_igualdad_exacta():
    corto = "pregunta corta " * 20
    despues = [_turno("usuario", corto[:100], "u1"), _turno("ia", "r", "a1")]
    assert nav.evaluar_turnos([], despues, corto)[0] == "ajeno"


def test_t333_el_mismo_prompt_largo_recortado_que_ya_estaba_antes_es_viejo():
    largo = "Ayudas a un proyecto personal. " + "palabra de relleno util " * 400
    turnos = [_turno("usuario", largo[:3000] + " Mostrar más", "u1"), _turno("ia", "respuesta", "a1")]
    assert nav.evaluar_turnos(turnos, turnos, largo)[0] == "viejo"


# ------------------------------------------------------------ 11/10: Gemini cambia los nombres del menu de modo
# Menu real del 11/10: "Automatico" (Gemini 3 models) + nivel "Min." / "Medio" / "Max."; ya no hay "3.1 Pro" ni
# "Razonamiento ampliado". Equivalente: Automatico + Max. Fallo cerrado si no se reconoce.

def _menu_viejo(pro_sel=True, ampliado_sel=False, con_ampliado=True):
    return [{"etiqueta": "Rápido", "sublabel": "", "sel": not pro_sel},
            {"etiqueta": "3.1 Pro", "sublabel": "", "sel": pro_sel}] + (
        [{"etiqueta": "Razonamiento ampliado", "sublabel": "", "sel": ampliado_sel}] if con_ampliado else [])


def test_menu_gemini_11_10_se_lee_del_dom():
    items = nav.items_modo_gemini_html(dom("gemini_menu_automatico.html"))
    assert [(i["etiqueta"], i["sel"]) for i in items] == [
        ("Automático", True), ("Mín.", True), ("Medio", False), ("Máx.", False)]
    assert items[3]["sublabel"] == "Muy exhaustivo"


def test_menu_gemini_11_10_plan_es_automatico_mas_max_y_no_confirma_con_min():
    items = nav.items_modo_gemini_html(dom("gemini_menu_automatico.html"))
    plan = nav.plan_modo_gemini(items)
    assert plan["modelo"]["etiqueta"] == "Automático" and plan["nivel"]["etiqueta"] == "Máx."
    assert plan["desconocido"] == ""
    ok, motivo = nav.modo_gemini_confirmado(items)          # tal como estaba: Automatico + Min.
    assert ok is False and "Máx." in motivo
    items[1]["sel"], items[3]["sel"] = False, True           # tras pulsar Max.
    assert nav.modo_gemini_confirmado(items) == (True, "")


def test_menu_gemini_respaldo_pro_es_automatico_mas_medio():
    items = nav.items_modo_gemini_html(dom("gemini_menu_automatico.html"))
    assert nav.plan_modo_gemini(items, "pro")["nivel"]["etiqueta"] == "Medio"


def test_menu_gemini_viejo_sigue_funcionando():
    assert nav.modo_gemini_confirmado(_menu_viejo(ampliado_sel=True)) == (True, "")
    assert nav.modo_gemini_confirmado(_menu_viejo(ampliado_sel=False))[0] is False
    assert nav.modo_gemini_confirmado(_menu_viejo(con_ampliado=False)) == (True, "")   # T147: basta Pro
    assert nav.modo_gemini_confirmado(_menu_viejo(), "pro") == (True, "")
    assert nav.modo_gemini_confirmado(_menu_viejo(pro_sel=False), "pro")[0] is False


@pytest.mark.parametrize("etiquetas", [
    ["Máximo", "Pro"],                       # orden y nombre cambiados: sigue reconociendolo
    ["Automatico", "Max"],                  # sin tildes ni punto
    ["auto", ("Nivel 3", "Muy exhaustivo")],  # nivel reconocido solo por su descripcion
])
def test_menu_gemini_sinonimos(etiquetas):
    items = [{"etiqueta": e, "sublabel": "", "sel": True} if isinstance(e, str)
             else {"etiqueta": e[0], "sublabel": e[1], "sel": True} for e in etiquetas]
    assert nav.modo_gemini_confirmado(items)[0] is True


def test_menu_gemini_desconocido_no_confirma_y_avisa(monkeypatch):
    items = [{"etiqueta": e, "sublabel": s, "sel": True} for e, s in
             [("Ultra", "Gemini 4"), ("Bajo", ""), ("Alto", "")]]
    ok, motivo = nav.modo_gemini_confirmado(items)
    assert ok is False and "no reconozco" in motivo
    auto = [{"etiqueta": "Automático", "sublabel": "", "sel": True}, {"etiqueta": "Alto", "sublabel": "", "sel": True}]
    ok, motivo = nav.modo_gemini_confirmado(auto)            # Automatico sin nivel reconocible: no se envia
    assert ok is False and "sin nivel" in motivo
    emitidos = []
    from nucleo import avisos
    monkeypatch.setattr(avisos, "emitir", lambda *a, **k: emitidos.append((a, k)))
    nav._avisar_menu_gemini(items, motivo)
    assert emitidos and "Gemini" in emitidos[0][0][1] and emitidos[0][1]["clave"] == "gemini_menu:ultra|bajo|alto"


class _MenuFalso:
    """Pagina minima con el selector de modo de Gemini (como el menu real del 17/10): al pulsar una opcion se marca
    (modelo o nivel), los bloqueados no se activan y los niveles solo existen con 'Nivel de razonamiento' desplegado."""

    def __init__(self, items):
        self.items = items          # [{"etiqueta", "sublabel", "sel", "grupo", "bloqueado", "plegable"}]
        self.abierto = False
        self.expandido = False
        self.etiqueta = "Abrir selector de modo, actualmente Gemini Automático"
        self.rancio = False         # 17/10 real: tras Escape, el SIGUIENTE clic en el boton no abre el menu
        self.keyboard = type("K", (), {"press": lambda _s, k: self.escape()})()

    def cerrar(self):
        self.abierto = self.expandido = False

    def escape(self):
        if self.abierto:
            self.rancio = True
        self.cerrar()

    def visibles(self):
        hay_plegable = any(i.get("plegable") for i in self.items)
        return [i for i in self.items if i.get("grupo") != "nivel" or self.expandido or not hay_plegable]

    def wait_for_timeout(self, ms):
        pass

    def locator(self, selector, **_):
        return _LocFalso(self, selector)


class _Icono:
    def __init__(self, nombre):
        self.nombre = nombre

    def get_attribute(self, _n):
        return self.nombre


class _LocFalso:
    def __init__(self, pagina, selector, indice=None):
        self.p, self.sel, self.i = pagina, selector, indice

    def _it(self):
        return self.p.visibles()[self.i]

    def count(self):
        if "bard-mode-menu-button" in self.sel:
            return 1
        if "gem-menu-item" in self.sel and self.i is None:
            return len(self.p.visibles()) if self.p.abierto else 0
        return 1 if "sublabel" not in self.sel or self._it()["sublabel"] else 0

    @property
    def first(self):
        return self

    def nth(self, i):
        return _LocFalso(self.p, self.sel, i)

    def locator(self, sub):
        return _LocFalso(self.p, sub, self.i)

    def all(self):
        return [_Icono("lock" if self._it().get("bloqueado") else "check")] if self.sel == "mat-icon" else []

    def inner_text(self):
        it = self._it()
        return it["sublabel"] if "sublabel" in self.sel else f" {it['etiqueta']} "

    def get_attribute(self, nombre):
        if "bard-mode-menu-button" in self.sel or self.sel == "button[aria-label]":
            # real (17/10): el contenedor no lleva aria-label; lo lleva el <button> de dentro
            return self.p.etiqueta if self.sel == "button[aria-label]" and nombre == "aria-label" else None
        it = self._it()
        if nombre == "data-mode-id":
            return "upsell_MODE_CATEGORY_PRO" if it.get("bloqueado") else "cf41b0e0dd7d53e5"
        if nombre == "aria-expanded":
            return ("true" if self.p.expandido else "false") if it.get("plegable") else None
        if self.sel == "gem-menu-item-content":
            return "checkmark-only" + (" selected" if it["sel"] else "")
        return "expandable ng-star-inserted" if it.get("plegable") else "ng-star-inserted"

    def click(self, timeout=0):
        if "bard-mode-menu-button" in self.sel:
            if self.p.rancio:
                self.p.rancio = False
            elif self.p.abierto:
                self.p.cerrar()
            else:
                self.p.abierto = True
            return
        pulsado = self._it()
        if pulsado.get("plegable"):
            self.p.expandido = True
            return
        if not pulsado.get("bloqueado"):
            for it in self.p.items:
                if it["grupo"] == pulsado["grupo"]:
                    it["sel"] = it is pulsado
        self.p.cerrar()


def test_fijar_modo_gemini_con_el_menu_nuevo_pulsa_max(monkeypatch):
    monkeypatch.setattr(nav, "_cerrar_overlays", lambda p: None)
    items = nav.items_modo_gemini_html(dom("gemini_menu_automatico.html"))
    for k, it in enumerate(items):
        it["grupo"] = "modelo" if k == 0 else "nivel"
    pagina = _MenuFalso(items)
    ok, detalle = nav._fijar_modo(pagina, "gemini")
    assert ok, detalle
    assert "'Máx.' pulsado" in detalle and "ACTIVOS: ['Automático', 'Máx.']" in detalle
    assert nav.ETIQUETA_GEMINI_CONFIRMADA["ampliado"] == pagina.etiqueta
    # tras enviar, el boton dice lo mismo que al confirmar: vale; si cambia, no
    html = f'<button data-test-id="bard-mode-menu-button" aria-label="{pagina.etiqueta}"></button>'
    assert nav.modo_en_pantalla(html, "gemini", pagina.etiqueta)["ok"] is True
    assert nav.modo_en_pantalla(html.replace("Automático", "Rápido"), "gemini", pagina.etiqueta)["ok"] is False
    assert nav.modo_en_pantalla(html, "gemini")["ok"] is False


def test_fijar_modo_gemini_menu_desconocido_no_envia(monkeypatch):
    monkeypatch.setattr(nav, "_cerrar_overlays", lambda p: None)
    avisados = []
    monkeypatch.setattr(nav, "_avisar_menu_gemini", lambda items, motivo: avisados.append(motivo))
    pagina = _MenuFalso([{"etiqueta": "Ultra", "sublabel": "", "sel": True, "grupo": "m"}])
    ok, detalle = nav._fijar_modo(pagina, "gemini")
    assert ok is False and "no reconozco" in detalle and avisados


# ------------------------------------------------------------ 17/10 (T890): menu REAL con candado y niveles plegados
# Captura del Chrome de NEXO: "Automatico" (marcado), "3.1 Pro" y "4 Argon" BLOQUEADOS (no se activan) y un item
# plegable "Nivel de razonamiento" con Min. / Medio / Max. dentro. El aria-label del boton vive en el <button> interior.

def _menu_17_10(desplegado=True):
    items = nav.items_modo_gemini_html(dom("gemini_menu_17_10.html" if desplegado else "gemini_menu_17_10_plegado.html"))
    grupo = {"Automático": "modelo", "3.1 Pro": "modelo", "4 Argon": "modelo", "Nivel de razonamiento": "plegable"}
    for it in items:
        it["grupo"] = grupo.get(it["etiqueta"], "nivel")
    return items


def test_menu_gemini_17_10_se_lee_del_dom_con_candados_y_plegable():
    items = nav.items_modo_gemini_html(dom("gemini_menu_17_10.html"))
    assert [(i["etiqueta"], i["sel"], i["bloqueado"], i["plegable"]) for i in items] == [
        ("Automático", True, False, False), ("3.1 Pro", False, True, False), ("4 Argon", False, True, False),
        ("Nivel de razonamiento", False, False, True), ("Mín.", False, False, False), ("Medio", False, False, False),
        ("Máx.", True, False, False)]
    assert items[3]["sublabel"] == "" and items[6]["sublabel"] == "Muy exhaustivo"


def test_menu_gemini_17_10_plan_salta_los_bloqueados_y_pide_desplegar_el_nivel():
    plegado = nav.items_modo_gemini_html(dom("gemini_menu_17_10_plegado.html"))
    assert [i["etiqueta"] for i in plegado] == ["Automático", "3.1 Pro", "4 Argon", "Nivel de razonamiento"]
    plan = nav.plan_modo_gemini(plegado)
    assert plan["modelo"]["etiqueta"] == "Automático" and plan["nivel"] is None and plan["desconocido"] == ""
    assert plan["plegable"]["etiqueta"] == "Nivel de razonamiento"
    assert nav.modo_gemini_confirmado(plegado)[0] is False            # plegado no se puede leer: fallo cerrado
    desplegado = nav.items_modo_gemini_html(dom("gemini_menu_17_10.html"))
    plan = nav.plan_modo_gemini(desplegado)
    assert plan["nivel"]["etiqueta"] == "Máx." and plan["plegable"] is None
    assert nav.modo_gemini_confirmado(desplegado) == (True, "")          # Automatico + Max. ya marcados
    assert nav.plan_modo_gemini(desplegado, "pro")["nivel"]["etiqueta"] == "Medio"


def test_menu_gemini_solo_con_pro_bloqueado_no_se_envia():
    items = [{"etiqueta": "3.1 Pro", "sublabel": "", "sel": False, "bloqueado": True}]
    ok, motivo = nav.modo_gemini_confirmado(items)
    assert ok is False and "no reconozco" in motivo


def test_fijar_modo_gemini_17_10_despliega_el_nivel_pulsa_max_y_no_toca_pro():
    items = _menu_17_10()
    for it in items:                       # punto de partida: Automatico con nivel Min.
        if it["grupo"] == "nivel":
            it["sel"] = it["etiqueta"] == "Mín."
    pagina = _MenuFalso(items)
    ok, detalle = nav._fijar_modo(pagina, "gemini")
    assert ok, detalle
    assert "'Automático' ya activo" in detalle and "'Máx.' pulsado" in detalle
    assert "ACTIVOS: ['Automático', 'Máx.']" in detalle and "3.1 Pro" not in detalle
    assert nav.ETIQUETA_GEMINI_CONFIRMADA["ampliado"] == pagina.etiqueta
    # el boton real lleva el aria-label en el <button> interior: tras enviar se reconoce igual
    html = dom("gemini_menu_17_10.html")
    assert nav.modo_en_pantalla(html, "gemini", pagina.etiqueta)["ok"] is True
    assert nav.modo_en_pantalla(html.replace("Automático", "Rápido", 1), "gemini", pagina.etiqueta)["ok"] is False


def test_fijar_modo_gemini_no_usa_escape_que_deja_el_menu_rancio():
    """Con el menu 17/10, tras 'Automatico ya activo' hay que volver a abrirlo para el nivel: si se cerrase con
    Escape el siguiente clic no abriria nada (menu vacio, 'no reconozco ningun modelo')."""
    pagina = _MenuFalso(_menu_17_10())
    ok, detalle = nav._fijar_modo(pagina, "gemini")
    assert ok, detalle
    assert "'Automático' ya activo" in detalle and "'Máx.' ya activo" in detalle
    pagina.escape() if pagina.abierto else None
    pagina.abierto = False
    pagina.rancio = True                   # un Escape de antes: el primer clic solo reinicia; _abrir_menu_gemini reintenta
    ok, detalle = nav._fijar_modo(pagina, "gemini")
    assert ok, detalle
