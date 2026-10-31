# -*- coding: utf-8 -*-
"""T157: failover robusto. Tabla tipo de error -> accion (nucleo/fallos.py) aplicada en todos los proveedores."""
from __future__ import annotations

import json

import httpx
import pytest

import proveedores as P
from nucleo import enfriamiento, fallos
from nucleo import modelos_estado as M


class Resp:
    def __init__(self, codigo, texto="OK", cuerpo="", cabeceras=None):
        self.status_code, self._t, self.text, self.headers = codigo, texto, cuerpo, cabeceras or {}

    def json(self):
        return {"choices": [{"message": {"content": self._t}}],
                "candidates": [{"content": {"parts": [{"text": self._t}]}}]}


# ---------------------------------------------------------------- la tabla
@pytest.mark.parametrize("args,tipo,accion", [
    (dict(codigo=200, texto="hola"), "ok", "devolver"),
    (dict(codigo=200, texto="  "), "vacia", "siguiente"),
    (dict(codigo=429), "ritmo", "siguiente"),
    (dict(codigo=429, cabeceras={"retry-after": "12"}), "ritmo", "repetir"),
    (dict(codigo=429, cabeceras={"retry-after": "3600"}), "ritmo", "siguiente"),
    (dict(codigo=429, cuerpo="Rate limit reached on tokens per day (TPD)"), "cuota", "siguiente"),
    (dict(codigo=429, cuerpo='{"error":{"status":"RESOURCE_EXHAUSTED"}}'), "cuota", "siguiente"),
    (dict(codigo=429, cuerpo="Rate limit exceeded: free-models-per-day"), "cuota", "siguiente"),
    (dict(codigo=401), "clave", "terminal"),
    (dict(codigo=403), "clave_403", "terminal"),
    (dict(codigo=400, cuerpo="API key not valid. Please pass a valid API key."), "clave", "terminal"),
    (dict(codigo=402), "sin_creditos", "terminal"),
    (dict(codigo=404), "retirado", "siguiente"),
    (dict(codigo=410), "retirado", "siguiente"),
    (dict(codigo=503), "saturado", "siguiente"),
    (dict(codigo=500), "saturado", "siguiente"),
    (dict(codigo=413), "peticion", "siguiente"),
    (dict(codigo=400, cuerpo="context length exceeded"), "peticion", "siguiente"),
    (dict(excepcion=httpx.ReadTimeout("x")), "timeout", "siguiente"),
    (dict(excepcion=httpx.ConnectError("x")), "red", "siguiente"),
])
def test_tabla(args, tipo, accion):
    c = fallos.clasificar(**args)
    assert (c.tipo, c.accion) == (tipo, accion)
    assert c.espera <= fallos.ESPERA_MAXIMA


def test_enfriamiento_final():
    C = fallos.clasificar
    assert fallos.enfriamiento_final([C(429, cuerpo="per day"), C(429, cuerpo="daily")]) == "cuota"
    assert fallos.enfriamiento_final([C(429), C(503)]) == "saturado"
    assert fallos.enfriamiento_final([C(429), C(404)]) is None      # hay un retirado: no es cosa de cuota
    assert fallos.enfriamiento_final([]) is None


def test_web():
    class Bloqueo(Exception):
        pass

    class LimiteUso(Exception):
        pass

    class ModoNoActivo(Exception):
        pass
    assert fallos.clasificar_web(Bloqueo("captcha")).tipo == "captcha"
    assert fallos.clasificar_web(Bloqueo("Inicia sesion para continuar")).tipo == "sesion"
    assert fallos.clasificar_web(LimiteUso("hasta las 18:00")).tipo == "limite_web"
    assert fallos.clasificar_web(ModoNoActivo("no hay Pro")).tipo == "fallo_web"
    assert fallos.clasificar_web(ModoNoActivo("Log in to ChatGPT")).tipo == "sesion"


# ---------------------------------------------------------------- la cascada en los proveedores
@pytest.fixture
def red(monkeypatch):
    for clase in (P.GroqProvider, P.NvidiaProvider, P.OpenRouterProvider, P.GeminiAPIProvider):
        monkeypatch.setattr(clase, "_clave", lambda self: "k-falsa")
    esperas = []
    monkeypatch.setattr(fallos.time, "sleep", lambda s: esperas.append(s))

    def instalar(por_modelo):
        llamadas = []

        def post(url, headers=None, json=None, timeout=None):
            m = (json or {}).get("model") or url.split("/models/")[-1].split(":")[0]
            llamadas.append(m)
            cola = por_modelo[m]
            v = cola.pop(0) if isinstance(cola, list) else cola
            if isinstance(v, Exception):
                raise v
            return v if isinstance(v, Resp) else Resp(v)
        monkeypatch.setattr(httpx, "post", post)
        return llamadas
    instalar.esperas = esperas
    return instalar


def _enfriado(nombre):
    d = json.loads(enfriamiento.ALMACEN.read_text(encoding="utf-8")) if enfriamiento.ALMACEN.exists() else {}
    return d.get(nombre, {}).get("tipo")


FABRICAS = {
    "groq": lambda ms: P.GroqProvider(modelos=ms, rondas=1),
    "nvidia": lambda ms: P.NvidiaProvider(modelos=ms),
    "openrouter": lambda ms: P.OpenRouterProvider(modelos=ms),
    "gemini_api": lambda ms: P.GeminiAPIProvider(modelos=ms, rondas=1),
}
MODELOS = {"groq": ("g1", "g2"), "nvidia": ("openai/gpt-oss-20b", "nvidia/nemotron-3-super-120b-a12b"),
           "openrouter": ("a/b:free", "c/d:free"), "gemini_api": ("gm1", "gm2")}


@pytest.mark.parametrize("prov", list(FABRICAS))
def test_retry_after_corto_repite_el_mismo_modelo_una_vez(red, prov):
    a, b = MODELOS[prov]
    ll = red({a: [Resp(429, cabeceras={"retry-after": "7"}), Resp(200, "hola")], b: 200})
    r = FABRICAS[prov]((a, b)).enviar("x")
    assert r.ok and r.texto == "hola" and ll == [a, a] and red.esperas == [7.0]


@pytest.mark.parametrize("prov", list(FABRICAS))
def test_clave_mala_bloquea_enfria_y_no_prueba_otro_modelo(red, prov):
    a, b = MODELOS[prov]
    ll = red({a: 401, b: 200})
    r = FABRICAS[prov]((a, b)).enviar("x")
    assert r.estado == "BLOCKED" and ll == [a] and _enfriado(prov) == "bloqueo"
    assert "k-falsa" not in r.detalle


@pytest.mark.parametrize("prov", list(FABRICAS))
def test_cuota_diaria_en_todos_enfria_cuota_y_ritmo_enfria_corto(red, prov):
    a, b = MODELOS[prov]
    red({a: Resp(429, cuerpo="limit per day"), b: Resp(429, cuerpo="quota exceeded")})
    assert FABRICAS[prov]((a, b)).enviar("x").estado == "ERROR" and _enfriado(prov) == "cuota"
    enfriamiento.limpiar(prov)
    red({a: 429, b: 503})
    assert FABRICAS[prov]((a, b)).enviar("x").estado == "ERROR" and _enfriado(prov) == "saturado"


@pytest.mark.parametrize("prov", list(FABRICAS))
def test_retirado_vacia_timeout_y_peticion_pasan_al_siguiente_sin_enfriar(red, prov):
    a, b = MODELOS[prov]
    for fallo in (410, Resp(200, "  "), httpx.ReadTimeout("x"), 413):
        red({a: [fallo], b: 200})
        assert FABRICAS[prov]((a, b)).enviar("x").ok, fallo
    assert _enfriado(prov) is None


def test_gemini_api_anota_retirados_como_los_demas(red):
    red({"gm1": 404, "gm2": 200})
    for _ in range(2):
        assert P.GeminiAPIProvider(modelos=("gm1", "gm2"), rondas=1).enviar("x").ok
    assert M.estado_de("gemini_api", "gm1") == M.RETIRADO


def test_la_espera_entre_rondas_nunca_pasa_de_60_s(red):
    red({"g1": [503, 200]})
    assert P.GroqProvider(modelos=("g1",), rondas=2, espera=300).enviar("x").ok
    assert red.esperas == [fallos.ESPERA_MAXIMA]


def test_web_con_sesion_caducada_enfria_1h_y_no_esta_disponible(monkeypatch):
    from extremidades import navegador
    monkeypatch.setattr(navegador, "activo", lambda: True)

    def preguntar(*a, **k):
        raise navegador.RespuestaNoVerificada("La pagina pide Log in para continuar")
    monkeypatch.setattr(navegador, "preguntar", preguntar)
    r = P.ChatGPTProvider().enviar("hola")
    assert r.estado == "NOT_AVAILABLE" and r.meta["fallo"] == "sesion"
    assert _enfriado("chatgpt") == "sesion" and enfriamiento.enfriado("chatgpt")


# ---------------------------------------------------------------- T1013: 403 suelto de Groq
def test_403_sin_cuota_es_transitorio_y_401_sigue_terminal():
    c = fallos.clasificar(403)
    assert (c.tipo, c.enfriar) == ("clave_403", "transitorio")
    assert fallos.clasificar(401).enfriar == "bloqueo"
    assert fallos.clasificar(403, cuerpo="Rate limit: tokens per day (TPD)").tipo == "cuota"
    assert enfriamiento.DURACION["transitorio"] == 30 * 60


def test_403_suelto_enfria_30_min_y_no_horas(red):
    a, b = MODELOS["groq"]
    red({a: 403, b: 200})
    assert FABRICAS["groq"]((a, b)).enviar("x").estado == "BLOCKED"
    e = json.loads(enfriamiento.ALMACEN.read_text(encoding="utf-8"))["groq"]
    assert e["tipo"] == "transitorio" and 25 * 60 < e["hasta"] - __import__("time").time() <= 30 * 60


def test_sondeo_tras_el_transitorio_con_otro_403_bloquea_horas(red):
    a, b = MODELOS["groq"]
    enfriamiento.enfriar("groq", "transitorio", "403", segundos=-5)      # ya caduco: la llamada de ahora sondea
    red({a: 403, b: 200})
    FABRICAS["groq"]((a, b)).enviar("x")
    assert _enfriado("groq") == "bloqueo"


def test_sondeo_que_va_bien_borra_el_transitorio(red):
    a, b = MODELOS["groq"]
    enfriamiento.enfriar("groq", "transitorio", "403", segundos=-5)
    red({a: 200, b: 200})
    assert FABRICAS["groq"]((a, b)).enviar("x").ok
    assert "groq" not in json.loads(enfriamiento.ALMACEN.read_text(encoding="utf-8"))
