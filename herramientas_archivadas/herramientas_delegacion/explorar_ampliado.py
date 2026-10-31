# -*- coding: utf-8 -*-
import sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, r"C:\Users\damia\Desktop\AI\agente")
from extremidades.navegador import _cerrar_overlays  # noqa: E402
with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp("http://127.0.0.1:9333")
    g = [p for p in b.contexts[0].pages if "gemini" in p.url][0]
    _cerrar_overlays(g)
    g.locator('[data-test-id="bard-mode-menu-button"]').first.click(timeout=8000)
    g.wait_for_timeout(1500)
    print(g.evaluate("""() => [...document.querySelectorAll('gem-menu[data-test-id=gem-mode-menu] gem-menu-item, gem-menu[data-test-id=gem-mode-menu] [data-test-id^=bard-mode-option]')]
       .map(e => (e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,40) + '  ==>  ' + e.innerHTML.replace(/_ngcontent-[^= ]+=""/g,'').replace(/<!---->/g,'').replace(/\\s+/g,' ').replace(/<svg.*?<\\/svg>/g,'<svg/>').slice(0, 700)).join('\\n\\n')"""))
    g.keyboard.press("Escape")
