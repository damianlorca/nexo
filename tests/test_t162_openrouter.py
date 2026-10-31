# -*- coding: utf-8 -*-
"""T162 (Damian 04/10): OpenRouterProvider llama SOLO a modelos cuyo id termina en ':free' (la cuenta tiene limite de
0 USD): cualquier otro falla cerrado y no se llama. La clave nunca sale en resultados ni detalles. Sin red."""
from __future__ import annotations

import httpx
import pytest

import proveedores as P
from nucleo import modelos_estado as M

CLAVE = "sk-FALSOXXXXXXXXXXXXXXXXXXXX"


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "ESTADO", tmp_path / "modelos_estado.json")
    monkeypatch.setattr(M, "CANDADO", tmp_path / ".candado_modelos")
    monkeypatch.setattr(P.OpenRouterProvider, "_clave", lambda self: CLAVE)
    monkeypatch.setattr("nucleo.enfriamiento.enfriado", lambda nombre: None)


class Resp:
    def __init__(self, codigo, texto="OK"):
        self.status_code, self._t = codigo, texto

    def json(self):
        return {"choices": [{"message": {"content": self._t}}]}


def _http(monkeypatch, por_modelo=None):
    llamados = []

    def post(url, headers=None, json=None, timeout=None):
        llamados.append((url, json["model"], headers))
        v = (por_modelo or {}).get(json["model"], 200)
        if v == "timeout":
            raise httpx.ReadTimeout("x")
        return Resp(v)

    monkeypatch.setattr(httpx, "post", post)
    return llamados


def test_es_modelo_free_exige_el_sufijo_exacto():
    assert P.es_modelo_free("thinkingmachines/inkling:free")
    for malo in ("openai/gpt-4o", "x/y:free-extended", "x/y:free ", ":free", "", None, "x/y:paid", "x/y:FREE"):
        assert not P.es_modelo_free(malo), malo


def test_la_lista_por_defecto_es_toda_free():
    assert P.MODELOS_OPENROUTER_FREE and all(P.es_modelo_free(m) for m in P.MODELOS_OPENROUTER_FREE)


def test_un_modelo_que_no_es_free_se_rechaza_y_nunca_se_llama(monkeypatch):
    llamados = _http(monkeypatch)
    p = P.OpenRouterProvider(modelos=("openai/gpt-4o", "meta-llama/llama-4:paid", "thinkingmachines/inkling:free"))
    assert p.modelos == ("thinkingmachines/inkling:free",)
    assert p.rechazados == ("openai/gpt-4o", "meta-llama/llama-4:paid")
    assert p.enviar("hola").ok
    assert [m for _, m, _ in llamados] == ["thinkingmachines/inkling:free"]


def test_si_ninguno_es_free_no_esta_disponible_ni_llama(monkeypatch):
    llamados = _http(monkeypatch)
    p = P.OpenRouterProvider(modelos=("openai/gpt-4o",))
    assert not p.disponible() and "fail-closed" in p.estado()["motivo"]
    assert p.enviar("x").estado == "NOT_AVAILABLE" and llamados == []


def test_segunda_barrera_aunque_alguien_toque_la_lista_despues(monkeypatch):
    llamados = _http(monkeypatch)
    p = P.OpenRouterProvider(modelos=("a/b:free",))
    p.modelos = ("openai/gpt-4o",)                       # alguien la modifica tras crear el objeto
    r = p.enviar("x")
    assert r.estado == "BLOCKED" and "no es :free" in r.detalle and llamados == []


def test_la_lista_de_secretos_tambien_se_filtra(monkeypatch):
    monkeypatch.setattr("nucleo.config.valor", lambda clave, defecto=None: ["z/y:free", "caro/modelo"]
                        if clave == "openrouter.modelos" else defecto)
    assert P.OpenRouterProvider().modelos == ("z/y:free",)


def test_la_clave_va_en_la_cabecera_y_nunca_en_resultados(monkeypatch):
    llamados = _http(monkeypatch, {"a/b:free": 429, "c/d:free": 401})
    r = P.OpenRouterProvider(modelos=("a/b:free", "c/d:free")).enviar("x")
    assert r.estado == "BLOCKED"                                       # 401: clave mal, no insistir
    assert CLAVE not in repr(r) and CLAVE not in r.detalle
    url, _, cab = llamados[0]
    assert CLAVE not in url and cab["Authorization"] == f"Bearer {CLAVE}"


def test_429_enfria_y_404_dos_veces_lo_retira(monkeypatch):
    llamados = _http(monkeypatch, {"a/b:free": 404})
    enfriados = []
    monkeypatch.setattr("nucleo.enfriamiento.enfriar", lambda *a, **k: enfriados.append(a))
    for _ in range(2):
        assert P.OpenRouterProvider(modelos=("a/b:free", "c/d:free")).enviar("x").ok       # salta al siguiente
    assert M.estado_de("openrouter", "a/b:free") == M.RETIRADO
    llamados.clear()
    P.OpenRouterProvider(modelos=("a/b:free", "c/d:free")).enviar("x")
    assert [m for _, m, _ in llamados] == ["c/d:free"]
    _http(monkeypatch, {"c/d:free": 429})
    assert P.OpenRouterProvider(modelos=("c/d:free",)).enviar("x").estado == "ERROR" and enfriados

