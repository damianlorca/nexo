# -*- coding: utf-8 -*-
"""T273 pieza B: "quota hold": si la cuota se reabre pronto, esperar en vez de escalar o parar el turno.

Tests dados (los escribe Claude; el implementador SOLO cambia nucleo/cuota.py, anadiendo dos funciones; lo que ya
hay no cambia). Datos: los de cuota.json (`_leer()`): {proveedor: {modelo: {"cuando": t, "peticiones"|"tokens":
{"queda", "limite", "reset_s"}}}}. Contrato:
- `reabre_en(proveedor, ahora=None) -> float | None` (segundos):
    1. `margen(proveedor, ahora)` es None (sin datos)          -> None
    2. el proveedor esta enfriado (enfriamiento.enfriado)        -> None (no se sabe cuando vuelve)
    3. margen >= UMBRAL_PARADA                                   -> 0.0 (ya hay cuota)
    4. si no: para cada modelo con datos vigentes, su hora de reapertura es el MAXIMO, entre sus tipos agotados
       (queda/limite < UMBRAL_PARADA y ahora < cuando + reset), de cuando + reset - ahora, con
       reset = reset_s o CADUCA_SIN_RESET si reset_s es None. El proveedor reabre con el PRIMER modelo que reabra
       (MINIMO entre modelos). Redondeado a 1 decimal.
- `esperar(nombres, max_espera=180, ahora=None) -> float | None`:
    `seguir(nombres, ahora)` es (True, _) -> 0.0; si no, el minimo de reabre_en de los nombres que no son None;
    si ese minimo <= max_espera -> ese valor; si no, o si todos son None -> None (no esperar: parar como ahora).
"""
from __future__ import annotations

import json

import pytest

from nucleo import cuota, enfriamiento

T0 = 1_000_000.0


@pytest.fixture
def datos(tmp_path, monkeypatch):
    monkeypatch.setattr(cuota, "ALMACEN", tmp_path / "cuota.json")
    monkeypatch.setattr(enfriamiento, "enfriado", lambda p: False)

    def poner(d):
        (tmp_path / "cuota.json").write_text(json.dumps(d), encoding="utf-8")
    return poner


def _e(queda, limite=100, reset_s=60.0, cuando=T0, tipo="peticiones"):
    return {"cuando": cuando, tipo: {"queda": queda, "limite": limite, "reset_s": reset_s}}


def test_sin_datos(datos):
    datos({})
    assert cuota.reabre_en("groq", ahora=T0) is None


def test_con_cuota_es_cero(datos):
    datos({"groq": {"m": _e(50)}})
    assert cuota.reabre_en("groq", ahora=T0 + 10) == 0.0


def test_agotado_reabre_con_su_reset(datos):
    datos({"groq": {"m": _e(0, reset_s=90.0)}})
    assert cuota.reabre_en("groq", ahora=T0 + 30) == 60.0


def test_dos_tipos_agotados_manda_el_mas_tardio(datos):
    e = _e(0, reset_s=20.0)
    e["tokens"] = {"queda": 1, "limite": 1000, "reset_s": 120.0}
    datos({"groq": {"m": e}})
    assert cuota.reabre_en("groq", ahora=T0) == 120.0


def test_entre_modelos_el_primero_que_reabre(datos):
    datos({"groq": {"a": _e(0, reset_s=300.0), "b": _e(2, reset_s=45.5)}})
    assert cuota.reabre_en("groq", ahora=T0) == 45.5


def test_sin_reset_usa_caduca(datos):
    datos({"groq": {"m": _e(0, reset_s=None)}})
    assert cuota.reabre_en("groq", ahora=T0 + 600) == cuota.CADUCA_SIN_RESET - 600


def test_enfriado_es_none(datos, monkeypatch):
    datos({"groq": {"m": _e(0)}})
    monkeypatch.setattr(enfriamiento, "enfriado", lambda p: p == "groq")
    assert cuota.reabre_en("groq", ahora=T0) is None


def test_esperar(datos):
    datos({"groq": {"m": _e(0, reset_s=100.0)}, "nvidia": {"m": _e(0, reset_s=400.0)}})
    assert cuota.esperar(["groq", "nvidia"], ahora=T0) == 100.0
    assert cuota.esperar(["groq", "nvidia"], max_espera=99, ahora=T0) is None
    assert cuota.esperar(["nvidia"], ahora=T0) is None


def test_esperar_con_cuota_es_cero_y_sin_datos_none(datos):
    datos({"groq": {"m": _e(0, reset_s=100.0)}, "nvidia": {"m": _e(80)}})
    assert cuota.esperar(["groq", "nvidia"], ahora=T0) == 0.0
    datos({"groq": {"m": _e(0, reset_s=100.0)}})
    assert cuota.esperar(["groq", "openrouter"], ahora=T0) == 0.0   # openrouter sin datos: seguir() ya es True
