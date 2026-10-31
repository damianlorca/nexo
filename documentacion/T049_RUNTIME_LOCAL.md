# T049 — Runtime/infraestructura local de Nexo: auditoría y recomendación

**Fecha:** 13/09/2026
**Autor:** Claude (Sonnet 5), a petición explícita de Damián
**Relación con otras tareas:** T049 responde "¿qué runtime/infraestructura debe usar Nexo?". **No** es T050 (qué modelos rinden mejor y para qué rol dentro de ese runtime) ni T051. Ninguna de las dos se ha tocado en este documento.
**Alcance respetado:** no se ha cambiado la instalación actual de Ollama, no se ha sustituido `qwen2.5:7b`, no se ha hecho ninguna migración ni cambio de producción. Todo lo que sigue es auditoría y recomendación, no implementación.

**Método:** evidencia real medida en este PC (Ollama 0.34.0, `config.toml`, `extremidades/qwen.py`) + 4 investigaciones independientes en paralelo (una por Ollama, una por LM Studio, una por llama.cpp/llama-server en AMD, una de barrido de alternativas), cada una con fuentes citadas. Las etiquetas de cada afirmación distinguen:

- **HECHO** — verificado en este PC, con este hardware, hoy.
- **MEDIDO** — hay una cifra concreta (propia o de un tercero en hardware equivalente/idéntico), no solo una afirmación cualitativa.
- **DOCUMENTADO** — está en la documentación oficial o en fuentes fiables (issues, changelog), pero no lo hemos ejecutado nosotros.
- **INFERIDO** — deducción razonable a partir de lo anterior, no confirmada directamente.
- **PENDIENTE DE MEDIR** — hipótesis relevante para la decisión que sigue sin datos y que T050 (o una tarea previa a T050) debería medir.

---

## 1. Contexto real de Nexo (para que la comparación no sea genérica)

- Windows 11, Ryzen AI 9 HX 370, 31GB RAM, iGPU Radeon 890M (RDNA3.5, gfx1150, ~3GB de VRAM compartida utilizable en la práctica). **HECHO.**
- Sin CUDA (no hay GPU NVIDIA). ROCm no soporta oficialmente el 890M en Windows — la allowlist de ROCm-Windows es de GPU discretas, no de iGPUs de esta serie. **DOCUMENTADO** (repositorio ROCm, issues de compatibilidad).
- `qwen2.5:7b` corre hoy en Ollama 0.34.0 a **100% CPU**, 0% GPU. **MEDIDO** en este PC (`ollama ps` tras una inferencia real con `ollama run`).
- Interés declarado de Damián: modelos más grandes (Qwen3 8B–27B), futuros modelos multi-rol, agentes locales de larga duración, tool calling/structured output, control programático desde Python, control determinista del modelo, concurrencia, observabilidad, recuperación ante fallos, cambio dinámico de modelo, trabajo continuo LOCAL-FIRST.
- `config.toml` ya prevé una arquitectura de **fallback dual**: Ollama como `url` principal, LM Studio como `url_reserva`, con sondeo automático (timeout 5s) en `extremidades/qwen.py`. Es decir: la idea de "más de una pieza" ya estaba en el diseño antes de que se planteara T049. **HECHO** (código leído).
- `extremidades/qwen.py` hoy: cliente OpenAI-compatible sin uso de `tools`/`response_format` (no hay tool calling ni structured output activos todavía, aunque el backend los soportaría), sin concurrencia (`lote()` es secuencial), con lógica propia para el problema medido de que qwen3 puede agotar el presupuesto de tokens razonando y devolver vacío (`MINIMO_TOKENS`, reintento con `TECHO_TOKENS`). **HECHO** (código leído).

## 2. Candidatos evaluados

| Candidato | Qué es | Por qué está en la lista |
|---|---|---|
| **Ollama** (actual) | Runtime todo-en-uno sobre una instantánea propia de `llama.cpp`/GGML + motor multimodal propio | Es lo que usamos hoy; punto de partida obligado |
| **LM Studio** | Runtime todo-en-uno con GUI, ya configurado como reserva | Ya está en `config.toml`, coste marginal cero de mantenerlo |
| **llama.cpp / `llama-server`** | El motor de inferencia en sí, usado directamente sin envoltorio | Candidato fuerte por evidencia de rendimiento real en este chip exacto |
| **AMD Lemonade** | Runtime propio de AMD para la serie Ryzen AI 300/400/Max 300, con soporte Hybrid NPU+iGPU | Hallazgo nuevo de esta investigación — único candidato que puede tocar la NPU, no solo la iGPU |

**Descartados en el barrido, con motivo (DOCUMENTADO, no requieren tabla completa):**
- **vLLM** — sin soporte real de Windows/AMD para este tipo de hardware; pensado para GPU NVIDIA de servidor.
- **LocalAI** — Docker/Linux-first; añadiría una capa de virtualización innecesaria en Windows nativo.
- **text-generation-webui** y **KoboldCpp** — viables técnicamente (ambos pueden envolver llama.cpp), pero ninguna investigación encontró una ventaja concreta sobre usar `llama-server` directamente para el caso de Nexo (agente programático, no interfaz de chat manual). Quedan como opción "plausible pero sin motivo para preferirla" — no se profundiza más porque no cambiarían la recomendación.
- **GAIA** (AMD) — posible proyecto relacionado o predecesor de Lemonade; su estado exacto frente a Lemonade queda **PENDIENTE DE MEDIR** si en algún momento Lemonade entra en juego de verdad.

## 3. Matriz de evaluación (22 criterios pedidos + 1 añadido)

Leyenda rápida: 🟢 punto fuerte · 🟡 aceptable/mixto · 🔴 punto débil · ⚪ sin datos suficientes

| # | Criterio | Ollama | LM Studio | llama.cpp/`llama-server` | AMD Lemonade |
|---|---|---|---|---|---|
| 1 | Estabilidad/madurez | 🟢 producto establecido, usado en producción ampliamente. MEDIDO en este PC (proceso estable durante la sesión) | 🟡 el modo headless (`llmster`, desde v0.4.0, ene-2026) es reciente; issues documentados de fugas de memoria en uso prolongado desatendido, incluida una específica del modo headless. DOCUMENTADO | 🟢 como motor es el más maduro de todos (es la base de casi todo lo demás); como *servidor* gestionado a mano, la madurez operativa la pone Nexo. DOCUMENTADO/INFERIDO | 🔴 proyecto activo pero joven (desarrollo activo hasta ago-2026), sin historial de uso en agentes de larga duración. INFERIDO |
| 2 | Integración Windows | 🟢 instalador nativo, servicio de Windows. HECHO (ya instalado y en uso) | 🟢 instalador nativo, pero el modo headless no sobrevive logout/reinicio sin herramientas de terceros (NSSM, Task Scheduler). DOCUMENTADO | 🟡 binario nativo, pero sin instalador — hay que gestionarlo como proceso propio (Task Scheduler/NSSM) igual que LM Studio headless. INFERIDO | 🟢 instalador MSI nativo para Windows, pensado explícitamente para esta serie de chips. DOCUMENTADO |
| 3 | Compatibilidad hardware AMD | 🟡 corre, pero hoy en este equipo va 100% CPU. MEDIDO | 🟡 mismo techo de memoria de iGPU compartida en Windows que cualquier herramienta basada en llama.cpp (~3.5GB). DOCUMENTADO | 🟢 mejor evidencia de aprovechamiento real de la iGPU vía Vulkan en este chip exacto. MEDIDO (benchmark de terceros, mismo hardware) | 🟢 diseñado específicamente para esta familia de chips (Hybrid NPU+iGPU). DOCUMENTADO |
| 4 | Backends (DirectML/ROCm/Vulkan) | 🟡 backend Vulkan experimental existe (`OLLAMA_VULKAN=1` + `OLLAMA_IGPU_ENABLE=1`), pero no probado en este PC; hay evidencia contradictoria (un caso de GPU forzada MÁS LENTA que CPU en chip similar). DOCUMENTADO, efecto real PENDIENTE DE MEDIR | 🟡 mismos backends de fondo que Ollama (llama.cpp), sin control fino expuesto al usuario. INFERIDO | 🟢 acceso directo a Vulkan (y a cualquier backend que soporte llama.cpp) sin intermediarios ni flags experimentales de un tercero. MEDIDO en benchmark externo | 🟢 usa el *execution provider* híbrido de ONNX Runtime GenAI de AMD para la NPU, además de rutas de GPU. DOCUMENTADO |
| 5 | Instalación/mantenimiento | 🟢 ya instalado, cero coste adicional. HECHO | 🟢 ya instalado como reserva, cero coste adicional. HECHO | 🔴 haríamos nosotros el empaquetado/actualización/arranque como servicio — coste real de mantenimiento que hoy no pagamos. INFERIDO | 🟡 instalador simple, pero es una pieza nueva a mantener y sin trayectoria larga. INFERIDO |
| 6 | Gestión de modelos (descarga/catálogo/versión) | 🟢 `ollama pull`/registro propio, maduro. HECHO/DOCUMENTADO | 🟢 catálogo con GUI, cómodo para pruebas manuales. DOCUMENTADO | 🔴 sin gestor propio; parcialmente mitigado con la bandera `-hf` (tira directo de Hugging Face) pero sin versión/catálogo local real. DOCUMENTADO | 🟡 gestor propio más limitado, catálogo de modelos verificados para su Hybrid mode más pequeño que el de Ollama. DOCUMENTADO |
| 7 | Consumo RAM/VRAM | 🟡 hoy todo en RAM (CPU-only). MEDIDO | 🟡 mismo perfil que Ollama al compartir motor de fondo. INFERIDO | 🟡 igual que los anteriores en CPU; con Vulkan, reparte en la VRAM compartida de la iGPU (techo ~3GB). DOCUMENTADO | 🟢 en teoría el único que puede descargar trabajo a la NPU sin competir por la misma VRAM de iGPU. INFERIDO, PENDIENTE DE MEDIR |
| 8 | Rendimiento | 🔴 100% CPU medido hoy con `qwen2.5:7b`; posible brecha frente a llama.cpp upstream porque Ollama vendoriza una instantánea de llama.cpp que puede ir meses por detrás (issue de GitHub documentado, ~56% de brecha medida en un chip hermano). MEDIDO (lo malo) + DOCUMENTADO (la causa) | 🔴 mismo motor de fondo que Ollama; sin motivo para esperar mejor rendimiento salvo que empaqueten una versión de llama.cpp más reciente. INFERIDO | 🟢 benchmark real en el **mismo chip exacto** (Ryzen AI 9 HX 370 + Radeon 890M) con Vulkan: ~51.7 tok/s prompt / ~19.1 tok/s generación en un modelo de 30B. MEDIDO (fuente externa, hardware idéntico) | ⚪ sin benchmark encontrado en este chip concreto todavía. PENDIENTE DE MEDIR |
| 9 | Concurrencia | 🟢 soporta peticiones concurrentes, bien documentado y maduro. DOCUMENTADO | 🟡 soporte de concurrencia añadido en v0.4.0 (reciente), menos probado en producción que el de Ollama. DOCUMENTADO | 🟢 concurrencia nativa vía `--parallel`/`--cont-batching`, con control fino directo. DOCUMENTADO | ⚪ sin documentación clara de concurrencia bajo carga. PENDIENTE DE MEDIR |
| 10 | API local | 🟢 API OpenAI-compatible, ya integrada en `extremidades/qwen.py`. HECHO | 🟢 API OpenAI-compatible, ya integrada como reserva. HECHO | 🟢 API OpenAI-compatible también, mismo patrón de integración que los anteriores. DOCUMENTADO | 🟢 API OpenAI-compatible. DOCUMENTADO |
| 11 | Streaming | 🟢 soportado. DOCUMENTADO | 🟢 soportado. DOCUMENTADO | 🟢 soportado. DOCUMENTADO | 🟡 soportado según documentación, sin verificación independiente. DOCUMENTADO |
| 12 | Structured output | 🟢 soportado (`format: json`/JSON-schema), maduro. DOCUMENTADO, no usado hoy en `qwen.py` | 🟢 soportado. DOCUMENTADO, no usado hoy | 🟢 vía gramáticas GBNF + JSON-schema — el control más fino de los cuatro. DOCUMENTADO | 🟡 soporte declarado, menos documentado en profundidad. DOCUMENTADO |
| 13 | Tool calling | 🟢 soportado y maduro. DOCUMENTADO, no usado hoy | 🟢 soportado. DOCUMENTADO, no usado hoy | 🟢 soportado a nivel de motor (vía la misma vía que Ollama expone). DOCUMENTADO | 🟡 soporte declarado, sin ejemplos de uso extenso encontrados. DOCUMENTADO |
| 14 | Multimodalidad | 🟢 motor multimodal propio, bien integrado. DOCUMENTADO | 🟡 soporte multimodal más limitado/desigual entre modelos. DOCUMENTADO | 🟡 depende del soporte multimodal de llama.cpp puro, más manual que el de Ollama. DOCUMENTADO | ⚪ no confirmado en la investigación. PENDIENTE DE MEDIR |
| 15 | Agentes de larga duración | 🟡 estable como servicio, pero sin datos propios de uso desatendido 24/7 con este hardware. INFERIDO | 🔴 issues documentados de fugas de memoria/inestabilidad específicamente en uso prolongado desatendido. DOCUMENTADO | 🟡 al ser un proceso simple y controlado por Nexo, la fiabilidad a largo plazo depende de que Nexo mismo implemente reinicio/salud — no hay nada "gratis" aquí ni en contra. INFERIDO | ⚪ sin trayectoria suficiente para opinar. PENDIENTE DE MEDIR |
| 16 | Automatización Python | 🟢 cliente `openai` estándar, ya en uso (`extremidades/qwen.py`). HECHO | 🟢 mismo cliente, ya en uso como reserva. HECHO | 🟢 mismo cliente, sin diferencia real de integración. INFERIDO | 🟡 cliente OpenAI-compatible según documentación, sin probarlo desde Python en este proyecto. DOCUMENTADO |
| 17 | Observabilidad/control | 🟡 logs de servicio, sin métricas finas expuestas por defecto. DOCUMENTADO | 🟡 similar a Ollama. DOCUMENTADO | 🟢 al ser un proceso controlado directamente por Nexo, toda su salida (stdout, métricas de `--metrics`) es más fácil de capturar sin intermediarios. INFERIDO | ⚪ sin datos. PENDIENTE DE MEDIR |
| 18 | Manejo de errores/recuperación | 🟡 reinicio de servicio de Windows como red de seguridad básica. DOCUMENTADO | 🔴 el propio modo headless tiene un issue abierto de inestabilidad; sin red de reinicio automática nativa. DOCUMENTADO | 🔴 la recuperación (reinicio si cae, healthcheck) la construiría Nexo desde cero — hoy ese código no existe. HECHO (ausencia confirmada al leer el código actual) | ⚪ sin datos. PENDIENTE DE MEDIR |
| 19 | Facilidad de ejecutar distintos modelos/perfiles | 🟢 cambio de modelo con `ollama run <modelo>`, ya usado en la práctica. HECHO | 🟢 cambio de modelo vía GUI o API, cómodo para pruebas manuales. DOCUMENTADO | 🟡 hay que apuntar `llama-server` a otro `.gguf` y reiniciar el proceso (o gestionar varios procesos) — más fricción que un simple `pull`+`run`. INFERIDO | 🟡 catálogo de perfiles verificados, pero más pequeño y menos flexible que el de Ollama. DOCUMENTADO |
| 20 | Facilidad de integración en Nexo | 🟢 ya integrado, cero coste. HECHO | 🟢 ya integrado como reserva, cero coste. HECHO | 🟡 mismo contrato OpenAI-compatible que ya maneja `qwen.py`; el coste real está en construir la gestión de proceso/modelos alrededor, no en el cliente. INFERIDO | 🔴 requeriría una integración nueva de principio a fin, sin ningún código previo en el repo. HECHO (ausencia confirmada) |
| 21 | Coste/licencia | 🟢 MIT, gratis. DOCUMENTADO | 🟢 gratis para uso personal y comercial. DOCUMENTADO | 🟢 MIT, gratis. DOCUMENTADO | 🟢 gratis (AMD). DOCUMENTADO |
| 22 | Ecosistema/mantenimiento futuro | 🟢 comunidad muy grande, ritmo de releases alto. DOCUMENTADO | 🟡 comunidad activa pero más pequeña; roadmap ligado a la empresa detrás del producto. DOCUMENTADO | 🟢 upstream de referencia del propio ecosistema (Ollama y LM Studio se apoyan en él); su ritmo de novedades es, de hecho, más rápido que el de sus envoltorios. DOCUMENTADO | 🟡 respaldado por AMD, pero es una apuesta de nicho (una sola familia de chips); su continuidad depende de la prioridad que AMD le siga dando. INFERIDO |
| 23 *(añadido)* | Aprovechamiento de NPU dedicada (no solo iGPU) | 🔴 sin soporte de NPU. DOCUMENTADO | 🔴 sin soporte de NPU. DOCUMENTADO | 🔴 sin soporte de NPU (Vulkan solo habla con la iGPU). DOCUMENTADO | 🟢 único candidato con una vía documentada a la NPU del Ryzen AI 9 HX 370. DOCUMENTADO |

*Criterio 23 se añade porque, a diferencia de los otros, la NPU de este chip es silicio dedicado hoy completamente inutilizado (Ollama/LM Studio/llama.cpp solo hablan con CPU/iGPU) — es la única palanca de rendimiento/eficiencia energética que ningún candidato basado en llama.cpp puede tocar, y por tanto puede cambiar la decisión a medio plazo si Lemonade madura.*

## 4. ¿Un único runtime, principal+complementario, o combinación por capas?

Separando por capa, como pidió Damián, la imagen es más clara que si se busca "un ganador único":

- **Capa de motor de inferencia** (quién ejecuta de verdad los tensores): Ollama, LM Studio y `llama-server` directo comparten en el fondo el mismo motor (llama.cpp/GGML) — la diferencia real está en **qué versión** de ese motor corre cada uno y **qué tan directo** es el acceso a los flags de rendimiento (Vulkan, `--parallel`, gramáticas). Aquí `llama-server` directo gana con evidencia medida (MEDIDO, benchmark en el mismo chip). Lemonade es la excepción: no comparte ese motor para su ruta NPU, usa el stack propio de AMD (ONNX Runtime GenAI).
- **Capa de gestión de modelos** (descargar, versionar, catálogo): Ollama gana con claridad — es lo más maduro y ya está integrado. `llama-server` no tiene nada equivalente de fábrica.
- **Capa de GUI** (inspección manual, pruebas rápidas): LM Studio es el único pensado para esto — su valor no es ser el runtime de producción, es ser la herramienta de mano cuando Damián quiere probar un modelo nuevo o mirar qué está pasando sin escribir código.
- **Capa de API/programación**: las tres ofrecen el mismo contrato OpenAI-compatible, así que el cliente Python (`extremidades/qwen.py`) no tendría que cambiar de forma sustancial para apuntar a cualquiera de ellas.
- **Capa de ejecución de agentes** (concurrencia real, recuperación, observabilidad fina, control determinista): es donde más difieren. Ollama y LM Studio "regalan" un runtime gestionado a cambio de menos control fino; `llama-server` da el control fino a cambio de que Nexo construya la parte operativa (reinicio, salud, logs) que hoy no existe en el repo.

**Conclusión de esta sección:** la pregunta "¿uno o varios?" tiene una respuesta clara — **no hay un único candidato que gane en las cinco capas a la vez**, así que la arquitectura correcta es de **capas separadas con más de una pieza**, no un reemplazo de Ollama por otra cosa igual de monolítica.

## 5. Recomendación

### 5.1 Opción principal recomendada

**Mantener Ollama como runtime de producción hoy** (importancia y urgencia: 3/2, según T049 en `tareas.json`). No hay ninguna razón de estabilidad, integración o coste para moverse de él ahora mismo — todo lo que Nexo usa ya funciona sobre él (HECHO). El problema real detectado no es "Ollama está mal", es "Ollama en este PC concreto no está usando la iGPU" (MEDIDO), lo cual solo importa de verdad cuando entren en juego los modelos más grandes que Damián quiere probar (Qwen3 8B-27B) — con `qwen2.5:7b` en CPU el rendimiento ya es aceptable hoy.

### 5.2 Posibles complementos

1. **LM Studio se mantiene exactamente como está** — reserva automática ya cableada en `config.toml`, y herramienta manual de inspección/prueba cuando Damián quiera mirar un modelo a mano. No compite con Ollama, lo complementa.
2. **`llama-server` directo, como candidato de "capa de ejecución avanzada"** para el escalón de rendimiento que Ollama no puede dar hoy en este hardware — pendiente de la medición que se describe en 5.7. No se propone para sustituir a Ollama de forma completa, sino como una vía adicional que Nexo podría invocar para cargas concretas (p. ej. un modelo grande en modo batch nocturno) si el hueco de rendimiento se confirma.
3. **AMD Lemonade, como línea de exploración a más largo plazo**, no como decisión ya tomada — es el único camino documentado hacia la NPU de este chip, lo cual encaja directamente con el objetivo de LOCAL-FIRST CONTINUOUS WORK (más trabajo útil por vatio, sin competir por la misma iGPU). Su madurez para agentes de larga duración, concurrencia y recuperación de errores está hoy indocumentada — no se recomienda tocarlo en producción hasta tener datos propios.

### 5.3 Arquitectura concreta propuesta (para cuando se implemente, no ahora)

```
Nexo
 ├─ Gestión de modelos / catálogo  → Ollama (sigue siendo el "pull" y el registro local)
 ├─ Runtime de producción por defecto → Ollama (API OpenAI-compatible ya integrada)
 ├─ Reserva/fallback → LM Studio (ya cableado, sin cambios)
 ├─ Inspección manual → LM Studio (GUI)
 └─ Escalón de alto rendimiento (opcional, solo si T050/una medición previa lo confirma)
     → llama-server directo, gestionado como proceso propio por Nexo
       (con su propio healthcheck/reinicio, hoy inexistente)
```

Lemonade queda fuera de este diagrama a propósito: es una línea de investigación futura, no una pieza de la arquitectura de hoy.

### 5.4 Principales ventajas de esta recomendación

- Cero riesgo inmediato: no se toca nada que funcione hoy.
- Cierra la única debilidad medida (100% CPU) con una ruta de validación barata (activar el flag Vulkan experimental de Ollama primero, antes de saltar a algo más costoso como gestionar `llama-server` a mano).
- Respeta la separación de capas que pidió Damián en vez de forzar un ganador único.
- Deja una vía real hacia la NPU (Lemonade) sin comprometerse a ella antes de tener datos.

### 5.5 Principales inconvenientes/riesgos

- Si se añade `llama-server` como escalón adicional, Nexo pasa a ser responsable de una pieza de infraestructura (reinicio, salud, logs) que hoy delega por completo en Ollama/LM Studio — coste de mantenimiento real, no solo de implementación inicial.
- El backend Vulkan experimental de Ollama tiene evidencia contradictoria (un caso documentado de GPU forzada más lenta que CPU en un chip similar) — activar flags experimentales sin medir podría empeorar el rendimiento en vez de mejorarlo.
- AMD Lemonade es una apuesta de nicho (una sola familia de chips); si AMD baja la prioridad del proyecto, Nexo se quedaría con una pieza sin mantenimiento activo.
- Ninguna de las cifras de rendimiento decisivas (Vulkan en Ollama en este PC concreto, comportamiento de Lemonade en este PC concreto) se ha medido todavía en este equipo — todo lo que apunta a "cambiar algo" se apoya en benchmarks de terceros en hardware equivalente o idéntico, no en mediciones propias.

### 5.6 Hipótesis que quedan sin demostrar (en este PC, hoy)

- Que activar `OLLAMA_VULKAN=1` + `OLLAMA_IGPU_ENABLE=1` en la instalación actual de Ollama mejora de verdad el rendimiento en este chip concreto (hay evidencia a favor y en contra en chips similares, ninguna en este exacto).
- Que la brecha de rendimiento de `llama-server` sobre Ollama-CPU (que sí está medida en este chip para Vulkan) se mantiene igual de amplia si se compara contra un Ollama-Vulkan ya activado (en vez de contra Ollama-CPU).
- Que AMD Lemonade es capaz de sostener un agente de larga duración, con recuperación de errores y observabilidad suficientes, al nivel que Nexo necesita — no hay ningún dato propio ni de terceros sobre esto todavía.
- Que el techo de memoria de iGPU compartida (~3GB) no se convierte en el cuello de botella real en cuanto se pruebe un modelo de la familia Qwen3 27B, sea cual sea el runtime.

### 5.7 Qué debe medir T050 antes de dar esta elección por validada

1. Tok/s real de `qwen2.5:7b` (y de al menos un modelo mayor, p. ej. Qwen3 8B) en este PC con Ollama-CPU (línea base ya conocida) vs. Ollama con el flag Vulkan activado — sin tocar producción, en un entorno aislado, igual que se hizo con la prueba de Pieza 1.
2. Si el punto 1 no cierra el hueco frente al benchmark externo de `llama-server`+Vulkan, medir `llama-server` directo en este PC con el mismo modelo, para confirmar (o descartar) que merece la pena el coste operativo de gestionarlo a mano.
3. Uso real de RAM/VRAM en este PC con un modelo de la franja 8B-27B, en cada backend probado, para saber si el techo de ~3GB de iGPU compartida es o no el límite real antes de llegar al de RAM del sistema.
4. Una prueba mínima, aislada, de AMD Lemonade en este PC (instalación + una inferencia simple) solo para confirmar que arranca y reconoce la NPU del Ryzen AI 9 HX 370 — sin comprometerse a nada más que eso en esta fase.
5. Comportamiento de concurrencia real (2-3 peticiones simultáneas) en Ollama hoy, como línea base, antes de decidir si hace falta migrar algo por el criterio de concurrencia.

---

## Fuentes

- `ollama ps` / `ollama run qwen2.5:7b` — medición propia en este PC, 13/09/2026.
- `config.toml`, `extremidades/qwen.py` — código propio del repo, leído íntegro el 13/09/2026.
- Documentación oficial de Ollama (backends, API, changelog de versiones).
- Documentación oficial de LM Studio / `llmster` (modo headless, changelog v0.4.0) e issues públicos de fugas de memoria en uso prolongado.
- Documentación de `llama.cpp`/`llama-server` (flags de servidor, GBNF, `--parallel`/`--cont-batching`) e issue de GitHub sobre la brecha de rendimiento entre la instantánea vendorizada por Ollama y el upstream de llama.cpp en AMD/Vulkan (~56% medido en un chip hermano).
- Benchmark de terceros en Ryzen AI 9 HX 370 + Radeon 890M con `llama-server`+Vulkan (~51.7 tok/s prompt / ~19.1 tok/s generación, modelo de 30B).
- Documentación pública de AMD Lemonade (instalador, modos Hybrid NPU+iGPU, API OpenAI-compatible, actividad del repositorio hasta agosto 2026).
- Barrido de vLLM, LocalAI, text-generation-webui, KoboldCpp, GAIA — documentación pública de cada proyecto, usada solo para descartar o dejar constancia, sin profundizar más de lo necesario para justificar la decisión.
