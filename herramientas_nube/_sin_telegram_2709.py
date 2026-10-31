"""27/09/2026 Damian: no quiere usar Telegram; no se desarrolla ni se prueba nada nuevo por Telegram."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from nucleo import tareas as T  # noqa: E402

NOTA = "27/09 Damian: SIN Telegram. Todo lo de Telegram de esta tarea queda FUERA; solo la web/app."
for tid in ("T186", "T195", "T077", "T154", "T160"):
    T.anotar(tid, NOTA)

c = RAIZ / "CLAUDE.md"
t = c.read_bytes().decode("utf-8")
nl = "\r\n" if "\r\n" in t else "\n"
linea = ("- **Telegram: NADA nuevo.** Damian no quiere usarlo (27/09). No se desarrollan comandos ni pruebas por Telegram; "
         "ordenes, avisos y pruebas van por la web/app. El bot sigue como esta hasta que Damian decida retirarlo.")
if "Telegram: NADA nuevo" not in t:
    marca = "## Cómo hablar con Damián"
    t = t.replace(marca, linea + nl + nl + marca, 1)
    c.write_bytes(t.encode("utf-8"))
print("ok")
