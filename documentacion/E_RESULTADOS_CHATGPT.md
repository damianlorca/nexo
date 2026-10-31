# E. Resultados de ChatGPT — 5 casos especiales (Fase 3 acotada)

**Mismo aviso metodológico que en `D_RESULTADOS_GEMINI.md`**: respuestas A/B/C reordenadas por contenido real; D y E recuperados limpios en la segunda tanda con más margen de espera.

## A. Despertar de Claude bajo demanda
> No asumiría que varias llamadas `fire` sobre la misma rutina sean sesiones aisladas. Dado el incidente de memoria, trátalo como recurso exclusivo. Implementaría en Nexo una cola propia de trabajos: `/ahora → job_id → persistencia → dispatcher → un único fire → detectar finalización → siguiente job`. Para tareas independientes, aislaría el estado por job (`estado/{job_id}.json`, workspace/git worktree separado) y haría que Claude escriba únicamente ahí. Si se necesita verdadera concurrencia, la vía limpia sería múltiples entornos/rutinas independientes, no múltiples `fire` concurrentes sobre una misma rutina. **En resumen: cola + aislamiento de estado es la solución compatible con las restricciones; no hay vía oficial documentada para paralelismo seguro dentro de una misma rutina.**

**Lectura**: la propuesta de "cola de un solo trabajo a la vez" coincide EXACTAMENTE con la recomendación independiente de Claude en `F_ANALISIS_CLAUDE.md` — coincidencia fuerte entre dos análisis hechos por separado.

## B. Detección de límites/disponibilidad de Claude
> Después de cada `fire`: registrar exhaustivamente HTTP status, cuerpo, headers y request-id. Estimación local: ventanas deslizantes de 5h y semanal, con un modelo conservador (DISPONIBLE / PROBABLEMENTE_AGOTADA / DESCONOCIDA). No convertir número de turnos en cuota exacta. **Muy importante: evitar endpoints internos no documentados** — aunque funcionen hoy, son frágiles. El objetivo realista es **detectar + aprender + retrasar, no conocer la cuota anticipadamente con certeza.**

**Lectura**: la más cautelosa de las tres IAs externas — desaconseja explícitamente depender de endpoints no documentados (a diferencia de Gemini, que sí sugiere explorarlos). Coincide con Claude en que la detección será siempre reactiva.

## C. Model Router
> Política por escalones, priorizando coste: Qwen → tareas simples; Gemini/ChatGPT → tareas medias con rate-limit/cooldown/presupuesto diario; Claude → tareas complejas/críticas, solo si el beneficio justifica gastar cuota. Fallback automático si un proveedor falla. **El router solo decide DISPARAR la rutina, no decide modelo/razonamiento** — puede marcar `reasoning_required=high` y notificar a Damián si hace falta cambiarlo a mano. Registrar cada decisión (tarea→decisión→resultado→coste/latencia). Empezar con un `PolicyRouter` simple con reglas en JSON/YAML.

**Lectura**: la formulación más precisa de las cuatro fuentes sobre el límite exacto de lo que el Router puede/no puede decidir — coincide exactamente con el bloqueo de plataforma confirmado por evidencia de código en esta misma auditoría.

## D. Comunicación entre IAs / protocolo (recuperado en la segunda tanda)
> Un mini-bus persistente basado en archivos, reutilizando el patrón de `buzon.py`. Mensaje: `{id, task_id, sender, receiver, type, priority, payload, context, created_at, status, result, error}`. Cola en `cola.json` protegida con el mismo file-lock de `buzon.py`, estados `pending → processing → done|failed`, con **claim atómico** para impedir que dos procesos ejecuten el mismo mensaje. Resultados grandes en `tareas/<task_id>/steps/NNN.json` (el mensaje solo lleva una referencia, evitando duplicar payloads). Añadir a `proveedores.py` un `MessageBus`/`Dispatcher` que reclama, comprueba `disponible()`/capacidades, llama a `enviar()`, registra resultado/error y genera el siguiente mensaje. **Añadir `max_steps`, `max_retries`, `cooldown` y `chain_id` para evitar bucles y ráfagas.**

**Lectura**: la propuesta más orientada a "ingeniería de producción" de las cuatro (claim atómico explícito, límites de reintentos y de pasos incorporados al propio diseño desde el principio, no como añadido posterior). Coincide en la estructura de campos con Qwen y Gemini.

## E. Autonomía completa (recuperado en la segunda tanda)
> Convertir `tareas.py` + `vigilante.py` en una máquina de estados persistente, sin crear otro orquestador independiente. `tareas.py` guarda además `fase, subtareas, dependencias, intentos, proveedor, resultado, next_action, updated_at`. Cada objetivo es un workflow: `OBSERVAR → PLANIFICAR → DELEGAR → EJECUTAR → VERIFICAR → CORREGIR → DOCUMENTAR → FINALIZAR`. `estado.json::siguiente_turno` deja de contener instrucciones libres y guarda solo acciones reanudables (`{"task_id":"T42","action":"ejecutar","step":"S3"}`). `vigilante.py` (que ya vive siempre) ejecuta un dispatcher pequeño: detecta acciones pendientes, comprueba bloqueos/cuotas, dispara el proveedor apropiado, registra el resultado. **Claude no debe poseer el estado del proceso: puede planificar/verificar, pero el estado canónico vive en archivos de Nexo** — así su cuota, fallo o finalización no destruyen el estado. `intentos + backoff + límite de reintentos` evita bucles; si falla repetidamente, escalar a otra IA o aparcar. `USER_DECISION_REQUIRED` congela el workflow hasta respuesta humana.

**Lectura**: la formulación más clara de las cuatro sobre un principio de diseño importante — **"Claude como worker sustituible, no como dueño del estado"** — que ninguna de las otras tres fuentes expresó con esta claridad, aunque todas apuntan en la misma dirección (persistencia en archivos, no en la cabeza de un turno).
