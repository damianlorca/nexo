# -*- coding: utf-8 -*-
"""Fábrica de puzzles (T689), segundo juego: Takuzu (también Binairo; el Tango de LinkedIn es una variante con signos).

Tests dados (los escribe Claude; el implementador SOLO crea extremidades/puzzles/takuzu.py). Biblioteca estándar.
Nombre genérico siempre: nada de "Tango" ni de LinkedIn en el código ni en los libros.

Reglas: rejilla n x n (n par) de 0 y 1; en cada fila y columna, tantos 0 como 1; nunca tres iguales seguidos en una
fila o columna; no hay dos filas iguales ni dos columnas iguales.

Contrato (rejilla = str de n*n caracteres por filas: '0', '1' y '.' para vacío):
- TAMANOS = (4, 6, 8, 10, 12).
- valida(puzzle, n) -> bool: True si n está en TAMANOS, la longitud es n*n, solo hay '0', '1' y '.', y lo puesto no
  rompe ninguna regla (ni "000" ni "111" en filas y columnas, ningún dígito más de n/2 veces por línea, y las filas
  completas distintas entre sí, igual que las columnas completas). Cualquier otra cosa: False, sin excepción.
- es_solucion(rejilla, n) -> bool: completa (sin '.') y valida.
- contar_soluciones(puzzle, n, limite=2) -> int: soluciones contadas hasta `limite`; 0 si no es valida.
- resolver(puzzle, n) -> str | None.
- generar(semilla, n=8, pistas=None) -> {"puzzle", "solucion", "pistas", "n"}: determinista con
  random.Random(semilla); solucion completa y correcta; puzzle con solución ÚNICA que coincide con la solución en sus
  pistas; "pistas" = casillas llenas. Con pistas=None quita casillas mientras siga habiendo solución única (y al
  final no se puede quitar ninguna más); con pistas=k para en cuanto queden k o menos (o antes, si ya no se puede
  quitar nada). ValueError si n no está en TAMANOS.
Contrato comun (T1027): si el modulo tiene bloque `if __name__ == "__main__":`, su PRIMERA linea es
`from nucleo import ayuda; ayuda.atender(__doc__)` (o el modulo usa argparse): --help/-h no ejecuta nada. Lo exige
tests/test_ayuda_entradas.py en la suite completa (T938 cayo por eso).
"""
from __future__ import annotations

import time

import pytest

from extremidades.puzzles import takuzu as T

SOL6 = "001011" "010101" "101010" "011001" "100110" "110100"


def test_reglas_y_solucion_conocida():
    assert T.es_solucion(SOL6, 6)
    assert T.valida(SOL6[:20] + "." * 16, 6)


COLUMNA_CON_4_CEROS = "0....." "......" "0....." "......" "0....." "0....."


@pytest.mark.parametrize("malo,n", [
    ("000111" + "." * 30, 6),                         # tres seguidos
    (COLUMNA_CON_4_CEROS, 6),                         # más de n/2 ceros en una columna (sin tres seguidos)
    ("001011" "001011" + "." * 24, 6),               # dos filas completas iguales
    ("." * 25, 5),                                    # n impar
    ("2" + "." * 35, 6),                              # carácter raro
    ("." * 35, 6),                                    # longitud mala
    (None, 6),
])
def test_valida_rechaza(malo, n):
    assert T.valida(malo, n) is False


def test_contar_y_resolver():
    assert T.contar_soluciones("." * 16, 4, limite=5) == 5
    hueco = SOL6[:-1] + "."
    assert T.contar_soluciones(hueco, 6) == 1 and T.resolver(hueco, 6) == SOL6
    assert T.contar_soluciones("000" + "." * 33, 6) == 0 and T.resolver("000" + "." * 33, 6) is None


@pytest.mark.parametrize("n", [6, 8])
def test_generar_unico_determinista_y_minimo(n):
    for semilla in (1, 2):
        g = T.generar(semilla, n)
        assert g == T.generar(semilla, n) and g["n"] == n
        assert T.es_solucion(g["solucion"], n)
        assert all(p == "." or p == s for p, s in zip(g["puzzle"], g["solucion"]))
        assert T.contar_soluciones(g["puzzle"], n) == 1
        assert g["pistas"] == sum(c != "." for c in g["puzzle"])
        for i, c in enumerate(g["puzzle"]):              # mínimo: quitar cualquier pista rompe la unicidad
            if c != ".":
                assert T.contar_soluciones(g["puzzle"][:i] + "." + g["puzzle"][i + 1:], n) > 1


def test_generar_con_pistas_y_errores():
    g = T.generar(3, 8, pistas=30)
    minimo = T.generar(3, 8)["pistas"]
    assert g["pistas"] == max(30, minimo)              # misma semilla = mismo orden de quitar casillas
    assert T.contar_soluciones(g["puzzle"], 8) == 1
    with pytest.raises(ValueError):
        T.generar(1, 7)


def test_rendimiento():
    t0 = time.time()
    for semilla in range(3):
        T.generar(semilla, 8)
    assert time.time() - t0 < 60
