# -*- coding: utf-8 -*-
"""Fábrica de puzzles (T689), tercer juego: Star Battle de una estrella (el Queens de LinkedIn es este género).

Tests dados (los escribe Claude; el implementador SOLO crea extremidades/puzzles/estrellas.py). Biblioteca estándar.
Nombre genérico siempre ("Star Battle" o "estrellas"); nada de "Queens" ni de LinkedIn en el código ni en los libros.

Reglas: rejilla n x n partida en n regiones; una estrella por fila, por columna y por región; dos estrellas nunca se
tocan, ni en diagonal.

Contrato (casillas numeradas por filas, i = fila * n + columna):
- TAMANOS = (5, 6, 7, 8, 9, 10).
- valida_regiones(regiones, n) -> bool: lista o tupla de n*n enteros, cada uno de 0 a n-1, están todos y cada
  región es conexa (casillas unidas por lados). n fuera de TAMANOS o cualquier otra cosa: False, sin excepción.
- es_solucion(estrellas, regiones, n) -> bool: `estrellas` es la lista de n columnas (una por fila) y cumple todas
  las reglas con esas regiones.
- soluciones(regiones, n, limite=2) -> list[list[int]]: soluciones (como `estrellas`) hasta `limite`; [] si las
  regiones no son válidas.
- generar(semilla, n=8, intentos=200) -> {"regiones": list[int], "estrellas": list[int], "n": n}: determinista con
  random.Random(semilla); regiones válidas con solución ÚNICA, que es `estrellas`. ValueError si n no está en
  TAMANOS; RuntimeError si se agotan los intentos. Pista para generar (no obligatoria): colocar una solución
  válida, hacer crecer una región desde cada estrella y, si sale otra solución, pasar a la región de al lado una
  casilla de esa otra solución que no tenga estrella en la buena, hasta que solo quede una.
Contrato comun (T1027): si el modulo tiene bloque `if __name__ == "__main__":`, su PRIMERA linea es
`from nucleo import ayuda; ayuda.atender(__doc__)` (o el modulo usa argparse): --help/-h no ejecuta nada. Lo exige
tests/test_ayuda_entradas.py en la suite completa (T938 cayo por eso).
"""
from __future__ import annotations

import itertools
import time

import pytest

from extremidades.puzzles import estrellas as E

R5 = [int(x) for x in "1102211122111243332433344"]
R7 = [int(x) for x in "0011122111322211132425333442553444455364445666644"]


def _todas(regiones, n):
    """Comprobación independiente por fuerza bruta (permutaciones)."""
    return [list(p) for p in itertools.permutations(range(n))
            if all(abs(p[i] - p[i + 1]) > 1 for i in range(n - 1))
            and len({regiones[f * n + c] for f, c in enumerate(p)}) == n]


@pytest.mark.parametrize("regiones,n,unica", [(R5, 5, [2, 0, 3, 1, 4]), (R7, 7, [0, 2, 6, 3, 5, 1, 4])])
def test_puzzles_conocidos(regiones, n, unica):
    assert E.valida_regiones(regiones, n)
    assert _todas(regiones, n) == [unica]
    assert E.soluciones(regiones, n) == [unica]
    assert E.es_solucion(unica, regiones, n)


@pytest.mark.parametrize("malas,n", [
    (R5[:-1], 5),                                    # longitud
    ([0] * 25, 5),                                   # faltan regiones
    ([0, 1, 0, 2, 3] + [2] * 5 + [3] * 5 + [4] * 10, 5),   # región 0 partida en dos
    ([x % 4 for x in range(16)], 4),                 # tamaño fuera de TAMANOS
    ("1102211122111243332433344", 5),                # no es lista de enteros
    (None, 5),
])
def test_valida_regiones_rechaza(malas, n):
    assert E.valida_regiones(malas, n) is False


def test_es_solucion_rechaza():
    assert not E.es_solucion([2, 0, 3, 1, 4][:4], R5, 5)
    assert not E.es_solucion([0, 2, 4, 1, 3], R5, 5)     # válida sin regiones, pero repite región
    assert not E.es_solucion([2, 3, 0, 4, 1], R5, 5)     # se tocan en diagonal
    assert not E.es_solucion([2, 0, 2, 1, 4], R5, 5)     # columna repetida


def test_soluciones_y_limite():
    filas = [f for f in range(5) for _ in range(5)]      # regiones = filas: muchas soluciones
    todas = _todas(filas, 5)
    assert len(E.soluciones(filas, 5, limite=100)) == len(todas) > 2
    assert len(E.soluciones(filas, 5, limite=2)) == 2
    assert E.soluciones([0] * 25, 5) == []


@pytest.mark.parametrize("n", [6, 8])
def test_generar(n):
    for semilla in (1, 2):
        g = E.generar(semilla, n)
        assert g == E.generar(semilla, n) and g["n"] == n
        assert E.valida_regiones(g["regiones"], n)
        assert _todas(g["regiones"], n) == [g["estrellas"]]


def test_generar_errores_y_rendimiento():
    for malo in (4, 11):
        with pytest.raises(ValueError):
            E.generar(1, malo)
    t0 = time.time()
    g = E.generar(5, 9)
    assert E.soluciones(g["regiones"], 9) == [g["estrellas"]]
    assert time.time() - t0 < 60
