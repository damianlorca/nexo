"""Diagnostico minimo de torch-directml, sin ComfyUI de por medio.

ComfyUI falla con UnicodeDecodeError ('utf-8' codec can't decode byte 0xe1)
al mover el modelo a la GPU. Ese error NO es el error de verdad: es torch
intentando leer en UTF-8 un mensaje de error del driver que Windows en
espanol devuelve en cp1252 (0xe1 es la 'a' con tilde de "direccion",
"memoria"...). El error real queda escondido debajo.

Esta prueba va de menos a mas para averiguar que aguanta de verdad la
Radeon 890M via DirectML, y captura el fallo en bytes crudos cuando la
decodificacion revienta.

    C:\\Users\\damia\\Desktop\\AI\\ComfyUI\\venv\\Scripts\\python.exe prueba_directml.py
"""

from __future__ import annotations

import traceback


def intentar(nombre, funcion):
    try:
        resultado = funcion()
        print(f"OK   {nombre}: {resultado}", flush=True)
        return True

    except UnicodeDecodeError as error:
        crudo = error.object if isinstance(error.object, bytes) else b""
        print(
            f"FALLO {nombre}: el driver contesto algo que torch no sabe leer. "
            f"Mensaje crudo -> {crudo.decode('cp1252', errors='replace')!r}",
            flush=True,
        )
        return False

    except Exception as error:  # noqa: BLE001
        print(f"FALLO {nombre}: {type(error).__name__}: {error}", flush=True)
        traceback.print_exc()
        return False


def main() -> int:
    import torch
    import torch_directml

    print(f"torch {torch.__version__}", flush=True)

    dispositivos = torch_directml.device_count()
    print(f"dispositivos DirectML: {dispositivos}", flush=True)

    for i in range(dispositivos):
        print(f"  [{i}] {torch_directml.device_name(i)}", flush=True)

    d = torch_directml.device()

    intentar("tensor pequeno a la GPU", lambda: torch.randn(64, 64).to(d).sum().item())

    intentar(
        "multiplicacion 1024x1024",
        lambda: (torch.randn(1024, 1024).to(d) @ torch.randn(1024, 1024).to(d)).cpu().shape,
    )

    intentar(
        "float16 (lo que usa SDXL)",
        lambda: (torch.randn(512, 512, dtype=torch.float16).to(d) * 2).cpu().sum().item(),
    )

    # Cuanta memoria admite de verdad: bloques de 256 MB hasta que reviente.
    print("Cuanta memoria traga (bloques de 256 MB):", flush=True)

    guardados = []
    total = 0

    for i in range(1, 33):
        try:
            # 256 MB en float32 = 64M elementos
            guardados.append(torch.empty(64 * 1024 * 1024, dtype=torch.float32, device=d))
            total += 256
            print(f"  {total} MB ok", flush=True)

        except Exception as error:  # noqa: BLE001
            nombre = type(error).__name__
            print(f"  se planta en {total + 256} MB ({nombre})", flush=True)
            break

    print(f"VEREDICTO: memoria util aproximada {total} MB", flush=True)
    print("FIN_DIRECTML", flush=True)

    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(main())
