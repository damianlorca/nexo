"""Arranca ComfyUI diciendole cuanta memoria de GPU hay DE VERDAD.

El problema, medido el 12/09/2026:

ComfyUI, cuando corre sobre DirectML, no tiene forma de preguntarle a la
GPU cuanta memoria tiene, asi que se inventa 1024 MB y toma todas sus
decisiones con ese numero. La Radeon 890M admite en realidad unos 3 GB
(medido en pruebas/prueba_directml.py). Con el numero falso pasan dos cosas:

  * con --highvram o --novram no sale ni una sola imagen;
  * con --lowvram sale la primera y a partir de la segunda ComfyUI cree
    que le quedan 64 MB libres, carga el modelo a cachos ridiculos y o
    revienta o se queda clavado en el paso 0 de 4.

La solucion NO es editar el codigo de ComfyUI: es de otro y se pierde en
cuanto se actualice. Lo que hace este lanzador es arrancar su main.py
desde dentro de Python, habiendo sustituido antes las dos funciones que
mienten (get_total_memory y get_free_memory) por otras que devuelven la
cifra real. ComfyUI se queda entero como esta y solo cambia lo que ve.

    .venv\\Scripts\\python.exe -m extremidades.arrancar_comfyui

Ojo: hay que ejecutarlo con el Python de ComfyUI, no con el del agente,
porque el torch con DirectML esta en el venv de ComfyUI:

    C:\\Users\\damia\\Desktop\\AI\\ComfyUI\\venv\\Scripts\\python.exe
        C:\\Users\\damia\\Desktop\\AI\\agente\\extremidades\\arrancar_comfyui.py
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


COMFY = Path(os.environ.get("COMFYUI_RAIZ", r"C:\Users\damia\Desktop\AI\ComfyUI"))

# Medido en pruebas/prueba_directml.py: la 890M traga 3072 MB y se planta
# en 3328 MB. Se deja un poco de margen para que ComfyUI no apure hasta el
# borde, porque cuando se pasa no da un error claro, da un UnicodeDecodeError.
MEMORIA_REAL = int(os.environ.get("COMFYUI_VRAM_MB", "2816")) * 1024 * 1024


def main() -> int:
    if not COMFY.is_dir():
        print(f"No encuentro ComfyUI en {COMFY}", flush=True)
        return 1

    sys.path.insert(0, str(COMFY))

    os.chdir(COMFY)

    # Los argumentos van antes de importar nada de comfy: model_management
    # los lee al importarse (ahi decide si usa DirectML).
    if len(sys.argv) <= 1:
        sys.argv = ["main.py", "--directml", "--lowvram"]

    else:
        sys.argv = ["main.py"] + sys.argv[1:]

    import comfy.options

    comfy.options.enable_args_parsing()

    import comfy.model_management as mm

    total_antes = mm.get_total_memory(mm.get_torch_device())

    def total_de_verdad(dev=None, torch_total_too=False):
        if torch_total_too:
            return (MEMORIA_REAL, MEMORIA_REAL)

        return MEMORIA_REAL

    def libre_de_verdad(dev=None, torch_free_too=False):
        # ComfyUI resta por su cuenta lo que ya ha cargado; aqui solo hay
        # que darle un techo honesto en vez del 1 GB inventado.
        if torch_free_too:
            return (MEMORIA_REAL, MEMORIA_REAL)

        return MEMORIA_REAL

    mm.get_total_memory = total_de_verdad
    mm.get_free_memory = libre_de_verdad
    mm.total_vram = MEMORIA_REAL / (1024 * 1024)

    print(
        f"[nexo] memoria de GPU: ComfyUI creia {total_antes / 1024 / 1024:.0f} MB, "
        f"le decimos {MEMORIA_REAL / 1024 / 1024:.0f} MB (medido: 3072 MB reales)",
        flush=True,
    )

    runpy.run_path(str(COMFY / "main.py"), run_name="__main__")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
