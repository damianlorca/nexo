"""Prueba de nucleo/escritura.py y de la carga de estado robusta.

Se ejecuta sola y dice VALE o FALLA en cada punto. No toca nada
real: trabaja en una carpeta temporal propia.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo.escritura import escribir_atomico, limpiar_temporales  # noqa: E402


fallos = 0


def comprobar(titulo: str, condicion: bool, detalle: str = "") -> None:
    global fallos

    if condicion:
        print(f"  VALE  {titulo}")
    else:
        fallos += 1
        print(f"  FALLA {titulo} {detalle}")


BANCO = RAIZ / "_pruebas_tmp"

if BANCO.exists():
    shutil.rmtree(BANCO)

BANCO.mkdir(parents=True)

print("\n1. Escritura atomica basica")

destino = BANCO / "cosa.txt"

escribir_atomico(destino, "hola")

comprobar("crea el archivo", destino.is_file())
comprobar("contenido correcto", destino.read_text(encoding="utf-8") == "hola")

escribir_atomico(destino, "adios mundo")

comprobar("sobrescribe entero", destino.read_text(encoding="utf-8") == "adios mundo")


print("\n2. No deja temporales tirados")

sobrantes = list(BANCO.glob(".*.tmp"))

comprobar("sin temporales tras escribir", not sobrantes, str(sobrantes))


print("\n3. Si la escritura revienta, el archivo viejo sigue entero")

escribir_atomico(destino, "VALIOSO")


class Explota(str):
    """Un 'texto' que revienta al escribirse de verdad."""

    def __str__(self):
        raise RuntimeError("boom")


try:
    # Forzamos el fallo a mitad pasando algo que f.write rechaza.
    escribir_atomico(destino, 12345)  # type: ignore[arg-type]
except Exception as e:
    print(f"  (fallo provocado a proposito: {type(e).__name__})")

comprobar(
    "el archivo viejo sobrevive intacto",
    destino.read_text(encoding="utf-8") == "VALIOSO",
    repr(destino.read_text(encoding="utf-8")),
)

comprobar("tampoco deja temporales", not list(BANCO.glob(".*.tmp")))


print("\n4. Crea carpetas que no existian")

hondo = BANCO / "a" / "b" / "c" / "x.txt"

escribir_atomico(hondo, "profundo")

comprobar("escribe en ruta profunda", hondo.is_file())


print("\n5. UTF-8 con acentos y emojis")

escribir_atomico(destino, "camión, ñandú, año — ok")

comprobar(
    "acentos intactos",
    destino.read_text(encoding="utf-8") == "camión, ñandú, año — ok",
)


print("\n6. JSON grande (como estado.json) de ida y vuelta")

grande = {
    "mision": "probar",
    "hechos": [f"hecho numero {i} con acentuación" for i in range(200)],
}

jd = BANCO / "estado_falso.json"

escribir_atomico(jd, json.dumps(grande, ensure_ascii=False, indent=2))

vuelto = json.loads(jd.read_text(encoding="utf-8"))

comprobar("json completo de ida y vuelta", vuelto == grande)


print("\n7. limpiar_temporales barre huerfanos de un corte anterior")

(BANCO / ".huerfano.txt.abc.tmp").write_text("basura", encoding="utf-8")
(BANCO / ".otro.json.xyz.tmp").write_text("basura", encoding="utf-8")

n = limpiar_temporales(BANCO)

comprobar("barre los dos huerfanos", n == 2, f"barrio {n}")
comprobar("no toca los archivos buenos", destino.is_file())


print("\n8. Escrituras seguidas rapidas no se pisan")

for i in range(50):
    escribir_atomico(destino, f"vuelta {i}")

comprobar("ultima escritura gana", destino.read_text(encoding="utf-8") == "vuelta 49")
comprobar("sigue sin temporales", not list(BANCO.glob(".*.tmp")))


shutil.rmtree(BANCO)

print("\n" + ("TODO VALE" if fallos == 0 else f"{fallos} FALLOS"))

sys.exit(1 if fallos else 0)
