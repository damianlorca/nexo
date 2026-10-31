# -*- coding: utf-8 -*-
"""Enfriamiento (cooldown) por proveedor — T143, idea tomada de OpenClaw (T142).

Medido 23/09: con la API de Gemini sin cuota (429) o saturada (503), cada tarea
perdia ~1-2 min reintentando 4 modelos x 3 rondas antes de pasar a la web. Con
esto, tras un fallo de cuota el proveedor se da por NO disponible durante un rato
y la cascada salta directamente al siguiente.

Estado en memoria/enfriamiento.json: {proveedor: {"hasta": epoch, "motivo": str}}.

T549 (05/10): ademas, el INTERRUPTOR MANUAL por proveedor (Damian, desde la web: Proveedores). Un proveedor apagado
a mano no caduca: sigue apagado hasta que se encienda. Vive en memoria/proveedores_apagados.json (fuera de git:
cambiarlo no ensucia principal). enfriado() lo devuelve primero, asi que lo respeta todo lo que ya miraba el
enfriamiento (cascadas, tribunal -con "tribunal:x" mira "x"-, implementador); proveedores.py ademas lo comprueba
en enviar()/disponible()/estado() de cada clase (el router llama a algunos sin preguntar disponible()).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ALMACEN = RAIZ / "memoria" / "enfriamiento.json"

APAGADOS = RAIZ / "memoria" / "proveedores_apagados.json"

# segundos por tipo de fallo
# "transitorio" (T1013): un 403 suelto sin texto de cuota; el siguiente intento tras los 30 min hace de sondeo.
DURACION = {"cuota": 30 * 60, "saturado": 5 * 60, "bloqueo": 6 * 3600, "transitorio": 30 * 60}
SONDEO_VALE = 2 * 3600   # un transitorio caducado hace menos de esto convierte el siguiente 403 en bloqueo


def _leer() -> dict:
    try:
        return json.loads(ALMACEN.read_text(encoding="utf-8"))
    except Exception:
        return {}


def enfriar(proveedor: str, tipo: str, motivo: str = "", segundos: float | None = None) -> None:
    """`segundos` fija la duracion a mano (T667: el cupo diario de la web del tribunal enfria hasta manana)."""
    d = _leer()
    dura = DURACION.get(tipo, 300) if segundos is None else max(0.0, float(segundos))
    d[proveedor] = {"hasta": time.time() + dura, "tipo": tipo, "motivo": motivo[:200]}
    try:
        ALMACEN.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def apagados() -> dict:
    """{proveedor: {"cuando", "motivo"}} de los apagados a mano (T549)."""
    try:
        d = json.loads(APAGADOS.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def apagado(proveedor: str) -> str | None:
    """Motivo si el proveedor (o, para "tribunal:x", x) esta apagado a mano; None si no."""
    d = apagados()
    for nombre in dict.fromkeys((proveedor, proveedor.split(":", 1)[-1])):
        if nombre in d:
            return f"apagado a mano: {d[nombre].get('motivo') or 'sin motivo'}"
    return None


def _guardar_apagados(d: dict) -> None:
    from nucleo.escritura import escribir_atomico
    APAGADOS.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(APAGADOS, json.dumps(d, ensure_ascii=False, indent=1))


def apagar(proveedor: str, motivo: str = "") -> None:
    d = apagados()
    d[proveedor] = {"cuando": time.strftime("%Y-%m-%d %H:%M:%S"), "motivo": " ".join(motivo.split())[:200]}
    _guardar_apagados(d)


def encender(proveedor: str) -> None:
    d = apagados()
    if d.pop(proveedor, None) is not None:
        _guardar_apagados(d)


def enfriado(proveedor: str) -> str | None:
    """Motivo si el proveedor esta apagado a mano (T549) o en enfriamiento ahora; None si esta libre."""
    manual = apagado(proveedor)
    if manual:
        return manual
    e = _leer().get(proveedor)
    if not e or e.get("hasta", 0) <= time.time():
        return None
    return f"{e.get('tipo')} hasta {time.strftime('%H:%M', time.localtime(e['hasta']))}: {e.get('motivo', '')}"


def transitorio_reciente(proveedor: str) -> bool:
    """True si el ultimo enfriamiento fue 'transitorio' y caduco hace poco: la llamada de ahora es el sondeo (T1013)."""
    e = _leer().get(proveedor)
    return bool(e and e.get("tipo") == "transitorio" and time.time() - e.get("hasta", 0) < SONDEO_VALE)


def limpiar(proveedor: str) -> None:
    d = _leer()
    if d.pop(proveedor, None) is not None:
        ALMACEN.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    # T667: reactivar un proveedor parado a mano (p.ej. Claude web tras resolver Damian una verificacion).
    #   .venv\Scripts\python.exe -m nucleo.enfriamiento limpiar claude_web
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "limpiar":
        limpiar(sys.argv[2])
        print(f"{sys.argv[2]}: sin enfriamiento")
    else:
        print(json.dumps(_leer(), ensure_ascii=False, indent=1))
