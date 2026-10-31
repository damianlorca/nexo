"""Inventario de extremidades: que hay y que responde ahora mismo.

El cerebro pregunta aqui antes de encargar nada, para no pedirle algo
a una extremidad que esta apagada.

Regla de esta pieza (hallazgo L1, 11/09/2026): una extremidad rota se
declara rota, NO tumba el inventario. Antes, una sola sonda que lanzase
algo inesperado dejaba al cerebro sin poder consultar ni las sanas, que
es justo el caso para el que existe este archivo.
"""

from __future__ import annotations

# Para que siga valiendo "python extremidades\base.py" a pelo, y no solo
# "python -m extremidades.base". Este archivo se mira a mano cuando algo
# no responde, y a esa hora nadie se acuerda del -m.
if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Callable

from nucleo.registro import logger

log = logger("extremidades.base")


def _sonda_qwen() -> bool:
    from extremidades import qwen

    return qwen.disponible()


def _sonda_imagen() -> bool:
    from extremidades import imagen

    return imagen.disponible()


def _sonda_voz() -> bool:
    from extremidades import voz

    return voz.disponible()


def _sonda_video() -> bool:
    from extremidades import video

    return video.disponible()


def _sonda_navegador() -> bool:
    from extremidades import navegador

    return navegador.activo()


# nombre -> (para que sirve, como se enciende, como se comprueba)
# La sonda importa su modulo por dentro a proposito: asi un modulo que
# ni siquiera se deja importar (falta una libreria, un error de sintaxis)
# sale como "rota" en vez de reventar el inventario entero.
EXTREMIDADES: dict[str, tuple[str, str, Callable[[], bool] | None]] = {
    "qwen": (
        "volumen: resumir, clasificar, limpiar",
        "Arranca Ollama (qwen2.5:7b obrero y criterio). "
        "LM Studio es la reserva.",
        _sonda_qwen,
    ),
    "papers": (
        "investigacion academica, TFG",
        "No necesita nada: son APIs publicas",
        None,
    ),
    "imagen": (
        "imagenes rapidas, bocetos",
        "Arranca ComfyUI",
        _sonda_imagen,
    ),
    "voz": (
        "narracion para videos",
        "Descarga Piper y una voz en espanol",
        _sonda_voz,
    ),
    "video": (
        "montaje de video",
        "winget install Gyan.FFmpeg",
        _sonda_video,
    ),
    "navegador": (
        "Gemini y ChatGPT para lo que Claude no hace",
        "navegador.arrancar()",
        _sonda_navegador,
    ),
}


def inventario() -> dict[str, dict]:
    """Estado de cada extremidad. Nunca lanza: una rota se marca y ya.

    Cada entrada trae siempre 'para', 'listo' y 'arranque'. Si la sonda
    ha fallado, trae ademas 'error' con el motivo, que es informacion
    util y no ruido: distingue "apagada" de "rota".

    OJO al coste: sondear cuesta unos 5-8 s cuando las cosas estan
    apagadas, porque imagen espera 5 s y navegador 3 s a que alguien
    conteste. No llamar a esto dentro de un bucle.
    """

    estado: dict[str, dict] = {}

    for nombre, (para, arranque, sonda) in EXTREMIDADES.items():
        entrada: dict = {"para": para, "arranque": arranque}

        if sonda is None:
            entrada["listo"] = True
        else:
            try:
                entrada["listo"] = bool(sonda())
            except Exception as e:
                entrada["listo"] = False
                entrada["error"] = f"{type(e).__name__}: {e}"

                log.warning("la sonda de %s ha fallado: %s", nombre, e)

        estado[nombre] = entrada

    return estado


def resumen() -> str:
    lineas = []

    for nombre, datos in inventario().items():
        marca = "OK  " if datos["listo"] else "-   "

        lineas.append(f"{marca}{nombre:12} {datos['para']}")

        if datos.get("error"):
            lineas.append(f"{'':16}ROTA: {datos['error']}")
        elif not datos["listo"]:
            lineas.append(f"{'':16}como: {datos['arranque']}")

    return "\n".join(lineas)


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    print(resumen())
