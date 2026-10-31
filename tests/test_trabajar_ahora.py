# -*- coding: utf-8 -*-
"""Bloque 8 (17/10): "Trabajar ahora" = planificador.encolar_todos + modo trabajo. Dobles, sin procesos reales."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from nucleo import freno, parada, plantillas_turno, turnos
from nucleo import planificador as P

AHORA = datetime(2026, 10, 17, 10, 0, 0)


def _turno(plantilla, nombre=None, **campos):
    base = {"nombre": nombre or plantilla, "plantilla": plantilla, "dias": list(turnos.DIAS), "horas": ["03:30"]}
    return turnos.guardar_turno(dict(base, **campos))


@pytest.fixture
def mundo(monkeypatch):
    """Turnos de reels, vigia, cola y tribunal (en ese orden de alta) con trabajo en todos; freno abierto."""
    cfg = turnos.cargar()
    cfg["turnos"] = []
    turnos.guardar(cfg)
    ids = {p: _turno(p)["id"] for p in ("reels", "vigia", "cola", "tribunal", "implementador")}
    trabajo = {p: 1 for p in ids}
    monkeypatch.setattr(plantillas_turno, "candidatas", lambda ctx: trabajo.get(ctx["plantilla"], 0))
    monkeypatch.setattr(freno, "puede_generar", lambda pl, tareas=None: (True, ""))
    monkeypatch.setattr(parada, "activa", lambda: None)
    return ids, trabajo


def _cola():
    return [x["turno"] for x in sorted(P.cola(), key=lambda x: P._orden_cola(x, turnos.cargar()))]


def test_encola_en_el_orden_pedido_y_reels_el_ultimo(mundo):
    ids, _ = mundo
    r = P.encolar_todos(ahora=AHORA)
    esperado = [ids[p] for p in ("tribunal", "implementador", "cola", "vigia", "reels")]
    assert r["encolados"] == esperado and r["saltados"] == []
    assert _cola() == esperado          # el orden de salida de la cola, no solo el de alta


def test_no_encola_lo_que_no_tiene_trabajo_y_dice_por_que(mundo, monkeypatch):
    ids, trabajo = mundo
    trabajo["tribunal"] = 0
    monkeypatch.setattr(plantillas_turno, "por_que_nada", lambda ctx: "no hay borradores")
    r = P.encolar_todos(ahora=AHORA)
    assert ids["tribunal"] not in r["encolados"]
    assert {"turno": ids["tribunal"], "motivo": "sin trabajo: no hay borradores"} in r["saltados"]


def test_el_freno_f0_no_se_salta(mundo, monkeypatch):
    ids, _ = mundo
    monkeypatch.setattr(freno, "puede_generar", lambda pl, tareas=None: (False, "freno F0: 30 propuestas")
                        if pl in freno.GENERADORAS else (True, ""))
    r = P.encolar_todos(ahora=AHORA)
    assert ids["vigia"] not in r["encolados"]
    assert {"turno": ids["vigia"], "motivo": "freno F0: 30 propuestas"} in r["saltados"]
    assert ids["cola"] in r["encolados"]       # lo que no genera propuestas, pasa


def test_inactivos_parada_e_interruptor(mundo, monkeypatch):
    ids, _ = mundo
    turnos.poner_activo(ids["reels"], False)
    assert ids["reels"] not in P.encolar_todos(ahora=AHORA)["encolados"]
    monkeypatch.setattr(parada, "activa", lambda: "parada de prueba")
    r = P.encolar_todos(ahora=AHORA)
    assert r["encolados"] == [] and r["saltados"][0]["motivo"] == "PARADA puesta"
    monkeypatch.setattr(parada, "activa", lambda: None)
    turnos.desactivar("prueba")
    assert P.encolar_todos(ahora=AHORA)["encolados"] == []


def test_no_duplica_lo_que_ya_esta_en_la_cola(mundo):
    ids, _ = mundo
    P.encolar(ids["cola"])
    r = P.encolar_todos(ahora=AHORA)
    assert ids["cola"] not in r["encolados"]
    assert {"turno": ids["cola"], "motivo": "ya esta en la cola"} in r["saltados"]
    assert len([x for x in P.cola() if x["turno"] == ids["cola"]]) == 1


def test_horas_no_validas(mundo):
    with pytest.raises(turnos.ConfigInvalida):
        P.encolar_todos(horas=5)


class _Lanzador:
    def __init__(self):
        self.lanzados = []

    def __call__(self, entrada):
        self.lanzados.append(entrada["turno"])
        return 99999999


def _acabar_turno():
    P.terminar()


def test_modo_trabajo_reencola_con_tope_de_tres_tandas(mundo):
    ids, trabajo = mundo
    for p in list(trabajo):
        if p != "cola":
            trabajo[p] = 0
    P.encolar_todos(horas=2, ahora=AHORA)
    assert P.modo_trabajo()["hasta"] == (AHORA + timedelta(hours=2)).isoformat(timespec="seconds")
    l = _Lanzador()
    t = AHORA
    for _ in range(6):
        t += timedelta(minutes=1)
        P.tick(t, lanzar=l)          # lanza lo que haya
        _acabar_turno()              # el turno acaba
        P.tick(t + timedelta(seconds=5), lanzar=l)   # cola vacia: nueva tanda (o fin)
        _acabar_turno()
    assert l.lanzados.count(ids["cola"]) == P.TANDAS_MAX      # y no mas
    assert P.modo_trabajo() is None                           # al agotarse el tope, el modo acaba solo
    assert P.estado()["ultimo_trabajo"]["fin"]


def test_modo_trabajo_termina_sin_trabajo_con_la_hora_y_con_parada(mundo, monkeypatch):
    ids, trabajo = mundo
    P.encolar_todos(horas=1, ahora=AHORA)
    P.cola()                             # (hay cola, el tick la lanza)
    for p in list(trabajo):
        trabajo[p] = 0
    l = _Lanzador()
    for _ in range(len(ids) + 1):        # vacia la cola
        P.tick(AHORA + timedelta(minutes=1), lanzar=l)
        _acabar_turno()
    P.tick(AHORA + timedelta(minutes=2), lanzar=l)
    assert P.modo_trabajo() is None and P.estado()["ultimo_trabajo"]["fin"] == "sin trabajo"

    P.encolar_todos(horas=1, ahora=AHORA)
    P.tick(AHORA + timedelta(hours=1, minutes=1), lanzar=l)
    assert P.modo_trabajo() is None and P.estado()["ultimo_trabajo"]["fin"] == "llego la hora"

    P.encolar_todos(horas=3, ahora=AHORA)
    monkeypatch.setattr(parada, "activa", lambda: "parada de prueba")
    P.tick(AHORA + timedelta(minutes=5), lanzar=l)
    assert P.modo_trabajo() is None and P.estado()["ultimo_trabajo"]["fin"] == "PARADA puesta"


def test_modo_trabajo_corta_con_la_cuota(mundo, monkeypatch):
    from nucleo import cuota
    ids, _ = mundo
    P.encolar_todos(horas=1, ahora=AHORA)
    monkeypatch.setattr(cuota, "seguir", lambda nombres, ahora=None: (False, "cuota agotada"))
    l = _Lanzador()
    for _ in range(8):
        P.tick(AHORA + timedelta(minutes=1), lanzar=l)
        _acabar_turno()
    P.tick(AHORA + timedelta(minutes=2), lanzar=l)
    assert P.modo_trabajo() is None and P.estado()["ultimo_trabajo"]["fin"] == "cuota agotada"


def test_dejar_de_trabajar_no_toca_la_cola(mundo):
    ids, _ = mundo
    P.encolar_todos(horas=1, ahora=AHORA)
    antes = P.cola()
    assert P.dejar_de_trabajar() is True and P.modo_trabajo() is None
    assert P.cola() == antes and P.dejar_de_trabajar() is False
