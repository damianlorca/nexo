"""T190 (27/09/2026): que todo lo que NEXO investiga o revisa acabe en revision de Claude
y, si vale la pena, en tarea de implementacion. Peticion explicita de Damian."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import tareas as T  # noqa: E402

t = T.anadir(
    "Circuito cerrado: todo borrador de NEXO -> revision de Claude -> tarea de implementacion si vale la pena",
    detalle=(
        "Damian 27/09: NEXO ya trabaja solo; hay que asegurar que lo que investiga/revisa acaba revisado por Claude y, "
        "si conviene, implementado. Estado real 27/09: trabajo.py NUNCA cierra (bien) y etiqueta borrador:revisar_claude, "
        "pero NADA hace que Claude lo revise: 13 borradores esperando, algunos desde el 23/09. No existe el paso "
        "'propuesta implementable -> tarea'.\n"
        "Construir:\n"
        "1) Plantilla de investigacion: todo borrador termina con la seccion PROPUESTAS IMPLEMENTABLES "
        "(que, donde en NEXO, valor 1-5, esfuerzo 1-5, riesgo) o 'ninguna' justificada.\n"
        "2) Al guardar el borrador, NEXO (Qwen local) crea por cada propuesta una tarea en estado 'propuesta' "
        "(prov:claude, enlazada a la tarea origen y al borrador). No se implementa nada sin revision de Claude.\n"
        "3) Cola de revision visible: pantalla/tarjeta en la web con los borradores y propuestas pendientes, antiguedad y "
        "push cuando haya >=5 o alguno supere 7 dias.\n"
        "4) Sesion de revision por lotes (barata): Claude revisa N borradores de golpe; por cada uno: APROBADO -> propuestas "
        "a 'pendiente' con prioridad; DESCARTADO -> cerrar con motivo; REHACER -> vuelve a NEXO con instrucciones. "
        "La tarea origen solo se cierra tras ese veredicto (registro de evidencia T160).\n"
        "5) Test: un borrador simulado con 2 propuestas genera 2 tareas 'propuesta' enlazadas y aparece en la cola.\n"
        "Primera tanda manual: revisar los 13 borradores pendientes en una sesion de revision."),
    importancia=5, urgencia=4, dificultad=3, coste=2, depende="ia",
    etiquetas=["cat:codigo", "prov:claude", "tema:orquestacion", "circuito_revision"])
T.anotar("T173", f"27/09: la parte 'que Claude reciba y revise lo que hace NEXO' se construye en {t['id']}.")
print(t["id"])
