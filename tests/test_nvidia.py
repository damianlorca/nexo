# -*- coding: utf-8 -*-
"""T227: proveedor NVIDIA build.nvidia.com (OpenAI-compatible, solo modelos gratuitos). Sin red ni clave real."""
from __future__ import annotations

import json

import httpx
import pytest

import proveedores
from nucleo import auditor, enfriamiento, trabajo, uso_proveedores

CLAVE = "nvapi-FALSA-de-test"


class Resp:
    def __init__(self, code, payload=None):
        self.status_code, self._p = code, payload or {}

    def json(self):
        return self._p


@pytest.fixture
def nv(tmp_path, monkeypatch):
    monkeypatch.setattr(enfriamiento, "ALMACEN", tmp_path / "enfriamiento.json")
    monkeypatch.setattr(uso_proveedores, "REGISTRO", tmp_path / "uso.jsonl")
    monkeypatch.setattr(proveedores.NvidiaProvider, "_clave", lambda self: CLAVE)
    llamadas = []

    def instalar(*respuestas):
        cola = list(respuestas)

        def post(url, headers=None, json=None, timeout=None):
            llamadas.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
            r = cola.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        monkeypatch.setattr(httpx, "post", post)
        return llamadas
    return instalar


def _ok(texto="revision"):
    return Resp(200, {"choices": [{"message": {"content": texto}}]})


def test_200_devuelve_texto_con_la_clave_en_la_cabecera(nv):
    ll = nv(_ok("hola"))
    r = proveedores.NvidiaProvider(modelos=("openai/gpt-oss-20b",)).enviar("prueba")
    assert r.ok and r.texto == "hola" and r.meta["modelo"] == "openai/gpt-oss-20b"
    assert ll[0]["url"] == proveedores.NvidiaProvider.URL and CLAVE not in ll[0]["url"]
    assert ll[0]["headers"]["Authorization"] == f"Bearer {CLAVE}"
    assert ll[0]["timeout"] == 120 and ll[0]["json"]["model"] == "openai/gpt-oss-20b"


def test_modelos_por_defecto_vienen_de_config(monkeypatch):
    """La lista de modelos no es secreta, vive en config.toml (no en secretos.toml)."""
    from nucleo import config as config_mod

    def falso_valor(ruta, defecto=None):
        if ruta == "nvidia.modelos":
            return ["openai/gpt-oss-20b", "nvidia/nemotron-3-super-120b-a12b"]
        return defecto
    monkeypatch.setattr(config_mod, "valor", falso_valor)
    p = proveedores.NvidiaProvider()
    assert p.modelos == ("openai/gpt-oss-20b", "nvidia/nemotron-3-super-120b-a12b")


def test_config_toml_trae_los_modelos_aprobados():
    """24/10 (coordinador, registros/probar_nvidia_1024.txt): ultra el primero y solo los que responden con "Free
    Endpoint"; fuera super-120b (404) y gpt-oss-20b (sin respuesta). Damian 04/10: fuera mistral-nemotron (HTTP 410)
    y glm-5.3-flash (sin respuesta)."""
    from nucleo import config as config_mod
    config_mod.config.cache_clear()
    try:
        modelos = config_mod.valor("nvidia.modelos", [])
        assert modelos[0] == "nvidia/nemotron-3-ultra-550b-a55b"
        assert not {"nvidia/nemotron-3-super-120b-a12b", "openai/gpt-oss-20b"} & set(modelos)
        assert not {"mistralai/mistral-nemotron", "z-ai/glm-5.3-flash"} & set(modelos)
        assert all(m in proveedores.MODELOS_NVIDIA_GRATIS for m in modelos)
    finally:
        config_mod.config.cache_clear()


def test_lista_blanca_de_otra_familia_que_gpt_oss_y_sin_retirados():
    for m in ("nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3-ultra-550b-a55b"):
        assert m in proveedores.MODELOS_NVIDIA_GRATIS, m
    for m in ("mistralai/mistral-nemotron", "z-ai/glm-5.3-flash"):       # 04/10: retirado / sin respuesta
        assert m not in proveedores.MODELOS_NVIDIA_GRATIS, m


def test_lista_blanca_solo_modelos_gratuitos():
    p = proveedores.NvidiaProvider(modelos=("openai/gpt-oss-20b", "nvidia/modelo-enterprise-de-pago"))
    assert p.modelos == ("openai/gpt-oss-20b",) and p.rechazados == ("nvidia/modelo-enterprise-de-pago",)
    assert set(p.modelos) <= set(proveedores.MODELOS_NVIDIA_GRATIS)


def test_sin_modelos_de_la_lista_no_esta_disponible_ni_llama(nv):
    ll = nv()
    p = proveedores.NvidiaProvider(modelos=("de/pago",))
    assert not p.disponible() and "lista blanca" in p.estado()["motivo"]
    assert p.enviar("x").estado == "NOT_AVAILABLE" and ll == []


def test_429_enfria_poco_y_deja_de_estar_disponible(nv):
    nv(Resp(429))
    p = proveedores.NvidiaProvider(modelos=("openai/gpt-oss-20b",))
    r = p.enviar("x")
    assert r.estado == "ERROR" and "429" in r.detalle
    e = json.loads(enfriamiento.ALMACEN.read_text(encoding="utf-8"))["nvidia"]
    assert e["tipo"] == "saturado" and not p.disponible()


def test_402_sin_creditos_enfria_largo_y_no_prueba_otro_modelo(nv):
    ll = nv(Resp(402), _ok())
    r = proveedores.NvidiaProvider(modelos=proveedores.MODELOS_NVIDIA_GRATIS).enviar("x")
    assert r.estado == "ERROR" and len(ll) == 1
    assert json.loads(enfriamiento.ALMACEN.read_text(encoding="utf-8"))["nvidia"]["tipo"] == "bloqueo"


def test_401_bloquea_sin_insistir(nv):
    ll = nv(Resp(401), _ok())
    assert proveedores.NvidiaProvider(modelos=proveedores.MODELOS_NVIDIA_GRATIS).enviar("x").estado == "BLOCKED"
    assert len(ll) == 1


def test_403_bloquea_sin_insistir(nv):
    ll = nv(Resp(403), _ok())
    assert proveedores.NvidiaProvider(modelos=proveedores.MODELOS_NVIDIA_GRATIS).enviar("x").estado == "BLOCKED"
    assert len(ll) == 1


def test_404_prueba_el_siguiente_modelo_en_vez_de_bloquear(nv):
    """T275: un modelo puede desaparecer del catalogo (400/404) sin que la clave este mal."""
    ll = nv(Resp(404), _ok("hola"))
    r = proveedores.NvidiaProvider(modelos=proveedores.MODELOS_NVIDIA_GRATIS).enviar("x")
    assert r.ok and r.texto == "hola" and len(ll) == 2


def test_400_prueba_el_siguiente_modelo_en_vez_de_bloquear(nv):
    ll = nv(Resp(400), _ok("hola"))
    r = proveedores.NvidiaProvider(modelos=proveedores.MODELOS_NVIDIA_GRATIS).enviar("x")
    assert r.ok and r.texto == "hola" and len(ll) == 2


def test_timeout_no_filtra_la_clave(nv):
    nv(httpx.ReadTimeout(f"timeout con Bearer {CLAVE}"))
    r = proveedores.NvidiaProvider(modelos=("openai/gpt-oss-20b",)).enviar("x")
    assert r.estado == "ERROR" and "ReadTimeout" in r.detalle and CLAVE not in r.detalle


def test_cada_envio_queda_en_uso_proveedores(nv):
    nv(_ok("abc"))
    proveedores.NvidiaProvider(modelos=("openai/gpt-oss-20b",)).enviar("prueba")
    fila = json.loads(uso_proveedores.REGISTRO.read_text(encoding="utf-8").splitlines()[-1])
    assert fila["proveedor"] == "nvidia" and fila["estado"] == "OK" and fila["salida"] == 3
    assert CLAVE not in uso_proveedores.REGISTRO.read_text(encoding="utf-8")


def test_es_revisor_independiente_de_chatgpt_pero_no_de_groq(monkeypatch):
    monkeypatch.setattr(trabajo, "_web", lambda: False)
    monkeypatch.setattr(proveedores.NvidiaProvider, "disponible", lambda self: True)
    monkeypatch.setattr(proveedores.GeminiAPIProvider, "disponible", lambda self: True)
    monkeypatch.setattr(proveedores.GroqProvider, "disponible", lambda self: True)
    assert [r.nombre for r in trabajo._revisores("chatgpt")][0] == "nvidia"      # antes que las API de respaldo
    assert "nvidia" not in [r.nombre for r in trabajo._revisores("groq")]         # mismos gpt-oss que Groq
    assert auditor.familia("nvidia") == auditor.familia("groq") != auditor.familia("chatgpt")
