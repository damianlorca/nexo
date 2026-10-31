# -*- coding: utf-8 -*-
"""Avisos para la web/app (T189, 27/09): lo que Damian tiene que ver aunque no este mirando.

El core no conoce la web (corre en otro proceso: turno, ordenes, pruebas). Deja cada aviso como un
JSON en memoria/avisos/ y la vigilancia de la web (interfaz/vigilancia.py) lo convierte en evento
"aviso" -> panel del centro + push al movil. Nada de Telegram (decision de Damian, 27/09).

Dos fuentes hoy:
  - el auditor de delegaciones (nucleo/auditor.py): una delegacion que falla el checklist;
  - el modo Pensar/Pro: si ChatGPT Y Gemini web fallan el modo (ModoNoActivo) en la misma ventana
    de tiempo sin un exito entre medias, "ningun proveedor consigue el modo".
Anti-repeticion: la misma `clave` no genera otro aviso antes de REPETIR_TRAS segundos.
"""
from __future__ import annotations

import json
import secrets
import time
from datetime import datetime
from pathlib import Path

from nucleo.candado import bloqueo
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico

CARPETA = RAIZ / "memoria" / "avisos"
REPETIR_TRAS = 3600          # s: misma clave, como mucho un aviso por hora
VENTANA_MODO = 1800          # s: ChatGPT y Gemini fallando el modo dentro de esta ventana
SITIOS_MODO = ("chatgpt", "gemini")


def _estado_ruta() -> Path:
    return CARPETA / "_estado.json"


def _leer_estado() -> dict:
    try:
        datos = json.loads(_estado_ruta().read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar_estado(datos: dict) -> None:
    CARPETA.mkdir(parents=True, exist_ok=True)
    escribir_atomico(_estado_ruta(), json.dumps(datos, ensure_ascii=False, indent=1))


def emitir(tipo: str, titulo: str, cuerpo: str, ruta: str = "/", clave: str = "",
           urgencia: str = "high", ahora: float | None = None) -> Path | None:
    """Deja un aviso para la web. None si la misma clave ya aviso hace menos de REPETIR_TRAS."""
    ahora = time.time() if ahora is None else ahora
    clave = clave or f"{tipo}:{titulo}"
    CARPETA.mkdir(parents=True, exist_ok=True)
    with bloqueo(CARPETA / ".candado"):
        estado = _leer_estado()
        ultimos = estado.setdefault("ultimos", {})
        if clave in ultimos and ahora - float(ultimos[clave]) < REPETIR_TRAS:
            return None
        ultimos[clave] = ahora
        _guardar_estado(estado)
    aviso = {"tipo": tipo, "titulo": titulo[:120], "cuerpo": cuerpo[:400], "ruta": ruta, "clave": clave,
             "urgencia": urgencia, "cuando": datetime.fromtimestamp(ahora).strftime("%Y-%m-%d %H:%M:%S")}
    f = CARPETA / f"aviso_{datetime.fromtimestamp(ahora):%Y%m%d_%H%M%S}_{secrets.token_hex(3)}.json"
    escribir_atomico(f, json.dumps(aviso, ensure_ascii=False, indent=1))
    return f


def ya_emitido(clave: str) -> bool:
    """La clave ya aviso alguna vez (para avisos que llevan la fecha en la clave: uno al dia)."""
    return clave in (_leer_estado().get("ultimos") or {})


def recientes(n: int = 10) -> list[dict]:
    """Los ultimos avisos (mas nuevo primero), para el panel de la web."""
    try:
        rutas = sorted(CARPETA.glob("aviso_*.json"), reverse=True)[:n]
    except OSError:
        return []
    salida = []
    for r in rutas:
        try:
            d = json.loads(r.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict):
            d["archivo"] = r.name
            salida.append(d)
    return salida


# ------------------------------------------------------------ modo Pensar/Pro
def modo_fallido(sitio: str, detalle: str = "", ahora: float | None = None) -> Path | None:
    """Anota que `sitio` no consiguio su modo. Si los dos sitios web estan fallando -> aviso."""
    if sitio not in SITIOS_MODO:
        return None
    ahora = time.time() if ahora is None else ahora
    CARPETA.mkdir(parents=True, exist_ok=True)
    with bloqueo(CARPETA / ".candado"):
        estado = _leer_estado()
        modo = estado.setdefault("modo", {})
        modo[sitio] = {"fallo": ahora, "detalle": (detalle or "")[:200]}
        _guardar_estado(estado)
        todos = all(isinstance(modo.get(s), dict) and ahora - float(modo[s].get("fallo", 0)) <= VENTANA_MODO
                    for s in SITIOS_MODO)
        detalles = "; ".join(f"{s}: {modo[s].get('detalle', '')[:120]}" for s in SITIOS_MODO if modo.get(s))
    if not todos:
        return None
    return emitir("modo", "Ningún proveedor consigue el modo Pensar/Pro",
                  "ChatGPT (Pensar) y Gemini (Pro) han fallado el modo. Las delegaciones web no salen hasta "
                  "arreglarlo. " + detalles, ruta="/logs", clave="modo:todos", ahora=ahora)


def modo_ok(sitio: str) -> None:
    """Un exito con el modo verificado borra el fallo pendiente de ese sitio."""
    if sitio not in SITIOS_MODO:
        return
    try:
        with bloqueo(CARPETA / ".candado"):
            estado = _leer_estado()
            if (estado.get("modo") or {}).pop(sitio, None) is not None:
                _guardar_estado(estado)
    except OSError:
        pass
