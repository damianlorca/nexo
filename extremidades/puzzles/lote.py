# -*- coding: utf-8 -*-
"""Lote reanudable de sudokus por nivel (libro «Sudoku 1 · Cuadernos de Lógica»).

    python -m extremidades.puzzles.lote --nivel experto --n 50 --salida memoria/monetizacion/libro1/expertos.json

Niveles: facil, medio, dificil, experto (nivel4 de dificultad_avanzada: certificados como resolubles solo con lógica).
Guarda por puzzle: puzzle, solucion, pistas, nivel, puntuacion, tecnicas y semilla, ordenados por puntuación
ascendente. Si la salida ya existe continúa donde se quedó (misma semilla siguiente, mismos puzzles); se guarda tras
cada tanda. --procesos reparte las semillas entre procesos (por defecto, hasta 4); el resultado no depende de ello.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from extremidades.puzzles import dificultad_avanzada as A

AVISO_SEGUNDOS = 20 * 60


def _uno(args):
    semilla, nivel = args
    try:
        return semilla, A.generar_por_nivel4(semilla, nivel)
    except RuntimeError:
        return semilla, None


def _cargar(salida: Path, nivel: str) -> dict:
    if salida.exists():
        d = json.loads(salida.read_text(encoding="utf-8"))
        if d.get("nivel") != nivel:
            raise SystemExit(f"{salida} es de nivel {d.get('nivel')}, no {nivel}: usa otra --salida")
        return d
    return {"nivel": nivel, "siguiente_semilla": 1, "semillas_fallidas": [], "puzzles": []}


def _guardar(salida: Path, d: dict) -> None:
    d["puzzles"].sort(key=lambda p: (p["puntuacion"], p["semilla"]))
    salida.parent.mkdir(parents=True, exist_ok=True)
    tmp = salida.with_suffix(salida.suffix + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, salida)


def generar_lote(nivel: str, n: int, salida: Path, procesos: int = 1, tanda: int | None = None, log=print) -> dict:
    """Completa `salida` hasta `n` puzzles de `nivel` (reanuda si existe). Devuelve el contenido guardado."""
    d = _cargar(salida, nivel)
    tanda = tanda or max(4, procesos * 4)
    inicio = time.time()
    pool = ProcessPoolExecutor(max_workers=procesos) if procesos > 1 else None
    try:
        while len(d["puzzles"]) < n:
            desde = d["siguiente_semilla"]
            tareas = [(s, nivel) for s in range(desde, desde + tanda)]
            res = list(pool.map(_uno, tareas)) if pool else [_uno(t) for t in tareas]
            for semilla, p in res:               # en orden de semilla: el resultado no depende del nº de procesos
                d["siguiente_semilla"] = semilla + 1
                if p is None:
                    d["semillas_fallidas"].append(semilla)
                elif len(d["puzzles"]) < n and not any(q["puzzle"] == p["puzzle"] for q in d["puzzles"]):
                    d["puzzles"].append(p)
            _guardar(salida, d)
            seg = time.time() - inicio
            log(f"{len(d['puzzles'])}/{n} {nivel} · semilla {d['siguiente_semilla'] - 1} · {seg:.0f} s")
            if seg > AVISO_SEGUNDOS:
                log(f"AVISO: el lote lleva más de {AVISO_SEGUNDOS // 60} min")
    finally:
        if pool:
            pool.shutdown()
    _guardar(salida, d)
    return d


def main(argv=None) -> int:
    try:
        from nucleo import consola
        consola.preparar()   # consola cp1252 de Windows
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nivel", required=True, choices=["facil", "medio", "dificil", "experto"])
    ap.add_argument("--n", type=int, default=50, help="cuántos puzzles en total (con lo que ya haya en la salida)")
    ap.add_argument("--salida", required=True, help="JSON de salida (se reanuda si ya existe)")
    ap.add_argument("--procesos", type=int, default=min(4, os.cpu_count() or 1))
    a = ap.parse_args(argv)
    d = generar_lote(a.nivel, a.n, Path(a.salida), max(1, a.procesos))
    pts = [p["puntuacion"] for p in d["puzzles"]]
    print(f"listo: {len(pts)} {a.nivel}, puntuación mín {min(pts)} · mediana {sorted(pts)[len(pts) // 2]} · máx {max(pts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
