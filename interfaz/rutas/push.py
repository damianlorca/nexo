# -*- coding: utf-8 -*-
"""Suscripcion a notificaciones push (hito movil). Todo con sesion; los POST con CSRF (middleware).

El navegador se suscribe con la clave publica VAPID (GET /push/clave) y manda su suscripcion
(POST /push/suscribir, JSON). "Desactivar" en Ajustes = baja en el navegador + POST /push/baja.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from interfaz.push import endpoint_valido, suscripcion_valida

router = APIRouter(prefix="/push")

MAX_CUERPO = 4096


async def _json(request: Request):
    cuerpo = await request.body()
    if len(cuerpo) > MAX_CUERPO:
        return None
    try:
        return json.loads(cuerpo)
    except ValueError:
        return None


@router.get("/clave")
def clave(request: Request):
    return JSONResponse({"clave": request.app.state.notificador.almacen.clave_publica()})


@router.post("/suscribir")
async def suscribir(request: Request):
    sub = await _json(request)
    if not suscripcion_valida(sub):
        return JSONResponse({"ok": False, "error": "Suscripción no válida."}, status_code=400)
    request.app.state.notificador.almacen.guardar(sub)
    return JSONResponse({"ok": True})


@router.post("/baja")
async def baja(request: Request):
    datos = await _json(request)
    endpoint = datos.get("endpoint", "") if isinstance(datos, dict) else ""
    if not endpoint_valido(endpoint):
        return JSONResponse({"ok": False, "error": "Suscripción no válida."}, status_code=400)
    return JSONResponse({"ok": True, "quitada": request.app.state.notificador.almacen.quitar(endpoint)})


@router.post("/prueba")
async def prueba(request: Request):
    r = await asyncio.to_thread(request.app.state.notificador.prueba)
    return JSONResponse({"ok": r["enviados"] > 0, **r})
