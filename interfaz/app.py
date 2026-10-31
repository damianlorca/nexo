# -*- coding: utf-8 -*-
"""App FastAPI de la interfaz de NEXO.

Arrancar (solo 127.0.0.1):
    .venv\\Scripts\\python.exe -m uvicorn interfaz.app:app --host 127.0.0.1 --port 8765
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from interfaz.config import Ajustes
from interfaz.eventos import Bus
from interfaz.push import Almacen, Notificador
from interfaz.rutas import ajustes as ajustes_rutas
from interfaz.chat import ChatTrabajador
from interfaz.rutas import boceto, centro, chat, grafo, logs, ordenes, parada, proveedores, push, pwa, sesion, sse, tareas
from interfaz.rutas import turnos as turnos_rutas
from interfaz.seguridad import CABECERAS, MiddlewareSeguridad, Seguridad, instalar_filtro_logs
from interfaz.trabajador import Trabajador
from interfaz.vigilancia import Vigilante
from interfaz.vistas import DIR, pintar
from nucleo.config import valor


REFRESCO_INCOMPLETO = 60     # s entre preguntas a Tailscale mientras falte host o dueno
REFRESCO_COMPLETO = 600


def describir_tailnet(ajustes: Ajustes) -> str:
    return (f"tailnet: host={ajustes.tailnet_host or '-'}, "
            f"dueno={'si' if ajustes.tailnet_dueno else 'NO (el movil no entra por identidad)'}")


async def refrescar_tailnet(ajustes: Ajustes, dormir=asyncio.sleep) -> None:
    """Mantiene host y dueno de la tailnet al dia sin bloquear el event loop (tailscale status en un hilo)."""
    from interfaz import tailnet
    registro = logging.getLogger("uvicorn.error")
    primera = True
    while True:
        # La primera pregunta, nada mas arrancar (Ajustes.produccion no pregunta: corre al importar).
        try:
            if ajustes.aplicar_tailnet(await asyncio.to_thread(tailnet.estado)) or primera:
                registro.info(describir_tailnet(ajustes))
        except Exception as e:  # Tailscale raro nunca tira la web
            registro.warning("tailnet: no se pudo refrescar: %s", type(e).__name__)
        primera = False
        completo = bool(ajustes.tailnet_host and ajustes.tailnet_dueno)
        await dormir(REFRESCO_COMPLETO if completo else REFRESCO_INCOMPLETO)


def crear_app(ajustes: Ajustes | None = None) -> FastAPI:
    ajustes = ajustes or Ajustes.produccion()
    seguridad = Seguridad(ajustes)
    bus = Bus()
    trabajador = Trabajador(bus)
    chat_trabajador = ChatTrabajador(bus)
    notificador = Notificador(Almacen(ajustes.push_carpeta), buscar_orden=trabajador.orden)
    bus.oir(notificador.oir)

    @asynccontextmanager
    async def ciclo(app: FastAPI):
        bus.iniciar(asyncio.get_running_loop())
        vigilancia = None
        if ajustes.vigilar:
            vigilancia = asyncio.create_task(Vigilante(bus, ajustes.intervalo_vigilancia, ajustes.planificar).correr())
        refresco = asyncio.create_task(refrescar_tailnet(ajustes)) if ajustes.tailnet_auto else None
        oyente = None
        if ajustes.altavoz and ajustes.vigilar and valor("altavoz.oyente", True):
            from extremidades import altavoz   # T697: hilo propio; si el altavoz no esta, lo busca cada minuto
            oyente = altavoz.arrancar_oyente()
        seguridad.guardar_token()
        try:
            yield
        finally:
            seguridad.borrar_token()
            if oyente is not None:
                from extremidades import altavoz
                altavoz.parar_oyente()
            for tarea in (vigilancia, refresco):
                if tarea is not None:
                    tarea.cancel()
            # Descarta las ordenes en cola; una que ya este en curso termina (no se puede matar un hilo).
            trabajador.cerrar()
            chat_trabajador.cerrar()
            notificador.cerrar()

    # Sin /docs ni /openapi.json: no hay por que publicar el mapa de la API.
    app = FastAPI(title="NEXO", docs_url=None, redoc_url=None, openapi_url=None, lifespan=ciclo)
    app.state.ajustes = ajustes
    app.state.seguridad = seguridad
    app.state.bus = bus
    app.state.trabajador = trabajador
    app.state.chat = chat_trabajador
    app.state.notificador = notificador

    app.add_middleware(MiddlewareSeguridad, seguridad=seguridad)
    app.mount("/estatico", StaticFiles(directory=DIR / "estatico"), name="estatico")
    app.include_router(sesion.router)
    app.include_router(pwa.router)
    app.include_router(push.router)
    app.include_router(centro.router)
    app.include_router(parada.router)
    app.include_router(sse.router)
    app.include_router(ordenes.router)
    app.include_router(tareas.router)
    app.include_router(chat.router)  # T290: chat dentro de cada tarea
    app.include_router(proveedores.router)
    app.include_router(logs.router)
    app.include_router(ajustes_rutas.router)
    app.include_router(turnos_rutas.router)  # T231: turnos programables
    app.include_router(boceto.router)  # T230: boceto de la interfaz nueva, solo lectura
    app.include_router(grafo.router)  # T251: grafo de tareas, borradores, turnos e IAs

    @app.exception_handler(StarletteHTTPException)
    async def error_http(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/estatico/"):
            return PlainTextResponse("No encontrado", status_code=exc.status_code)
        return pintar(request, "error.html", exc.status_code, codigo_error=exc.status_code)

    @app.exception_handler(Exception)
    async def error_interno(request: Request, exc: Exception):
        # Nunca volcar la traza al navegador (puede llevar rutas o datos).
        # Starlette corre este handler en ServerErrorMiddleware, POR FUERA de MiddlewareSeguridad:
        # las cabeceras de seguridad hay que ponerlas aqui a mano.
        resp = pintar(request, "error.html", 500, codigo_error=500)
        resp.headers.update(CABECERAS)
        resp.headers["cache-control"] = "no-store"
        return resp

    instalar_filtro_logs()
    return app


app = crear_app()
