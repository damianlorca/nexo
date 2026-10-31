# -*- coding: utf-8 -*-
"""Bloque 23 (29/10): T945 (extremidades/puzzles/cubierta.py) mide con kdp.SANGRADO; T939 dejo el 0.125 suelto en
kdp.cubierta() y la suite de T945 caia con AttributeError sin poder tocar kdp.py (fuera de su lista blanca)."""
from extremidades.puzzles import kdp


def test_sangrado_es_la_constante_que_usa_la_cubierta():
    assert kdp.SANGRADO == 0.125
    m = kdp.cubierta(102)
    assert m["alto_total"] == round(11 + 2 * kdp.SANGRADO, 4)
    assert m["ancho_total"] == round(2 * 8.5 + m["lomo"] + 2 * kdp.SANGRADO, 4)
