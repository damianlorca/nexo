# T1020 pieza 4: `motivo` en las herramientas de las «manos» (manos/servidor_mcp.py, BLINDADO)

**Estado: HECHO SIN APLICAR.** Probado en un worktree aparte; falta que lo veas y lo apliques tú.

## Qué cambia, en llano
1. Las herramientas que pueden pedir permiso (`comando`, `lanzar`, `ejecutar_python`, `escribir`, `leer`, `listar` y
   `archivar`) aceptan `motivo`: una frase de para qué lo pide quien lo pide. Se guarda en la solicitud
   (`extra.motivo`, que no entra en la huella) y sale en la ficha («Quién lo pide y para qué») y en lo que lee el
   tribunal. Sin motivo, la ficha dice «No lo ha dicho».
2. Si la solicitud ya sale **aprobada** de la cola (el guardián la aprobó al entrar porque solo lee, o tú ya
   aprobaste esa misma acción exacta), se gasta en ese momento y la orden se ejecuta sin esperar. Hoy, aunque el guardián
   apruebe una lectura como la A0064, quien la pidió tiene que volver a llamar con `aprobacion_id`.
3. El aviso de «NECESITA APROBACION» de `leer`/`listar`/`archivar` dice además en qué estado quedó la solicitud.

No cambia nada de lo rojo (sigue bloqueado) ni de lo ámbar que no esté aprobado: sin aprobación no se ejecuta nada.

## Qué NO hace (queda para después)
`leer` fuera de las carpetas de NEXO (como la A0066) sigue sin poder usar una aprobación: `manos/archivos.leer` no
acepta `aprobado`. El guardián ya la aprueba y deja de molestarte, pero quien la pidió no puede leer el archivo
hasta que se toque también `manos/archivos.py` (otro blindado).

## Base
Hecho encima de T1023 (commit ae5c168, `lanzar()` con el envoltorio de la guardia y sus dos tests), que ya está en
`principal`. `git apply --check` pasa sobre `principal` tal como está.

## Cómo se probó
Worktree del scratchpad con el estado del disco + el parche; `mcp` sacado de la caché de uv sin descargar nada (en
`.venv` no está, por eso estos tests se saltan en la suite normal):
`tests/test_enganche_aprobaciones.py` 19 passed (3 nuevos: el motivo queda en la solicitud y no en la huella; lo que
aprueba el guardián se ejecuta a la primera; `leer` fuera de zona guarda el motivo) y `tests/test_t1020_guardian.py`
51 passed.

## Para aplicarlo
```
git apply documentacion/diffs/T1020_servidor_mcp_motivo.patch
```
Después hay que reiniciar el servidor MCP (el proceso viejo sigue sirviendo el código anterior; ver docs/ARRANQUE.md).
