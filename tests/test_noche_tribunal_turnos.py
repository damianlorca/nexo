# -*- coding: utf-8 -*-
"""Noche 05/10: (1) un turno que el proceso no entiende (p. ej. plantilla nueva y web sin reiniciar) NO se pierde al
guardar la tabla: asi desaparecio el turno del piloto implpil2 a las 01:10; (2) el resultado de un turno del
tribunal se cuenta por lo que hizo el tribunal, no por 'tarea(s)/propuesta(s)'; (3) un turno del tribunal sin
cambios queda registrado en silencio: sin aviso y fuera del Centro."""
from __future__ import annotations

import json

from nucleo import planificador, turnos


def _turno(**k):
    base = {"id": "u1", "nombre": "Tribunal", "plantilla": "tribunal", "dias": ["lunes"], "horas": ["22:00"],
            "max_tareas": 3, "max_minutos": 25, "avisar": True, "activo": True}
    return dict(base, **k)


def test_turno_con_plantilla_desconocida_sobrevive_a_un_guardado():
    raro = _turno(id="implpil2", nombre="Implementador (piloto)", plantilla="plantilla_del_futuro")
    turnos.CONFIG.parent.mkdir(parents=True, exist_ok=True)
    turnos.CONFIG.write_text(json.dumps({"version": 2, "turnos": [_turno(), raro]}), encoding="utf-8")
    cfg = turnos.cargar()
    assert [t["id"] for t in cfg["turnos"]] == ["u1"]               # no se programa lo que no se entiende...
    cfg["turnos"][0]["activo"] = False
    turnos.guardar(cfg)
    datos = json.loads(turnos.CONFIG.read_text(encoding="utf-8"))
    assert any(t["id"] == "implpil2" for t in datos["turnos"])      # ...pero tampoco se borra al guardar
    assert next(t for t in datos["turnos"] if t["id"] == "u1")["activo"] is False


def _reg(pasos, **k):
    return dict({"inicio": "2026-10-05T01:02:41", "plantilla": "tribunal", "pasos": pasos}, **k)


def test_resultado_corto_del_tribunal_cuenta_expedientes():
    paso = {"sincronizado": {"nuevos": [], "fuera": [], "a_claude": [],
                             "reconsiderar": {"encolados": ["reconsiderar_T083"], "sueltas": []}},
            "hechos": [{"nombre": "a", "fase": "resuelto", "decision": "APROBADO"},
                       {"nombre": "b", "fase": "espera"}, {"nombre": "c", "fase": "damian"}],
            "a_damian": ["c"], "a_claude": []}
    txt = planificador.resultado_corto(_reg({"tribunal": paso}))
    assert "tarea(s)" not in txt
    assert "1 resuelto" in txt and "1 a tu bandeja" in txt and "1 esperando revisores" in txt
    assert "1 lote(s) de reconsideracion" in txt


def test_tribunal_sin_cambios_es_silencioso_y_no_sale_en_el_centro(tmp_path):
    from turno_nexo import tribunal_silencioso
    quieto = {"sincronizado": {"nuevos": [], "fuera": [], "a_claude": [], "reconsiderar": {"encolados": [], "sueltas": []}},
              "hechos": [{"nombre": "b", "fase": "espera"}], "a_damian": [], "a_claude": []}
    assert tribunal_silencioso(quieto) and not tribunal_silencioso({"error": "x"})
    assert not tribunal_silencioso(dict(quieto, hechos=[{"nombre": "a", "fase": "resuelto"}]))
    (tmp_path / "turno_nexo_20261005_010000.json").write_text(json.dumps(_reg({"tribunal": {}}, nombre_turno="Cola")),
                                                               encoding="utf-8")
    (tmp_path / "turno_nexo_20261005_013000.json").write_text(
        json.dumps(_reg({"tribunal": quieto}, silencioso=True)), encoding="utf-8")
    assert planificador.ultimo_registro(carpeta=tmp_path, ruidoso=True)["archivo"] == "turno_nexo_20261005_010000.json"
    assert planificador.ultimo_registro(carpeta=tmp_path)["archivo"] == "turno_nexo_20261005_013000.json"
    assert "sin cambios" in planificador.resultado_corto(_reg({"tribunal": quieto}, silencioso=True))
