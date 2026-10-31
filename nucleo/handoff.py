# -*- coding: utf-8 -*-
"""Handoff formal a Claude para lo que NEXO no puede resolver solo."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA = RAIZ / "memoria" / "handoff_claude.jsonl"


def _leer_lineas_crudas() -> list[str]:
    if not RUTA.exists():
        return []
    return RUTA.read_text(encoding="utf-8").splitlines()


def _escribir_lineas_crudas(lineas: list[str]) -> None:
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    temp_path = RUTA.with_suffix(RUTA.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as f:
        for linea in lineas:
            f.write(linea + "\n")
    os.replace(temp_path, RUTA)


def anotar(
    tarea: str,
    orden: str,
    motivo: str,
    contexto: str = "",
    canal: str = "web",
    ahora: datetime | None = None,
) -> dict:
    if not tarea or not tarea.strip() or not orden or not orden.strip():
        raise ValueError("Tarea y orden son obligatorios y no pueden estar vacíos")

    pend = pendientes()
    for p in pend:
        if p.get("tarea") == tarea:
            return p

    if ahora is None:
        ahora = datetime.now()

    entrada = {
        "tarea": tarea,
        "orden": orden,
        "motivo": motivo[:300],
        "contexto": contexto[:2000],
        "canal": canal,
        "cuando": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "recogido": None,
    }

    lineas_crudas = _leer_lineas_crudas()
    lineas_crudas.append(json.dumps(entrada, ensure_ascii=False))
    _escribir_lineas_crudas(lineas_crudas)
    return entrada


def pendientes() -> list[dict]:
    if not RUTA.exists():
        return []
    res = []
    for linea in _leer_lineas_crudas():
        if not linea.strip():
            continue
        try:
            data = json.loads(linea)
            if isinstance(data, dict) and data.get("recogido") is None:
                res.append(data)
        except json.JSONDecodeError:
            continue
    return res


def recoger(tarea: str, nota: str, ahora: datetime | None = None) -> int:
    if not RUTA.exists():
        return 0

    if ahora is None:
        ahora = datetime.now()

    cuando_str = ahora.strftime("%Y-%m-%d %H:%M:%S")
    nota_recortada = nota[:300]

    lineas_crudas = _leer_lineas_crudas()
    nuevas_lineas = []
    marcadas = 0

    for linea in lineas_crudas:
        if not linea.strip():
            nuevas_lineas.append(linea)
            continue
        try:
            data = json.loads(linea)
            if isinstance(data, dict) and data.get("tarea") == tarea and data.get("recogido") is None:
                data["recogido"] = {"cuando": cuando_str, "nota": nota_recortada}
                marcadas += 1
                nuevas_lineas.append(json.dumps(data, ensure_ascii=False))
            else:
                nuevas_lineas.append(linea)
        except json.JSONDecodeError:
            nuevas_lineas.append(linea)

    if marcadas > 0:
        _escribir_lineas_crudas(nuevas_lineas)

    return marcadas


if __name__ == "__main__":
    from nucleo import ayuda
    ayuda.atender(__doc__)