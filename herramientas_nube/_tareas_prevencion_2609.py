"""Tareas de PREVENCION (26/09/2026): Damian pidio que los fallos de clasificacion,
de modo Pensar/Pro y de revision no solo se corrijan sino que no se repitan.
Evidencia sacada de la revision de las 17 ordenes registradas (T086-T185)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import tareas as T  # noqa: E402

T.actualizar("T186", titulo="Triaje de ordenes a prueba de fallos: acciones directas, duplicados, literal y prioridad reales",
             importancia=5, urgencia=5, detalle=(
    "Revision de las 17 ordenes reales (22-25/09) hecha el 26/09. Fallos SISTEMICOS en nucleo/ordenes.py y "
    "consumidor de mensajes sueltos, no casos aislados:\n"
    "P1 No existe la categoria ACCION DIRECTA: 'cambia T170 a Claude' (T171) y 'mandame un push en 5 min' (T185) "
    "acabaron como cat:codigo/escalado:claude y nadie las ejecuto.\n"
    "P2 Importancia/urgencia fijas 4/4 en toda orden (ordenes.py): no se analizan.\n"
    "P3 Mensajes sueltos de Telegram: Qwen REESCRIBE el titulo (se pierde el literal, T088/T089) y los marca todos "
    "'categoria=tarea'; nunca se trabajan (T094 pendiente desde el 22/09).\n"
    "P4 Sin deduplicado: T148 y T153 (misma orden 'claude red') se investigaron dos veces; T086/T087 duplicadas.\n"
    "P5 La web perdio ordenes en silencio con el 401 del 25/09 (causa ya arreglada por Code; falta avisar si no se guarda).\n"
    "P6 Nadie recoge lo escalado a Claude (ver T173).\n"
    "COMO EVITAR QUE SE REPITA (criterio de terminado):\n"
    "1) Conjunto de ORO: las 17 ordenes reales con su clasificacion/accion correcta como test de regresion; "
    "cada cambio del clasificador debe pasarlo. Toda orden mal clasificada que aparezca se anade al conjunto.\n"
    "2) Categoria ACCION con ejecutor de lista blanca (editar campos de una tarea, programar aviso/push, "
    "consultar estado) que ejecuta y CONFIRMA al usuario; lo que no este en la lista blanca pasa por la cola de aprobaciones.\n"
    "3) Deduplicado antes de dar de alta (similitud con tareas abiertas y de los ultimos 7 dias): si coincide, se anota en la existente y se avisa.\n"
    "4) El literal SIEMPRE se guarda intacto; el titulo puede resumirse, el detalle no.\n"
    "5) Importancia/urgencia estimadas por el clasificador con justificacion; si no puede, 3/3 y marca 'sin_estimar'.\n"
    "6) Respuesta al usuario en toda orden: guardada (id) / ejecutada / duplicada / error. Nunca silencio.\n"
    "7) Informe semanal automatico: ordenes por estado y cuantas llevan >48 h sin tocar."))

pensar = T.anadir(
    "BUG: NEXO no activa Pensar/Pro/Avanzado en ChatGPT y Gemini y sigue trabajando en modo normal",
    detalle=("Evidencia 26/09 13:58-14:19: registros/investigacion_N08_N09_*.log, 12 veces 'chatgpt: no encuentro el boton "
             "Pensar' y aun asi envio los prompts. Damian lo ve tambien a mano en las webs. Borradores T124_20260926_1413 y "
             "T167_20260926_1405 salieron SIN Pensar (calidad baja, rehacer).\n"
             "Arreglo: (1) actualizar selectores del selector de modelo/modo (UI cambio) con prueba en vivo; "
             "(2) FALLO CERRADO: si la tarea exige Pensar/Pro y no se activa, NO se envia: se reintenta, se prueba el otro "
             "proveedor y si no, se para y se avisa; (3) verificar tras enviar que el modo quedo activo (leer la UI) y "
             "registrarlo en la evidencia de cada borrador; (4) test de regresion con captura del DOM. Relacionado: T147."),
    importancia=5, urgencia=5, dificultad=3, coste=2, depende="ia",
    etiquetas=["cat:codigo", "prov:claude", "tema:modelos_proveedores_roles", "bug", "correccion_errores"])

revisor = T.anadir(
    "Revisor/auditor de TODO el trabajo delegado a las webs (modo, conversacion, prompt, OK absoluto)",
    detalle=("Damian 26/09: el revisor debe revisar absolutamente todo, no solo el contenido. Evidencia: T169 salio "
             "SIN_REVISION (autor groq, ningun revisor) y se dio por valido; OK absoluto solo documentado (T183 pendiente); "
             "conversaciones nuevas para el mismo tema; prompts con relleno que puede hacer alucinar a la otra IA.\n"
             "Checklist obligatorio por cada delegacion, con evidencia en registros:\n"
             "a) modo pedido (Pensar/Pro/Avanzado) ACTIVO de verdad (ver bug de Pensar);\n"
             "b) conversacion correcta: mismo tema -> misma conversacion/proyecto; tema nuevo -> nueva;\n"
             "c) prompt minimo suficiente: sin contexto sobrante, sin datos privados, instrucciones verificables; "
             "un revisor local (gpt-oss:20b, T182) puntua el prompt ANTES de enviarlo;\n"
             "d) revision independiente obligatoria con secciones FALLOS/OMISIONES/MEJORAS/ANADIR (T163); sin revisor "
             "disponible -> estado PENDIENTE_REVISION, nunca hecha;\n"
             "e) protocolo OK absoluto (T183) cumplido paso a paso: entender -> trabajar -> autoauditar -> OK justificado, "
             "con tope de iteraciones;\n"
             "f) informe de auditoria por lote y alerta si algun punto falla.\n"
             "Criterio de terminado: una delegacion que incumpla cualquier punto queda bloqueada y visible en la web."),
    importancia=5, urgencia=4, dificultad=4, coste=3, depende="ia",
    etiquetas=["cat:arquitectura", "prov:claude", "tema:orquestacion", "correccion_errores"])

T.anotar("T183", f"26/09: confirmado que el OK absoluto NO se aplica hoy en el pipeline (solo documentado). Se integra en {revisor['id']}.")
T.anotar("T147", f"26/09: el fallo de Pensar pasa a bug propio {pensar['id']}.")
T.anotar("T169", "26/09: borrador SIN_REVISION (groq, sin revisor): no cuenta como revisado. Rehacer con revision.")
T.anotar("T153", "26/09: DUPLICADA de T148 (misma orden 'claude red'); se investigo dos veces. Ejemplo para el deduplicado de T186.")
T.anotar("T094", "26/09: orden de Telegram sin trabajar desde el 22/09 (fallo P3/P6 de T186).")
for tid in ("T124", "T167"):
    T.anotar(tid, "26/09: borrador de hoy hecho por ChatGPT SIN modo Pensar (bug). Calidad baja: rehacer cuando el bug este arreglado.")
print("T186 ampliada;", pensar["id"], revisor["id"])
