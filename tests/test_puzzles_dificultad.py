# -*- coding: utf-8 -*-
"""Piloto de monetización (T689), pieza P0c: dificultad real de un sudoku según las técnicas que necesita una persona.

Por qué: el número de pistas engaña. Con la referencia, de 40 sudokus de 28 pistas ("difícil" por pistas) 29 eran
de nivel medio, 4 fáciles y 6 imposibles sin técnicas avanzadas; justo lo que castigan las reseñas.

Tests dados (los escribe Claude; el implementador SOLO crea extremidades/puzzles/dificultad.py). Biblioteca estándar
y sudoku.py (P0a: valida, resolver, contar_soluciones, generar).

Contrato:
- TECNICAS = ("solitario_desnudo", "solitario_oculto", "bloqueo", "pareja_desnuda", "pareja_oculta"), de más fácil a
  más difícil:
  * solitario_desnudo: una casilla con un solo candidato -> se coloca.
  * solitario_oculto: un dígito que en una fila, columna o caja solo cabe en una casilla -> se coloca.
  * bloqueo (candidatos bloqueados): si en una caja un dígito solo cabe en una fila o columna, se quita de esa
    fila o columna fuera de la caja; y si en una fila o columna solo cabe dentro de una caja, se quita del resto de
    la caja.
  * pareja_desnuda: dos casillas de una unidad con los mismos dos candidatos -> esos dos se quitan del resto de la
    unidad.
  * pareja_oculta: dos dígitos que en una unidad solo caben en las mismas dos casillas -> esas casillas se quedan
    solo con esos dos.
- NIVELES = ("facil", "medio", "dificil", "experto").
- resolver_logico(rejilla) -> {"resuelto": bool, "rejilla": str de 81, "tecnicas": {técnica: veces} con las 5
  claves, "maxima": la técnica más difícil usada o None}: parte de los candidatos de la rejilla y, en cada paso,
  aplica UNA vez la primera técnica de TECNICAS que cambie algo (colocar o quitar candidatos) y vuelve a empezar
  por la primera; para cuando ninguna cambia nada. Nunca adivina: todo lo colocado es correcto. ValueError si
  sudoku.valida(rejilla) es False.
- nivel(rejilla) -> str: "experto" si resolver_logico no la resuelve; si la resuelve: "facil" si maxima es None o
  solitario_desnudo, "medio" si es solitario_oculto y "dificil" si es bloqueo o una pareja.
- generar_por_nivel(semilla, nivel, intentos=300) -> dict como sudoku.generar más "nivel": prueba
  sudoku.generar(semilla * 1000 + k, pistas) con k = 0, 1, 2... (pistas: facil 40, medio 32, dificil 26) y devuelve
  el primero cuyo nivel() es el pedido. Determinista. ValueError si el nivel no es facil, medio o dificil;
  RuntimeError si se agotan los intentos.
Contrato comun (T1027): si el modulo tiene bloque `if __name__ == "__main__":`, su PRIMERA linea es
`from nucleo import ayuda; ayuda.atender(__doc__)` (o el modulo usa argparse): --help/-h no ejecuta nada. Lo exige
tests/test_ayuda_entradas.py en la suite completa (T938 cayo por eso).
"""
from __future__ import annotations

import pytest

from extremidades.puzzles import dificultad as D
from extremidades.puzzles import sudoku as S

CLASICO = "530070000600195000098000060800060003400803001700020006060000280000419005000080079"
FACIL = "072503040306821700100406280280100430003700590457000002520030000008604001900008075"
MEDIO = "380710009005830647270905381967300400452000010001509006009003864700006000040050000"
DIFICIL = "000010048280670000091500200000000000307000000810000092000900006040820003160300084"
EXPERTO = "800000000003600000070090200050007000000045700000100030001000068008500010090000400"   # A. Inkala, 2012


@pytest.mark.parametrize("rejilla,esperado,maxima", [
    (CLASICO, "facil", "solitario_desnudo"), (FACIL, "facil", "solitario_desnudo"),
    (MEDIO, "medio", "solitario_oculto"), (DIFICIL, "dificil", "bloqueo"), (EXPERTO, "experto", None)])
def test_niveles_de_referencia(rejilla, esperado, maxima):
    assert D.nivel(rejilla) == esperado
    r = D.resolver_logico(rejilla)
    assert set(r["tecnicas"]) == set(D.TECNICAS)
    if maxima:
        assert r["maxima"] == maxima


@pytest.mark.parametrize("rejilla", [CLASICO, FACIL, MEDIO, DIFICIL, EXPERTO])
def test_nunca_coloca_mal(rejilla):
    solucion = S.resolver(rejilla)
    r = D.resolver_logico(rejilla)
    assert all(p == "0" or p == q for p, q in zip(rejilla, r["rejilla"]))          # respeta las pistas
    assert all(x == "0" or x == s for x, s in zip(r["rejilla"], solucion))         # nada incorrecto
    assert r["resuelto"] == (r["rejilla"] == solucion)
    assert r["resuelto"] is (rejilla != EXPERTO)


def test_solidez_en_generados():
    for semilla in range(8):
        p = S.generar(semilla, 26)
        r = D.resolver_logico(p["puzzle"])
        assert all(x == "0" or x == s for x, s in zip(r["rejilla"], p["solucion"]))


@pytest.mark.parametrize("pedido", ["facil", "medio", "dificil"])
def test_generar_por_nivel(pedido):
    for semilla in (1, 2):
        p = D.generar_por_nivel(semilla, pedido)
        assert p["nivel"] == pedido and D.nivel(p["puzzle"]) == pedido
        assert S.contar_soluciones(p["puzzle"]) == 1
        assert p == D.generar_por_nivel(semilla, pedido)


@pytest.mark.parametrize("malo", ["experto", "imposible"])
def test_generar_por_nivel_errores(malo):
    with pytest.raises(ValueError):
        D.generar_por_nivel(1, malo)


def test_rejilla_no_valida():
    with pytest.raises(ValueError):
        D.resolver_logico("55" + "0" * 79)
