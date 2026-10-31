# -*- coding: utf-8 -*-
"""T147: prueba en vivo de _asegurar_modo sin enviar ningun prompt (abre pestanas si faltan)."""
import sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, r"C:\Users\damia\Desktop\AI\agente")
from extremidades import navegador  # noqa: E402
from extremidades.navegador import URL_NUEVA, _asegurar_modo, _cerrar_overlays  # noqa: E402
sitios = sys.argv[1:] or ["gemini", "chatgpt"]
with navegador.en_exclusiva("prueba de modos en vivo"), sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = b.contexts[0]
    for sitio in sitios:
        pg = next((p for p in ctx.pages if sitio in p.url), None) or ctx.new_page()
        pg.bring_to_front()
        pg.goto(URL_NUEVA[sitio], wait_until="domcontentloaded")
        pg.wait_for_timeout(4000)
        _cerrar_overlays(pg)
        print(sitio, "1a:", _asegurar_modo(pg, sitio), flush=True)
        print(sitio, "2a (idempotente):", _asegurar_modo(pg, sitio), flush=True)
