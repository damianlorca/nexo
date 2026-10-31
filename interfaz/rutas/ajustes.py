# -*- coding: utf-8 -*-
"""Ajustes (hito movil): notificaciones push de este dispositivo y acceso desde el movil.

La activacion/baja la hace el navegador (nexo.js, componente "notificaciones") contra /push/*.
Aqui solo se pinta el estado que sabe el servidor: cuantos dispositivos hay suscritos y la
direccion de la tailnet.
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request

from interfaz.vistas import pintar
from nucleo import guardian, orden_proveedores

router = APIRouter()


@router.get("/ajustes")
def pagina(request: Request):
    aj = request.app.state.ajustes
    sesion = getattr(request.state, "sesion", None) or {}
    return pintar(request, "ajustes.html",
                  suscritos=len(request.app.state.notificador.almacen.todas()),
                  direccion=f"https://{aj.tailnet_host}" if aj.tailnet_host else None,
                  por_tailnet=sesion.get("via") == "tailnet", orden=orden_proveedores.actual(),
                  orden_propio=bool(orden_proveedores.leer()), guardian_activo=guardian.activo())


@router.post("/ajustes/guardian")
def guardian_post(request: Request, accion: str = Form("")):
    """T1020: interruptor del guardian de aprobaciones. Apagado = NEXO no decide ningun permiso (ni el guardian, ni el
    tribunal, ni el revisor de reglas): todo te llega a ti, con su ficha y su minichat."""
    error = aviso = ""
    if accion in ("encender", "apagar"):
        guardian.poner_activo(accion == "encender", quien="damian:web")
        aviso = "Guardián encendido: NEXO resuelve solo lo que puede." if accion == "encender" else \
            "Guardián apagado: todos los permisos te llegan a ti."
    else:
        error = "Acción desconocida."
    return pintar(request, "_ajustes_guardian.html", guardian_activo=guardian.activo(), aviso=aviso, error=error)


@router.post("/ajustes/orden-proveedores")
def orden_proveedores_post(request: Request, nombre: str = Form(""), accion: str = Form("")):
    """T195: subir, bajar o restablecer el orden en que trabajo.py llama a los proveedores."""
    error = aviso = ""
    try:
        if accion == "restablecer":
            orden_proveedores.restablecer()
            aviso = "Orden de siempre restablecido."
        elif accion in ("subir", "bajar"):
            orden_proveedores.mover(nombre, -1 if accion == "subir" else 1)
            aviso = f"{nombre} {'sube' if accion == 'subir' else 'baja'} un puesto."
        else:
            error = "Acción desconocida."
    except ValueError:
        error = "Proveedor desconocido."
    return pintar(request, "_ajustes_orden.html", orden=orden_proveedores.actual(),
                  orden_propio=bool(orden_proveedores.leer()), aviso=aviso, error=error)
