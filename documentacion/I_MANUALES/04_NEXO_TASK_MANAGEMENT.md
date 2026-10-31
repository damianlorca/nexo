# I.4 NEXO_TASK_MANAGEMENT

## Sistema real (`nucleo/tareas.py`, verificado)

- CLI: `anadir "<titulo>" --importancia N --urgencia N --dificultad N --coste N --depende ia|damian`, `estado <ID> hecha`, `testeada <ID> "<evidencia>"`, `nota <ID> "<texto>"`, `siguiente|mias|tuyas`.
- Estados reales (5, no los 10 de la especificación maestra — decisión deliberada de no tocar esto sin que Damián lo pida expresamente): `pendiente, en_curso, esperando, bloqueada, aparcada` + cerrados (`hecha, descartada`).
- Puntuación: `puntuacion = (3*urgencia + 2*importancia) / freno`, `freno = 1 + 0.30*(dificultad-1) + 0.20*(coste-1)`.
- Modelo sugerido (informativo, no aplicado solo): `peso = 2*dificultad + importancia`; ≤6→sonnet/media, ≤11→sonnet/alta, si no→opus/alta.
- Candado entre procesos (`nucleo/candado.py`) para que el bot y un turno de Claude no se pisen escribiendo `memoria/tareas.json` a la vez (T031).

## Campo `testeado` (22/09/2026) — Principio de Verdad sin tocar la máquina de estados

`estado` sigue con sus 5 valores vivos de siempre. Para distinguir HECHO Y TESTEADO de HECHO SIN TESTEAR (que exige la Constitución) se añadió un campo booleano `testeado`, ortogonal a `estado`, en vez de ampliar la máquina de estados:

- `completar(id, nota)` (CLI: `hecha`) cierra la tarea como `estado=hecha` pero **no** toca `testeado` — cerrar no es lo mismo que comprobar.
- `verificar(id, evidencia)` (CLI: `testeada`) marca `testeado=True` y dejar `evidencia` es casi obligatorio en la práctica: queda anotado en la tarea (test ejecutado, salida real, archivo comprobado a mano — no un tick sin más).
- `estado_real(tarea)` traduce `estado`+`testeado` al vocabulario exacto de la Constitución: `PLANIFICADO / EN PROCESO / BLOQUEADO / HECHO SIN TESTEAR / HECHO Y TESTEADO`.
- En `tareas.md`, `[x]` = hecha y testeada, `[x?]` = hecha pero sin comprobar todavía. Las 119 tareas previas al 22/09 se migraron con `testeado=False` (honesto: no había evidencia registrada de que se hubiera comprobado cada una).

Por defecto una tarea recién cerrada queda **sin testear** — hay que verificarla explícitamente. Esto es intencional: evita que "cerrar" se confunda con "comprobado".

## `bloqueada_por` / `pregunta_id` — ya existían, ahora hay que usarlos

Estos dos campos están en el esquema desde antes del 22/09 pero llevaban vacíos en las ~95 tareas previas. Antes de inventar un campo nuevo para "esto depende de otra tarea" o "esto depende de una respuesta de Damián", usar estos:

- `bloqueada_por`: id de la tarea que bloquea a esta (o texto libre si el bloqueo no es otra tarea de la cola).
- `pregunta_id`: referencia a una pregunta/decisión pendiente de Damián (p. ej. el id de una `mcp__claude-code-remote` question, o una referencia corta en texto).

Ambos se muestran ya en `tareas.md` cuando no están vacíos.

## Cómo entra una tarea nueva

- Desde Telegram: `/tarea <titulo>` (T002, coste cero, sin pasar por Claude ni Qwen).
- Desde un turno de Claude: `nucleo.tareas.anadir(...)`.
- Desde Qwen: **nunca decide sola**, solo propone en el triaje (`extremidades/triaje.py`); alguien tiene que confirmar. Esto es deliberado: un modelo de 7B leyendo un mensaje ambiguo y dando de alta tareas sin supervisión llenaría la cola de basura.

## Regla de elección en un turno

Primero lo que tenga urgencia alta. Entre iguales, lo que dependa de Nexo (no de Damián) y sea de coste bajo, para no gastar el plan esperando a nada.

## Trazabilidad de origen (auditorías, migraciones, etc.)

Para marcar de dónde viene un lote de tareas (p. ej. una auditoría de cobertura), usar `etiquetas` (`origen:<fuente>`, `auditoria_id:<ref>`) en vez de un campo dedicado — ya lo soporta el esquema, no rompe nada y ya se usó así (T093-T095, T096-T119).

## Lo que falta (ver `A_MATRIZ_REQUISITOS.md` REQ-001, REQ-050)

Máquina de 10 estados de la especificación maestra, Planner que divida objetivos en subtareas automáticamente. No implementar sin decisión explícita de Damián.
