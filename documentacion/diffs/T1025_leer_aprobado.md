# T1025: leer con aprobación fuera de las carpetas de NEXO (manos/archivos.py y manos/servidor_mcp.py, BLINDADOS)

**Estado: HECHO SIN APLICAR.** Probado en una copia aparte; falta que lo veas y lo apliques tú.

## Qué pasa hoy
Leer un archivo fuera de las carpetas de NEXO (por ejemplo `herramientas_externas\MiroFish\.env.example`, la A0066)
es ámbar: sale una solicitud y el guardián la aprueba porque solo lee. Pero la herramienta `leer` de las manos no
tiene forma de usar esa aprobación (`manos/archivos.leer` no acepta `aprobado`), así que la lectura nunca llega a
hacerse: quien la pidió se queda igual y tú ves solicitudes aprobadas que no sirven para nada.

## Qué cambia, en llano
1. `manos/archivos.leer` acepta `aprobado=True`, igual que `escribir` desde T861: salta el **ámbar** y **nunca el
   rojo**. `secretos.toml` sigue bloqueado aunque haya una aprobación.
2. La herramienta `leer` del servidor MCP pasa por la misma puerta que `escribir`: pide la aprobación atada a **esa
   ruta exacta**, acepta `aprobacion_id` y la gasta al usarla (una aprobación sirve una vez y solo para esa ruta).
   Si el guardián la aprueba al entrar (lo que solo lee en el repo o en `herramientas_externas`), se lee a la primera,
   sin volver a llamar.

Lo que hoy es verde (las carpetas de NEXO) sigue igual, sin solicitud. Lo que hoy es rojo sigue rojo. Sin aprobación no
se lee nada de fuera.

## Qué NO hace
- `listar` fuera de las carpetas de NEXO tiene el mismo hueco (ámbar sin forma de usar la aprobación). No lo toco aquí
  porque no se pidió; sería el mismo patrón.
- El servidor MCP que está corriendo sigue con el código viejo hasta que lo reinicies.

## Cómo se probó
Copia aparte (worktree en el scratchpad de la sesión, sin `secretos.toml`) con el parche aplicado y `mcp` 1.24.0
sacado de la caché de uv sin descargar nada (en `.venv` no está):
`tests/test_enganche_aprobaciones.py`, `tests/test_t1025_leer_aprobado.py`, `tests/test_t1020_guardian.py` y
`tests/test_revisor.py`: **154 passed**. Los nuevos:
- sin id, pide la aprobación y no lee (la solicitud lleva la ruta y el motivo);
- con el id aprobado lee esa ruta una sola vez; con otra ruta, el id no vale y no se gasta;
- el caso A0066: el guardián aprueba al entrar y se lee a la primera (`decidida_por=guardian`, estado `usada`);
- `secretos.toml` con un id: BLOQUEADO (rojo), sin solicitud y sin leer;
- `archivos.leer`: ámbar sin aprobar pide aprobación, aprobado lee, el rojo nunca pasa, lo de NEXO no cambia.

En la suite normal estos tests se **saltan solos** hasta que el parche esté aplicado (igual que los de T861).
`git apply --check` pasa sobre `principal` tal como está.

## Para aplicarlo
```
git apply documentacion/diffs/T1025_leer_aprobado.patch
```
Después hay que reiniciar el servidor MCP (el proceso viejo sigue sirviendo el código anterior; ver docs/ARRANQUE.md).
