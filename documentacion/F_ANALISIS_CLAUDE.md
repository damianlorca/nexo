# F. Análisis propio de Claude — 5 casos especiales (Fase 4)

Escrito antes de leer las respuestas completas de Qwen/Gemini/ChatGPT (para que sea un análisis independiente, no contaminado), basado solo en la evidencia de código reunida en `A_MATRIZ_REQUISITOS.md` y `B_AUDITORIA_REAL.md`. La síntesis conjunta con las otras 3 IAs está en `G_SINTESIS_MULTI_IA.md`.

## A. Despertar de Claude bajo demanda

**Viabilidad de lo que ya hay**: alta, ya funciona (`/ahora` vía Routines Fire API, T039). **Coste**: cero adicional (plan Code existente). **Estabilidad**: no probada bajo carga (solo una llamada de prueba con éxito hoy); no probada con dos disparos simultáneos.

**Lo que creo que es genuinamente difícil, no solo "no implementado"**: dos turnos de Claude en paralelo sobre la misma Rutina/dispositivo van a chocar en memoria (`estado.json`, `tareas.json`) igual que ya pasó una vez (incidente documentado en el historial). Esto no es un problema de "activar Claude", es un problema de **concurrencia de memoria compartida**, y ya hay mitigación parcial: los candados de `nucleo/candado.py` protegen cambios MECÁNICOS de un solo campo, pero no protegen una sesión completa de Claude leyendo→pensando→escribiendo durante minutos (el propio código lo documenta así en `nucleo/estado.py`).

**Mi recomendación**: no perseguir "paralelismo real" de turnos de Claude. Es más barato y más seguro diseñar para **un turno a la vez, con cola**: si llega una segunda petición de `/ahora` mientras hay un turno en marcha, que se encole (un archivo o campo en `estado.json`) en vez de dispararse. Evita el problema de raíz en vez de intentar resolver concurrencia real, que es cara y arriesgada para un beneficio (paralelismo) que Damián no ha pedido explícitamente.

## B. Detección de límites/disponibilidad de Claude

**Viabilidad**: baja para detección PREVENTIVA fiable; razonable para detección REACTIVA (después del hecho). No existe API pública documentada de cuota, y no se debe intentar averiguarla vía scraping de la interfaz web (T038 ya lo descarta por ToS).

**Lo único defendible sin tocar ninguna línea roja**: registrar cada disparo y su resultado (éxito/429/error) en `nucleo/uso.py` (ya existe la infraestructura), y tratar un patrón de fallos recientes como señal de "probablemente sin cuota" — una heurística, no una certeza. Esto es barato, ya está construido a medias, y no arriesga nada.

**Mi valoración de "aproximaciones creativas"**: cualquier intento de deducir cuota restante de cabeceras HTTP no documentadas es frágil (Anthropic puede cambiarlas sin aviso) y de bajo valor comparado con el coste de mantenerlo. No lo recomendaría como prioridad, aunque no lo descarto sin ver qué proponen las otras IAs.

## C. Model Router

**Viabilidad**: alta para la parte "qué proveedor" (Qwen/Gemini/ChatGPT/Claude); bloqueada por plataforma para la parte "qué modelo/razonamiento dentro de Claude" (confirmado repetidamente: no se puede cambiar el modelo de una Rutina atada a un dispositivo sin que Damián lo apruebe él mismo).

**Diseño mínimo que yo propondría** (sin implementarlo todavía, es diseño): una función pura `elegir_proveedor(tarea) -> str` que tome como entrada lo que YA existe (`dificultad`, `importancia`, `urgencia`, `coste` de `nucleo/tareas.py`, más un flag "necesita herramientas del PC" que solo Claude tiene) y devuelva uno de `qwen/gemini/chatgpt/claude`. Reglas de partida razonables: tarea mecánica y corta → Qwen; necesita razonar pero no herramientas del PC ni el plan de pago → Gemini/ChatGPT; necesita tocar archivos/ejecutar código/el propio sistema Nexo → Claude (vía Routines Fire), sin discutir el modelo interno (eso lo decide la Rutina, no el Router). Esto es una función de pocas líneas, fácilmente probable con `prueba_*`.

## D. Comunicación entre IAs / protocolo

**Viabilidad**: alta, con el patrón que ya existe (`canal/buzon.py` + `nucleo/candado.py` + `escribir_atomico`). No hace falta infraestructura nueva.

**Mi propuesta concreta**: una carpeta `canal/entre_ias/` con un archivo JSON por mensaje (mismo patrón que `canal/salida/`), con exactamente los campos que pide la especificación (sender, receiver, task_id, message_type, payload, context, priority, timestamp, status, result, error). Quien produce un mensaje lo escribe con `escribir_atomico`; quien lo consume lo lee y lo mueve/renombra (como ya hace `buzon.mensajes_nuevos()` con `.leido`). Es exactamente el mismo patrón ya probado en producción, aplicado a un caso nuevo.

## E. Autonomía completa

**Viabilidad del ciclo COMPLETO de 12 pasos que pide la especificación**: baja a corto plazo, no por imposibilidad técnica sino porque depende de A, C y D (despertar/model router/protocolo) estando ya construidos y probados primero. Intentar construir el ciclo completo antes que sus piezas sería, otra vez, exactamente el automatismo grande que Damián ha pedido auditar y diseñar antes de tocar.

**Lo que sí creo viable ya, como primer paso pequeño y reversible**: que `canal/vigilante.py` (que YA vive siempre en el PC) lea periódicamente `memoria/estado.json::siguiente_turno` y, si hay algo pendiente Y ha pasado un tiempo razonable sin que nadie lo haya tocado, mande un aviso a Damián por Telegram (`buzon.avisar`) en vez de disparar un turno de Claude por su cuenta. Es decir: primero "vigilar y avisar", no "vigilar y actuar solo". Encaja con la regla de la propia especificación de separar OBSERVATION de ACTION/APPROVAL.

---

**Nota de honestidad**: este análisis es mío, hecho ANTES de leer las respuestas completas de las otras 3 IAs para esta misma tarea (Qwen/Gemini/ChatGPT ya se lanzaron en paralelo, en segundo plano, y sus resultados se leen después). La síntesis en `G_SINTESIS_MULTI_IA.md` compara coincidencias y discrepancias reales, no ajustadas a posteriori.
