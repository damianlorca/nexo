# -*- coding: utf-8 -*-
"""GET /eventos: flujo SSE del bus, con replay por Last-Event-ID (o ?desde= de la pagina).

La pagina pinta en sse-connect el ultimo id del bus en el momento de renderizarla (?desde=):
asi no se pierde lo que pase entre pintar y conectar. Al reconectar, el navegador manda
Last-Event-ID, que manda sobre ?desde=. Si no se puede reenviar lo perdido (otro arranque,
hueco en el buffer) se emite "reconciliar" y el cliente recarga el estado entero.
"""
from __future__ import annotations

import json
from typing import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from interfaz.eventos import Bus, Evento

router = APIRouter()

REINTENTO_MS = 3000   # retry: que el navegador reintente cada 3 s si se corta
ESPERA = 15.0         # cada cuanto se revisa si el cliente sigue ahi / la sesion sigue viva
PING = 15             # comentario keep-alive de sse-starlette


def _sse(e: Evento) -> dict:
    return {"id": e.id, "event": e.tipo, "data": json.dumps(e.datos, ensure_ascii=False)}


async def flujo(bus: Bus, ultimo_id: str | None,
                seguir: Callable[[], Awaitable[bool]], espera: float = ESPERA) -> AsyncIterator[dict]:
    r = bus.replay(ultimo_id)
    n = r.desde
    if r.reconciliar:
        # El id actual del bus: a partir de aqui el cliente vuelve a estar al dia.
        yield {"id": f"{bus.arranque}-{n}", "event": "reconciliar", "data": "{}", "retry": REINTENTO_MS}
    else:
        yield {"comment": "nexo", "retry": REINTENTO_MS}
        if r.logs_perdidos:
            # Sin id: no mueve el Last-Event-ID. La vista de logs (incremento 8) se recarga.
            yield {"event": "logs_perdidos", "data": "{}"}
        for e in r.eventos:
            yield _sse(e)
        n = r.desde
    while await seguir():
        for e in await bus.esperar(n, espera):
            yield _sse(e)
            n = e.n


@router.get("/eventos")
async def eventos(request: Request, desde: str = ""):
    bus: Bus = request.app.state.bus
    seg = request.app.state.seguridad
    sid = request.state.sid
    ultimo = request.headers.get("last-event-id") or desde or None

    async def seguir() -> bool:
        # Se corta si el navegador se fue o si la sesion se cerro (Salir) mientras escuchaba.
        return not await request.is_disconnected() and seg.sesion(sid) is not None

    return EventSourceResponse(flujo(bus, ultimo, seguir), ping=PING, headers={"X-Accel-Buffering": "no"})
