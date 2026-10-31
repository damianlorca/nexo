# -*- coding: utf-8 -*-
"""Abre el Chrome de NEXO (perfil propio, CDP 9333) y, si se pide, una pestana con una URL (p. ej. claude.ai)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extremidades import navegador  # noqa: E402

if not navegador.activo():
    print(navegador.arrancar(aprobado=True))
    for _ in range(20):
        if navegador.activo():
            break
        time.sleep(1)
print("activo:", navegador.activo())
if len(sys.argv) > 1:
    from playwright.sync_api import sync_playwright
    with navegador.en_exclusiva("abrir pestana a mano"), sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{navegador.puerto()}")
        pg = b.contexts[0].new_page()
        pg.goto(sys.argv[1], wait_until="domcontentloaded")
        pg.bring_to_front()
        print("abierta:", pg.url)
