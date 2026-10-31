"""Prueba del triaje con el obrero nuevo, sobre mensajes REALES.

Los tres textos son mensajes que Damian mando el 11/09 por la manana.
No son ejemplos inventados para que salga bien: son exactamente lo que
el obrero se va a encontrar.

Lo que se comprueba:
- que conteste (el fallo del obrero viejo era devolver vacio)
- que acierte la categoria
- cuanto tarda

La urgencia no se da por fallada si no coincide: "urgente" o "no
urgente" es un juicio, y ahi cabe discrepar. Se imprime para mirarla.
"""

from __future__ import annotations

import time

from extremidades import triaje
from nucleo.config import valor


CASOS = [
    (
        "el de las 06:31 (pantalla)",
        "Tranquilo no ha sonado. Hay q buscar herramientas para q "
        "puedas ver tu propia pantalla o para q otra IA comandada por "
        "ti la vea y te explique cosas asi podras ir viendo tu uso y "
        "recalcular",
        "tarea",
    ),
    (
        "el de las 06:53 (la hora)",
        "Necesito tambien que me confirmes si puedes ver la hora "
        "mientras trabajas, a las 8 vuelve a haber tokens",
        "tarea",
    ),
    (
        "el de las 08:12 (aviso al despertar)",
        "Envia un mensaje por aqui cuando despiertes para comprobar "
        "que todo ok",
        "tarea",
    ),
]


print("=" * 66)
print("PRUEBA DE TRIAJE")
print("=" * 66)
print(f"\nobrero configurado: {valor('qwen.modelo_obrero', '?')}\n")

fallos = 0
total = 0.0

for nombre, texto, categoria_esperada in CASOS:
    print("-" * 66)
    print(nombre)

    inicio = time.time()

    lectura = triaje.triar(texto)

    tardo = time.time() - inicio
    total += tardo

    print(f"  categoria : {lectura['categoria'] or 'VACIA'}"
          f"   (esperaba {categoria_esperada})")
    print(f"  urgencia  : {lectura['urgencia'] or 'VACIA'}")
    print(f"  resumen   : {lectura['resumen'] or 'VACIO'}")
    print(f"  tardo     : {tardo:.1f} s")

    if not lectura["categoria"]:
        print("  FALLO: categoria vacia")
        fallos += 1
    elif lectura["categoria"] != categoria_esperada:
        print(f"  FALLO: esperaba '{categoria_esperada}'")
        fallos += 1

    if not lectura["urgencia"]:
        print("  FALLO: urgencia vacia")
        fallos += 1

    if not lectura["resumen"]:
        print("  FALLO: resumen vacio")
        fallos += 1

print("-" * 66)
print(f"\n{len(CASOS)} mensajes en {total:.1f} s "
      f"({total / len(CASOS):.1f} s por mensaje)")

print(f"\n{fallos} fallos")

if fallos:
    raise SystemExit(1)

print("TODO EN VERDE")

# Referencia contra la que comparar: el obrero viejo tardo 316,8 s en
# UN solo mensaje y devolvio el resumen vacio.
print(f"\nEl obrero viejo (qwen3:4b) tardo 316,8 s en UN mensaje y dejo")
print(f"el resumen vacio. Ahora: {total / len(CASOS):.1f} s por mensaje, completo.")
print("\nFIN_PRUEBA_TRIAJE")
