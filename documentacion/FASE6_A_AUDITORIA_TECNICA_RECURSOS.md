# FASE 6 — Auditoría técnica de recursos (código real, no documentos)

Metodología: cada afirmación de este documento viene de leer el código fuente real en el PC, ejecutar comandos reales (`ollama list`, `git log`, `Get-Process`, `Select-String`/grep), o leer registros/mediciones ya guardados en disco — no de lo que dicen las Fases 2-4. Donde un documento anterior decía algo distinto de lo que el código muestra, se señala explícitamente. **No se ha implementado nada.**

Etiquetas usadas: **REAL Y TESTEADO** (código en producción + evidencia de ejecución real) / **REAL SIN TESTEAR** (código existe y se puede llamar, pero no hay evidencia de haberse probado en las condiciones reales que importan) / **DISEÑADO** (está en algún FASE*.md pero no hay una línea de código) / **NO EXISTE** (ni diseño ni código).

---

## A. IA LOCAL / QWEN

### Qué hay instalado (evidencia: `ollama list`, ejecutado ahora)

| Modelo | Tamaño | Descargado |
|---|---|---|
| qwen3:14b | 9.3 GB | hace 2 días |
| qwen3:4b | 2.5 GB | hace 2 días |
| qwen2.5:7b | 4.7 GB | hace 2 meses |
| llama3.2:3b | 2.0 GB | hace 2 meses |

Gemma y DeepSeek-R1-Distill, mencionados como "candidatos a medir" en las Fases 2-4, **no están descargados**. Siguen siendo teóricos.

### Qué modelo se usa REALMENTE (evidencia: `config.toml`, sección `[qwen]`)

```
modelo_obrero = "qwen2.5:7b"     # NO qwen3:4b
modelo_criterio = "qwen3:14b"
```

El valor por defecto que trae el código si faltara la config (`extremidades/qwen.py`, función `pedir()`: `valor(f"qwen.{clave}", "qwen3:4b")`) **nunca se usa** en la práctica porque `config.toml` lo sobreescribe. Esto es relevante porque las Fases 2-4 hablaban de "Qwen3:4b/8b como candidatos a medir" sin mencionar que la medición **ya se hizo el 11/09/2026**, antes incluso de la Fase 2, y quedó guardada en `memoria/comparativa_modelos.json` (leído ahora, real):

| Modelo | Tarea | Segundos | Resultado |
|---|---|---|---|
| qwen3:4b | clasificar/urgencia/resumir | 37.8–40.4 s | **VACÍO en las 3** (corte `length`: se gastó el presupuesto pensando) |
| qwen2.5:7b | clasificar/urgencia/resumir | 1.8–11.4 s | correcto en las 3 — **ganador, es el que está en producción** |
| llama3.2:3b | clasificar/urgencia/resumir | 0.9–23.9 s | correcto en las 3 |
| qwen3:14b | clasificar/urgencia/resumir | 43.7–78.6 s | correcto en las 3, pero 4-40× más lento que qwen2.5:7b |

Conclusión con evidencia: **"más grande y más nuevo" no fue mejor** para esta tarea. El modelo que razona antes de responder (qwen3) es contraproducente para trabajo mecánico rápido: gasta el mismo presupuesto de tokens pensando que contestando (documentado también en la cabecera de `extremidades/qwen.py`, con una medición aparte del 11/09: `max_tokens=20` → cadena vacía en 74,8 s; `max_tokens=400` → respuesta en 9,1 s).

### Cómo se invoca

`extremidades/qwen.py`: cliente OpenAI-compatible contra Ollama (`http://localhost:11434/v1`), con LM Studio (`http://localhost:1234/v1`) de reserva si Ollama no responde. Cuatro funciones públicas: `pedir()`, `clasificar()`, `resumir()`, `lote()`.

### Qué tareas puede realizar hoy (por código, no por diseño)

- `clasificar(texto, categorias)`: una de N categorías. Tiene lógica no trivial para no invertir la respuesta (bug real corregido, documentado en el propio código: antes devolvía la categoría contraria por buscar subcadenas).
- `resumir(texto, palabras)`.
- `pedir(instruccion, texto)`: libre.
- `lote(instruccion, textos)`: **secuencial**, no paralelo — N tareas tardan N × latencia individual, sin nada que lo acelere.

Ninguna de las cuatro tiene acceso a herramientas: `extremidades/qwen.py` no importa `manos/*` ni `proveedores.py` — confirmado por grep. Qwen solo ve el texto que se le pasa y devuelve texto.

### Qué hace YA dentro de Nexo — REAL Y TESTEADO

**Una sola cosa: triaje de mensajes sueltos de Telegram.** `extremidades/triaje.py` (`triar()`) llama a `clasificar()` dos veces (categoría, urgencia) y a `pedir()` una vez (resumen de una frase). Se dispara desde `canal/bot.py` (`_texto_triaje()` → `_avisar_con_qwen()`, en un hilo aparte) para cualquier mensaje suelto de Telegram, solo si `config.toml [canal] qwen_responde_libres = true` (está en `true`). Explícitamente **no da de alta tareas ni decide nada** — informa y ya. Probado de verdad: `prueba_qwen_vivo.py` y `prueba_triaje_bot.py`, con logs reales en `registros/` (`prueba_qwen_vivo_20260911_041627.log`, `prueba_triaje_20260912_001947.log`, etc.).

Todo lo demás de la lista que pedías auditar — planificación, descomposición de tareas, gestión de la cola, preparación de contexto, búsqueda en documentación, ejecución de herramientas, generación/debugging de código, verificación, monitorización, recuperación de errores, preparación de prompts para otros modelos, comparación de respuestas, filtrado, gestión de memoria/estado, decidir si escalar — es **NO EXISTE**: ni una línea de código conecta a Qwen con ninguna de esas funciones hoy. `nucleo/tareas.py` (la cola) es código puro determinista (una fórmula, no un modelo). `canal/vigilante.py` (el "monitor" de procesos) también es puro código, no usa ningún modelo. `nucleo/estado.py` igual.

### Trabajo desperdiciado por no usar más a Qwen

Con la evidencia de arriba: Qwen hace hoy en producción una fracción mínima de lo que ya sabe hacer con el código que existe (clasificar/resumir/pedir sirven, tal cual están, para: dar una primera lectura a una tarea nueva antes de metrla en la cola, resumir un archivo largo antes de pasarlo a Claude, dar una primera lectura de lo que responde Gemini/ChatGPT antes de decidir si hace falta escalar). El motor (`qwen.pedir/clasificar/resumir`) y el contrato (`proveedores.QwenProvider`) YA EXISTEN y están probados por separado — lo que falta no es "usar más a Qwen" en abstracto, es construir los puntos de conexión (Router + estado vivo) que hoy no existen.

### ¿Debería Qwen ser el worker/organizador permanente?

Con matices, basados en evidencia: **sí, como primera capa para trabajo texto-a-texto de bajo riesgo** (clasificar, resumir, redactar, dar una primera lectura) — motor por defecto **qwen2.5:7b** (el que ya ganó la medición real), reservando **qwen3:14b** solo cuando haga falta más criterio (aceptando su latencia de 40-80 s). **No** para nada que necesite herramientas, memoria de proyecto o coordinar varios pasos — eso hoy no existe en absoluto, ni en Qwen ni en ningún otro proveedor, y construirlo es la pieza 1 + Router de la Fase 4, no una cuestión de "usarlo más".

### Latencia / RAM / CPU / GPU (medido, no estimado)

- Latencia: tabla de arriba (`comparativa_modelos.json`), real y verificada dos veces (la medición del 11/09 y la nota de cabecera del propio `qwen.py`).
- Ollama corre en **CPU**, no en la GPU (la 890M la usa ComfyUI para imágenes, no hay CUDA — confirmado en fases anteriores y en `config.toml`).
- Medido ahora en vivo: el proceso `ollama.exe` en reposo (sin modelo cargado) ocupa **~23 MB de RAM** de working set. Ollama carga el modelo en memoria bajo demanda y lo libera tras inactividad (comportamiento estándar de Ollama; el timeout exacto no está fijado en este repo, así que no se puede dar un número propio).
- `config.toml` documenta una previsión de capacidad ("con 32 GB compartidos, el 14B (~9 GB en q4) y ComfyUI (~7 GB) caben a la vez") — es una previsión razonada, **no una medición en vivo bajo carga simultánea real**.

---

## B. REPARTO ENTRE IAS

Esto es política, no código — pero se apoya en dos hechos técnicos reales que limitan qué reparto es viable:

1. **Gemini/ChatGPT no pueden ser una "primera capa" de volumen alto.** El propio `extremidades/navegador.py` lo dice en su docstring: "Volumen bajo, con pausas, nunca en bucle desatendido" — es una regla de diseño para no arriesgar la cuenta (`nexoclaude@sepio.net`), no solo una preferencia. Cualquier política que mande mucho volumen a Gemini/ChatGPT contradice el propio código que ya existe.
2. **Claude vía `ClaudeProvider` no es "una llamada más": dispara un turno de Rutina completo** (`proveedores.py`, docstring de `ClaudeProvider`), con acceso a todas las herramientas de Nexo, y el resultado no vuelve en la misma llamada. No sirve para "resolver una subtarea pequeña" sin más — es una unidad de trabajo grande.

Con eso, la política que propongo (consistente con el diseño de Router de la Fase 4, sin cambiarlo, solo confirmándolo con evidencia):

- **LOCAL (Qwen) primero**, siempre que la tarea sea texto-a-texto de bajo riesgo: clasificar, resumir, redactar, dar una primera lectura, comparar dos textos.
- **Escalar a Gemini/ChatGPT** cuando la tarea necesite razonamiento con web/conocimiento actualizado, o cuando Qwen ya lo intentó y no hay forma de confiar en el resultado (hoy no hay ninguna medida de confianza — construirla es trabajo futuro, no existe).
- **Reservar Claude** para arquitectura, coding no trivial, verificación final de algo importante, o cuando Gemini/ChatGPT fallan o no alcanzan.
- Regla explícita: "usar el recurso más barato que sea suficientemente bueno, nunca el más barato al precio que sea" — ya diseñada en `FASE4_E_ROUTER_V3.md`. Esta auditoría no la cambia, solo confirma con evidencia real por qué Gemini/ChatGPT no pueden sustituir a Qwen como primera capa (limitación de volumen, no de calidad).

---

## C. DELEGACIÓN REAL

Tu lista de 12 pasos, contra el código real:

| # | Paso | Estado |
|---|---|---|
| 1 | Recibir una petición | **HECHO Y TESTEADO** (`canal/bot.py` recibe Telegram; `nucleo/tareas.py` recibe altas) |
| 2 | Analizarla | Parcial: **HECHO Y TESTEADO** solo para triaje de mensajes sueltos; NO EXISTE análisis de "qué proveedor conviene" |
| 3 | Decidir qué IA es adecuada | **NO EXISTE** (grep confirma: ninguna clase/función `Router`/`enrutar`/`decidir_proveedor` en todo el repo) |
| 4 | Enviarle una tarea | **HECHO Y TESTEADO por separado**, cada proveedor (`prueba_proveedores_vivo.py`, log real `prueba_proveedores_20260912_152236.log`) |
| 5 | Recibir el resultado | **HECHO Y TESTEADO por separado**, mismo test |
| 6 | Pasarlo a otra IA | **NO EXISTE** — ningún código encadena la salida de un proveedor como entrada de otro |
| 7 | Combinar resultados | **NO EXISTE** |
| 8 | Pedir una segunda opinión | **NO EXISTE** (grep de `segunda_opinion`/`comparar_respuestas`/`confianza`: cero resultados en todo el repo) |
| 9 | Verificar | **NO EXISTE** |
| 10 | Continuar con el siguiente paso | **NO EXISTE** — no hay concepto de "paso" ni máquina de estados de ejecución en ningún sitio |
| 11 | Cambiar de proveedor si falla | **DISEÑADO, no construido**: `Resultado.estado` (OK/NOT_AVAILABLE/BLOCKED/ERROR) es exactamente la información que un fallback necesitaría leer, y ya existe — pero nada la lee para decidir un cambio de proveedor |
| 12 | Escalar a Claude solo cuando haga falta | **NO EXISTE** como "escalar una subtarea": `ClaudeProvider.enviar()` pide un turno de Rutina entero, no una respuesta puntual |

**Hallazgo más importante de esta sección, con evidencia:** `proveedores.py` (T046, "cerrada") **solo lo importan tres scripts** — `consulta_fase3.py`, `consulta_fase3_relleno.py`, `demo_en_vivo.py` — y su propio test (`prueba_proveedores_vivo.py`). Grep confirmado: `canal/bot.py` y `nucleo/tareas.py` **nunca** importan `proveedores.py`. Es decir: **"tenemos proveedores conectados" es cierto y probado; "Nexo puede delegar trabajo automáticamente" es falso** — no hay ningún punto de producción que decida y dispare un proveedor por su cuenta.

**Cuánto falta para que Qwen actúe como coordinador práctico:** las dos piezas de ladrillo ya existen y están probadas (`QwenProvider`/`clasificar()` para decidir, `proveedores.py` para disparar) — falta la argamasa: un Router mínimo (aunque sea el propio Qwen clasificando "dificultad/riesgo" con un prompt) y un estado vivo donde registrar qué se intentó, con qué resultado, para poder encadenar y no perder el hilo si algo falla a mitad. Eso es exactamente la pieza 1 + el Router de la Fase 4 — este hallazgo no cambia su orden, pero sí confirma que gran parte del trabajo será "conectar lo que ya existe", no construir desde cero.

---

## D. CONTROL DEL PC

Comprobado con `pip list` real sobre el entorno del proyecto (`.venv` de `agente`, no el de ComfyUI, que es un entorno Python **separado** con sus propias dependencias — torch/pillow etc. de generación de imágenes viven ahí, no aquí):

**Instalado: solo `playwright` (1.62.0).** Nada de `pywinauto`, `pyautogui`, `uiautomation`, `opencv`, ni ninguna librería de automatización de escritorio o visión.

| Capacidad | Estado |
|---|---|
| Navegador (Playwright/CDP) | **REAL Y TESTEADO** — `extremidades/navegador.py`, verificado en vivo con Gemini y ChatGPT (T043/T045) |
| DOM (leer texto de la página) | **REAL Y TESTEADO** — `inner_text`, con lógica de extracción de respuesta ya depurada dos veces |
| Click / escribir | **REAL Y TESTEADO** — `caja.click()`, `caja.fill()`, `caja.press("Enter")` |
| Pestañas | **REAL Y TESTEADO** — itera `contexto.pages`, crea una si no existe |
| Screenshots / lectura visual | **NO EXISTE** — ninguna llamada a `.screenshot()` en `navegador.py`; toda la lectura es por DOM, no por imagen |
| Scroll explícito | **NO EXISTE** una función dedicada (no hace falta hoy: el patrón actual escribe y espera, no necesita desplazar la página) |
| Ventanas / apps de Windows | **NO EXISTE** — no hay ninguna librería ni código para controlar Excel, SolidWorks, o cualquier app nativa |
| UI Automation / accessibility | **NO EXISTE** — ni instalado ni diseñado con código, solo mencionado como "nivel 3" en el diseño de 5 niveles de la Fase 2 |
| Automatización de escritorio genérica | **NO EXISTE** |
| Visión (interpretar una captura) | **NO EXISTE** |
| Coordenadas | **NO EXISTE** |

**¿Hay una base reutilizable para "ver → decidir → actuar → comprobar" sobre cualquier aplicación?** No. La única base real es `navegador.py`, y es específica de Chrome vía CDP — no generaliza a aplicaciones Windows nativas. Para cubrir "cualquier aplicación del PC" hace falta construir un nivel nuevo (UI Automation / accessibility, ya identificado en la Fase 2 como nivel 3 de 5) que hoy **no tiene ni una línea de código ni una librería instalada** — es 100% DISEÑADO, no iniciado.

---

## E. EFICIENCIA GLOBAL

Con toda la evidencia de arriba, el cuadro real hoy es: Qwen resuelve una tarea (triaje), Gemini/ChatGPT responden si se les pregunta a mano o desde un script de prueba, Claude se dispara con un turno completo de Rutina — y **nada conecta estas tres cosas entre sí automáticamente**. No hay caché, no hay puntuación de confianza, no hay reutilización de respuestas, no hay detección de cuota más allá de lo que cada proveedor ya informa por su cuenta (`disponible()`/`estado()`).

Sobre el ejemplo conceptual que propones (Usuario→Qwen→resuelve o escala→Gemini/ChatGPT→si sigue siendo complejo→Claude→Qwen integra/documenta/verifica): es coherente con lo ya diseñado en las Fases 3-4 (LOCAL→EXTERNO→CLAUDE) y con la evidencia técnica de hoy (Qwen es rápido y gratis pero sin herramientas; Gemini/ChatGPT son gratis pero lentos y de volumen limitado; Claude es el recurso más caro y el único con acceso pleno a herramientas de Nexo). Lo confirmo como razonable **con un matiz importante**: el paso final ("Qwen integra/documenta/verifica") es, con diferencia, el que menos base tiene hoy — cero código de verificación cruzada existe. Si se quisiera probar el patrón a mano antes de construir el Router general, ese sería el primer tramo a construir, porque es el que more falta y el que menos arrastra de lo ya hecho.

Sobre las piezas que mencionas (caché, reutilización, memoria de resultados, perfiles dinámicos, detección de cuota, estimación de dificultad, puntuación de confianza, límites de pasos, timeouts, fallback, escalado automático, verificación adaptativa): **ninguna existe hoy en código** (confirmado por grep para las que tienen nombre buscable). Todas dependen de tener primero un sitio donde registrar qué se intentó y con qué resultado — es decir, dependen de la pieza 1 (estado vivo + registro de evidencia) de la Fase 4. No se pueden construir sueltas sin eso: un "caché de resultados" sin datos que lo alimenten es una función vacía.

---

## F. MULTIAGENTE LOCAL — revisión con evidencia

Reafirmo la Opción D (híbrida, sin framework) de la Fase 4, ahora con datos reales que la sostienen mejor de lo que se sabía entonces:

- Con solo 4 modelos instalados y uno de ellos (qwen3:4b) descartado por no servir para nada mecánico, **no hay hoy variedad real de modelos locales que justifique varios agentes especializados** — serían instancias distintas de los mismos 3 modelos utilizables, con el coste de coordinación añadido y sin ningún beneficio medido.
- Qwen no tiene acceso a herramientas hoy (sección A) — un "agente" sin herramientas es solo un modelo con un prompt distinto, que es exactamente la Opción A/D (roles sobre un mismo modelo), no la B (agentes especializados de verdad).
- Conclusión: nada de esta auditoría cambia la recomendación de la Fase 4. Un modelo reutilizado con roles distintos (clasificar / resumir / criterio), coordinado por código determinista, sigue siendo lo que la evidencia sostiene.

---

## G. BOOTSTRAP Y ROADMAP

**Bootstrap:** sin cambios respecto a la Fase 5 — sigue siendo una pieza independiente y de riesgo cero (solo documentación), que puede crearse cuando Damián lo pida, sin que esta auditoría añada ni quite nada a esa conclusión.

**¿Cambia el orden BOOTSTRAP → PIEZA 0 → PIEZA 1 → ROUTER → DELEGACIÓN → AUTONOMÍA?**

**No.** Esta auditoría no descubre ningún motivo técnico para adelantar Qwen/proveedores/delegación/PC control/eficiencia de contexto/observabilidad por delante de la seguridad (pieza 0) o del estado vivo (pieza 1). Al contrario: confirma que casi todo lo que haría falta para el Router y la delegación (Qwen.clasificar(), proveedores.py con sus 4 adaptadores, la distinción de estados OK/NOT_AVAILABLE/BLOCKED/ERROR) **ya existe y está probado por separado** — lo que falta es exactamente la pieza 1 (un sitio donde registrar qué se intentó) y el Router que lea esa información y decida. Es decir: el trabajo pendiente en el Router será mayoritariamente "conectar piezas ya construidas", no "construir desde cero" — un dato que reduce el riesgo estimado de esa pieza, sin cambiar su posición en el orden.

**Siguiente paso exacto, sin cambios:** PIEZA 0 (seguridad, `nucleo/permisos.py` / `manos/servidor_mcp.py`), pendiente de tu confirmación explícita en el momento — igual que se dejó en la Fase 5. Confirmado con evidencia de código en esta misma auditoría: `ejecutar_python()` en `manos/servidor_mcp.py` (líneas ~131-157) llama directamente a `subprocess.run(...)` sin pasar por `exigir()`/`nivel_de_ruta()`/`nivel_de_comando()` en ningún punto — es la única de las 8 tools MCP que lo hace así. Y `nivel_de_ruta()` en `nucleo/permisos.py` tiene, literalmente en el código, el comentario "Leer fuera del proyecto es inofensivo; escribir no" seguido de `return Nivel.AMBAR if escritura else Nivel.VERDE` — confirma REQ-070 exactamente como se documentó en fases anteriores, ahora con la línea de código exacta.
