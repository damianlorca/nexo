# -*- coding: utf-8 -*-
"""Chat de la tarea (T290) en segundo plano: el POST guarda el mensaje y responde al instante; lo que
tarda (Qwen interpreta, NVIDIA contesta...) va en un hilo y avisa por SSE (evento "chat").

UN solo hilo, en serie: Qwen es un modelo local y se carga uno cada vez. Si la web se reinicia con
un mensaje a medias, queda "sin contestar" en el historial y la ficha ofrece reintentarlo.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from interfaz.eventos import Bus
from nucleo import chat_tarea as C

log = logging.getLogger("uvicorn.error")


class ChatTrabajador:
    def __init__(self, bus: Bus):
        self.bus = bus
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chat")
        self._ocupadas: set[str] = set()
        self._candado = threading.Lock()

    def ocupada(self, tarea_id: str) -> bool:
        with self._candado:
            return tarea_id in self._ocupadas

    def enviar(self, tarea_id: str, texto: str, escalar: bool = False) -> dict:
        """ChatRechazado si no se acepta (texto vacio, PARADA...)."""
        m = C.enviar(tarea_id, texto, escalar)
        self.procesar(tarea_id.strip().upper(), m["n"])
        return m

    def procesar(self, tarea_id: str, n: int) -> None:
        with self._candado:
            self._ocupadas.add(tarea_id)
        self.publicar(tarea_id)
        self._pool.submit(self._trabajar, tarea_id, n)

    def _trabajar(self, tarea_id: str, n: int) -> None:
        try:
            C.procesar(tarea_id, n)
        except Exception as e:  # nunca tumba el hilo: el mensaje queda sin contestar y se puede reintentar
            log.warning("chat %s #%s fallo: %s", tarea_id, n, type(e).__name__)
        finally:
            with self._candado:
                self._ocupadas.discard(tarea_id)
            self.publicar(tarea_id)

    def publicar(self, tarea_id: str) -> None:
        self.bus.publicar("chat", {"tarea": tarea_id})

    def cerrar(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
