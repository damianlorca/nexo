# -*- coding: utf-8 -*-
"""Plantillas Jinja2 (autoescape activo en .html) y helper para pintar con el contexto comun."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from interfaz.lecturas import estado_parada

DIR = Path(__file__).resolve().parent
plantillas = Jinja2Templates(directory=DIR / "plantillas")
plantillas.env.filters["hora"] = lambda epoch: time.strftime("%H:%M:%S", time.localtime(epoch or 0))

# T691 fase 1 (05/10, maqueta aprobada por Damian): cinco destinos (barra inferior en el movil, lateral desde
# 900 px) y el resto en "Mas". Las rutas viejas siguen vivas; el Centro de siempre esta en /tecnico.
NAV = [
    ("/", "Centro", "◎"),
    ("/tareas", "Tareas", "☰"),
    ("/ordenes", "Órdenes", "✎"),
    ("/bandejas", "Bandejas", "▤"),
    ("/radares", "Radares", "◈"),
]
NAV_MAS = [
    ("/turnos", "Turnos"),
    ("/proveedores", "Proveedores"),
    ("/grafo", "Grafo"),
    ("/logs", "Logs"),
    ("/ajustes", "Ajustes"),
    ("/tecnico", "Detalle técnico"),
]
CACHE_BANDEJAS = 20.0   # segundos: el contador se pinta en cada pagina y no merece leer la cola cada vez
_contador = {"cuando": 0.0, "n": None}


def contador_bandejas() -> int | None:
    """Decisiones que esperan a Damian (icono de Bandejas). None si no se puede leer: no se pinta numero."""
    ahora = time.monotonic()
    if ahora - _contador["cuando"] > CACHE_BANDEJAS:
        try:
            from interfaz import presentar
            _contador["n"] = presentar.n_bandejas()
        except Exception as e:   # noqa: BLE001
            logging.getLogger("uvicorn.error").warning("contador de bandejas: %s", type(e).__name__)
            _contador["n"] = None
        _contador["cuando"] = ahora
    return _contador["n"]


def _seccion(ruta: str) -> str:
    """Destino principal al que pertenece una ruta (para marcarlo en la barra); '' si es de "Mas"."""
    for destino, *_ in NAV:
        if ruta == destino or (destino != "/" and ruta.startswith(destino + "/")):
            return destino
    return "/centro" if ruta.startswith("/centro/") else ""


def pintar(request: Request, nombre: str, codigo: int = 200, **contexto):
    sesion = getattr(request.state, "sesion", None)
    contexto.setdefault("sesion", sesion)
    contexto.setdefault("csrf", sesion["csrf"] if sesion else "")
    contexto.setdefault("nav", NAV)
    contexto.setdefault("nav_mas", NAV_MAS)
    contexto.setdefault("actual", request.url.path)
    contexto.setdefault("seccion", _seccion(request.url.path))
    if sesion is not None and "n_bandejas" not in contexto and not request.headers.get("HX-Request"):
        contexto["n_bandejas"] = contador_bandejas()
    if sesion is not None and "parada" not in contexto:
        contexto["parada"] = estado_parada()
    if sesion is not None:
        contexto.setdefault("ultimo_evento", request.app.state.bus.ultimo_id)
    return plantillas.TemplateResponse(request, nombre, contexto, status_code=codigo)


def pintar_panel(request: Request, plantilla: str, url: str, leer, **extra):
    """Pinta un panel con lo que devuelva leer(); si la lectura falla, el panel de error con
    reintento (200, nunca un 500) y en el log solo el tipo de excepcion (nada de datos)."""
    try:
        datos = leer()
    except Exception as e:
        logging.getLogger("uvicorn.error").warning("panel %s fallo: %s", url, type(e).__name__)
        return pintar(request, "_panel_error.html", url=url, tipo_error=type(e).__name__)
    return pintar(request, plantilla, **datos, **extra)
