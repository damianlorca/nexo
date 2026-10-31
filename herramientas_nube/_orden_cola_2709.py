"""27/09: el OK absoluto pasa delante (Damian quiere asegurarse de que se sigue) y el
interruptor de turnos se anota para web/Telegram."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from nucleo import tareas as T  # noqa: E402

T.anotar("T186", "27/09: anadir a la lista blanca de ACCIONES 'activar/desactivar turnos' (nucleo/turnos.py ya existe, "
                 "CLI: python -m nucleo.turnos on|off|estado). Falta el boton en la web (Centro/Ajustes) y /turnos on|off en Telegram.")
T.anotar("T183", "27/09: Damian quiere garantia de que NEXO sigue el OK absoluto. Pasa por delante en la cola (justo tras T188). "
                 "Los turnos quedan DESACTIVADOS (memoria/TURNOS_DESACTIVADOS) hasta que T188 y T183 esten hechos y testeados.")
T.actualizar("T183", importancia=5, urgencia=5)

p = RAIZ / "memoria" / "INTEGRACION_NUBE.md"
c = p.read_text(encoding="utf-8")
viejo_ini = c.index("## Encargos siguientes para Code")
viejo_fin = c.index("Plantilla:", viejo_ini)
nuevo = (
    "## Encargos siguientes para Code (UNO por sesion, en este orden; actualizado el 27/09)\n"
    "1. **T188**: bug de Pensar/Pro. Fallo cerrado: si no se activa el modo, no se envía.\n"
    "2. **T183 + T189**: OK absoluto aplicado de verdad en el pipeline, más el revisor y auditor de todo lo delegado "
    "(modo, conversación, prompt, revisión obligatoria). Damián quiere garantía de que se sigue.\n"
    "   -> Al terminar 1 y 2 con evidencia, Damián decide si reactiva los turnos (`python -m nucleo.turnos on`).\n"
    "3. **T186**: triaje de órdenes a prueba de fallos, incluidos /turnos on|off y el botón en la web.\n"
    "4. **T192**: circuito cerrado de revisión de borradores (primera tanda: los 13 pendientes).\n"
    "5. **T077**: bandeja de aprobaciones en la web.\n"
)
c = c[:viejo_ini] + nuevo + c[viejo_fin:]
p.write_text(c, encoding="utf-8")
print("ok")
