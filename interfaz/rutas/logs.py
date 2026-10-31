# -*- coding: utf-8 -*-
"""Logs: las lineas de registros/*.jsonl (filtrables, con limite y SIN secretos) y los borradores.

La lista se lee siempre de disco (lecturas.lineas_log) y se recarga con los eventos SSE "log":
asi nunca depende del buffer del bus. Si el bus tuvo que desalojar lineas mientras el navegador
estaba desconectado, el SSE manda "logs_perdidos": la pantalla lo dice con la hora (aviso) y la
lista se recarga desde disco, donde siguen estando.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Request

from interfaz import lecturas
from interfaz.vistas import pintar, pintar_panel

router = APIRouter()


def _filtros(fuente: str, proveedor: str, estado: str, limite: int) -> dict:
    return {"fuente": fuente if fuente in lecturas.FUENTES_LOG else "",
            "proveedor": proveedor.strip()[:40], "estado": estado.strip()[:40],
            "limite": limite if limite in lecturas.LIMITES_LOGS else lecturas.LIMITES_LOGS[1]}


@router.get("/logs")
def pagina(request: Request, fuente: str = "", proveedor: str = "", estado: str = "", limite: int = 100):
    return pintar(request, "logs.html", f=_filtros(fuente, proveedor, estado, limite),
                  fuentes=lecturas.FUENTES_LOG, limites=lecturas.LIMITES_LOGS, proveedores=lecturas.nombres_proveedores())


@router.get("/logs/lista")
def lista(request: Request, fuente: str = "", proveedor: str = "", estado: str = "", limite: int = 100):
    f = _filtros(fuente, proveedor, estado, limite)
    return pintar_panel(request, "_logs_lista.html", "/logs/lista", lambda: {**lecturas.lineas_log(**f), "f": f})


@router.get("/logs/borradores")
def borradores(request: Request):
    return pintar_panel(request, "_logs_borradores.html", "/logs/borradores",
                        lambda: {"borradores": lecturas.borradores_recientes()})


@router.get("/logs/perdidos")
def perdidos(request: Request):
    return pintar(request, "_logs_perdidos.html", cuando=time.time())
