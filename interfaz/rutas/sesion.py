# -*- coding: utf-8 -*-
"""Entrada con el token de arranque, salida y healthcheck."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from interfaz.config import APP_ID
from interfaz.seguridad import COOKIE, DUENO, cookie_segura, identidad
from interfaz.vistas import pintar

router = APIRouter()


@router.get("/entrar")
def entrar(request: Request, t: str = ""):
    seg = request.app.state.seguridad

    if not t and seg.sesion(request.cookies.get(COOKIE)):
        return RedirectResponse("/", status_code=303)
    # Por Tailscale Serve con el login del dueno no hace falta token: "/" crea la sesion.
    if not t and identidad(request.scope, request.app.state.ajustes) == DUENO:
        return RedirectResponse("/", status_code=303)

    # Con el limite alcanzado ni se mira el token: asi no se puede seguir probando.
    if seg.limitado():
        return pintar(request, "rechazo.html", 429, titulo="Demasiados intentos",
                      texto="Espera un minuto y vuelve a abrir NEXO con abrir_nexo.bat.")

    if not t or not seg.token_valido(t):
        seg.fallo()
        return pintar(request, "rechazo.html", 401, titulo="Token no válido",
                      texto="El token no es el de este arranque. Ábrela con interfaz\\scripts\\abrir_nexo.bat.")

    sid = seg.crear_sesion()
    # 200 + meta refresh (no 303): la navegacion a / sale ya de 127.0.0.1, asi la cookie
    # SameSite=Strict viaja seguro aunque el .bat abra el navegador desde fuera.
    resp = pintar(request, "entrar.html")
    resp.set_cookie(COOKIE, sid, httponly=True, samesite="strict",
                    secure=cookie_segura(request.scope, request.app.state.ajustes), path="/")
    return resp


@router.post("/salir")
def salir(request: Request):
    request.app.state.seguridad.cerrar(request.state.sid)
    resp = Response(status_code=204, headers={"HX-Redirect": "/entrar"})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@router.get("/salud")
def salud():
    return JSONResponse({"ok": True, "app": APP_ID})
