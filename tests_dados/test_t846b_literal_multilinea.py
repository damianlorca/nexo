# -*- coding: utf-8 -*-
"""Seguimiento de T846: el deduplicado de ordenes compara el literal ENTERO, aunque tenga varias lineas.

Tests dados (los escribe Claude; el implementador SOLO cambia nucleo/orden_dedup.py). Va DESPUES de T846.
Defecto (revision de Claude del 12/10): el literal de una tarea se sacaba con re.search sin DOTALL y solo tomaba la
PRIMERA linea; una orden nueva igual a esa primera linea se daba por "identica" a una orden multilinea distinta.
Contrato:
- El texto de una candidata es TODO lo que va despues de la linea "Orden literal de Damián (<canal>):" (todas las
  lineas siguientes, sin espacios en los extremos); si no hay esa linea, su "titulo". El resto del contrato de T846
  (candidatas, normalizado, precedencia identica > parecida, empates) no cambia.
"""
from __future__ import annotations

from datetime import datetime

from nucleo import orden_dedup as D

AHORA = datetime(2026, 10, 13, 12, 0)


def _t(tid, literal):
    return {"id": tid, "titulo": literal.splitlines()[0][:90], "estado": "pendiente", "cerrada": None,
            "creada": "2026-10-12 10:00:00", "etiquetas": [],
            "detalle": f"Orden literal de Damián (web):\n{literal}"}


def test_la_primera_linea_sola_no_es_identica_a_una_orden_multilinea():
    ts = [_t("T900", "revisa el turno de noche\ny luego apaga los avisos de la GPU que salen cada hora")]
    r = D.buscar("revisa el turno de noche", ts, AHORA)
    assert r is None or r["tipo"] != "identica"


def test_la_orden_multilinea_entera_si_es_identica():
    literal = "revisa el turno de noche\ny luego apaga los avisos de la GPU que salen cada hora"
    r = D.buscar(literal.replace("\n", "\n  "), [_t("T900", literal)], AHORA)
    assert r == {"id": "T900", "tipo": "identica", "similitud": 1.0, "estado": "pendiente"}


def test_las_lineas_siguientes_cuentan_para_parecida():
    ts = [_t("T901", "medir la temperatura\nde la GPU cada hora y avisar si pasa de 80 grados")]
    r = D.buscar("medir la temperatura de la GPU cada hora y avisar si pasa de 80", ts, AHORA)
    assert r is not None and r["id"] == "T901" and r["tipo"] == "parecida"
