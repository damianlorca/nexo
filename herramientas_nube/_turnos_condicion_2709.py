"""27/09/2026 Damian: turnos solo si TODO se revisa y cada investigacion genera tareas de revision/implementacion (T192)."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from nucleo import tareas as T  # noqa: E402

T.anotar("T192", "27/09 Damian: CONDICION para reactivar los turnos. Solo si al acabar cada investigacion se crean las tareas "
                 "de revision de Claude y de posible implementacion, y todo pasa por el auditor (T189). Pasa a ser el siguiente encargo.")
T.actualizar("T192", importancia=5, urgencia=5)

p = RAIZ / "memoria" / "INTEGRACION_NUBE.md"
c = p.read_text(encoding="utf-8")
ini = c.index("## Encargos siguientes para Code")
fin = c.index("Plantilla:", ini)
nuevo = (
    "## Encargos siguientes para Code (UNO por sesion; actualizado el 27/09 noche)\n"
    "HECHOS: T188+T193 (navegador fiable) y T183+T189 (OK absoluto + auditor).\n"
    "1. **T192**: circuito cerrado. Cada investigación genera una tarea de revisión de Claude y tareas 'propuesta' de implementación; "
    "primera tanda con los borradores pendientes. **Condición de Damián para reactivar los turnos.**\n"
    "   -> Con T192 hecha y probada: `python -m nucleo.turnos on`.\n"
    "2. **T186**: triaje de órdenes a prueba de fallos (sin Telegram; el botón de turnos en la web).\n"
    "3. **T195**: activar/desactivar proveedores y ordenarlos en la app.\n"
    "4. **T194**: rotación de proveedores y evaluación cruzada.\n"
    "5. **T077** web / **T196** vigía / **T198** defectos pequeños / **T182** gpt-oss:20b (con Damián delante).\n"
)
p.write_text(c[:ini] + nuevo + c[fin:], encoding="utf-8")
print("ok")
