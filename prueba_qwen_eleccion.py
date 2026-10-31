"""Prueba de la eleccion de categoria de qwen.clasificar().

Offline y exhaustiva: no toca el modelo. Comprueba que lo que antes
salia invertido ahora sale bien, y que no se ha roto lo que ya
funcionaba.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from extremidades.qwen import _elegir_categoria, _normalizar  # noqa: E402


fallos = 0


def caso(dice_el_modelo: str, categorias: list[str], esperado) -> None:
    global fallos

    obtenido = _elegir_categoria(dice_el_modelo, categorias)

    if obtenido == esperado:
        print(f"  VALE  {dice_el_modelo!r:42} -> {obtenido!r}")
    else:
        fallos += 1
        print(f"  FALLA {dice_el_modelo!r:42} -> {obtenido!r}, esperaba {esperado!r}")


print("\n1. LOS CINCO CASOS QUE ANTES SALIAN INVERTIDOS")

caso("no urgente", ["urgente", "no urgente"], "no urgente")
caso("no spam", ["spam", "no spam"], "no spam")
caso("inutil", ["util", "inutil"], "inutil")
caso("sin accion", ["accion", "sin accion"], "sin accion")
caso("beca denegada", ["beca", "beca denegada"], "beca denegada")


print("\n2. Y los contrarios siguen bien")

caso("urgente", ["urgente", "no urgente"], "urgente")
caso("spam", ["spam", "no spam"], "spam")
caso("util", ["util", "inutil"], "util")
caso("accion", ["accion", "sin accion"], "accion")
caso("beca", ["beca", "beca denegada"], "beca")


print("\n3. Da igual el orden en que se pasen las categorias")

caso("no urgente", ["no urgente", "urgente"], "no urgente")
caso("urgente", ["no urgente", "urgente"], "urgente")


print("\n4. Respuestas sucias: mayusculas, puntos, comillas, acentos")

caso("No urgente.", ["urgente", "no urgente"], "no urgente")
caso("  NO URGENTE  ", ["urgente", "no urgente"], "no urgente")
caso('"no urgente"', ["urgente", "no urgente"], "no urgente")
caso("Categoria: no urgente", ["urgente", "no urgente"], "no urgente")
caso("accion", ["acción", "sin acción"], "acción")
caso("sin accion", ["acción", "sin acción"], "sin acción")


print("\n5. El modelo se enrolla aunque se le diga que no")

caso(
    "no urgente - el plazo ya paso hace meses",
    ["urgente", "no urgente"],
    "no urgente",
)

caso(
    "La categoria correcta es no urgente",
    ["urgente", "no urgente"],
    "no urgente",
)


print("\n6. Cuando el modelo no contesta nada util, se dice")

caso("", ["urgente", "no urgente"], None)
caso("   ", ["urgente", "no urgente"], None)
caso("ni idea", ["urgente", "no urgente"], None)
caso("42", ["urgente", "no urgente"], None)


print("\n7. Trampa de subcadena al reves: la categoria corta dentro de una palabra")

# 'util' NO debe saltar dentro de 'inutilizado'
caso("inutilizado", ["util", "inutil"], None)

# pero 'util' suelta si
caso("es util", ["util", "inutil"], "util")


print("\n8. Tres o mas categorias")

cats = ["beca concedida", "beca denegada", "beca", "sin relacion"]

caso("beca denegada", cats, "beca denegada")
caso("beca concedida", cats, "beca concedida")
caso("beca", cats, "beca")
caso("sin relacion", cats, "sin relacion")


print("\n9. _normalizar hace lo que dice")

pruebas_norm = [
    ("Acción", "accion"),
    ("NO URGENTE.", "no urgente"),
    ('  "spam"  ', "spam"),
    ("ñandú", "nandu"),
]

for entrada, esperado in pruebas_norm:
    obtenido = _normalizar(entrada)

    if obtenido == esperado:
        print(f"  VALE  {entrada!r} -> {obtenido!r}")
    else:
        fallos += 1
        print(f"  FALLA {entrada!r} -> {obtenido!r}, esperaba {esperado!r}")


print("\n" + ("TODO VALE" if fallos == 0 else f"{fallos} FALLOS"))

sys.exit(1 if fallos else 0)
