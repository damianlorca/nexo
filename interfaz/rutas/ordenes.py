# -*- coding: utf-8 -*-
"""Ordenes: escribir una orden -> nucleo.ordenes.procesar() en el trabajador (interfaz/trabajador.py).

POST /orden responde AL INSTANTE con la tarjeta "en cola" (nunca espera a que se trabaje); cada
cambio de estado llega por SSE (evento "orden") y la tarjeta se repinta sola. Con PARADA activa
se rechaza (y el formulario sale deshabilitado), pero el resto de la web sigue viva.
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from interfaz import lecturas
from interfaz.trabajador import FINALES, OrdenRechazada
from interfaz.vistas import pintar, pintar_panel
from nucleo import auditor

router = APIRouter()


def _presentar(o: dict) -> dict:
    """Traduce el dict del core a lo que se pinta (etiqueta, texto y enlace al borrador)."""
    r = o.get("resultado") or {}
    estado = r.get("estado", "")
    vista = {"estado_core": estado, "tarea": r.get("tarea", ""), "categoria": r.get("categoria", ""),
             "proveedor": r.get("proveedor", ""), "autor": r.get("autor") or "", "revisor": r.get("revisor") or "",
             "veredicto": r.get("veredicto") or "", "respuesta": r.get("respuesta", ""), "borrador": ""}
    if r.get("archivo"):
        vista["borrador"] = str(r["archivo"]).replace("\\", "/").rsplit("/", 1)[-1]
    etiquetas = {"BORRADOR": "Borrador hecho (Claude lo revisa antes de darlo por bueno)",
                 "SIN_BORRADOR": "Apuntada, pero sin borrador ahora (queda en la cola)",
                 "PARA_DAMIAN": "Apuntada como tuya",
                 "ENCOLADA": "Encolada: la trabajará NEXO en un turno (resumen/redacción/investigación)",
                 "ESCALADO": "Encolada para Claude (código/arquitectura/PC)",
                 "VACIA": "Orden vacía"}
    vista["etiqueta"] = etiquetas.get(estado, estado)
    return vista


def _tarjeta(request: Request, o: dict, anunciar: bool = False, codigo: int = 200):
    aviso = ""
    if anunciar and o["estado"] in FINALES:
        aviso = {"hecha": f"Orden {o['id']} terminada: {_presentar(o)['etiqueta']}.",
                 "error": f"Orden {o['id']} con error.",
                 "cancelada": f"Orden {o['id']} cancelada por la PARADA."}[o["estado"]]
    return pintar(request, "_orden.html", codigo, o=o, v=_presentar(o), aviso=aviso)


@router.get("/ordenes")
def pagina(request: Request):
    recientes = request.app.state.trabajador.recientes()
    return pintar(request, "ordenes.html", ordenes_sesion=[(o, _presentar(o)) for o in recientes])


@router.get("/ordenes/bloqueo")
def bloqueo(request: Request):
    return pintar(request, "_orden_bloqueo.html")


@router.post("/orden")
def enviar(request: Request, texto: str = Form(""), modo: str = Form("instantanea")):
    try:
        o = request.app.state.trabajador.enviar(texto, modo)
    except OrdenRechazada as e:
        # 200 + HX-Retarget: el mensaje va junto al formulario y la lista no se toca.
        resp = pintar(request, "_mensaje_error.html", motivo=str(e))
        resp.headers["HX-Retarget"] = "#error-orden"
        resp.headers["HX-Reswap"] = "innerHTML"
        return resp
    return pintar(request, "_orden_aceptada.html", o=o, v=_presentar(o))


@router.get("/ordenes/lista")
def lista(request: Request):
    recientes = request.app.state.trabajador.recientes()
    return pintar(request, "_ordenes_lista.html", ordenes_sesion=[(o, _presentar(o)) for o in recientes])


@router.get("/ordenes/historial")
def historial(request: Request):
    return pintar_panel(request, "_ordenes_historial.html", "/ordenes/historial",
                        lambda: {"filas": lecturas.ultimas_ordenes()})


@router.get("/ordenes/{id_orden}")
def tarjeta(request: Request, id_orden: str, anunciar: bool = False):
    o = request.app.state.trabajador.orden(id_orden)
    if o is None:
        # La web se reinicio o la orden salio de las 50 recordadas: la tarjeta desaparece.
        return HTMLResponse("")
    return _tarjeta(request, o, anunciar)


@router.get("/borrador")
def borrador(request: Request, f: str = ""):
    try:
        contenido = lecturas.leer_borrador(f)
    except OSError:
        contenido = None
    auditoria = auditor.de_borrador(f) if contenido is not None else None
    return pintar(request, "borrador.html", 200 if contenido is not None else 404, archivo=f, contenido=contenido,
                  auditoria=auditoria)
