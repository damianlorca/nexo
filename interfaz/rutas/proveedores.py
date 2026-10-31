# -*- coding: utf-8 -*-
"""Proveedores: salud de cada uno (disponible / enfriamiento / motivo) y uso real a 1, 7 y 30 dias.

Salud: lecturas.salud_proveedores (la misma cache que el Centro). "Comprobar ahora" pide una
comprobacion nueva, pero nunca mas de una cada FRESCO_MIN segundos (Qwen/Gemini/ChatGPT sondean).
Uso: nucleo.uso_proveedores.totales via lecturas; se refresca con los logs nuevos (SSE).
"""
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request

from interfaz import lecturas
from interfaz.vistas import pintar, pintar_panel

router = APIRouter()
FRESCO_MIN = 5.0


@router.get("/proveedores")
def pagina(request: Request):
    return pintar(request, "proveedores.html", periodos=lecturas.PERIODOS_USO, web=WEB)


@router.get("/proveedores/salud")
def panel_salud(request: Request, fresco: bool = False):
    edad = FRESCO_MIN if fresco else lecturas.CACHE_PROVEEDORES
    return pintar_panel(request, "_proveedores_salud.html", "/proveedores/salud",
                        lambda: {"salud": lecturas.salud_proveedores(edad)})


@router.get("/proveedores/uso")
def panel_uso(request: Request, dias: int = 1):
    if dias not in lecturas.PERIODOS_USO:
        raise HTTPException(400)
    # url sin ?dias: el Reintentar hereda hx-include="#periodo-uso" y lleva el periodo marcado.
    return pintar_panel(request, "_proveedores_uso.html", "/proveedores/uso",
                        lambda: {"filas": lecturas.uso_por_proveedor(dias), "dias": dias})


# Noche 05/10 (peticion de Damian): "Inicializar" cada proveedor web o todos. Abre su web en el Chrome de NEXO
# (una ventana, una pestana de fondo por proveedor; nunca el Chrome personal) y dice si la sesion esta activa.
WEB = (("chatgpt", "ChatGPT"), ("gemini", "Gemini (web)"), ("claude", "Claude (web de NEXO)"))


@router.post("/proveedores/inicializar")
def inicializar(request: Request, sitio: str = Form("")):
    from extremidades import navegador, sesiones_web
    sitios = [sitio] if sitio else [s for s, _ in WEB]
    if any(s not in sesiones_web.SITIOS for s in sitios):
        raise HTTPException(400)
    try:
        filas = sesiones_web.inicializar(sitios)
        error = ""
    except navegador.ChromeOcupado:
        filas, error = [], "El Chrome de NEXO lo está usando un turno ahora mismo: vuelve a probar en un rato."
    except Exception as e:   # Chrome no arranca, Playwright falla...: se dice, sin datos
        filas, error = [], f"No se pudo abrir el Chrome de NEXO ({type(e).__name__})."
    nombres = dict(WEB)
    return pintar(request, "_proveedores_sesiones.html", web=WEB,
                  filas=[dict(f, nombre=nombres.get(f["sitio"], f["sitio"])) for f in filas], error=error)


@router.post("/proveedores/interruptor")
def interruptor(request: Request, nombre: str = Form(""), accion: str = Form(""), motivo: str = Form("")):
    """T549: apagar o encender a mano un proveedor (nucleo/enfriamiento.apagar/encender). No caduca."""
    import proveedores
    from nucleo import enfriamiento
    nombres = {c.nombre for c in proveedores.CON_INTERRUPTOR}
    aviso = error = ""
    if nombre not in nombres:
        error = "Proveedor desconocido."
    elif accion == "apagar":
        enfriamiento.apagar(nombre, motivo or "desde la web")
        aviso = f"{nombre} apagado: no se le manda nada hasta que lo enciendas."
    elif accion == "encender":
        enfriamiento.encender(nombre)
        aviso = f"{nombre} encendido."
    else:
        error = "Acción desconocida."
    return pintar_panel(request, "_proveedores_salud.html", "/proveedores/salud",
                        lambda: {"salud": lecturas.salud_proveedores(0)}, aviso=aviso, error=error)
