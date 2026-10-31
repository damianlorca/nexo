# FASE 2 — F. Observabilidad y control del agente local en tiempo casi real

## El problema tal como lo describe Damián

Ve "pensando... / usando agente local..." reaparecer poco después de que una acción parezca terminada, y no puede distinguir si es: otra acción legítima, una llamada a herramienta normal, una espera, un reintento, un bucle, una recuperación de error, o trabajo innecesario. Hoy no hay ninguna pieza del sistema que responda a esa pregunta — se confirma revisando `canal/vigilante.py` (un watchdog de 30s que solo comprueba si el proceso del bot sigue vivo, con `ctypes`+`OpenProcess`, nunca `os.kill`) y `nucleo/registro.py` (`logger()`/`traza()`, registro estructurado por evento, pero pensado para depuración posterior, no para una vista en vivo del estado actual).

## Qué hay que distinguir (dos preguntas distintas, no una)

1. **Qué está haciendo Nexo ahora mismo** — tarea, subtarea, herramienta, comando/proceso, proveedor, modelo, tiempo transcurrido en el paso actual, número de pasos dados, reintentos, errores encontrados, resultado del último paso, próxima acción prevista y por qué.
2. **Quién pidió esa acción** — si la inició Damián, el turno programado, o una respuesta de Gemini/ChatGPT que Claude está ejecutando como intermediario. Esto es una distinción que hoy no existe en ningún dato del sistema: `navegador.py` devuelve texto de Gemini/ChatGPT sin ninguna marca de procedencia que sobreviva más allá de la respuesta inmediata a Claude. Sin esto, es imposible saber después "¿esto lo decidió Nexo o se lo sugirió otra IA sin que nadie lo revisara?" — que es exactamente el escenario que preocupa a Damián (una IA externa generando trabajo innecesario).

## Diseño propuesto (no implementar todavía)

**Una traza de estado, no solo un log de eventos.** Extender `nucleo/registro.py` con un archivo de estado vivo (ej. `memoria/estado_actual.json`, distinto del histórico `trazas.jsonl` que ya existe) que un paso en curso sobrescribe con: tarea, subtarea, herramienta, comando, proveedor, modelo, inicio del paso, pasos dados, reintentos, origen de la orden (Damián / turno programado / sugerencia de IA externa pendiente de confirmar), y la razón de la siguiente acción prevista. Cada nuevo paso lo sobrescribe — no crece sin límite, siempre refleja "ahora mismo".

**Detección de bucle, delegada a Qwen (ver sección A), no a Claude mirándose a sí mismo.** Un vigilante ligero (ya propuesto en FASE2_A como candidato de bajo riesgo) lee `trazas.jsonl` cada pocos minutos mientras hay un turno activo y busca patrones mecánicos simples: misma herramienta+argumento repetido N veces seguidas, un proceso lanzado hace más de X minutos sin traza de fin, más de Y llamadas a un proveedor externo en Z minutos. No decide nada — deja una señal en `memoria/estado_actual.json` que la interfaz de observabilidad puede resaltar.

**Controles, no solo visibilidad.** Los pedidos por Damián — pausar, cancelar, matar, fijar timeout, fijar límite de pasos, fijar límite de reintentos — necesitan un punto de enganche que hoy no existe: ni `permisos.py` ni ningún módulo actual expone "detener la acción en curso" desde fuera del propio proceso de Claude Code. La vía más realista sin tocar el núcleo de Claude Code es a nivel de **proceso lanzado por Nexo** (Qwen, Playwright, scripts) — ahí sí hay control real (matar el proceso, con el mismo cuidado de `ctypes`+`OpenProcess` ya usado en `vigilante.py`, nunca `os.kill` en Windows). Controlar el propio turno de Claude Code desde dentro de sí mismo (pausar/cancelar la sesión que está ejecutando el propio código de control) es una limitación estructural: normalmente el canal para eso es el propio Damián cancelando la rutina o cerrando la sesión desde la interfaz de Claude, no algo que Nexo pueda hacerse a sí mismo de forma fiable.

## Qué interfaz usarla

No un archivo de 5000 líneas, como pide Damián explícitamente. Tres opciones reales, no mutuamente excluyentes:

- **Telegram (ya existe el canal):** un comando `/estado` que lee `memoria/estado_actual.json` y devuelve un resumen de 4-6 líneas — tarea, paso actual, tiempo en el paso, próxima acción. Coste de implementación bajo (reutiliza `canal/bot.py`), y es lo único de las tres opciones que llega al teléfono sin que Damián tenga que abrir nada, que es justo el objetivo original del proyecto ("desde mi teléfono que me avise o pregunte"). **Es la opción recomendada como base.**
- **Consola/log local:** ya existe en forma de `trazas.jsonl`; seguirá siendo la fuente de verdad para depuración profunda, no para observabilidad del día a día.
- **Una pequeña web local:** más trabajo de construir y mantener, y solo es útil estando delante del PC — contradice la ventaja de Telegram (verlo desde el teléfono fuera de casa). Se descarta como prioridad; queda como posible ampliación futura si `/estado` por Telegram resulta insuficiente en la práctica.

**Recomendación: Telegram (`/estado`) como interfaz principal, alimentada por el archivo de estado vivo descrito arriba.** No requiere nueva infraestructura (canal ya existente), resuelve directamente la pregunta que originó esta sección, y es coherente con el objetivo general del proyecto.

## Relación con el resto del diseño

Depende de: nada nuevo de otras secciones — puede implementarse de forma independiente y temprana (ver orden en FASE2_L). Es un prerrequisito útil, aunque no estrictamente bloqueante, para la autonomía incremental (sección O) y para el control visual (sección D): cuanto antes exista visibilidad real del estado, más seguro es dar más autonomía o abrir una capa nueva (visual) que puede fallar de formas nuevas.
