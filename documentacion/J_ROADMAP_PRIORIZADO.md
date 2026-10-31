# J. Roadmap priorizado

No se implementa nada de esto en esta fase (auditoría + diseño únicamente). Cada ítem lleva objetivo, dependencias, riesgo, dificultad, qué IA debería hacerlo, qué modelo/esfuerzo, si necesita a Damián, criterio de aceptación y prueba necesaria.

## P0 — bloqueos críticos / decisiones que destraban todo lo demás

### P0.1 — Corregir el estado de T039 en la cola
- **Objetivo**: que `memoria/tareas.json` refleje la realidad (T039 resuelta, no pendiente).
- **Dependencias**: ninguna.
- **Riesgo**: ninguno.
- **Dificultad**: trivial.
- **Quién**: Claude (o Nexo por CLI), un turno corto.
- **Modelo/esfuerzo**: Sonnet, baja concentración.
- **Necesita a Damián**: no.
- **Criterio de aceptación**: `T039.estado == "hecha"` con nota explicando la corrección.
- **Prueba necesaria**: releer `memoria/tareas.json` tras el cambio.

### P0.2 — Decisión de Damián: T016/L1 (`ejecutar_python` sin permisos)
- **Objetivo**: cerrar o aceptar conscientemente el mayor agujero de seguridad confirmado.
- **Dependencias**: ninguna técnica; sí de criterio de Damián.
- **Riesgo de NO decidir**: ejecución arbitraria de código sigue abierta indefinidamente.
- **Riesgo de decidir mal** (cerrarlo mal): romper scripts de auditoría/mantenimiento legítimos.
- **Dificultad**: media (analizar quién usa `ejecutar_python` hoy antes de meterlo en el gate).
- **Quién**: Damián decide; Claude implementa si se aprueba.
- **Necesita a Damián**: **sí, imprescindible.**
- **Criterio de aceptación**: decisión documentada en `memoria/tareas.json` (T016), con el motivo.
- **Prueba necesaria**: si se cierra, `prueba_*` que confirme que `ejecutar_python` ahora exige permisos como el resto.

### P0.3 — Decisión de Damián: token de Rutina en `secretos.toml`
- Ya está en `K_ACCIONES_DAMIAN.md` punto 1. Sin esto, `/ahora` sigue sin poder usarse de verdad.

## P1 — piezas base para autonomía real

### P1.1 — Model Router (versión mínima: solo "qué proveedor")
- **Objetivo**: `elegir_proveedor(tarea) -> str` según dificultad/importancia/urgencia/necesidad de herramientas (ver diseño en `F_ANALISIS_CLAUDE.md` y `G_SINTESIS_MULTI_IA.md`).
- **Dependencias**: ninguna (usa datos que ya existen en `nucleo/tareas.py`).
- **Riesgo**: bajo (función pura, fácil de probar).
- **Dificultad**: baja-media.
- **Quién**: Claude, un turno.
- **Modelo/esfuerzo**: Sonnet, concentración media.
- **Necesita a Damián**: no para esta versión mínima (sí para la parte "modelo dentro de Claude", que queda fuera de esta primera versión).
- **Criterio de aceptación**: función pura + pruebas cubriendo los 4 casos (mecánico→Qwen, razonar sin herramientas→Gemini/ChatGPT, necesita PC→Claude).
- **Prueba necesaria**: `prueba_model_router.py` (nueva), casos claros y casos límite.

### P1.2 — Protocolo mínimo de comunicación entre IAs
- **Objetivo**: carpeta `canal/entre_ias/` con la estructura de mensaje acordada (ver `M_DECISIONES_ARQUITECTONICAS_PENDIENTES.md` punto 4).
- **Dependencias**: P1.1 (para saber a quién enviar cada paso).
- **Riesgo**: bajo (mismo patrón ya probado en `canal/buzon.py`).
- **Dificultad**: media.
- **Quién**: Claude.
- **Necesita a Damián**: confirmar el formato exacto antes de construirlo (decisión de diseño, no bloqueo técnico).
- **Criterio de aceptación**: dos proveedores encadenados de verdad en una prueba controlada (p.ej. Qwen resume → Claude revisa), con archivo de traza legible.
- **Prueba necesaria**: prueba de extremo a extremo con un caso real y pequeño.

### P1.3 — Vigilante que avisa (primer paso de autonomía sostenida)
- **Objetivo**: `canal/vigilante.py` lee `estado.json::siguiente_turno` y avisa por Telegram si hay algo pendiente sin tocar hace tiempo, SIN actuar solo.
- **Dependencias**: ninguna técnica.
- **Riesgo**: bajo (solo avisa, no ejecuta).
- **Dificultad**: baja.
- **Quién**: Claude.
- **Necesita a Damián**: confirmar que quiere este primer paso conservador antes de nada más ambicioso.
- **Criterio de aceptación**: un aviso real llega por Telegram cuando se simula una tarea pendiente antigua.

## P2 — mejoras de fiabilidad ya identificadas

### P2.1 — Corregir/paliar el desajuste de extracción en `navegador.py` para conversaciones encadenadas
- **Objetivo**: que preguntas seguidas a Gemini/ChatGPT no capturen la respuesta de la pregunta anterior (hallazgo nuevo de esta auditoría, Fase 3).
- **Riesgo**: bajo, pero afecta a la fiabilidad de cualquier uso futuro con varias preguntas seguidas.
- **Dificultad**: media (tocar la lógica de espera/estabilidad de `_extraer_respuesta`, o abrir conversación nueva por pregunta).
- **Quién**: Claude, consultando si hace falta a Gemini/ChatGPT sobre su propio comportamiento de UI (irónico, pero válido).
- **Necesita a Damián**: no debería, es un bug de fiabilidad, no una decisión de diseño.
- **Criterio de aceptación**: 5 preguntas seguidas y espaciadas a Gemini, cada respuesta corresponde a su propia pregunta.

### P2.2 — B5 (`vivo()` con `aprobado=True` hardcodeado)
- Confirmar quién lo usa, quitar el hardcodeo. Bajo riesgo, baja dificultad.

### P2.3 — REQ-070 (lectura sin restricción fuera del proyecto)
- Decisión de Damián primero (`M` punto pendiente), luego implementación si se aprueba.

## P3 — piezas de producto pendientes de decisión de Damián, no de diseño

- T025 (pychromecast / Google Home Mini).
- T037 (Wake-on-LAN / encendido remoto).
- T034 (Sonnet vs Opus turno de noche).
- T024/L6 (analizador de línea de PowerShell) — explícitamente "con calma, con pruebas, no de madrugada".

## P4 — mejoras futuras, sin prisa

- Poda automática de `memoria/estado.json`/`memoria/tareas.json`/`registros/trazas.jsonl` (REQ-060).
- Sincronización automática de `memoria/auditoria.md` con el código (propuesta en `H_NEXO_MASTER_ARCHITECTURE.md`).
- Máquina de 10 estados de tareas de la especificación maestra (no tocar sin que Damián lo pida expresamente).
- Pipeline completo de auto-mejora (`09_NEXO_SELF_IMPROVEMENT.md`) más allá del diseño ya escrito.
- Nuevas tareas reales para Qwen más allá de triaje (REQ-020).
