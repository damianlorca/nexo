"""Pruebas de extremidades/base.py (el inventario).

Lo que se comprueba:
  1. Forma: estan las seis extremidades y cada una trae para/listo/arranque.
  2. L1: una sonda que revienta NO tumba el inventario; esa sale rota y
     las demas siguen respondiendo.
  3. Varias rotas a la vez tampoco lo tumban.
  4. resumen() distingue "apagada" (dice como encenderla) de "rota"
     (dice que ha petado).
  5. Coherencia: lo que dice el inventario de video es lo mismo que dice
     extremidades.video, no una copia que pueda desviarse.
  6. 'papers' no tiene sonda y se declara siempre listo (son APIs publicas).

Se ejecuta con: .venv\\Scripts\\python.exe prueba_base.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from extremidades import base

fallos: list[str] = []
comprobaciones = 0


def comprobar(condicion: bool, que: str) -> None:
    global comprobaciones

    comprobaciones += 1

    if condicion:
        print(f"  ok   {que}")
    else:
        print(f"  FALLO {que}")
        fallos.append(que)


def con_sondas(**rotas):
    """Sustituye sondas por otras que hacen lo que se le diga.

    Devuelve una funcion que restaura el original.
    """

    originales = dict(base.EXTREMIDADES)

    nuevo = {}

    for nombre, (para, arranque, sonda) in originales.items():
        nuevo[nombre] = (para, arranque, rotas.get(nombre, sonda))

    base.EXTREMIDADES = nuevo

    def restaurar() -> None:
        base.EXTREMIDADES = originales

    return restaurar


def revienta(excepcion):
    def sonda() -> bool:
        raise excepcion

    return sonda


def fija(valor: bool):
    def sonda() -> bool:
        return valor

    return sonda


print("\n[1] Forma del inventario")

inv = base.inventario()

esperadas = {"qwen", "papers", "imagen", "voz", "video", "navegador"}

comprobar(set(inv) == esperadas, f"estan las seis extremidades: {sorted(inv)}")

for nombre, datos in inv.items():
    comprobar("para" in datos, f"{nombre} trae 'para'")
    comprobar("arranque" in datos, f"{nombre} trae 'arranque'")
    comprobar(isinstance(datos.get("listo"), bool), f"{nombre}.listo es bool")


print("\n[2] L1: una sonda rota no tumba el inventario")

restaurar = con_sondas(imagen=revienta(ValueError("URL mal formada")))

try:
    inv = base.inventario()

    comprobar(set(inv) == esperadas, "siguen estando las seis")
    comprobar(inv["imagen"]["listo"] is False, "imagen sale como no lista")
    comprobar("ValueError" in inv["imagen"].get("error", ""), "imagen dice por que")
    comprobar("error" not in inv["papers"], "papers no arrastra el error de imagen")
    comprobar(inv["papers"]["listo"] is True, "papers sigue respondiendo")
except Exception as e:
    comprobar(False, f"inventario() ha reventado: {type(e).__name__}: {e}")
finally:
    restaurar()


print("\n[3] Varias rotas a la vez, y de tipos distintos")

restaurar = con_sondas(
    imagen=revienta(OSError("disco")),
    voz=revienta(KeyboardInterrupt()) if False else revienta(RuntimeError("piper")),
    navegador=revienta(ImportError("falta httpx")),
)

try:
    inv = base.inventario()

    comprobar(set(inv) == esperadas, "siguen estando las seis con tres rotas")

    for nombre in ("imagen", "voz", "navegador"):
        comprobar(inv[nombre]["listo"] is False, f"{nombre} sale no lista")
        comprobar(bool(inv[nombre].get("error")), f"{nombre} explica el fallo")
except Exception as e:
    comprobar(False, f"inventario() ha reventado: {type(e).__name__}: {e}")
finally:
    restaurar()


print("\n[4] resumen() distingue apagada de rota")

restaurar = con_sondas(
    imagen=revienta(ValueError("comfyui mal configurado")),
    voz=fija(False),
    qwen=fija(True),
)

try:
    texto = base.resumen()

    comprobar("ROTA:" in texto, "la rota aparece marcada como ROTA")
    comprobar("comfyui mal configurado" in texto, "el resumen dice el motivo")
    comprobar("Descarga Piper" in texto, "la apagada dice como encenderla")
    comprobar(
        "OK  qwen" in texto, "la encendida sale con OK y sin instrucciones"
    )

    lineas_qwen = [ln for ln in texto.splitlines() if "qwen" in ln]
    comprobar(len(lineas_qwen) == 1, "la encendida ocupa una sola linea")
finally:
    restaurar()


print("\n[5] Coherencia con extremidades.video")

from extremidades import video

inv = base.inventario()

comprobar(
    inv["video"]["listo"] == video.disponible(),
    "el inventario y video.disponible() dicen lo mismo",
)


print("\n[6] papers no tiene sonda")

para, arranque, sonda = base.EXTREMIDADES["papers"]

comprobar(sonda is None, "papers no tiene sonda que pueda fallar")
comprobar(base.inventario()["papers"]["listo"] is True, "papers siempre listo")


print("\n[7] El texto de arranque de qwen dice la verdad")

_, arranque_qwen, _ = base.EXTREMIDADES["qwen"]

comprobar("Ollama" in arranque_qwen, "qwen apunta a Ollama, que es el runtime real")


print(f"\n{'=' * 52}")
print(f"{comprobaciones} comprobaciones, {len(fallos)} fallos")

if fallos:
    for f in fallos:
        print(f"  - {f}")

    raise SystemExit(1)

print("TODO VERDE")
