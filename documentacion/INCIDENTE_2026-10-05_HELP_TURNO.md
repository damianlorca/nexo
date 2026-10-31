# Incidente 05/10/2026 17:01: `turno_nexo.py --help` arrancó un turno real

## Qué pasó
- Una sesión de Claude Code ejecutó `turno_nexo.py --help` para ver su ayuda. El script no atendía `--help`
  (lo ignoraba) y arrancó un turno REAL, plantilla `cola`, sobre **T699** (investigar prime-agent).
- Se cerró con `taskkill /PID ... /T` y con `/T` cayó también un proceso hijo sin identificar (PID 17860).

## Qué dicen los registros (evidencia)
- `registros/turno_nexo_20261005_170344.json`: inicio 17:01:26, sin `turno_id` (lanzado a mano), abortado:
  "el turno murio sin dejar registro: ultimo latido hace 18 s, en el paso 'trabajo', tarea T699".
- `registros/trazas.jsonl` y `uso_proveedores.jsonl`: ChatGPT web respondió como autor (OK, 17:02:53, 5045 car.).
- `registros/agente_20261005.log`: 17:03:04-17:03:37 empezaba a preguntar a Gemini web (revisor) cuando murió.
- `registros/chrome_nexo.lock.quien`: "pid 14712 desde 17:02:58 (preguntar a gemini)". 14712 era el turno.
- **PID 17860: no aparece en ningún registro** (`registros/`, `memoria/*.json`, `canal/*.json`). No se puede saber
  con certeza qué era. Hipótesis más probables (sin comprobar): (1) el intérprete real de Python, porque
  `.venv\Scripts\python.exe` en Windows es un lanzador que crea el intérprete base como proceso hijo; (2) el
  `conhost.exe` de la consola. El turno no lanza procesos propios: en su cadena (turno_nexo, trabajo, navegador,
  proveedores) no hay `subprocess`, y el Chrome de NEXO ya estaba abierto (no era hijo del turno).

## Qué quedó a medias
- **T699**: sigue `pendiente`; solo guarda la conversación de ChatGPT (`conversaciones.chatgpt:autor`), que el
  siguiente turno reutilizará. No se guardó borrador ni hay nada de T699 en `memoria/borradores`.
- `chrome_nexo.lock.quien` quedó con el pid 14712 (solo informativo: el turno de las 18:00 usó Chrome sin problema).
- La pestaña de Gemini pudo quedarse con una pregunta enviada sin leer (inocuo).
- No hay cambios en `memoria/` de ese turno entre 17:01 y 17:05 (los del radar de las 17:04 son de otra sesión).

## Prevención
1. `nucleo/ayuda.py`: `ayuda.atender(__doc__)` como primera línea del `__main__` de cada script de entrada →
   `-h`, `--help` o `/?` imprimen el docstring y salen con 0 sin ejecutar nada.
   La edición de los 44 scripts la bloqueó el clasificador del modo automático ("Self-Modification"), así que va
   como parche verificado: `documentacion/propuestas/ayuda_entradas_0510.patch` (44 scripts + `tests/test_ayuda_entradas.py`).
   Probado en un worktree temporal: 53 tests en verde con el parche; sin la guarda en `turno_nexo.py`, 1 en rojo;
   `python -m nucleo.mapa --help` y `python -m nucleo.tareas -h` imprimen la ayuda (exit 0).
   Aplicar: `git apply documentacion/propuestas/ayuda_entradas_0510.patch`, después pytest.
   Fuera del parche: `manos/servidor_mcp.py` (blindado), `extremidades/arrancar_comfyui.py` y
   `documentacion/propuestas/aplicar_n01.py` (no pueden importar `nucleo`). Ya atendían -h: `interfaz/vigia.py`,
   `herramientas_nube/publicar_nube.py` (argparse) y `nucleo/freno.py`.
2. Regla en `CLAUDE.md`: nunca ejecutar un script para "ver su ayuda" sin comprobar antes en el código que la
   tiene; `taskkill /T` solo después de identificar a todos los hijos (PID y línea de comando).
