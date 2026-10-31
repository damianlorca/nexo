# FASE 2 — H. ¿Debe correr el turno de noche esta noche?

**Recordatorio explícito: esta sección es una recomendación. No se ha pausado ni modificado la rutina. Cualquier cambio requiere confirmación expresa de Damián, tal como pidió.**

## Qué haría el turno de noche si corre tal cual esta noche

La rutina arranca una sesión de Claude Code con un prompt fijo que revisa la cola de tareas pendientes y encadena trabajo sin supervisión hasta agotar lo razonable de la sesión. La cola "ia" tiene ahora mismo tareas pendientes reales (entre otras: T029, T002, T042, T027, T005, T014, T035, T037, T024, T044) — es decir, el turno de noche encontraría trabajo real que hacer y lo haría, no se quedaría inactivo.

El problema no es que no tenga qué hacer: es que **una parte no trivial de esas piezas está tocada directamente por esta misma revisión de arquitectura** — T037 (documentado como abierto, con nota extensa) y T039 (recién cerrada con una conclusión nueva que el propio turno de noche podría no conocer si su prompt no se ha actualizado con esta conclusión) son los casos más claros. Si el turno de noche decide "seguir con T037" o "reabrir T039" con el conocimiento que tenía antes de esta revisión, puede: (a) duplicar trabajo ya hecho aquí, (b) tomar una dirección ya descartada explícitamente (p. ej., intentar de nuevo la vía de API Routines para T039), o (c) tocar código que esta misma revisión ha dejado señalado como "a cambiar" sin que el turno de noche sepa que ese cambio está pendiente de decisión de Damián.

## Cuánto uso de Claude podría generar

Un turno de noche que encadena varias tareas de una cola con 10 pendientes puede fácilmente consumir una sesión larga completa — es su diseño (trabajo desatendido, no una tarea puntual). No hay una medición exacta de coste en esta revisión (no era su objetivo), pero el patrón de "cola larga + encadenar sin parar" es, por diseño, el escenario de mayor consumo de los que existen hoy en el sistema.

## Riesgo de interferencia con las pruebas en curso

Alto en dos sentidos concretos:
1. **Riesgo de contradecir esta misma auditoría** — si el turno de noche actúa sobre T037/T039 sin conocer las conclusiones de esta revisión (que vive en `documentacion/FASE2_*.md`, no en el prompt de la rutina ni en `memoria/estado.json` todavía, dado que esta revisión sigue en curso), puede deshacer o contradecir trabajo de análisis que Damián todavía no ha terminado de revisar.
2. **Riesgo de tocar módulos "en revisión conceptual"** — aunque esta fase es explícitamente de análisis y no de implementación (nada se ha tocado en `nucleo/`, `extremidades/`, `canal/`), el turno de noche no tiene forma de saber que hay una decisión de arquitectura pendiente sobre, por ejemplo, el papel de Qwen o la integración con Claude — si decide "mejorar" algo de eso por su cuenta, competiría con lo que Damián decida a partir de esta misma revisión.

## Recomendación: (C) pausar temporalmente durante esta fase de reorganización

De las cuatro opciones que planteó Damián (A: mantenerlo, B: pausar solo esta noche, C: pausar temporalmente, D: rediseñar antes de reactivar):

- **(A) se descarta**: el riesgo de interferencia descrito arriba es real y concreto, no hipotético — hay tareas pendientes que esta misma revisión afecta directamente.
- **(B) es insuficiente**: el motivo de la pausa no es "solo esta noche" — es "mientras dure esta fase de decisiones de arquitectura", que previsiblemente sigue más de una noche (quedan decisiones pendientes en la sección S).
- **(D) es excesivo ahora mismo**: rediseñar el turno de noche es en sí mismo una de las piezas de este roadmap (depende del Model Router, la observabilidad y la autonomía incremental — secciones B, F, O), no algo que deba bloquear el resto de la reorganización.
- **(C) es la recomendación**: pausar la rutina de forma explícita y reversible mientras Damián revisa y decide sobre las secciones de esta auditoría, y reactivarla (tal cual, sin rediseño) en cuanto las decisiones pendientes más relevantes (Model Router, papel de Qwen, estrategia de Claude) estén al menos confirmadas — no necesariamente implementadas del todo.

**Esto es una recomendación, no una acción tomada.** La rutina sigue activa tal como estaba (`0 23 * * *`, "turno de noche (único, 01:00)") salvo que Damián confirme la pausa.
