# -*- coding: utf-8 -*-
"""T290: chat dentro de cada tarea (ficha). La logica esta en nucleo.chat_tarea; aqui solo la web.

- Enviar responde al instante (el mensaje ya se ve y sale "Pensando..."); la respuesta llega por SSE.
- Deshacer, aprobar y denegar son rapidos: se hacen en la peticion y se repinta la conversacion.
- Todo POST pasa por el CSRF del middleware, como el resto de la web.
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request

from interfaz import humano as H
from interfaz import lecturas
from interfaz.vistas import pintar
from nucleo import chat_tarea as C

router = APIRouter()


def datos_chat(request: Request, id_tarea: str) -> dict:
    trabajador = request.app.state.chat
    pendiente = C.sin_contestar(id_tarea)
    return {"chat": C.conversacion(id_tarea), "pensando": trabajador.ocupada(id_tarea),
            "sin_contestar": pendiente, "hace": H.hace}


def _mensajes(request: Request, id_tarea: str, aviso: str = "", form: bool = False):
    t = lecturas.tarea(id_tarea)
    if t is None:
        return pintar(request, "_mensaje_error.html", motivo=f"La tarea {id_tarea} ya no existe.")
    resp = pintar(request, "_tarea_chat_mensajes.html", t=t, aviso_chat=aviso, form_oob=form,
                  **datos_chat(request, t["id"]))
    return resp


def _rechazo(request: Request, motivo: str):
    resp = pintar(request, "_mensaje_error.html", motivo=motivo)
    resp.headers["HX-Retarget"] = "#error-chat"
    resp.headers["HX-Reswap"] = "innerHTML"
    return resp


@router.get("/tareas/{id_tarea}/chat")
def mensajes(request: Request, id_tarea: str):
    try:
        return _mensajes(request, id_tarea)
    except C.ChatRechazado as e:
        return pintar(request, "_mensaje_error.html", motivo=str(e))


@router.post("/tareas/{id_tarea}/chat")
def enviar(request: Request, id_tarea: str, mensaje: str = Form(""), escalar: str = Form("")):
    try:
        request.app.state.chat.enviar(id_tarea, mensaje, escalar == "1")
    except C.ChatRechazado as e:
        return _rechazo(request, str(e))
    return _mensajes(request, id_tarea, form=True)


@router.post("/tareas/{id_tarea}/chat/{n}/reintentar")
def reintentar(request: Request, id_tarea: str, n: int):
    try:
        pendiente = C.sin_contestar(id_tarea)
    except C.ChatRechazado as e:
        return _rechazo(request, str(e))
    if pendiente is None or pendiente["n"] != n or request.app.state.chat.ocupada(id_tarea.upper()):
        return _rechazo(request, "Ese mensaje ya tiene respuesta o se está contestando.")
    from nucleo import parada
    if parada.activa() is not None:
        return _rechazo(request, "PARADA de emergencia activa: el chat no hace nada hasta pulsar «Seguir».")
    request.app.state.chat.procesar(id_tarea.upper(), n)
    return _mensajes(request, id_tarea)


def _decidir(request: Request, id_tarea: str, n: int, que):
    try:
        que()
    except C.ChatRechazado as e:
        return _rechazo(request, str(e))
    request.app.state.chat.publicar(id_tarea.upper())
    resp = _mensajes(request, id_tarea)
    resp.headers["HX-Trigger"] = "nexo:tareas"       # la ficha de arriba se repinta ya
    return resp


@router.post("/tareas/{id_tarea}/chat/{n}/deshacer")
def deshacer(request: Request, id_tarea: str, n: int):
    return _decidir(request, id_tarea, n, lambda: C.deshacer(id_tarea, n))


@router.post("/tareas/{id_tarea}/chat/{n}/aprobar")
def aprobar(request: Request, id_tarea: str, n: int):
    return _decidir(request, id_tarea, n, lambda: C.decidir(id_tarea, n, True))


@router.post("/tareas/{id_tarea}/chat/{n}/denegar")
def denegar(request: Request, id_tarea: str, n: int):
    return _decidir(request, id_tarea, n, lambda: C.decidir(id_tarea, n, False))
