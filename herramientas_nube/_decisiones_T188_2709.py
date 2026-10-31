"""Decisiones tras T188+T193 (27/09/2026), tomadas por Claude por encargo de Damian."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import tareas as T  # noqa: E402

for tid in ("T124", "T167"):
    T.anotar(tid, "27/09: rehacer con NEXO DESPUES de T183+T189 (navegador ya fiable desde T188/T193, falta OK absoluto).")
T.anotar("T189", "27/09: incluir AVISO en la web/app (push) cuando ningun proveedor consiga el modo Pensar/Pro o una delegacion "
                 "falle el checklist. Hoy el fallo cerrado de T188 solo deja ERROR en router/handoff/trazas.")
T.anotar("T198", "27/09: anadir: herramientas_delegacion/* y herramientas_logo/* se conectan al Chrome de NEXO sin el candado de "
                 "T193; deben usarlo o archivarse los que ya no sirven.")
print("ok")
