"""Prueba de humo: que todos los modulos importen y que las piezas
tocadas esta noche encajen. Rapido y sin efectos.
"""

from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo import registro  # noqa: E402
registro.aislar()  # T198: sus logs (401 simulados...) no van a registros/ reales

MODULOS = [
    "nucleo.config",
    "nucleo.permisos",
    "nucleo.registro",
    "nucleo.estado",
    "nucleo.escritura",
    "nucleo.instancia",
    "manos.archivos",
    "manos.shell",
    "canal.buzon",
    "extremidades.base",
    "extremidades.qwen",
    "extremidades.papers",
    "extremidades.navegador",
    "extremidades.imagen",
    "extremidades.video",
    "extremidades.voz",
]

fallos = 0

print("IMPORTS")

for m in MODULOS:
    try:
        importlib.import_module(m)
        print(f"  VALE  {m}")
    except Exception:
        fallos += 1
        print(f"  FALLA {m}")
        traceback.print_exc(limit=2)

print("\nENCAJE DE LAS PIEZAS NUEVAS")

try:
    from manos import archivos
    from canal import buzon
    from nucleo import estado
    from nucleo.escritura import escribir_atomico

    comprobaciones = [
        ("archivos.escribir usa escritura atomica",
         "escribir_atomico" in Path(RAIZ / "manos" / "archivos.py").read_text(encoding="utf-8")),
        ("buzon._poner usa escritura atomica",
         "escribir_atomico" in Path(RAIZ / "canal" / "buzon.py").read_text(encoding="utf-8")),
        ("estado.guardar usa escritura atomica",
         "escribir_atomico" in Path(RAIZ / "nucleo" / "estado.py").read_text(encoding="utf-8")),
        ("Estado tiene el campo siguiente_turno",
         "siguiente_turno" in estado.Estado.__dataclass_fields__),
        ("archivar tiene frenos",
         hasattr(archivos, "_comprobar_archivable")),
        ("respaldos con nombre por ruta",
         hasattr(archivos, "_nombre_de_respaldo")),
    ]

    for titulo, ok in comprobaciones:
        if ok:
            print(f"  VALE  {titulo}")
        else:
            fallos += 1
            print(f"  FALLA {titulo}")

except Exception:
    fallos += 1
    traceback.print_exc(limit=3)

print("\nEL ESTADO REAL SE LEE BIEN")

try:
    from nucleo.estado import cargar

    e = cargar()

    print(f"  estado={e.estado!r} paso={e.paso} hechos={len(e.hechos)} "
          f"siguiente_turno={len(e.siguiente_turno)}")

    if e.estado == "fallo":
        fallos += 1
        print("  FALLA el estado real viene marcado como fallo")
    else:
        print("  VALE  el estado real carga limpio")

except Exception:
    fallos += 1
    traceback.print_exc(limit=3)

print("\n" + ("TODO VALE" if fallos == 0 else f"{fallos} FALLOS"))

sys.exit(1 if fallos else 0)
