# -*- coding: utf-8 -*-
"""Hito movil, incremento 3: app instalable (manifest, service worker, sin conexion)."""
from __future__ import annotations

import re
import struct

from interfaz.rutas.pwa import MANIFEST
from interfaz.vistas import DIR

SW = (DIR / "estatico" / "sw.js").read_text(encoding="utf-8")


def _lado_png(ruta) -> tuple[int, int]:
    cab = ruta.read_bytes()[:24]
    assert cab[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", cab[16:24])


def test_manifest_publico_e_instalable(cliente):
    r = cliente.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    m = r.json()
    assert m["name"] == "NEXO" and m["display"] == "standalone" and m["start_url"] == "/"
    tamanos = {(i["sizes"], i["purpose"]) for i in m["icons"]}
    assert {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= tamanos


def test_iconos_existen_con_su_tamano_y_se_sirven(cliente):
    for icono in MANIFEST["icons"]:
        ruta = DIR / icono["src"].lstrip("/")
        lado = int(icono["sizes"].split("x")[0])
        assert _lado_png(ruta) == (lado, lado)
        assert cliente.get(icono["src"]).status_code == 200


def test_sw_en_la_raiz_publico_y_como_javascript(cliente):
    r = cliente.get("/sw.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/javascript")
    assert "addEventListener(\"fetch\"" in r.text


def test_sin_conexion_publica_y_sin_datos(cliente):
    r = cliente.get("/sin-conexion")
    assert r.status_code == 200
    assert "Sin conexión" in r.text
    assert "csrf" not in r.text.lower() and "sse-connect" not in r.text


def test_sw_solo_precachea_estaticos_y_sin_conexion():
    lista = re.search(r"var ESENCIALES = \[(.*?)\];", SW, re.S).group(1)
    urls = re.findall(r'"(/[^"]*)"', lista)
    assert "SIN_CONEXION" in lista and urls
    assert all(u.startswith("/estatico/") for u in urls)


def test_sw_solo_guarda_en_cache_lo_estatico():
    # Unico put a la cache, y dentro de la rama esEstatico(url).
    assert SW.count("c.put(") == 1 and SW.count(".put(") == 1
    rama = SW[SW.index("if (esEstatico(url))"):]
    assert "c.put(" in rama
    navegacion = SW[SW.index('req.mode === "navigate"'):SW.index("if (esEstatico(url))")]
    assert "put(" not in navegacion           # las paginas con datos nunca se guardan
    codigo = re.sub(r"//.*", "", SW)
    assert "/eventos" not in codigo           # el SSE ni se menciona en el codigo: no se intercepta
    assert 'req.method !== "GET"' in SW       # POST (ordenes, PARADA) nunca pasan por el SW


def test_paginas_enlazan_manifest_y_csp_lo_permite(cliente, csrf):
    r = cliente.get("/")
    assert '<link rel="manifest" href="/manifest.webmanifest">' in r.text
    csp = r.headers["content-security-policy"]
    assert "manifest-src 'self'" in csp and "worker-src 'self'" in csp
    assert "default-src 'none'" in csp


def test_estaticos_se_revalidan_siempre(cliente):
    """Sin Cache-Control el navegador cacheaba nexo.js "a ojo" y seguia con el viejo tras actualizar."""
    r = cliente.get("/estatico/nexo.js")
    assert r.headers["cache-control"] == "no-cache"
    assert "etag" in r.headers or "last-modified" in r.headers     # para que la revalidacion de 304
