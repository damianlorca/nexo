# -*- coding: utf-8 -*-
"""T186 pieza A: detectar ACCIONES DIRECTAS de lista blanca en una orden de Damian, sin IA.

Tests dados (los escribe Claude; el implementador SOLO crea nucleo/orden_accion.py). Contrato:
`detectar(texto: str) -> dict | None`. Funcion PURA: no lee ni escribe nada, no llama a ninguna IA.

Normalizacion previa (solo para reconocer; los valores devueltos salen de ella):
- minusculas, sin tildes (unicodedata NFKD), espacios colapsados, sin "¿¡" iniciales ni ".!?" finales;
- se quita UN prefijo de cortesia al principio si lo hay: "nexo,", "nexo", "porfa,", "porfa", "por favor,", "por favor".
- Texto vacio o de mas de 160 caracteres (tras quitar espacios de los extremos) -> None (un bloque no es una accion).

Acciones (la expresion debe empezar al principio del texto normalizado; ids T + 3 o 4 cifras, devueltos en mayuscula):
1. estado_tarea: "como va|como esta|estado de|que tal va" + [la tarea] + Txxx
   -> {"accion": "estado_tarea", "tarea": "T170"}
2. asignar: "cambia|pasa|asigna|manda" + [la] [tarea] + Txxx + "a" + claude|damian|nexo|ia
   -> {"accion": "asignar", "tarea": "T170", "a": "claude"|"damian"|"ia"}   ("nexo" se devuelve como "ia")
3. prioridad: "sube|baja" + [la] [prioridad de] [la] [tarea] + Txxx
   -> {"accion": "prioridad", "tarea": "T170", "sentido": 1 (sube) | -1 (baja)}
4. turnos: "activa|enciende|reanuda" | "desactiva|apaga|para|pausa" + [los] + "turnos"
   -> {"accion": "turnos", "activar": True|False}
5. aviso: "mandame|enviame|avisame" + ... + una de "notificacion|push|aviso" en cualquier punto del texto;
   minutos = el numero N de "en N min|minuto|minutos" si aparece, si no 0.
   -> {"accion": "aviso", "minutos": 5, "texto": <texto ORIGINAL sin espacios en los extremos>}
Precedencias y casos limite:
- En 1-4, si tras la expresion reconocida queda algo que no sea cortesia ("por favor", "porfa", "gracias", sin
  puntuacion), la orden es compuesta o ambigua -> None. En 5 (aviso) el resto es libre.
- Negaciones ("no cambies...") o cualquier otro verbo al principio -> None. "borra"/"elimina" NUNCA son accion.
- Se prueban en el orden 1, 2, 3, 4, 5; la primera que encaja gana.
- CONJUNTO DE ORO: las ordenes reales de 22-25/09 (T186) estan abajo con su resultado correcto; toda orden mal
  detectada que aparezca se anade aqui.
"""
from __future__ import annotations

import pytest

from nucleo import orden_accion as A

ORO = [
    ("cambia T170 a Claude", {"accion": "asignar", "tarea": "T170", "a": "claude"}),
    ("mándame una notificación push al teléfono en 5 min para comprobar que funcionan",
     {"accion": "aviso", "minutos": 5,
      "texto": "mándame una notificación push al teléfono en 5 min para comprobar que funcionan"}),
    ("investiga Fast-jev compaction", None),
    ("borra algo", None),
    ("investigar y auditar \"claude red\" y añadir a tareas implementacion si conviene", None),
    ("comprueba todas las tareas y haz una lista de si alguna se repite", None),
    ("Esto es una prueba: abre chatgpt y pregúntale cuál puede ser un buen prompt", None),
    ("añadir que nexo tenga acceso a fecha y hora", None),
]


@pytest.mark.parametrize("texto,esperado", ORO)
def test_conjunto_de_oro(texto, esperado):
    assert A.detectar(texto) == esperado


@pytest.mark.parametrize("texto,esperado", [
    ("¿Cómo va T0042?", {"accion": "estado_tarea", "tarea": "T0042"}),
    ("estado de la tarea t745", {"accion": "estado_tarea", "tarea": "T745"}),
    ("Nexo, pasa la tarea T812 a Damián por favor", {"accion": "asignar", "tarea": "T812", "a": "damian"}),
    ("asigna T300 a nexo", {"accion": "asignar", "tarea": "T300", "a": "ia"}),
    ("sube la prioridad de T186", {"accion": "prioridad", "tarea": "T186", "sentido": 1}),
    ("baja T186.", {"accion": "prioridad", "tarea": "T186", "sentido": -1}),
    ("porfa, apaga los turnos", {"accion": "turnos", "activar": False}),
    ("Reanuda turnos!", {"accion": "turnos", "activar": True}),
    ("avísame con un aviso", {"accion": "aviso", "minutos": 0, "texto": "avísame con un aviso"}),
    ("envíame un push en 1 minuto", {"accion": "aviso", "minutos": 1, "texto": "envíame un push en 1 minuto"}),
])
def test_acciones(texto, esperado):
    assert A.detectar(texto) == esperado


@pytest.mark.parametrize("texto", [
    "", "   ", "no cambies T170 a claude", "cambia T170 a claude y borra T171", "cambia T170 a gemini",
    "cambia T17 a claude", "sube la prioridad de T186 y baja T187", "elimina T170", "mándame un correo",
    "cambia T170 a claude " + "x" * 160, "apaga los turnos mañana a las 8",
])
def test_no_son_accion(texto):
    assert A.detectar(texto) is None


def test_cortesia_al_final_no_rompe():
    assert A.detectar("activa los turnos, gracias") == {"accion": "turnos", "activar": True}
