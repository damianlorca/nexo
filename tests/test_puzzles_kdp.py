# -*- coding: utf-8 -*-
"""Piloto de monetización (T689), pieza P0b: medidas y costes de Amazon KDP para tapa blanda (solo cálculo).

Tests dados (los escribe Claude; el implementador SOLO crea extremidades/puzzles/kdp.py, biblioteca estándar).
Datos oficiales de KDP (ayuda G201834560 y G201834340, consultados el 16/10/2026):
- Lomo por página (tinta negra): papel blanco 0.002252", crema 0.0025". Sangrado 0.125". Texto en el lomo solo
  con MÁS de 79 páginas.
- Margen interior (encuadernación) por nº de páginas: 24-150 -> 0.375"; 151-300 -> 0.5"; 301-500 -> 0.625";
  501-700 -> 0.75"; 701-828 -> 0.875". Fuera de 24-828 -> ValueError. Margen exterior mínimo 0.25" sin sangrado.
- Tamaño "grande" = ancho > 6.12" o alto > 9". 8.5x11 es grande; 6x9 es normal.
- Coste de impresión tinta negra (por libro): hasta 110 páginas INCLUIDAS solo coste fijo; desde 111 fijo + por página
  (sobre el total de páginas):
    "es" (EUR, tiendas UE):  normal 2.05 | 0.75 + 0.012/pág ; grande 2.48 | 0.75 + 0.016/pág
    "com" (USD):             normal 2.30 | 1.00 + 0.012/pág ; grande 2.84 | 1.00 + 0.017/pág
- Regalía: 50 % si el precio <= 9.98; 60 % si >= 9.99 (mismo umbral en EUR y USD). regalía = tasa*precio - impresión.

Contrato:
- margen_interior(paginas) -> float (pulgadas), ValueError fuera de 24-828.
- es_grande(ancho, alto) -> bool.
- coste_impresion(paginas, mercado="es", ancho=8.5, alto=11) -> float redondeado a 2 decimales; mercado
  desconocido o páginas fuera de 24-828 -> ValueError.
- regalia(precio, paginas, mercado="es", ancho=8.5, alto=11) -> dict {"tasa", "impresion", "regalia"} con
  "regalia" redondeada a 2 decimales (puede ser negativa: así se ve que el precio no compensa).
- cubierta(paginas, papel="blanco", ancho=8.5, alto=11) -> dict en pulgadas, redondeado a 4 decimales:
  {"lomo", "ancho_total", "alto_total", "texto_lomo"} con ancho_total = 2*ancho + lomo + 2*0.125,
  alto_total = alto + 2*0.125, texto_lomo = paginas > 79. Papel distinto de "blanco"/"crema" -> ValueError.
Contrato comun (T1027): si el modulo tiene bloque `if __name__ == "__main__":`, su PRIMERA linea es
`from nucleo import ayuda; ayuda.atender(__doc__)` (o el modulo usa argparse): --help/-h no ejecuta nada. Lo exige
tests/test_ayuda_entradas.py en la suite completa (T938 cayo por eso).
"""
from __future__ import annotations

import pytest

from extremidades.puzzles import kdp as K


@pytest.mark.parametrize("paginas,margen", [(24, 0.375), (150, 0.375), (151, 0.5), (300, 0.5), (301, 0.625),
                                            (500, 0.625), (501, 0.75), (700, 0.75), (701, 0.875), (828, 0.875)])
def test_margen_interior(paginas, margen):
    assert K.margen_interior(paginas) == margen


@pytest.mark.parametrize("paginas", [23, 829, 0])
def test_margen_fuera_de_rango(paginas):
    with pytest.raises(ValueError):
        K.margen_interior(paginas)


def test_es_grande():
    assert K.es_grande(8.5, 11) and K.es_grande(6.13, 9) and K.es_grande(6, 9.01)
    assert not K.es_grande(6, 9) and not K.es_grande(5, 8)


@pytest.mark.parametrize("paginas,mercado,ancho,alto,esperado", [
    (86, "es", 8.5, 11, 2.48), (110, "es", 8.5, 11, 2.48), (111, "es", 8.5, 11, 2.53),
    (200, "es", 8.5, 11, 3.95), (120, "es", 6, 9, 2.19), (100, "es", 6, 9, 2.05),
    (86, "com", 8.5, 11, 2.84), (200, "com", 8.5, 11, 4.40), (150, "com", 6, 9, 2.80),
])
def test_coste_impresion(paginas, mercado, ancho, alto, esperado):
    assert K.coste_impresion(paginas, mercado, ancho, alto) == pytest.approx(esperado, abs=0.005)


def test_coste_errores():
    with pytest.raises(ValueError):
        K.coste_impresion(100, "jp")
    with pytest.raises(ValueError):
        K.coste_impresion(10, "es")


def test_regalia_umbral_de_precio():
    alta = K.regalia(9.99, 86, "es")
    baja = K.regalia(9.98, 86, "es")
    assert alta["tasa"] == 0.6 and baja["tasa"] == 0.5
    assert alta["impresion"] == pytest.approx(2.48)
    assert alta["regalia"] == pytest.approx(3.51, abs=0.005)
    assert baja["regalia"] == pytest.approx(2.51, abs=0.005)
    assert K.regalia(4.99, 300, "es")["regalia"] < 0


def test_cubierta():
    c = K.cubierta(86, "blanco")
    assert c["lomo"] == pytest.approx(0.1937, abs=0.0001)
    assert c["ancho_total"] == pytest.approx(2 * 8.5 + 0.1937 + 0.25, abs=0.0002)
    assert c["alto_total"] == pytest.approx(11.25)
    assert c["texto_lomo"] is True
    assert K.cubierta(79, "crema")["texto_lomo"] is False
    assert K.cubierta(200, "crema")["lomo"] == pytest.approx(0.5)
    with pytest.raises(ValueError):
        K.cubierta(100, "satinado")
