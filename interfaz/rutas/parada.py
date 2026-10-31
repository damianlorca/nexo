# -*- coding: utf-8 -*-
"""PARADA de emergencia: POST /parada -> nucleo.parada.activar(motivo, "damian"); POST /seguir -> desactivar().

- Doble confirmacion: en la UI (boton -> panel de confirmar) y en el servidor (campo confirmacion=si).
- Sin optimistic update: la respuesta se pinta RELEYENDO la bandera despues de llamar al core.
- La web sigue viva y navegable con la PARADA activa; /seguir funciona siempre. Solo las
  ordenes se bloquean (incremento 5).
Son `def` (no async): FastAPI las corre en el threadpool, y activar() puede tardar unos
segundos descargando los modelos de Ollama.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import PlainTextResponse

from interfaz.lecturas import estado_parada
from interfaz.vistas import pintar
from nucleo import parada

router = APIRouter()

MAX_MOTIVO = 300
MOVIL = re.compile(r"Mobile|Android|iPhone|iPad", re.I)


def motivo_por_defecto(request: Request) -> str:
    """Motivo vacio (es opcional): se dice desde donde se paro, para que la bandera no quede muda."""
    return "desde el móvil" if MOVIL.search(request.headers.get("user-agent", "")) else "desde la web"


def _respuesta(request: Request, aviso: str, error: str = ""):
    return pintar(request, "_parada_respuesta.html", parada=estado_parada(), aviso=aviso, error=error)


@router.get("/parada/estado")
def estado(request: Request, anunciar: bool = False):
    """Boton + banner desde la bandera real. anunciar=1 cuando el cambio vino de fuera (SSE)."""
    aviso = ""
    if anunciar:
        real = estado_parada()
        aviso = (f"NEXO se ha PARADO desde fuera: {real['motivo']}." if real["activa"]
                 else "La PARADA se ha quitado desde fuera: NEXO vuelve a estar activo.")
    return _respuesta(request, aviso)


@router.post("/parada")
def parar(request: Request, confirmacion: str = Form(""), motivo: str = Form("")):
    if confirmacion != "si":
        return PlainTextResponse("Falta la confirmación de la PARADA", status_code=400)
    # La vista puede estar desfasada (parada puesta desde Telegram): no pisar motivo/quien/cuando.
    previa = estado_parada()
    if previa["activa"]:
        return _respuesta(request, f"NEXO ya estaba parado ({previa['motivo']}). No se ha cambiado nada.")
    try:
        parada.activar(motivo.strip()[:MAX_MOTIVO] or motivo_por_defecto(request), "damian")
    except Exception as e:
        return _respuesta(request, "", error=f"No se pudo activar la PARADA: {str(e)[:200]}")
    real = estado_parada()
    return _respuesta(request, "NEXO parado." if real["activa"] else "",
                      error="" if real["activa"] else "La PARADA no consta activa tras pedirla. Reintenta.")


@router.post("/seguir")
def seguir(request: Request, confirmacion: str = Form("")):
    if confirmacion != "si":
        return PlainTextResponse("Falta la confirmación para seguir", status_code=400)
    try:
        habia = parada.desactivar()
    except Exception as e:
        return _respuesta(request, "", error=f"No se pudo quitar la PARADA: {str(e)[:200]}")
    if estado_parada()["activa"]:
        return _respuesta(request, "", error="La PARADA sigue activa tras pedir seguir. Reintenta.")
    return _respuesta(request, "NEXO reanudado." if habia else "No había PARADA activa.")
