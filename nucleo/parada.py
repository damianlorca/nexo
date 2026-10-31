# -*- coding: utf-8 -*-
"""Parada de emergencia de NEXO (T079, pedida por Damian 23/09).

Un archivo bandera: memoria/PARADA_NEXO. Mientras exista, ningun turno
automatico empieza ni sigue (turno_nexo.py lo mira antes de cada paso y
en cada vuelta del bucle). Se activa desde Telegram (/parar [motivo]) o a
mano (crear el archivo). Se quita con /seguir.

activar() ademas descarga ya los modelos de Ollama que esten cargados,
para cortar una generacion en curso (Ollama sigue generando aunque el
cliente muera: ver referencia-incidentes-tecnicos.md).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BANDERA = RAIZ / "memoria" / "PARADA_NEXO"


def activa() -> str | None:
    """Motivo de la parada si esta activa; None si no."""
    if not BANDERA.exists():
        return None
    try:
        return json.loads(BANDERA.read_text(encoding="utf-8")).get("motivo") or "sin motivo"
    except Exception:
        return "parada activa (bandera ilegible)"


def _descargar_ollama() -> list[str]:
    descargados = []
    try:
        import httpx
        for puerto in (11434, 11435):
            try:
                ps = httpx.get(f"http://127.0.0.1:{puerto}/api/ps", timeout=3).json().get("models", [])
            except Exception:
                continue
            for m in ps:
                httpx.post(f"http://127.0.0.1:{puerto}/api/generate",
                           json={"model": m["name"], "keep_alive": 0}, timeout=10)
                descargados.append(f"{m['name']}@{puerto}")
    except Exception:
        pass
    return descargados


def activar(motivo: str = "", quien: str = "damian") -> dict:
    BANDERA.parent.mkdir(parents=True, exist_ok=True)
    datos = {"motivo": motivo.strip() or "parada manual", "quien": quien,
             "cuando": datetime.now().isoformat(timespec="seconds")}
    BANDERA.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    datos["ollama_descargados"] = _descargar_ollama()
    return datos


def desactivar() -> bool:
    try:
        BANDERA.unlink()
        return True
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------- cierre suave
# Damian 23/09: turno a las 03:30, aviso del vigilante a las 04:20 y fin seguro a las 04:30.
# El vigilante crea esta bandera; el turno termina lo que tiene entre manos, no empieza nada
# nuevo y escribe su handoff. El corte duro lo hace Windows (limite de 60 min de la tarea).
CIERRE = RAIZ / "memoria" / "CIERRE_TURNO"


def pedir_cierre(motivo: str = "hora limite") -> None:
    CIERRE.write_text(json.dumps({"motivo": motivo, "cuando": datetime.now().isoformat(timespec="seconds")}), encoding="utf-8")


def cierre_pedido() -> bool:
    return CIERRE.exists()


def motivo_cierre() -> str:
    try:
        return json.loads(CIERRE.read_text(encoding="utf-8")).get("motivo") or ""
    except (OSError, ValueError):
        return ""


def limpiar_cierre() -> None:
    try:
        CIERRE.unlink()
    except FileNotFoundError:
        pass
