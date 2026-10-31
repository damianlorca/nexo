# -*- coding: utf-8 -*-
"""T147: atributos del boton 'Pensar' de ChatGPT y del selector de modo de Gemini (solo lectura)."""
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp("http://127.0.0.1:9333")
    for ctx in b.contexts:
        for pg in ctx.pages:
            if "chatgpt.com" in pg.url:
                print("CHATGPT", pg.evaluate("""() => [...document.querySelectorAll('button')].filter(b => (b.innerText||'').trim()==='Pensar')
                  .map(b => ({attrs: [...b.attributes].map(a => a.name + '=' + a.value.slice(0,60)), padre: b.parentElement.outerHTML.slice(0,300)}))"""))
            if "gemini.google.com" in pg.url:
                print("GEMINI", pg.evaluate("""() => [...document.querySelectorAll('button')].filter(b => (b.getAttribute('aria-label')||'').startsWith('Abrir selector de modo'))
                  .map(b => [...b.attributes].map(a => a.name + '=' + a.value.slice(0,60)))"""))
