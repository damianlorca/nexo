# -*- coding: utf-8 -*-
"""Piloto de monetización (T689), pieza P1a: plan de páginas del libro de sudokus (solo datos, sin PDF).

Tests dados (los escribe Claude; el implementador SOLO crea extremidades/puzzles/libro.py, biblioteca estándar).
El PDF real (P1b) irá después con fpdf2 y una fuente libre incrustada (KDP exige fuentes incrustadas); esta pieza
solo decide qué va en cada página.

Contrato: plan_paginas(n_puzzles, por_pagina=2, soluciones_por_pagina=6) -> list[dict]
- Orden: 1 "portadilla", 1 "instrucciones", las páginas "puzzle" (en orden, `por_pagina` puzzles cada una; la
  última puede ir incompleta), las páginas "soluciones" (en orden, `soluciones_por_pagina` cada una; la última puede
  ir incompleta) y, si el total queda impar, una "blanca" al final (KDP imprime a doble cara: total PAR).
- Cada página: {"numero": 1..N consecutivo, "tipo": str, "indices": list[int]} con índices de puzzle 0-based;
  portadilla, instrucciones y blanca llevan [].
- Cada puzzle aparece exactamente una vez en páginas "puzzle" y exactamente una vez en páginas "soluciones".
- ValueError si n_puzzles < 1, por_pagina no está en (1, 2, 4) o soluciones_por_pagina no está en (4, 6, 9).
- paginas_totales(n_puzzles, por_pagina=2, soluciones_por_pagina=6) -> int == len(plan_paginas(...)).
Contrato comun (T1027): si el modulo tiene bloque `if __name__ == "__main__":`, su PRIMERA linea es
`from nucleo import ayuda; ayuda.atender(__doc__)` (o el modulo usa argparse): --help/-h no ejecuta nada. Lo exige
tests/test_ayuda_entradas.py en la suite completa (T938 cayo por eso).
"""
from __future__ import annotations

import pytest

from extremidades.puzzles import libro as L


def test_plan_basico_120_puzzles():
    plan = L.plan_paginas(120)
    tipos = [p["tipo"] for p in plan]
    assert tipos[:2] == ["portadilla", "instrucciones"]
    assert tipos.count("puzzle") == 60
    assert tipos.count("soluciones") == 20
    assert len(plan) % 2 == 0
    assert len(plan) == 82
    assert [p["numero"] for p in plan] == list(range(1, len(plan) + 1))
    assert L.paginas_totales(120) == 82


def test_cada_puzzle_una_vez_en_puzzles_y_en_soluciones():
    plan = L.plan_paginas(25, por_pagina=4, soluciones_por_pagina=9)
    en_puzzles = [i for p in plan if p["tipo"] == "puzzle" for i in p["indices"]]
    en_soluciones = [i for p in plan if p["tipo"] == "soluciones" for i in p["indices"]]
    assert en_puzzles == list(range(25))
    assert en_soluciones == list(range(25))
    assert [len(p["indices"]) for p in plan if p["tipo"] == "puzzle"] == [4] * 6 + [1]
    assert [len(p["indices"]) for p in plan if p["tipo"] == "soluciones"] == [9, 9, 7]


def test_pagina_blanca_solo_si_impar():
    impar = L.plan_paginas(3, por_pagina=1, soluciones_por_pagina=4)      # 2 + 3 + 1 = 6 -> par, sin blanca
    assert [p["tipo"] for p in impar][-1] == "soluciones"
    par = L.plan_paginas(4, por_pagina=1, soluciones_por_pagina=4)        # 2 + 4 + 1 = 7 -> blanca
    assert par[-1]["tipo"] == "blanca" and par[-1]["indices"] == []
    assert len(par) == 8


def test_paginas_sin_indices():
    plan = L.plan_paginas(10)
    for p in plan:
        if p["tipo"] in ("portadilla", "instrucciones", "blanca"):
            assert p["indices"] == []


@pytest.mark.parametrize("args", [(0,), (10, 3), (10, 2, 5), (-1,)])
def test_errores(args):
    with pytest.raises(ValueError):
        L.plan_paginas(*args)
