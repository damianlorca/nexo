# FASE 4 — I. Watchdog, fallback, recuperación, observabilidad y métricas

Estas cinco piezas van juntas porque comparten la misma fuente de datos (el estado vivo + el registro de evidencia) — se diseñan aquí como una sola capa transversal de la capa A (Runtime), no como funcionalidades separadas.

## La cadena de fallo, formalizada

```
FALLO DE RECURSO -> DETECCION -> RECUPERACION -> FALLBACK -> CONTINUACION o ESCALADO
```

**Casos concretos ya identificados en fases anteriores, ahora bajo una sola política:**

| Fallo | Detección | Recuperación | Fallback |
|---|---|---|---|
| Claude no disponible / límite de uso (ya observado en T042) | El propio intento de disparo de rutina falla o no responde | Reintento acotado (máximo de pasos del Router, FASE4_E) | Degradar a un proveedor externo disponible si la tarea lo permite, o encolar para el siguiente turno si no |
| Gemini/ChatGPT no responde o bloqueado | Timeout de `navegador.preguntar()`, o señal de bloqueo (`SENALES_BLOQUEO` ya existente en `navegador.py`) | Reintentar tras una pausa (ya se hace de facto en `descargar_ultima_imagen()`) | Probar el otro proveedor equivalente, o degradar a local si la tarea lo permite |
| Chrome muerto | `navegador.activo()` devuelve falso | `navegador.arrancar()` (ya existe) | Si arrancar falla repetidamente, marcar el recurso como caído en el `PerfilProveedor` (FASE4_F) y avisar, no reintentar indefinidamente |
| Ollama caído / modelo no cargado | `qwen.disponible()` (ya existe, usado en la sonda de `extremidades/base.py`) | Reintento con backoff acotado | Si Qwen no está disponible, las tareas que dependían de él se posponen o, si el riesgo es bajo, se resuelven con una regla determinista sin modelo (cuando exista una) |
| Tool bloqueada / proceso colgado | Ausencia de traza de progreso más allá del timeout del Router | Kill del proceso (mismo patrón ya usado en `vigilante.py`, `ctypes`+`OpenProcess`, nunca `os.kill`) | Marcar el paso como fallido, escalar según el nivel de riesgo de la tarea |
| Respuesta incompleta | Verificación (FASE3_J) detecta que el resultado no cumple lo esperado | Reintento con el mismo recurso, una vez | Si vuelve a fallar, escalar a un recurso más fuerte o pedir intervención humana |

**Límites explícitos, sin excepción:** timeout por paso, máximo de reintentos, detección de falta de progreso, detección de bucles (ya diseñado como vigilante ligero en FASE3_A/B) — nunca reintentos indefinidos. Cuando se agotan los reintentos y no hay fallback razonable, el sistema se detiene y reporta como bloqueado, pidiendo intervención humana — nunca sigue intentando en silencio.

## Observabilidad: sin cambios de fondo respecto a FASE3_H, con la cadena de origen ahora completa

El campo `origen` del estado vivo (`memoria/estado_actual.json`, diseñado en FASE2_F/FASE3_H) se rellena ahora con el vocabulario exacto de la cadena de ejecución de FASE4_B: `Nexo decidió` / `IA externa propuso` / `Nexo aceptó` / `tool ejecutó` / `verificador confirmó` — son, literalmente, los eslabones de esa cadena, así que no hace falta inventar un vocabulario nuevo, solo usar el ya definido.

**Interfaz:** se mantiene Telegram `/estado` como base (reafirmado en FASE2_F y FASE3_H). Sobre si hace falta además una interfaz local más completa: la respuesta honesta es "todavía no" — con el volumen de trabajo actual de Nexo, una interfaz local añadiría una superficie más que mantener sin un caso de uso concreto que Telegram no cubra ya. Se marca como algo a reconsiderar únicamente si, tras implementar `/estado`, la experiencia real muestra que el resumen de texto se queda corto (por ejemplo, si hace falta ver un histórico completo de una tarea larga de un vistazo) — no se construye por anticipado.

## Métricas de eficiencia (nuevo respecto a la Fase 3)

Damián pide poder DEMOSTRAR, no solo asumir, que la arquitectura mejora Nexo. El registro de evidencia del Router (FASE4_E) ya captura casi todo lo necesario; esta sección solo añade las métricas AGREGADAS que se calculan a partir de ese registro, no una infraestructura nueva:

- Tareas totales, tareas resueltas localmente, tareas escaladas (y a qué proveedor).
- Tiempo medio, reintentos medios, tasa de intervención humana, por categoría de tarea.
- **Porcentaje de tareas que llegaron a Claude** — la métrica central para el objetivo de "reservar Claude para lo que aporta valor real": una tendencia a la baja en tareas triviales/mecánicas, estable o solo al alza en tareas complejas, es la señal de que el Router está funcionando bien.
- Motivo del escalado (capacidad necesaria, fallo de un recurso, riesgo alto) — permite distinguir "escalamos porque hacía falta" de "escalamos porque algo local falló".
- Cuando sea medible: consumo/cuota aproximado por proveedor, coste evitado estimado (comparando cuántas tareas se resolvieron sin tocar Claude frente al escenario contrafactual de mandarlo todo a Claude).

**Cómo se compara "Nexo local-first" contra "Nexo mandándolo casi todo a Claude":** con el mismo registro, calculando las mismas métricas sobre dos periodos (o, más simple, llevando la cuenta desde el día en que el Router entra en producción) — no hace falta un experimento controlado artificial, el propio uso diario genera los datos si el registro está bien diseñado desde el principio (de ahí que el registro de evidencia, FASE4_E, sea de las primeras piezas del roadmap, no una ocurrencia tardía).

## Sin implementación en esta fase

Ninguna de estas piezas se construye todavía. El watchdog de bucles ligero, el registro de evidencia y el estado vivo con cadena de origen son, con esta fase, los tres candidatos más claros para entrar pronto en el roadmap (ver índice) precisamente porque desbloquean, a la vez, fallback, métricas y observabilidad sin necesitar todavía el Router completo.
