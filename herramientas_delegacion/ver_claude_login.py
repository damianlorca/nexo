# -*- coding: utf-8 -*-
"""Comprueba (solo lectura) si la pestana de claude.ai del Chrome de NEXO tiene sesion iniciada."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extremidades import navegador  # noqa: E402  (T198: candado del Chrome de NEXO)
with navegador.en_exclusiva("ver sesion de claude.ai"), sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp("http://127.0.0.1:9333")
    pags = [p for p in b.contexts[0].pages if "claude.ai" in p.url]
    if not pags:
        print("no hay pestana de claude.ai"); raise SystemExit
    p = pags[0]
    print("URL:", p.url)
    print("caja de texto:", p.locator('[contenteditable="true"]').count(), "| texto login:", "Log in" in p.inner_text("body")[:3000] or "Iniciar sesión" in p.inner_text("body")[:3000])
    print(p.evaluate("() => [...document.querySelectorAll('button')].map(b => (b.getAttribute('aria-label')||b.innerText||'').trim()).filter(Boolean).slice(0,25)"))
