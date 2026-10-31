# -*- coding: utf-8 -*-
"""Incremento 3: bus de eventos (ids, buffer, replay/reconciliar, espera entre hilos)."""
from __future__ import annotations

import asyncio
import threading

from interfaz.eventos import Bus, Replay


def test_ids_incrementales_con_arranque():
    bus = Bus()
    a, b = bus.publicar("x"), bus.publicar("y", {"k": 1})
    assert (a.n, b.n) == (1, 2)
    assert a.id == f"{bus.arranque}-1" and bus.ultimo_id == f"{bus.arranque}-2"
    assert b.datos == {"k": 1}


def test_replay_sin_id_no_reenvia_nada():
    bus = Bus()
    bus.publicar("x")
    assert bus.replay(None) == Replay(1, [], False, False)


def test_replay_desde_un_id_reenvia_lo_posterior():
    bus = Bus()
    e1, e2, e3 = bus.publicar("a"), bus.publicar("log"), bus.publicar("c")
    r = bus.replay(e1.id)
    assert (r.desde, [e.tipo for e in r.eventos], r.reconciliar, r.logs_perdidos) == (3, ["log", "c"], False, False)
    assert bus.replay(e3.id) == Replay(3, [], False, False)


def test_replay_de_otro_arranque_pide_reconciliar():
    bus = Bus()
    bus.publicar("a")
    assert bus.replay("deadbeef-1") == Replay(1, [], True, False)
    assert bus.replay("basura") == Replay(1, [], True, False)
    assert bus.replay(f"{bus.arranque}-99") == Replay(1, [], True, False)  # id del futuro: no cuadra


def test_replay_con_criticos_expulsados_pide_reconciliar():
    bus = Bus(capacidad_criticos=3)
    primero = bus.publicar("parada")
    for _ in range(5):
        bus.publicar("tareas")
    r = bus.replay(primero.id)
    assert r.reconciliar and r.desde == 6 and r.eventos == []


def test_rafaga_de_logs_no_expulsa_el_ultimo_evento_de_parada():
    """Seguridad: los logs tienen buffer propio y no pueden desalojar a PARADA/tareas."""
    bus = Bus(capacidad_logs=50)
    antes = bus.publicar("tareas")
    parada = bus.publicar("parada", {"activa": True, "motivo": "rafaga"})
    for i in range(10_000):
        bus.publicar("log", {"i": i})
    assert parada in bus.despues(0)
    r = bus.replay(antes.id)
    # Se perdieron logs (se avisa para recargar la vista de logs), pero NO hay que reconciliar:
    # la PARADA sigue en el buffer y se reenvia, y los 50 logs mas recientes tambien.
    assert not r.reconciliar and r.logs_perdidos
    assert r.eventos[0] == parada
    assert [e.datos["i"] for e in r.eventos[1:]] == list(range(9_950, 10_000))


def test_replay_mezcla_ambos_buffers_en_orden():
    bus = Bus()
    tipos = ["log", "parada", "log", "tareas", "log", "borrador"]
    eventos = [bus.publicar(t) for t in tipos]
    assert [e.n for e in bus.replay(eventos[0].id).eventos] == [2, 3, 4, 5, 6]


def test_esperar_despierta_con_publicacion_desde_otro_hilo():
    async def prueba():
        bus = Bus()
        bus.iniciar(asyncio.get_running_loop())
        threading.Timer(0.05, lambda: bus.publicar("desde_hilo")).start()
        eventos = await bus.esperar(0, timeout=2)
        return [e.tipo for e in eventos]

    assert asyncio.run(prueba()) == ["desde_hilo"]


def test_esperar_sin_eventos_vuelve_al_timeout():
    async def prueba():
        bus = Bus()
        bus.iniciar(asyncio.get_running_loop())
        return await bus.esperar(0, timeout=0.05)

    assert asyncio.run(prueba()) == []


def test_esperar_con_bus_sin_iniciar_duerme_y_no_gira_en_vacio():
    import time

    async def prueba():
        t0 = time.monotonic()
        await Bus().esperar(0, timeout=0.2)
        return time.monotonic() - t0

    assert asyncio.run(prueba()) >= 0.18
