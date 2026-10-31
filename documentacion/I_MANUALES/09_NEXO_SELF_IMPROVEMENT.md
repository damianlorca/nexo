# I.9 NEXO_SELF_IMPROVEMENT

Ninguna auto-mejora ciega. Toda propuesta de cambiar el propio código de Nexo pasa por estas fases, separadas y visibles, nunca fundidas en un solo paso automático:

1. **OBSERVATION** — algo se ha notado (un fallo repetido, un hallazgo de auditoría, una petición de Damián). Se registra con evidencia (log, traza, commit), no de memoria.
2. **PROPOSAL** — se propone un cambio concreto, en texto, antes de tocar ningún archivo. Igual que `extremidades/triaje.py` PROPONE tareas pero nunca las da de alta sola: la propuesta de mejora nunca se autoaplica.
3. **ANALYSIS** — qué rompe, qué no, qué prueba hace falta. Si toca un archivo blindado (`ARCHIVOS_BLINDADOS`) o el sistema de permisos, es automáticamente `USER_DECISION_REQUIRED`, sin excepción.
4. **APPROVAL** — Damián aprueba (o un turno de Claude decide seguir, si es un cambio de bajo riesgo ya cubierto por las reglas existentes — nunca si toca algo blindado o de seguridad).
5. **IMPLEMENTATION** — un cambio por turno (regla ya en vigor en esta misma auditoría), con `escribir()` (que ya respalda automáticamente antes de sobrescribir).
6. **TEST** — probar de verdad, no suponer. Seguir la disciplina ya existente en el proyecto (`prueba_*.py` por módulo).
7. **DEPLOY** — el cambio entra en uso real (no solo "el código existe": tiene que estar conectado al flujo real, como pide la regla de esta auditoría).
8. **MONITOR** — vigilar que no rompió nada, con evidencia (logs, próximo turno).
9. **ROLLBACK** — si algo se rompe, deshacer con Git (`git checkout -- <archivo>`, ya usado una vez en T035 cuando se pisó `nucleo/estado.py` sin leerlo primero) o restaurando el respaldo automático de `escribir()`.

## Por qué existe esto como documento propio

Porque ya ha pasado (T035, este mismo proyecto): un turno intentó "mejorar" creando un archivo que ya existía, sin leerlo primero, y lo pisó. Se arregló con `git checkout` porque Git ya estaba puesto (T019/K2). Sin esta disciplina de fases separadas, cada mejora es un riesgo de repetir ese incidente.

## Relación con `T016`/`L1` (ejecutar_python sin permisos)

Cualquier auto-mejora que use `ejecutar_python` para "corregir código solo" heredaría automáticamente el mismo agujero de seguridad. Hasta que T016 se resuelva, ninguna auto-mejora debe apoyarse en `ejecutar_python` para modificar el propio sistema sin pasar por las fases de arriba.
