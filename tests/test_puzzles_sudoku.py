# -*- coding: utf-8 -*-
"""Piloto de monetización (T689), pieza P0a: generador de sudokus con solución ÚNICA, determinista y sin dependencias.

Tests dados (los escribe Claude; el implementador SOLO crea extremidades/puzzles/__init__.py (vacío) y
extremidades/puzzles/sudoku.py, solo con la biblioteca estándar). Contrato:

Una rejilla es un str de 81 caracteres '0'-'9' por filas (fila 0 primero); '0' = casilla vacía.

- valida(rejilla) -> bool: True si tiene 81 caracteres, todos '0'-'9', y ningún dígito distinto de '0' se repite
  en una fila, una columna o una caja 3x3. Cualquier otra cosa (longitud mala, letras, None) -> False, sin excepción.
- contar_soluciones(rejilla, limite=2) -> int: cuántas soluciones tiene, contando como mucho hasta `limite`
  (para en cuanto llega). Rejilla no válida -> 0.
- resolver(rejilla) -> str | None: una solución completa (81 dígitos '1'-'9') que respeta las pistas, o None si no
  tiene solución o no es válida.
- generar(semilla, pistas) -> dict con "puzzle", "solucion" y "pistas" (int = casillas no vacías del puzzle):
  * determinista: misma semilla y mismas pistas -> exactamente el mismo resultado (usar random.Random(semilla),
    nunca el random global ni la hora);
  * "solucion" es una rejilla completa y válida, y el puzzle coincide con ella en todas sus pistas;
  * el puzzle tiene EXACTAMENTE una solución (contar_soluciones == 1) y esa solución es "solucion";
  * quita pistas mientras siga habiendo solución única; para al llegar a `pistas` o cuando ya no puede quitar
    ninguna más: el resultado tiene entre `pistas` y `pistas + 4` pistas.
- NIVELES: dict {"facil": 40, "medio": 32, "dificil": 28} (pistas objetivo).
- generar_nivel(semilla, nivel) -> el dict de generar(semilla, NIVELES[nivel]) más la clave "nivel";
  nivel desconocido -> ValueError.
Contrato comun (T1027): si el modulo tiene bloque `if __name__ == "__main__":`, su PRIMERA linea es
`from nucleo import ayuda; ayuda.atender(__doc__)` (o el modulo usa argparse): --help/-h no ejecuta nada. Lo exige
tests/test_ayuda_entradas.py en la suite completa (T938 cayo por eso).
"""
from __future__ import annotations

import time

import pytest

from extremidades.puzzles import sudoku as S

# Puzzle clásico con solución única conocida.
PUZZLE = ("530070000600195000098000060800060003400803001700020006060000280000419005000080079")
SOLUCION = ("534678912672195348198342567859761423426853791713924856961537284287419635345286179")


def _valida_completa(r):
    return len(r) == 81 and "0" not in r and S.valida(r)


def test_valida_acepta_puzzle_y_solucion():
    assert S.valida(PUZZLE) and S.valida(SOLUCION)
    assert S.valida("0" * 81)


@pytest.mark.parametrize("mala", [
    "5" + "5" + "0" * 79,                     # mismo dígito dos veces en la fila 0
    "5" + "0" * 8 + "5" + "0" * 71,           # mismo dígito en la columna 0
    "5" + "0" * 9 + "5" + "0" * 70,           # mismo dígito en la caja 0 (fila 1, columna 1)
    "0" * 80,                                 # longitud mala
    "x" + "0" * 80,                           # carácter no válido
    None,
])
def test_valida_rechaza(mala):
    assert S.valida(mala) is False


def test_contar_soluciones():
    assert S.contar_soluciones(PUZZLE) == 1
    assert S.contar_soluciones("0" * 81) == 2           # se para en el límite
    assert S.contar_soluciones("0" * 81, limite=5) == 5
    assert S.contar_soluciones("55" + "0" * 79) == 0     # no válida


def test_resolver():
    assert S.resolver(PUZZLE) == SOLUCION
    assert S.resolver("55" + "0" * 79) is None
    sin_solucion = "123456780" + "0" * 8 + "9" + "0" * 63   # la casilla 8 no admite dígito (9 en su columna)
    assert S.resolver(sin_solucion) is None


def test_generar_es_determinista():
    a = S.generar(7, 32)
    b = S.generar(7, 32)
    c = S.generar(8, 32)
    assert a == b
    assert a["puzzle"] != c["puzzle"]


@pytest.mark.parametrize("nivel", ["facil", "medio", "dificil"])
@pytest.mark.parametrize("semilla", [1, 2, 3])
def test_generar_nivel_unica_y_coherente(semilla, nivel):
    r = S.generar_nivel(semilla, nivel)
    objetivo = S.NIVELES[nivel]
    p, s = r["puzzle"], r["solucion"]
    assert r["nivel"] == nivel
    assert _valida_completa(s)
    assert S.valida(p)
    assert all(pc == "0" or pc == sc for pc, sc in zip(p, s))
    assert r["pistas"] == sum(ch != "0" for ch in p)
    assert objetivo <= r["pistas"] <= objetivo + 4
    assert S.contar_soluciones(p) == 1
    assert S.resolver(p) == s


def test_niveles_y_error():
    assert S.NIVELES == {"facil": 40, "medio": 32, "dificil": 28}
    with pytest.raises(ValueError):
        S.generar_nivel(1, "imposible")


def test_rendimiento_razonable():
    t0 = time.perf_counter()
    for semilla in (11, 12, 13):
        S.generar_nivel(semilla, "dificil")
    assert time.perf_counter() - t0 < 60
