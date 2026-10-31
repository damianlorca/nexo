# FASE 4 — C. Nexo como runtime/servicio permanente

## El conceptual completo, tal como lo pide Damián

```
NEXO RUNTIME
├── estado
├── memoria
├── cola
├── scheduler
├── router
├── proveedores
├── modelos locales
├── tools
├── permisos
├── watchdog
├── observabilidad
├── recuperacion
└── interfaz movil
```

**Qué de esto ya existe hoy, con honestidad, componente a componente:**

| Componente | Estado real hoy |
|---|---|
| estado | `nucleo/estado.py` (`memoria/estado.json`) — existe, sin candado conectado a `bot.py`/`vigilante.py` (T035) |
| memoria | `memoria/` (tareas, historial, triaje) — existe y funciona |
| cola | `nucleo/tareas.py` — existe, con puntuación por criterio |
| scheduler | Las rutinas programadas de Claude Code (cron) — existe, pero SOLO para arrancar Claude, no un scheduler genérico de Nexo |
| router | No existe — diseñado en FASE3_E, no implementado |
| proveedores | `proveedores.py` — existe como contrato, `capacidades()` sin consumidor |
| modelos locales | Ollama + Qwen — existe y funciona |
| tools | `manos/archivos.py`, `manos/shell.py`, `extremidades/imagen.py`, `extremidades/navegador.py` — existen, dispersas, sin capa común de tool (capa C de FASE4_A) |
| permisos | `nucleo/permisos.py` — existe, con L1/REQ-070 abiertos, sin cobertura de proveedor/visual/origen |
| watchdog | `canal/vigilante.py` — existe, pero SOLO liveness de proceso del bot, no watchdog de tareas/bucles |
| observabilidad | Solo `nucleo/registro.py` (trazas pasadas) — sin estado vivo (diseñado en FASE3_H, no implementado) |
| recuperación | No existe de forma explícita — cada pieza maneja sus propios errores sin una política común |
| interfaz móvil | Telegram (`canal/bot.py`) — existe y funciona |

**Lectura honesta:** Nexo YA es, en la práctica, un runtime disperso — los componentes existen, pero no como piezas de una arquitectura pensada, sino como código que fue creciendo por necesidad puntual. Esta fase no propone construir un runtime desde cero — propone reconocer que ya hay un runtime implícito, formalizarlo (las capas de FASE4_A), y llenar los huecos reales: scheduler genérico, router, capa de tool común, watchdog de tareas (no solo de proceso), observabilidad con estado vivo, y una política de recuperación explícita (sección H de esta fase).

## Nexo debe seguir vivo aunque un recurso falle — esto ya es parcialmente cierto

El bot de Telegram y el vigilante ya sobreviven a que Claude no esté disponible (el bot sigue respondiendo `/tareas`, `/estado`, etc. sin tocar Claude para nada). Lo que falta es que el resto de recursos (Gemini, ChatGPT, un modelo local) tengan la misma independencia formal — hoy, si Chrome se cierra, `navegador.py` simplemente falla la próxima vez que se le pide algo (con `arrancar()` como recuperación parcial ya existente); no hay una política uniforme de "recurso caído → Nexo lo sabe → Nexo decide sin ese recurso" aplicada a los cuatro proveedores por igual. Esta política uniforme es exactamente el contenido de la sección H (watchdog/fallback/recuperación) de esta fase.

## El puente móvil↔Nexo↔PC↔IAs, releído bajo el runtime

```
MÓVIL <-> NEXO RUNTIME <-> (PROVEEDORES: modelos locales, Claude, Gemini, ChatGPT...) <-> TOOLS
```

La diferencia con cómo se describía en FASE3_I: antes "Nexo" era un poco difuso (¿el bot? ¿una sesión de Claude?) — con el runtime formalizado, el móvil habla SIEMPRE con el Runtime (vía Telegram, hoy), y es el Runtime — no el móvil, no Claude — quien decide si resuelve local, despierta un recurso, o escala. Esto ya es, de hecho, lo más cerca que está hoy Nexo de "no depender de que Claude esté pensando constantemente": el bot recibe, Qwen triaje, y solo si hace falta se despierta una rutina o `/ahora` toca a Claude. Lo que falta para que sea el runtime completo que pide Damián es que esa misma decisión ("¿hace falta Claude, o basta con esto?") pase por el Router formal (FASE3_E) en vez de la lógica ad-hoc actual de `bot.py`.

## Relación con el resto de esta fase

Este documento es el marco; el resto de FASE4 rellena sus huecos: la cadena de ejecución (B) formaliza cómo actúan las tools; el Router (E) formaliza la decisión; el watchdog/fallback (H) formaliza la recuperación; la observabilidad (I) formaliza la visibilidad; la seguridad (J) formaliza los permisos transversales. El roadmap (índice, sección de dependencias) determina qué pieza de este runtime construir primero.
