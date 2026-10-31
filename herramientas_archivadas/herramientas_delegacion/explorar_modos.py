# -*- coding: utf-8 -*-
"""T147: abre chat nuevo en Gemini y ChatGPT y lista las opciones de modo (abre menus y los cierra con Escape)."""
from playwright.sync_api import sync_playwright

VISIBLES = """(sel) => [...document.querySelectorAll(sel)].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height; })
  .map(e => ({t: (e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,90), a: (e.getAttribute('aria-label')||'').slice(0,70),
              d: e.getAttribute('data-test-id') || e.getAttribute('data-testid') || '', chk: e.getAttribute('aria-checked') || e.getAttribute('aria-pressed') || ''}))"""
with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = b.contexts[0]
    pags = {("gemini" if "gemini" in p.url else "chatgpt" if "chatgpt" in p.url else ""): p for p in ctx.pages}
    g = pags.get("gemini")
    if g:
        g.goto("https://gemini.google.com/app", wait_until="domcontentloaded"); g.wait_for_timeout(3500)
        import sys; sys.path.insert(0, r"C:\Users\damia\Desktop\AI\agente")
        from extremidades.navegador import _cerrar_overlays
        _cerrar_overlays(g)
        btn = g.locator('[data-test-id="bard-mode-menu-button"]')
        print("GEMINI boton:", btn.first.get_attribute("aria-label") if btn.count() else None)
        if btn.count():
            btn.first.click(timeout=8000); g.wait_for_timeout(1500)
            for x in g.evaluate(VISIBLES, '[role=menuitem],[role=menuitemradio],[role=menuitemcheckbox],[role=switch],.mat-mdc-menu-item,mat-slide-toggle,button[role=switch]'):
                print("   ", x)
            g.keyboard.press("Escape")
    c = pags.get("chatgpt")
    if c:
        c.goto("https://chatgpt.com/", wait_until="domcontentloaded"); c.wait_for_timeout(3500); _cerrar_overlays(c)
        print("CHATGPT pills:", c.evaluate(VISIBLES, "button.__composer-pill, [data-testid*=composer] button"))
        sw = c.locator('[data-testid="model-switcher-dropdown-button"], button[aria-label*="modelo" i]')
        print("CHATGPT selector modelo:", sw.count())
        if sw.count():
            sw.first.click(timeout=8000); c.wait_for_timeout(1500)
            for x in c.evaluate(VISIBLES, '[role=menuitem],[role=menuitemradio],[role=option]'):
                print("   ", x)
            c.keyboard.press("Escape")
        plus = c.locator('[data-testid="composer-plus-btn"], button[aria-label*="Añadir" i]')
        print("CHATGPT boton +:", plus.count())
        if plus.count():
            plus.first.click(timeout=8000); c.wait_for_timeout(1500)
            for x in c.evaluate(VISIBLES, '[role=menuitem],[role=menuitemradio],[role=option]'):
                print("   +", x)
            c.keyboard.press("Escape")
