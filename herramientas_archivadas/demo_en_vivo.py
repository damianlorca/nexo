"""Demo en vivo para Damian (12/09/2026): Qwen, Gemini (con imagen),
ChatGPT y el canal de Telegram ya arreglado, todo de una vez.

Va en segundo plano (lanzar()) porque Gemini generando y descargando
una imagen puede tardar bien mas de los 45-50s que aguanta una
llamada del puente MCP. Deja el resultado en registros/demo_vivo.txt
y la imagen en registros/demo_imagen/.

Manda los mensajes/foto a Telegram dejandolos en canal/salida/, que
es el mecanismo normal de Nexo: el bot ya en marcha los recoge solo,
no hace falta tocar el bot para nada.
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

import proveedores  # noqa: E402


SALIDA = RAIZ / "registros" / "demo_vivo.txt"
SALIDA.parent.mkdir(parents=True, exist_ok=True)

CARPETA_IMAGEN = RAIZ / "registros" / "demo_imagen"
CARPETA_IMAGEN.mkdir(parents=True, exist_ok=True)

lineas: list[str] = []
_contador = 0


def anotar(texto: str = "") -> None:
    print(texto, flush=True)
    lineas.append(str(texto))
    SALIDA.write_text("\n".join(lineas), encoding="utf-8")


def mandar_telegram(texto: str = "", ruta_foto: Path | None = None) -> None:
    """Deja un mensaje en canal/salida/: el bot que ya esta corriendo lo recoge solo."""

    global _contador

    outbox = RAIZ / "canal" / "salida"
    outbox.mkdir(parents=True, exist_ok=True)

    _contador += 1
    marca = time.strftime("%H%M%S") + f"_{_contador:03d}"

    if ruta_foto is not None:
        datos = {"tipo": "foto", "ruta": str(ruta_foto), "texto": texto}
        nombre = f"demo_foto_{marca}.json"
    else:
        datos = {"tipo": "aviso", "texto": texto}
        nombre = f"demo_msg_{marca}.json"

    (outbox / nombre).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


anotar(f"DEMO EN VIVO  {time.strftime('%Y-%m-%d %H:%M:%S')}")
anotar("=" * 60)

mandar_telegram(
    "🔧 Canal de Telegram restaurado. Empieza la demo: Qwen, Gemini "
    "(con imagen) y ChatGPT en vivo."
)


anotar("\n1. Qwen")

try:
    q = proveedores.QwenProvider()
    r = q.enviar(
        "En una frase: por que es util tener varias IAs especializadas "
        "en vez de una sola?"
    )
    anotar(f"  Qwen -> {r}")
except Exception:
    anotar("EXCEPCION Qwen:")
    anotar(traceback.format_exc())


anotar("\n2. Gemini: pregunta + genera una imagen")

ruta_img = None

try:
    from extremidades import navegador

    if not navegador.activo():
        navegador.arrancar()

    g = proveedores.GeminiProvider()
    r = g.enviar("En una frase: que es un agente de IA autonomo?")
    anotar(f"  Gemini (texto) -> {r}")

    r_img = navegador.preguntar(
        "gemini",
        "Genera una imagen de un faro en un acantilado al amanecer, estilo realista.",
        espera=90,
    )
    anotar(f"  Gemini (pide imagen) -> {r_img}")

    time.sleep(3)

    ruta_img = navegador.descargar_ultima_imagen(destino_carpeta=CARPETA_IMAGEN)
    anotar(f"  Imagen descargada en: {ruta_img}")

    mandar_telegram("🖼️ Imagen generada por Gemini para la demo:", ruta_foto=ruta_img)
except Exception:
    anotar("EXCEPCION Gemini:")
    anotar(traceback.format_exc())


anotar("\n3. ChatGPT")

try:
    c = proveedores.ChatGPTProvider()
    r = c.enviar(
        "En una frase: en que se diferencia razonar de solo recordar datos?"
    )
    anotar(f"  ChatGPT -> {r}")
except Exception:
    anotar("EXCEPCION ChatGPT:")
    anotar(traceback.format_exc())


anotar("\n4. Claude (T039 aun pendiente: solo estado, no se dispara nada)")

try:
    cl = proveedores.ClaudeProvider()
    anotar(f"  estado(): {cl.estado()}")
except Exception:
    anotar("EXCEPCION Claude:")
    anotar(traceback.format_exc())


mandar_telegram("✅ Demo terminada. Resultado completo en registros/demo_vivo.txt.")

anotar("\nFIN")
