"""Prueba EN VIVO de extremidades/imagen.py contra el ComfyUI local.

No es una prueba unitaria: habla con el ComfyUI de verdad (DirectML sobre la
Radeon 890M) y mide cuanto tarda una imagen. Se lanza a mano, con lanzar(),
porque la primera generacion carga un checkpoint de 6,9 GB desde disco y se
come de largo los 50 s que aguanta comando().

    .venv\\Scripts\\python.exe -m prueba_imagen_viva
"""

from __future__ import annotations

import time

from extremidades import imagen


def main() -> int:
    print("FASE 1: ComfyUI responde?", flush=True)

    if imagen.disponible():
        print("OK: ComfyUI ya estaba en marcha", flush=True)

    else:
        print(
            "AVISO: ComfyUI apagado. Que lo levante generar(), que para eso sabe.",
            flush=True,
        )

    print("FASE 2: primera imagen (incluye cargar el checkpoint)", flush=True)

    arranque = time.time()

    try:
        destino = imagen.generar(
            "a red ceramic coffee cup on a wooden table, morning light",
            semilla=12345,
            espera_max=150,
        )

    except Exception as error:  # noqa: BLE001 - queremos verlo entero en el log
        print(f"FALLO en la primera imagen: {type(error).__name__}: {error}", flush=True)
        print("FIN_PRUEBA_IMAGEN", flush=True)
        return 1

    primera = time.time() - arranque

    print(f"OK: {destino.name} ({destino.stat().st_size} bytes) en {primera:.0f}s", flush=True)

    print("FASE 3: segunda imagen (con el modelo ya en memoria)", flush=True)

    arranque = time.time()

    try:
        segundo = imagen.generar(
            "a small blue bicycle leaning on a white wall",
            semilla=999,
            espera_max=150,
        )

    except Exception as error:  # noqa: BLE001
        print(f"FALLO en la segunda imagen: {type(error).__name__}: {error}", flush=True)
        print("FIN_PRUEBA_IMAGEN", flush=True)
        return 1

    segunda = time.time() - arranque

    print(f"OK: {segundo.name} ({segundo.stat().st_size} bytes) en {segunda:.0f}s", flush=True)

    print(
        f"RESUMEN: primera {primera:.0f}s (con carga de modelo), "
        f"siguientes {segunda:.0f}s por imagen",
        flush=True,
    )

    print("FIN_PRUEBA_IMAGEN", flush=True)

    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(main())
