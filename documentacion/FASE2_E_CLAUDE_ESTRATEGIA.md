# FASE 2 — E. Estrategia de integración con Claude: Routines vs. Playwright vs. alternativas

Punto de partida obligado: T039 demostró que "rutinas programadas vinculadas a un dispositivo" (lo que Damián tiene en `claude.ai/code/routines`) y "Claude Code Routines con disparo por API" (lo que documenta `platform.claude.com/docs/en/api/claude-code/routines-fire`) son **dos productos distintos**, y el segundo no está expuesto en la cuenta de Damián. Cualquier estrategia aquí debe partir de lo que SÍ existe hoy, no de lo que el código de T039 asumió.

## Las opciones sobre la mesa

**(A) Rutinas programadas actuales (cron interno del producto, sin API).** Lo que ya funciona: dos rutinas (`turno de noche`, `turno corto`) que arrancan una sesión de Claude Code con un prompt fijo, a una hora fija, opcionalmente "requiriendo este ordenador". Es la ÚNICA vía confirmada hoy para que Claude arranque trabajo sin que Damián abra nada.

**(B) Claude Code Routines con disparo por API (`/routines/{id}/fire`).** Documentada, real, pero NO disponible en la interfaz de Damián — no aparece "Select a trigger / API / Generate token" en ninguna de sus dos rutinas. Sin evidencia de qué la habilita (¿plan distinto? ¿otra superficie del producto, como cuentas de equipo/API console en vez de la app de consumo?), no se puede dar por alcanzable. Se mantiene como opción a **reintentar más adelante si cambia la cuenta o el producto**, no como plan actual.

**(C) Playwright sobre claude.ai.** Es técnicamente la misma técnica que ya usa `navegador.py` para Gemini/ChatGPT — automatizar una pestaña de Chrome real, no una API. La restricción existente es **T038, cerrada explícitamente y por decisión ya tomada**: no automatizar claude.ai con Playwright. Esta revisión no encuentra ningún hecho nuevo desde entonces que cambie el motivo original de esa decisión (dependencia de una interfaz que cambia sin aviso + riesgo de romper condiciones de uso al automatizar el propio front-end de Anthropic con una sesión de usuario real, algo distinto de automatizar Gemini/ChatGPT, servicios de terceros). **No se reabre T038 con esta revisión** — se documenta como opción existente, descartada, con la razón de por qué sigue descartada, tal como pide el punto 6 de Damián ("si Playwright termina siendo la solución más práctica, dilo" — en este caso concreto, para claude.ai, no lo es, y ya había una decisión tomada al respecto).
   - Distinto es Playwright sobre **Gemini/ChatGPT**, ya en uso y fuera de esta pregunta — eso no está en duda.

**(D) Automatización visual del cliente de escritorio de Claude.** Abrir la app de escritorio, ver la pantalla, hacer clic en "Nueva conversación", escribir el prompt. Técnicamente posible con la misma pila de control visual descrita en FASE2_D (una vez exista). Hoy: no implementado, no hay ninguna pieza de código que lo intente.

**(E) Combinación visual + estructurado.** Ídem (D) pero usando primero cualquier atajo de teclado/URL profunda que la app de escritorio ofrezca (si los tiene) antes de caer a clics por coordenadas — es la aplicación directa de la jerarquía de FASE2_D a este caso concreto.

**(F) Otro mecanismo oficial actual.** Búsqueda web (parcial, por el límite de sesión de `WebFetch` durante esta revisión) no encontró ningún tercer mecanismo oficial de disparo remoto de Claude Code distinto de (A) y (B). No se puede descartar que exista y no haya aparecido en esta búsqueda parcial.

**(G) Combinación de varias.** La más razonable dado lo de arriba: (A) para lo que ya cubre (arranque programado, con o sin ordenador exigido) + (D)/(E) como plan de contingencia SOLO para recuperar una rutina que se ha quedado bloqueada esperando algo que un humano normalmente resolvería con un clic — no como mecanismo primario de arranque.

## La distinción de cuatro niveles que pidió Damián

| Opción | Técnicamente posible | Fiable en producción | Compatible con condiciones de uso | Mantenible |
|---|---|---|---|---|
| (A) Rutina programada actual | Sí, ya funciona | Alta — es el mecanismo soportado por el producto | Sí, es la vía oficial | Alta — no hay nada que mantener, lo mantiene Anthropic |
| (B) API Routines/fire | Sí, documentado | Desconocida — no probada, no disponible en esta cuenta | Sí, es una API oficial | Buena SI estuviera disponible (evita frágilidad de UI) |
| (C) Playwright sobre claude.ai | Sí (misma técnica que ya usa navegador.py) | Baja — dependiente de una interfaz de producción propia de Anthropic que puede cambiar sin aviso, y automatizando la propia sesión de usuario del producto que Claude Code corre encima | Dudosa/no clara para este caso concreto (distinto de automatizar un tercero como Gemini) — motivo por el que T038 se cerró así | Baja — cualquier cambio de UI de claude.ai rompe el script, sin aviso previo |
| (D)/(E) Automatización visual del cliente de escritorio | Sí, en cuanto exista la capa de FASE2_D | Media — mejor que (C) porque un cliente de escritorio cambia menos que una web, pero sigue siendo UI | Sí — es usar la app tal como la usaría Damián, con sus manos sustituidas por las del agente, no una llamada de red no autorizada | Media — requiere la capa de control visual completa antes de poder evaluarlo de verdad |

## Recomendación

1. **Mantener (A) como mecanismo primario**, sin cambios: ya funciona, es la vía oficial y no tiene mantenimiento propio.
2. **No perseguir (B) activamente ahora mismo** — no hay ruta conocida para obtenerlo en esta cuenta; revisar de nuevo si Damián ve en el futuro cualquier cambio en su plan o en la interfaz que sugiera que ha aparecido.
3. **No reabrir (C) para claude.ai** — T038 sigue siendo la decisión correcta con la información actual; nada de esta revisión cambia el motivo por el que se cerró.
4. **Construir (D)/(E) no como sustituto de (A), sino como red de recuperación**, y solo después de que exista la capa de control visual (FASE2_D) y de permisos ampliada (FASE2_J) — es decir, al final del orden de implementación (ver FASE2_L), no antes.
5. Documentar T039 como **cerrada con causa conocida** (arquitectura equivocada, no capacidad inexistente) y mantener el código de `_cmd_ahora()` en `canal/bot.py` sin borrar, marcado como "válido para Claude Code Routines cloud, no aplicable a las rutinas actuales de Damián" — por si en el futuro cambia de superficie de producto.

## Qué NO cambia con esta revisión

- El turno de noche/corto sigue siendo la única vía de arranque autónomo — esta sección no propone tocarlo (eso es la sección N/FASE2_H, y ahí se recomienda por separado pausarlo temporalmente por otros motivos, no por lo tratado aquí).
- No se toca `secretos.toml` ni se pide ninguna acción manual nueva de Damián derivada de esta sección.
