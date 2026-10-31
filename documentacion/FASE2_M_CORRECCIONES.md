# FASE 2 — Correcciones a la auditoría anterior

Sección explícita pedida por Damián: "afirmaciones de la auditoría anterior que deben corregirse o reverificarse". La auditoría de la Fase 1 (documentacion/A-M, 12/09 tarde) no se trata como verdad absoluta — esto es lo que la evidencia nueva obliga a corregir.

## 0. T039 — corrección central de esta fase

**Lo que decía la auditoría anterior (F_ANALISIS_CLAUDE.md, G_SINTESIS_MULTI_IA.md, memoria/tareas.json nota del 12/09 00:44 y 18:21):** T039 estaba "RESUELTO Y CONFIRMADO VIABLE" — bastaba con que Damián generase un token en `claude.ai/code/routines` y lo pegara en `secretos.toml`.

**Lo que la evidencia real de hoy demuestra:** eso era cierto para el producto "Claude Code Routines" (cloud, con repositorios/entornos/GitHub), documentado en `code.claude.com/docs/en/routines` y `platform.claude.com/docs/en/api/claude-code/routines-fire` — documentación que leí y comparé línea por línea contra `bot.py`, y que coincide exactamente (mismo endpoint, mismas cabeceras, incluida la cadena exacta del beta `experimental-cc-routine-2026-04-01`). **Pero las rutinas de Nexo no son ese tipo de objeto.** Damián confirmó, entrando en modo edición de las dos rutinas reales ("turno de noche" y "turno corto"), que la pantalla solo ofrece: Nombre, Instrucciones, Modelo, Frecuencia, Permisos, "Requerir este ordenador" — sin "Select a trigger", sin "API", sin "Generate token". Son **scheduled tasks ligadas a un dispositivo**, creadas vía `create_trigger`/`update_trigger`/`fire_trigger`/`list_triggers` (las mismas herramientas MCP que yo tengo en esta sesión) — un producto distinto, más simple, sin repositorios ni entornos ni disparador de API.

**Conclusión correcta:** el código de `_cmd_ahora()` en `canal/bot.py` es técnicamente correcto y fiel a la documentación real — pero para el objeto equivocado. No hay ninguna credencial que Damián pueda generar para las rutinas de Nexo tal como existen hoy. La única forma verificada de disparar una de estas rutinas fuera de su horario es `fire_trigger`, una llamada de herramienta MCP utilizable solo desde dentro de una sesión de Claude Code con el conector `claude-code-remote` — no una URL pública con bearer token que un script externo como `bot.py` pueda invocar.

**Qué se conserva:** el código de `/ahora` en `canal/bot.py`, `secretos.ejemplo.toml` y las 9 pruebas de `prueba_comandos_bot.py` NO se borran — son una implementación válida para un tipo de rutina que Nexo podría llegar a tener en el futuro (si algún día se crea una rutina cloud de verdad para otra cosa), y sirven de referencia de cómo se llama correctamente a esa API si hiciera falta. Se documentan como "código correcto, arquitectura inaplicable a las scheduled tasks de dispositivo actuales".

**Qué queda pendiente:** la capacidad "que Damián pida un turno de Claude ya mismo, desde el móvil, sin tener una sesión de Claude Code abierta" no tiene hoy una vía oficial confirmada. Se trata en FASE2_E_CLAUDE_ESTRATEGIA.md como una decisión de arquitectura abierta, no como un bug a corregir.

## 1. El "Model Router" del roadmap anterior estaba subespecificado

`J_ROADMAP_PRIORIZADO.md` y `M_DECISIONES_ARQUITECTONICAS_PENDIENTES.md` mencionaban un "Model Router" como una pieza futura, con la única distinción explícita de "separar qué proveedor de qué modelo/razonamiento dentro de Claude". Tras esta revisión (FASE2_B_MODEL_ROUTER.md) esa distinción sigue siendo válida, pero era incompleta: no contemplaba explícitamente el nivel de esfuerzo/razonamiento, el contexto mínimo, la política de segunda opinión, ni sobre todo la regla "cuándo NO llamar a ningún modelo externo" — que es la pieza que más ahorro puede dar y que no estaba ni mencionada. Se corrige con el diseño completo de la sección B.

## 2. La extensión de Gemini/ChatGPT se documentó como "resuelta" sin cubrir gestión de conversaciones

`documentacion/12_NEXO_PROVIDER_MANUAL.md` (Fase 1) documentó T043/T045 como cerradas ("Gemini y ChatGPT funcionan de verdad") — cierto para el caso de una sola pregunta suelta, pero la auditoría no señaló que `extremidades/navegador.py` **no tiene ningún concepto de proyecto o conversación**: `preguntar()` reutiliza cualquier pestaña ya abierta que coincida con el dominio, o abre una nueva sin ningún criterio de "a qué conversación pertenece esta tarea". Esto no es un hallazgo nuevo de una IA distinta: es una omisión de alcance de la Fase 1, que se centró en verificar que la extracción de texto funcionaba, no en la gestión de sesiones. Se corrige con el diseño de FASE2_C_PROYECTOS_CHATS_PROVEEDORES.md.

## 3. La discrepancia del Caso E (autonomía) sigue abierta, no se resuelve aquí por descarte

`G_SINTESIS_MULTI_IA.md` dejó constancia de una discrepancia real 3 contra 1 (Qwen/Gemini/ChatGPT proponían un vigilante que delega/ejecuta; el análisis propio de Claude proponía uno que solo avisa). Esta revisión (FASE2_I_AUTONOMIA_INCREMENTAL.md) NO cierra esa discrepancia por autoridad — la reevalúa con las piezas nuevas (Model Router, observabilidad, control visual, límites de pasos, kill switch) y ofrece una arquitectura incremental que da cabida a ambas posturas como fases sucesivas, no como una elección entre una u otra. Sigue habiendo una decisión real pendiente de Damián.

## 4. Lo que la auditoría anterior acertó y no cambia

Para que quede claro qué NO se corrige: los hallazgos L1/T016 (bypass de permisos en `ejecutar_python`), REQ-070 (lectura sin restricción fuera del proyecto), y el bug de `navegador.py` con pausas cortas, siguen siendo válidos tal como se documentaron — la evidencia de esta fase los confirma otra vez (se ha vuelto a leer `permisos.py` completo) y no aporta nada que los contradiga. Se retoman en FASE2_J_SEGURIDAD_PERMISOS.md porque condicionan directamente el diseño de autonomía y control visual.
