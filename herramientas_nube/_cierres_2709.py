"""27/09/2026: cierres decididos por Claude tras la sesion de correcciones de Code."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import tareas as T  # noqa: E402

T.actualizar("T142", estado="hecha")
T.anotar("T142", "27/09: cerrada. Primera pasada hecha (piezas T143-T160); la segunda pasada vive en T199 (OpenClaw) y T200 (Hermes).")
T.actualizar("T051", estado="hecha")
T.anotar("T051", "27/09: cerrada. Superada por la tabla de roles y el banco del 24/09.")
T.actualizar("T134", estado="aparcada", depende="damian")
T.anotar("T134", "27/09: aparcada. Solo quedan los modelos grandes, que necesitan a Damian delante (junto con T182 gpt-oss:20b).")
t = T.anadir(
    "BUG pequeno: prueba_parada.py activa y desactiva la PARADA real mientras corre",
    detalle="Visto por Code 27/09. Con los turnos activos puede cortar un turno real. Debe usar una bandera temporal (monkeypatch de nucleo.parada.BANDERA), como el resto de suites.",
    importancia=3, urgencia=3, dificultad=1, coste=1, depende="ia",
    etiquetas=["cat:codigo", "prov:claude", "bug", "correccion_errores"])
print("ok", t["id"])
