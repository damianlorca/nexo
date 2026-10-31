"""27/09/2026 Damian: la interfaz es el puente entre el y NEXO; tiene que estar hecha para que EL la entienda y la maneje."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from nucleo import tareas as T  # noqa: E402

t = T.anadir(
    "Interfaz pensada para Damian: filtrar y ordenar todo, y textos que entienda una persona",
    detalle=(
        "Damian 27/09: la interfaz es el puente entre el y NEXO y hoy muchas cosas estan escritas para que las entienda una IA "
        "(ids, etiquetas cat:/prov:/tema:, jerga interna, notas tecnicas). Esta bien que exista esa capa para las IAs, pero "
        "Damian tiene que poder navegar y entenderlo todo comodamente.\n"
        "1) FILTRAR y ORDENAR en Tareas, Ordenes, Borradores, Cola de revision y Auditoria: por texto, estado, categoria, "
        "proveedor, importancia/urgencia, fecha de creacion y de actualizacion, origen (web/NEXO/Claude). Filtros guardados en la URL "
        "para poder volver. Funciona igual en el movil.\n"
        "2) REVISION DE LENGUAJE de todas las pantallas: cada tarea muestra un titulo y un resumen en espanol claro de 1-2 frases "
        "(que es, por que importa, que falta, que tiene que hacer Damian si algo); estados en palabras normales; etiquetas "
        "traducidas a nombres legibles; fechas relativas ('hace 2 dias'); nada de ids sueltos sin su titulo.\n"
        "3) CAPA PARA IAs aparte: el detalle tecnico, notas y etiquetas crudas siguen disponibles en un desplegable 'Detalle tecnico', "
        "no en la vista principal.\n"
        "4) Donde falte el resumen humano de una tarea, generarlo con Qwen local y guardarlo en un campo propio (no pisar el detalle).\n"
        "5) Revision de accesibilidad y manejo: tamanos tactiles, contraste, navegacion con teclado, lo importante arriba.\n"
        "Criterio de terminado: Damian encuentra cualquier tarea u orden en pocos segundos y entiende cada pantalla sin preguntar. "
        "Proponer primero un boceto de 2-3 pantallas y que Damian lo apruebe antes de implementarlo entero."),
    importancia=5, urgencia=4, dificultad=3, coste=2, depende="ia",
    etiquetas=["cat:codigo", "prov:claude", "tema:interfaz_app_voz", "origen:damian_chat"])

T.anotar("T224", "27/09: al implementar SUPERADO, reclasificar T134, T142 y T051 como SUPERADAS (su trabajo se hizo por otra via), "
                 "no como descartadas.")

p = RAIZ / "memoria" / "INTEGRACION_NUBE.md"
c = p.read_text(encoding="utf-8")
ini = c.index("## Encargos siguientes para Code")
fin = c.index("Plantilla:", ini)
nuevo = (
    "## Encargos siguientes para Code (UNO por sesion; actualizado el 27/09 noche)\n"
    "HECHOS: T188+T193, T183+T189, T192 (turnos ACTIVADOS), revision de los 12 borradores.\n"
    "1. **Correcciones pequenas en una sesion**: T225 (WinError 5), T229 (anuncios de ChatGPT), T224 (veredicto SUPERADO + "
    "reclasificar T134/T142/T051), T198 (defectos de CLIs), T196 (vigia).\n"
    f"2. **{t['id']}**: interfaz pensada para Damian (filtrar/ordenar + textos humanos). Primero boceto y aprobacion de Damian.\n"
    "3. **T186**: triaje de ordenes a prueba de fallos (boton de turnos en la web).\n"
    "4. **T195**: activar/desactivar y ordenar proveedores en la app.\n"
    "5. **T194**: rotacion de proveedores y evaluacion cruzada.\n"
    "6. **T077** bandeja web / **T182** gpt-oss:20b (con Damian delante) / T227 NVIDIA (clave de Damian) / T226-T228 (blindados, parche).\n"
)
p.write_text(c[:ini] + nuevo + c[fin:], encoding="utf-8")
print(t["id"])
