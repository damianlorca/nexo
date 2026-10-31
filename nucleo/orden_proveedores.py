# -*- coding: utf-8 -*-
"""Orden de llamada de los proveedores (T195): editable en Ajustes y respetado por trabajo.py.

Sin preferencia guardada, `trabajo.py` conserva su orden de siempre (autores y revisores tienen el suyo, decidido con
datos). Con una preferencia, los proveedores que aparezcan en ella van PRIMERO y en ese orden; los que no, detras y sin
cambiar su orden relativo. El interruptor de apagado (T549), el enfriamiento y la cuota (T684) siguen mandando: este
orden solo reordena los que ya estan disponibles. Se guarda en `memoria/orden_proveedores.json`.
"""
from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ / "memoria" / "orden_proveedores.json"

# lo que se puede ordenar: las IAs que trabajo.py llama (nombre de cada proveedor)
ORDENABLES = ("chatgpt", "nvidia", "gemini_api", "gemini", "groq", "qwen")
ORDEN_BASE = ORDENABLES    # el orden de los generadores (04/10): el que se ve si no hay preferencia


def leer() -> list[str]:
    """La preferencia guardada (vacia = ninguna)."""
    try:
        d = json.loads(ARCHIVO.read_text(encoding="utf-8"))
        return [n for n in d.get("orden", []) if n in ORDENABLES] if isinstance(d, dict) else []
    except Exception:
        return []


def guardar(orden: list[str]) -> list[str]:
    """Guarda `orden` (sin repetidos ni desconocidos; los que falten se anaden detras) y lo devuelve."""
    visto: list[str] = []
    for n in list(orden) + list(ORDENABLES):
        if n in ORDENABLES and n not in visto:
            visto.append(n)
    from nucleo.escritura import escribir_atomico
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(ARCHIVO, json.dumps({"orden": visto}, ensure_ascii=False, indent=1))
    return visto


def actual() -> list[str]:
    """El orden que se muestra: la preferencia completa, o el de base."""
    pref = leer()
    return pref + [n for n in ORDEN_BASE if n not in pref] if pref else list(ORDEN_BASE)


def mover(nombre: str, delta: int) -> list[str]:
    """Sube (delta<0) o baja (delta>0) un proveedor y guarda."""
    orden = actual()
    if nombre not in orden:
        raise ValueError(f"proveedor desconocido: {nombre}")
    i = orden.index(nombre)
    j = max(0, min(len(orden) - 1, i + delta))
    orden.insert(j, orden.pop(i))
    return guardar(orden)


def restablecer() -> None:
    try:
        ARCHIVO.unlink()
    except FileNotFoundError:
        pass


def aplicar(proveedores: list) -> list:
    """Reordena una lista de proveedores segun la preferencia (sin preferencia, tal cual)."""
    pref = leer()
    if not pref:
        return list(proveedores)
    puesto = {n: i for i, n in enumerate(pref)}
    return sorted(proveedores, key=lambda p: puesto.get(getattr(p, "nombre", ""), len(pref)))   # sorted es estable
