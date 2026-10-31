# -*- coding: utf-8 -*-
"""Notificaciones push al movil (hito movil, Web Push con VAPID).

Todo vive en memoria/push/ (en .gitignore, nunca al repo ni al espejo de la nube):
  vapid_privada.pem   clave privada VAPID (se genera UNA vez, la primera vez que hace falta)
  suscripciones.json  navegadores suscritos (endpoint + claves del navegador)

Que se avisa (lo escucha del bus de eventos, sin tocar el core):
  - "orden"  con estado hecha/error  -> "Orden W12 · T185 terminada" + frase corta de la orden
  - "parada"                         -> "PARADA activada" + motivo / "PARADA quitada"
  - "turno"  con fallos reales       -> "Turno nocturno: 2 fallos" + pasos
Contenido: tipo + id + frase corta, SIEMPRE pasada por ocultar.texto (OK de Damian, 25/09).

Anti-spam (Damian, 25/09): como mucho 1 push por orden y 1 por turno; si en 60 s ya salieron 5,
lo que llegue se AGRUPA en un unico push al acabar la ventana.
Suscripciones caducadas (404/410 del servidor push) se borran.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

from interfaz import ocultar

log = logging.getLogger("uvicorn.error")

# El "sub" de VAPID lo ve el servidor push (Google): nada de datos de Damian.
CONTACTO = "mailto:nexo@localhost"
TTL = 24 * 3600
MAX_POR_VENTANA = 5
VENTANA = 60.0
LARGO_FRASE = 70
MAX_SUSCRIPCIONES = 20
MAX_YA_AVISADOS = 2000
# Solo se envia a servidores push conocidos: la web no hace POST a una URL cualquiera.
SERVIDORES_PUSH = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "push.apple.com",
                   "notify.windows.com")
ORDEN_FINAL = {"hecha": "terminada", "error": "con error"}


def frase(texto: str, largo: int = LARGO_FRASE) -> str:
    """Frase corta para la pantalla de bloqueo: sin secretos (ocultar ANTES de recortar) y en una linea."""
    limpio = " ".join(ocultar.texto(texto or "").split())
    return limpio if len(limpio) <= largo else limpio[:largo - 1].rstrip() + "…"


def endpoint_valido(endpoint: str) -> bool:
    try:
        p = urlsplit(endpoint)
    except ValueError:
        return False
    host = (p.hostname or "").lower()
    return (p.scheme == "https" and len(endpoint) <= 2000
            and any(host == s or host.endswith("." + s) for s in SERVIDORES_PUSH))


def suscripcion_valida(s) -> bool:
    if not isinstance(s, dict) or not endpoint_valido(s.get("endpoint", "")):
        return False
    claves = s.get("keys")
    return (isinstance(claves, dict)
            and all(isinstance(claves.get(k), str) and 0 < len(claves[k]) <= 200 for k in ("p256dh", "auth")))


# ------------------------------------------------------------------ almacen
class Almacen:
    def __init__(self, carpeta: Path):
        self.carpeta = carpeta
        self._candado = threading.Lock()

    @property
    def _fichero(self) -> Path:
        return self.carpeta / "suscripciones.json"

    @property
    def clave_privada(self) -> Path:
        return self.carpeta / "vapid_privada.pem"

    def _leer(self) -> list[dict]:
        try:
            datos = json.loads(self._fichero.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [s for s in datos if suscripcion_valida(s)] if isinstance(datos, list) else []

    def _escribir(self, subs: list[dict]) -> None:
        self.carpeta.mkdir(parents=True, exist_ok=True)
        tmp = self._fichero.with_suffix(".tmp")
        tmp.write_text(json.dumps(subs, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self._fichero)

    def todas(self) -> list[dict]:
        with self._candado:
            return self._leer()

    def guardar(self, sub: dict) -> None:
        limpia = {"endpoint": sub["endpoint"],
                  "keys": {"p256dh": sub["keys"]["p256dh"], "auth": sub["keys"]["auth"]},
                  "alta": time.strftime("%Y-%m-%d %H:%M:%S")}
        with self._candado:
            subs = [s for s in self._leer() if s["endpoint"] != sub["endpoint"]]
            subs.append(limpia)
            self._escribir(subs[-MAX_SUSCRIPCIONES:])

    def quitar(self, endpoint: str) -> bool:
        with self._candado:
            subs = self._leer()
            quedan = [s for s in subs if s["endpoint"] != endpoint]
            if len(quedan) != len(subs):
                self._escribir(quedan)
            return len(quedan) != len(subs)

    # ------------------------------------------------------------- VAPID
    def clave_publica(self) -> str:
        """applicationServerKey para el navegador (base64url del punto sin comprimir). Genera las
        claves la primera vez."""
        from cryptography.hazmat.primitives import serialization
        from py_vapid import Vapid01
        from py_vapid.utils import b64urlencode
        with self._candado:
            if self.clave_privada.exists():
                v = Vapid01.from_file(str(self.clave_privada))
            else:
                self.carpeta.mkdir(parents=True, exist_ok=True)
                v = Vapid01()
                v.generate_keys()
                v.save_key(str(self.clave_privada))
                log.info("push: claves VAPID generadas en memoria/push/")
        crudo = v.public_key.public_bytes(serialization.Encoding.X962,
                                          serialization.PublicFormat.UncompressedPoint)
        return b64urlencode(crudo)


def webpush_real(sub: dict, datos: str, clave_privada: Path, urgencia: str) -> int:
    """Envia con pywebpush. Devuelve el codigo HTTP del servidor push (201 = aceptado)."""
    from pywebpush import WebPushException, webpush
    try:
        r = webpush(subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]}, data=datos,
                    vapid_private_key=str(clave_privada), vapid_claims={"sub": CONTACTO}, ttl=TTL,
                    headers={"Urgency": urgencia}, timeout=15)
        return getattr(r, "status_code", 201)
    except WebPushException as e:
        return getattr(e.response, "status_code", 0) or 0


# --------------------------------------------------------------- notificador
class Notificador:
    """Traduce eventos del bus en avisos, aplica el anti-spam y envia en segundo plano."""

    def __init__(self, almacen: Almacen, buscar_orden=None, enviar=webpush_real, ejecutor=None,
                 reloj=time.monotonic, temporizador=threading.Timer):
        self.almacen = almacen
        self._buscar_orden = buscar_orden or (lambda _id: None)
        self._enviar = enviar
        self._ejecutor = ejecutor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="push")
        self._reloj = reloj
        self._temporizador = temporizador
        self._candado = threading.Lock()
        self._enviados: deque[float] = deque()
        self._pendientes: list[dict] = []
        self._timer = None
        # "orden:W12", "turno:turno_nexo_...json" -> None. Ordenado por llegada: al pasar del tope se
        # tiran las MAS ANTIGUAS (un set no tiene orden y podia tirar la recien anadida).
        self._ya_avisados: OrderedDict[str, None] = OrderedDict()
        self._cerrado = False

    # ------------------------------------------------ eventos -> avisos
    def oir(self, evento) -> None:
        """Oyente del bus (se llama en el hilo que publica: aqui no se bloquea nunca)."""
        try:
            aviso = self.aviso_de(evento.tipo, evento.datos)
        except Exception as e:  # un evento raro nunca rompe el bus
            log.warning("push: evento %s no se pudo traducir: %s", evento.tipo, type(e).__name__)
            return
        if aviso is not None:
            self.avisar(aviso)

    def aviso_de(self, tipo: str, datos: dict) -> dict | None:
        if tipo == "orden":
            final = ORDEN_FINAL.get(datos.get("estado"))
            clave = f"orden:{datos.get('id')}"
            if not final or not self._primera_vez(clave):
                return None
            orden = self._buscar_orden(datos.get("id")) or {}
            tarea = (orden.get("resultado") or {}).get("tarea")
            ident = datos["id"] + (f" · {tarea}" if tarea else "")
            return {"titulo": f"Orden {ident} {final}", "cuerpo": frase(orden.get("texto", "")),
                    "ruta": "/ordenes", "etiqueta": clave, "urgencia": "normal"}
        if tipo == "parada":
            if datos.get("activa"):
                return {"titulo": "PARADA activada", "cuerpo": frase(datos.get("motivo") or "sin motivo"),
                        "ruta": "/", "etiqueta": "parada", "urgencia": "high"}
            return {"titulo": "PARADA quitada", "cuerpo": "NEXO vuelve a aceptar órdenes.",
                    "ruta": "/", "etiqueta": "parada", "urgencia": "high"}
        if tipo == "turno":
            fallos = datos.get("fallos") or []
            if datos.get("avisado"):   # T231: el propio turno ya aviso (resumen con sus fallos)
                return None
            if not fallos or not self._primera_vez(f"turno:{datos.get('nombre')}"):
                return None
            n = len(fallos)
            return {"titulo": f"Turno nocturno: {n} fallo{'s' if n != 1 else ''}",
                    "cuerpo": frase(", ".join(fallos)), "ruta": "/logs",
                    "etiqueta": f"turno:{datos.get('nombre')}", "urgencia": "normal"}
        if tipo == "aprobacion":
            # T751: aprobacion ambar nueva (antes solo la avisaba Telegram). La frase ya viene pasada por ocultar.
            clave = f"aprobacion:{datos.get('id')}"
            if not datos.get("id") or not self._primera_vez(clave):
                return None
            origen = f" ({datos['origen']})" if datos.get("origen") else ""
            return {"titulo": f"Aprobación {datos['id']}{origen}", "cuerpo": frase(datos.get("frase") or ""),
                    "ruta": "/bandejas#bandeja-ambar", "etiqueta": clave, "urgencia": "high"}
        if tipo == "aviso":
            # T189: delegacion bloqueada por el auditor / ningun proveedor con Pensar-Pro (nucleo/avisos.py).
            clave = f"aviso:{datos.get('nombre') or datos.get('clave')}"
            if not self._primera_vez(clave):
                return None
            ruta = datos.get("ruta") or "/"
            return {"titulo": frase(datos.get("titulo") or "Aviso de NEXO"), "cuerpo": frase(datos.get("cuerpo") or ""),
                    "ruta": ruta if ruta.startswith("/") else "/", "etiqueta": clave, "urgencia": "high"}
        return None

    def _primera_vez(self, clave: str) -> bool:
        with self._candado:
            if clave in self._ya_avisados:
                return False
            self._ya_avisados[clave] = None
            while len(self._ya_avisados) > MAX_YA_AVISADOS:   # memoria acotada
                self._ya_avisados.popitem(last=False)
            return True

    # --------------------------------------------------- anti-spam
    def avisar(self, aviso: dict) -> None:
        with self._candado:
            ahora = self._reloj()
            while self._enviados and self._enviados[0] <= ahora - VENTANA:
                self._enviados.popleft()
            if len(self._enviados) < MAX_POR_VENTANA and not self._pendientes:
                self._enviados.append(ahora)
                self._ejecutor.submit(self._enviar_a_todos, aviso)
                return
            self._pendientes.append(aviso)
            if self._timer is None:
                espera = max(0.0, self._enviados[0] + VENTANA - ahora) if self._enviados else 0.0
                self._timer = self._temporizador(espera, self._vaciar)
                self._timer.daemon = True
                self._timer.start()

    def _vaciar(self) -> None:
        with self._candado:
            pendientes, self._pendientes, self._timer = self._pendientes, [], None
            if not pendientes or self._cerrado:
                return
            self._enviados.append(self._reloj())
        aviso = pendientes[0] if len(pendientes) == 1 else agrupar(pendientes)
        try:
            self._ejecutor.submit(self._enviar_a_todos, aviso)
        except RuntimeError:
            # La web se cerro entre medias (cancel() no para un Timer que ya ha saltado): se pierde
            # el agrupado, como cualquier aviso en cola al apagar; sin traza en el log.
            log.info("push: web cerrandose, agrupado de %d avisos no enviado", len(pendientes))

    # ------------------------------------------------------ envio
    def _enviar_a_todos(self, aviso: dict) -> dict:
        datos = json.dumps({k: aviso[k] for k in ("titulo", "cuerpo", "ruta", "etiqueta")}, ensure_ascii=False)
        resultado = {"enviados": 0, "caducadas": 0, "fallos": 0}
        for sub in self.almacen.todas():
            try:
                codigo = self._enviar(sub, datos, self.almacen.clave_privada, aviso.get("urgencia", "normal"))
            except Exception as e:
                log.warning("push: envio fallido: %s", type(e).__name__)
                codigo = 0
            if codigo in (404, 410):
                self.almacen.quitar(sub["endpoint"])
                resultado["caducadas"] += 1
            elif 200 <= codigo < 300:
                resultado["enviados"] += 1
            else:
                log.warning("push: el servidor push respondio %s", codigo)
                resultado["fallos"] += 1
        return resultado

    def prueba(self) -> dict:
        """'Enviar prueba' de Ajustes: directo (sin anti-spam), en el hilo de quien llama."""
        self.almacen.clave_publica()   # por si aun no hay claves
        return self._enviar_a_todos({"titulo": "NEXO: prueba", "cuerpo": "Las notificaciones funcionan.",
                                     "ruta": "/ajustes", "etiqueta": "prueba", "urgencia": "normal"})

    def cerrar(self) -> None:
        with self._candado:
            self._cerrado = True
            if self._timer is not None:
                self._timer.cancel()
        self._ejecutor.shutdown(wait=False, cancel_futures=True)


def agrupar(avisos: list[dict]) -> dict:
    # La PARADA primero: es lo que mas importa si se mezcla con otras cosas.
    orden = sorted(avisos, key=lambda a: 0 if a["etiqueta"] == "parada" else 1)
    return {"titulo": f"NEXO: {len(avisos)} avisos", "cuerpo": frase(" · ".join(a["titulo"] for a in orden), 120),
            "ruta": "/", "etiqueta": "agrupado",
            "urgencia": "high" if any(a.get("urgencia") == "high" for a in avisos) else "normal"}
