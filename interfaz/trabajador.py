# -*- coding: utf-8 -*-
"""Ejecuta las ordenes de la web en segundo plano: nucleo.ordenes.procesar(texto, canal="web", ...).

- Instantanea: trabajar=True (si es delegable hace borrador + revisor: puede tardar MINUTOS).
- Bloque:      trabajar=False (solo la da de alta y la triaja; la trabaja un turno despues).
El POST responde al instante con la orden "en cola"; el resultado llega por SSE (evento "orden").

UN solo hilo, en serie, a proposito: el triaje usa Qwen (un modelo cargado cada vez) y
ordenes.procesar() cambia trabajo.candidatas a nivel de modulo mientras trabaja, asi que dos
ordenes a la vez se pisarian. Con PARADA activa no se acepta ninguna, y una que estuviera en
cola cuando se activo no arranca. Si la web se reinicia con una orden a medias, esta se pierde
de esta lista (la tarea ya dada de alta por el core sigue en tareas.json).
"""
from __future__ import annotations

import itertools
import logging
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from interfaz.eventos import Bus
from nucleo import ordenes, parada

MODOS = ("instantanea", "bloque")
MAX_RECORDADAS = 50
FINALES = ("hecha", "error", "cancelada")

log = logging.getLogger("uvicorn.error")


def _ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class OrdenRechazada(Exception):
    """La orden no se acepta (PARADA activa, texto invalido...). El mensaje es para Damian."""


class Trabajador:
    def __init__(self, bus: Bus):
        self.bus = bus
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="orden")
        self._ordenes: OrderedDict[str, dict] = OrderedDict()
        self._contador = itertools.count(1)
        self._candado = threading.Lock()

    # ------------------------------------------------------------ enviar
    def enviar(self, texto: str, modo: str) -> dict:
        texto = (texto or "").strip()
        if modo not in MODOS:
            raise OrdenRechazada("Modo de orden desconocido.")
        if not 4 <= len(texto) <= 4000:
            raise OrdenRechazada("La orden debe tener entre 4 y 4000 caracteres.")
        motivo = parada.activa()
        if motivo is not None:
            raise OrdenRechazada(f"PARADA de emergencia activa ({motivo}): no se aceptan órdenes hasta pulsar «Seguir».")
        with self._candado:
            orden = {"id": f"W{next(self._contador)}", "texto": texto, "modo": modo, "estado": "en_cola",
                     "creada": _ahora(), "terminada": "", "resultado": None, "error": ""}
            self._ordenes[orden["id"]] = orden
            self._recortar()
            # Copia ANTES del submit: despues, el hilo puede haber pasado ya la orden a en_curso y la
            # tarjeta de respuesta saldria "Trabajando" en vez de "En cola" (N02, test_ordenes intermitente).
            copia = dict(orden)
        self._publicar(copia)
        self._pool.submit(self._ejecutar, orden["id"])
        return copia

    # ------------------------------------------------------------- leer
    def orden(self, id_orden: str) -> dict | None:
        with self._candado:
            o = self._ordenes.get(id_orden)
            return dict(o) if o else None

    def recientes(self) -> list[dict]:
        with self._candado:
            return [dict(o) for o in reversed(self._ordenes.values())]

    def cerrar(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ---------------------------------------------------------- ejecutar
    def _recortar(self) -> None:
        """Con el candado cogido. Solo se olvidan ordenes TERMINADAS (las mas antiguas): una en
        cola o en curso que saliera de la lista ya no se ejecutaria (_ejecutar no la encontraria)."""
        sobran = len(self._ordenes) - MAX_RECORDADAS
        if sobran > 0:
            for viejo in [k for k, o in self._ordenes.items() if o["estado"] in FINALES][:sobran]:
                del self._ordenes[viejo]

    def _cambiar(self, id_orden: str, **campos) -> dict | None:
        with self._candado:
            o = self._ordenes.get(id_orden)
            if o is None:
                return None
            o.update(campos)
            copia = dict(o)
            if o["estado"] in FINALES:
                self._recortar()
        self._publicar(copia)
        return copia

    def _publicar(self, orden: dict) -> None:
        self.bus.publicar("orden", {"id": orden["id"], "estado": orden["estado"]})

    def _ejecutar(self, id_orden: str) -> None:
        o = self.orden(id_orden)
        if o is None:
            return
        # Se comprueba otra vez al arrancar: la PARADA pudo activarse mientras esperaba en cola.
        motivo = parada.activa()
        if motivo is not None:
            self._cambiar(id_orden, estado="cancelada", terminada=_ahora(),
                          error=f"No se ejecutó: se activó la PARADA ({motivo}) mientras esperaba en cola.")
            return
        self._cambiar(id_orden, estado="en_curso")
        try:
            r = ordenes.procesar(o["texto"], canal="web", trabajar=o["modo"] == "instantanea")
        except Exception as e:
            log.warning("orden %s fallo: %s", id_orden, type(e).__name__)
            self._cambiar(id_orden, estado="error", terminada=_ahora(),
                          error=f"El core falló al procesarla ({type(e).__name__}). Detalle en el log de la web.")
            return
        self._cambiar(id_orden, estado="hecha", terminada=_ahora(), resultado=r)
