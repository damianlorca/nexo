# A. Matriz completa de requisitos de Nexo

Generado: 12/09/2026, turno de auditoría. Fuente: código real del PC (leído línea a línea esta auditoría), `memoria/tareas.json` (46 tareas, todos los estados), `memoria/*.md`, `docs/*.md`, `memoria/auditoria.md` (auditoría en frío del 10-11/09), y los 5 docs del proyecto NEXO en claude.ai.

**Regla seguida**: código existente NO basta. Para contar IMPLEMENTED/VERIFIED hace falta que esté (1) implementado, (2) probado, (3) integrado, (4) usado de verdad en el flujo real. Si falta cualquiera de los cuatro, cuenta como pendiente en algún grado.

**Estados usados**: IMPLEMENTED · VERIFIED · PARTIALLY_IMPLEMENTED · PLANNED · BLOCKED · REJECTED · NOT_FEASIBLE_YET · NOT_STARTED.

**IDs**: `T0xx` = tarea real de `memoria/tareas.json` (se cita tal cual). `REQ-xxx` = requisito de la especificación maestra / checklist de Damián que hoy NO tiene una tarea propia en la cola (hueco real, no inventado: si más adelante se le da una tarea, hay que enlazarla aquí).

Fuera de alcance en este documento (confirmado repetidas veces en el historial): becas/UPV (T013, T014, T015), Waver (T017), Parity (T018), explicalodamian salvo lo ya cerrado. Se listan al final solo para que no se pierdan de la cola, no se auditan.

---

## 1. Autonomía (ciclo completo objetivo→ejecución→mejora)

### REQ-001 · Bucle de autonomía sostenido (recibir→dividir→asignar→ejecutar→comprobar→corregir→reintentar→escalar→autorizar→terminar→documentar→mejorar)
- **Origen**: especificación maestra (documento de ChatGPT, 11/09) + petición repetida de Damián ("que Nexo funcione todo el tiempo quitándole trabajo").
- **Prioridad**: alta (es el objetivo central del proyecto, ver descripción del proyecto NEXO).
- **Estado**: **PARTIALLY_IMPLEMENTED** (~15-20%).
- **Evidencia**: hoy el bucle completo ocurre DENTRO de un único turno de Claude (este mismo tipo de turno). No hay división automática en subtareas asignadas a otros proveedores, ni reintento/escalado automático fuera de lo que decida un turno de Claude en marcha. `nucleo/tareas.py` da un almacén de 5 estados (`pendiente, en_curso, esperando, bloqueada, aparcada` + cerrados), no la máquina de 10 fases (PENDING/PLANNING/RUNNING/WAITING/WAITING_USER/WAITING_MODEL/BLOCKED/VERIFYING/COMPLETED/FAILED) que pide la especificación.
- **Archivos**: `nucleo/tareas.py`, `nucleo/estado.py` (campo `siguiente_turno`), `canal/vigilante.py` (único proceso que vive siempre, hoy solo relanza el bot).
- **Pruebas realizadas**: ninguna de "bucle completo"; sí hay pruebas de las piezas sueltas (`nucleo/tareas.py`, `nucleo/estado.py`).
- **Dependencias**: Model Router (REQ-010), Message Bus (REQ-011), Planner (REQ-012) — ninguno existe todavía.
- **Motivo pendiente**: construir esto de golpe sería exactamente el tipo de automatismo grande que Damián ha pedido auditar y diseñar antes de tocar, no implementar sobre la marcha.
- **Siguiente acción recomendada**: diseñar en Fase 6 de esta misma auditoría (ver `H_NEXO_MASTER_ARCHITECTURE.md`); no implementar hasta que Damián apruebe el diseño.

### T002 · "Mejorar el sistema Nexo (continua)"
- **Origen**: Damián, 11/09 07:08. Tarea paraguas explícita, no se cierra.
- **Prioridad**: alta (paraguas).
- **Estado**: **PARTIALLY_IMPLEMENTED** (en curso permanente por diseño).
- **Evidencia**: siguiente paso concreto que ella misma marca ("que el bot sepa dar de alta/cerrar tareas desde el móvil") **YA HECHO** (`/tarea`, `/tareas`, `/hecha` en `canal/bot.py`, probado en `prueba_comandos_bot.py`, 9/9).
- **Archivos**: `canal/bot.py`, `nucleo/tareas.py`.
- **Pruebas**: `prueba_comandos_bot.py` (9/9, contra almacén de mentira).
- **Dependencias**: ninguna bloqueante.
- **Siguiente acción**: sigue abierta como paraguas; de aquí salen T005, T027, T029, etc. No cerrar nunca "del todo": es correcto que quede pendiente.

### REQ-002 · Autocuración / detección de fallos / corrección de código autónoma
- **Origen**: checklist de Damián (Fase 1).
- **Prioridad**: media.
- **Estado**: **NOT_STARTED** como capacidad general. Hay piezas reactivas puntuales (p.ej. `extremidades/imagen.py` reinicia ComfyUI solo si un encargo falla; `canal/vigilante.py` relanza el bot si muere), pero ningún mecanismo que lea un log/traceback y proponga o aplique una corrección de código por su cuenta.
- **Evidencia**: no hay ningún módulo de "self-healing" a nivel de código; solo reinicio de procesos concretos ya conocidos.
- **Archivos**: N/A (no existe).
- **Dependencias**: NEXO_SELF_IMPROVEMENT (ver Fase 5, documento propio) — pide explícitamente separar OBSERVATION→PROPOSAL→ANALYSIS→APPROVAL→IMPLEMENTATION→TEST→DEPLOY→MONITOR→ROLLBACK, es decir, nunca autocuración ciega.
- **Siguiente acción**: diseñar el pipeline de auto-mejora (Fase 5, `NEXO_SELF_IMPROVEMENT`) antes de escribir nada que toque código solo.

---

## 2. Comunicación entre IAs / protocolo

### REQ-010 · Model Router (decidir automáticamente Qwen/Gemini/ChatGPT/Claude y, dentro de Claude, modelo/razonamiento)
- **Origen**: especificación maestra + T005/N-04 (Damián, 11/09: "que se proponga el modelo óptimo y se asigne").
- **Prioridad**: alta.
- **Estado**: **PARTIALLY_IMPLEMENTED** (~30%: existe la sugerencia, no la decisión ni la aplicación).
- **Evidencia**: `nucleo/tareas.py::modelo_sugerido()` calcula `sonnet/media`, `sonnet/alta` u `opus/alta` según `peso = 2*dificultad + importancia`, y se muestra al crear la tarea (CLI y bot) — es **informativo**, nadie lo aplica automáticamente. `proveedores.py` (T046) da la interfaz común a los cuatro proveedores, pero tampoco decide cuál usar: solo permite invocarlos con el mismo contrato una vez que YA se ha decidido a mano.
- **Archivos**: `nucleo/tareas.py`, `proveedores.py`.
- **Pruebas**: `prueba_modelo_sugerido.py` (sugerencia), `prueba_proveedores_vivo.py` (100%, los 4 proveedores responden o informan correctamente su estado).
- **Dependencias**: **BLOQUEO DE PLATAFORMA CONFIRMADO** — el modelo/nivel de una Rutina de Claude Code atada a un dispositivo NO se puede cambiar mecánicamente desde fuera (confirmado varias veces, ver T034); solo Damián puede cambiarlo aprobándolo él mismo desde su propio Claude Code. Esto no bloquea decidir entre Qwen/Gemini/ChatGPT/disparar-Claude, pero sí bloquea automatizar Sonnet↔Opus dentro de la rutina.
- **Siguiente acción recomendada**: construir el Router para la decisión "qué proveedor" (sí es viable hoy); dejar la decisión "qué modelo/razonamiento dentro de Claude" como PLANNED hasta que la plataforma lo permita o Damián decida cambiarlo a mano. Consultado a las 4 IAs — ver `G_SINTESIS_MULTI_IA.md`.

### REQ-011 · Message Bus / protocolo de comunicación entre IAs (sender/receiver/task_id/message_type/payload/context/priority/timestamp/status/result/error)
- **Origen**: especificación maestra.
- **Prioridad**: alta.
- **Estado**: **NOT_STARTED** como bus formal. Existe un patrón de archivo+candado reutilizable (`canal/buzon.py` para agente↔móvil), pero nada equivalente entre IAs.
- **Evidencia**: `extremidades/triaje.py` es la única "comunicación entre IAs" real hoy (Qwen clasifica mensajes de Telegram), y es de un solo paso, no encadenada.
- **Archivos**: patrón de referencia en `canal/buzon.py` + `nucleo/candado.py` + `nucleo/escritura.py::escribir_atomico`.
- **Dependencias**: REQ-010 (Model Router) para saber a quién mandar cada paso.
- **Siguiente acción**: ver `G_SINTESIS_MULTI_IA.md` (caso especial D) para la propuesta de estructura mínima.

### REQ-012 · Planner (dividir un objetivo en subtareas)
- **Origen**: especificación maestra.
- **Prioridad**: media-alta.
- **Estado**: **NOT_STARTED**. Hoy la "división en subtareas" la hace un turno de Claude a mano, mentalmente, no hay ningún componente de software que lo haga.
- **Dependencias**: REQ-001, REQ-011.
- **Siguiente acción**: diseño en Fase 6, no implementación aún.

---

## 3. Qwen (modelo local)

### T004 · "Delegar trabajo de verdad en Qwen" — **VERIFIED**
- Evidencia: `extremidades/qwen.py::clasificar()`/`pedir()` en uso real en producción (triaje de mensajes de Telegram desde T032, respuesta libre a mensajes sin turno abierto desde T030). Modelo obrero cambiado de `qwen3:4b` (fallaba, 3/3 respuestas vacías, gasta el presupuesto de tokens "pensando") a `qwen2.5:7b` (0 vacías, 15,9s), medido en `memoria/comparativa_modelos.json`.
- Pruebas: `prueba_qwen.py`, `prueba_qwen_eleccion.py` (33), `prueba_qwen_vivo.py` (14), `prueba_proveedores_vivo.py`.
- Uso real confirmado: `canal/bot.py` (`_avisar_con_qwen`), `extremidades/triaje.py`, demo en vivo del 12/09.

### REQ-020 · Qwen con trabajo "de verdad" más allá de triaje/clasificación
- **Origen**: N-05 (cola.md, 11/09): "aún no se le ha dado ningún trabajo de verdad a las extremidades".
- **Estado**: **PARTIALLY_IMPLEMENTED**. Triaje y clasificación sí son trabajo real y en producción; tareas más ambiciosas (resumir documentos largos, primera pasada de código) no se han asignado todavía.
- **Siguiente acción**: elegir 1-2 tareas concretas nuevas para Qwen (candidata natural: resumir logs largos antes de que un turno de Claude los lea, ya sugerido en `manos/archivos.py::leer()` cuando un archivo supera 400 KB).

---

## 4. Claude (como proveedor, despertar, límites)

### T039 · "Investigar si el bot puede disparar un turno de Claude bajo demanda" — **estado en cola: `pendiente` — DISCREPANCIA DETECTADA, ver abajo**
- **Evidencia real**: la propia nota del 12/09 00:44 dice literalmente *"RESUELTO Y CONFIRMADO VIABLE"*: `canal/bot.py` implementa `/ahora [texto]`, que llama a `_cmd_ahora()` (línea 326), que dispara `POST https://api.anthropic.com/v1/claude_code/routines/{id}/fire` con un token propio de la rutina (no API de pago aparte), facturado contra el plan Claude Code. Commit `3472fb9`. Además, `proveedores.py::ClaudeProvider` (T046, VERIFIED) envuelve exactamente esta misma función y fue probado en vivo hoy (informa `NOT_AVAILABLE` correctamente cuando falta el token, sin gastar plan).
- **Discrepancia de auditoría (a corregir)**: el campo `estado` de T039 en `memoria/tareas.json` sigue en `pendiente` a pesar de que sus propias notas y el commit dicen que está resuelto. Esto es exactamente el tipo de brecha "documentación vs código real" que esta auditoría existe para encontrar.
- **Estado correcto según evidencia real**: **VERIFIED** para "disparar un turno" (probado con `/ahora` real, y `ClaudeProvider` probado en `prueba_proveedores_vivo.py`). El propio token de rutina (`rutina.token_api`/`rutina.id` en `secretos.toml`) sigue sin rellenar en este PC — por eso `ClaudeProvider.disponible()` da `False` hoy — así que en el sentido de "listo para usarse ahora mismo" sigue **BLOCKED** por una acción pendiente de Damián (pegar el token), no por código.
- **Siguiente acción recomendada**: (1) corregir el estado de T039 a `hecha` con nota explicando la discrepancia; (2) `USER_ACTION_REQUIRED`: Damián debe generar el token de la rutina en claude.ai/code/routines y pegarlo en `secretos.toml [rutina]` si quiere usar `/ahora` de verdad (nadie más puede hacerlo por él).

### REQ-030 · Detección de límites/disponibilidad de Claude (cuota 5h y semanal)
- **Origen**: especificación maestra (caso especial B) + caso real T042.
- **Estado**: **NOT_FEASIBLE_YET** con la información disponible hoy, no NOT_STARTED por descuido: se ha buscado y no hay API pública documentada de consulta de cuota.
- **Evidencia del problema real**: T042 — la rutina "Nexo - turno de noche" del 11/09 23:00 apareció como `FAILED` en el historial (disparada 23:00, terminada 00:04, ~64 min), sin log local que lo explique. Damián confirmó el 12/09 mediodía que dentro de esa conversación solo hay un aviso de límite de uso superado hacia las 2am. Conclusión razonable (no probada al 100%): la rutina se cortó por agotar cuota del plan, no por un fallo de Nexo.
- **Lo que sí existe**: `nucleo/uso.py` cuenta turnos PROPIOS (`registrar_turno`/`resumen`, candado, 8/8 pruebas, comando `/uso [dias]` en el bot) — mide cuánto pide Nexo, no cuánto le queda a la cuenta.
- **Archivos**: `nucleo/uso.py`.
- **Dependencias**: sin acceso a una API de cuota, esto depende de encontrar una señal indirecta (ver consulta multi-IA, caso B, en `G_SINTESIS_MULTI_IA.md`).
- **Siguiente acción**: no inventar una API que no existe; usar `nucleo/uso.py` como aproximación de "cuánto hemos gastado nosotros" y aceptar que la detección de límite REAL será siempre reactiva (por un FAILED o un aviso de Damián) salvo que la consulta multi-IA proponga algo mejor.

---

## 5. Gemini y ChatGPT (vía navegador)

### T043 · "Activar Gemini como proveedor real" — **VERIFIED** (commit `0f6bd04`, `56abdf0`)
### T045 · "Verificar y arreglar navegador.py con ChatGPT" — **VERIFIED** (commit `de874ba`, `e6b5ab9`)
- Evidencia conjunta: `extremidades/navegador.py` (Playwright/CDP puerto 9333, perfil `chrome-perfil`, cuenta secundaria `nexoclaude@sepio.net`) probado en vivo hoy con `proveedores.py`: Qwen→"Hola", Gemini→"Hola" (tras `arrancar()`), ChatGPT→"hola". Además usado en la demo en vivo del 12/09 (Gemini generó y descargó una imagen real, enviada por Telegram).
- Guardas ya en código: `class Bloqueo(RuntimeError)` con detector de captcha/bloqueo (`_revisar_bloqueo`), cuenta secundaria dedicada, sin API de pago.
- Limitación conocida y ya documentada: el detector de bloqueo solo escanea los primeros 4000 caracteres de la página (hallazgo L4 de `memoria/auditoria.md`, serie de `navegador.py`) — no re-verificado línea a línea esta sesión, pendiente de una relectura futura de `navegador.py` completo si se quiere cerrar del todo.

### T044 · "Conectar Gemini como proveedor real del Model Router, cuando exista" — **pendiente, correctamente pendiente**
- No es una discrepancia: `GeminiProvider` existe y funciona (T046/T043), pero nada en el flujo de PRODUCCIÓN (bot, turno de noche, triaje) lo invoca todavía para resolver una tarea real de Damián — solo se ha usado en pruebas y en la demo. Por la regla "código existe no basta, tiene que estar USADO", esto es correctamente `PARTIALLY_IMPLEMENTED`, no `IMPLEMENTED`.
- Depende de REQ-010 (Model Router): no tiene sentido conectarlo a un router que no existe.

### REQ-040 · Riesgo de bloqueo de cuenta por volumen de consultas a Gemini/ChatGPT
- **Origen**: preocupación explícita y repetida de Damián (motivo de la propia acotación de esta Fase 3).
- **Estado**: gestionado por PROCEDIMIENTO (volumen bajo, espaciado, nunca desatendido), no por código. No hay ningún limitador automático de tasa en `navegador.py` — el freno es hoy una regla que sigue quien escribe el script (yo), no una barrera en el código.
- **Siguiente acción recomendada**: valorar (no implementar ya) un limitador simple en `extremidades/navegador.py` (p.ej. un contador diario con candado, similar a `nucleo/uso.py`) que impida por código superar un número de consultas/día a Gemini o ChatGPT, en vez de depender solo de la disciplina de quien escribe cada script.

---

## 6. Telegram / comunicación con Damián

### T040 · "Bot con token inválido 401" — **VERIFIED** (cerrada hoy, 12/09)
- Diagnosticada con evidencia primaria (llamada directa a `getMe` de la API de Telegram, no solo releer `secretos.toml`), causa confirmada (`TOKEN` se cachea al importar `canal/bot.py`; el bot llevaba corriendo desde antes del cambio de token) y resuelta con nuevo token verificado en vivo.
- **Lección procedimental registrada** (no técnica): un comando de PowerShell mío (`-replace` tras `Write-Output` en una sola tubería) imprimió el token completo en mi propia salida de herramienta al diagnosticar esto. Nunca llegó a Damián. Recomendé regenerar el token por precaución (hecho). Anotado en `memoria/estado.json` como lección permanente: nunca encadenar un paso de redacción de secretos después de un paso de impresión en una sola línea de PowerShell sin comprobarlo antes.

### REQ-050 · Estructura de mensaje/estado de tareas de 10 fases
- Ver REQ-001. `nucleo/tareas.py` usa 5 estados reales, no los 10 de la especificación. **PARTIALLY_IMPLEMENTED**. No tocar sin decisión explícita de Damián (ya lo pidió así en el historial).

---

## 7. Memoria y persistencia

### Todos VERIFIED, con evidencia de commit y prueba:
- **estado.json atómico + recuperación de corrupción** (D1-D3 de `auditoria.md`): `nucleo/estado.py::cargar()/_recuperar()/_apartar_roto()`, nunca pisa en silencio, recupera de `_respaldos/` si puede. Prueba: `prueba_estado.py` (10 bloques).
- **Candado mecánico para cambios atómicos** (T035): `nucleo/estado.py::actualizar_campos()/anadir_hecho()` bajo `nucleo/candado.py`. Prueba: `prueba_estado_mecanico.py` (10/10). De paso corrigió un bug real de candado en Windows (`PermissionError` vs `FileExistsError` en el hueco de `unlink()`).
- **Candado para tareas.json entre procesos** (T031): `prueba_candado_tareas.py`.
- **Escritura atómica genérica**: `nucleo/escritura.py::escribir_atomico()` (temporal + `os.replace`, con `fsync`), usado por TODO lo que escribe JSON en el proyecto (estado, tareas, uso, triaje, buzón).
- **T035 aún abierta en un punto concreto**: `nucleo/estado.py` sigue SIN conectar al prompt de la rutina de noche (`canal/bot.py`/`canal/vigilante.py` no lo llaman todavía) — la infraestructura está lista y probada, falta el cableado final. **PARTIALLY_IMPLEMENTED**, no cerrada.

### REQ-060 · Poda/mantenimiento de memoria a largo plazo
- `nucleo/uso.py` sí poda solo (90 días). `memoria/estado.json`, `memoria/tareas.json`, `registros/trazas.jsonl` NO tienen poda automática. **NOT_STARTED** para estos tres. Riesgo bajo a corto plazo (tamaños hoy pequeños/medios: tareas.json 66 KB), pero a vigilar.

---

## 8. Permisos y seguridad

### K1 · secretos.toml legible por la herramienta `leer` en verde — **RESUELTO, con matiz nuevo esta auditoría**
- `nucleo/permisos.py::ARCHIVOS_EN_ROJO = ("secretos.toml",)` — `nivel_de_ruta()` da ROJO si el nombre del archivo coincide, sea lectura o escritura. Confirmado leyendo el código actual línea a línea. **VERIFIED como cerrado**, contradice el estado "sin tocar, pendiente de Damián" que aún tiene `memoria/auditoria.md` (documento desactualizado, no incorrecto en su día).
- **Matiz nuevo encontrado esta auditoría (no estaba en K1 original)**: `nivel_de_ruta()` da **VERDE (sin ninguna aprobación) para LECTURA de cualquier ruta absoluta fuera del proyecto** que no sea `secretos.toml` ni esté en `ARCHIVOS_BLINDADOS`. Es decir, `leer()` puede leer cualquier archivo del PC que el usuario de Windows pueda leer, sin pedir permiso, siempre que no se llame `secretos.toml`. No es K1 (que era específico de secretos.toml) ni L1 (que es de ejecución): es un hallazgo nuevo, más amplio de lo que parecía. Ver `REQ-070`.

### K2 · `escribir()` puede reescribir `nucleo/permisos.py` — **MITIGADO, no eliminado**
- Confirmado: `escribir()` a un archivo blindado da AMBAR (pide aprobación), no ROJO — sigue siendo posible con aprobación. La mitigación real es Git (cualquier cambio al núcleo se ve en el diff), no una barrera técnica que lo impida. Commit `a0ef863` dice explícitamente "K1 y K2 cerrados": correcto para K1 (cierre técnico real), impreciso para K2 (sigue siendo "mitigado por proceso", no "cerrado por barrera técnica"). Ajustado aquí.

### T016/L1 · `ejecutar_python` no pasa por el sistema de permisos — **CONFIRMADO ABIERTO, RE-VERIFICADO ESTA AUDITORÍA**
- Leído `manos/servidor_mcp.py` completo hoy: la función `ejecutar_python(ruta, timeout)` NO llama a `exigir()` ni a `nivel_de_ruta()`/`nivel_de_comando()` en ningún punto — a diferencia de TODAS las demás herramientas del mismo archivo (`leer`, `escribir`, `listar`, `archivar`, `comando`, `lanzar` sí pasan por `_envuelto`+el sistema de permisos vía `manos/archivos.py`/`manos/shell.py`).
- **Hallazgo agravado respecto a lo ya sabido**: `ejecutar_python` acepta una ruta absoluta fuera del proyecto sin restricción (`if not archivo.is_absolute(): archivo = RAIZ / archivo` — si YA es absoluta, se usa tal cual, sin comprobar que esté dentro de `RAIZ`). Combinado con `escribir()` (que si puede escribir cualquier `.py` dentro de zona verde, con aprobación si es fuera), esto es ejecución de código arbitrario con el intérprete del proyecto, con **cero comprobación de permisos**, ni siquiera AMBAR.
- **Estado**: **BLOCKED** — anotado en la cola como `esperando` (T016), decisión pendiente de Damián desde el 11/09, explícitamente "no lo cierro sin que decida, porque cerrarlo también ata las manos para el trabajo normal". No se toca sin su aprobación en tiempo real, por instrucción permanente.
- **Siguiente acción**: `USER_DECISION_REQUIRED` (repetido de T016, no nuevo): decidir si `ejecutar_python` debe pasar por el mismo gate de permisos que el resto (con el coste de que algunos scripts de auditoría/prueba legítimos podrían necesitar aprobación), y si debe restringirse a rutas dentro de `RAIZ`.

### B5 · `manos/shell.py::vivo()` llama a `ejecutar(..., aprobado=True)` a mano — **CONFIRMADO ABIERTO**
- Leído `manos/shell.py` completo: `vivo(pid)` hardcodea `aprobado=True`, saltándose el gate para ese caso concreto. Es una puerta trasera limitada (solo permite comprobar si un PID sigue vivo, no ejecutar comandos arbitrarios), pero es exactamente el patrón que K1/K2/L1 buscan evitar. No estaba en el criterio de "5 casos especiales" de Fase 4, así que no se ha consultado a las otras IAs sobre esto — es mecánico y su solución es evidente (quitar el `aprobado=True` y usar el argumento normal), coherente con el criterio de Damián de no consultar IAs para lo obvio.
- **Siguiente acción recomendada**: `USER_DECISION_REQUIRED` menor — confirmar que se puede quitar el `aprobado=True` hardcodeado sin romper nada (revisar quién más llama a `vivo()` primero).

### T024/L6 · El filtro de permisos mira la línea entera, no solo la orden — **CONFIRMADO ABIERTO, sin tocar por diseño**
- Confirmado en el propio texto de la tarea: arreglarlo bien exige un analizador de línea de PowerShell (comillas, tuberías, subexpresiones), no otra expresión regular. Damián mismo lo dejó explícitamente "con pruebas delante o nada, no de madrugada ni con prisa". **NOT_STARTED** por decisión deliberada, no por olvido.

### REQ-070 · Lectura sin restricción de rutas absolutas fuera del proyecto (hallazgo nuevo de esta auditoría, ver K1 arriba)
- **Estado**: **NOT_STARTED** (nadie lo había señalado como problema separado hasta ahora).
- **Siguiente acción**: `USER_DECISION_REQUIRED` — decidir si `leer()`/`listar()` deben poder acceder a rutas fuera de `RAIZ` en absoluto, o si toda lectura fuera de zona verde debería ser AMBAR igual que la escritura.

---

## 9. Imagen, voz, vídeo, papers (extremidades)

### T041 · Imágenes locales con ComfyUI — **VERIFIED**
- `extremidades/imagen.py`: sd-turbo + DirectML + `--lowvram --fp32-vae`, 512px/4 pasos → 12s/imagen (medido). Reinicio automático de ComfyUI ante fallo (necesario porque el cálculo de VRAM de ComfyUI sobre DirectML se degrada tras el primer encargo — comportamiento real de esta GPU, no un bug de Nexo). Usado en producción (`/imagen` en el bot) y en la demo del 12/09 (vía Gemini, no ComfyUI, para mejor calidad).
- Limitación conocida y documentada en el propio código: para publicar, mejor pedir a Gemini; ComfyUI es para bocetos.

### Voz (Piper) — **VERIFIED**
- `extremidades/voz.py::narrar()`. Instalado y probado con audio real de 7s (T011).
- **REQ-080 pendiente**: hallazgo H1 de `auditoria.md` (`narrar()` no comprueba que el WAV se escribiera de verdad) — no re-verificado en código esta sesión, sigue en la lista, prioridad baja.

### Vídeo (FFmpeg) — **PARTIALLY_IMPLEMENTED**
- `extremidades/video.py`: monta ya en vertical desde origen (`lienzo()`, corrige I1). Instalado (T012). No hay evidencia de un vídeo completo de divulgación producido de principio a fin en producción todavía (T007, guiones concretos, es de Damián y está fuera del alcance de esta auditoría de sistema).

### Google Home Mini (altavoz) — **PARTIALLY_IMPLEMENTED**
- T022/T010: descubierto por mDNS, responde TLS en <0,1s, sin instalar nada (`descubrir_altavoces.py`). Camino claro: `pychromecast` + servidor HTTP local + Piper.
- T025 ("Hacer hablar al Google Home mini") sigue **pendiente**: bloqueada en `pip install pychromecast` (ámbar), preguntado, sin respuesta de Damián todavía. `USER_ACTION_REQUIRED` ya existente, no nuevo.

### Papers (investigación académica) — **IMPLEMENTED**, sin evidencia de uso real todavía
- `extremidades/papers.py`: OpenAlex + Semantic Scholar + arXiv + Crossref (mencionado en docstring, sin función propia en el código leído — revisar si Crossref quedó sin implementar o se fusionó, `REQ-090` menor). Reintentos con backoff, deduplicación por DOI. Sin tarea de la cola que lo use en un caso real todavía; código bien escrito y aparentemente listo.

---

## 10. Infraestructura de proceso (arranque, instancia única, logging)

Todos **VERIFIED**, con hallazgos de la auditoría en frío ya corregidos y confirmados en el código actual:
- Instancia única por mutex de Windows (`nucleo/instancia.py`), corrige el incidente real de dos bots simultáneos del 10/09 (A1-A3).
- Vigilante como proceso de arranque (`canal/vigilante.py`) vía acceso directo en la carpeta de Inicio (no `schtasks`, que pedía admin y fue denegado).
- Comportamiento de "2-3 procesos por 1 bot lógico" (lanzador de venv + intérprete real) **ya documentado en `docs/ARRANQUE.md` desde antes** — redescubierto de forma independiente en esta sesión, lo que revela un hueco de indexación: el hecho existía por escrito pero no estaba enlazado desde `memoria/estado.json`, así que una sesión anterior (12/09 13:06) también lo registró como un misterio sin explicar. **`REQ-100`: corregido en esta auditoría con un enlace cruzado explícito** (ver `H_NEXO_MASTER_ARCHITECTURE.md`).
- `manos/shell.py`: `PYTHONUNBUFFERED=1` (L5, cierra salida vacía en logs), sin `| Out-String` en `lanzar()` (L4), `PATHEXT` corregido, `CREATE_BREAKAWAY_FROM_JOB` para sobrevivir al reinicio del servidor MCP por Claude Desktop (hallazgo B1).

---

## 11. Fuera de alcance (listadas solo por trazabilidad, no auditadas)

| ID | Título | Motivo |
|---|---|---|
| T007 | explicalodamian: guiones y tomas | De Damián, contenido, no sistema |
| T013 | Beca general 2026-2027 | Fuera de alcance (becas/UPV) |
| T014 | Beca del máster 2027-2028 | Fuera de alcance |
| T015 | Becas de Colaboración (descartada) | Fuera de alcance |
| T017 | WAVER | Bloqueada, contexto en otro proyecto |
| T018 | Parity (trading) | Aparcada explícitamente por Damián |

---

**Resumen numérico**: 46 tareas reales en la cola (25 hechas, 14 pendientes, 3 descartadas, 2 esperando, 1 bloqueada, 1 aparcada) + 12 requisitos `REQ-xxx` nuevos identificados en esta auditoría que no tenían tarea propia. Detalle de motivos y evidencia de cada uno, arriba por área.
