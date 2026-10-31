# -*- coding: utf-8 -*-
"""B6: vuelve a revisar borradores ya hechos con el revisor calibrado (sin rehacer el trabajo)."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from nucleo import tareas as T, trabajo  # noqa: E402

for nombre in sys.argv[1:]:
    f = RAIZ / "memoria" / "borradores" / nombre
    texto = f.read_text(encoding="utf-8")
    cuerpo = texto.split("\n---\n## Revision")[0]
    tid = nombre.split("_")[0]
    rev, ver, salida = trabajo._revisar(T.buscar(tid), cuerpo, "chatgpt")
    print(f"{tid}: revisor={rev} veredicto={ver} graves={trabajo._graves(salida or '')}")
    print("   ", (salida or "")[-700:].replace("\n", "\n    "))
    f.write_text(texto + f"\n\n---\n## Segunda revision, revisor calibrado ({rev}) -> {ver}\n{salida}\n", encoding="utf-8")
