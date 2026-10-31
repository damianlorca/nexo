# FASE 6 — Índice: auditoría técnica de recursos (antes de la Pieza 0)

Auditoría pedida por Damián para inspeccionar el estado REAL del código (no lo que dicen los documentos) antes de empezar la Pieza 0, con foco en maximizar trabajo útil por unidad de recurso — Qwen/local, Gemini, ChatGPT y Claude — en vez de simplemente "ahorrar tokens de Claude". Documento único: `FASE6_A_AUDITORIA_TECNICA_RECURSOS.md`, con las 7 secciones pedidas (A-G), cada afirmación con archivo/función/test/commit de evidencia. **No se ha implementado nada.**

## Resumen de hallazgos más importantes (con evidencia, detalle en el documento)

1. El modelo obrero real en producción es **qwen2.5:7b**, no qwen3:4b — la medición que "faltaba" según las Fases 2-4 en realidad ya se hizo el 11/09/2026 (`memoria/comparativa_modelos.json`), antes incluso de la Fase 2. qwen3:4b quedó descartado por devolver vacío en las 3 pruebas.
2. Qwen hace hoy en producción **una sola cosa real y probada**: triaje informativo de mensajes sueltos de Telegram (`extremidades/triaje.py` + `canal/bot.py`). Todo lo demás de la lista de tareas absorbibles (planificación, gestión de tareas, ejecución de herramientas, verificación, etc.) es NO EXISTE.
3. **`proveedores.py` (T046) está probado pero no está conectado a nada**: solo lo importan scripts de prueba/consulta, nunca `canal/bot.py` ni `nucleo/tareas.py`. "Tenemos proveedores conectados" es cierto; "Nexo puede delegar automáticamente" es falso.
4. Control del PC: solo `playwright` está instalado en el entorno de Nexo. Cero UI Automation, cero visión, cero automatización de escritorio genérica — la única base real es el navegador vía CDP, específica de Chrome.
5. Cero código de verificación cruzada, segunda opinión, caché o puntuación de confianza en todo el repo (confirmado por grep).

## Conclusión sobre el roadmap

**No cambia.** El orden BOOTSTRAP → PIEZA 0 → PIEZA 1 → ROUTER → DELEGACIÓN → AUTONOMÍA se mantiene. Esta auditoría confirma que gran parte de lo que hace falta para el Router y la delegación ya existe y está probado por separado (Qwen.clasificar(), los 4 adaptadores de proveedores.py, la distinción OK/NOT_AVAILABLE/BLOCKED/ERROR) — lo que falta es la pieza 1 (estado vivo) que les dé un sitio donde registrar qué pasó, y el Router que lea eso y decida. Reduce el riesgo estimado del Router, no cambia su posición.

El siguiente paso exacto sigue siendo la **Pieza 0 (seguridad)**, con evidencia de código confirmada en esta auditoría: `manos/servidor_mcp.py`, función `ejecutar_python()`, llama a `subprocess.run()` directamente sin pasar por `exigir()`; `nucleo/permisos.py`, función `nivel_de_ruta()`, da VERDE a cualquier lectura fuera del proyecto salvo `secretos.toml` (REQ-070).

## NEXT_DECISION_REQUIRED

Nada nuevo respecto a la Fase 5 — siguen abiertas las mismas 3 decisiones, sin cambios por esta auditoría:

1. ¿Confirmas empezar ya con la PIEZA 0 (seguridad)? Seguirá necesitando tu aprobación explícita en el momento antes de tocar `nucleo/permisos.py` o `manos/servidor_mcp.py`.
2. ¿Quieres que cree ya el documento Bootstrap (pieza 0-bis, sin riesgo)?
3. Si confirmas el Bootstrap: ¿quieres el texto para pegar tú en "instrucciones del proyecto" de claude.ai?
