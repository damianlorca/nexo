# I.8 NEXO_ERROR_RECOVERY

## Principio general (ya aplicado, verificado)

Nunca pisar en silencio. Ante corrupción o fallo, apartar lo roto (nunca borrarlo), recuperar lo mejor posible, y dejarlo dicho explícitamente en el propio resultado para que quien lo lea después no se fíe a ciegas.

## Mecanismos reales que ya existen

- **`nucleo/estado.py::cargar()`**: si `memoria/estado.json` está roto, lo aparta a `_archivo/<fecha>/estado_roto_<hora>.json` (nunca lo borra), intenta recuperar el último respaldo de `_respaldos/`, y dejar escrito en el propio estado recuperado que ha pasado algo y que puede faltar lo último del turno anterior.
- **`nucleo/escritura.py::escribir_atomico()`**: usado en todo el proyecto. Si el proceso muere a mitad de escribir, el archivo viejo se queda intacto (nunca un archivo a medias).
- **`nucleo/candado.py`**: candados huérfanos (más de 30s, umbral muy por encima de lo que tarda cualquier operación real) se roban en vez de bloquear el sistema para siempre — necesario porque Claude Desktop mata el servidor MCP sin avisar (hallazgo B1, confirmado).
- **`extremidades/imagen.py`**: ante un encargo de ComfyUI roto, reinicia el servicio y reintenta una vez antes de rendirse, con mensaje de diagnóstico específico (el `UnicodeDecodeError` con byte `0xe1` es falta de memoria de GPU, no un fallo de texto — documentado para no perder tiempo interpretándolo mal otra vez).
- **`canal/vigilante.py`**: si el bot muere, lo relanza en <10s.

## Lo que NO existe todavía

Ningún mecanismo de recuperación para: una tarea de la cola que falla a mitad sin que nadie la marque `bloqueada`; un turno de Claude que se corta por límite de cuota (T042) sin que el siguiente turno sepa exactamente por dónde se quedó (parcialmente cubierto por `siguiente_turno`, pero no de forma automática); una consulta a Gemini/ChatGPT que devuelve un `Bloqueo` (captcha) sin que se avise a Damián automáticamente (hoy hay que fijarse en el resultado del script).

## Regla para cualquier mecanismo nuevo de recuperación

Nunca "reintentar hasta que funcione" sin límite. Todo reintento automático existente tiene un tope (ComfyUI: una vez; candados: 30s de umbral). Cualquier autocuración nueva debe seguir el pipeline de `09_NEXO_SELF_IMPROVEMENT.md`, no aplicarse a ciegas.
