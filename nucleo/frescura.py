"""¿Este proceso esta corriendo con el codigo que hay en disco?

Por que existe
--------------
Dos veces (14/09 y 22/09) el bot de Telegram siguio vivo con codigo viejo
despues de cambios en router.py/bot.py: Damian veia respuestas de antes
del cambio y parecia un bug, pero era solo un proceso sin reiniciar
(T099, incidencias-y-mejoras.md ronda 23-24). canal/vigilante.py solo
relanza el bot si MUERE, no si su codigo cambia.

Este modulo apunta la hora a la que se importo (= arranque del proceso,
porque se importa al principio) y sabe decir que archivos .py del
proyecto se han modificado DESPUES. Quien lo use (el bot, /estado, un
turno) decide que hacer con eso: avisar, reiniciarse... Este modulo solo
mira; no reinicia nada.

Uso:
    from nucleo import frescura      # lo antes posible al arrancar
    ...
    cambiados = frescura.desfasados()
    if cambiados:
        avisar("Corro con codigo viejo: " + ", ".join(cambiados))
"""

from __future__ import annotations

import time
from pathlib import Path

from nucleo.config import RAIZ

ARRANQUE = time.time()

# Carpetas cuyo codigo carga un proceso de larga vida (bot, vigilante).
CARPETAS = ("", "nucleo", "canal", "extremidades", "roles", "manos")

# Margen para no avisar por el propio guardado que ocurre al arrancar.
MARGEN_S = 2.0


def desfasados(desde: float | None = None, raiz: Path | None = None) -> list[str]:
    """Rutas relativas de los .py modificados despues de `desde`
    (por defecto, el arranque de este proceso), ordenadas."""

    desde = ARRANQUE if desde is None else desde
    raiz = raiz or RAIZ
    fuera: list[str] = []

    for carpeta in CARPETAS:
        base = raiz / carpeta if carpeta else raiz

        if not base.is_dir():
            continue

        for p in base.glob("*.py"):
            # Los scripts sueltos de prueba/temporales no los carga un proceso vivo.
            if not carpeta and (p.name.startswith(("_tmp", "prueba_", "banco_", "_")) or p.name.startswith("verificar_")):
                continue

            try:
                if p.stat().st_mtime > desde + MARGEN_S:
                    fuera.append(str(p.relative_to(raiz)).replace("\\", "/"))
            except OSError:
                continue

    return sorted(fuera)
