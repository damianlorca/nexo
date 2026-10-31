# -*- coding: utf-8 -*-
"""T684: decision adaptativa segun la cuota restante (nucleo/cuota.py). Sin red: cabeceras de prueba."""
from __future__ import annotations

import httpx
import pytest

import proveedores as P
from nucleo import cuota, enfriamiento, fallos, trabajo

T0 = 1_800_000_000.0
GROQ = {"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "990",
        "x-ratelimit-reset-requests": "2m59.56s", "x-ratelimit-limit-tokens": "8000",
        "x-ratelimit-remaining-tokens": "400", "x-ratelimit-reset-tokens": "45s"}


@pytest.mark.parametrize("v,s", [("2m59.56s", 179.56), ("7.66s", 7.66), ("120ms", 0.12), ("1h2m", 3720.0),
                                 ("30", 30.0), ("nada", None), (None, None)])
def test_duraciones(v, s):
    r = cuota._segundos(v)
    assert (r is None and s is None) or abs(r - s) < 1e-6


def test_leer_cabeceras_groq_y_openrouter_y_sin_datos():
    g = cuota.leer_cabeceras(GROQ)
    assert g["peticiones"]["queda"] == 990 and g["tokens"]["limite"] == 8000 and g["tokens"]["reset_s"] == 45
    o = cuota.leer_cabeceras({"X-RateLimit-Limit": "20", "X-RateLimit-Remaining": "2"})
    assert o["peticiones"] == {"limite": 20, "queda": 2, "reset_s": None}
    assert cuota.leer_cabeceras({"content-type": "json"}) is None and cuota.leer_cabeceras(None) is None


def test_margen_es_el_minimo_de_peticiones_y_tokens_y_caduca_con_el_reset():
    cuota.registrar("groq", "m", GROQ, ahora=T0)
    assert cuota.margen("groq", ahora=T0 + 10) == pytest.approx(0.05)      # 400/8000 tokens manda
    assert cuota.margen("groq", ahora=T0 + 50) == pytest.approx(0.99)      # tokens recargados: quedan peticiones
    assert cuota.margen("groq", ahora=T0 + 200) is None                     # todo recargado: no se sabe


def test_sin_dato_es_unknown_y_sin_reset_caduca_en_una_hora():
    assert cuota.margen("gemini_api", ahora=T0) is None
    cuota.registrar("openrouter", "a:free", {"x-ratelimit-limit": "50", "x-ratelimit-remaining": "5"}, ahora=T0)
    assert cuota.margen("openrouter", ahora=T0 + 60) == pytest.approx(0.1)
    assert cuota.margen("openrouter", ahora=T0 + cuota.CADUCA_SIN_RESET + 1) is None


def test_el_proveedor_vale_lo_que_su_mejor_modelo_y_enfriado_es_cero():
    cuota.registrar("groq", "a", {"x-ratelimit-limit-requests": "100", "x-ratelimit-remaining-requests": "1"}, ahora=T0)
    cuota.registrar("groq", "b", {"x-ratelimit-limit-requests": "100", "x-ratelimit-remaining-requests": "60"}, ahora=T0)
    assert cuota.margen("groq", ahora=T0 + 1) == pytest.approx(0.6)
    enfriamiento.enfriar("groq", "cuota", "x")
    assert cuota.margen("groq") == 0.0


class _P:
    def __init__(self, nombre):
        self.nombre = nombre


def test_reordenar_manda_al_final_a_los_casi_agotados_y_deja_unknown_en_su_sitio():
    cuota.registrar("nvidia", "m", {"x-ratelimit-limit-requests": "40", "x-ratelimit-remaining-requests": "2"}, ahora=T0)
    cuota.registrar("groq", "m", {"x-ratelimit-limit-requests": "40", "x-ratelimit-remaining-requests": "30"}, ahora=T0)
    orden = cuota.reordenar([_P("chatgpt"), _P("nvidia"), _P("gemini_api"), _P("groq")], ahora=T0 + 1)
    assert [p.nombre for p in orden] == ["chatgpt", "gemini_api", "groq", "nvidia"]


def test_seguir_para_solo_si_todos_los_conocidos_estan_agotados():
    vacio = {"x-ratelimit-limit-requests": "100", "x-ratelimit-remaining-requests": "0"}
    cuota.registrar("groq", "m", vacio, ahora=T0)
    cuota.registrar("nvidia", "m", vacio, ahora=T0)
    assert cuota.seguir(["groq", "nvidia", "gemini_api"], ahora=T0 + 1) == (True, "")   # gemini: UNKNOWN, sigue
    sigue, motivo = cuota.seguir(["groq", "nvidia"], ahora=T0 + 1)
    assert not sigue and "groq 0%" in motivo
    assert cuota.seguir([]) == (False, "ningun proveedor disponible")


def test_la_cascada_anota_las_cabeceras(monkeypatch):
    class R:
        status_code, text, headers = 200, "", {"x-ratelimit-limit-requests": "10", "x-ratelimit-remaining-requests": "9"}

        def json(self):
            return {"choices": [{"message": {"content": "hola"}}]}
    monkeypatch.setattr(P.GroqProvider, "_clave", lambda self: "k")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: R())
    assert P.GroqProvider(modelos=("m",), rondas=1).enviar("x").ok
    assert cuota.margen("groq") == pytest.approx(0.9)


def test_el_ciclo_para_con_motivo_si_no_queda_cuota(monkeypatch):
    monkeypatch.setattr(trabajo, "_generadores", lambda cat: [_P("groq")])
    monkeypatch.setattr(cuota, "seguir", lambda nombres: (False, "cuota agotada: groq 0%"))
    llamadas = []
    monkeypatch.setattr(trabajo, "delegar", lambda *a, **k: llamadas.append(a))
    filas = trabajo.ciclo(lista=[{"id": "T9001", "titulo": "x", "_cat": "redaccion"}])
    assert filas == [{"tarea": "T9001", "cat": "redaccion", "titulo": "x", "parado_cuota": "cuota agotada: groq 0%"}]
    assert llamadas == []


def test_fallos_no_rompe_si_registrar_falla(monkeypatch):
    monkeypatch.setattr(cuota, "leer_cabeceras", lambda c: 1 / 0)
    cuota.registrar("groq", "m", GROQ)          # no lanza
    assert fallos.ESPERA_MAXIMA == 60.0


# ---- presupuesto diario por consumidor (T859 6b): el lote de reels no deja sin Gemini al tribunal
def test_tope_diario_es_la_fraccion_del_total():
    assert cuota.tope_diario(200, 0.20) == 40 and cuota.tope_diario(7, 0.2) == 1
    assert cuota.tope_diario(200, 0) == 0 and cuota.tope_diario(200, 5) == 200   # fraccion acotada a 0..1


def test_el_consumidor_se_para_en_su_tope_y_no_toca_al_otro():
    kw = dict(total_dia=10, fraccion=0.30)                       # 3 peticiones al dia para reels
    for _ in range(3):
        assert cuota.permite("gemini_api", "reels", **kw, ahora=T0)
        cuota.gastar("gemini_api", "reels", ahora=T0)
    assert not cuota.permite("gemini_api", "reels", **kw, ahora=T0)
    assert cuota.queda_hoy("gemini_api", "reels", **kw, ahora=T0) == 0
    assert cuota.permite("gemini_api", "tribunal", total_dia=10, fraccion=1.0, ahora=T0)   # su cuenta es aparte
    assert cuota.permite("gemini_api", "reels", **kw, ahora=T0 + 86400 * 2)                # otro dia, de cero


def test_presupuesto_no_deja_pasar_a_un_proveedor_enfriado(monkeypatch):
    monkeypatch.setattr(enfriamiento, "enfriado", lambda p: "cupo")
    assert not cuota.permite("gemini_api", "reels", total_dia=100, fraccion=0.5, ahora=T0)


def test_el_tribunal_conserva_su_reserva_de_gemini():
    """6c: los demas consumidores juntos no pasan de (1 - reserva) del total diario; el tribunal no cuenta ahi."""
    total = 100
    for _ in range(50):
        assert cuota.permite("gemini_api", "reels", total, 1.0, ahora=T0)
        cuota.gastar("gemini_api", "reels", ahora=T0)
    assert not cuota.permite("gemini_api", "reels", total, 1.0, ahora=T0)        # 50 % = tope de los demas
    assert not cuota.permite("gemini_api", "modelos", total, 1.0, ahora=T0)
    assert cuota.permite("gemini_api", "tribunal", total, 1.0, ahora=T0)         # el tribunal sigue teniendo la suya
    assert cuota.gastado_otros_hoy("gemini_api", ahora=T0) == 50
