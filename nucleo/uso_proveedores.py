# -*- coding: utf-8 -*-
"""T078 (REQ-103), primera pieza: registro de uso REAL por proveedor.

Cada envio de un proveedor (qwen, gemini_api, gemini, chatgpt, claude) deja una
linea en registros/uso_proveedores.jsonl: cuando, proveedor, estado, caracteres
de entrada/salida y segundos. No hay cuota oficial legible para las webs, asi
que esto mide lo que NEXO gasta de verdad y cuanto falla cada uno (429/503,
negativas...). Base para decidir a quien delegar y para T029.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REGISTRO = RAIZ / "registros" / "uso_proveedores.jsonl"


def registrar(proveedor: str, estado: str, entrada: int, salida: int, segundos: float) -> None:
    fila = {"cuando": datetime.now().isoformat(timespec="seconds"), "proveedor": proveedor, "estado": estado,
            "entrada": entrada, "salida": salida, "segundos": round(segundos, 1)}
    try:
        REGISTRO.parent.mkdir(parents=True, exist_ok=True)
        with REGISTRO.open("a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    except Exception:
        pass  # medir nunca rompe el trabajo


def medido(enviar):
    """Decorador para Proveedor.enviar(self, tarea, ...)."""
    @wraps(enviar)
    def envoltura(self, tarea, *a, **k):
        t0 = time.time()
        r = enviar(self, tarea, *a, **k)
        registrar(getattr(self, "nombre", "?"), getattr(r, "estado", "?"), len(tarea or ""),
                  len(getattr(r, "texto", "") or ""), time.time() - t0)
        return r
    return envoltura


def totales(dias: int = 1) -> dict[str, dict]:
    """{proveedor: {n, ok, entrada, salida, seg}} de los ultimos `dias` dias. Lineas rotas se saltan."""
    desde = datetime.now() - timedelta(days=dias)
    tot = defaultdict(lambda: {"n": 0, "ok": 0, "entrada": 0, "salida": 0, "seg": 0.0})
    if REGISTRO.is_file():
        for linea in REGISTRO.read_text(encoding="utf-8").splitlines():
            try:
                x = json.loads(linea)
                if datetime.fromisoformat(x["cuando"]) < desde:
                    continue
                fila = (x["proveedor"], x["estado"] == "OK", int(x["entrada"]), int(x["salida"]),
                        float(x["segundos"]))
            except Exception:
                continue
            t = tot[fila[0]]
            t["n"] += 1
            t["ok"] += fila[1]
            t["entrada"] += fila[2]
            t["salida"] += fila[3]
            t["seg"] += fila[4]
    return dict(tot)


def resumen(dias: int = 1) -> str:
    tot = totales(dias)
    if not tot:
        return "Sin llamadas a proveedores registradas en ese periodo."
    lineas = [f"Uso por proveedor (ultimos {dias} dia/s):"]
    for p, t in sorted(tot.items(), key=lambda kv: -kv[1]["n"]):
        lineas.append(f"- {p}: {t['n']} llamadas ({t['ok']} OK), ~{(t['entrada'] + t['salida']) // 4000}k tokens aprox., "
                      f"{t['seg'] / max(t['n'], 1):.0f} s de media")
    return "\n".join(lineas)
