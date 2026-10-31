# -*- coding: utf-8 -*-
"""T147: explora (solo lectura) los selectores de modelo/modo de Gemini y ChatGPT en el Chrome de NEXO."""
from playwright.sync_api import sync_playwright

JS = """() => {
  const out = [];
  document.querySelectorAll('button, [role=button], [role=menuitem], [role=option]').forEach(b => {
    const r = b.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    const t = (b.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 60);
    const a = b.getAttribute('aria-label') || '';
    const d = b.getAttribute('data-testid') || '';
    if (/pro|flash|r[aá]pid|pensa|think|model|modo|mode|deep|avanz|gpt|nuevo|new chat|nueva/i.test(t + ' ' + a + ' ' + d))
      out.push({t, a: a.slice(0, 60), d, tag: b.tagName.toLowerCase(), y: Math.round(r.y)});
  });
  return out.slice(0, 40);
}"""
with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp("http://127.0.0.1:9333")
    for ctx in b.contexts:
        for pg in ctx.pages:
            if any(s in pg.url for s in ("gemini.google.com", "chatgpt.com")):
                print("URL", pg.url)
                for x in pg.evaluate(JS):
                    print("   ", x)
