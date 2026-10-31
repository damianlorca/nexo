# -*- coding: utf-8 -*-
"""Inicializar los proveedores web (peticion de Damian, noche 05/10): abre en el Chrome de NEXO (el del puerto CDP
de extremidades.navegador, perfil propio; NUNCA el Chrome personal) la web de cada proveedor, UNA pestana de fondo
por proveedor en la unica ventana (regla del 04/10), y dice si la sesion esta activa o caducada.

  estado_sesion(sitio, url, html)  -> "activa" | "caducada" | "desconocida"   (puro: sin navegador, testeable)
  inicializar(sitios)              -> [{"sitio", "estado", "url", "detalle"}]  (abre/reutiliza pestanas)

No escribe nada en las webs ni envia prompts: solo carga la pagina y la lee. Si Chrome de NEXO no esta abierto, lo
arranca con extremidades.navegador.arrancar (lo pide Damian con el boton: es su aprobacion).
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

SITIOS = {"chatgpt": ("chatgpt.com", "https://chatgpt.com/"),
          "gemini": ("gemini.google.com", "https://gemini.google.com/app"),
          "claude": ("claude.ai", "https://claude.ai/new")}

# Pagina de entrada: la URL ya lo dice (Claude redirige a /login; Google a accounts.google.com).
_URL_LOGIN = re.compile(r"(?i)(accounts\.google\.com|/login\b|/auth/|/signin|auth\.openai\.com)")
# Botones de entrar que solo salen sin sesion (vistos en las tres webs; textos en espanol e ingles).
_LOGIN_HTML = {
    "chatgpt": re.compile(r'(?i)data-testid="(login-button|signup-button)"'),
    "gemini": re.compile(r'(?i)(href="https://accounts\.google\.com/ServiceLogin|aria-label="(Iniciar sesi[oó]n|Sign in)")'),
    "claude": re.compile(r'(?i)(data-testid="login-|>\s*(Continuar con Google|Continue with Google)\s*<)'),
}
# Caja de texto del chat (la misma que usa extremidades.navegador._caja_texto).
_CAJA = {"chatgpt": re.compile(r"(?i)data-chatgpt-composer|id=\"prompt-textarea\""),
         "gemini": re.compile(r"(?i)<rich-textarea"),
         "claude": re.compile(r'(?i)data-testid="chat-input"')}


def estado_sesion(sitio: str, url: str, html: str) -> str:
    if sitio not in SITIOS:
        raise ValueError(f"sitio desconocido {sitio!r}: {', '.join(SITIOS)}")
    if _URL_LOGIN.search(url or ""):
        return "caducada"
    if _LOGIN_HTML[sitio].search(html or ""):
        return "caducada"   # ChatGPT deja escribir sin sesion: el boton de entrar manda sobre la caja
    if _CAJA[sitio].search(html or ""):
        return "activa"
    return "desconocida"


def inicializar(sitios: list[str] | tuple[str, ...] | None = None, espera_ms: int = 4000) -> list[dict]:
    """Abre (o reutiliza) una pestana de fondo por sitio en el Chrome de NEXO y lee el estado de la sesion."""
    from extremidades import navegador
    sitios = [s for s in (sitios or SITIOS) if s in SITIOS]
    if not navegador.activo():
        navegador.arrancar(aprobado=True)
    from playwright.sync_api import sync_playwright
    salida = []
    with navegador.en_exclusiva("inicializar proveedores web", espera=20):
        with sync_playwright() as p:
            chrome = p.chromium.connect_over_cdp(f"http://127.0.0.1:{navegador.puerto()}")
            for sitio in sitios:
                dominio, url = SITIOS[sitio]
                try:
                    pagina = next((x for c in chrome.contexts for x in c.pages if dominio in x.url), None)
                    if pagina is None:
                        pagina = navegador._abrir_pestana(chrome, url)
                    else:
                        pagina = navegador._en_ventana_principal(chrome, pagina)
                        pagina.reload(wait_until="domcontentloaded")
                    pagina.wait_for_timeout(espera_ms)
                    estado = estado_sesion(sitio, pagina.url, pagina.content())
                    salida.append({"sitio": sitio, "estado": estado, "url": pagina.url.split("?")[0], "detalle": ""})
                except Exception as e:   # un sitio caido no impide mirar los demas
                    log.warning("inicializar %s fallo: %s", sitio, type(e).__name__)
                    salida.append({"sitio": sitio, "estado": "error", "url": url, "detalle": f"{type(e).__name__}"})
    return salida
