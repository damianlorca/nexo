# -*- coding: utf-8 -*-
"""Piloto de monetización (T689), pieza P1b: interior del libro de sudokus en PDF, listo para KDP.

Tests dados (los escribe Claude; el implementador SOLO crea extremidades/puzzles/pdf.py). Usa reportlab, dependencia
aprobada para esto que Claude añade a requirements antes de esta pieza, y los módulos ya fusionados libro.py (plan de
páginas) y kdp.py (margen interior). Sin red y sin escribir nada fuera de `ruta`.

Contrato (medidas en puntos PDF: 72 por pulgada; origen abajo a la izquierda, como en reportlab):
- PT = 72; MARGEN_EXTERIOR = 0.5 y MARGEN_VERTICAL = 0.5 (pulgadas; KDP pide al menos 0,25 sin sangrado).
- NIVELES = {"facil": "Fácil", "medio": "Medio", "dificil": "Difícil"}.
- area_util(numero, n_paginas, ancho=8.5, alto=11) -> (x0, y0, x1, y1) en puntos. Página impar (recto): margen
  interior a la IZQUIERDA y MARGEN_EXTERIOR a la derecha; página par (verso): al revés. MARGEN_VERTICAL arriba y
  abajo. Margen interior = kdp.margen_interior(n_paginas), y con menos de 24 páginas el de 24 (KDP no imprime libros
  tan cortos, pero sirve para pruebas).
- maquetar(puzzles, titulo, subtitulo="", autor="", instrucciones=(), por_pagina=2, soluciones_por_pagina=6,
  ancho=8.5, alto=11) -> list[dict]: una entrada por página de libro.plan_paginas(len(puzzles), por_pagina,
  soluciones_por_pagina), en el mismo orden: {"numero", "tipo", "rejillas": list[dict], "textos": list[str]}.
  * puzzles: lista de {"puzzle": 81 dígitos '0'-'9', "solucion": 81 dígitos, "nivel": opcional}, como los da
    sudoku.generar_nivel. ValueError si está vacía o si a alguno le falta puzzle o solucion de 81 dígitos.
  * Cada rejilla: {"indice", "x", "y", "lado", "digitos", "etiqueta"}. (x, y) es la esquina inferior izquierda y
    lado el del cuadrado, en puntos. "digitos" es el puzzle (páginas "puzzle") o la solucion (páginas
    "soluciones"). Los índices de cada página son los de su página del plan, en el mismo orden.
  * "etiqueta": "Sudoku N" (N = indice + 1) y, solo en páginas "puzzle" con nivel conocido, " · " + NIVELES[nivel]
    (por ejemplo "Sudoku 1 · Fácil").
  * Las rejillas caben enteras en area_util de su página y no se solapan entre sí.
  * Letra grande (en 8,5 x 11): lado mínimo en pulgadas = puzzles 1 por página 6,0; 2 por página 4,0; 4 por página
    3,0; soluciones 4 por página 3,0; 6 por página 2,25; 9 por página 2,0.
  * textos: portadilla = [titulo, subtitulo, autor] quitando los vacíos; instrucciones = ["Instrucciones",
    *instrucciones]; soluciones = ["Soluciones"]; puzzle y blanca = []. Portadilla, instrucciones y blanca no
    llevan rejillas.
- generar_interior(puzzles, ruta, titulo, subtitulo="", autor="", instrucciones=(), por_pagina=2,
  soluciones_por_pagina=6, ancho=8.5, alto=11) -> {"paginas": int, "ruta": str(ruta)}: escribe en `ruta` el PDF de
  maquetar(...), una página por entrada y todas de ancho x alto pulgadas. Dibuja cada rejilla de 9 x 9 (líneas de
  caja 3 x 3 más gruesas), los dígitos distintos de '0' centrados en su casilla, la etiqueta encima y los textos.
  Fuentes TrueType INCRUSTADAS, porque KDP lo exige: las Bitstream Vera que trae reportlab (reportlab/fonts/Vera.ttf
  y VeraBd.ttf). Nunca las 14 estándar (Helvetica, Times, Courier...), que no se incrustan. Ojo: reportlab pone
  Helvetica como fuente inicial de cada página si no se le dice otra, así que hay que registrar antes la Vera
  (pdfmetrics.registerFont(TTFont(...))) y crear el canvas con initialFontName=<ese nombre>. Determinista (canvas
  con invariant=1): la misma entrada da el mismo archivo byte a byte.
- trozos(texto) -> list[(str, bool)]: parte un párrafo en tramos normales (False) y en negrita (True): lo que va
  entre dos asteriscos es negrita y los asteriscos no se imprimen; si el número de asteriscos es impar, el último
  se queda como texto normal. Sin tramos vacíos. generar_interior escribe así los párrafos de `instrucciones`
  (negrita con la VeraBd), ajustando las líneas al ancho de area_util de la página 2, con el cuerpo que da
  cuerpo_instrucciones.
- TAMANOS_CUERPO = (14, 13, 12, 11, 10, 9). cuerpo_instrucciones(instrucciones, n_paginas, ancho=8.5, alto=11) -> int:
  el MAYOR de esos tamaños (pt) con el que todos los párrafos caben en el área útil de la página de instrucciones
  (página 2), bajo el título "Instrucciones" (17/10: en A5, 5,83 x 8,27 in, el texto de Damián no cabe a 14 pt).
  ValueError si no caben ni al menor. generar_interior lanza el mismo ValueError.
Contrato comun (T1027): si el modulo tiene bloque `if __name__ == "__main__":`, su PRIMERA linea es
`from nucleo import ayuda; ayuda.atender(__doc__)` (o el modulo usa argparse): --help/-h no ejecuta nada. Lo exige
tests/test_ayuda_entradas.py en la suite completa (T938 cayo por eso).
"""
from __future__ import annotations

import re

import pytest

from extremidades.puzzles import kdp, libro
from extremidades.puzzles import pdf as P

A5 = (5.83, 8.27)
TEXTO_LARGO = [("Tu objetivo es rellenar todas las casillas vacías de la cuadrícula *correctamente*. " * 4).strip(),
               "*La única norma: del 1 al 9 sin repetir*",
               ("El tablero tiene *9 filas*, *9 columnas* y *9 cuadrados de 3×3*; ningún número se repite. " * 4).strip(),
               ("Empieza por la fila, columna o cuadrado con menos *huecos libres* y juega por descarte. " * 4).strip(),
               "¡Mucha suerte!"]

PUZZLE = "530070000600195000098000060800060003400803001700020006060000280000419005000080079"
SOLUCION = "534678912672195348198342567859761423426853791713924856961537284287419635345286179"
NIVELES = ["facil", "medio", "dificil"]
LADO_MINIMO = {("puzzle", 1): 6.0, ("puzzle", 2): 4.0, ("puzzle", 4): 3.0,
               ("soluciones", 4): 3.0, ("soluciones", 6): 2.25, ("soluciones", 9): 2.0}


def _puzzles(n):
    return [{"puzzle": PUZZLE, "solucion": SOLUCION, "pistas": 30, "nivel": NIVELES[i % 3]} for i in range(n)]


def test_area_util_recto_y_verso():
    mi = kdp.margen_interior(102) * 72                      # 0,375 in
    assert P.area_util(1, 102) == pytest.approx((mi, 36, 8.0 * 72, 10.5 * 72))
    assert P.area_util(2, 102) == pytest.approx((36, 36, 8.5 * 72 - mi, 10.5 * 72))
    assert P.area_util(3, 200)[0] == pytest.approx(kdp.margen_interior(200) * 72)   # 0,5 in
    assert P.area_util(1, 6) == pytest.approx(P.area_util(1, 24))                   # libro corto: margen de 24


def test_maquetar_sigue_el_plan_y_pone_los_textos():
    pags = P.maquetar(_puzzles(150), "Sudokus de letra grande", subtitulo="150 sudokus", autor="",
                      instrucciones=["Regla 1", "Regla 2"])
    plan = libro.plan_paginas(150)
    assert len(pags) == 102
    assert [(p["numero"], p["tipo"]) for p in pags] == [(p["numero"], p["tipo"]) for p in plan]
    for p, q in zip(pags, plan):
        assert [r["indice"] for r in p["rejillas"]] == (q["indices"] if q["tipo"] in ("puzzle", "soluciones") else [])
    assert pags[0]["textos"] == ["Sudokus de letra grande", "150 sudokus"]
    assert pags[1]["textos"] == ["Instrucciones", "Regla 1", "Regla 2"]
    for p in pags:
        if p["tipo"] == "soluciones":
            assert p["textos"] == ["Soluciones"]
        elif p["tipo"] in ("puzzle", "blanca"):
            assert p["textos"] == []


def test_maquetar_digitos_y_etiquetas():
    vistos = {"puzzle": [], "soluciones": []}
    for p in P.maquetar(_puzzles(7), "T"):
        for r in p["rejillas"]:
            vistos[p["tipo"]].append(r["indice"])
            if p["tipo"] == "puzzle":
                assert r["digitos"] == PUZZLE
                assert r["etiqueta"] == f"Sudoku {r['indice'] + 1} · {P.NIVELES[NIVELES[r['indice'] % 3]]}"
            else:
                assert r["digitos"] == SOLUCION
                assert r["etiqueta"] == f"Sudoku {r['indice'] + 1}"
    assert vistos == {"puzzle": list(range(7)), "soluciones": list(range(7))}
    sin_nivel = P.maquetar([{"puzzle": PUZZLE, "solucion": SOLUCION}], "T")
    assert [r["etiqueta"] for p in sin_nivel for r in p["rejillas"]] == ["Sudoku 1", "Sudoku 1"]


@pytest.mark.parametrize("por_pagina,soluciones", [(1, 4), (2, 6), (4, 9)])
def test_rejillas_caben_no_se_solapan_y_son_de_letra_grande(por_pagina, soluciones):
    pags = P.maquetar(_puzzles(37), "T", por_pagina=por_pagina, soluciones_por_pagina=soluciones)
    for p in pags:
        x0, y0, x1, y1 = P.area_util(p["numero"], len(pags))
        rs = p["rejillas"]
        for r in rs:
            assert r["x"] >= x0 - 1e-6 and r["y"] >= y0 - 1e-6
            assert r["x"] + r["lado"] <= x1 + 1e-6 and r["y"] + r["lado"] <= y1 + 1e-6
            minimo = LADO_MINIMO[(p["tipo"], por_pagina if p["tipo"] == "puzzle" else soluciones)]
            assert r["lado"] >= minimo * 72 - 1e-6
        for a in range(len(rs)):
            for b in range(a + 1, len(rs)):
                ra, rb = rs[a], rs[b]
                assert (ra["x"] + ra["lado"] <= rb["x"] + 1e-6 or rb["x"] + rb["lado"] <= ra["x"] + 1e-6 or
                        ra["y"] + ra["lado"] <= rb["y"] + 1e-6 or rb["y"] + rb["lado"] <= ra["y"] + 1e-6)


@pytest.mark.parametrize("malos", [[], [{"puzzle": PUZZLE[:80], "solucion": SOLUCION}],
                                   [{"puzzle": PUZZLE, "solucion": "x" * 81}], [{"puzzle": PUZZLE}]])
def test_errores(malos):
    with pytest.raises(ValueError):
        P.maquetar(malos, "T")


def _pdf(tmp_path, nombre):
    ruta = tmp_path / nombre
    res = P.generar_interior(_puzzles(5), ruta, "Sudokus de prueba", autor="Autor", instrucciones=["Regla"])
    return ruta, res, ruta.read_bytes()


def test_pdf_paginas_tamano_y_fuentes_incrustadas(tmp_path):
    ruta, res, datos = _pdf(tmp_path, "interior.pdf")
    esperadas = len(P.maquetar(_puzzles(5), "Sudokus de prueba"))
    assert res == {"paginas": esperadas, "ruta": str(ruta)}
    assert datos.startswith(b"%PDF-")
    assert len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", datos)) == esperadas
    cajas = re.findall(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]", datos)
    assert cajas and all(tuple(float(v) for v in caja) == (0, 0, 612, 792) for caja in cajas)
    assert b"/FontFile2" in datos
    for estandar in (b"Helvetica", b"Times", b"Courier", b"Symbol", b"ZapfDingbats"):
        assert b"/BaseFont /" + estandar not in datos


def test_pdf_determinista(tmp_path):
    assert _pdf(tmp_path, "a.pdf")[2] == _pdf(tmp_path, "b.pdf")[2]


@pytest.mark.parametrize("texto,esperado", [
    ("a *b* c", [("a ", False), ("b", True), (" c", False)]),
    ("*todo en negrita*", [("todo en negrita", True)]),
    ("sin marcas", [("sin marcas", False)]),
    ("3*4 = 12", [("3*4 = 12", False)]),
    ("*uno* y *dos*", [("uno", True), (" y ", False), ("dos", True)]),
])
def test_trozos(texto, esperado):
    assert P.trozos(texto) == esperado


def test_instrucciones_con_negrita_y_demasiado_largas(tmp_path):
    ruta = tmp_path / "n.pdf"
    P.generar_interior(_puzzles(4), ruta, "T", instrucciones=["Texto con *negrita* en medio y una palabra *muy* larga."])
    assert ruta.read_bytes().count(b"/FontFile2") >= 2              # normal y negrita incrustadas
    with pytest.raises(ValueError):
        P.generar_interior(_puzzles(4), tmp_path / "largo.pdf", "T", instrucciones=["palabra " * 2000])


def test_cuerpo_instrucciones_baja_hasta_caber():
    assert P.TAMANOS_CUERPO == (14, 13, 12, 11, 10, 9)
    assert P.cuerpo_instrucciones(["Regla corta"], 104) == 14
    carta = P.cuerpo_instrucciones(TEXTO_LARGO, 104)
    a5 = P.cuerpo_instrucciones(TEXTO_LARGO, 188, *A5)
    assert a5 in P.TAMANOS_CUERPO and a5 < carta                     # en A5 cabe, pero más pequeño
    with pytest.raises(ValueError):
        P.cuerpo_instrucciones(["palabra " * 2000], 188, *A5)


def test_libro_a5_dos_por_pagina(tmp_path):
    pags = P.maquetar(_puzzles(300), "T", por_pagina=2, soluciones_por_pagina=9, ancho=A5[0], alto=A5[1])
    assert len(pags) == len(libro.plan_paginas(300, 2, 9))
    for p in pags:
        x0, y0, x1, y1 = P.area_util(p["numero"], len(pags), *A5)
        rs = p["rejillas"]
        for r in rs:
            assert x0 - 1e-6 <= r["x"] and r["x"] + r["lado"] <= x1 + 1e-6
            assert y0 - 1e-6 <= r["y"] and r["y"] + r["lado"] <= y1 + 1e-6
        if p["tipo"] == "puzzle":
            assert all(r["lado"] >= 3.0 * 72 for r in rs)                # rejilla de 7,6 cm o más
    ruta = tmp_path / "a5.pdf"
    res = P.generar_interior(_puzzles(20), ruta, "T", instrucciones=TEXTO_LARGO, ancho=A5[0], alto=A5[1])
    datos = ruta.read_bytes()
    cajas = re.findall(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]", datos)
    assert res["paginas"] == len(cajas) and all(tuple(round(float(v), 2) for v in caja) == (0, 0, 419.76, 595.44)
                                                for caja in cajas)
