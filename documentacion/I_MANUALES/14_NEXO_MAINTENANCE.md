# I.14 NEXO_MAINTENANCE

## Rutinas de mantenimiento que YA existen

- `nucleo/uso.py`: poda automática a 90 días.
- `nucleo/escritura.py::limpiar_temporales()`: barre `.tmp` huérfanos de un corte anterior (no se ha confirmado en esta auditoría que algo la llame periódicamente — candidato a revisar).
- Respaldo automático antes de cualquier `escribir()` que sobrescriba (`_respaldos/<fecha>/`).

## Lo que requiere revisión periódica manual (no automatizada todavía)

- **`memoria/auditoria.md` vs código real**: se desincronizó en 5 de ~33 hallazgos entre el 11/09 y el 12/09 simplemente porque nadie la revisó al cerrar cada hallazgo. Recomendación: revisarla contra el código cada vez que se cierre un hallazgo de seguridad, no solo en auditorías grandes como esta.
- **Tamaño de `memoria/tareas.json`** (66 KB con 46 tareas): sin poda todavía. Vigilar si crece mucho más.
- **`registros/trazas.jsonl`**: crece sin límite, sin candado entre escrituras concurrentes (hallazgo M2 de la auditoría en frío, no re-verificado esta sesión).
- **Consistencia `estado` vs `notas` en tareas** (ver T039 en esta misma auditoría): una tarea puede quedar con el campo `estado` desactualizado aunque sus notas digan que está resuelta. No hay ninguna comprobación automática de esto. Candidato a una pequeña utilidad de "salud de la cola" (listar tareas cuya última nota contenga palabras como "resuelto"/"cerrado"/"hecho" pero cuyo estado siga en `pendiente`).

## Checklist de mantenimiento recomendado (mensual, manual, no automatizado)

1. `git log --oneline` desde la última revisión: ¿algún cambio a un archivo blindado sin que se recuerde haberlo aprobado?
2. Tamaño de `memoria/tareas.json`, `memoria/estado.json`, `registros/trazas.jsonl`.
3. Tareas `pendiente`/`esperando`/`bloqueada` con más de N semanas sin nota nueva.
4. Releer `memoria/auditoria.md` y tachar lo que el código ya haya resuelto desde la última vez.
