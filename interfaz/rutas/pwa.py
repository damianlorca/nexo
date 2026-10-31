# -*- coding: utf-8 -*-
"""App instalable en el movil (hito movil): manifest, service worker y pagina "sin conexion".

Las tres rutas son publicas (el navegador pide manifest y SW sin cookie) y no llevan ningun dato.
El SW va en /sw.js y no en /estatico/ porque su alcance es su carpeta: tiene que ser "/".
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from interfaz.vistas import DIR, pintar

router = APIRouter()

FONDO = "#0f1115"   # --fondo del tema oscuro (nexo.css): la pantalla de arranque de la app

MANIFEST = {
    "id": "/",
    "name": "NEXO",
    "short_name": "NEXO",
    "description": "Centro de control de NEXO",
    "lang": "es",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": FONDO,
    "theme_color": FONDO,
    "icons": [
        {"src": "/estatico/iconos/nexo-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/estatico/iconos/nexo-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "/estatico/iconos/nexo-maskable-192.png", "sizes": "192x192", "type": "image/png",
         "purpose": "maskable"},
        {"src": "/estatico/iconos/nexo-maskable-512.png", "sizes": "512x512", "type": "image/png",
         "purpose": "maskable"},
    ],
}


@router.get("/manifest.webmanifest")
def manifest():
    return JSONResponse(MANIFEST, media_type="application/manifest+json")


@router.get("/sw.js")
def service_worker():
    codigo = (DIR / "estatico" / "sw.js").read_text(encoding="utf-8")
    return Response(codigo, media_type="text/javascript")


@router.get("/sin-conexion")
def sin_conexion(request: Request):
    return pintar(request, "sin_conexion.html")
