# -*- coding: utf-8 -*-
"""Vigila lo que el core YA escribe en disco y lo convierte en eventos del bus (sin tocar el core).

Cada `intervalo` segundos, en un hilo (la E/S de disco no bloquea el event loop):
  - memoria/PARADA_NEXO   -> "parada"  {activa, motivo}      (tambien si la pone Telegram)
  - memoria/tareas.json   -> "tareas"  {}                    (por mtime)
  - registros/{trazas,evidencia,uso_proveedores}.jsonl -> "log" {fuente, linea} por linea nueva
    (la linea pasa por ocultar.valor: nada con pinta de secreto sale por el SSE)
  - memoria/borradores/*.md nuevos -> "borrador" {nombre}
  - registros/turno_nexo_*.json nuevos -> "turno" {nombre, fallos}   (hito movil: push si hay fallos)
  - memoria/avisos/aviso_*.json nuevos -> "aviso" {tipo, titulo, cuerpo, ruta, clave}  (T189: push siempre;
    delegacion bloqueada por el auditor o ningun proveedor con el modo Pensar/Pro)
  - cada CADA_COLA s, la cola de revision de Claude (T192, nucleo.revision.comprobar_cola): si hay
    >= 5 borradores esperando o alguno pasa de 7 dias deja un aviso (uno al dia) -> "aviso" -> push.
    fallos = pasos con error real + handoff_error; los "saltado: ..." (PARADA, tope, RAM, cierre de
    las 04:20) NO cuentan (decision de Damian, 25/09). Un fichero a medio escribir se reintenta.
La primera pasada solo toma la foto inicial: no emite nada ni reenvia el historico.
Las rutas se leen del core en cada pasada (asi los tests pueden redirigirlas).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date
from pathlib import Path

from interfaz import ocultar
from interfaz.eventos import Bus
from interfaz.lecturas import FUENTES_LOG, estado_parada
from nucleo import aprobaciones, avisos, planificador, registro, revision, tareas, trabajo

MAX_BYTES_PASADA = 1_000_000      # por fichero y pasada; lo que sobre sale en la siguiente
MAX_LINEAS_PASADA = 200
MAX_CARACTERES_LINEA = 8000

CADA_APARCADAS = 300.0              # s entre comprobaciones de tareas aparcadas que vuelven (T230)
CADA_COLA = 600.0                   # s entre comprobaciones de la cola de revision (T192)
CADA_LATIDO = 60.0                  # s entre latidos de la cola de aprobaciones (plazos parados con el PC apagado)
REINTENTOS_TURNO = 10               # pasadas esperando a que un turno_nexo_*.json se pueda leer

log = logging.getLogger("uvicorn.error")


def fallos_turno(datos: dict) -> list[str]:
    """Nombres de los pasos con fallo REAL (no los saltados) y 'handoff' si fallo el aviso final."""
    fallos = []
    pasos = datos.get("pasos") if isinstance(datos, dict) else None
    for nombre, r in (pasos or {}).items():
        err = r.get("error") if isinstance(r, dict) else None
        if err and not str(err).startswith("saltado"):
            fallos.append(str(nombre))
    if isinstance(datos, dict) and datos.get("handoff_error"):
        fallos.append("handoff")
    return fallos


def _mtime(ruta: Path) -> float | None:
    try:
        return ruta.stat().st_mtime
    except OSError:
        return None


def _linea(bruta: bytes) -> dict:
    """La linea ya sin secretos: el evento viaja tal cual al navegador por el SSE."""
    return ocultar.valor(_leer_linea(bruta))


def _leer_linea(bruta: bytes) -> dict:
    texto = bruta.decode("utf-8", errors="replace").strip()
    if len(texto) > MAX_CARACTERES_LINEA:
        # Ocultar ANTES de recortar: un corte en mitad de una clave dejaria un trozo sin reconocer.
        return {"texto": ocultar.texto(texto)[:MAX_CARACTERES_LINEA] + "…", "recortada": True}
    try:
        obj = json.loads(texto)
    except ValueError:
        return {"texto": texto}
    return obj if isinstance(obj, dict) else {"texto": texto}


class Vigilante:
    def __init__(self, bus: Bus, intervalo: float = 1.0, planificar: bool = False):
        self.bus = bus
        self.planificar = planificar          # T231: solo la web de produccion lanza turnos
        self._plan_ultima: float | None = None
        self.intervalo = intervalo
        self._parada: tuple | None = None
        self._tareas: float | None = None
        self._iniciado = False
        self._offsets: dict[str, int] = {}
        self._saltando: set[str] = set()
        self._borradores: set[str] | None = None
        self._turnos: set[str] | None = None
        self._turnos_reintentos: dict[str, int] = {}
        self._avisos: set[str] | None = None
        self._cola_ultima: float | None = None
        self._aparcadas_ultima: float | None = None
        self._aprob_mtime: float | None = None
        self._aprob_vistas: set[str] | None = None
        self._latido_ultimo: float | None = None

    # ------------------------------------------------------------ pasada
    def revisar(self) -> list[tuple[str, dict]]:
        # Cada comprobacion por separado: si una falla (un .jsonl bloqueado en Windows...), las
        # demas ya han dado su cambio por visto y sus eventos NO se pueden perder con ella.
        eventos: list[tuple[str, dict]] = []
        for comprobar in (self._revisar_parada, self._revisar_tareas, self._revisar_logs, self._revisar_borradores,
                          self._revisar_turnos, self._revisar_aparcadas, self._revisar_avisos, self._revisar_cola,
                          self._latir_aprobaciones, self._revisar_aprobaciones, self._revisar_planificador):
            try:
                eventos += comprobar()
            except Exception as e:
                log.warning("vigilancia: %s fallo: %s", comprobar.__name__, type(e).__name__)
        self._iniciado = True
        return eventos

    def _revisar_parada(self) -> list[tuple[str, dict]]:
        e = estado_parada()
        clave = (e["activa"], e.get("motivo"), e.get("cuando"))
        cambio = self._iniciado and clave != self._parada
        self._parada = clave
        return [("parada", {"activa": e["activa"], "motivo": e.get("motivo", "")})] if cambio else []

    def _revisar_tareas(self) -> list[tuple[str, dict]]:
        mt = _mtime(tareas.ALMACEN)
        cambio = self._iniciado and mt != self._tareas
        self._tareas = mt
        return [("tareas", {})] if cambio else []

    def _revisar_logs(self) -> list[tuple[str, dict]]:
        eventos = []
        for fuente in FUENTES_LOG:
            ruta = registro.CARPETA / f"{fuente}.jsonl"
            try:
                tam = ruta.stat().st_size
            except OSError:
                self._offsets.pop(fuente, None)
                continue
            if fuente not in self._offsets:
                # Fichero visto por primera vez: si ya estaba al arrancar, desde el final;
                # si aparece despues, desde el principio (todo en el es nuevo).
                self._offsets[fuente] = tam if not self._iniciado else 0
                if not self._iniciado:
                    continue
            if tam < self._offsets[fuente]:
                self._offsets[fuente] = 0  # truncado o rotado
                self._saltando.discard(fuente)
            if tam == self._offsets[fuente]:
                continue
            with ruta.open("rb") as f:
                f.seek(self._offsets[fuente])
                trozo = f.read(MAX_BYTES_PASADA)
            if fuente in self._saltando:
                # Resto de una linea gigante ya avisada: descartar hasta su salto de linea.
                corte = trozo.find(b"\n")
                if corte < 0:
                    self._offsets[fuente] += len(trozo)
                    continue
                self._saltando.discard(fuente)
                self._offsets[fuente] += corte + 1
                trozo = trozo[corte + 1:]
            fin = trozo.rfind(b"\n")
            if fin < 0:
                if len(trozo) >= MAX_BYTES_PASADA:
                    # Una sola linea mas grande que la pasada: avisar recortada y saltar el resto,
                    # o este log se quedaria atascado para siempre en el mismo trozo.
                    eventos.append(("log", {"fuente": fuente, "linea": _linea(trozo)}))
                    self._offsets[fuente] += len(trozo)
                    self._saltando.add(fuente)
                continue  # si no, linea a medio escribir: esperar a que termine
            consumido = lineas = 0
            for bruta in trozo[:fin + 1].split(b"\n")[:-1]:
                if lineas >= MAX_LINEAS_PASADA:
                    break  # el resto, en la siguiente pasada
                consumido += len(bruta) + 1
                if bruta.strip():
                    eventos.append(("log", {"fuente": fuente, "linea": _linea(bruta)}))
                    lineas += 1
            self._offsets[fuente] += consumido
        return eventos

    def _revisar_borradores(self) -> list[tuple[str, dict]]:
        try:
            nombres = {p.name for p in trabajo.BORRADORES.glob("*.md")}
        except OSError:
            nombres = set()
        previos = self._borradores
        self._borradores = nombres
        if previos is None or not self._iniciado:
            return []
        return [("borrador", {"nombre": n}) for n in sorted(nombres - previos)]

    def _revisar_turnos(self) -> list[tuple[str, dict]]:
        nombres = {p.name for p in registro.CARPETA.glob("turno_nexo_*.json")}
        if self._turnos is None or not self._iniciado:
            self._turnos = nombres   # foto inicial: los turnos de antes no avisan
            return []
        eventos = []
        for nombre in sorted(nombres - self._turnos):
            try:
                datos = json.loads((registro.CARPETA / nombre).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                n = self._turnos_reintentos.get(nombre, 0) + 1
                self._turnos_reintentos[nombre] = n
                if n < REINTENTOS_TURNO:
                    continue   # a medio escribir: en la siguiente pasada
                log.warning("vigilancia: %s ilegible, se ignora", nombre)
                datos = {}
            self._turnos.add(nombre)
            self._turnos_reintentos.pop(nombre, None)
            ev = {"nombre": nombre, "fallos": fallos_turno(datos)}
            if isinstance(datos, dict) and datos.get("aviso_push"):
                ev["avisado"] = True   # T231: el turno ya mando su propio push con el resumen (nucleo.avisos)
            eventos.append(("turno", ev))
        return eventos

    def _revisar_avisos(self) -> list[tuple[str, dict]]:
        try:
            nombres = {p.name for p in avisos.CARPETA.glob("aviso_*.json")}
        except OSError:
            nombres = set()
        if self._avisos is None or not self._iniciado:
            self._avisos = nombres   # foto inicial: los avisos de antes no se reenvian
            return []
        eventos = []
        for nombre in sorted(nombres - self._avisos):
            try:
                datos = json.loads((avisos.CARPETA / nombre).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue   # se escribe atomico: si no se lee, se reintenta en la siguiente pasada
            self._avisos.add(nombre)
            if isinstance(datos, dict):
                eventos.append(("aviso", {k: str(datos.get(k, "")) for k in ("tipo", "titulo", "cuerpo", "ruta", "clave")}
                                | {"nombre": nombre}))
        return eventos

    def _latir_aprobaciones(self) -> list[tuple[str, dict]]:
        """Damian 05/10 (A0015): latido de la cola cada CADA_LATIDO s. Al volver de un hueco (PC apagado), los
        plazos abiertos se alargan lo que duro. Solo la web de produccion (planificar): una de pruebas no late."""
        if not self.planificar:
            return []
        ahora = time.monotonic()
        if self._latido_ultimo is not None and ahora - self._latido_ultimo < CADA_LATIDO:
            return []
        self._latido_ultimo = ahora
        hueco = aprobaciones.latir()
        if hueco:
            log.info("aprobaciones: plazos alargados %s (NEXO estuvo apagado)", hueco)
        return []

    def _revisar_aprobaciones(self) -> list[tuple[str, dict]]:
        """T751: cada aprobacion AMBAR nueva de la cola (nucleo/aprobaciones.py) -> evento "aprobacion" -> push.
        Era lo unico que solo avisaba Telegram. Las R1/R2 de la matriz no: tienen su propia bandeja. Solo se relee
        la cola cuando cambia el fichero; las pendientes de antes de arrancar no se reenvian."""
        mt = _mtime(aprobaciones.ALMACEN)
        if mt == self._aprob_mtime and self._aprob_vistas is not None:
            return []
        self._aprob_mtime = mt
        from nucleo import guardian   # T1020: lo que el tribunal del guardian aun mira no avisa (avisara al salir)
        pendientes = guardian.para_damian(aprobaciones.pendientes()) if mt is not None else []
        ids = {s["id"] for s in pendientes}
        if self._aprob_vistas is None or not self._iniciado:
            self._aprob_vistas = ids
            return []
        nuevas = [s for s in pendientes if s["id"] not in self._aprob_vistas]
        self._aprob_vistas |= ids
        # (c) Damian 05/10: el push dice que es, quien lo pide y el riesgo (T1020: con la ficha del guardian)
        return [("aprobacion", {"id": s["id"], "origen": str(s.get("origen") or ""),
                                "frase": ocultar.texto(guardian.explicacion(s)["frase"]),
                                "vence": str(s.get("vence") or "")}) for s in nuevas]

    def _revisar_aparcadas(self) -> list[tuple[str, dict]]:
        """T230: las tareas aparcadas cuyo dia ha llegado vuelven solas. No emite eventos: deja un
        aviso en disco (-> push por _revisar_avisos) y el cambio de tareas.json lo ve _revisar_tareas."""
        if not self._iniciado:
            return []   # despues de la foto inicial de avisos: si no, el de "ha vuelto" nunca saldria como push
        ahora = time.monotonic()
        if self._aparcadas_ultima is not None and ahora - self._aparcadas_ultima < CADA_APARCADAS:
            return []
        self._aparcadas_ultima = ahora
        hoy = date.today().isoformat()
        for t in tareas.despertar_aparcadas():
            avisos.emitir("recordatorio", f"{t['id']} ha vuelto: {t['titulo']}",
                          "Estaba aparcada hasta hoy y vuelve a estar en pendientes.", ruta=f"/tareas/{t['id']}",
                          clave=f"vuelve:{t['id']}:{hoy}", urgencia="normal")
        return []

    def _revisar_cola(self) -> list[tuple[str, dict]]:
        """No emite eventos: deja el aviso en disco y _revisar_avisos lo convierte en push."""
        ahora = time.monotonic()
        if self._cola_ultima is not None and ahora - self._cola_ultima < CADA_COLA:
            return []
        self._cola_ultima = ahora
        revision.comprobar_cola()
        return []

    def _revisar_planificador(self) -> list[tuple[str, dict]]:
        """T231: cada planificador.CADA s, encola los turnos que tocan y lanza el siguiente si no hay otro."""
        if not self.planificar:
            return []
        ahora = time.monotonic()
        if self._plan_ultima is not None and ahora - self._plan_ultima < planificador.CADA:
            return []
        self._plan_ultima = ahora
        hecho = planificador.tick()
        if hecho.get("lanzado") or hecho.get("encolados"):
            log.info("planificador: %s", hecho)
            return [("turno_estado", {k: v for k, v in hecho.items() if v})]
        return []

    # ------------------------------------------------------------- bucle
    async def correr(self) -> None:
        while True:
            try:
                eventos = await asyncio.to_thread(self.revisar)
            except Exception as e:  # vigilar nunca tira la web
                log.warning("vigilancia: pasada fallida: %s", type(e).__name__)
                eventos = []
            for tipo, datos in eventos:
                self.bus.publicar(tipo, datos)
            await asyncio.sleep(self.intervalo)
