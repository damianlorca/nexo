"""Comprobacion en frio de canal/bot.py despues de los parches.

No arranca ningun bot ni toca Telegram. Solo mira que el modulo se
importa, que estan las piezas nuevas y que no ha quedado nada del
diseno que se descarto.

    .venv\\Scripts\\python.exe prueba_bot_arranque.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo import registro  # noqa: E402
registro.aislar()  # T198: sus logs (401 simulados...) no van a registros/ reales


def main() -> int:
    fallos = []

    try:
        from canal import bot
    except Exception as e:                      # noqa: BLE001
        print(f"FALLO: canal/bot.py no se importa: {e!r}")
        return 1

    print("OK: canal/bot.py se importa")

    if not hasattr(bot, "CEDER_TRAS"):
        fallos.append("falta CEDER_TRAS")
    else:
        print(f"OK: CEDER_TRAS = {bot.CEDER_TRAS}")

    if hasattr(bot, "otro_bot_hablando"):
        fallos.append("sigue ahi el sondeo descartado otro_bot_hablando")

    if not hasattr(bot, "main"):
        fallos.append("falta main()")

    try:
        from nucleo.instancia import unico
    except Exception as e:                      # noqa: BLE001
        fallos.append(f"nucleo/instancia.py no se importa: {e!r}")
    else:
        print("OK: nucleo/instancia.py se importa")

        if "unico" not in bot.__dict__ and "unico" not in dir(bot):
            fallos.append("bot.py no ha importado unico()")
        else:
            print("OK: bot.py usa el candado")

    fuente = (RAIZ / "canal" / "bot.py").read_text(encoding="utf-8")

    for pieza in ('unico("nexo_bot")', "SystemExit(3)", "SystemExit(4)", "409"):
        if pieza not in fuente:
            fallos.append(f"no aparece {pieza!r} en bot.py")

    if fallos:
        print("\nFALLOS:")

        for f in fallos:
            print(" -", f)

        return 1

    print("\nOK: el bot esta listo para arrancar con candado.")

    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    sys.exit(main())
