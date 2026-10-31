"""27/09/2026 noche: extension adaptable de los borradores + plan de retorno pedido por Damian."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from nucleo import tareas as T  # noqa: E402

ext = T.anadir(
    "Extension de los borradores adaptable por tarea (hoy fija: 600/700/300 palabras)",
    detalle=("Damian 27/09: el 'maximo 600 palabras' limita cosas que no deberian. Motivo actual: los borradores se reenvian "
             "a revisores/mejoras recortados a 7000 caracteres (trabajo.py) y Claude revisa cada borrador. Hacer: etiqueta "
             "'extension:corta|normal|larga' (300/600/1500 palabras aprox.), elegida al crear la tarea segun su alcance "
             "(las segundas pasadas a fondo y analisis internos, larga); los recortes de reenvio y LIMITE_PROMPT del auditor "
             "escalan con ella para no cortar nunca un borrador; la seccion PROPUESTAS no cuenta. Tests: borrador largo llega "
             "entero al revisor."),
    importancia=4, urgencia=3, dificultad=2, coste=1, depende="ia",
    etiquetas=["cat:codigo", "prov:claude", "tema:orquestacion", "origen:damian_chat"])

for tid in ("T174", "T175", "T176"):
    T.actualizar(tid, importancia=4, urgencia=5)
    T.anotar(tid, "27/09 Damian: se hace YA (tras el top 5). Investigan los proveedores; Claude solo revisa e implementa.")
T.anotar("T227", "27/09 Damian: se hace YA si conviene. Necesita la clave nvapi- de Damian (build.nvidia.com); la guarda el en secretos.toml "
                 "cuando Code le diga el nombre exacto del campo. Nunca pegarla en un chat.")

p = RAIZ / "memoria" / "INTEGRACION_NUBE.md"
c = p.read_text(encoding="utf-8")
ini = c.index("## Encargos siguientes para Code")
fin = c.index("Plantilla:", ini)
nuevo = (
    "## PLAN DE RETORNO (27/09 noche, pedido por Damian: al acabar el bloque urgente, volver aqui)\n"
    "BLOQUE URGENTE (ahora):\n"
    "  a. T232 top 5 de tareas baratas en Claude y de alto impacto -> hacer las que se elijan.\n"
    "  b. T174 Agent Skills, T175 Graphify, T176 Ponytail: investigan NEXO/proveedores (trabajar_tarea.py), Claude solo revisa (T192) e implementa lo aprobado.\n"
    "  c. NVIDIA como proveedor: T227 (con T162); necesita la clave de Damian.\n"
    "DESPUES, en este orden (plan anterior):\n"
    "1. **T230**: interfaz pensada para Damian (filtrar/ordenar + textos humanos). Primero boceto y aprobacion.\n"
    "2. **T231**: turnos programables desde la app con plantillas de instrucciones.\n"
    "3. **T186**: triaje de ordenes a prueba de fallos.\n"
    "4. **T195**: activar/desactivar y ordenar proveedores en la app.\n"
    f"5. **T194**: rotacion de proveedores y evaluacion cruzada. **{ext['id']}**: extension adaptable de borradores.\n"
    "6. **T077** bandeja web / **T234** prueba_parada / **T182** gpt-oss:20b y T134 (con Damian delante) / T226-T228 (blindados, parche) / T199-T203 investigaciones.\n"
    "Si al volver el plan no encaja: repasar la cola por prioridad y reestructurarlo antes de seguir.\n"
)
p.write_text(c[:ini] + nuevo + c[fin:], encoding="utf-8")
print(ext["id"])
