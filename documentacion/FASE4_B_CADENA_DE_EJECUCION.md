# FASE 4 — B. La cadena formal: proponer no es ejecutar

## La regla, explícita de una vez

**Ningún modelo — local o externo, incluido Claude — ejecuta nada por el simple hecho de proponerlo.** Esto ya era cierto de facto en varios sitios del sistema (Qwen en `triaje.py` nunca decide ni da de alta tareas; `permisos.py` exige aprobación para lo ÁMBAR/ROJO), pero no estaba escrito como regla arquitectónica única aplicable a TODOS los recursos por igual. Esta fase lo formaliza como la cadena que debe recorrer cualquier acción que cambie algo del mundo real:

```
PROPUESTA -> VALIDACION (Nexo/Runtime) -> PERMISOS -> TOOL -> EJECUCION -> VERIFICACION -> RESULTADO
```

## Qué hace cada eslabón

- **PROPUESTA:** cualquier modelo (Claude, Gemini, ChatGPT, Qwen) puede proponer una acción — "ejecuta este PowerShell", "escribe este archivo", "haz clic aquí". Una propuesta es texto, no una llamada a función real todavía; se registra con su origen exacto (qué modelo, en qué contexto, sección FASE3_H).
- **VALIDACIÓN (Nexo/Runtime, capa A):** el Runtime interpreta la propuesta contra el estado actual — ¿tiene sentido en el contexto de la tarea? ¿coincide con lo que el Router (capa A) había decidido delegar? Una propuesta que no encaja con el plan vigente se descarta o se marca para revisión, no se ejecuta "porque la dijo un modelo".
- **PERMISOS:** la acción validada pasa por `nivel_de_ruta()`/`nivel_de_comando()` (o su extensión futura a acciones visuales/de proveedor, FASE3_J) — exactamente igual sea la propuesta de Claude, de Gemini, de Qwen o generada por el propio código de Nexo. **El nivel de permiso no depende de quién lo propuso, depende de qué es la acción.**
- **TOOL (capa C):** la ejecución real siempre pasa por una tool concreta (archivos, shell, navegador, visión) — nunca una llamada directa "porque el modelo lo pidió". Esto es lo que ya hace bien `manos/archivos.py` (siempre vía `exigir()`) y lo que NO hace `ejecutar_python()` (L1) — la cadena formal de esta sección es, en el fondo, la descripción general de por qué L1 es un agujero: se salta los eslabones VALIDACIÓN y PERMISOS y va directo de PROPUESTA a EJECUCIÓN.
- **EJECUCIÓN:** la tool hace el trabajo, con los límites del Router (timeout, máximo de pasos, FASE3_E) ya aplicados antes de empezar.
- **VERIFICACIÓN:** obligatoria para ÁMBAR/ROJO, recomendable para VERDE de volumen (FASE3_J) — comprueba que el resultado es el esperado, no solo que "no hubo excepción".
- **RESULTADO:** se registra (evidencia para el Router, FASE3_E/E de esta fase) y se reporta (observabilidad, FASE3_H).

## Qué gana el sistema con esto, en concreto

- **Controlar agentes externos y locales con la misma regla** — hoy no hay ninguna diferencia formal entre "Claude decide ejecutar algo" (que corre dentro de una sesión de Claude Code, con sus propias herramientas MCP) y "Qwen sugiere un comando que el código de Nexo ejecuta directamente" — ambos deberían pasar por la misma cadena, aunque el mecanismo técnico de cada paso sea distinto según quién genera la propuesta.
- **Registrar origen sin ambigüedad** — cada acción ejecutada lleva consigo qué la propuso, quién la validó, qué nivel de permiso tuvo — es la pieza que hace posible la "cadena de origen" ya diseñada en observabilidad (FASE3_H): "Nexo decidió / IA externa propuso / Nexo aceptó / tool ejecutó / verificador confirmó" es, literalmente, esta cadena leída en voz alta.
- **Detectar acciones peligrosas antes de que ocurran** — el eslabón VALIDACIÓN es el punto donde una propuesta claramente fuera de lugar (una IA externa proponiendo borrar algo, o un comando que no tiene relación con la tarea en curso) se puede interceptar antes de llegar siquiera a PERMISOS.
- **Poder detener el proceso** — como la ejecución real siempre pasa por una tool concreta (capa C) y nunca es "el modelo actuando directamente sobre el mundo", detener/matar/pausar (FASE3_H/J) tiene un punto de enganche real: la tool en ejecución, no "la mente del modelo".

## Caso concreto: Claude dentro de su propia sesión de Claude Code

Una precisión honesta que hay que hacer explícita: cuando Claude actúa en una sesión de Claude Code (como esta misma), ya usa herramientas con su propio control de permisos (aprobaciones del entorno, blindaje de archivos) — la cadena de esta sección no sustituye eso, lo generaliza como PRINCIPIO para que el resto del sistema (Qwen, Gemini, ChatGPT, y cualquier ejecución que NO pase por una sesión de Claude Code) siga la misma disciplina en vez de tener sus propias reglas ad-hoc. Dicho de otro modo: esta cadena es lo que `nucleo/permisos.py` + las tools de `manos/` ya intentan ser para el propio Claude — extenderla explícitamente a Qwen/Gemini/ChatGPT es lo nuevo.

## Qué NO se implementa en esta fase

Nada. Esta cadena es la descripción formal de cómo deben conectarse las piezas cuando se implemente el Runtime (FASE4_C) — no se toca `permisos.py`, `bot.py` ni ningún otro archivo todavía.
