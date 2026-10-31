# -*- coding: utf-8 -*-
"""Fábrica de puzzles (T689): nivel real de Takuzu y Star Battle según las técnicas que necesita una persona (como P0c).

Por qué: los Takuzu mínimos salen casi todos difíciles o imposibles sin probar, y los Star Battle varían mucho;
para hacer libros "de fácil a difícil" hay que medirlo.

Tests dados (los escribe Claude; el implementador SOLO crea extremidades/puzzles/nivel_juegos.py). Biblioteca
estándar más takuzu.py y estrellas.py.

Contrato común: en cada paso se aplica UNA vez la primera técnica de la lista que cambie algo y se vuelve a empezar
por la primera; se para cuando ninguna cambia nada. Nunca se adivina: todo lo colocado es correcto. "maxima" es la
técnica más avanzada usada (o None).
- NIVELES = ("facil", "medio", "dificil", "experto").
- TECNICAS_TAKUZU = ("pareja", "hueco", "cuenta", "linea", "unicidad"), sobre filas y columnas:
  * pareja: dos casillas seguidas iguales -> las casillas justo antes y justo después (si están vacías) llevan el
    otro símbolo (rellena una por paso).
  * hueco: X . X -> el hueco lleva el otro símbolo.
  * cuenta: una línea ya tiene n/2 de un símbolo -> sus huecos llevan el otro (toda la línea en un paso).
  * linea: se prueban todas las formas de completar UNA línea sin tres iguales y con n/2 de cada símbolo; las
    casillas que valen lo mismo en todas se fijan.
  * unicidad: como linea, pero quitando además las formas que repiten una línea ya completa del mismo tipo.
- resolver_takuzu(puzzle, n) -> {"resuelto", "rejilla", "tecnicas": {técnica: veces}, "maxima"}; ValueError si
  takuzu.valida es False.
- nivel_takuzu(puzzle, n): "experto" si no se resuelve; si no, maxima pareja/hueco/cuenta/None -> "facil",
  linea -> "medio", unicidad -> "dificil".
- TECNICAS_ESTRELLAS = ("unico_sitio", "bloqueo", "vecindad"), con candidatos = casillas que aún pueden llevar
  estrella (al poner una estrella se quitan su fila, su columna, su zona y sus 8 vecinas):
  * unico_sitio: una fila, columna o zona sin estrella con un solo candidato -> estrella ahí.
  * bloqueo: si los candidatos de una zona caen todos en una misma fila (o columna), se quitan los demás
    candidatos de esa fila (o columna); y si los de una fila o columna caen todos en una misma zona, se quitan los
    demás de esa zona.
  * vecindad: se quita un candidato si, al ponerle estrella, dejaría sin candidatos a alguna fila, columna o zona
    sin estrella que no lo contiene (porque todos sus candidatos son él mismo, su fila, su columna, su zona o sus
    vecinas).
- resolver_estrellas(regiones, n) -> {"resuelto", "estrellas": columna por fila o None, "tecnicas", "maxima"};
  ValueError si las regiones no son válidas.
- nivel_estrellas(regiones, n): "experto" si no se resuelve; maxima unico_sitio/None -> "facil", bloqueo -> "medio",
  vecindad -> "dificil".
- PISTAS_TAKUZU = {6: {"facil": 20, "medio": 16, "dificil": None}, 8: {"facil": 36, "medio": 28, "dificil": None}}.
- generar_takuzu_por_nivel(semilla, n, nivel, intentos=300): prueba takuzu.generar(semilla * 1000 + k, n,
  pistas=PISTAS_TAKUZU[n][nivel]) con k = 0, 1… y devuelve el primero de ese nivel, con "nivel" añadido.
  ValueError si n o nivel no están en PISTAS_TAKUZU; RuntimeError si se agotan los intentos.
- generar_estrellas_por_nivel(semilla, n, nivel, intentos=300): igual con estrellas.generar(semilla * 1000 + k, n).
  ValueError si el nivel no es facil, medio o dificil.
Contrato comun (T1027): si el modulo tiene bloque `if __name__ == "__main__":`, su PRIMERA linea es
`from nucleo import ayuda; ayuda.atender(__doc__)` (o el modulo usa argparse): --help/-h no ejecuta nada. Lo exige
tests/test_ayuda_entradas.py en la suite completa (T938 cayo por eso).
"""
from __future__ import annotations

import pytest

from extremidades.puzzles import estrellas as E
from extremidades.puzzles import nivel_juegos as N
from extremidades.puzzles import takuzu as T

TK = {"facil": "...........1...1.1...11...0..1......", "medio": "1....1..00.0......1.......1.....0.0.",
      "dificil": ".......0.....0..1.1...1.......1...1.", "experto": "...0.1....0.1.........1..1......00.."}
ES = {"facil": "110222114422444422444333444333443353", "medio": "111220111222122222532522552544555544",
      "dificil": "000000111002111002333022355422355422", "experto": "0011122111322211132425333442553444455364445666644"}


@pytest.mark.parametrize("nivel", N.NIVELES)
def test_takuzu_niveles_y_correccion(nivel):
    puzzle = TK[nivel]
    assert T.contar_soluciones(puzzle, 6) == 1
    solucion = T.resolver(puzzle, 6)
    r = N.resolver_takuzu(puzzle, 6)
    assert set(r["tecnicas"]) == set(N.TECNICAS_TAKUZU)
    assert all(x == "." or x == s for x, s in zip(r["rejilla"], solucion))
    assert r["resuelto"] is (nivel != "experto")
    assert N.nivel_takuzu(puzzle, 6) == nivel


@pytest.mark.parametrize("nivel", N.NIVELES)
def test_estrellas_niveles_y_correccion(nivel):
    regiones = [int(x) for x in ES[nivel]]
    n = 7 if nivel == "experto" else 6
    unica = E.soluciones(regiones, n)
    assert len(unica) == 1
    r = N.resolver_estrellas(regiones, n)
    assert set(r["tecnicas"]) == set(N.TECNICAS_ESTRELLAS)
    assert all(x is None or x == y for x, y in zip(r["estrellas"], unica[0]))
    assert r["resuelto"] is (nivel != "experto")
    assert N.nivel_estrellas(regiones, n) == nivel


def test_solidez_en_generados():
    for s in range(6):
        g = T.generar(s, 8)
        assert all(x == "." or x == y for x, y in zip(N.resolver_takuzu(g["puzzle"], 8)["rejilla"], g["solucion"]))
        h = E.generar(s, 7)
        assert all(x is None or x == y for x, y in zip(N.resolver_estrellas(h["regiones"], 7)["estrellas"], h["estrellas"]))


@pytest.mark.parametrize("nivel", ["facil", "medio", "dificil"])
def test_generar_por_nivel(nivel):
    t = N.generar_takuzu_por_nivel(1, 6, nivel)
    assert t["nivel"] == nivel == N.nivel_takuzu(t["puzzle"], 6) and T.contar_soluciones(t["puzzle"], 6) == 1
    assert t == N.generar_takuzu_por_nivel(1, 6, nivel)
    e = N.generar_estrellas_por_nivel(1, 6, nivel)
    assert e["nivel"] == nivel == N.nivel_estrellas(e["regiones"], 6) and len(E.soluciones(e["regiones"], 6)) == 1
    assert e == N.generar_estrellas_por_nivel(1, 6, nivel)


def test_errores():
    with pytest.raises(ValueError):
        N.generar_takuzu_por_nivel(1, 10, "facil")
    with pytest.raises(ValueError):
        N.generar_takuzu_por_nivel(1, 6, "experto")
    with pytest.raises(ValueError):
        N.generar_estrellas_por_nivel(1, 6, "experto")
    with pytest.raises(ValueError):
        N.resolver_takuzu("000" + "." * 33, 6)
    with pytest.raises(ValueError):
        N.resolver_estrellas([0] * 36, 6)
