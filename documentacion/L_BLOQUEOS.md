# L. Lista de bloqueos

Cosas que NO pueden avanzar más sin que ocurra algo fuera del control de un turno de Claude corriente.

## Bloqueos de plataforma (no de diseño, no de código)

1. **Cambio de modelo/nivel de razonamiento de una Rutina de Claude Code atada a un dispositivo**: confirmado repetidas veces (T005, T029, T034) que no se puede parchear mecánicamente desde fuera. Solo el dueño puede cambiarlo desde su propio Claude Code. Esto bloquea la mitad de REQ-010 (Model Router) — la mitad "qué proveedor" no está bloqueada, la mitad "qué modelo dentro de Claude" sí.
2. **Detección de cuota/límite de Claude Code de forma preventiva**: no hay API pública documentada. Ver REQ-030 en la matriz. No se recomienda intentar rodear esto con scraping (violaría la decisión ya tomada sobre T038/ToS).
3. **Ejecución de dos turnos de Claude en paralelo sobre la misma memoria**: ya causó un incidente real (memoria pisada). No es un bloqueo de plataforma sino de diseño propio, pero se lista aquí porque no se recomienda "resolverlo" con más concurrencia, sino evitarlo con una cola de un solo turno a la vez (ver `F_ANALISIS_CLAUDE.md`, caso A).

## Bloqueos por decisión pendiente de Damián (no técnicos)

4. T016/L1 (`ejecutar_python` sin permisos) — decisión suya, explícitamente no se toca sin su aprobación en tiempo real.
5. B5 (`vivo()` con `aprobado=True` hardcodeado) — pendiente de confirmar que no rompe nada antes de tocarlo.
6. REQ-070 (lectura sin restricción fuera del proyecto) — pendiente de decisión.
7. T024/L6 (filtro de permisos mira la línea entera) — pendiente por decisión propia de Damián de no tocarlo sin pruebas y con calma.
8. T037 (Wake-on-LAN/encendido remoto) — pendiente de que decida hardware/BIOS o Connected Standby.
9. T025 (pychromecast) — pendiente de aprobación de instalación.
10. T034 (modelo Sonnet vs Opus en el turno de noche) — pendiente de que lo cambie él mismo.

## Bloqueos por falta de infraestructura que hay que construir primero (dependencias de diseño)

11. REQ-001 (autonomía completa) depende de REQ-010 (Model Router) + REQ-011 (Message Bus) + REQ-012 (Planner), ninguno de los tres existe todavía como componente real.
12. REQ-011 (Message Bus) no está bloqueado técnicamente (el patrón ya existe en `canal/buzon.py`), solo no se ha construido todavía.

No hay ningún bloqueo en esta lista que se recomiende "saltarse" o rodear. Donde hace falta decisión de Damián, se marca `USER_DECISION_REQUIRED` en el documento correspondiente; donde hace falta una acción suya, está en `K_ACCIONES_DAMIAN.md`.
