"""Prueba de Piper: que genere un WAV de verdad y que suene a algo.

No basta con que el archivo exista. Un WAV de cabecera vacia son 44
bytes y "existe" igual. Aqui se mira el tamano y se lee la cabecera.
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path

from extremidades import voz


FALLOS: list[str] = []
PASADAS = 0


def comprobar(condicion: bool, que: str) -> None:
    global PASADAS

    if condicion:
        PASADAS += 1
        print(f"  ok    {que}")
    else:
        FALLOS.append(que)
        print(f"  FALLO {que}")


print("=" * 62)
print("PRUEBA DE VOZ (Piper)")
print("=" * 62)

comprobar(voz.disponible(), "voz.disponible() dice que si")

texto = (
    "Hola Damian. Soy Nexo. Si oyes esto, la voz ya funciona en el "
    "equipo y el altavoz de casa puede hablar."
)

print(f"\ntexto: {texto}\n")

destino = Path("salidas") / "prueba_voz.wav"

salida = voz.narrar(texto, destino)

comprobar(salida.is_file(), f"se creo el archivo {salida.name}")

tam = salida.stat().st_size

print(f"\n  tamano: {tam} bytes ({tam / 1024:.1f} KB)")

comprobar(tam > 20000, "pesa mas de 20 KB (no es un WAV vacio)")

with wave.open(str(salida), "rb") as w:
    canales = w.getnchannels()
    hercios = w.getframerate()
    marcos = w.getnframes()
    segundos = marcos / hercios if hercios else 0

print(f"  canales: {canales}   frecuencia: {hercios} Hz")
print(f"  duracion: {segundos:.2f} s")

comprobar(hercios >= 16000, "frecuencia de muestreo razonable")
comprobar(segundos > 2.0, "dura mas de dos segundos")

# Que no sea silencio: si todas las muestras son cero, Piper ha
# escrito una cabecera y nada mas.
with wave.open(str(salida), "rb") as w:
    crudo = w.readframes(min(marcos, hercios * 3))

muestras = struct.unpack(f"<{len(crudo) // 2}h", crudo[: len(crudo) // 2 * 2])

pico = max(abs(m) for m in muestras) if muestras else 0

print(f"  pico de amplitud: {pico} (de 32767)")

comprobar(pico > 1000, "hay sonido de verdad, no silencio")

print("\n" + "=" * 62)
print(f"{PASADAS} en verde, {len(FALLOS)} en rojo")

if FALLOS:
    raise SystemExit(1)

print("TODO EN VERDE")
print(f"\nEl WAV esta en: {salida.resolve()}")
