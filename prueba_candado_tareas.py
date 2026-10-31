"""Prueba de concurrencia del candado en nucleo.tareas.

Lanza muchos hilos anadiendo tareas a la vez contra un almacen
temporal. Sin candado, esto pierde actualizaciones: dos hilos leen el
mismo siguiente_id antes de que ninguno escriba, y uno de los dos
IDs (o una de las tareas) desaparece en silencio. Con el candado,
tienen que quedar TODAS y con IDs unicos.

No toca memoria/tareas.json real: usa un almacen temporal.
"""

from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo import tareas  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="prueba_candado_"))
tareas.ALMACEN = TMP / "tareas.json"
tareas.VISTA = TMP / "tareas.md"
tareas.CANDADO = TMP / ".candado.lock"

HILOS = 8
POR_HILO = 15
TOTAL_ESPERADO = HILOS * POR_HILO


def trabajo(n_hilo: int) -> None:
    for i in range(POR_HILO):
        tareas.anadir(f"tarea de prueba hilo={n_hilo} i={i}")


hilos = [threading.Thread(target=trabajo, args=(h,)) for h in range(HILOS)]

for h in hilos:
    h.start()

for h in hilos:
    h.join()

datos = tareas.cargar()
todas = datos["tareas"]
ids = [t["id"] for t in todas]

print(f"esperadas: {TOTAL_ESPERADO}")
print(f"guardadas: {len(todas)}")
print(f"ids unicos: {len(set(ids))} de {len(ids)}")
print(f"siguiente_id final: {datos['siguiente_id']}")

fallo = (
    len(todas) != TOTAL_ESPERADO
    or len(set(ids)) != len(ids)
    or datos["siguiente_id"] != TOTAL_ESPERADO + 1
)

if fallo:
    print("MAL: se perdieron tareas o se repitieron IDs. El candado no protegio bien.")
    raise SystemExit(1)

print("OK: todas las tareas quedaron, con IDs unicos. El candado protege bien.")
