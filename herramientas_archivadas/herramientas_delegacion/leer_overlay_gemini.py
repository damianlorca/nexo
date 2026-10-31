# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp("http://127.0.0.1:9333")
    for p in b.contexts[0].pages:
        if "gemini" in p.url:
            print(p.evaluate("() => { const o = document.querySelector('.cdk-overlay-container'); return o ? o.innerText.slice(0, 1500) : null }"))
            print("BOTONES:", p.evaluate("() => [...document.querySelectorAll('.cdk-overlay-container button, .cdk-overlay-container a')].map(b => (b.innerText||b.getAttribute('aria-label')||'').trim()).filter(Boolean)"))
