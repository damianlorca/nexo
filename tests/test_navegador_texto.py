# -*- coding: utf-8 -*-
"""extremidades/navegador.py: la parte que NO necesita Chrome (texto y deteccion de bloqueo).

prueba_extraer_respuesta.py cubre casos de _extraer_respuesta como script; aqui van en
pytest junto con _limpiar_respuesta, _revisar_bloqueo y arrancar() con la shell simulada.
Lo que maneja la pagina (preguntar, _esperar_respuesta_dom) necesita Chrome por CDP:
no se prueba aqui.
"""
from __future__ import annotations

import pytest

from extremidades import navegador as nav


def test_extraer_respuesta_corta_por_la_ultima_aparicion_del_prompt():
    antes = "Menu\nHistorial"
    ultimo = "Menu\nHistorial\nhola que tal\nGemini ha dicho\nBien, gracias.\nGemini no es humano. Puede cometer errores"
    assert nav._extraer_respuesta(antes, ultimo, "hola que tal") == "Bien, gracias."


def test_extraer_respuesta_quita_insignia_suelta():
    ultimo = "pregunta\nRespuesta larga.\n\n\n\nFlash"
    assert nav._extraer_respuesta("", ultimo, "pregunta") == "Respuesta larga."


def test_extraer_respuesta_pagina_muy_cambiada_usa_todo():
    assert nav._extraer_respuesta("x" * 100, "otra cosa\nprompt\nsol", "prompt") == "sol"


def test_limpiar_respuesta_quita_botones_y_encuesta():
    texto = "Copiar\nLa capital es Paris.\nHa pensado durante 3 s\n¿Te está resultando útil esta conversación?\nSi No"
    assert nav._limpiar_respuesta(texto) == "La capital es Paris."


def test_revisar_bloqueo_detecta_captcha():
    with pytest.raises(nav.Bloqueo):
        nav._revisar_bloqueo("Please verify you are human")
    nav._revisar_bloqueo("Respuesta normal")  # no lanza


# B6 de N02 (arreglado): hablar de captchas en la conversacion ya no se toma por un bloqueo.
def test_revisar_bloqueo_no_salta_por_hablar_de_captchas():
    prompt = "¿Que es un captcha y por que da 'too many requests'?"
    respuesta = "Un captcha es una prueba para distinguir personas de bots..."
    cuerpo = f"Gemini\nTu\n{prompt}\nGemini ha dicho\n{respuesta}"
    nav._revisar_bloqueo(cuerpo, (prompt, respuesta))


def test_revisar_bloqueo_sigue_viendo_un_captcha_real_aunque_se_hable_de_el():
    prompt = "Explicame que es un captcha"
    cuerpo = f"{prompt}\nUnusual activity: verify you are human"
    with pytest.raises(nav.Bloqueo):
        nav._revisar_bloqueo(cuerpo, (prompt,))


# B10 de N02 (arreglado)
def test_limpiar_respuesta_no_corta_una_frase_legitima():
    texto = "Primer punto.\nUn becario puede cometer errores si nadie revisa.\nTercer punto."
    assert "Tercer punto." in nav._limpiar_respuesta(texto)


def test_arrancar_si_ya_esta_activo_no_lanza_nada(monkeypatch):
    monkeypatch.setattr(nav, "activo", lambda: True)
    monkeypatch.setattr(nav.shell, "lanzar", lambda *a, **k: pytest.fail("no deberia lanzar"))
    assert nav.arrancar()["ya_estaba"] is True


def test_arrancar_lanza_por_la_shell_con_perfil_aparte(monkeypatch, reloj_falso):
    reloj_falso(nav)
    estados = iter([False, False, True])
    monkeypatch.setattr(nav, "activo", lambda: next(estados))
    monkeypatch.setattr(nav, "valor", lambda r, d=None: {"navegador.perfil": "C:/perfil"}.get(r, d))
    lanzados = []
    monkeypatch.setattr(nav.shell, "lanzar",
                        lambda cmd, nombre, aprobado: lanzados.append((cmd, nombre, aprobado)) or {"log": "x"})
    assert nav.arrancar() == {"log": "x"}
    cmd, nombre, aprobado = lanzados[0]
    assert "--remote-debugging-port=9333" in cmd and '--user-data-dir="C:/perfil"' in cmd
    assert nombre == "chrome_agente" and aprobado is False


def test_arrancar_sin_puerto_da_error_legible(monkeypatch, reloj_falso):
    reloj_falso(nav)
    monkeypatch.setattr(nav, "activo", lambda: False)
    monkeypatch.setattr(nav.shell, "lanzar", lambda *a, **k: {"log": "registros/chrome.log"})
    with pytest.raises(RuntimeError, match="chrome.log"):
        nav.arrancar()


def test_limpiar_respuesta_corta_el_pie_de_chatgpt():
    texto = "Respuesta buena.\nChatGPT puede cometer errores. Considera verificar la informacion importante.\nPensar"
    assert nav._limpiar_respuesta(texto) == "Respuesta buena."


# 27/09 (caso real): los titulos de la barra lateral "Recientes" ("Para que sirve un
# captcha") hacian saltar el bloqueo en TODAS las peticiones siguientes, incluso al
# cargar la pagina antes de enviar nada. La navegacion no es donde sale un captcha real.
class _Localizador:
    def __init__(self, textos):
        self._textos = textos

    def all_inner_texts(self):
        return list(self._textos)


class _PaginaFalsa:
    def __init__(self, cuerpo, navegacion):
        self.cuerpo, self.navegacion, self.selectores = cuerpo, navegacion, []

    def inner_text(self, selector):
        assert selector == "body"
        return self.cuerpo

    def locator(self, selector):
        self.selectores.append(selector)
        return _Localizador(self.navegacion)


BARRA = "Recientes\nPara qué sirve un captcha\nInforme sobre gstack"


def test_revisar_bloqueo_ignora_los_titulos_de_la_barra_lateral():
    pagina = _PaginaFalsa(f"Gemini\n{BARRA}\nHola, ¿en qué te ayudo?", [BARRA])
    nav._revisar_bloqueo(pagina.inner_text("body"), nav._navegacion(pagina))
    assert "[role=navigation]" in pagina.selectores[0]


def test_revisar_bloqueo_sigue_viendo_un_captcha_real_con_barra_lateral():
    pagina = _PaginaFalsa(f"{BARRA}\nUnusual activity: verify you are human", [BARRA])
    with pytest.raises(nav.Bloqueo):
        nav._revisar_bloqueo(pagina.inner_text("body"), nav._navegacion(pagina))


def test_navegacion_quita_primero_los_trozos_largos():
    # nav dentro de aside: si se quitara antes el trozo corto, el largo ya no casaria.
    corto, largo = "Uso del captcha", "Biblioteca\nUso del captcha\nOtro"
    pagina = _PaginaFalsa(f"x\n{largo}\ny", [corto, largo])
    assert nav._navegacion(pagina) == (largo, corto)
    nav._revisar_bloqueo(pagina.inner_text("body"), nav._navegacion(pagina))


def test_navegacion_sin_pagina_valida_no_rompe():
    class Rota:
        def locator(self, s):
            raise RuntimeError("pagina cerrada")
    assert nav._navegacion(Rota()) == ()


def test_selector_cubre_los_turnos_de_gemini_y_chatgpt():
    for zona in ("[role=navigation]", "user-query", "model-response", "[data-message-author-role]",
                 ".cdk-live-announcer-element"):
        assert zona in nav.SELECTOR_NO_BLOQUEO
    assert "[aria-live]" not in nav.SELECTOR_NO_BLOQUEO  # un aviso real podria ir ahi


def test_revisar_bloqueo_ignora_la_pregunta_pintada_distinta_y_el_titulo_del_razonamiento():
    # Caso real 27/09: la pregunta con otro espaciado y "Defining CAPTCHA Purpose".
    turnos = ["Has dicho Responde en una sola frase corta: ¿para qué sirve un captcha en una web?",
              "Defining CAPTCHA Purpose\nUn captcha sirve para verificar que el usuario es humano."]
    cuerpo = "Conversación con Gemini\n" + "\n".join(turnos) + "\nGemini no es humano."
    pagina = _PaginaFalsa(cuerpo, turnos)
    nav._revisar_bloqueo(cuerpo, ("Responde en una sola frase corta: ¿para qué sirve un captcha en una web?",)
                         + nav._navegacion(pagina))
