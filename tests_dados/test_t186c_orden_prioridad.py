# -*- coding: utf-8 -*-
"""T186 pieza C: importancia y urgencia de una orden estimadas por reglas, con justificacion. Sin IA.

Tests dados (los escribe Claude; el implementador SOLO crea nucleo/orden_prioridad.py). Contrato:
`estimar(texto: str) -> {"importancia": int, "urgencia": int, "justificacion": str, "sin_estimar": bool}`.
Funcion PURA. Se busca sobre el texto en minusculas y sin tildes, por palabras o frases completas (limites de
palabra: "hoyo" no es "hoy", "yate" no es "ya").

Valor de cada campo = la senal MAS EXTREMA: si todas son >= 4, la mayor; si todas son <= 2, la menor
("algun dia, sin prisa" -> 1). Una frase contenida en otra mas larga que tambien aparece no cuenta aparte
("muy importante" no suma "importante"; "esto es una prueba" no suma "es una prueba").
Senales de URGENCIA:
  5: "urgente", "ya mismo", "ahora mismo", "inmediatamente"
  4: "hoy", "cuanto antes", "esta tarde", "esta noche"
  2: "cuando puedas", "sin prisa", "esta semana"
  1: "a largo plazo", "algun dia", "mas adelante", "cuando haya tiempo"
Senales de IMPORTANCIA:
  5: "critico", "muy importante", "prioridad maxima"
  4: "importante"
  1: "es una prueba", "esto es una prueba", "solo probar"
Reglas:
- Sin senal de urgencia -> urgencia 3; sin senal de importancia -> importancia 3.
- CONTRADICCION: senales de urgencia de los dos lados (alguna >= 4 y alguna <= 2) -> urgencia 3; igual con
  importancia (>= 4 y 1). Una contradiccion cuenta como "sin senal" para ese campo.
- sin_estimar = True solo si NINGUN campo tiene senal valida (los dos quedan en 3).
- justificacion: "sin senales" si sin_estimar; si no, las senales usadas separadas por ", " en el orden en que
  aparecen en el texto (cada una tal cual esta en las listas de arriba), y si hubo contradiccion, ademas
  "contradiccion en urgencia" o "contradiccion en importancia" al final.
"""
from __future__ import annotations

import pytest

from nucleo import orden_prioridad as P


def test_sin_senales():
    assert P.estimar("investiga Remotion para editar videos") == {
        "importancia": 3, "urgencia": 3, "justificacion": "sin senales", "sin_estimar": True}


@pytest.mark.parametrize("texto,imp,urg", [
    ("Urgente: el bot no arranca", 3, 5),
    ("arregla esto hoy", 3, 4),
    ("cuando puedas mira lo de la GPU", 3, 2),
    ("tarea a largo plazo: anadir un presentador", 3, 1),
    ("es importante revisar los permisos", 4, 3),
    ("MUY IMPORTANTE y ya mismo: la parada no funciona", 5, 5),
    ("Esto es una prueba: abre chatgpt", 1, 3),
    ("crítico, inmediatamente", 5, 5),
    ("algún día, sin prisa", 3, 1),
])
def test_senales(texto, imp, urg):
    r = P.estimar(texto)
    assert (r["importancia"], r["urgencia"], r["sin_estimar"]) == (imp, urg, False)


def test_justificacion_en_orden_de_aparicion():
    assert P.estimar("hoy es importante")["justificacion"] == "hoy, importante"
    assert P.estimar("Esto es una prueba, hoy")["justificacion"] == "esto es una prueba, hoy"


def test_contradiccion_de_urgencia():
    r = P.estimar("urgente pero sin prisa, es importante")
    assert (r["urgencia"], r["importancia"], r["sin_estimar"]) == (3, 4, False)
    assert r["justificacion"] == "importante, contradiccion en urgencia"


def test_contradiccion_total_es_sin_estimar():
    r = P.estimar("urgente o mas adelante")
    assert (r["urgencia"], r["importancia"], r["sin_estimar"]) == (3, 3, True)
    assert r["justificacion"] == "sin senales"


@pytest.mark.parametrize("texto", ["el hoyo de la carretera", "compra un yate", "importantes no hay"])
def test_limites_de_palabra(texto):
    assert P.estimar(texto)["sin_estimar"] is True
