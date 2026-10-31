# T050 — Protocolo de benchmark: runtime + backend + modelo para Nexo

**Fecha:** 13/09/2026
**Fase:** DISEÑO del benchmark y su protocolo de validación. **No se ha ejecutado ninguna prueba que implique cambios en el entorno.** No se ha descargado ningún modelo, no se ha instalado nada, no se ha tocado Ollama ni su configuración.
**Relación con T049:** T049 (cerrada, aprobada) concluyó mantener Ollama en producción, evaluar `llama-server`+Vulkan como escalón de alto rendimiento, y dejar AMD Lemonade como línea de exploración futura para la NPU — sin medir nada de eso en este PC todavía. T050 es exactamente esa medición: este documento diseña CÓMO se va a medir, no mide todavía.
**Relación con T051:** T051 (roles locales especializados) depende de los resultados de T050 — no se toca aquí.

**Etiquetas de estado de dato usadas en todo el documento** (tal y como pidió Damián, ninguna sustituye a otra):
`YA MEDIDO` · `A MEDIR` · `REQUIERE CAMBIO` · `REQUIERE DESCARGA` · `REQUIERE INSTALACIÓN` · `INFERENCIA` · `DECISIÓN POSTERIOR`

---

## 0. Objetivo y qué NO es este benchmark

Determinar, con evidencia reproducible en este PC, qué combinación de **runtime + backend + modelo** da el mejor equilibrio entre calidad, velocidad, consumo de recursos, estabilidad y capacidad de trabajo sostenido, para producir al final:

- runtime principal,
- backend recomendado,
- modelo FAST,
- modelo DETAILED/LONG,
- si tiene sentido mantener varios modelos especializados (informa a T051, no lo decide).

No es una carrera de tokens/s aislada, ni una comparación que mezcle dos variables a la vez. Sección 1 fija el orden exacto para evitar eso.

## 1. Separación de variables (A: runtime/backend · B: modelo · C: calidad)

**Regla de diseño:** nunca cambiar más de una variable entre dos pruebas cuyo resultado se vaya a comparar.

**Orden de las pruebas (obligatorio, en 3 fases secuenciales):**

**Fase 1 — aísla A (runtime/backend), modelo fijo.**
Modelo fijo = `qwen2.5:7b` (el único con datos `YA MEDIDO` en Ollama-CPU, ver sección 3). Se ejecutan las mismas tareas fijas (sección 4) en cada backend candidato (sección 2), en este orden:
1. Ollama + CPU — `YA MEDIDO` parcialmente (ver sección 3), completar lo que falte.
2. Ollama + Vulkan (si resulta viable arrancarlo de forma aislada, ver sección 2).
3. `llama-server` + Vulkan (si Ollama+Vulkan no cierra el hueco frente al benchmark externo citado en T049).
Además de tiempos, se hace una **comprobación de cordura de salida**: con el mismo modelo y el mismo prompt, la respuesta debe ser textualmente equivalente entre backends (mismo contenido, orden de ideas, sin truncados ni caracteres corruptos) — un backend más rápido pero con salida degradada no cuenta como mejora real. Esto evita el error de atribuir al runtime una diferencia que en realidad es un bug de esa integración concreta.

**Fase 2 — aísla B (modelo), runtime/backend fijo (el ganador de la Fase 1, o Ollama-CPU si ninguna alternativa mejora nada).**
Se ejecutan las mismas tareas fijas con cada modelo candidato (sección 3), sobre el mismo backend, para que la única variable que cambie sea el modelo.

**Fase 3 — mide C (calidad) de forma consistente en las Fases 1 y 2.**
No es una fase temporal aparte, es una regla transversal: la calidad se juzga con la misma rúbrica fija (sección 5) en cualquier combinación, para que sea comparable entre sí. No se usa un modelo local como "juez" de otro (evita el sesgo de autorrecomendación ya documentado en `G_SINTESIS_MULTI_IA.md` — Qwen se recomendó a sí mismo en más de una consulta pasada); la calidad de las tareas DETAILED/TOOL se evalúa con una checklist objetiva de aciertos/fallos (sección 5.3), no con una puntuación subjetiva de otro modelo.

**Fase 4 (solo sobre el/los candidato(s) ganador(es) de las Fases 1-2) — concurrencia (sección 8) y carga sostenida (sección 7).**
Son las pruebas más caras; no tiene sentido correrlas sobre una configuración que ya perdió en velocidad/calidad básica.

## 2. Runtimes/backends candidatos

| Candidato | ¿Entra en T050? | Por qué | Estado |
|---|---|---|---|
| **Ollama + CPU** | Sí — es la línea base de producción | Ya es lo que usa Nexo hoy; sin esto no hay punto de comparación | `YA MEDIDO` (parcial, ver sección 3) / `A MEDIR` (para completar tareas DETAILED/TOOL) |
| **Ollama + Vulkan** (`OLLAMA_VULKAN=1`+`OLLAMA_IGPU_ENABLE=1`) | Sí, con matiz | T049 lo señaló como la ruta de validación más barata antes de considerar `llama-server`; cero instalación nueva, solo variables de entorno | `REQUIERE CAMBIO` — pero ver más abajo cómo probarlo SIN tocar la instalación de producción |
| **`llama-server` + Vulkan** | Condicional — solo si Ollama+Vulkan no cierra el hueco de rendimiento que T049 documentó | Evidencia externa (T049, benchmark de terceros en el mismo chip) es la más prometedora, pero tiene coste operativo real (sin gestor de modelos, sin reinicio automático) | `REQUIERE INSTALACIÓN` |
| **AMD Lemonade** | Como candidato separado, no bloqueante | Único camino a la NPU; su valor no se mide con las mismas métricas de tokens/s de los demás — ver sección 2.3 | `REQUIERE INSTALACIÓN` |
| LM Studio (runtime propio, no solo GUI/reserva) | **No entra como candidato de rendimiento** | T049 concluyó que comparte el mismo motor de fondo que Ollama, sin motivo documentado para esperar una diferencia — benchmarking separado no aportaría información nueva. Se mantiene fuera de T050; su rol de reserva/GUI no cambia. | `DECISIÓN POSTERIOR` (no se reabre salvo hallazgo nuevo) |
| vLLM, LocalAI, text-generation-webui, KoboldCpp | **No entran** | Ya descartados/sin ventaja clara en T049, sin hallazgo nuevo que lo cambie — reabrirlos sería releer lo ya sabido sin producir nada nuevo (principio de eficiencia de contexto de la Constitución) | `DECISIÓN POSTERIOR` |

### 2.1 Cómo probar Ollama+Vulkan SIN tocar la instalación de producción

Esto es importante porque activar esas variables de entorno en el servicio de Ollama que ya usa `extremidades/qwen.py` **sí sería** un cambio de producción (prohibido en esta fase). La forma de probarlo sin tocarla, siguiendo el mismo patrón que la prueba aislada de la Pieza 1 (nunca tocar el original, replicar aparte lo mínimo necesario):

- Lanzar una **segunda instancia** de `ollama serve` en un puerto distinto (p. ej. `11435`), como proceso hijo con `OLLAMA_VULKAN=1`/`OLLAMA_IGPU_ENABLE=1` puestas SOLO en el entorno de ese proceso concreto — la instancia de producción en `11434` sigue corriendo exactamente igual, sin ninguna variable nueva.
- Esto sigue siendo un **cambio de entorno** en el sentido de la "Regla importante" de Damián (arranca un proceso nuevo, puede fallar de forma impredecible al ser un backend experimental) — así que **antes de ejecutarlo se para y se pregunta**, con el formato de la sección 10.2, aunque no toque nada de producción.

### 2.2 `llama-server` + Vulkan

Requiere descargar el binario de `llama.cpp` (build con soporte Vulkan) e iniciarlo como proceso aparte, también en un puerto propio (p. ej. `11436`), apuntando a un `.gguf` de `qwen2.5:7b` (habría que obtener el mismo modelo en formato GGUF si el que gestiona Ollama no es reutilizable directamente — a confirmar como parte de la propia instalación, no antes). Checkpoint obligatorio antes de instalar nada (sección 10.2).

### 2.3 AMD Lemonade — tratamiento distinto

No compite en la misma tabla de tokens/s que los demás en esta primera vuelta: su valor es arquitectónico (acceso a la NPU, no solo a la iGPU). Se le reserva una prueba mínima propia, separada del resto del benchmark, con un objetivo distinto: confirmar que arranca en este equipo y que reconoce la NPU — no decidir todavía si sustituye a nada. Ver sección 8 de T049 (punto 4 de "qué debe medir T050") y el checkpoint de instalación en sección 10.2. No bloquea la recomendación FAST/DETAILED de este documento.

## 3. Modelos candidatos

**Baseline obligatorio:** `qwen2.5:7b` — ya instalado, ya es el modelo de producción, y es el único con datos reales medidos (`memoria/comparativa_modelos.json`, 11/09/2026):

| Modelo | Tarea | Segundos | Tokens | Resultado | Estado |
|---|---|---|---|---|---|
| `qwen2.5:7b` | clasificar | 11.4 | 3 | correcto (`"tarea"`) | `YA MEDIDO` |
| `qwen2.5:7b` | urgencia | 1.8 | 3 | correcto (`"urgente"`) | `YA MEDIDO` |
| `qwen2.5:7b` | resumir | 2.6 | 13 | correcto, resumen fiel | `YA MEDIDO` |

Estas 3 tareas son justo las que se reutilizan como el set fijo de FAST (sección 4.1) — así los nuevos resultados son directamente comparables con esta medición ya existente, sin repetirla desde cero.

**Ya instalados en este equipo** (confirmado con `ollama list`, sin necesidad de descarga):

| Modelo | Tamaño en disco | Datos previos |
|---|---|---|
| `qwen2.5:7b` | 4.7 GB | `YA MEDIDO` (arriba) |
| `qwen3:14b` | 9.3 GB | `YA MEDIDO` parcial (mismas 3 tareas, 11/09 — pero mucho más lento: 44-79s, 4-40× qwen2.5:7b) |
| `qwen3:4b` | 2.5 GB | `YA MEDIDO` — **falló las 3 pruebas** (salida vacía, agota los 800 tokens de presupuesto razonando). Descartado como candidato salvo que se le dé un presupuesto de tokens mucho mayor, lo cual ya está mitigado en `extremidades/qwen.py` (`TECHO_TOKENS=8000`) pero no se ha vuelto a probar con ese mecanismo — `A MEDIR` si se decide darle una segunda oportunidad |
| `llama3.2:3b` | 2.0 GB | `YA MEDIDO` — el más rápido de los 3 sencillos en `urgencia` (0.9s) y `resumir` (1.6s), algo más lento que qwen2.5:7b en `clasificar` (23.9s vs 11.4s) |

**No instalados — candidatos a evaluar según hipótesis concreta:**

| Modelo | Por qué entra | Hipótesis a comprobar | Coste de probarlo | ¿Descarga? | ¿Runtime/backend distinto? |
|---|---|---|---|---|---|
| **Gemma3:12b** | Ya propuesto desde la Fase 2 como candidato de razonamiento medio, nunca medido | Que su calidad en tareas DETAILED (razonamiento/análisis) supere a `qwen2.5:7b` sin pagar el coste de latencia de `qwen3:14b` | Medio (~8GB de descarga, tamaño intermedio) | Sí, `REQUIERE DESCARGA` | No, funciona igual en Ollama |
| **DeepSeek-R1-Distill-Qwen-14b** | Propuesto desde la Fase 2 como candidato de razonamiento/coding | Que su especialización en razonamiento paso a paso mejore la calidad de las tareas DETAILED/coding frente a `qwen3:14b` genérico, al mismo coste de tamaño | Medio-alto (~9GB, mismo orden que qwen3:14b, y su patrón "piensa antes de responder" puede repetir el problema de `qwen3:4b` con presupuestos de tokens cortos) | Sí, `REQUIERE DESCARGA` | No |
| **Qwen3.8-27B** *(nombre exacto a confirmar en el catálogo de Ollama al momento de la descarga — variantes conocidas rondan los 27B parámetros)* | Candidato explícito de Damián para el escalón "modelo grande" | Que un modelo mucho mayor mejore la calidad de tareas DETAILED/LONG lo suficiente para justificar su coste de RAM/tiempo de carga, incluso a 100% CPU | **Alto** — a este tamaño (cuantizado, probablemente 15-20GB en disco, orden de magnitud) el tiempo de descarga, la carga en RAM (con 31GB totales, deja poco margen para el resto de Nexo mientras esté cargado) y el tiempo de inferencia en CPU pueden ser considerables | Sí, `REQUIERE DESCARGA` (tamaño exacto: `A MEDIR` en el momento del checkpoint, no se asume) | Probablemente sí se beneficiaría de Ollama+Vulkan o `llama-server`+Vulkan si la Fase 1 confirma mejora — a CPU pura podría no ser utilizable en la práctica para trabajo continuo |
| **Modelo especializado en coding** *(candidato abierto, p. ej. una variante Coder de Qwen si existe en el catálogo)* | Solo si la Fase 2 muestra que ningún modelo generalista da calidad suficiente en la tarea de coding fija (sección 4.2) | Que un modelo específico de código mejore sustancialmente la tarea de coding sin ser necesario para el resto de roles | Depende del modelo exacto — a determinar solo si hace falta | Sí, `REQUIERE DESCARGA` | No, en principio |

**Explícitamente NO se descarga nada de esta tabla en esta fase.** Gemma3:12b y DeepSeek-R1-Distill-Qwen-14b son candidatos razonables de "modelo intermedio de calidad" — se decide cuál probar primero (si hace falta alguno) **después** de ver si `qwen2.5:7b`/`qwen3:14b`/`llama3.2:3b` (los 3 ya instalados) dejan un hueco de calidad real en las tareas DETAILED. Si `qwen3:14b` ya da calidad suficiente pese a ser lento, puede no hacer falta descargar nada nuevo para el rol DETAILED — eso es precisamente lo que la Fase 2 del benchmark debe decidir antes de gastar ancho de banda/disco en modelos nuevos.

## 4. Escenarios de uso de Nexo

Tareas fijas, reutilizables entre corridas — el mismo prompt exacto cada vez que se repite una prueba (sección 6).

### 4.1 FAST (latencia y coste de recursos)

Reutiliza literalmente las 3 tareas ya medidas el 11/09 (mismo `mensaje` de entrada, mismo formato de salida esperado), para mantener comparabilidad directa con los datos `YA MEDIDO`:
1. **Clasificar** (tarea vs. mensaje informativo vs. pregunta) — ver `extremidades/triaje.py` para el formato real de producción.
2. **Urgencia** (urgente / no urgente).
3. **Resumir** (una frase).

Añadir, por ser un uso real de Nexo hoy no cubierto en la medición del 11/09:
4. **Extracción estructurada corta** (p. ej. extraer de un mensaje libre: fecha, acción, destinatario, en 3 campos) — representa el tipo de tarea que alimentaría un futuro Controlador de Tareas/Planificador.

### 4.2 DETAILED / LONG (calidad, estabilidad, velocidad sostenida, consumo)

4 tareas fijas, cada una acotada para no convertirse en un benchmark largo por sí sola (sección 10 recuerda no ejecutar benchmarks largos en esta fase de diseño; incluso en ejecución futura, cada tarea individual debe tener un techo de tiempo/tokens razonable, p. ej. 3-5 minutos por intento):
1. **Coding acotado**: escribir una función Python pequeña con un contrato claro (p. ej. "fusionar dos diccionarios anidados sin perder claves existentes, con 3 casos de prueba") — mide razonamiento + código correcto, verificable de forma objetiva (los tests pasan o no pasan).
2. **Razonamiento paso a paso**: un problema lógico corto con una única respuesta verificable (evita ambigüedad de corrección).
3. **Análisis de un documento corto real**: resumir/criticar un fragmento de ~1 página de la propia documentación de Nexo (p. ej. un extracto de `T049_RUNTIME_LOCAL.md`) — mide comprensión y síntesis sobre contenido real del proyecto, no un texto de examen artificial.
4. **Planificación**: descomponer un objetivo pequeño y concreto (p. ej. "cómo probar Ollama+Vulkan sin tocar producción") en pasos ordenados — mide si el modelo entiende dependencias y orden, útil de cara al futuro Planificador (T065).

### 4.3 TOOL / STRUCTURED

3 tareas fijas:
1. **Structured output obligatorio**: dado un mensaje libre, devolver *solo* un JSON válido contra un esquema fijo de 3-4 campos (sin texto alrededor) — mide si el modelo respeta el formato de forma fiable, no solo una vez.
2. **Tool calling simulado**: dado un catálogo de 2-3 "herramientas" ficticias (nombre, descripción, parámetros — sin ejecutarlas de verdad), pedir que el modelo elija la herramienta correcta y genere los argumentos en el formato que espera la API de tool calling del backend.
3. **Interacción repetida con herramientas** (2-3 turnos): simular un intercambio de "el modelo pide una herramienta → se le devuelve un resultado ficticio → el modelo debe usar ese resultado para responder" — mide estabilidad del formato a lo largo de varios turnos, no solo en el primero.

## 5. Métricas

**5.1 — Categorías, sin mezclarlas.**

| Categoría | Métricas que entran aquí | Se mide en |
|---|---|---|
| **Latencia** | tiempo hasta primer token (TTFT); tiempo total de la tarea | Todas las tareas FAST/DETAILED/TOOL, un valor por intento |
| **Throughput** | tokens/s de generación (sostenido, no solo el pico inicial) | Tareas DETAILED/LONG y la prueba de carga sostenida (sección 7) |
| **Calidad** | corrección (checklist objetiva, sección 5.3); consistencia entre ejecuciones (¿misma respuesta en esencia con temperatura baja/fija?) | Tareas DETAILED/TOOL, comparando repeticiones (sección 6) |
| **Consumo** | RAM (proceso + total del sistema); uso de GPU/VRAM (si aplica); uso de CPU (%) | Muestreado durante cada tarea y de forma continua en la prueba sostenida |
| **Estabilidad** | errores (tasa, tipo); tiempo de arranque del backend; comportamiento en sesiones largas (degradación sí/no); recuperación ante error (¿el proceso se cae o se recupera solo?) | Prueba sostenida (sección 7) y prueba de concurrencia (sección 8), más cualquier fallo puntual en las demás |
| **Capacidad agentiva** | tool calling (¿elige la herramienta correcta? ¿formato válido?); structured output (¿JSON válido contra el esquema, siempre?); concurrencia (¿se degrada, y a partir de cuántas tareas simultáneas?) | Tareas TOOL/STRUCTURED (5.1) y prueba de concurrencia (sección 8) |

**5.2 — Cómo medir cada cosa en este PC, en concreto (sin ejecutarlo todavía):**
- TTFT/tokens por segundo/tiempo total: se leen directamente de la respuesta de la API OpenAI-compatible (`usage`, timestamps propios alrededor de la llamada) — no requiere instrumentación adicional.
- RAM/CPU del proceso: `Get-Process` (PowerShell) sobre el proceso del backend, muestreado a intervalo fijo durante la tarea.
- GPU/VRAM: Windows expone contadores de rendimiento por motor de GPU (`Get-Counter '\GPU Engine(*)\Utilization Percentage'` y equivalentes de memoria dedicada/compartida) que funcionan también con la iGPU de AMD, sin necesitar herramientas de NVIDIA — a confirmar que dan lecturas útiles para este chip en el momento de implementar (no supuesto como un hecho, `A MEDIR`).
- Errores/estabilidad: capturar código de salida, excepciones del cliente `openai`, y timeouts explícitos con un techo fijo por intento.

**5.3 — Checklist de corrección (evita puntuaciones subjetivas):**
Para cada tarea DETAILED/TOOL se define de antemano una lista corta de comprobaciones binarias (sí/no) específica de esa tarea — p. ej., para el coding: "¿el código es sintácticamente válido?", "¿pasan los 3 tests?", "¿no inventa una API que no existe?". La "calidad" de una corrida es la proporción de comprobaciones que pasan, no una nota subjetiva de 1 a 10. Esto se define al detallar cada tarea, no en esta fase de protocolo general.

## 6. Repetibilidad

- **Repeticiones:** 3 intentos por combinación (backend × modelo × tarea) en las tareas FAST/DETAILED/TOOL — suficiente para detectar una ejecución anómala sin convertir esto en estadística pesada, tal y como pidió Damián. Si las 3 difieren mucho entre sí (ver "outliers" abajo), se hacen 2 intentos más antes de concluir nada.
- **Prompts/tareas fijas:** exactamente los definidos en la sección 4, palabra por palabra, guardados como archivos de texto versionados (no reescritos a mano cada vez) antes de la primera ejecución real.
- **Condiciones constantes:** mismo PC, sin otras cargas pesadas activas a la vez (Chrome con Gemini/ChatGPT cerrado durante la medición, por ejemplo), misma temperatura ambiente razonable, mismo `top_p`/`temperature` fijados explícitamente por tarea (no dejados por defecto, para que la variabilidad entre intentos sea la del propio modelo, no de un parámetro que cambia solo).
- **Identificación de una ejecución:** cada corrida de benchmark genera su propio identificador simple (marca de tiempo + backend + modelo + tarea + número de intento, p. ej. `20260913-153000_ollama-cpu_qwen2.5-7b_clasificar_intento2`). Se guarda en un archivo **propio del benchmark**, separado por completo de `registros/evidencia.jsonl` (Pieza 1) — Pieza 1 queda cerrada y sin re-ejecutar, y mezclar datos de benchmark con el esquema de evidencia de producción confundiría ambas cosas. Ubicación propuesta: `memoria/benchmarks/resultados.jsonl` (una línea por intento, mismo espíritu jsonl que el resto del proyecto).
- **Qué se guarda por intento:** identificador, backend, modelo, tarea, intento número, todas las métricas de la sección 5 aplicables, la salida completa del modelo (para poder auditar la checklist de calidad después, no solo confiar en una nota), y cualquier error.
- **Outliers/fallos:** un intento que falla (error, timeout, salida vacía) se registra igual (no se descarta en silencio) y se repite una vez; si vuelve a fallar, se cuenta como fallo real de esa combinación, no como ruido. Un intento que "sale bien" pero con un tiempo muy alejado de los otros dos (p. ej. 3× la mediana) se marca como sospechoso y se repite en vez de promediarlo sin más.
- **Evidencia suficiente para concluir:** una combinación queda con datos suficientes cuando tiene sus 3 (o 5) intentos completos, sin fallos sistemáticos, y su checklist de calidad aplicada — antes de eso cualquier cifra se cita como `A MEDIR`/preliminar, nunca como conclusión.

## 7. Carga sostenida (LOCAL-FIRST CONTINUOUS WORK)

**Diseño de la prueba** (no ejecutada todavía — requiere el checkpoint de la sección 10.2 antes de correrla, por mantener el PC bajo carga un tiempo apreciable):
- Repetir la tarea DETAILED de coding (4.2.1) en bucle, sin pausas artificiales, sobre la configuración ganadora de las Fases 1-2, muestreando cada iteración: tokens/s, RAM, CPU, GPU/VRAM si aplica, y cualquier error.
- **Duración propuesta para una primera medición: 30 minutos.** Motivo: en hardware portátil (como este Ryzen AI 9 HX 370), los efectos de throttling térmico o de memoria suelen manifestarse dentro de los primeros 10-15 minutos de carga sostenida — 30 minutos da margen para observar una tendencia clara (estable / degradándose) sin comprometer varias horas de PC a una primera prueba exploratoria. Si el resultado es estable, se propone una segunda medición más larga (p. ej. 2h) como paso posterior, explícitamente aprobado aparte.
- **Qué buscar:** ¿el tokens/s de la iteración 20 es comparable al de la iteración 1, o cae progresivamente (degradación térmica/memoria)? ¿la RAM crece de forma acumulativa (fuga) o se mantiene estable? ¿aparecen errores que no aparecían al principio?
- Esta prueba se corre **una sola vez sobre el candidato ganador**, no sobre todas las combinaciones — es cara, y su propósito es validar la elección final, no explorar alternativas.

## 8. Concurrencia

**Diseño de la prueba** (misma condición de checkpoint que la sostenida si se prevé que sature el equipo):
- Usar la tarea FAST de clasificación (4.1.1), representativa del patrón real de producción (triaje de mensajes de Telegram, que puede recibir más de un mensaje seguido).
- Lanzar 1, luego 2, luego 4 peticiones simultáneas contra el mismo backend, midiendo: latencia individual de cada una, throughput agregado, y si alguna falla o se degrada de forma desproporcionada.
- **Hipótesis a comprobar, no asumida:** que el sistema escala razonablemente hasta cierto número de peticiones simultáneas y luego se degrada — el objetivo es encontrar ese punto de quiebre en este hardware concreto, no confirmar que "más concurrencia es mejor" (no lo es, por defecto, en un equipo de un único usuario con recursos compartidos).
- Se corre sobre el candidato ganador de las Fases 1-2, igual que la prueba sostenida — no sobre todas las combinaciones.

## 9. Clasificación de estado — resumen

Ya aplicada línea a línea en las secciones 2-3. Regla general para el resto del documento y para cualquier informe posterior de T050: ningún resultado se presenta como "esto funciona mejor" si su estado no es `YA MEDIDO` con evidencia real de este PC — todo lo demás se cita como `A MEDIR`, `INFERENCIA` (si viene de una fuente externa razonable, como los hallazgos de T049) o `DECISIÓN POSTERIOR` (si depende de un resultado que aún no existe).

## 10. Qué NO hacer todavía (recordatorio explícito de esta fase)

No descargar `Qwen3.8-27B` ni ningún otro modelo nuevo (Gemma3:12b, DeepSeek-R1-Distill-Qwen-14b incluidos). No eliminar modelos existentes. No sustituir `qwen2.5:7b`. No cambiar la configuración de Ollama de producción. No activar Vulkan (ni siquiera en la instancia aparte del punto 2.1, hasta que se apruebe explícitamente). No instalar `llama-server`. No instalar AMD Lemonade. No cambiar ninguna configuración de producción. No ejecutar los benchmarks largos (sostenido, concurrencia) descritos en las secciones 7-8. Todo lo de este documento es diseño y revisión de infraestructura existente, no ejecución.

### 10.1 Lo que SÍ se puede hacer sin este checkpoint (ninguno de estos pasos se ha ejecutado en este turno, pero no requerirían aprobación previa cuando se retome T050, por no descargar/instalar/cambiar nada ni cargar el equipo de forma apreciable):
- Ejecutar las tareas FAST/DETAILED/TOOL sobre Ollama+CPU (el backend de producción, ya en marcha, sin tocarlo) para completar los datos que faltan (todo lo DETAILED/TOOL de `qwen2.5:7b`, y las tareas nuevas de `qwen3:14b`/`qwen3:4b`/`llama3.2:3b`, ya instalados).
- Registrar esos resultados en `memoria/benchmarks/resultados.jsonl` según el diseño de la sección 6.
- Revisar de nuevo la infraestructura (versiones, catálogos, disco disponible) sin modificarla.

### 10.2 Checkpoint obligatorio antes de cualquiera de estos pasos

Antes de: descargar un modelo, instalar software (llama.cpp/llama-server, AMD Lemonade), cambiar cualquier variable de entorno o configuración (incluida la instancia aparte de Ollama+Vulkan del punto 2.1, aunque no toque producción), o ejecutar la prueba sostenida/concurrencia (secciones 7-8), Nexo se detiene y comunica a Damián, exactamente en este formato:

1. Qué se quiere descargar/cambiar.
2. Tamaño o impacto aproximado (disco, RAM, tiempo estimado, uso de CPU/GPU esperado).
3. Por qué es necesario (qué pregunta de este protocolo responde).
4. Qué prueba concreta permitirá hacer.
5. Qué alternativas existen sin modificar el entorno.

Ningún cambio de esta lista se hace hasta que Damián lo revise y apruebe explícitamente esa acción concreta.

## 11. Criterios finales de decisión

La recomendación final de T050 se construye así, no como una impresión general:

- **Por escenario** (FAST, DETAILED/LONG, TOOL/STRUCTURED), el candidato ganador es el que, entre las combinaciones con evidencia `YA MEDIDO` completa (sección 6), mejor cumple el equilibrio pedido — no solo el más rápido: una combinación más lenta pero con checklist de calidad más alta para DETAILED puede ganar igual que una más rápida puede ganar en FAST si su calidad es equivalente.
- **Runtime/backend principal**: el que gane la Fase 1 (sección 1) de forma consistente en más de un escenario, o el de producción actual (Ollama+CPU) si ninguna alternativa mejora de forma clara y verificada (nunca se cambia el runtime de producción "porque en teoría debería ir mejor" — solo con datos `YA MEDIDO` de este equipo).
- Cuando dos configuraciones queden empatadas dentro del margen de variación observado en la sección 6 (repeticiones), se prefiere la de menor coste operativo (menos piezas nuevas que mantener, menos riesgo) — mismo principio de "mínimo recurso suficiente" de la Constitución.
- **Si una categoría no tiene evidencia suficiente** (por ejemplo, porque el checkpoint de un modelo o backend nunca se aprobó, o porque las repeticiones no fueron consistentes), esa categoría se cierra explícitamente como **`NO VALIDADO`** — nunca se rellena con una recomendación basada en la evidencia de T049 (externa) o en una sola corrida. `NO VALIDADO` es una conclusión legítima de esta fase, no un fallo del protocolo.
- El resultado final se expresa en el formato pedido: `FAST → X`, `DETAILED/LONG → Y`, `runtime principal → Z`, `backend → W`, o "una única configuración es suficiente para todo", con cada elemento marcado `YA MEDIDO`/`NO VALIDADO` según corresponda — nunca todo el bloque como una única afirmación sin matices.

## 12. Resultados parciales — primera ejecución (13/09, fase FAST)

Damián aprobó el protocolo y autorizó ejecutar únicamente lo que no requiere
descargar modelos, instalar software ni modificar la configuración de
producción: la fila 1 y la fila 3 completa de la matriz (fase FAST sobre los
4 modelos ya instalados), contra el Ollama de producción, sin tocarlo.

**Incidencia durante la ejecución (corregida antes de medir nada útil):** dos
intentos de lanzar el benchmark que el bridge reportó como error de timeout
sí habían llegado al PC y arrancado el proceso real. Llegaron a coexistir
hasta 4 procesos `runner_t050.py` en paralelo, lo que habría invalidado la
condición de "condiciones constantes" (sección 6). Se detectó inspeccionando
los procesos reales del sistema, se mataron todos, se archivó (nunca se
borró) el `resultados.jsonl` y el log contaminados en `_archivo/20260913/`, y
se relanzó una única ejecución limpia, verificada como proceso único antes de
dejarla correr. Detalle completo en `claude/incidencias-y-mejoras.md` y en la
nota de T050 en `memoria/tareas.json`.

**Harness usado:** `memoria/benchmarks/runner_t050.py` — replica el cliente y
las tareas fijas de `extremidades/qwen.py`/`extremidades/triaje.py`, con el
modelo parametrizado por llamada, streaming para TTFT/tokens-por-segundo, y
medición de RAM de Ollama vía `Get-Process` de PowerShell (no se instaló
`psutil`, para no contar como "instalar software" bajo la regla de esta
fase). Resultados crudos, uno por línea, en
`memoria/benchmarks/resultados.jsonl` (48/48 líneas, 0 excepciones).

### Resultados por modelo (backend `ollama-cpu`, producción, YA MEDIDO)

| Modelo | Checklist OK | Latencia por llamada | Hallazgo de calidad |
|---|---|---|---|
| `qwen2.5:7b` | 12/12 | 2.2–4.8s (media ~3.4s) | Ninguno — las 4 tareas correctas y consistentes en los 3 intentos |
| `qwen3:14b` | 12/12 | 43–320s (media ~89s) | 2 de 3 intentos de "resumir" superan el límite de 20 palabras pedido (23 palabras) — fallo menor y repetible |
| `qwen3:4b` | 9/12 | 47–285s (clasificar/urgencia/extracción); "resumir" nunca produce salida | "resumir" falla las 3 veces (salida vacía, `finish_reason=length`, agota incluso el reintento ampliado a 2400 tokens) — el presupuesto de razonamiento se agota antes de responder |
| `llama3.2:3b` | 9/12 | 2.2–15.3s (media rápida, con arranque en frío de 15.3s en la primera llamada) | "extracción" falla las 3 veces por formato (JSON envuelto en un array con backticks de markdown en vez de un objeto plano); los datos extraídos en sí son correctos |

`qwen2.5:7b` resultó notablemente más rápido que en la medición parcial del
11/09 (2-5s aquí vs 11.4s/1.8s/2.6s entonces) — posible efecto de
caché/contexto entre ejecuciones sucesivas del mismo proceso; no se investiga
más en esta pasada (`DECISIÓN POSTERIOR`).

### Limitación de medición detectada

La RAM de Ollama vía `Get-Process -Name ollama` dio valores bajos y casi
constantes entre modelos (21–43MB), lo que sugiere que el método está
capturando un proceso auxiliar/tray y no el proceso real que carga los pesos
del modelo — `INFERENCIA`, `PENDIENTE DE MEDIR` con otro método (a revisar
antes de usar esta cifra para nada). CPU% no se midió en esta pasada
(requiere muestreo continuo, no implementado todavía). GPU/VRAM no aplica
(backend Ollama+CPU, sin GPU implicada por diseño de esta fase).

### Qué NO se hizo en esta pasada (y por qué)

La fase FAST completa tardó ~45 minutos reales (14:26–15:11) para 48
llamadas — más de lo esperado, sobre todo por `qwen3:14b`/`qwen3:4b`. Dado
ese tiempo ya invertido, no se continuó en la misma pasada a las filas 2 y 6
de la matriz (DETAILED/TOOL), ni a ninguna fila que requiera checkpoint
(4-5, 7-11), para no poner el equipo bajo una carga adicional apreciable sin
avisar antes, tal y como pidió Damián. Cero descargas, cero instalaciones,
ningún cambio de configuración, Vulkan no activado, prueba sostenida y de
concurrencia no ejecutadas.

**Estado de T050 tras esta pasada:** sigue `en_curso`, no `hecha` — hay
evidencia real de la fase FAST, pero faltan DETAILED, TOOL, carga sostenida,
concurrencia, y ninguna decisión final de runtime/backend/modelo se ha
tomado todavía.

## 13. Resultados parciales — segunda ejecución (13/09, fase DETAILED/LONG reducida, qwen2.5:7b vs qwen3:14b)

Damián revisó los resultados FAST y aprobó una fase DETAILED/LONG reducida y
controlada, comparando únicamente `qwen2.5:7b` frente a `qwen3:14b`, para
responder una pregunta concreta: ¿aporta qwen3:14b una mejora cualitativa
suficiente en tareas complejas como para justificar su enorme coste temporal
respecto a qwen2.5:7b? Igual que en la fase FAST, contra el Ollama de
producción, sin tocarlo, sin descargas ni instalaciones ni cambios de
configuración.

**Corrección del método de medición de memoria** (la fase FAST había
invalidado `Get-Process -Name ollama`, ver sección 12): el harness ahora usa
el endpoint nativo `GET http://localhost:11434/api/ps` de Ollama — la misma
fuente que usa el propio `ollama ps` — que da el tamaño real del modelo
cargado en RAM/VRAM. Cambio hecho únicamente en
`memoria/benchmarks/runner_t050.py` (el harness), sin tocar producción, tal y
como autorizó Damián.

**Tareas usadas** (5, ampliando las 4 originales de la sección 4.2 con
contexto largo): coding acotado (fusionar diccionarios anidados, con 4
asserts), razonamiento (problema de edades con respuesta única verificable),
análisis de un fragmento real de `T049_RUNTIME_LOCAL.md` (máximo 4 frases),
planificación (migrar el registro de evidencia de la Pieza 1 a
`manos/shell.py`, siguiendo el método de la Constitución), y una tarea nueva
de contexto largo (leer un fragmento real y extenso de este mismo protocolo
— incluida la sección 4.3 al final — y responder una pregunta cuya respuesta
solo está en la última parte del texto, con `num_ctx=8192` fijado por
petición vía la API nativa de Ollama, sin cambiar la configuración
persistente del servidor). 2 repeticiones por tarea (menos que el estándar de
3 de la sección 6, para mantener la fase "reducida y controlada" que pidió
Damián dado el coste temporal ya observado en FAST).

**No se usó otro modelo local como juez.** Cada tarea tiene una comprobación
objetiva cuando es posible (el código parsea y pasan los asserts; la
respuesta lógica es la correcta; el JSON es válido; el texto menciona el
número correcto de tareas). Para la fidelidad del resumen de análisis al
documento real (¿inventa datos que no están?), no hay comprobación
automática fiable — se documenta como límite metodológico en el propio
registro (`nota_metodologica` en cada línea de `resultados.jsonl`), en vez de
inventar una puntuación de calidad.

### Resultados por tarea (backend `ollama-cpu`, producción, YA MEDIDO)

| Tarea | qwen2.5:7b | qwen3:14b | Diferencia de calidad observada |
|---|---|---|---|
| Coding (fusionar dicts) | 2/2 correcto, 27-44s por intento | 1/2 falló (cortado por el límite de tokens del presupuesto estándar de 2000, `SyntaxError` por llave sin cerrar); el 2º intento necesitó triplicar el presupuesto a 6000 y 734s (~12 min) para llegar a un resultado igual de correcto | qwen3:14b no solo no mejora, en el primer intento **falla** donde qwen2.5:7b acierta a la primera con el mismo presupuesto |
| Razonamiento (edades) | 2/2 correcto ("Cris"), 2.3-3.3s | 2/2 correcto ("Cris"), 47.5-79.2s | Ninguna — misma respuesta correcta en ambos, qwen3:14b 15-34× más lento |
| Análisis de documento real | 2/2 con contenido correcto y fiel a los hechos del extracto (hardware, Ollama, alternativas); ambos intentos superan el límite pedido de 4 frases (7 frases detectadas) | 2/2 con contenido igual de correcto y fiel, mismos hechos; también supera el límite pedido (9 frases detectadas) | Ninguna apreciable — mismo incumplimiento del límite de frases en ambos modelos, mismo nivel de fidelidad; qwen3:14b 3-4× más lento |
| Planificación (migrar registro de evidencia) | 2/2 con 8 pasos numerados, incluye ≥2 términos del método de la Constitución | 2/2 con 8 pasos numerados, mismos términos detectados; redacción algo más detallada por paso, pero mismo número de pasos y mismo cumplimiento del método | Marginal a favor de qwen3:14b en verbosidad/detalle, no en corrección; qwen3:14b 7-9× más lento |
| Contexto largo (pregunta sobre la sección 4.3, al final de un documento largo) | 2/2 correcto (identifica las 3 tareas fijas y la tercera como interacción repetida/multiturno) | 2/2 correcto, con una explicación algo más completa de en qué consiste la tercera tarea | Marginal a favor de qwen3:14b en detalle explicativo, ambos correctos en el hecho pedido; qwen3:14b 3-8× más lento |

### Tiempo y consumo agregados por modelo (grupo completo: 5 tareas × 2 intentos = 10 llamadas)

| Modelo | Duración total del grupo | Memoria del modelo cargado (RAM, método corregido) | VRAM | CPU delta medido |
|---|---|---|---|---|
| `qwen2.5:7b` | 215.19s (~3.6 min) | 6595.0 MB | 0.0 MB (backend CPU, sin GPU) | `INFERENCIA`, no disponible — ver limitación abajo |
| `qwen3:14b` | 1877.22s (~31.3 min) — **~8.7× más lento en agregado** | 15969.4 MB (~2.4× qwen2.5:7b) | 0.0 MB | `INFERENCIA`, no disponible — ver limitación abajo |

Las cifras de memoria ahora son plausibles y consistentes con el tamaño real
de cada modelo en disco (4.7GB/9.3GB), a diferencia de los 21-43MB de la fase
FAST — la corrección del método (sección de arriba) funcionó.

### Limitación de medición aún pendiente

El nuevo `cpu_ollama_segundos()` (pensado para dar núcleos-CPU equivalentes
usados, vía `Get-Process -Name 'ollama*' | Measure-Object CPU -Sum`) devolvió
`null` en ambos grupos — la resta antes/después no produjo un valor válido.
No se investiga la causa exacta en esta pasada (no es bloqueante para
responder la pregunta de Damián, que es sobre calidad vs. tiempo, no sobre
CPU%) — queda como `INFERENCIA`, `PENDIENTE DE MEDIR` con otro método si en
el futuro hace falta esa cifra concreta.

### Respuesta a la pregunta de esta fase

**No** — con la evidencia de estas 5 tareas y 2 repeticiones, `qwen3:14b` no
muestra una mejora cualitativa que justifique su coste temporal frente a
`qwen2.5:7b`. En 4 de las 5 tareas (razonamiento, análisis, planificación,
contexto largo) ambos modelos llegan al mismo resultado correcto, con
`qwen3:14b` aportando como mucho algo más de detalle redaccional en 2 de
ellas (planificación, contexto largo) sin diferencia de corrección. En la
única tarea donde una diferencia de capacidad real podría notarse (coding),
`qwen3:14b` **falló** en el primer intento con el mismo presupuesto de tokens
que a `qwen2.5:7b` le bastó para acertar a la primera, y necesitó triplicar
el presupuesto y 12 minutos para igualar (no superar) el resultado que
`qwen2.5:7b` dio en 44 segundos. En conjunto, `qwen3:14b` tardó ~8.7× más
tiempo total y usa ~2.4× más RAM, sin ninguna ventaja de calidad observada en
esta muestra.

Esto es evidencia real de esta pasada (`YA MEDIDO`), sobre una muestra
reducida (2 intentos por tarea, 5 tareas, evaluación semi-automática con una
limitación documentada en la fidelidad de "análisis") — coherente con la
lectura provisional de Damián tras la fase FAST (`qwen3:14b` candidato a
DETAILED/LONG pero no validado), y ahora con datos DETAILED reales que la
refuerzan. No se convierte en decisión definitiva por Nexo — queda para que
Damián la revise junto con el resto.

### Qué NO se hizo en esta pasada (y por qué)

No se ejecutó la fase TOOL/STRUCTURED, no se probó `qwen3:4b` ni
`llama3.2:3b` en DETAILED, no se descargó ningún modelo (`Qwen3.8-27B`
incluido), no se instaló nada, no se activó Vulkan, no se instaló
`llama-server` ni AMD Lemonade, no se ejecutó la prueba de carga sostenida ni
la de concurrencia, y no se cambió el modelo ni la configuración de
producción — exactamente el alcance que pidió Damián para esta fase.

**Estado de T050 tras esta pasada:** sigue `en_curso`, no `hecha` — hay ahora
evidencia real de FAST y de un DETAILED reducido, pero faltan TOOL, carga
sostenida, concurrencia, DETAILED de los otros 2 modelos instalados, y
ninguna decisión final de runtime/backend/modelo se ha tomado todavía.
Pendiente de la revisión de Damián sobre este resultado antes de considerar
cualquier acción sujeta a checkpoint (sección 10.2), incluida la descarga de
`Qwen3.8-27B`.

---

## Matriz de pruebas (resumen operativo)

| # | Fase | Backend | Modelo | Escenario | Requiere | Estado antes de ejecutar |
|---|---|---|---|---|---|---|
| 1 | 1 | Ollama+CPU | qwen2.5:7b | FAST (4.1.1-3) | Nada nuevo | `YA MEDIDO` |
| 2 | 1 | Ollama+CPU | qwen2.5:7b | FAST (4.1.4), DETAILED, TOOL | Nada nuevo | `A MEDIR` (FAST 4.1.4 ya `YA MEDIDO` 13/09 — ver sección 12; DETAILED reducido de 5 tareas ya `YA MEDIDO` 13/09 — ver sección 13; TOOL completo pendiente) |
| 3 | 1 | Ollama+CPU | qwen3:14b, qwen3:4b, llama3.2:3b | FAST completo | Nada nuevo (ya instalados) | `YA MEDIDO` (13/09 — ver sección 12; ver matices de fallos por modelo ahí) |
| 4 | 1 | Ollama+Vulkan (instancia aparte) | qwen2.5:7b | FAST+DETAILED+TOOL (mismo set que backend 1) | Checkpoint 10.2 (cambio de entorno) | `REQUIERE CAMBIO` |
| 5 | 1 | `llama-server`+Vulkan | qwen2.5:7b (GGUF) | FAST+DETAILED+TOOL | Checkpoint 10.2 (instalación) | `REQUIERE INSTALACIÓN` |
| 6 | 2 | Ganador de Fase 1 | qwen3:14b, llama3.2:3b (ya instalados) | DETAILED+TOOL completo | Nada nuevo si el ganador es Ollama | `A MEDIR` (qwen3:14b: DETAILED reducido de 5 tareas ya `YA MEDIDO` 13/09 sobre Ollama+CPU — ver sección 13; TOOL completo y llama3.2:3b DETAILED aún pendientes) |
| 7 | 2 | Ganador de Fase 1 | Gemma3:12b / DeepSeek-R1-Distill-14b (solo si 6 deja hueco de calidad) | DETAILED | Checkpoint 10.2 (descarga) | `REQUIERE DESCARGA` (condicional) |
| 8 | 2 | Ganador de Fase 1 (preferiblemente con aceleración, si la Fase 1 la valida) | Qwen3.8-27B | DETAILED/LONG | Checkpoint 10.2 (descarga grande) | `REQUIERE DESCARGA` (condicional a que 6-7 no basten) |
| 9 | — | AMD Lemonade | el que Lemonade traiga por defecto | Prueba mínima de arranque/NPU (no comparable a las demás) | Checkpoint 10.2 (instalación) | `REQUIERE INSTALACIÓN` |
| 10 | 4 | Candidato ganador global | Candidato ganador global | Carga sostenida (sección 7) | Checkpoint 10.2 (carga prolongada) | `REQUIERE CAMBIO` (ejecución larga) |
| 11 | 4 | Candidato ganador global | Candidato ganador global | Concurrencia (sección 8) | Checkpoint 10.2 si se prevé saturar el equipo | `REQUIERE CAMBIO`/`A MEDIR` |

## Orden óptimo de ejecución (cuando se apruebe empezar)

1. Filas 1-3 (completar Ollama+CPU con lo ya instalado) — **sin checkpoint, se puede hacer en la siguiente sesión de trabajo real sin pedir nada más**.
2. Con esos datos completos, decidir si vale la pena pedir el checkpoint de la fila 4 (Ollama+Vulkan) — probablemente sí, es la prueba más barata de las que requieren aprobación.
3. Según el resultado de 4, decidir si hace falta la fila 5 (`llama-server`).
4. Con el runtime/backend ya decidido (Fase 1 cerrada), pasar a la Fase 2 (filas 6-8), empezando siempre por lo ya instalado antes de pedir ninguna descarga.
5. Fila 9 (Lemonade) puede investigarse en paralelo en cualquier momento, porque no bloquea ni depende de las demás.
6. Filas 10-11 al final, solo sobre el ganador.

---

## Resumen para el resultado esperado de esta fase

1. **Protocolo completo:** este documento.
2. **Matriz de pruebas:** sección "Matriz de pruebas".
3. **Modelos candidatos y justificación:** sección 3.
4. **Orden óptimo de ejecución:** sección "Orden óptimo de ejecución".
5. **Dependencias de cada prueba:** columna "Requiere" de la matriz + sección 1 (orden por fases).
6. **Pruebas que no requieren modificar nada:** filas 1-3 de la matriz, detalladas en 10.1.
7. **Pruebas que requieren descargas/instalación/cambios:** filas 4-5, 7-11 de la matriz, todas sujetas al checkpoint de la sección 10.2.
8. **Métricas y criterios de aceptación:** sección 5 (métricas) + sección 6 (cuándo hay evidencia suficiente).
9. **Método de repetición y registro de resultados:** sección 6.
10. **Criterio final para elegir runtime/backend/modelos:** sección 11.
