# FASE 2 — G. Economía de tokens y recursos: dónde se gasta de más y cómo evitarlo

## Fuentes de gasto innecesario identificadas (evidencia, no suposición)

1. **Releer historial largo de una tarea en cada turno que la toca.** Confirmado en las notas de T037/T039 (cientos de palabras cada una). Cada vez que Claude retoma la tarea, relee la nota entera para recordar qué se sabe. Esto es exactamente lo que un resumen de Qwen (sección A) puede evitar: mantener un resumen corto siempre actualizado y solo acudir al historial completo cuando el resumen no basta.
2. **Cruzar manualmente `canal/entrada/` con lo ya respondido.** Ya parcialmente resuelto por `memoria/triaje.json` (T032) para mensajes sueltos, pero no para todo el flujo de entrada — sigue habiendo trabajo de lectura/cruce que un script determinista podría dejar resuelto antes de que Claude entre a interpretar.
3. **Verificación de resultados mecánicos hecha por Claude cuando podría delegarse.** Comprobar que un JSON es válido, que un script importa, que un archivo tiene el tamaño esperado — hoy lo hace el propio turno de Claude leyendo la salida; es trabajo de "sí/no" que Qwen o Python puro resuelven mucho más barato.
4. **Segundas opiniones no acotadas por una regla explícita.** Antes de esta revisión, no existía un criterio escrito de cuándo vale la pena consultar a otra IA — la consulta selectiva de esta misma fase (2 preguntas, no un barrido) es el ejemplo de cómo debería hacerse siempre; sin una regla, el riesgo es repetir el patrón "consultar por si acaso" que ya se evitó aquí a propósito.
5. **Uso de un modelo más caro que el que exige la tarea**, en ausencia del Model Router (sección B) — sin una clasificación previa de la tarea, todo tiende a ir por la vía por defecto (Claude), incluida la que un modelo local ya resolvería igual de bien (ver ejemplos concretos en sección A).

## Tres políticas a fijar (diseño, no implementación)

**Política 1 — "Contexto mínimo suficiente".** Antes de mandar una tarea a Claude (interactivo o de rutina), el contexto que se adjunta debe ser el resumen más corto que sea correcto, no el historial completo por defecto. Regla concreta: si existe un resumen de Qwen más reciente que el último cambio real de la tarea, usar el resumen; releer el historial completo solo si el resumen mismo señala que faltan detalles, o si la tarea ha estado inactiva más de un umbral de tiempo (para no arrastrar un resumen obsoleto sin decirlo).

**Política 2 — "Segunda opinión solo si el valor esperado la justifica".** Consultar a otra IA (Gemini/ChatGPT o incluso una segunda pasada de Qwen) solo cuando se cumplan a la vez: (a) hay más de una alternativa razonable, (b) el coste de equivocarse es alto o difícil de revertir, y (c) el conocimiento propio de Claude tiene una razón concreta para ser insuficiente (corte de conocimiento, especialización que no es la suya, ausencia de acceso en vivo a algo). Las tres condiciones deben cumplirse — es la misma regla, ahora explícita, que ya se aplicó de facto al elegir solo 2 preguntas para esta fase en vez de un barrido.

**Política 3 — "No volver a preguntar lo que Nexo ya sabe".** Si un dato ya está en `memoria/estado.json`, `config.toml`, o una nota de tarea vigente, no debe volver a pedirse por otra vía (ni a Damián, ni a otra IA, ni recalculándolo) salvo que haya una razón concreta para sospechar que cambió. Esto incluye no repetir preguntas de arquitectura ya resueltas en fases anteriores de esta misma auditoría — el motivo explícito de la sección M (correcciones) es precisamente evitar que una conclusión ya alcanzada se vuelva a investigar desde cero sin causa.

## Qué NO sacrificar

Ninguna de las tres políticas debe aplicarse a costa de fiabilidad en tareas importantes — el propio enunciado de Damián lo pide así. En la práctica: el umbral de "importante" lo marca el sistema de permisos existente (`nucleo/permisos.py`, niveles VERDE/ÁMBAR/ROJO) — una acción ÁMBAR o ROJA nunca debe recortar contexto ni saltarse verificación para ahorrar, aunque cueste más; el ahorro se dirige a las acciones VERDES y al trabajo repetitivo de bajo riesgo.

## Relación con el resto del diseño

Depende directamente de: el Model Router (sección B, para saber a qué proveedar/modelo mandar cada cosa), el papel ampliado de Qwen (sección A, quien hace los resúmenes y verificaciones baratas), y la observabilidad (sección F, para detectar en la práctica cuándo se están rompiendo estas políticas — p. ej., el vigilante ligero de trazas puede señalar "N llamadas al mismo proveedor en poco tiempo" como posible violación de la Política 2).
