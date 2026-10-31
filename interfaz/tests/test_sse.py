# -*- coding: utf-8 -*-
"""Incremento 3: endpoint SSE (auth, replay, reconciliar) y refresco de la PARADA por SSE."""
from __future__ import annotations

import asyncio
import json

from interfaz.eventos import Bus
from interfaz.rutas.sse import flujo
from nucleo import parada


def _recoger(bus, ultimo_id, cuantos, publicar_despues=()):
    """Saca `cuantos` mensajes del flujo; `publicar_despues` se publica ya con el flujo escuchando."""
    async def prueba():
        bus.iniciar(asyncio.get_running_loop())
        vivo = {"si": True}

        async def seguir():
            return vivo["si"]

        gen = flujo(bus, ultimo_id, seguir, espera=0.05)
        salida = [await gen.__anext__()]
        for tipo in publicar_despues:
            bus.publicar(tipo, {"t": tipo})
        while len(salida) < cuantos:
            salida.append(await asyncio.wait_for(gen.__anext__(), 2))
        vivo["si"] = False
        await gen.aclose()
        return salida

    return asyncio.run(prueba())


def test_sin_id_empieza_con_retry_y_solo_lo_nuevo():
    bus = Bus()
    bus.publicar("viejo")
    mensajes = _recoger(bus, None, 2, publicar_despues=["nuevo"])
    assert mensajes[0] == {"comment": "nexo", "retry": 3000}
    assert mensajes[1]["event"] == "nuevo" and mensajes[1]["id"] == f"{bus.arranque}-2"
    assert json.loads(mensajes[1]["data"]) == {"t": "nuevo"}


def test_con_last_event_id_reenvia_lo_perdido_en_orden():
    bus = Bus()
    e1 = bus.publicar("a")
    bus.publicar("b")
    bus.publicar("c")
    mensajes = _recoger(bus, e1.id, 3)
    assert [m["event"] for m in mensajes[1:]] == ["b", "c"]


def test_id_de_otro_arranque_manda_reconciliar_con_el_id_actual():
    bus = Bus()
    bus.publicar("a")
    bus.publicar("b")
    mensajes = _recoger(bus, "otroarranque-7", 2, publicar_despues=["c"])
    assert mensajes[0]["event"] == "reconciliar" and mensajes[0]["id"] == f"{bus.arranque}-2"
    assert mensajes[1]["event"] == "c"  # y sigue en directo tras reconciliar


def test_eventos_requiere_sesion(cliente):
    assert cliente.get("/eventos").status_code == 401


def test_pagina_conecta_al_sse_con_el_ultimo_id(cliente, csrf, app):
    app.state.bus.publicar("x")
    r = cliente.get("/")
    assert 'hx-ext="sse"' in r.text
    assert f'sse-connect="/eventos?desde={app.state.bus.arranque}-1"' in r.text
    assert 'id="conexion"' in r.text and "Conexión en tiempo real perdida" in r.text


def test_parada_estado_anuncia_cambio_venido_de_fuera(cliente, csrf):
    parada.activar("desde telegram", "telegram")
    r = cliente.get("/parada/estado", params={"anunciar": 1})
    assert 'data-activa="1"' in r.text and "NEXO se ha PARADO desde fuera: desde telegram." in r.text
    assert 'id="banner-parada" hx-swap-oob="true"' in r.text
    parada.desactivar()
    r = cliente.get("/parada/estado", params={"anunciar": 1})
    assert 'data-activa="0"' in r.text and "vuelve a estar activo" in r.text
    # Sin anunciar: repinta pero no dice nada.
    assert "desde fuera" not in cliente.get("/parada/estado").text


def test_ciclo_de_vida_conecta_vigilancia_con_el_bus(ajustes):
    """Extremo a extremo sin streaming: con la app arrancada, una PARADA puesta a mano llega al bus."""
    import time

    from fastapi.testclient import TestClient

    from interfaz.app import crear_app
    from interfaz.tests.conftest import BASE
    ajustes.vigilar, ajustes.intervalo_vigilancia = True, 0.05
    app = crear_app(ajustes)
    with TestClient(app, base_url=BASE):
        time.sleep(0.2)  # foto inicial
        parada.activar("a mano", "damian")
        limite = time.monotonic() + 3
        while time.monotonic() < limite and not app.state.bus.despues(0):
            time.sleep(0.05)
        assert [(e.tipo, e.datos["activa"]) for e in app.state.bus.despues(0)] == [("parada", True)]


def test_refresco_silencioso_no_toca_los_avisos(cliente, csrf):
    r = cliente.get("/parada/estado")
    assert "#avisos" not in r.text and 'data-motivo=""' in r.text


def test_flujo_avisa_logs_perdidos_y_reenvia_la_parada():
    bus = Bus(capacidad_logs=5)
    antes = bus.publicar("tareas")
    bus.publicar("parada", {"activa": True})
    for i in range(20):
        bus.publicar("log", {"i": i})
    mensajes = _recoger(bus, antes.id, 8)
    assert mensajes[1] == {"event": "logs_perdidos", "data": "{}"}
    assert mensajes[2]["event"] == "parada"
    assert [json.loads(m["data"])["i"] for m in mensajes[3:]] == [15, 16, 17, 18, 19]
