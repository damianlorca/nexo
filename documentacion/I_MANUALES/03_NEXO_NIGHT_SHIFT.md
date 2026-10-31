# I.3 NEXO_NIGHT_SHIFT

## Configuración actual (verificada)

Una única Rutina activa, "Nexo - turno de noche", programada a las 23:00, modelo `claude-opus-5` (T034: cambiarlo a Sonnet está pendiente de que Damián lo haga desde su propio Claude Code — no se puede parchear desde dentro). El turno de día corto se desactivó por decisión de Damián (ver historial, commit `c2fec6e`).

## Lo que hace el turno de noche

1. Lee `extremidades/triaje.py` (Qwen ya clasificó los mensajes libres, en vez de que el turno los lea en crudo — T032, ahorra tokens).
2. Trabaja la cola de tareas (`nucleo/tareas.py`) por prioridad.
3. Al terminar cada paso, registra su propio turno en `nucleo/uso.py` (modelo en duro en el prompt: `claude-opus-5`, hay que actualizarlo a mano si Damián cambia el modelo de la rutina).
4. Dejar `memoria/estado.json::siguiente_turno` con lo que el siguiente turno necesita saber sin releer todo el historial.

## Incidente conocido: T042 (FAILED, 11/09 23:00→00:04)

La rutina apareció como `FAILED` sin log local que lo explique. Evidencia indirecta (aviso de límite de uso hacia las 2am, reportado por Damián): probablemente se agotó la cuota del plan, no un bug de Nexo. No cerrada del todo hasta confirmarlo una noche más sin que se repita. Ver `A_MATRIZ_REQUISITOS.md` REQ-030 para la falta de detección preventiva de este mismo problema.

## Reglas de silencio nocturno

`buzon.avisar(silencioso=True)` para el resumen de la noche: llega al chat sin sonido ni vibración, pero está esperando cuando Damián se despierte. Nunca despertarlo salvo urgencia real (marcador `urgente=True`).

## Riesgo de colisión

Si alguna vez hay dos turnos a la vez (turno de noche + `/ahora` disparado a la misma hora), ya se ha visto que se pisan la memoria (incidente documentado, T026). Recomendación de esta auditoría (ver `F_ANALISIS_CLAUDE.md`): encolar, no paralelizar.
