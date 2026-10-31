# -*- coding: utf-8 -*-
"""Piloto de monetización (T689), pieza P2: cubierta completa de tapa blanda para KDP (PDF de una página).

Tests dados (los escribe Claude; el implementador SOLO crea extremidades/puzzles/cubierta.py). Usa reportlab
(dependencia ya aprobada) y kdp.py (medidas). Cubierta solo tipográfica y vectorial: sin imágenes, así que nada que
declarar como IA. Sin red y sin escribir nada fuera de `ruta`.

Contrato (puntos PDF, 72 por pulgada; origen abajo a la izquierda; cajas = (x0, y0, x1, y1)):
- PT = 72; SEGURIDAD = 0.25 (pulgadas del corte a cualquier texto); LOMO_MINIMO_TEXTO = 0.25 (pulgadas);
  CODIGO_BARRAS = (2.0, 1.2) (ancho, alto en pulgadas: hueco que KDP rellena con el código de barras).
- zonas(paginas, papel="blanco", ancho=8.5, alto=11) -> dict con:
  * "ancho", "alto": tamaño total de la página = kdp.cubierta(...)["ancho_total"] y ["alto_total"], en puntos.
  * "contraportada", "lomo", "portada": cajas de izquierda a derecha, SIN el sangrado (kdp.SANGRADO alrededor):
    contraportada de ancho `ancho`, lomo de ancho kdp.cubierta(...)["lomo"], portada de ancho `ancho`; las tres van
    de y = SANGRADO a y = SANGRADO + alto y son contiguas.
  * "codigo_barras": caja de CODIGO_BARRAS abajo a la derecha de la contraportada, a SEGURIDAD de su borde derecho
    (el del lomo) y de su borde inferior.
  * "texto_lomo": kdp.cubierta(...)["texto_lomo"] y además lomo >= LOMO_MINIMO_TEXTO.
- generar_cubierta(ruta, titulo, paginas, subtitulo="", autor="", contraportada=(), papel="blanco", ancho=8.5,
  alto=11, color=(0.11, 0.25, 0.45)) -> {"ruta": str, "ancho": float, "alto": float, "texto_lomo": bool}: escribe
  un PDF de UNA página del tamaño de zonas(...): fondo de `color` (RGB 0-1) hasta el borde (cubre el sangrado),
  título, subtítulo, autor y una rejilla de sudoku decorativa en la portada, los párrafos de `contraportada` en la
  contraportada sin pisar la caja del código de barras (que queda en blanco) y, solo si texto_lomo, el título en el
  lomo. Todo texto a SEGURIDAD o más de los cortes. ValueError si el título está vacío.
  Fuentes TrueType INCRUSTADAS (Vera de reportlab/fonts); nunca las 14 estándar: registrar la Vera y crear el
  canvas con initialFontName=<ese nombre>. Determinista (invariant=1).
Contrato comun (T1027): si el modulo tiene bloque `if __name__ == "__main__":`, su PRIMERA linea es
`from nucleo import ayuda; ayuda.atender(__doc__)` (o el modulo usa argparse): --help/-h no ejecuta nada. Lo exige
tests/test_ayuda_entradas.py en la suite completa (T938 cayo por eso).
"""
from __future__ import annotations

import re

import pytest

from extremidades.puzzles import cubierta as C
from extremidades.puzzles import kdp


@pytest.mark.parametrize("paginas,papel", [(102, "blanco"), (300, "crema")])
def test_zonas_medidas(paginas, papel):
    z = C.zonas(paginas, papel)
    medidas = kdp.cubierta(paginas, papel)
    s = kdp.SANGRADO * 72
    assert z["ancho"] == pytest.approx(medidas["ancho_total"] * 72)
    assert z["alto"] == pytest.approx(medidas["alto_total"] * 72)
    contra, lomo, portada = z["contraportada"], z["lomo"], z["portada"]
    assert contra[0] == pytest.approx(s) and contra[2] == pytest.approx(s + 8.5 * 72)
    assert lomo[0] == pytest.approx(contra[2]) and lomo[2] - lomo[0] == pytest.approx(medidas["lomo"] * 72)
    assert portada[0] == pytest.approx(lomo[2]) and portada[2] == pytest.approx(z["ancho"] - s)
    for caja in (contra, lomo, portada):
        assert caja[1] == pytest.approx(s) and caja[3] == pytest.approx(s + 11 * 72)


def test_codigo_barras_y_texto_en_lomo():
    z = C.zonas(102)
    x0, y0, x1, y1 = z["codigo_barras"]
    assert (x1 - x0, y1 - y0) == pytest.approx((2.0 * 72, 1.2 * 72))
    assert x1 == pytest.approx(z["contraportada"][2] - 0.25 * 72)
    assert y0 == pytest.approx(z["contraportada"][1] + 0.25 * 72)
    assert z["texto_lomo"] is False                    # 102 págs: lomo de 0,23 in
    assert C.zonas(300)["texto_lomo"] is True          # 300 págs: lomo de 0,68 in
    assert C.zonas(80)["texto_lomo"] is False          # KDP: texto solo con más de 79 págs, y el lomo es estrecho


def _pdf(tmp_path, nombre, paginas=102):
    ruta = tmp_path / nombre
    res = C.generar_cubierta(ruta, "Sudokus de letra grande", paginas, subtitulo="150 sudokus", autor="Autor",
                             contraportada=["Párrafo de prueba.", "Otro párrafo."])
    return ruta, res, ruta.read_bytes()


def test_pdf_una_pagina_tamano_y_fuentes(tmp_path):
    ruta, res, datos = _pdf(tmp_path, "cubierta.pdf")
    z = C.zonas(102)
    assert res == {"ruta": str(ruta), "ancho": pytest.approx(z["ancho"]), "alto": pytest.approx(z["alto"]),
                   "texto_lomo": False}
    assert datos.startswith(b"%PDF-")
    assert len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", datos)) == 1
    caja = re.search(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]", datos)
    assert caja and (float(caja.group(3)), float(caja.group(4))) == pytest.approx((z["ancho"], z["alto"]), abs=0.01)
    assert b"/FontFile2" in datos
    for estandar in (b"Helvetica", b"Times", b"Courier", b"Symbol", b"ZapfDingbats"):
        assert b"/BaseFont /" + estandar not in datos


def test_lomo_con_texto_y_determinista(tmp_path):
    assert _pdf(tmp_path, "gorda.pdf", paginas=300)[1]["texto_lomo"] is True
    assert _pdf(tmp_path, "a.pdf")[2] == _pdf(tmp_path, "b.pdf")[2]


@pytest.mark.parametrize("titulo", ["", "   "])
def test_titulo_obligatorio(tmp_path, titulo):
    with pytest.raises(ValueError):
        C.generar_cubierta(tmp_path / "x.pdf", titulo, 102)
    assert not (tmp_path / "x.pdf").exists()
