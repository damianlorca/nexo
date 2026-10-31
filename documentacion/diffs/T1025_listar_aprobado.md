# T1025 (2): listar con aprobación fuera de las carpetas de NEXO (manos/archivos.py y manos/servidor_mcp.py, BLINDADOS)

**Estado: HECHO SIN APLICAR.** Probado en una copia aparte; falta que lo veas y lo apliques tú. Es el compañero de
`T1025_leer_aprobado.patch` (el de `leer`, ya aprobado): mismo patrón, para `listar`.

## Qué pasa hoy
Listar una carpeta fuera de las carpetas de NEXO (por ejemplo `herramientas_externas\MiroFish`) es ámbar: sale una
solicitud y el guardián la aprueba porque solo mira nombres de archivo. Pero la herramienta `listar` no puede usar
esa aprobación, así que el listado nunca llega.

## Qué cambia, en llano
1. `manos/archivos.listar` acepta `aprobado=True`: salta el **ámbar** y **nunca el rojo**.
2. La herramienta `listar` del servidor MCP pasa por la misma puerta que `leer` y `escribir`: la aprobación va atada a
   **esa carpeta** (el detalle es la carpeta, igual que hoy), acepta `aprobacion_id` y se gasta al usarla. Lo que el
   guardián aprueba al entrar se lista a la primera.

Las carpetas de NEXO siguen igual (verde, sin solicitud). Una aprobación vale para listar esa carpeta una vez, con el
patrón que se pida (el listado ya era recursivo).

## Cómo se probó
Copia aparte (worktree en el scratchpad, sin `secretos.toml`) con los DOS parches aplicados (`leer` y después
`listar`) y `mcp` 1.24.0 sacado de la caché de uv, sin descargar nada: `tests/test_enganche_aprobaciones.py`,
`tests/test_t1025_leer_aprobado.py`, `tests/test_t1020_guardian.py` y `tests/test_revisor.py`: **157 passed**. Los
nuevos: sin id pide la aprobación y no lista; con el id lista esa carpeta una sola vez y otra carpeta no vale; lo que
el guardián aprueba se lista a la primera; `archivos.listar` ámbar sin aprobar pide y aprobado lista.

En la suite normal estos tests se saltan solos hasta que el parche esté aplicado. `git apply --check` pasa sobre
`principal` tal como está y también después del parche de `leer`.

## Para aplicarlo (después del de leer, o solo)
```
git apply documentacion/diffs/T1025_leer_aprobado.patch
git apply documentacion/diffs/T1025_listar_aprobado.patch
```
Después hay que reiniciar el servidor MCP (el proceso viejo sigue sirviendo el código anterior; ver docs/ARRANQUE.md).
