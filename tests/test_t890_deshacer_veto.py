# -*- coding: utf-8 -*-
"""T890 (3): 'Deshacer veto'. Un R1 vetado hace menos de 7 dias, con su tarea sin cerrar, vuelve a pendiente (veto
nuevo de 8 h). Todo en tmp_path."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from nucleo import aprobaciones as ap
from nucleo import riesgo
from nucleo import tareas as T

T0 = datetime(2026, 10, 14, 17, 57, 33)


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "ALMACEN", tmp_path / "aprobaciones.json")
    monkeypatch.setattr(ap, "HISTORIAL", tmp_path / "aprobaciones_historial.jsonl")
    monkeypatch.setattr(ap, "CANDADO", tmp_path / ".candado.lock")
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "tareas.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado_tareas.lock")
    return tmp_path


def _veto(tarea="T844", nivel="R1", tipo="veto"):
    s = ap.solicitar(f"fusionar {tarea}", "R1 veto sha256:abc", nivel=nivel, origen="riesgo", ahora=T0 - timedelta(hours=1),
                     ttl=timedelta(hours=24), tipo=tipo, extra={"tarea": tarea, "titulo": "algo"})
    return ap.denegar(s["id"], quien="damian", motivo="web", ahora=T0)


def _tarea(id_, estado="pendiente"):
    """Una tarea con ese id exacto (la cola reparte los ids: se crea y se renombra) y ese estado."""
    t = T.anadir(f"tarea {id_}", detalle="x")
    datos = T.cargar()
    for x in datos["tareas"]:
        if x["id"] == t["id"]:
            x["id"], x["estado"] = id_, estado
    T.guardar(datos)
    return id_


def test_deshacer_veto_vuelve_a_pendiente_con_veto_nuevo_y_queda_en_el_historial():
    _tarea("T844")
    s = _veto()
    ahora = T0 + timedelta(days=3)
    assert [x["id"] for x in ap.vetos_deshacibles(ahora)] == [s["id"]]
    r = ap.deshacer_veto(s["id"], ahora=ahora)
    assert r["estado"] == "pendiente" and r["vence"] == (ahora + timedelta(hours=8)).strftime(ap.FORMATO)
    assert r["eventos"][-1]["tipo"] == "veto_deshecho" and r["eventos"][-1]["quien"] == "damian"
    assert ap.verificar_historial()[0] is True
    assert ap.vetos_deshacibles(ahora) == []                     # ya no esta vetada


def test_no_se_deshace_pasados_7_dias_ni_si_no_esta_vetada_ni_si_no_es_un_veto_r1():
    _tarea("T844")
    s = _veto()
    with pytest.raises(ap.EstadoInvalido, match="más de 7 días"):
        ap.deshacer_veto(s["id"], ahora=T0 + timedelta(days=7))
    assert ap.vetos_deshacibles(T0 + timedelta(days=7)) == []
    ap.deshacer_veto(s["id"], ahora=T0 + timedelta(days=1))
    with pytest.raises(ap.EstadoInvalido, match="no vetada"):    # ya esta pendiente
        ap.deshacer_veto(s["id"], ahora=T0 + timedelta(days=1))
    r2 = _veto("T901", nivel="R2", tipo="normal")
    with pytest.raises(ap.EstadoInvalido, match="no es un veto R1"):
        ap.deshacer_veto(r2["id"], ahora=T0)


def test_no_se_deshace_si_la_tarea_ya_esta_cerrada(aislado):
    _tarea("T844")
    s = _veto()
    T.actualizar("T844", estado="hecha")
    with pytest.raises(ap.EstadoInvalido, match="ya está hecha"):
        ap.deshacer_veto(s["id"], ahora=T0 + timedelta(hours=1))


def test_no_se_deshace_si_ya_hay_otra_solicitud_abierta_para_lo_mismo():
    _tarea("T844")
    s = _veto()
    nueva = ap.solicitar(s["accion"], s["detalle"], nivel="R1", origen="riesgo", ahora=T0 + timedelta(hours=1),
                         tipo="veto", extra={"tarea": "T844"})
    assert nueva["id"] != s["id"]
    with pytest.raises(ap.EstadoInvalido, match="otra solicitud abierta"):
        ap.deshacer_veto(s["id"], ahora=T0 + timedelta(hours=2))


def test_la_bandeja_del_centro_lista_los_vetados_deshacibles():
    _tarea("T844")
    s = _veto()
    m = riesgo.bandeja(ahora=T0 + timedelta(days=1))
    assert [x["id"] for x in m["vetadas"]] == [s["id"]] and m["vetadas"][0]["vetada_el"] == "2026-10-14 17:57:33"
    assert m["r1"] == []
