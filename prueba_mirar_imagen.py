"""Comprueba que las imagenes generadas tienen contenido de verdad.

Que un PNG pese 380 KB ya descarta el cuadro negro, pero no dice si hay
algo dibujado. Esto mira los pixeles: cuanta variedad hay, si es plano, y
que colores dominan (las dos pruebas pedian "taza de ceramica ROJA" y
"bicicleta AZUL", asi que el color dominante es una pista razonable de que
el modelo entendio el encargo y no solo pinto ruido).
"""

from pathlib import Path

from PIL import Image, ImageStat

for archivo in sorted(Path("salidas").glob("imagen_20260912_*.png"))[-2:]:
    img = Image.open(archivo).convert("RGB")

    est = ImageStat.Stat(img)

    medias = [round(v) for v in est.mean]
    desvios = [round(v) for v in est.stddev]

    colores = img.getcolors(maxcolors=1_000_000) or []

    nombres = ("rojo", "verde", "azul")
    dominante = nombres[medias.index(max(medias))]

    plana = max(desvios) < 5

    print(
        f"{archivo.name}: {img.size[0]}x{img.size[1]} | "
        f"medias RGB {medias} | variacion {desvios} | "
        f"{len(colores)} colores distintos | tira a {dominante} | "
        f"{'PLANA (sospechosa)' if plana else 'con contenido'}",
        flush=True,
    )
