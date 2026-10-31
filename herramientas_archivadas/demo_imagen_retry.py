"""Reintento del paso de la imagen de la demo (12/09/2026).

Gemini a veces sigue "Creando tu imagen" unos segundos mas de lo que
tarda en dejar de crecer el texto de la pagina (preguntar() se fio del
texto, pero la imagen en si no es texto). Aqui solo se reintenta la
descarga con varios intentos espaciados, sin volver a pedirle nada a
Gemini ni a ChatGPT (ya contestaron bien en la pasada anterior).
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import logging  # noqa: E402
logging.disable(logging.INFO)

from extremidades import navegador  # noqa: E402


SALIDA = RAIZ / "registros" / "demo_imagen_retry.txt"
CARPETA_IMAGEN = RAIZ / "registros" / "demo_imagen"
CARPETA_IMAGEN.mkdir(parents=True, exist_ok=True)

lineas: list[str] = []


def anotar(texto: str = "") -> None:
    print(texto, flush=True)
    lineas.append(str(texto))
    SALIDA.write_text("\n".join(lineas), encoding="utf-8")


def mandar_telegram(texto: str = "", ruta_foto: Path | None = None) -> None:
    outbox = RAIZ / "canal" / "salida"
    outbox.mkdir(parents=True, exist_ok=True)

    marca = time.strftime("%H%M%S")

    if ruta_foto is not None:
        datos = {"tipo": "foto", "ruta": str(ruta_foto), "texto": texto}
        nombre = f"demo_foto_retry_{marca}.json"
    else:
        datos = {"tipo": "aviso", "texto": texto}
        nombre = f"demo_msg_retry_{marca}.json"

    (outbox / nombre).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


anotar(f"REINTENTO IMAGEN  {time.strftime('%Y-%m-%d %H:%M:%S')}")

ruta_img = None

for intento in range(1, 5):
    anotar(f"\nIntento {intento}/4")

    try:
        ruta_img = navegador.descargar_ultima_imagen(destino_carpeta=CARPETA_IMAGEN)
        anotar(f"  OK: {ruta_img}")
        break
    except Exception as e:
        anotar(f"  todavia no: {e}")
        time.sleep(10)

if ruta_img:
    mandar_telegram("🖼️ Imagen generada por Gemini para la demo:", ruta_foto=ruta_img)
    anotar("\nEnviada por Telegram.")
else:
    anotar("\nNo se ha podido descargar tras 4 intentos.")

anotar("FIN")
