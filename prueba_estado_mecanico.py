"""Prueba de nucleo.estado: actualizar_campos() y anadir_hecho() bajo
candado real, con hilos a la vez. NO toca memoria/estado.json real:
usa un almacen temporal (ARCHIVO/CANDADO redirigidos), igual que
prueba_estado.py.
"""

from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo import estado  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="prueba_estado_mecanico_"))
estado.ARCHIVO = TMP / "estado.json"
estado.CANDADO = TMP / ".candado_estado.lock"

fallos = []


def comprobar(nombre: str, cond: bool, detalle: str = "") -> None:
    marca = "OK " if cond else "MAL"
    print(f"[{marca}] {nombre}" + (f"  -- {detalle}" if detalle and not cond else ""))
    if not cond:
        fallos.append(nombre)


# 1. Sin archivo todavia, cargar() da un Estado en blanco, no revienta.
e = estado.cargar()
comprobar("sin archivo da un Estado en blanco", e.estado == "inactivo")

# 2. actualizar_campos() cambia solo lo que se le pasa.
estado.actualizar_campos(estado="trabajando", paso=3)
e = estado.cargar()
comprobar("actualizar_campos() cambia 'estado'", e.estado == "trabajando")
comprobar("actualizar_campos() cambia 'paso'", e.paso == 3)
comprobar("actualizar_campos() no toca 'errores'", e.errores == 0)
comprobar("actualizar_campos() no toca 'hechos'", e.hechos == [])

# 3. actualizar_campos() rechaza campos que no son suyos (hechos, siguiente_turno).
try:
    estado.actualizar_campos(hechos=["intento de colarla"])
    comprobar("actualizar_campos() rechaza 'hechos'", False, "no lanzo ValueError")
except ValueError:
    comprobar("actualizar_campos() rechaza 'hechos'", True)

try:
    estado.actualizar_campos(siguiente_turno=["intento"])
    comprobar("actualizar_campos() rechaza 'siguiente_turno'", False, "no lanzo ValueError")
except ValueError:
    comprobar("actualizar_campos() rechaza 'siguiente_turno'", True)

# 4. El estado sigue siendo 'trabajando'/paso=3 tras el intento fallido (3).
e = estado.cargar()
comprobar(
    "el intento rechazado no cambio nada",
    e.estado == "trabajando" and e.paso == 3,
)

# 5. HILOS anadiendo hechos a la vez: ninguno debe perderse.
HILOS, POR_HILO = 8, 10
TOTAL = HILOS * POR_HILO


def trabajo(n: int) -> None:
    for i in range(POR_HILO):
        estado.anadir_hecho(f"hecho de hilo={n} i={i}")


hilos = [threading.Thread(target=trabajo, args=(h,)) for h in range(HILOS)]

for h in hilos:
    h.start()
for h in hilos:
    h.join()

e = estado.cargar()
comprobar(
    f"los {TOTAL} hechos concurrentes quedaron todos",
    len(e.hechos) == TOTAL,
    f"quedaron {len(e.hechos)}",
)

# 6. actualizar_campos() concurrente con anadir_hecho() no se pisan
#    (mismo candado protege ambos: un guardar() completo por vez).
def mezcla(n: int) -> None:
    for i in range(5):
        estado.actualizar_campos(paso=n * 100 + i)
        estado.anadir_hecho(f"mezcla hilo={n} i={i}")


hilos2 = [threading.Thread(target=mezcla, args=(h,)) for h in range(4)]

for h in hilos2:
    h.start()
for h in hilos2:
    h.join()

e = estado.cargar()
comprobar(
    "tras la mezcla concurrente los hechos anteriores siguen (no se pisaron)",
    len(e.hechos) == TOTAL + 4 * 5,
    f"quedaron {len(e.hechos)}",
)

print()
if fallos:
    print(f"FALLARON {len(fallos)}: {fallos}")
    raise SystemExit(1)

print(f"TODO BIEN. Almacen de prueba en {TMP} (no es memoria/estado.json real).")
