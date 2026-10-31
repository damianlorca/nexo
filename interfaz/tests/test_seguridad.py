# -*- coding: utf-8 -*-
"""Incremento 1: token por arranque, cookie de sesion, CSRF, Host/Origin, CORS, CSP y logs sin token."""
from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from interfaz.seguridad import COOKIE, FiltroToken
from interfaz.tests.conftest import BASE


def test_token_se_escribe_al_arrancar_y_se_borra_al_parar(app, ajustes):
    with TestClient(app, base_url=BASE):
        assert ajustes.token_fichero.read_text(encoding="utf-8") == app.state.seguridad.token
    assert not ajustes.token_fichero.exists()


def test_salud_es_publica(cliente):
    r = cliente.get("/salud")
    assert r.status_code == 200 and r.json() == {"ok": True, "app": "nexo-interfaz"}


def test_sin_sesion_da_401(cliente):
    r = cliente.get("/")
    assert r.status_code == 401
    assert "abrir_nexo.bat" in r.text


def test_token_malo_da_401_y_no_crea_cookie(cliente):
    r = cliente.get("/entrar", params={"t": "no-es-el-token"})
    assert r.status_code == 401
    assert COOKIE not in cliente.cookies


def test_token_bueno_da_cookie_httponly_samesite_strict(cliente, app):
    r = cliente.get("/entrar", params={"t": app.state.seguridad.token})
    assert r.status_code == 200
    galleta = r.headers["set-cookie"].lower()
    assert "httponly" in galleta and "samesite=strict" in galleta and "path=/" in galleta
    # El token se canjea y se sale de la URL con un refresh a /.
    assert 'http-equiv="refresh"' in r.text and "url=/" in r.text
    assert cliente.get("/").status_code == 200


def test_rate_limit_en_entrar(cliente, app, ajustes):
    for _ in range(ajustes.intentos_login):
        assert cliente.get("/entrar", params={"t": "malo"}).status_code == 401
    assert cliente.get("/entrar", params={"t": "malo"}).status_code == 429
    # Con el limite alcanzado, ni el token bueno entra.
    assert cliente.get("/entrar", params={"t": app.state.seguridad.token}).status_code == 429


def test_host_ajeno_da_400(cliente):
    r = cliente.get("/salud", headers={"host": "evil.example:8765"})
    assert r.status_code == 400


def test_post_sin_csrf_da_403(cliente, csrf):
    assert cliente.post("/salir").status_code == 403
    assert cliente.post("/salir", headers={"X-CSRF-Token": "falso"}).status_code == 403


def test_post_con_csrf_funciona_y_cierra_sesion(cliente, csrf):
    r = cliente.post("/salir", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 204 and r.headers["hx-redirect"] == "/entrar"
    assert cliente.get("/").status_code == 401


def test_post_con_origen_ajeno_da_403_aunque_traiga_csrf(cliente, csrf):
    r = cliente.post("/salir", headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"})
    assert r.status_code == 403
    r = cliente.post("/salir", headers={"X-CSRF-Token": csrf, "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_post_sin_sesion_da_401(cliente):
    assert cliente.post("/salir", headers={"X-CSRF-Token": "x"}).status_code == 401


def test_cabeceras_de_seguridad_en_todas_las_respuestas(cliente, csrf):
    for ruta in ("/", "/salud", "/entrar", "/estatico/nexo.css", "/no-existe"):
        r = cliente.get(ruta)
        csp = r.headers["content-security-policy"]
        assert "default-src 'none'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
        assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "no-referrer"


def test_cors_denegado(cliente, csrf):
    r = cliente.options("/", headers={"Origin": "https://evil.example",
                                      "Access-Control-Request-Method": "POST"})
    assert r.status_code >= 400
    assert "access-control-allow-origin" not in r.headers
    r = cliente.get("/", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_sin_docs_ni_openapi(cliente, csrf):
    for ruta in ("/docs", "/redoc", "/openapi.json"):
        assert cliente.get(ruta).status_code == 404


def test_pagina_incluye_csrf_en_hx_headers(cliente, csrf):
    r = cliente.get("/")
    assert f'"X-CSRF-Token": "{csrf}"' in r.text
    assert "unsafe" not in r.text


def test_filtro_tacha_token_del_log_de_accesos():
    registro = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1,
                                 '%s - "%s %s HTTP/%s" %d',
                                 ("127.0.0.1:5000", "GET", "/entrar?t=SECRETO123", "1.1", 200), None)
    FiltroToken().filter(registro)
    assert "SECRETO123" not in registro.getMessage()
    assert "/entrar?t=***" in registro.getMessage()


def test_404_con_sesion_usa_la_plantilla_con_nav(cliente, csrf):
    r = cliente.get("/no-existe")
    assert r.status_code == 404 and 'aria-label="Principal"' in r.text


def test_error_500_lleva_cabeceras_de_seguridad_y_no_la_traza(app, csrf, cliente):
    @app.get("/revienta")
    def revienta():
        raise RuntimeError(r"detalle interno C:\ruta\secreta")

    with TestClient(app, base_url=BASE, raise_server_exceptions=False, cookies=cliente.cookies) as c:
        r = c.get("/revienta")
    assert r.status_code == 500
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"
    assert r"ruta\secreta" not in r.text and "RuntimeError" not in r.text
