# -*- coding: utf-8 -*-
"""Prueba REAL de conversaciones en las webs de IA, en el Chrome de NEXO (nunca el personal). Bloque 8, 17/10.

Por sitio (chatgpt, gemini, claude) y con prompts inocuos:
  1) chat NUEVO: se le da una palabra clave y se anota la URL de la conversacion;
  2) SEGUIR en el mismo: se le pregunta la palabra; la respuesta debe contenerla y la URL no cambia;
  3) RETOMAR por su URL desde OTRA pestana (la pestana del sitio se aparta a about:blank y se abre una nueva
     en la raiz del sitio): se le pregunta la palabra otra vez. (Claude web: solo 1 y 2, cupo de 3 al dia.)
Escribe el resultado en registros/prueba_chats_web_<fecha>.json. Gasta 2-3 mensajes por sitio y varios minutos
(modos Pensar / Razonamiento ampliado / Sonnet Alto reales).

Uso:  .venv\\Scripts\\python.exe herramientas_nube\\prueba_chats_web.py chatgpt [gemini] [claude]
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

PASOS_POR_SITIO = {"chatgpt": 3, "gemini": 3, "claude": 2}


def _proveedor(sitio: str):
    import proveedores
    return {"chatgpt": proveedores.ChatGPTProvider, "gemini": proveedores.GeminiProvider,
            "claude": proveedores.ClaudeWebProvider}[sitio]()


def _otra_pestana(sitio: str) -> str:
    """Aparta la(s) pestana(s) del sitio a about:blank y abre una nueva en su raiz. Devuelve lo que hizo."""
    from playwright.sync_api import sync_playwright
    from extremidades import navegador
    dominio = {"gemini": "gemini.google.com", "chatgpt": "chatgpt.com", "claude": "claude.ai"}[sitio]
    with navegador.en_exclusiva("prueba chats web: otra pestana"), sync_playwright() as p:
        nav = p.chromium.connect_over_cdp(f"http://127.0.0.1:{navegador.puerto()}")
        viejas = [pg for c in nav.contexts for pg in c.pages if dominio in pg.url]
        for pg in viejas:
            pg.goto("about:blank")
        nueva = navegador._abrir_pestana(nav, f"https://{dominio}/")
        nueva.wait_for_timeout(2500)
        return f"{len(viejas)} pestana(s) apartada(s); nueva en {nueva.url[:60]}"


def _cerrar_en_blanco() -> None:
    from playwright.sync_api import sync_playwright
    from extremidades import navegador
    with navegador.en_exclusiva("prueba chats web: limpiar"), sync_playwright() as p:
        nav = p.chromium.connect_over_cdp(f"http://127.0.0.1:{navegador.puerto()}")
        todas = [pg for c in nav.contexts for pg in c.pages]
        for pg in todas:
            if pg.url == "about:blank" and len(todas) > 1:
                pg.close()
                todas.remove(pg)


def _paso(nombre: str, r, esperada: str | None, url_esperada: str | None, url_real: str | None, t0: float) -> dict:
    texto = (r.texto or "")
    ok_palabra = (esperada.lower() in texto.lower()) if esperada else None
    return {"paso": nombre, "ok_envio": r.ok, "estado": r.estado, "detalle": (r.detalle or "")[:300],
            "palabra_en_respuesta": ok_palabra, "misma_url": (url_real == url_esperada) if url_esperada else None,
            "url": url_real, "respuesta": texto[:300], "segundos": round(time.time() - t0),
            "modo_antes": (r.meta or {}).get("modo_antes"), "modo_tras_enviar": (r.meta or {}).get("modo_tras_enviar")}


def probar(sitio: str) -> dict:
    prov = _proveedor(sitio)
    palabra = random.choice(["alcachofa", "tamarindo", "escalera", "violeta"]) + str(random.randint(100, 999))
    salida = {"sitio": sitio, "palabra": palabra, "pasos": []}
    if not prov.disponible():
        salida["error"] = "proveedor no disponible (Chrome de NEXO cerrado, enfriado...)"
        return salida

    t0 = time.time()
    r1 = prov.enviar(f"Prueba de NEXO (inocua). La palabra clave de esta conversacion es {palabra}. "
                     "Responde solo: ENTENDIDO.")
    url1 = prov.url if r1.ok else None
    salida["pasos"].append(_paso("1_chat_nuevo", r1, None, None, url1, t0))
    if not r1.ok or not url1:
        return salida

    t0 = time.time()
    r2 = prov.continuar("Prueba de NEXO (inocua). Cual era la palabra clave de esta conversacion? Responde solo la palabra.")
    salida["pasos"].append(_paso("2_seguir_en_el_mismo", r2, palabra, url1, prov.url if r2.ok else None, t0))
    if sitio == "claude" or not r2.ok:
        return salida

    salida["otra_pestana"] = _otra_pestana(sitio)
    t0 = time.time()
    r3 = prov.continuar("Prueba de NEXO (inocua). Otra vez: cual era la palabra clave de esta conversacion? "
                        "Responde solo la palabra.", url=url1)
    salida["pasos"].append(_paso("3_retomar_por_url_desde_otra_pestana", r3, palabra, url1,
                                 prov.url if r3.ok else None, t0))
    _cerrar_en_blanco()
    return salida


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    sitios = [a for a in sys.argv[1:] if a in PASOS_POR_SITIO]
    if not sitios:
        print("Indica al menos un sitio: chatgpt, gemini o claude (ver --help).")
        raise SystemExit(2)
    destino = RAIZ / "registros" / f"prueba_chats_web_{time.strftime('%Y%m%d')}.json"
    todo = json.loads(destino.read_text(encoding="utf-8")) if destino.exists() else {}
    for s in sitios:
        print(f"== {s} ==", flush=True)
        try:
            todo[s] = probar(s)
        except Exception as e:
            todo[s] = {"sitio": s, "error": f"{type(e).__name__}: {e}"[:400]}
        destino.write_text(json.dumps(todo, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(todo[s], ensure_ascii=False, indent=1), flush=True)
