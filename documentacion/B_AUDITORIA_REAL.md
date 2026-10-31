# B. Auditoría real (Fase 2)

Regla seguida: nada se afirma sin evidencia. Cada punto cita el archivo/línea, el commit o la prueba que lo respalda. Esta auditoría se hizo leyendo el código actual del PC en vivo (12/09/2026), no repitiendo lo que decía la documentación previa.

## B.1 — Reconciliación con `memoria/auditoria.md` (la auditoría en frío del 10-11/09)

`memoria/auditoria.md` sigue siendo un documento válido y útil (no se borra, se referencia), pero tres de sus hallazgos están **desactualizados respecto al código actual**:

| Hallazgo | Estado en `auditoria.md` | Estado real confirmado hoy (12/09) | Evidencia |
|---|---|---|---|
| K1 (secretos.toml legible en verde) | "ANOTADO, sin tocar, pendiente de Damián" | **CERRADO** | `nucleo/permisos.py`: `ARCHIVOS_EN_ROJO = ("secretos.toml",)`, `nivel_de_ruta()` devuelve ROJO incondicionalmente para ese nombre. Commit `a0ef863` ("K1 y K2 cerrados"). |
| K2 (escribir puede reescribir permisos.py) | "ANOTADO, sin tocar" | **MITIGADO** (no eliminado: sigue siendo posible con aprobación AMBAR; la protección real es el diff de Git, no una barrera técnica) | `nucleo/permisos.py`: `ARCHIVOS_BLINDADOS`/`_es_blindado()` da AMBAR, no ROJO, para escribir sobre los 6 archivos blindados. |
| L2/L3 (lista ámbar sin cubrir descargas/schtasks) | "pendiente" | **CERRADO** | `nucleo/permisos.py`: regex `AMBAR` ya cubre `Invoke-WebRequest/iwr/irm/curl/wget/certutil...urlcache/downloadfile/downloadstring` y `schtasks/Register-ScheduledTask/New-ScheduledTask/...`. |
| L4 (`| Out-String` vacía el log de `lanzar()`) | "pendiente" | **CERRADO** | `manos/shell.py`: comentario explícito en el código "L4: nada de \| Out-String aquí", confirmado en la implementación de `lanzar()`. |
| L5 (buffering de Python) | "pendiente" | **CERRADO** | `manos/shell.py::_entorno()`: `PYTHONUNBUFFERED=1` presente. |

No desactualizados, siguen abiertos tal cual los describe `auditoria.md`:

| Hallazgo | Estado |
|---|---|
| L1 (`ejecutar_python` sin permisos) | **ABIERTO**, releído hoy línea a línea en `manos/servidor_mcp.py`: confirmado, y agravado (acepta rutas absolutas fuera del proyecto sin restricción). Es T016. |
| B5 (`vivo()` con `aprobado=True` hardcodeado) | **ABIERTO**, releído hoy en `manos/shell.py`. |
| E2 (buzón.py/bot.py con escritura no atómica en algún punto) | no re-verificado esta sesión, se mantiene como estaba. |
| H1/H2 (voz/extremidades sin comprobar escritura) | no re-verificado esta sesión, se mantiene. |
| I2 (limpieza de temporales de vídeo) | no re-verificado esta sesión. |
| M1/M2 (logs por apertura, trazas.jsonl sin lock) | no re-verificado esta sesión. |

**Conclusión de esta reconciliación**: `memoria/auditoria.md` no está mal escrito, está desactualizado en 5 de sus ~33 hallazgos porque el código avanzó después de escribirse y nadie volvió a marcarlos. Esto es en sí mismo un hallazgo de proceso: **no hay ningún mecanismo que mantenga la auditoría sincronizada con el código** — cada vez que se cierra un hallazgo hay que acordarse de ir a editar el documento a mano. Se propone en `H_NEXO_MASTER_ARCHITECTURE.md` que el propio `nucleo/permisos.py` (o un test) declare qué hallazgos cierra, para que no vuelva a desincronizarse.

## B.2 — Verificación línea a línea de `manos/servidor_mcp.py` (hoy, evidencia nueva)

Leído completo. Confirma:

- Las 4 herramientas de archivos (`listar`, `leer`, `escribir`, `archivar`) pasan TODAS por `manos/archivos.py`, que llama a `exigir(nivel_de_ruta(...))` antes de tocar nada. Verificado en `manos/archivos.py`: cada función (`listar`, `leer`, `escribir`, `archivar`) tiene su línea `exigir(nivel_de_ruta(...), ...)` antes de actuar.
- `comando()` y `lanzar()` pasan por `manos/shell.py::ejecutar()`/`lanzar()`, que llaman a `nivel_de_comando()`+`exigir()` salvo que se pase `aprobado=True` explícitamente desde fuera (uso correcto: el propio Claude repite la llamada con `aprobado=True` tras que Damián lo apruebe).
- `ejecutar_python()` (dentro del propio `servidor_mcp.py`, no en un módulo de `manos/`) **NO llama a `exigir()` en ningún punto de su código**. Resuelve la ruta, comprueba que exista, y ejecuta directamente con `subprocess.run([shell.python_del_proyecto(), str(archivo)], ...)`. Es la única herramienta de las 8 que no pasa por el sistema de permisos.
- `proceso_vivo()` llama a `shell.vivo(pid)`, que en `manos/shell.py` está definida como `ejecutar(f"...", aprobado=True)` — con el `aprobado=True` escrito en el propio código fuente, no pasado por quien llama. Confirma B5.

## B.3 — Verificación del `venv launcher stub` (proceso "duplicado")

Redescubierto de forma independiente esta sesión (comparando `.venv/pyvenv.cfg` con `Get-CimInstance Win32_Process` y las cadenas de `ParentProcessId`) que 2-3 filas de proceso para `bot.py`/`vigilante.py` son un único bot lógico: `.venv\Scripts\python.exe` es un lanzador que Windows/venv reexecuta como hijo con el intérprete base de `pyvenv.cfg` (`home = C:\Users\damia\AppData\Local\Programs\Python\Python311`). **Confirmado que esto ya estaba documentado en `docs/ARRANQUE.md`** con la misma explicación casi palabra por palabra. Hallazgo de proceso: este hecho no estaba enlazado desde `memoria/estado.json`, así que se ha investigado como un misterio dos veces (12/09 13:06 y de nuevo en esta auditoría) antes de encontrar que ya estaba escrito. Corregido con un enlace cruzado en `H_NEXO_MASTER_ARCHITECTURE.md`.

## B.4 — Verificación de `nucleo/permisos.py` completo (hoy)

Confirmado por lectura directa: clases `Nivel` (VERDE/AMBAR/ROJO), excepciones `Bloqueado`/`NecesitaAprobacion`, regex de `ROJOS` (formatear disco, diskpart, cipher /w, bcdedit, shutdown, vssadmin delete, reg delete hklm), `BORRADO` (remove-item, clear-recyclebin, del, erase, rd /s, rmdir /s, rm -rf) — ambos enrutan a ROJO —, `AMBAR` (gestores de paquetes, git push, descargas, persistencia de arranque, configuración de sistema). Todo con regex ancladas por palabra, no subcadenas (corrige el bug histórico donde frases con "del" disparaban falsos positivos en patrones de borrado).

## B.5 — Verificación de infraestructura de escritura y candados (hoy)

`nucleo/escritura.py::escribir_atomico()`: temporal en la MISMA carpeta (necesario para que `os.replace` sea atómico dentro del mismo volumen), `fsync` antes del `replace`, limpieza del temporal si algo falla a mitad. Usado consistentemente por `manos/archivos.py`, `nucleo/estado.py`, `nucleo/uso.py`, `canal/buzon.py`, `extremidades/triaje.py`.

`nucleo/candado.py`: candado de archivo con `O_CREAT|O_EXCL` (atómico a nivel de sistema de archivos, portable Windows/Linux), con robo de candados huérfanos tras 30s (protege contra el caso ya confirmado de que Claude Desktop mata el servidor MCP sin avisar, dejando candados a medio soltar). Usado por `nucleo/estado.py` y `nucleo/uso.py` para cambios mecánicos.

## B.6 — Tareas: discrepancia de estado detectada (T039)

Ver detalle completo en `A_MATRIZ_REQUISITOS.md` sección 4. Resumen: el campo `estado` de T039 en `memoria/tareas.json` dice `pendiente`, pero sus propias notas y el commit `3472fb9` confirman que el disparo de rutina bajo demanda está implementado, probado y documentado como "RESUELTO Y CONFIRMADO VIABLE". Es una tarea a la que se le olvidó actualizar el campo `estado` tras cerrarla en las notas — un fallo de proceso, no de código.

## B.7 — Lo que esta auditoría NO pudo verificar con evidencia completa (limitaciones honestas)

- **Cobertura de `_revisar_bloqueo()` de `navegador.py`** más allá de lo ya documentado en `auditoria.md` (L4 de esa serie: solo escanea los primeros 4000 caracteres): no se releyó el archivo completo esta sesión (sí en una sesión anterior, para el trabajo real de T043/T045). No se afirma que siga roto ni que esté arreglado sin releerlo; queda como pendiente de re-verificación, no como hallazgo cerrado.
- **E2, H1, H2, I2, M1, M2** de `auditoria.md`: no releídos línea a línea esta sesión por límite de tiempo/alcance; se mantiene lo que ya decía la auditoría en frío, citado tal cual en B.1.
- **Cuota real de Claude Code**: no hay forma de comprobar desde el código si existe o no una API de consulta de cuota no documentada; lo que se afirma en `A_MATRIZ_REQUISITOS.md` (REQ-030) es que no se ha encontrado ninguna, no que sea imposible que exista.

## B.8 — Documentación existente inspeccionada antes de escribir nada nuevo (regla de Damián)

Inspeccionados antes de crear esta carpeta `documentacion/`: `docs/ARRANQUE.md`, `docs/TELEGRAM.md`, `memoria/auditoria.md`, `memoria/claude_organizacion.md`, `memoria/historial.md`, `memoria/cola.md`, `memoria/altavoz.md`, y los 5 documentos del proyecto NEXO en claude.ai. Ninguno se borra ni se duplica: los master documents de la Fase 5 (`H`/`I`) enlazan a estos en vez de repetir su contenido. `memoria/cola.md` está desactualizado (usa una numeración `B-01/N-01/I-01` distinta de los `T0xx` actuales de `nucleo.tareas`, y no se ha tocado desde el 11/09) — se conserva por trazabilidad histórica, se marca aquí como superseded por `memoria/tareas.json`, no se borra.
