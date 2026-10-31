# I.11 NEXO_MEMORY_AND_STATE

## Jerarquía real (verificada)

- **`memoria/estado.json`** — lo más valioso: misión en curso, paso, errores, `siguiente_turno` (lista de notas para el próximo turno), `hechos` (lecciones permanentes). Atómico, con recuperación de corrupción (`nucleo/estado.py`), candado para cambios mecánicos (T035).
- **`memoria/tareas.json`** — cola de tareas, candado entre procesos (T031), 46 tareas reales hoy.
- **`memoria/uso_diario.json`** — estadística, no memoria crítica: si se corrompe, se empieza de cero sin recuperar respaldos (decisión deliberada, `nucleo/uso.py`), poda automática a 90 días.
- **`memoria/historial.md`** — historial narrativo detallado, separado de `estado.json` desde T033 para no hincharlo.
- **`memoria/triaje.json`** — última lectura de Qwen sobre mensajes pendientes.
- **`registros/`** — logs día a día (`agente_<fecha>.log`) y `trazas.jsonl` (eventos estructurados). Excluido deliberadamente de `listar()` normal (hay que leerlo por ruta exacta).
- **`_respaldos/`** — copia automática de cualquier archivo antes de que `escribir()` lo sobrescriba, organizada por fecha.
- **`_archivo/`** — donde va todo lo que `archivar()` mueve. Nunca se borra nada: se archiva.

## Regla de oro para cualquier escritura de memoria

**Releer antes de escribir, fundir no reemplazar.** Ya ha causado un incidente real no seguirla (T035, se pisó `nucleo/estado.py` existiendo ya). Esto aplica sobre todo a cambios que hace un turno de Claude a mano con `leer()`+`escribir()` (dos llamadas separadas, con todo el pensar del turno en medio): un candado no protege ese hueco, que dura minutos, no milisegundos.

## Lo que falta (ver `A_MATRIZ_REQUISITOS.md` REQ-060)

Poda automática para `memoria/estado.json`, `memoria/tareas.json` y `registros/trazas.jsonl`. Riesgo bajo hoy (tamaños pequeños/medios), a vigilar según crezca el proyecto.
