# -*- coding: utf-8 -*-
"""Hito movil, incremento 1: host/origen de la tailnet, cookie Secure por Serve y aviso del vigia."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from interfaz import tailnet
from interfaz.app import crear_app
from interfaz.config import Ajustes
from interfaz.seguridad import COOKIE
from interfaz.vigia import PASADAS_SERVE, SANA, Vigia

HOST = "pc.ejemplo.ts.net"
SERVE = {"host": HOST, "x-forwarded-proto": "https"}


@pytest.fixture
def ajustes_tn(tmp_path):
    return Ajustes(token_fichero=tmp_path / "t.txt", vigilar=False, push_carpeta=tmp_path / "push", tailnet_host=HOST, tailnet_dueno="yo@x.com")


@pytest.fixture
def app_tn(ajustes_tn):
    return crear_app(ajustes_tn)


def cliente_de(app, ip="127.0.0.1", base="http://127.0.0.1:8765"):
    return TestClient(app, base_url=base, client=(ip, 50000))


# ------------------------------------------------------------ lectura de Tailscale
ESTADO = {"BackendState": "Running", "CertDomains": ["pc.ejemplo.ts.net"],
          "Self": {"DNSName": "PC.ejemplo.ts.net.", "UserID": 7}, "User": {"7": {"LoginName": "yo@x.com"}}}


def test_lee_host_y_dueno_del_status():
    assert tailnet.leer_estado(ESTADO) == {"host": HOST, "dueno": "yo@x.com"}


@pytest.mark.parametrize("cambio", [{"BackendState": "Stopped"}, {"CertDomains": []}, {"CertDomains": None}])
def test_sin_tailscale_en_marcha_o_sin_https_no_hay_tailnet(cambio):
    assert tailnet.leer_estado({**ESTADO, **cambio}) is None
    assert tailnet.leer_estado(None) is None


def test_lee_serve_activo_y_funnel():
    web = {"Web": {f"{HOST}:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8765"}}}}}
    assert tailnet.leer_serve(web, HOST, 8765) == {"activo": True, "funnel": False}
    assert tailnet.leer_serve(web, HOST, 9999)["activo"] is False
    assert tailnet.leer_serve({}, HOST, 8765) == {"activo": False, "funnel": False}
    assert tailnet.leer_serve({**web, "AllowFunnel": {f"{HOST}:443": True}}, HOST, 8765)["funnel"] is True


def test_produccion_no_pregunta_a_tailscale_al_importar_y_respeta_la_variable(monkeypatch):
    """Hallazgo 9: Ajustes.produccion() corre al importar interfaz.app (tests incluidos): nada de subprocess."""
    def prohibido():
        raise AssertionError("no debe llamar a tailscale")
    monkeypatch.setattr(tailnet, "estado", prohibido)
    monkeypatch.delenv("NEXO_TAILNET_DUENO", raising=False)
    a = Ajustes.produccion()
    assert a.tailnet_auto and (a.tailnet_host, a.tailnet_dueno) == (None, None)
    monkeypatch.setenv("NEXO_TAILNET_DUENO", "otro@x.com")
    assert Ajustes.produccion().tailnet_dueno == "otro@x.com"


def test_la_primera_pregunta_a_tailscale_es_nada_mas_arrancar(monkeypatch):
    import asyncio
    from interfaz import app as modulo_app
    monkeypatch.delenv("NEXO_TAILNET_DUENO", raising=False)
    monkeypatch.setattr(tailnet, "estado", lambda: {"host": HOST, "dueno": "yo@x.com"})
    a = Ajustes.produccion()

    async def dormir(s):
        raise asyncio.CancelledError   # parar en la primera espera: ya tiene que haber preguntado

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(modulo_app.refrescar_tailnet(a, dormir=dormir))
    assert (a.tailnet_host, a.tailnet_dueno) == (HOST, "yo@x.com")


# ------------------------------------------------------------ Host / Origin
def test_sin_tailnet_el_host_de_la_tailnet_se_rechaza(cliente):
    assert cliente.get("/salud", headers={"host": HOST}).status_code == 400


def test_con_tailnet_acepta_su_host_y_sigue_aceptando_el_local(app_tn):
    with cliente_de(app_tn) as c:
        assert c.get("/salud", headers=SERVE).status_code == 200
        assert c.get("/salud", headers={"host": f"{HOST}:443"}).status_code == 200
        assert c.get("/salud").status_code == 200
        assert c.get("/salud", headers={"host": "otro.ts.net"}).status_code == 400


def test_origen_https_de_la_tailnet_vale_y_http_no(app_tn):
    with cliente_de(app_tn) as c:
        c.get("/entrar", params={"t": app_tn.state.seguridad.token})
        csrf = app_tn.state.seguridad.sesion(c.cookies.get(COOKIE))["csrf"]
        ok = c.post("/salir", headers={"x-csrf-token": csrf, "origin": f"https://{HOST}"})
        assert ok.status_code == 204
        c.get("/entrar", params={"t": app_tn.state.seguridad.token})
        csrf = app_tn.state.seguridad.sesion(c.cookies.get(COOKIE))["csrf"]
        malo = c.post("/salir", headers={"x-csrf-token": csrf, "origin": f"http://{HOST}"})
        assert malo.status_code == 403


# ------------------------------------------------------------ cookie Secure
def test_cookie_secure_solo_por_serve(app_tn):
    token = app_tn.state.seguridad.token
    with cliente_de(app_tn) as c:
        local = c.get("/entrar", params={"t": token})
        assert "secure" not in local.headers["set-cookie"].lower()
    with cliente_de(app_tn) as c:
        por_serve = c.get("/entrar", params={"t": token}, headers=SERVE)
        assert "secure" in por_serve.headers["set-cookie"].lower()
    with cliente_de(app_tn, ip="100.64.0.9") as c:   # misma cabecera pero no viene de 127.0.0.1
        otro = c.get("/entrar", params={"t": token}, headers=SERVE)
        assert "secure" not in otro.headers["set-cookie"].lower()


def test_cookie_secure_con_proxy_headers_de_uvicorn(app_tn):
    """Como queda el scope tras el ProxyHeadersMiddleware de uvicorn: client = IP del movil, scheme https."""
    token = app_tn.state.seguridad.token
    with cliente_de(app_tn, ip="100.79.7.24", base=f"https://{HOST}") as c:
        r = c.get("/entrar", params={"t": token})
        assert "secure" in r.headers["set-cookie"].lower()
    with cliente_de(app_tn, ip="100.79.7.24", base=f"http://{HOST}") as c:   # ni https ni 127.0.0.1
        r = c.get("/entrar", params={"t": token})
        assert "secure" not in r.headers["set-cookie"].lower()


# ------------------------------------------------------------ vigia
def _vigia(aviso, log):
    return Vigia(8799, sondear=lambda p: SANA, lanzar=lambda p: 0, matar=lambda: True,
                 detenida=lambda: False, dormir=lambda s: None,
                 log=lambda n, m: log.append((n, m)), serve=lambda p: aviso[0])


def test_vigia_avisa_del_serve_solo_al_cambiar_y_cada_n_pasadas():
    log, aviso = [], [("warning", "falta serve")]
    v = _vigia(aviso, log)
    v.paso()
    assert ("warning", "falta serve") in log
    for _ in range(PASADAS_SERVE * 2):
        v.paso()
    assert log.count(("warning", "falta serve")) == 1
    aviso[0] = ("error", "funnel")
    for _ in range(PASADAS_SERVE):
        v.paso()
    assert ("error", "funnel") in log


def test_vigia_sobrevive_a_un_error_de_tailscale():
    log = []
    v = Vigia(8799, sondear=lambda p: SANA, lanzar=lambda p: 0, matar=lambda: True, detenida=lambda: False,
              dormir=lambda s: None, log=lambda n, m: log.append((n, m)), serve=lambda p: 1 / 0)
    assert v.paso() == "sana"
    assert any("no se pudo mirar tailscale serve" in m for _, m in log)


# ------------------------------------------------------------ refresco de la tailnet (fallo del 26/09)
def test_aplicar_tailnet_completa_y_no_borra_lo_que_ya_sabia(monkeypatch):
    monkeypatch.delenv("NEXO_TAILNET_DUENO", raising=False)
    a = Ajustes(tailnet_host=HOST)                       # arranco con host pero sin dueno
    assert a.aplicar_tailnet({"host": HOST, "dueno": "yo@x.com"}) is True
    assert a.tailnet_dueno == "yo@x.com"
    assert a.aplicar_tailnet(None) is False              # un fallo puntual de tailscale no borra nada
    assert (a.tailnet_host, a.tailnet_dueno) == (HOST, "yo@x.com")


def test_refresco_recupera_el_dueno_si_al_arrancar_no_estaba(monkeypatch):
    import asyncio
    from interfaz import app as modulo_app
    monkeypatch.delenv("NEXO_TAILNET_DUENO", raising=False)
    respuestas = iter([{"host": HOST, "dueno": None}, {"host": HOST, "dueno": "yo@x.com"}])
    monkeypatch.setattr(tailnet, "estado", lambda: next(respuestas))
    a = Ajustes.produccion()
    assert a.tailnet_auto and a.tailnet_dueno is None
    esperas = []

    async def dormir(s):
        esperas.append(s)
        if len(esperas) > 1:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(modulo_app.refrescar_tailnet(a, dormir=dormir))
    assert a.tailnet_dueno == "yo@x.com"
    assert esperas == [modulo_app.REFRESCO_INCOMPLETO, modulo_app.REFRESCO_COMPLETO]
