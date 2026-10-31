"""Prueba del arreglo de extremidades/video.py (fallo I1).

En este equipo FFmpeg NO esta instalado (es ambar: winget). Asi que
esta prueba no monta ningun video: sustituye _ffmpeg por un espia y
comprueba QUE ARGUMENTOS se le habrian pasado. Eso es exactamente
donde estaba el fallo, asi que la prueba sirve.

Lo que no queda probado: que FFmpeg acepte esos argumentos. Eso hay
que verlo el dia que se instale.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import extremidades.video as video  # noqa: E402


fallos = 0


def comprobar(titulo: str, condicion: bool, detalle: str = "") -> None:
    global fallos

    if condicion:
        print(f"  VALE  {titulo}")
    else:
        fallos += 1
        print(f"  FALLA {titulo} {detalle}")


espiados: list[list[str]] = []


def _espia(argumentos, timeout=900):
    espiados.append(list(argumentos))


video._ffmpeg = _espia


def filtro_de(argumentos: list[str]) -> str:
    return argumentos[argumentos.index("-vf") + 1]


print("\n1. lienzo() lee la configuracion de verdad")

ancho, alto = video.lienzo()

print(f"  config.toml da: {ancho}x{alto}")

comprobar("es vertical", alto > ancho, f"{ancho}x{alto}")
comprobar("es 1080x1920", (ancho, alto) == (1080, 1920), f"{ancho}x{alto}")


print("\n2. imagen_con_voz() monta YA en vertical (era el fallo I1)")

espiados.clear()

video.imagen_con_voz("foto.png", "voz.wav", "salida.mp4")

comprobar("ha llamado a ffmpeg una vez", len(espiados) == 1)

args = espiados[0]
f = filtro_de(args)

print(f"  filtro: {f}")

comprobar("escala a 1080:1920", "scale=1080:1920" in f, f)
comprobar("rellena a 1080:1920", "pad=1080:1920" in f, f)
comprobar("YA NO monta en 1920:1080", "1920:1080" not in f, f)
comprobar("no recorta nada", "crop" not in f, f)
comprobar("fija la relacion de pixel", "setsar=1" in f, f)


print("\n3. Los demas argumentos siguen siendo los correctos")

comprobar("imagen en bucle", "-loop" in args)
comprobar("coge la imagen", "foto.png" in args)
comprobar("coge el audio", "voz.wav" in args)
comprobar("codec de video", "libx264" in args)
comprobar("codec de audio", "aac" in args)
comprobar("corta con el mas corto", "-shortest" in args)
comprobar("destino correcto", args[-1] == "salida.mp4", args[-1])


print("\n4. Si la config dijera horizontal, montaria horizontal")

original = video.valor

video.valor = lambda ruta, defecto=None: (
    False if ruta == "video.vertical" else original(ruta, defecto)
)

try:
    comprobar("lienzo() da 1920x1080", video.lienzo() == (1920, 1080), str(video.lienzo()))

    espiados.clear()
    video.imagen_con_voz("foto.png", "voz.wav", "h.mp4")

    fh = filtro_de(espiados[0])

    comprobar("monta en 1920:1080", "scale=1920:1080" in fh, fh)

finally:
    video.valor = original


print("\n5. secuencia() encadena en vertical y no recorta")

espiados.clear()

destino = video.secuencia(
    [("a.png", "a.wav"), ("b.png", "b.wav"), ("c.png", "c.wav")],
    "sec.mp4",
)

# 3 trozos + 1 concat
comprobar("monta 3 trozos y los une", len(espiados) == 4, str(len(espiados)))

for i in range(3):
    fi = filtro_de(espiados[i])

    comprobar(f"    trozo {i} en vertical", "scale=1080:1920" in fi, fi)

union = espiados[3]

comprobar("la union usa concat", "concat" in union)
comprobar("la union copia sin recodificar", "copy" in union)


print("\n6. vertical() sigue ahi para material ajeno en horizontal")

espiados.clear()

video.vertical("ajeno.mp4", "v.mp4")

fv = filtro_de(espiados[0])

comprobar("sigue recortando a 9:16", "crop=1080:1920" in fv, fv)
comprobar(
    "y el docstring avisa de que ya casi nunca hace falta",
    "casi nunca hace falta" in (video.vertical.__doc__ or ""),
)


print("\n7. Limpieza de lo que ha dejado la prueba")

sobra = list((RAIZ / "salidas").glob("_trozos_*"))

print(f"  carpetas de trozos en salidas/: {len(sobra)}")

for s in sobra:
    print(f"    {s.name}  (queda ahi: el agente no borra)")


print("\n" + ("TODO VALE" if fallos == 0 else f"{fallos} FALLOS"))

sys.exit(1 if fallos else 0)
