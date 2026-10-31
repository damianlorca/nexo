# -*- coding: utf-8 -*-
"""Bloque 23 (29/10): un OK (R1 de veto o R2) ya 'usada' en una fusion que despues se deshizo (git revert) no cierra la
tarea. Caso real T844: la puerta fusiono con A0097 (c1fdef7), la salud la revirtio (7ecfc17), la rama reaplico el MISMO
diff (mismo sha) y riesgo._ultima devolvia A0097 'usada' -> piloto_serie la daba por terminada ("damian_usada").
Ahora se abre una solicitud NUEVA R2 (Damian vuelve a decidir; silencio = no; sin tribunal del guardian) y
piloto_serie no la marca final. Si la fusion sigue en principal, 'usada' sigue siendo final. Todo en tmp_path."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from nucleo import aprobaciones as ap
from nucleo import avisos, cierre_auto, piloto_serie, riesgo

T0 = datetime(2026, 10, 25, 13, 21, 24)
ASUNTO = "Fusiona impl/T844: T746 rehecha: fallback lexico de freno.pares_semanticos, tam"
DIFF = ("diff --git a/nucleo/freno.py b/nucleo/freno.py\n--- a/nucleo/freno.py\n+++ b/nucleo/freno.py\n"
        "@@ -1,1 +1,2 @@\n+UMBRAL_LEXICO = 0.5\n")
T844 = {"id": "T844", "titulo": "T746 rehecha: fallback lexico", "etiquetas": ["tests:dados"],
        "detalle": "DONDE: nucleo/freno.py"}


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "ALMACEN", tmp_path / "aprobaciones.json")
    monkeypatch.setattr(ap, "HISTORIAL", tmp_path / "aprobaciones_historial.jsonl")
    monkeypatch.setattr(ap, "CANDADO", tmp_path / ".candado.lock")
    monkeypatch.setattr(avisos, "CARPETA", tmp_path / "avisos")
    monkeypatch.setattr(riesgo, "TRIBUNAL_R1", False)


def _log(*asuntos):
    """Doble de git log --format=%s (el mas reciente primero)."""
    return lambda *a, **k: "\n".join(asuntos) + "\n"


def _fusionada_con_veto():
    f = riesgo.fusion(T844, DIFF, "R2", ahora=T0, puerta_ok=True)
    assert ap.ver(f["solicitud"])["nivel"] == "R1"
    ap.aprobar(f["solicitud"], ahora=T0 + timedelta(hours=1))
    s = ap.ver(f["solicitud"])
    ap.consumir(s["id"], s["accion"], s["detalle"], ahora=T0 + timedelta(hours=2))
    assert ap.ver(f["solicitud"])["estado"] == "usada"
    return f["solicitud"]


def test_fusion_deshecha_lee_los_reverts(monkeypatch):
    monkeypatch.setattr(cierre_auto, "_git", _log(f'Revert "{ASUNTO}"', ASUNTO))
    assert riesgo.fusion_deshecha("T844")
    monkeypatch.setattr(cierre_auto, "_git", _log(ASUNTO, f'Revert "{ASUNTO}"', ASUNTO))   # vuelta a fusionar
    assert not riesgo.fusion_deshecha("T844")
    monkeypatch.setattr(cierre_auto, "_git", _log(ASUNTO))
    assert not riesgo.fusion_deshecha("T844")
    monkeypatch.setattr(cierre_auto, "_git", _log())                                       # sin git o sin fusiones
    assert not riesgo.fusion_deshecha("T844")


def test_t844_ok_usado_y_fusion_revertida_abre_solicitud_nueva_r2(monkeypatch):
    usada = _fusionada_con_veto()
    monkeypatch.setattr(cierre_auto, "_git", _log(f'Revert "{ASUNTO}"', ASUNTO))
    g = riesgo.fusion(T844, DIFF, "R2", ahora=T0 + timedelta(days=1), puerta_ok=True)
    assert not g["puede"] and g["solicitud"] != usada and g["nivel_real"] == "R2"
    s = ap.ver(g["solicitud"])
    assert s["estado"] == "pendiente" and s["nivel"] == "R2" and s.get("tipo") != "veto"
    assert s["extra"]["fusion_deshecha"] is True and s["extra"]["puerta_ok"] is False   # el guardian no la aprueba
    # la siguiente pasada no abre otra: espera la decision de Damian
    h = riesgo.fusion(T844, DIFF, "R2", ahora=T0 + timedelta(days=1, hours=9), puerta_ok=True)
    assert not h["puede"] and h["solicitud"] == g["solicitud"]
    # silencio = no (7 dias)
    k = riesgo.fusion(T844, DIFF, "R2", ahora=T0 + timedelta(days=9), puerta_ok=True)
    assert not k["puede"] and "caducada" in k["motivo"]


def test_ok_de_damian_tras_el_revert_fusiona(monkeypatch):
    _fusionada_con_veto()
    monkeypatch.setattr(cierre_auto, "_git", _log(f'Revert "{ASUNTO}"', ASUNTO))
    g = riesgo.fusion(T844, DIFF, "R2", ahora=T0 + timedelta(days=1), puerta_ok=True)
    ap.aprobar(g["solicitud"], ahora=T0 + timedelta(days=1, hours=1))
    h = riesgo.fusion(T844, DIFF, "R2", ahora=T0 + timedelta(days=1, hours=2), puerta_ok=True)
    assert h["puede"] and h["solicitud"] == g["solicitud"]


def test_ok_usado_con_la_fusion_viva_sigue_siendo_final(monkeypatch):
    usada = _fusionada_con_veto()
    monkeypatch.setattr(cierre_auto, "_git", _log(ASUNTO))
    g = riesgo.fusion(T844, DIFF, "R2", ahora=T0 + timedelta(days=1), puerta_ok=True)
    assert not g["puede"] and g["solicitud"] == usada and "ya se uso" in g["motivo"]


def test_piloto_serie_no_da_por_terminada_la_usada_deshecha(monkeypatch):
    marcas = []
    monkeypatch.setattr(piloto_serie, "_marcar_cola", lambda tid, **k: marcas.append(k))
    monkeypatch.setattr(piloto_serie, "_solicitud_estado", lambda sid: "usada")
    monkeypatch.setattr(cierre_auto, "_git", _log(f'Revert "{ASUNTO}"', ASUNTO))
    assert piloto_serie._resolver_cola("T844", {"estado": "espera_ok", "solicitud": "A0097"}) == "espera"
    assert not any("final" in m for m in marcas)
    monkeypatch.setattr(cierre_auto, "_git", _log(ASUNTO))
    assert piloto_serie._resolver_cola("T844", {"estado": "espera_ok", "solicitud": "A0097"}) == "terminal"
    assert marcas[-1]["final"] == "damian_usada"
