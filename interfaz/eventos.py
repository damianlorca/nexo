# -*- coding: utf-8 -*-
"""Bus de eventos para el SSE: buffer en memoria con id incremental y replay (Last-Event-ID).

Un solo usuario: bastan buffers en memoria. Los ids son "<arranque>-<n>": si el navegador
reconecta con un id de OTRO arranque (la web se reinicio) o con un hueco de eventos criticos
que ya no se pueden reenviar, se le pide "reconciliar" (recargar el estado entero). Las lineas
de log van en un buffer aparte, desalojable, que nunca puede expulsar a los criticos.

publicar() se puede llamar desde cualquier hilo (el trabajador de ordenes corre en hilos);
el aviso a los que esperan se hace siempre en el hilo del event loop.
"""
from __future__ import annotations

import asyncio
import secrets
import threading
from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Evento:
    n: int
    id: str
    tipo: str
    datos: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Replay:
    desde: int              # numero del ultimo evento que el cliente queda teniendo
    eventos: list[Evento]   # lo que hay que reenviarle, en orden
    reconciliar: bool       # se perdio algo NO desalojable (u otro arranque): recargar el estado entero
    logs_perdidos: bool     # solo se perdieron lineas de log: la vista de logs debe recargarse


# Solo las lineas de log se pueden desalojar: llegan a rafagas y se pueden releer del .jsonl.
# Todo lo demas (parada, tareas, borrador, ordenes...) va a un buffer propio que los logs no
# pueden vaciar: asi una rafaga de logs nunca tira el ultimo evento de PARADA (seguridad).
DESALOJABLES = frozenset({"log"})


class Bus:
    def __init__(self, capacidad_logs: int = 500, capacidad_criticos: int = 200):
        self.arranque = secrets.token_hex(4)
        self._n = 0
        self._logs: deque[Evento] = deque()
        self._criticos: deque[Evento] = deque()
        self._capacidad = {"logs": capacidad_logs, "criticos": capacidad_criticos}
        # Numero del ultimo evento expulsado de cada buffer (0 = nunca se ha expulsado nada).
        self._expulsado = {"logs": 0, "criticos": 0}
        self._candado = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._senal: asyncio.Event | None = None
        self._oyentes: list = []

    def oir(self, oyente) -> None:
        """oyente(evento) tras cada publicar(), en el hilo que publica: tiene que ser rapido y no
        bloquear (el de push solo encola). Un oyente que falla no afecta al bus ni a los demas."""
        self._oyentes.append(oyente)

    def iniciar(self, loop: asyncio.AbstractEventLoop) -> None:
        """Llamar desde el event loop al arrancar la app."""
        self._loop = loop
        self._senal = asyncio.Event()

    # ------------------------------------------------------------ publicar
    def publicar(self, tipo: str, datos: dict | None = None) -> Evento:
        with self._candado:
            self._n += 1
            ev = Evento(self._n, f"{self.arranque}-{self._n}", tipo, datos or {})
            clase = "logs" if tipo in DESALOJABLES else "criticos"
            buffer = self._logs if clase == "logs" else self._criticos
            buffer.append(ev)
            if len(buffer) > self._capacidad[clase]:
                self._expulsado[clase] = buffer.popleft().n
        self._avisar()
        for oyente in list(self._oyentes):
            try:
                oyente(ev)
            except Exception:
                pass
        return ev

    def _avisar(self) -> None:
        if self._loop is None:
            return
        try:
            en_loop = asyncio.get_running_loop() is self._loop
        except RuntimeError:
            en_loop = False
        if en_loop:
            self._despertar()
        else:
            try:
                self._loop.call_soon_threadsafe(self._despertar)
            except RuntimeError:
                pass  # loop cerrado (apagando): nadie escucha ya

    def _despertar(self) -> None:
        viejo, self._senal = self._senal, asyncio.Event()
        if viejo is not None:
            viejo.set()

    # --------------------------------------------------------------- leer
    @property
    def ultimo_id(self) -> str:
        with self._candado:
            return f"{self.arranque}-{self._n}"

    def _despues(self, n: int) -> list[Evento]:
        # Llamar con el candado cogido. Los dos buffers mezclados en orden de numero.
        return sorted((e for b in (self._logs, self._criticos) for e in b if e.n > n), key=lambda e: e.n)

    def despues(self, n: int) -> list[Evento]:
        with self._candado:
            return self._despues(n)

    def replay(self, ultimo_id: str | None) -> Replay:
        """Que reenviar a quien reconecta con `ultimo_id` y si puede ponerse al dia sin recargar.

        Sin ultimo_id: solo lo nuevo a partir de ahora. Un hueco se detecta por lo EXPULSADO de
        cada buffer (con dos buffers, el mas antiguo de uno no dice nada del otro).
        """
        arranque, _, num = (ultimo_id or "").partition("-")
        with self._candado:
            actual = self._n
            if not ultimo_id:
                return Replay(actual, [], False, False)
            if arranque != self.arranque or not num.isdigit() or int(num) > actual:
                return Replay(actual, [], True, False)  # otro arranque o id imposible
            n = int(num)
            if self._expulsado["criticos"] > n:
                return Replay(actual, [], True, False)
            return Replay(actual, self._despues(n), False, self._expulsado["logs"] > n)

    async def esperar(self, n: int, timeout: float) -> list[Evento]:
        """Eventos con numero > n; si no hay, espera hasta timeout a que llegue alguno."""
        nuevos = self.despues(n)
        if nuevos:
            return nuevos
        if self._senal is None:
            # Bus sin iniciar (app sin lifespan): sin esto el SSE giraria en vacio a tope de CPU.
            await asyncio.sleep(timeout)
            return self.despues(n)
        senal = self._senal
        try:
            await asyncio.wait_for(senal.wait(), timeout)
        except asyncio.TimeoutError:
            pass
        return self.despues(n)
