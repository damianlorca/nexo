# -*- coding: utf-8 -*-
"""T251: pestaña Grafo. /grafo pinta la pagina (filtros vacios) y /grafo/datos da el grafo en node-link.

Solo lectura. El dibujo y los filtros van en el navegador (estatico/grafo.js con vis-network vendorizado):
filtrar no vuelve a pedir nada al servidor, asi va fluido con cientos de nodos y en el movil.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from interfaz import grafo, humano as H
from interfaz.vistas import pintar

router = APIRouter()
log = logging.getLogger("uvicorn.error")


@router.get("/grafo")
def pagina(request: Request):
    return pintar(request, "grafo.html", grupos=H.GRUPOS, tipos=grafo.TIPOS)


@router.get("/grafo/datos")
def datos():
    try:
        g = grafo.construir()
    except Exception as e:  # tareas.json roto o ilegible: la pagina ofrece reintentar
        log.warning("grafo: no se pudo construir: %s", type(e).__name__)
        return JSONResponse({"error": "No se ha podido leer el estado de NEXO."}, status_code=503,
                            headers={"cache-control": "no-store"})
    return JSONResponse(g, headers={"cache-control": "no-store"})
