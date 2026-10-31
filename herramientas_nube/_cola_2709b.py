from pathlib import Path

p = Path(__file__).resolve().parent.parent / "memoria" / "INTEGRACION_NUBE.md"
c = p.read_text(encoding="utf-8")
ini = c.index("## Encargos siguientes para Code")
fin = c.index("Plantilla:", ini)
nuevo = (
    "## Encargos siguientes para Code (UNO por sesion, en este orden; actualizado el 27/09 tarde)\n"
    "1. **T188 + T193**: navegador fiable. Modo Pensar/Pro con fallo cerrado, se acabó el falso OK (la respuesta solo vale si "
    "sigue a nuestro prompt), candado exclusivo del Chrome de NEXO y lectura DOM de ChatGPT.\n"
    "2. **T183 + T189**: OK absoluto de verdad (misma conversación por tema hasta una respuesta excelente) y auditor de todo lo delegado.\n"
    "   -> Con 1 y 2 hechos y con evidencia, Damián decide si reactiva los turnos (`python -m nucleo.turnos on`).\n"
    "3. **T186**: triaje de órdenes a prueba de fallos (con /turnos y el botón de turnos en la web).\n"
    "4. **T195**: en la app, activar/desactivar proveedores (general y por tarea) y ordenar el orden de llamada.\n"
    "5. **T194**: rotación de proveedores y evaluación cruzada, para decidir después el orden por tipo de tarea.\n"
    "6. **T192**: circuito cerrado de revisión de borradores (los 13 pendientes).\n"
    "7. **T077**: bandeja de aprobaciones en la web. **T196** (bug pequeño del vigía) cuando toque la interfaz.\n"
)
p.write_text(c[:ini] + nuevo + c[fin:], encoding="utf-8")
print("ok")
