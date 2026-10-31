"""03/10/2026: anota en T665 la evaluacion del estudio de hardware."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import tareas as T  # noqa: E402

T.anotar("T665", ("03/10: estudio de Damian (xlsx, 6 builds <=800 EUR, 2 TB minimo) evaluado en "
                  "documentacion/hardware/EVALUACION_ESTUDIO_0310.md. Recomendado N800-01 (AM4 + RTX 3060 12GB usada, 747 EUR). "
                  "Alerta: la placa B550M K enlaza a un dominio sospechoso, no comprar ahi. Faltan licencia Windows, BIOS "
                  "restore-on-power-loss/WoL, SAI y medir consumo. Pendiente: 4 decisiones de Damian (build, Windows, SAI, portatil)."))
print("T665 anotada")
