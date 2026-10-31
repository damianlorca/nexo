# G. Síntesis multi-IA — 5 casos especiales (Fase 3 acotada, Fase 4)

Comparación de las 4 fuentes: `F_ANALISIS_CLAUDE.md`, `C_RESULTADOS_QWEN.md`, `D_RESULTADOS_GEMINI.md`, `E_RESULTADOS_CHATGPT.md`. Formato pedido por Damián: pregunta / estado-contexto enviado / respuesta de cada IA / coincidencias / discrepancias / conclusión técnica / decisión pendiente.

**Nota metodológica importante, aplicable a todo este documento**: la primera tanda de consultas a Gemini/ChatGPT (5 preguntas seguidas, 8s de pausa) reveló un fallo real de `extremidades/navegador.py`: en una conversación con varias preguntas encadenadas, la extracción capturaba una respuesta antes de que terminara de generarse, y la lectura de la siguiente pregunta arrastraba el final de la respuesta anterior. Se reconstruyeron las respuestas de A/B/C por contenido real y se relanzó una segunda tanda con 60-120s de margen para D y E, que sí se capturaron limpiamente — confirmando que la causa era el margen insuficiente entre preguntas, no un fallo aleatorio del sitio. Este hallazgo en sí mismo es evidencia nueva de esta auditoría — ver `12_NEXO_PROVIDER_MANUAL.md` y `J_ROADMAP_PRIORIZADO.md` P2.1.

---

## Caso A — Despertar de Claude bajo demanda

**Pregunta enviada** (resumen): dado que `/ahora` (Routines Fire API) ya funciona pero no da la respuesta en la misma llamada ni soporta paralelismo real, ¿hay forma oficial de reducir la latencia o permitir varios turnos en paralelo sin pisar memoria?

- **CLAUDE_ASSESSMENT**: no perseguir paralelismo real; encolar (un turno a la vez) es más barato y seguro que resolver concurrencia de verdad para un beneficio que Damián no ha pedido.
- **QWEN_ASSESSMENT**: no hay vía oficial; advierte contra buscar soluciones de terceros no documentadas que puedan violar las restricciones ya fijadas.
- **GEMINI_ASSESSMENT**: no hay vía oficial; propone aislar estado por sesión (`estado_<session_id>.json`, distintos IDs de rutina) si algún día hiciera falta paralelismo, y delegar respuestas rápidas a un proceso local ligero en vez de a la Rutina.
- **CHATGPT_ASSESSMENT**: no asumir aislamiento entre llamadas `fire`; tratar la Rutina como recurso EXCLUSIVO; implementar una cola propia (`/ahora → job_id → dispatcher → un único fire → siguiente job`); para latencia en segundos, Routines no es la capa adecuada.

**Coincidencias**: las 4 fuentes coinciden en que NO existe una vía oficial para reducir la latencia o paralelizar sin riesgo, y las 4 (de forma independiente) convergen en la misma idea de fondo: **una cola de un solo trabajo a la vez**, no paralelismo real. Coincidencia fuerte entre análisis hechos por separado.

**Discrepancias**: Gemini es la única que propone activamente aislar estado por sesión como camino hacia paralelismo futuro; las otras tres recomiendan no perseguirlo todavía.

**Conclusión técnica**: implementar una cola simple de un solo turno de Claude a la vez (ver `J_ROADMAP_PRIORIZADO.md` P1.3). No intentar paralelismo real por ahora.

**Decisión pendiente de Damián**: ninguna urgente; confirmar que "un turno a la vez, en cola" es aceptable (no se ha pedido paralelismo explícitamente).

---

## Caso B — Detección de límites/disponibilidad de Claude

**Pregunta enviada**: sin API pública de cuota, ¿hay alguna señal indirecta razonable para aproximar cuánta cuota queda antes de disparar un turno?

- **CLAUDE_ASSESSMENT**: solo defendible registrar cada disparo y su resultado en `nucleo/uso.py`; cualquier intento de leer cabeceras no documentadas es frágil y de bajo valor frente al coste de mantenerlo.
- **QWEN_ASSESSMENT**: propone disparar rutinas de PRUEBA a intervalos regulares para mapear patrones de error — **la única de las 4 que propone gastar cuota activamente para medir cuánta cuota queda**, contraproducente dado el objetivo de minimizar el gasto.
- **GEMINI_ASSESSMENT**: inspeccionar cabeceras del disparo real (`x-ratelimit-remaining`, `x-ratelimit-reset`, `retry-after`) si existen; mapear el error FAILED; backoff en `nucleo/uso.py` con estado de "cuota agotada".
- **CHATGPT_ASSESSMENT**: registrar exhaustivamente cada disparo; ventanas deslizantes de 5h/semanal con 3 estados (DISPONIBLE/PROBABLEMENTE_AGOTADA/DESCONOCIDA); **advierte explícitamente contra depender de endpoints internos no documentados**. Objetivo realista: "detectar + aprender + retrasar", nunca certeza.

**Coincidencias**: Claude, Gemini y ChatGPT coinciden en instrumentar lo que YA se dispara (no generar tráfico nuevo) y tratarlo como aproximación, nunca certeza.

**Discrepancias**: Qwen es la única que propone gastar cuota activamente para medirla — descartado por las otras tres y por esta síntesis. Gemini es más optimista sobre la utilidad de las cabeceras HTTP; ChatGPT advierte de su fragilidad.

**Conclusión técnica**: extender `nucleo/uso.py` con un estado de "cuota probablemente agotada" derivado de los disparos reales, sin generar tráfico nuevo solo para medir.

**Decisión pendiente de Damián**: confirmar que "detectar + aprender + retrasar" (nunca detección preventiva perfecta) es un objetivo aceptable.

---

## Caso C — Model Router

**Pregunta enviada**: dado que el modelo/razonamiento dentro de una Rutina de Claude no se puede cambiar automáticamente, ¿cuál es el diseño mínimo de un Router que sí decida entre Qwen/Gemini/ChatGPT/disparar-Claude?

- **CLAUDE_ASSESSMENT**: función pura `elegir_proveedor(tarea) -> str`; reglas simples por tipo de necesidad, sin discutir el modelo interno de Claude.
- **QWEN_ASSESSMENT**: categorización + priorización + decisión por escalones; única en mencionar explícitamente que cualquier cambio de modelo de Claude debe llevar "siempre la aprobación de Damián".
- **GEMINI_ASSESSMENT**: árbol de reglas determinista por niveles (0 Qwen / 1 Gemini-ChatGPT con rate limiter / 2 Claude); aporta compensar la imposibilidad de cambiar el razonamiento inyectando una instrucción de concisión en el prompt.
- **CHATGPT_ASSESSMENT**: política por escalones con fallback automático; formulación más precisa del límite: el Router decide DISPARAR, nunca modelo/razonamiento — puede marcar `reasoning_required=high` y notificar a Damián; propone registrar cada decisión y empezar con un `PolicyRouter` en JSON/YAML.

**Coincidencias**: las 4 fuentes convergen, de forma independiente, en la MISMA estructura de niveles (Qwen→Gemini/ChatGPT→Claude) y las 4 aceptan sin discutirlo que el modelo/razonamiento dentro de Claude queda fuera del alcance automático del Router. Validación fuerte de que el diseño no es una ocurrencia aislada.

**Discrepancias**: ninguna de fondo; diferencias de énfasis (Gemini: instrucción de concisión; ChatGPT: registro de decisiones; Qwen: aprobación explícita de Damián).

**Conclusión técnica**: construir el Router en dos capas separadas: (1) decisión de PROVEEDOR, automatizable ya; (2) decisión de MODELO/RAZONAMIENTO dentro de Claude, sigue requiriendo a Damián. Adoptar la instrucción de concisión de Gemini como mitigación barata y el registro de decisiones de ChatGPT desde el primer día.

**Decisión pendiente de Damián**: confirmar el alcance de la primera versión (solo proveedor) — ver `M_DECISIONES_ARQUITECTONICAS_PENDIENTES.md` punto 3.

---

## Caso D — Comunicación entre IAs / protocolo

**Pregunta enviada**: usando solo archivos JSON con candado (como `canal/buzon.py`), ¿qué estructura mínima de mensaje y de cola bastaría para encadenar 2-3 proveedores de forma trazable, sin infraestructura nueva?

- **CLAUDE_ASSESSMENT**: carpeta `canal/entre_ias/`, un archivo por mensaje, mismo patrón que `canal/salida/`, con exactamente los campos de la especificación (sender/receiver/task_id/message_type/payload/context/priority/timestamp/status/result/error).
- **QWEN_ASSESSMENT**: archivos JSON con candado; reproduce literalmente los mismos 10 campos de la especificación; propone el orden concreto Qwen→Gemini→ChatGPT→Claude con cada uno leyendo/escribiendo su archivo.
- **GEMINI_ASSESSMENT**: `MensajePipeline` con `task_id, step_index, sender, receiver, status, timestamp, payload, context, error`; cola en `buzon_pipeline.json` con filelock y la secuencia de pasos predefinida (ej. `["qwen","gemini","claude"]`); espera obligatoria antes de cada paso hacia Gemini/ChatGPT integrada en el propio diseño.
- **CHATGPT_ASSESSMENT**: mensaje con `id, task_id, sender, receiver, type, priority, payload, context, created_at, status, result, error`; cola `cola.json` con file-lock y **claim atómico explícito** (para que dos procesos no ejecuten el mismo mensaje); resultados grandes referenciados aparte (`tareas/<task_id>/steps/NNN.json`); `MessageBus`/`Dispatcher` en `proveedores.py`; **`max_steps`, `max_retries`, `cooldown`, `chain_id`** incorporados desde el diseño.

**Coincidencias**: las 4 fuentes convergen, de forma independiente, en el MISMO patrón exacto (archivo JSON + candado, campos casi idénticos a los pedidos por la especificación maestra) — la coincidencia más fuerte de los 5 casos especiales. Ninguna propuso base de datos, servicio nuevo, ni nada fuera de lo que ya existe en el proyecto.

**Discrepancias**: de énfasis, no de fondo. ChatGPT es el único que insiste explícitamente en el "claim atómico" (evitar que dos procesos reclamen el mismo mensaje) y en límites de reintentos/pasos integrados desde el diseño inicial, no añadidos después. Gemini integra la pausa de rate-limit hacia Gemini/ChatGPT dentro del propio mecanismo de cola, en vez de como una regla externa.

**Conclusión técnica**: construir `canal/entre_ias/` (o el nombre que se prefiera) con la estructura de mensaje consolidada de las 4 fuentes: `id, task_id, step_index, sender, receiver, message_type, priority, payload, context, created_at, status, result, error`. Incluir desde el diseño inicial (no después): claim atómico vía candado (ya disponible en `nucleo/candado.py`), `max_retries`/`cooldown` para cualquier salto hacia Gemini/ChatGPT, y referencias a archivos aparte para payloads grandes en vez de incrustarlos.

**Decisión pendiente de Damián**: confirmar el formato exacto antes de construirlo — ver `M_DECISIONES_ARQUITECTONICAS_PENDIENTES.md` punto 4. Es una decisión de forma, no de si hacerlo: las 4 fuentes coinciden en que es viable y barato.

---

## Caso E — Autonomía completa

**Pregunta enviada**: con las piezas que ya existen (`estado.json::siguiente_turno`, `nucleo/tareas.py`, `canal/vigilante.py` siempre vivo), ¿qué diseño mínimo permitiría que el ciclo OBSERVAR→...→DOCUMENTAR sobreviva a que un turno de Claude concreto termine, sin construir un orquestador nuevo desde cero?

- **CLAUDE_ASSESSMENT**: primer paso pequeño y reversible — que `vigilante.py` AVISE por Telegram si hay algo pendiente en `siguiente_turno` sin tocar hace tiempo, sin actuar solo. Postura deliberadamente conservadora: "vigilar y avisar", no "vigilar y actuar".
- **QWEN_ASSESSMENT**: que `vigilante.py`, además de relanzar el bot, verifique `siguiente_turno`, ASIGNE tareas a Claude, monitoree su estado, pida autorización si hace falta, y registre el resultado — más ambicioso que Claude, propone que el vigilante actúe, no solo avise.
- **GEMINI_ASSESSMENT**: evolucionar `vigilante.py` a un "loop daemon" con máquina de estados (`fase_actual`: obs/plan/ejec/verif/corr/doc) en `nucleo/tareas.py`; delega fases mecánicas a Qwen/Gemini (ahorrando cuota); activa la Rutina de Claude solo para ejecutar con herramientas o tras fallo persistente; pausa y reprograma ante FAILED/cuota agotada sin perder la fase alcanzada; pausa el bucle ante `USER_DECISION_REQUIRED`.
- **CHATGPT_ASSESSMENT**: convertir `tareas.py`+`vigilante.py` en máquina de estados persistente (workflow `OBSERVAR→...→FINALIZAR`), con `next_action` reanudable en `estado.json`; principio explícito: **"Claude no debe poseer el estado del proceso: actúa como worker sustituible, el estado canónico vive en archivos de Nexo"**; `intentos+backoff+límite` para evitar bucles, con escalado a otra IA si falla repetidamente.

**Coincidencias**: las 4 coinciden en la pieza base (`vigilante.py` como proceso que ya vive siempre, ampliando `estado.json`/`tareas.py` con más estructura de fase/intento) y en que Claude nunca debe ser el único lugar donde vive el progreso de una tarea larga — el estado tiene que sobrevivir en archivos, no en la memoria de un turno.

**Discrepancia real y explícita**: **qué tan lejos debe llegar el vigilante por su cuenta.** Claude propone la versión más conservadora (solo avisar, nunca actuar ni asignar sin que un turno de Claude lo revise). Qwen, Gemini y ChatGPT proponen las tres, en distinto grado, que el vigilante DELEGUE y EJECUTE directamente en Qwen/Gemini para las fases mecánicas (planificar/verificar/corregir), reservando Claude solo para lo que necesita herramientas del sistema o ha fallado repetidamente. Esta es la discrepancia más importante de toda la Fase 3: 3 de 4 fuentes coinciden en ir más allá de "solo avisar", y solo Claude (el propio analista coordinador de esta auditoría) recomienda la vía más conservadora.

**Conclusión técnica**: dado que 3 de las 4 fuentes coinciden en un diseño más capaz, pero el riesgo de un vigilante que actúa solo es justo el tipo de automatismo que esta auditoría existe para frenar antes de construir, se recomienda una vía intermedia explícita, no la más conservadora ni la más ambiciosa tal cual: el vigilante puede delegar fases mecánicas de BAJO riesgo (planificar/verificar, usando Qwen/Gemini) sin pedir permiso, pero cualquier fase de EJECUCIÓN real sobre el sistema (tocar archivos, disparar una Rutina de Claude, algo irreversible) sigue exigiendo que se anote en `siguiente_turno` y avise, no que se dispare sola. Es decir: automatizar el "pensar/verificar" de bajo riesgo, mantener el "actuar" bajo el mismo criterio conservador que ya rige el resto del proyecto.

**Decisión pendiente de Damián**: cuál de las tres posturas prefiere como primer paso — la conservadora de Claude, la intermedia propuesta en esta síntesis, o ir directamente a lo que proponen Qwen/Gemini/ChatGPT. Ver `M_DECISIONES_ARQUITECTONICAS_PENDIENTES.md` punto 5.
