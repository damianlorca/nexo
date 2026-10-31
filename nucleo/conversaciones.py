# -*- coding: utf-8 -*-
"""Indice de conversaciones web (ChatGPT, Gemini, Claude web) para retomarlas entre tareas (Bloque 8, 17/10).

Damian: las IAs web deben saber abrir un chat nuevo, seguir en el mismo si el tema es el mismo y retomar el
chat que ya tiene el contexto de un tema aunque sea de otra tarea. El indice se calcula de `conversaciones` de
cada tarea (memoria/tareas.json): NO se busca nada en la barra lateral de la web.

Regla (`buscar`): para una tarea SIN conversacion propia utilizable, se retoma la conversacion del MISMO
proveedor, con rol AUTOR, del mismo tema (etiqueta `tema:xxx`) y de la misma epica (`epica:Txxx`; sin epica solo
casa con conversaciones sin epica), con menos de MAX_DIAS desde su ultimo uso y menos de MAX_MENSAJES mensajes.
Sin tema no se retoma nada (no hay con que comparar). Los REVISORES (revisor de borradores, tribunal,
apelacion) NUNCA reutilizan conversacion: su independencia depende de no haber visto el trabajo antes.
Una URL marcada `estropeada` por cualquier tarea no se vuelve a ofrecer.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from nucleo import tareas as T

MAX_DIAS = 7
MAX_MENSAJES = 12
ROL_REUTILIZABLE = "autor"
_FORMATO = "%Y-%m-%d %H:%M:%S"


def _etiqueta(t: dict, prefijo: str) -> str | None:
    for e in t.get("etiquetas") or []:
        if e.startswith(prefijo):
            return e[len(prefijo):] or None
    return None


def tema_de(t: dict) -> str | None:
    return _etiqueta(t, "tema:")


def epica_de(t: dict) -> str | None:
    return _etiqueta(t, "epica:")


def _fecha(texto: str | None) -> datetime | None:
    try:
        return datetime.strptime((texto or "")[:19], _FORMATO)
    except ValueError:
        return None


def indice(tareas: list[dict] | None = None) -> list[dict]:
    """Conversaciones web ok, una fila por (proveedor, rol, tema, epica, url):
    {proveedor, rol, tema, epica, url, tareas: [ids], fecha: 'AAAA-MM-DD HH:MM:SS', mensajes}.
    `mensajes` = envios nuestros a esa URL en TODAS las tareas. Las URL estropeadas en alguna tarea no salen."""
    tareas = T.cargar(detalle=True)["tareas"] if tareas is None else tareas
    malas = {c.get("url") for t in tareas for c in (t.get("conversaciones") or {}).values()
             if isinstance(c, dict) and c.get("estado") == "estropeada" and c.get("url")}
    mensajes: dict[str, int] = {}
    ultima: dict[str, str] = {}
    for t in tareas:
        for c in (t.get("conversaciones") or {}).values():
            if isinstance(c, dict) and c.get("url"):
                mensajes[c["url"]] = mensajes.get(c["url"], 0) + int(c.get("usos") or 0)
                ultima[c["url"]] = max(ultima.get(c["url"], ""), c.get("actualizada") or "")
    filas: dict[tuple, dict] = {}
    for t in tareas:
        for clave, c in (t.get("conversaciones") or {}).items():
            if not isinstance(c, dict) or c.get("estado") != "ok" or not c.get("url") or c["url"] in malas:
                continue
            proveedor, _, rol = clave.partition(":")
            k = (proveedor, rol, tema_de(t), epica_de(t), c["url"])
            f = filas.setdefault(k, {"proveedor": proveedor, "rol": rol, "tema": k[2], "epica": k[3], "url": c["url"],
                                     "tareas": [], "fecha": ultima[c["url"]], "mensajes": mensajes[c["url"]]})
            f["tareas"].append(t["id"])
    return list(filas.values())


def buscar(tarea: dict, proveedor: str, rol: str, tareas: list[dict] | None = None,
           ahora: datetime | None = None) -> dict | None:
    """La conversacion que `tarea` puede retomar (fila del indice) o None -> chat nuevo."""
    if rol != ROL_REUTILIZABLE:       # revisores, tribunal, apelacion: nunca (independencia)
        return None
    tema = tema_de(tarea)
    if not tema:
        return None
    ahora = ahora or datetime.now()
    epica = epica_de(tarea)
    propia = tarea["id"].lower()
    buenas = []
    for f in indice(tareas):
        f_fecha = _fecha(f["fecha"])
        if (f["proveedor"] != proveedor or f["rol"] != rol or f["tema"] != tema or f["epica"] != epica
                or propia in (x.lower() for x in f["tareas"])
                or f_fecha is None or ahora - f_fecha >= timedelta(days=MAX_DIAS)
                or f["mensajes"] >= MAX_MENSAJES):
            continue
        buenas.append((f_fecha, -f["mensajes"], f))
    return max(buenas, key=lambda x: x[:2])[2] if buenas else None
