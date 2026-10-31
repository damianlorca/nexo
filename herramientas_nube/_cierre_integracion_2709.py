"""Cierre de la integracion N01-N06 (27/09/2026): pendientes de Code decididos por Claude."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import tareas as T  # noqa: E402

T.anotar("T084", "27/09: los hallazgos de N01 que quedaron fuera (H09, H10, H12, H13, H15 -probablemente ya arreglado-, "
                 "H17, H22, H31) se trabajan DENTRO de esta tarea. Detalle en documentacion/nube/N01_2026-09-25.md y "
                 "documentacion/propuestas/N01_arreglos.patch. Baja prioridad frente a T188/T193/T183/T189.")
t = T.anadir(
    "Defectos pequenos de CLIs y suites (hallados por Code el 27/09)",
    detalle=("1) CLI de tareas: 'estado' con un solo argumento se cae. 2) 'anadir --etiquetas' guarda texto en vez de lista. "
             "3) CLI de aprobaciones anota siempre 'damian' como autor aunque la use Claude u otro proceso (trazabilidad: "
             "debe registrar el autor real). 4) Varias suites prueba_* escriben avisos falsos de 'token invalido' en el log "
             "real: deben usar logs temporales. Todo con test. Una sola sesion corta."),
    importancia=3, urgencia=2, dificultad=1, coste=1, depende="ia",
    etiquetas=["cat:codigo", "prov:claude", "bug", "correccion_errores"])
print(t["id"])
