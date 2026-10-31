"""Prueba de /imagen en el bot (T041), sin GPU y sin Telegram.

Se inyecta un generador falso y un buzon falso, asi que esto corre en
cualquier sitio y en menos de un segundo. Lo que se comprueba:

  1. /imagen sin texto explica como se usa y NO arranca nada.
  2. /imagen con texto contesta al momento (sin esperar los ~30 s).
  3. la imagen se genera con el texto pedido y se manda como foto.
  4. si la generacion falla, el fallo se avisa por el chat y el bot no
     se cae: era justo lo que no podia pasar, que una imagen rota se
     llevase por delante el canal entero.

    .venv\\Scripts\\python.exe prueba_imagen_bot.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo import registro  # noqa: E402
registro.aislar()  # T198: sus logs (401 simulados...) no van a registros/ reales

from canal.bot import _cmd_imagen  # noqa: E402


fallos = 0


def vale(condicion: bool, titulo: str) -> None:
    global fallos

    if condicion:
        print(f"  VALE  {titulo}")

    else:
        fallos += 1
        print(f"  FALLA {titulo}")


class BuzonFalso:
    def __init__(self) -> None:
        self.fotos: list[tuple] = []
        self.avisos: list[str] = []

    def enviar_foto(self, ruta, pie=""):
        self.fotos.append((ruta, pie))
        return "foto_falsa"

    def avisar(self, texto, urgente=False, silencioso=False):
        self.avisos.append(texto)
        return "aviso_falso"


def esperar_al_hilo(condicion, segundos: float = 3.0) -> None:
    """Los hilos no son instantaneos; se les da un momento."""

    limite = time.time() + segundos

    while time.time() < limite and not condicion():
        time.sleep(0.02)


print("SIN TEXTO")

buzon = BuzonFalso()

respuesta = _cmd_imagen("", generar=lambda t: Path("no.png"), buzon_=buzon)

vale("/imagen" in respuesta, "explica como se usa")
vale(not buzon.fotos, "no manda ninguna foto")

print("\nCON TEXTO: contesta al momento y trabaja por detras")

buzon = BuzonFalso()

encargos: list[str] = []


def generar_falso(encargo: str) -> Path:
    encargos.append(encargo)
    time.sleep(0.05)
    return Path("salidas/falsa.png")


arranque = time.time()

respuesta = _cmd_imagen(" un faro al amanecer ", generar=generar_falso, buzon_=buzon)

tardanza = time.time() - arranque

vale(tardanza < 0.5, f"contesta sin esperar a la imagen ({tardanza:.2f}s)")
vale("faro al amanecer" in respuesta, "dice lo que ha entendido")

esperar_al_hilo(lambda: bool(buzon.fotos))

vale(encargos == ["un faro al amanecer"], "genera con el texto limpio de espacios")
vale(len(buzon.fotos) == 1, "manda exactamente una foto")
vale(
    buzon.fotos and "faro al amanecer" in buzon.fotos[0][1],
    "la foto lleva de pie lo que se pidio",
)

print("\nSI LA IMAGEN FALLA: se avisa y el bot sigue vivo")

buzon = BuzonFalso()


def generar_roto(encargo: str) -> Path:
    raise RuntimeError("ComfyUI no responde")


respuesta = _cmd_imagen("un gato", generar=generar_roto, buzon_=buzon)

vale(bool(respuesta), "aun asi contesta al momento")

esperar_al_hilo(lambda: bool(buzon.avisos))

vale(len(buzon.avisos) == 1, "avisa del fallo por el chat")
vale(
    buzon.avisos and "ComfyUI no responde" in buzon.avisos[0],
    "el aviso dice que ha pasado de verdad",
)
vale(not buzon.fotos, "no manda una foto que no existe")

print()

if fallos:
    print(f"HAY {fallos} FALLO(S)")
    raise SystemExit(1)

print("TODO VALE")
