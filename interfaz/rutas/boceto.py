# -*- coding: utf-8 -*-
"""T230: el boceto (/boceto) ya es la web de verdad (aprobado por Damian el 28/09).

Solo quedan redirecciones para que los enlaces guardados del boceto sigan llevando a su sitio.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/boceto")


def _a(destino: str, request: Request) -> RedirectResponse:
    consulta = request.url.query.replace("quien=", "depende=")
    return RedirectResponse(destino + (f"?{consulta}" if consulta else ""), status_code=307)


@router.get("")
@router.get("/centro")
def centro(request: Request):
    return RedirectResponse("/", status_code=307)


@router.get("/tareas")
def tareas(request: Request):
    return _a("/tareas", request)


@router.get("/tareas/{id_tarea}")
def ficha(request: Request, id_tarea: str):
    return RedirectResponse(f"/tareas/{id_tarea}" if id_tarea.isalnum() else "/tareas", status_code=307)
