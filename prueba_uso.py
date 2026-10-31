"""Prueba de nucleo.uso: registrar_turno() concurrente y resumen().

NO toca memoria/uso_diario.json real: almacen temporal.
"""

from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo import uso  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="prueba_uso_"))
uso.ARCHIVO = TMP / "uso_diario.json"
uso.CANDADO = TMP / ".candado_uso.lock"

fallos = []


def comprobar(nombre: str, cond: bool, detalle: str = "") -> None:
    marca = "OK " if cond else "MAL"
    print(f"[{marca}] {nombre}" + (f"  -- {detalle}" if detalle and not cond else ""))
    if not cond:
        fallos.append(nombre)


# 1. Sin archivo todavia, resumen() no revienta.
comprobar("sin archivo, resumen() no revienta", uso.resumen() == "Sin turnos registrados todavia.")

# 2. Un registro simple.
uso.registrar_turno("claude-opus-5", "nocturno")
datos = uso._cargar()
hoy = uso._hoy()
comprobar("un turno queda anotado", datos["dias"][hoy]["total"] == 1)
comprobar("con el modelo correcto", datos["dias"][hoy]["por_modelo"]["claude-opus-5"] == 1)
comprobar("con el origen correcto", datos["dias"][hoy]["origenes"]["nocturno"] == 1)

# 3. Archivo corrupto: no revienta, empieza de cero (no es memoria critica).
uso.ARCHIVO.write_text("esto no es json valido {{{", encoding="utf-8")
datos = uso._cargar()
comprobar("archivo corrupto no revienta _cargar()", datos == {"version": 1, "dias": {}})

# 4. HILOS registrando turnos a la vez: ninguno se pierde.
HILOS, POR_HILO = 8, 15
TOTAL = HILOS * POR_HILO


def trabajo(n: int) -> None:
    modelo = "claude-opus-5" if n % 2 == 0 else "claude-sonnet-5"
    for _ in range(POR_HILO):
        uso.registrar_turno(modelo, "prueba")


hilos = [threading.Thread(target=trabajo, args=(h,)) for h in range(HILOS)]

for h in hilos:
    h.start()
for h in hilos:
    h.join()

datos = uso._cargar()
total_hoy = datos["dias"][hoy]["total"]
comprobar(
    f"los {TOTAL} turnos concurrentes quedaron todos",
    total_hoy == TOTAL,
    f"quedaron {total_hoy}",
)

suma_modelos = sum(datos["dias"][hoy]["por_modelo"].values())
comprobar(
    "el desglose por modelo suma igual que el total",
    suma_modelos == TOTAL,
    f"suma {suma_modelos}",
)

# 5. resumen() incluye la fecha de hoy y no revienta.
texto = uso.resumen()
comprobar(f"resumen() incluye la fecha {hoy}", hoy in texto)

print()
if fallos:
    print(f"FALLARON {len(fallos)}: {fallos}")
    raise SystemExit(1)

print(f"TODO BIEN. Almacen de prueba en {TMP} (no es memoria/uso_diario.json real).")
