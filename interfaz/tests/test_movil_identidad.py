# -*- coding: utf-8 -*-
"""Hito movil, incremento 2: entrar desde el movil con la identidad de Tailscale (sin token)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from interfaz.app import crear_app
from interfaz.config import Ajustes
from interfaz.seguridad import COOKIE

HOST = "pc.ejemplo.ts.net"
DUENO = "Yo@X.com"


@pytest.fixture
def app_tn(tmp_path):
    return crear_app(Ajustes(token_fichero=tmp_path / "t.txt", vigilar=False, push_carpeta=tmp_path / "push", tailnet_host=HOST, tailnet_dueno=DUENO))


def por_serve(app, login=None, ip="127.0.0.1"):
    """Cliente como lo ve la web detras de Serve (sin proxy-headers): 127.0.0.1 + Host tailnet + https."""
    cab = {"host": HOST, "x-forwarded-proto": "https"}
    if login:
        cab["tailscale-user-login"] = login
    # https: la cookie Secure solo se reenvia por https (como en el movil).
    return TestClient(app, base_url="https://127.0.0.1:8765", client=(ip, 50000), headers=cab)


def test_el_dueno_entra_sin_token_y_recibe_cookie_secure(app_tn):
    with por_serve(app_tn, "yo@x.com") as c:        # mayusculas/minusculas dan igual
        r = c.get("/")
        assert r.status_code == 200
        cookie = r.headers["set-cookie"]
        assert "nexo_sesion=" in cookie and "Secure" in cookie and "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
        sesion = app_tn.state.seguridad.sesion(c.cookies.get(COOKIE))
        assert sesion["via"] == "tailnet"
        # La segunda peticion reutiliza la sesion: no crea otra.
        r2 = c.get("/")
        assert "set-cookie" not in r2.headers


def test_con_proxy_headers_de_uvicorn_tambien_entra(app_tn):
    with TestClient(app_tn, base_url=f"https://{HOST}", client=("100.79.7.24", 5),
                    headers={"tailscale-user-login": DUENO}) as c:
        assert c.get("/").status_code == 200


def test_el_dueno_con_sesion_hace_post_con_csrf(app_tn):
    with por_serve(app_tn, DUENO) as c:
        c.get("/")
        csrf = app_tn.state.seguridad.sesion(c.cookies.get(COOKIE))["csrf"]
        assert c.post("/salir", headers={"x-csrf-token": csrf, "origin": f"https://{HOST}"}).status_code == 204
        # Sin CSRF, aunque la identidad sea buena, el POST no pasa.
        assert c.post("/salir", headers={"origin": f"https://{HOST}"}).status_code == 403


def test_entrar_sin_token_por_serve_lleva_a_inicio(app_tn):
    with por_serve(app_tn, DUENO) as c:
        r = c.get("/entrar", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/"


def test_otro_login_da_403_y_no_crea_sesion(app_tn):
    with por_serve(app_tn, "intruso@malo.com") as c:
        r = c.get("/")
        assert r.status_code == 403
        assert "set-cookie" not in r.headers
    assert app_tn.state.seguridad._sesiones == {}


def test_sin_login_por_serve_pide_token(app_tn):
    with por_serve(app_tn) as c:
        assert c.get("/").status_code == 401


@pytest.mark.parametrize("cab,ip", [
    ({"host": "127.0.0.1:8765", "x-forwarded-proto": "https"}, "127.0.0.1"),   # Host local
    ({"host": HOST}, "127.0.0.1"),                                               # sin https
    ({"host": HOST, "x-forwarded-proto": "https"}, "100.64.0.9"),                # no viene de 127.0.0.1
])
def test_cabecera_falsificada_fuera_de_serve_se_ignora(app_tn, cab, ip):
    with TestClient(app_tn, base_url="http://127.0.0.1:8765", client=(ip, 5),
                    headers={**cab, "tailscale-user-login": DUENO}) as c:
        r = c.get("/")
        assert r.status_code == 401
        assert "set-cookie" not in r.headers
    assert app_tn.state.seguridad._sesiones == {}


def test_sin_tailnet_configurada_la_cabecera_no_vale(cliente):
    r = cliente.get("/", headers={"tailscale-user-login": DUENO, "x-forwarded-proto": "https"})
    assert r.status_code == 401


def test_salir_no_se_muestra_entrando_por_tailscale(app_tn):
    with por_serve(app_tn, DUENO) as c:
        assert 'hx-post="/salir"' not in c.get("/").text


def test_salir_sigue_con_token(cliente, csrf):
    assert 'hx-post="/salir"' in cliente.get("/").text


# ------------------------------------------------------------ hallazgo 1: CSRF tras reiniciar la web
def test_cada_respuesta_con_sesion_lleva_su_csrf(cliente, csrf):
    assert cliente.get("/parada/estado").headers["x-nexo-csrf"] == csrf
    assert "x-nexo-csrf" not in cliente.get("/salud").headers        # publica: sin sesion, sin token


def test_tras_reiniciar_la_web_el_post_da_403_con_el_token_nuevo_y_luego_funciona(app_tn):
    with por_serve(app_tn, DUENO) as c:
        c.get("/")
        viejo = app_tn.state.seguridad.sesion(c.cookies.get(COOKIE))["csrf"]
        app_tn.state.seguridad._sesiones.clear()                    # "reinicio": sesiones perdidas
        # PARADA (u otro POST) pulsado con la pagina vieja: 403, pero ya trae sesion y token nuevos.
        r = c.post("/push/baja", json={"endpoint": "x"}, headers={"x-csrf-token": viejo})
        assert r.status_code == 403
        assert r.headers["x-nexo-sesion-nueva"] == "1"
        nuevo = r.headers["x-nexo-csrf"]
        assert nuevo != viejo
        assert nuevo == app_tn.state.seguridad.sesion(c.cookies.get(COOKIE))["csrf"]
        # Al volver a pulsar con el token nuevo pasa el CSRF (400 = llego a la ruta).
        assert c.post("/push/baja", json={"endpoint": "x"}, headers={"x-csrf-token": nuevo}).status_code == 400


def test_un_get_de_fondo_tras_reiniciar_entrega_el_token_de_la_sesion_nueva(app_tn):
    with por_serve(app_tn, DUENO) as c:
        c.get("/")
        app_tn.state.seguridad._sesiones.clear()
        r = c.get("/parada/estado")                                 # lo que pide nexo.js al reconciliar
        assert r.headers["x-nexo-sesion-nueva"] == "1"
        assert r.headers["x-nexo-csrf"] == app_tn.state.seguridad.sesion(c.cookies.get(COOKIE))["csrf"]


def test_js_actualiza_el_token_y_no_repite_la_accion():
    from interfaz.vistas import DIR
    js = (DIR / "estatico" / "nexo.js").read_text(encoding="utf-8")
    assert 'actualizarCsrf(cabecera(e.detail.xhr, "X-Nexo-CSRF"))' in js
    assert 'actualizarCsrf(r.headers.get("X-Nexo-CSRF"))' in js
    assert "vuelve a pulsar" in js


# ------------------------------------------------------------ hallazgo 5: sesiones acotadas
def test_las_sesiones_por_identidad_no_crecen_sin_limite(app_tn):
    from interfaz.seguridad import MAX_SESIONES
    seg = app_tn.state.seguridad
    primera = seg.crear_sesion()
    for _ in range(MAX_SESIONES + 30):
        with por_serve(app_tn, DUENO) as c:        # cliente nuevo cada vez: nunca trae cookie
            assert c.get("/parada/estado").status_code == 200
    assert len(seg._sesiones) == MAX_SESIONES
    assert seg.sesion(primera) is None               # se tiro la mas antigua
