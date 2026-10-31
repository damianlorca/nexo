# Requisito de arquitectura: turno nocturno adaptativo por cuota, tiempo y valor

Estado: **CONCEPTO / DISEÑO A FUTURO — NO IMPLEMENTADO**. Añadido al roadmap el 12/09/2026 noche, a petición explícita de Damián, en paralelo a la Pieza 0. No se ha escrito ni una línea de código para esto. No fija fórmula final: fija el concepto, las señales, las reglas y las dependencias.

## Objetivo

Cuando Nexo disponga de una forma fiable de conocer el uso/cuota real de los proveedores, debe poder decidir por sí mismo si activar un turno nocturno merece la pena. El objetivo **no es gastar cuota porque esté disponible**, sino **maximizar el trabajo útil obtenido antes de que esa cuota expire**.

## Señales a combinar

La decisión debe poder combinar, cuando estén disponibles de forma fiable:

- % de cuota/uso restante de cada proveedor.
- Fecha y hora actuales.
- Inicio y final de la ventana de cuota (si existe una ventana identificable).
- Momento de la próxima recarga.
- Tiempo restante hasta esa recarga.
- Tareas pendientes y su prioridad/valor (ya hay una base parcial en `nucleo/tareas.py`: `puntuacion()`, `modelo_sugerido()`).
- Recursos alternativos disponibles (local, otros proveedores).
- Coste o escasez relativa de cada recurso.

## Ejemplo ilustrativo (no es la regla final)

Si ha transcurrido ~60% de una ventana semanal pero solo se ha consumido ~30% de la cuota, puede haber margen para trabajo adicional de noche. Si la cuota está casi agotada, puede ser mejor no activar el turno, o activarlo solo con recursos locales. Caso especial: el último turno antes de una recarga — si va a quedar cuota que se perderá igualmente al recargar, puede tener sentido aprovecharla en trabajo útil de la cola o en mejoras de Nexo, precisamente porque desperdiciarla no ahorra nada.

El criterio matemático/heurístico exacto (cómo se pesan estas señales entre sí) **queda abierto** — se diseñará cuando se aborde esta pieza, no antes.

## Reglas obligatorias

1. No asumir que un porcentaje visible representa una cuota semanal (ni ningún otro periodo): primero hay que identificar qué representa realmente ese número, para cada proveedor.
2. No inventar fechas de recarga ni ventanas de uso que no se puedan confirmar.
3. Si la información no puede obtenerse de forma fiable, tratarla como `UNKNOWN` explícito — Nexo nunca debe presentar una estimación como si fuera un hecho verificado.
4. El sistema debe ser genérico entre proveedores, modelos y tipos de límite distintos (no una solución ad-hoc para uno solo).
5. Si existe una fuente estructurada y fiable de cuota (API, endpoint, campo de estado), debe preferirse sobre visión/OCR de pantalla. La visión de pantalla es un mecanismo válido cuando haga falta, nunca un objetivo en sí mismo.
6. La decisión debe poder reevaluarse durante el propio turno si cambia la cuota, la disponibilidad, la prioridad de las tareas o el estado del sistema.
7. Activación, motivo y resultado del turno deben quedar registrados y ser trazables (esto depende directamente de la Pieza 1 — estado vivo + evidencia).
8. Debe existir un criterio de parada explícito, para no consumir cuota en trabajo de bajo valor solo porque "hay margen".
9. Debe respetar siempre permisos, seguridad, límites de uso, prioridades y los mecanismos de intervención humana ya establecidos (Bootstrap: separación propuesta/validación/permisos/ejecución/verificación).

## Prioridad de trabajo cuando se activa un turno

1. Tareas pendientes de alta prioridad.
2. Tareas bloqueantes o necesarias para desbloquear otras.
3. Mejoras de Nexo con valor claro.
4. Investigación de mejoras, solo cuando exista una hipótesis concreta de mejora (no exploración abierta sin objetivo).
5. Implementación de mejoras seguras.
6. Tests, verificación y recuperación.
7. Documentación y mantenimiento.

## Selección de recurso durante el turno

Sigue la Constitución de Nexo (Bootstrap): mínimo recurso suficiente — local cuando sea suficiente, recursos premium (Gemini/ChatGPT/Claude) reservados para donde aporten valor diferencial. Este turno no es una excusa para gastar cuota "porque toca": la regla de asignación de recursos no cambia de noche.

## Conexión conceptual con otras piezas del roadmap

Esta pieza no es independiente — depende de que existan antes, con evidencia real de que funcionan:

- **Pieza 1 (estado vivo + evidencia)** — imprescindible para registrar activación/motivo/resultado de forma trazable (regla 7) y para saber qué tareas están pendientes y con qué prioridad.
- **Gestión de cuota/uso por proveedor** — hoy **NO EXISTE** como capacidad fiable. Lo único que hay hoy (`nucleo/uso.py`, T029) es un contador local de turnos en `memoria/uso_diario.json`, que no representa cuota real de ningún proveedor. Esta pieza necesita antes una fuente fiable de "cuánta cuota/uso queda", estructurada cuando sea posible (regla 5) — **se identifica aquí como una pieza nueva del roadmap, no contemplada explícitamente antes de esta conversación.**
- **Router y perfiles dinámicos de proveedores** — diseñados conceptualmente en la Fase 4 (`FASE4_E`), no implementados (confirmado en Fase 6: cero código de Router en todo el repo). El turno nocturno adaptativo usa al Router para decidir con qué recurso ejecutar cada tarea seleccionada.
- **Observabilidad** — el registro de origen/motivo de cada decisión (de qué fase salió, qué señales se usaron) se apoya en el mismo mecanismo de trazabilidad que exige el Bootstrap y la Pieza 1.
- **Planificación y cola de tareas** (`nucleo/tareas.py`) — ya existe una base parcial (`puntuacion()`, `modelo_sugerido()`) reutilizable para la prioridad de trabajo del turno.
- **Futuras rutinas nocturnas** — el "turno de noche" ya existente (hoy pausado, disparo por cron fijo `0 23 * * *`) es el punto de partida operativo: esta pieza lo convierte de "turno con horario fijo" a "turno que decide si activarse y cuánto durar según cuota/tiempo/valor".
- **Sistema de control visual (posterior)** — solo entra en juego como mecanismo de lectura de cuota cuando no exista una fuente estructurada fiable (regla 5); no es un prerrequisito de esta pieza, es un posible método secundario dentro de ella.

## Posición en el roadmap

No cambia el orden ya acordado (BOOTSTRAP → PIEZA 0 → PIEZA 1 → ROUTER → DELEGACIÓN → AUTONOMÍA). Esta pieza se sitúa **después de PIEZA 1, y necesita además al Router/perfiles dinámicos y a una gestión de cuota/uso real que hoy no existe** — por dependencias, encaja de forma natural dentro de la fase de AUTONOMÍA, o como pieza propia justo antes de ella. No se decide su posición exacta ni se prioriza su implementación en este documento: solo se deja registrada la dependencia real para cuando corresponda planificarla.
