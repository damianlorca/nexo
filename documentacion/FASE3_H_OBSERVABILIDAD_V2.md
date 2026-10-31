# FASE 3 — H. Observabilidad ampliada: qué hace Nexo, y quién se lo pidió

## Qué cambia respecto a FASE2_F

El diseño base (archivo de estado vivo + comando `/estado` en Telegram) se mantiene sin cambios — sigue siendo la base correcta. Lo que esta fase amplía es el ALCANCE de qué hay que observar, porque ahora hay más piezas moviéndose: un Model Router con 10 decisiones (sección E), posiblemente varios modelos locales especializados (sección B), y una capa de control del PC (sección G). Cuantas más piezas actúan, más importante es la distinción que pide Damián: **"lo que Nexo está haciendo" vs. "lo que una IA le ha propuesto hacer"**.

## Por qué esta distinción es ahora más urgente, no menos

Con la arquitectura de la Fase 2, la única fuente de "trabajo sugerido por una IA externa" era una respuesta de Gemini/ChatGPT que Claude decidía ejecutar. Con la arquitectura de esta fase, hay más eslabones: el Router local puede decidir escalar a Gemini, Gemini puede sugerir un plan, el Router puede decidir ejecutarlo con Qwen, y Qwen puede a su vez generar un comando. Sin marcar el ORIGEN de cada decisión en la traza de estado, se vuelve imposible reconstruir después "¿esto lo decidió Nexo, o lo generó una IA externa y nadie lo revisó?" — que es precisamente el escenario que le preocupa a Damián.

**Diseño concreto:** cada entrada del estado vivo (`memoria/estado_actual.json`, ya propuesto en FASE2_F) lleva un campo `origen` con una cadena de procedencia, no solo un valor único — por ejemplo: `damian → router_local → gemini(sugerencia) → qwen(ejecucion)`. Así, cualquier acción puede rastrearse hasta si nació de una petición directa de Damián, de una decisión mecánica del Router, o de una sugerencia de una IA externa que atravesó capas sin que un humano la revisara.

## Qué observar, ampliado

Todo lo ya listado en FASE2_F (tarea, subtarea, herramienta, comando, proveedor, modelo, tiempo, pasos, reintentos, errores, resultado, siguiente acción) más:

- **Qué decisión tomó el Router y por qué** (de las 10 decisiones de la sección E) — no solo "qué proveedor", sino "por qué ese proveedor y no otro", para poder auditar si el Router está decidiendo bien.
- **Cadena de origen** (campo `origen` descrito arriba).
- **Nivel de permiso de la acción en curso** (VERDE/ÁMBAR/ROJO, sección J) — para que un vistazo a `/estado` diga también si lo que está pasando ahora mismo es de bajo o alto riesgo.

## Controles, reafirmados y ampliados

Pausar, cancelar, matar, fijar timeout/pasos/reintentos, detectar bucles — todo lo de FASE2_F sigue vigente. Se añade: dado que ahora hay más proveedores y más pasos de escalado posibles, el límite de "número máximo de pasos" del Router (sección E, punto 9) debe aplicarse también a la CADENA completa, no solo a un proveedor individual — por ejemplo, evitar que una tarea rebote de Qwen a Gemini a ChatGPT a Claude sin que nadie note que ya lleva 4 escalados sin resolver nada.

## Interfaz: se mantiene Telegram `/estado` como base

Sin cambios respecto a la recomendación de FASE2_F — sigue siendo la interfaz correcta porque llega al móvil, que es el objetivo original del proyecto. Con el alcance ampliado de esta sección, `/estado` puede mostrar además la cadena de origen y el nivel de riesgo de la acción en curso, sin que eso obligue a construir una interfaz nueva. Una web local sigue quedando como ampliación futura opcional, no como necesidad de esta fase.
