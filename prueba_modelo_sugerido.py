"""Prueba de modelo_sugerido() y de que render_md no revienta con el campo nuevo.

No toca memoria/tareas.json real: usa un almacen temporal.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo import tareas  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="prueba_modelo_"))
tareas.ALMACEN = TMP / "tareas.json"
tareas.VISTA = TMP / "tareas.md"
tareas.CANDADO = TMP / ".candado.lock"

fallos = []


def comprobar(nombre: str, cond: bool, detalle: str = "") -> None:
    marca = "OK " if cond else "MAL"
    print(f"[{marca}] {nombre}" + (f"  -- {detalle}" if detalle and not cond else ""))
    if not cond:
        fallos.append(nombre)


# 1. Facil y poco importante -> el nivel mas barato.
barata = tareas.plantilla("mecanica", dificultad=1, importancia=1)
comprobar(
    "facil+pocoimportante -> sonnet concentracion media",
    tareas.modelo_sugerido(barata) == "sonnet, concentracion media",
    tareas.modelo_sugerido(barata),
)

# 2. Lo normal (3 y 3, los defectos) -> el nivel del medio.
media = tareas.plantilla("normalita")
comprobar(
    "dificultad/importancia por defecto -> sonnet concentracion alta",
    tareas.modelo_sugerido(media) == "sonnet, concentracion alta",
    tareas.modelo_sugerido(media),
)

# 3. Dificil Y importante de verdad -> el nivel caro.
dificil = tareas.plantilla("critica", dificultad=5, importancia=5)
comprobar(
    "dificil+importante -> opus concentracion alta",
    tareas.modelo_sugerido(dificil) == "opus, concentracion alta",
    tareas.modelo_sugerido(dificil),
)

# 4. Importante pero facil NO debe disparar el nivel caro por si sola.
importante_facil = tareas.plantilla("importante pero mecanica", dificultad=1, importancia=5)
comprobar(
    "importante+facil se queda por debajo de opus",
    tareas.modelo_sugerido(importante_facil) != "opus, concentracion alta",
    tareas.modelo_sugerido(importante_facil),
)

# 5. anadir() de verdad y que aparezca en el .md generado sin reventar.
t = tareas.anadir("tarea de prueba para el render", dificultad=4, importancia=4)
md = tareas.VISTA.read_text(encoding="utf-8")
comprobar("el .md incluye 'modelo sugerido'", "modelo sugerido:" in md, md[:200])
comprobar(f"el .md incluye el id {t['id']}", t["id"] in md)

print()
if fallos:
    print(f"FALLARON {len(fallos)}: {fallos}")
    raise SystemExit(1)

print(f"TODO BIEN. Almacen de prueba en {TMP} (no es memoria/tareas.json real).")
