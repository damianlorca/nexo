# -*- coding: utf-8 -*-
"""Fábrica de puzzles (T689): interior en PDF de libros de Takuzu y de Star Battle, adaptados a papel en blanco y negro.

Tests dados (los escribe Claude; el implementador SOLO crea extremidades/puzzles/pdf_juegos.py). Usa reportlab y los
módulos ya fusionados libro.py, pdf.py (SOLO pdf.area_util), takuzu.py y estrellas.py. Sin red.

Contrato (puntos PDF, 72 por pulgada; origen abajo a la izquierda, como en reportlab):
- JUEGOS = {"takuzu": "Takuzu", "estrellas": "Estrellas"} (clave -> nombre en las etiquetas).
- bordes_regiones(regiones, n) -> list: segmentos gruesos de una casilla de largo ((x0, y0), (x1, y1)) en
  coordenadas de casilla (columna, fila; origen ARRIBA a la izquierda), ordenados y sin repetir: todo el borde
  exterior más cada lado entre dos casillas de regiones distintas. Es lo que sustituye al color en papel.
- maquetar_juego(tipo, puzzles, titulo, subtitulo="", autor="", instrucciones=(), por_pagina=2,
  soluciones_por_pagina=6, ancho=8.5, alto=11) -> list[dict]: como pdf.maquetar del sudoku, una entrada por
  página de libro.plan_paginas, {"numero", "tipo", "rejillas", "textos"} con los mismos textos (portadilla,
  "Instrucciones", "Soluciones"). Cada rejilla: {"indice", "x", "y", "lado", "solucion": bool (True en páginas de
  soluciones), "etiqueta": f"{JUEGOS[tipo]} {indice + 1} · {n}×{n}"}; caben en pdf.area_util de su página y no se
  solapan; en 8,5 x 11 con 2 por página el lado es de 4 in o más.
  * tipo "takuzu": cada puzzle {"puzzle", "solucion", "n"} con takuzu.valida(puzzle, n) y
    takuzu.es_solucion(solucion, n), y cada pista del puzzle coincide con la solución.
  * tipo "estrellas": cada puzzle {"regiones", "estrellas", "n"} con estrellas.es_solucion(estrellas, regiones, n).
  * ValueError si el tipo no está en JUEGOS, si no hay puzzles o si alguno no cumple lo anterior.
- generar_interior_juego(tipo, puzzles, ruta, titulo, ...mismos parámetros...) -> {"paginas", "ruta": str(ruta)}:
  escribe el PDF de maquetar_juego (una página por entrada, de ancho x alto pulgadas). Takuzu: '0' = círculo
  relleno y '1' = anillo, en la casilla. Estrellas: rejilla fina más bordes_regiones en trazo grueso; las estrellas
  se dibujan como figura vectorial (no como texto: la fuente Vera no tiene "★") y solo en las soluciones. Fuentes
  TrueType incrustadas (la Vera de reportlab, registrada aquí con otro nombre si se quiere; nunca las 14 estándar:
  canvas con initialFontName). Determinista (invariant=1).
Contrato comun (T1027): si el modulo tiene bloque `if __name__ == "__main__":`, su PRIMERA linea es
`from nucleo import ayuda; ayuda.atender(__doc__)` (o el modulo usa argparse): --help/-h no ejecuta nada. Lo exige
tests/test_ayuda_entradas.py en la suite completa (T938 cayo por eso).
"""
from __future__ import annotations

import re

import pytest

from extremidades.puzzles import estrellas as E
from extremidades.puzzles import libro
from extremidades.puzzles import pdf
from extremidades.puzzles import pdf_juegos as J
from extremidades.puzzles import takuzu as T

SOL6 = "001011" "010101" "101010" "011001" "100110" "110100"
TK = {"puzzle": SOL6[:20] + "." * 16, "solucion": SOL6, "n": 6}
R5 = [int(x) for x in "1102211122111243332433344"]
ES = {"regiones": R5, "estrellas": [2, 0, 3, 1, 4], "n": 5}


def test_bordes_regiones():
    b = J.bordes_regiones([0, 0, 1, 1], 2)                 # dos filas, dos regiones
    exteriores = {((0, 0), (1, 0)), ((1, 0), (2, 0)), ((0, 2), (1, 2)), ((1, 2), (2, 2)),
                  ((0, 0), (0, 1)), ((0, 1), (0, 2)), ((2, 0), (2, 1)), ((2, 1), (2, 2))}
    assert set(b) == exteriores | {((0, 1), (1, 1)), ((1, 1), (2, 1))}
    assert b == sorted(set(b))
    assert len(J.bordes_regiones([0] * 25, 5)) == 20        # una sola región: solo el borde exterior


@pytest.mark.parametrize("tipo,base", [("takuzu", TK), ("estrellas", ES)])
def test_maquetar_juego(tipo, base):
    pags = J.maquetar_juego(tipo, [dict(base) for _ in range(9)], "Libro", subtitulo="Sub", instrucciones=["Regla"])
    plan = libro.plan_paginas(9)
    assert [(p["numero"], p["tipo"]) for p in pags] == [(p["numero"], p["tipo"]) for p in plan]
    assert pags[0]["textos"] == ["Libro", "Sub"] and pags[1]["textos"] == ["Instrucciones", "Regla"]
    n = base["n"]
    for p, q in zip(pags, plan):
        if p["tipo"] in ("puzzle", "soluciones"):
            assert [r["indice"] for r in p["rejillas"]] == q["indices"]
        x0, y0, x1, y1 = pdf.area_util(p["numero"], len(pags))
        for r in p["rejillas"]:
            assert r["solucion"] is (p["tipo"] == "soluciones")
            assert r["etiqueta"] == f"{J.JUEGOS[tipo]} {r['indice'] + 1} · {n}×{n}"
            assert x0 - 1e-6 <= r["x"] and r["x"] + r["lado"] <= x1 + 1e-6
            assert y0 - 1e-6 <= r["y"] and r["y"] + r["lado"] <= y1 + 1e-6
            if p["tipo"] == "puzzle":
                assert r["lado"] >= 4 * 72 - 1e-6


@pytest.mark.parametrize("tipo,malos", [
    ("sopa", [TK]), ("takuzu", []), ("takuzu", [{**TK, "solucion": SOL6[:-1] + "1"}]),
    ("takuzu", [{**TK, "puzzle": "1" + TK["puzzle"][1:]}]),     # pista que no coincide con la solución
    ("estrellas", [{**ES, "estrellas": [0, 2, 4, 1, 3]}]), ("estrellas", [TK])])
def test_errores(tipo, malos):
    with pytest.raises(ValueError):
        J.maquetar_juego(tipo, malos, "T")


def _pdf(tmp_path, tipo, base, nombre):
    ruta = tmp_path / nombre
    res = J.generar_interior_juego(tipo, [dict(base) for _ in range(5)], ruta, "Prueba", autor="Autor")
    return ruta, res, ruta.read_bytes()


@pytest.mark.parametrize("tipo,base", [("takuzu", TK), ("estrellas", ES)])
def test_pdf(tmp_path, tipo, base):
    ruta, res, datos = _pdf(tmp_path, tipo, base, "a.pdf")
    esperadas = len(J.maquetar_juego(tipo, [dict(base) for _ in range(5)], "Prueba"))
    assert res == {"paginas": esperadas, "ruta": str(ruta)}
    assert len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", datos)) == esperadas
    cajas = re.findall(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]", datos)
    assert cajas and all(tuple(float(v) for v in caja) == (0, 0, 612, 792) for caja in cajas)
    assert b"/FontFile2" in datos
    for estandar in (b"Helvetica", b"Times", b"Courier", b"Symbol", b"ZapfDingbats"):
        assert b"/BaseFont /" + estandar not in datos
    assert _pdf(tmp_path, tipo, base, "b.pdf")[2] == datos


def test_con_generadores_reales(tmp_path):
    tks = [{**T.generar(s, 8), "n": 8} for s in range(3)]
    ess = [E.generar(s, 7) for s in range(3)]
    assert J.generar_interior_juego("takuzu", tks, tmp_path / "t.pdf", "T")["paginas"] == len(libro.plan_paginas(3))
    assert J.generar_interior_juego("estrellas", ess, tmp_path / "e.pdf", "E")["paginas"] == len(libro.plan_paginas(3))
