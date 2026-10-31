"""Buzon entre el agente y el movil.

El bot es un proceso aparte que vive en el PC. El agente no habla
con el directamente: deja archivos en canal/salida/ y recoge las
respuestas de canal/entrada/. Asi el agente puede escribirte aunque
no sea el quien mantiene la conexion, y las preguntas sobreviven a
que se caiga cualquiera de los dos.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico


SALIDA = RAIZ / "canal" / "salida"
ENTRADA = RAIZ / "canal" / "entrada"


def _nuevo_id() -> str:
    return f"{time.strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}"


def _poner(mensaje: dict) -> str:
    SALIDA.mkdir(parents=True, exist_ok=True)

    mensaje.setdefault("id", _nuevo_id())
    mensaje.setdefault("creado", time.strftime("%Y-%m-%d %H:%M:%S"))

    destino = SALIDA / f"{mensaje['id']}.json"

    # Atomico a proposito: el bot vigila esta carpeta y si pilla un
    # archivo a medias lo marca .json.roto y el mensaje no llega
    # nunca. Ver hallazgo E1 de memoria/auditoria.md.
    escribir_atomico(
        destino,
        json.dumps(mensaje, ensure_ascii=False, indent=2),
    )

    return mensaje["id"]


def avisar(texto: str, urgente: bool = False, silencioso: bool = False) -> str:
    """Manda un aviso al movil. No espera respuesta.

    silencioso=True lo manda SIN sonido ni vibracion
    (disable_notification de Telegram). El mensaje llega igual y se
    queda esperando en el chat.

    Es lo que debe usar el turno de noche: Damian pidio que no se le
    escriba de madrugada salvo urgencia, pero el resumen de la noche
    tiene que estar ahi cuando se despierte. Con esto se cumplen las
    dos cosas.
    """

    return _poner({
        "tipo": "aviso",
        "texto": texto,
        "urgente": urgente,
        "silencioso": silencioso,
    })


def preguntar(
    texto: str,
    opciones: list[str] | None = None,
    silencioso: bool = False,
) -> str:
    """Pregunta con botones. Devuelve el id con el que recoger la respuesta.

    Sin opciones, se contesta escribiendo. Con opciones, salen
    botones y basta con tocar uno.
    """

    return _poner({
        "tipo": "pregunta",
        "texto": texto,
        "opciones": opciones or ["Si", "No"],
        "silencioso": silencioso,
    })


def enviar_foto(ruta: str | Path, pie: str = "") -> str:
    """Manda una imagen: una captura, un grafico, lo que sea."""

    return _poner({"tipo": "foto", "ruta": str(Path(ruta).resolve()), "texto": pie})


def enviar_archivo(ruta: str | Path, pie: str = "") -> str:
    """Manda un archivo cualquiera."""

    return _poner({"tipo": "archivo", "ruta": str(Path(ruta).resolve()), "texto": pie})


def respuesta(id_pregunta: str) -> str | None:
    """Devuelve la respuesta a una pregunta, o None si aun no ha contestado."""

    archivo = ENTRADA / f"{id_pregunta}.json"

    if not archivo.is_file():
        return None

    try:
        return json.loads(archivo.read_text(encoding="utf-8")).get("respuesta")
    except (json.JSONDecodeError, OSError):
        return None


def esperar(id_pregunta: str, segundos: int = 40, cada: float = 2.0) -> str | None:
    """Espera una respuesta un rato corto. None si no llega a tiempo.

    Pensado para llamarse desde el agente sin bloquear mas de lo que
    aguanta el puente. Si no llega, se vuelve a preguntar mas tarde.
    """

    limite = time.time() + segundos

    while time.time() < limite:
        r = respuesta(id_pregunta)

        if r is not None:
            return r

        time.sleep(cada)

    return None


def mensajes_nuevos(marcar: bool = True) -> list[dict]:
    """Lo que Damian ha escrito por su cuenta, sin que se le preguntara."""

    ENTRADA.mkdir(parents=True, exist_ok=True)

    sueltos = sorted(ENTRADA.glob("libre_*.json"))

    salida = []

    for archivo in sueltos:
        try:
            salida.append(json.loads(archivo.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue

        if marcar:
            archivo.rename(archivo.with_suffix(".json.leido"))

    return salida
