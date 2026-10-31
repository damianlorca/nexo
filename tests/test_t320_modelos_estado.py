# -*- coding: utf-8 -*-
"""T320 (Damian 04/10): modelos retirados o sin servicio se detectan, se avisa una vez y salen de uso sin tocar el
codigo. Casos reales del primer uso del tribunal: NVIDIA mistral-nemotron HTTP 410, Groq qwen3-32b HTTP 404 (bloqueaba
toda la llamada) y glm-5.3-flash sin respuesta. Sin red: httpx va con doble."""
from __future__ import annotations

import json

import httpx
import pytest

import proveedores as P
from nucleo import avisos, modelos_estado as M


@pytest.fixture(autouse=True)
def estado_aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "ESTADO", tmp_path / "modelos_estado.json")
    monkeypatch.setattr(M, "CANDADO", tmp_path / ".candado_modelos")
    monkeypatch.setattr(P.GroqProvider, "_clave", lambda self: "gsk_falsa")
    monkeypatch.setattr(P.NvidiaProvider, "_clave", lambda self: "nvapi-falsa")
    monkeypatch.setattr("nucleo.enfriamiento.enfriado", lambda nombre: None)


def _avisos():
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(avisos.CARPETA.glob("aviso_*.json"))]


class Resp:
    def __init__(self, codigo, texto="OK"):
        self.status_code = codigo
        self._t = texto

    def json(self):
        return {"choices": [{"message": {"content": self._t}}]}


def _http(monkeypatch, por_modelo):
    """por_modelo: {modelo: codigo | 'timeout'}; devuelve la lista de modelos llamados."""
    llamados = []

    def post(url, headers=None, json=None, timeout=None):
        m = json["model"]
        llamados.append(m)
        v = por_modelo.get(m, 200)
        if v == "timeout":
            raise httpx.ReadTimeout("x")
        return Resp(v)

    monkeypatch.setattr(httpx, "post", post)
    return llamados


# ------------------------------------------------------------------ registro
def test_un_solo_404_no_basta_y_dos_seguidos_lo_retiran_con_aviso_unico():
    assert M.anotar("groq", "m1", 404) == M.VIVO
    assert M.anotar("groq", "m1", 404) == M.RETIRADO
    assert M.anotar("groq", "m1", 404) == M.RETIRADO
    (aviso,) = _avisos()
    assert "RETIRADO" in aviso["titulo"] and "groq/m1" in aviso["cuerpo"] and "HTTP 404" in aviso["cuerpo"]
    assert M.fuera_de_uso("groq", "m1") and M.en_uso("groq", ("m1", "m2")) == ("m2",)


def test_un_ok_entre_medias_rompe_la_racha_y_rehabilita():
    M.anotar("nvidia", "m", 410)
    M.anotar("nvidia", "m", "ok")
    assert M.anotar("nvidia", "m", 410) == M.VIVO
    M.anotar("nvidia", "m", 410)
    assert M.estado_de("nvidia", "m") == M.RETIRADO
    assert M.anotar("nvidia", "m", "ok") == M.VIVO and not M.fuera_de_uso("nvidia", "m")


def test_tres_timeouts_seguidos_son_sin_servicio_y_otros_errores_no_cuentan():
    M.anotar("nvidia", "glm", "timeout")
    M.anotar("nvidia", "glm", 429)          # un 429 no dice nada del modelo: no corta ni suma
    M.anotar("nvidia", "glm", "timeout")
    assert M.estado_de("nvidia", "glm") == M.VIVO
    assert M.anotar("nvidia", "glm", "timeout") == M.SIN_SERVICIO
    assert "SIN SERVICIO" in _avisos()[0]["titulo"]


def test_senales_de_distinto_tipo_cortan_la_racha():
    M.anotar("groq", "m", 404)
    M.anotar("groq", "m", "timeout")
    assert M.anotar("groq", "m", 404) == M.VIVO


def test_rehabilitar_a_mano():
    M.anotar("groq", "m", 404), M.anotar("groq", "m", 404)
    assert M.rehabilitar("groq", "m") and M.estado_de("groq", "m") == M.VIVO
    assert not M.rehabilitar("groq", "no-existe")


# ------------------------------------------------------------------ proveedores
def test_groq_un_modelo_retirado_ya_no_bloquea_toda_la_llamada(monkeypatch):
    llamados = _http(monkeypatch, {"viejo": 404})
    g = P.GroqProvider(modelos=("viejo", "nuevo"), rondas=1)
    r = g.enviar("hola")
    assert r.ok and g.ultimo_modelo == "nuevo" and llamados == ["viejo", "nuevo"]   # antes: BLOCKED a la primera
    llamados.clear()
    assert P.GroqProvider(modelos=("viejo", "nuevo"), rondas=1).enviar("hola").ok
    assert llamados == ["viejo", "nuevo"]                                            # 2.o 404: ya retirado
    llamados.clear()
    assert P.GroqProvider(modelos=("viejo", "nuevo"), rondas=1).enviar("hola").ok
    assert llamados == ["nuevo"]                                                     # y desde ahora ni se llama


def test_groq_clave_mala_sigue_bloqueando(monkeypatch):
    _http(monkeypatch, {"a": 401})
    assert P.GroqProvider(modelos=("a", "b"), rondas=1).enviar("x").estado == "BLOCKED"


def test_nvidia_410_dos_veces_lo_retira_y_si_no_quedan_modelos_no_esta_disponible(monkeypatch):
    llamados = _http(monkeypatch, {"nvidia/nemotron-3-super-120b-a12b": 410})
    n = lambda: P.NvidiaProvider(modelos=("nvidia/nemotron-3-super-120b-a12b",), rondas=1)
    assert n().enviar("x").estado == "ERROR" and n().enviar("x").estado == "ERROR"
    assert not n().disponible()
    assert n().enviar("x").estado == "NOT_AVAILABLE" and len(llamados) == 2


def test_nvidia_timeouts_repetidos_marcan_sin_servicio(monkeypatch):
    _http(monkeypatch, {"openai/gpt-oss-20b": "timeout"})
    for _ in range(3):
        P.NvidiaProvider(modelos=("openai/gpt-oss-20b",), rondas=1).enviar("x")
    assert M.estado_de("nvidia", "openai/gpt-oss-20b") == M.SIN_SERVICIO


def test_sondear_rehabilita_un_modelo_que_vuelve(monkeypatch):
    modelo = P.MODELOS_GROQ[0]
    M.anotar("groq", modelo, 404), M.anotar("groq", modelo, 404)
    assert M.fuera_de_uso("groq", modelo)
    _http(monkeypatch, {})                                   # todos responden 200
    res = M.sondear(pausa=0)
    fila = next(f for f in res if f["modelo"] == f"groq/{modelo}")
    assert fila["antes"] == M.RETIRADO and fila["despues"] == M.VIVO and fila["resultado"] == "OK"
    assert len(res) == len(P.MODELOS_GROQ) + len(P.MODELOS_NVIDIA_GRATIS) + len(P.MODELOS_OPENROUTER_FREE)


def test_el_tribunal_salta_un_candidato_retirado(monkeypatch):
    from nucleo import tribunal
    c = tribunal.CANDIDATOS["groq:gpt-oss-120b"]
    assert tribunal._disponible(c)
    M.anotar("groq", c.modelo, 404), M.anotar("groq", c.modelo, 404)
    assert not tribunal._disponible(c)
