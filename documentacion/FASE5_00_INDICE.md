# FASE 5 — Índice: contexto persistente de Claude + confirmación de arquitectura operativa

Esta fase tiene dos partes: (A) auditoría y diseño de cómo Claude entra en contexto de Nexo sin que Damián tenga que pegar todo a mano (documento separado: `FASE5_A_CONTEXTO_PERSISTENTE_CLAUDE.md`), y (B) esta integración, que confirma que la arquitectura operativa de la Fase 4 sigue vigente y añade lo que cambia. **No se ha implementado nada. No se ha creado ninguna tarea nueva de implementación** (el Bootstrap se identifica como pieza futura, no se crea todavía).

## Documento de esta fase

| Doc | Contenido |
|---|---|
| `FASE5_A_CONTEXTO_PERSISTENTE_CLAUDE.md` | Auditoría real de mecanismos de Claude (memoria de cuenta, Proyecto, instrucciones), diseño de los 4 niveles de información, contenido del Bootstrap, jerarquía de autoridad, versionado, coste de contexto, respuestas A-J |

## CAMBIOS RESPECTO A LA FASE 4

**Nada de la arquitectura interna de Nexo cambia.** Las 4 capas (Runtime/Orquestador, Modelos/Agentes, Tools/Ejecución, Proveedores), la cadena de ejecución obligatoria, el Router, los perfiles de proveedor, el watchdog/fallback, la observabilidad, la seguridad transversal, el ciclo de autonomía y el roadmap por dependencias de la Fase 4 **se mantienen sin ningún cambio de fondo**.

Lo único que añade esta fase es una capa adicional, ortogonal a las 4 anteriores: **cómo Claude (uno de los modelos de la capa B) entra en contexto de Nexo cuando Damián abre un chat nuevo**, con estos hallazgos nuevos:

1. El mecanismo para que un chat nuevo "entre en modo Nexo" **ya existe y ya funciona**: adjuntar el chat al Proyecto NEXO de claude.ai carga automáticamente la documentación disponible, sin pegar nada. Antes de esta fase no estaba comprobado ni documentado como mecanismo formal.
2. Se descubrió una limitación real, no documentada antes: una sesión atada al Proyecto NEXO **no puede escribir la memoria de cuenta general** de Damián — solo su propio subárbol de proyecto. Esto explica por qué `/areas/agente-multi-ia.md` (memoria de cuenta) está desactualizado respecto a las Fases 2-4, y fija una regla nueva: ese archivo debe mantenerse deliberadamente mínimo y estable, para que la desactualización importe lo menos posible.
3. Se identifica una pieza nueva de trabajo, todavía no creada: el documento **Bootstrap/Constitución** (`claude/00-bootstrap.md` en el Proyecto + copia en el repo del PC). No formaba parte del roadmap de la Fase 4 porque no se había auditado todavía si hacía falta o si el mecanismo natural del Proyecto ya bastaba. Conclusión: hace falta el documento (para que el Proyecto tenga un punto de entrada corto y estable), pero el mecanismo de carga ya existe solo con adjuntar el Proyecto.

## Respuestas A-Q (Parte B)

La mayoría no cambian respecto a la Fase 4; se listan igualmente para que quede un cierre completo de esta fase.

- **A. Cómo entra un chat nuevo en contexto Nexo:** adjuntando el chat al Proyecto NEXO (mecanismo ya real, ver Parte A). Sin eso, solo el reconocimiento mínimo de memoria de cuenta.
- **B. Mecanismo real de Claude:** documentos de Proyecto (Bootstrap + documentación extensa) + memoria de cuenta (reconocimiento) + `estado.json` del PC (estado vivo). Ver Parte A, sección 1.
- **C. Contenido del Bootstrap:** ver `FASE5_A`, sección 3.
- **D. Qué queda en Proyecto:** toda la documentación de fases, manuales, historial, incidencias, roadmap — sin cambio.
- **E. Qué queda en estado vivo:** `estado.json` del PC (fuente real) + espejo condensado opcional en Proyecto — nuevo respecto a la Fase 4, ver Parte A sección 2 (Nivel 4).
- **F. Jerarquía de autoridad:** conversación actual > estado vivo > Bootstrap > documentación de proyecto vigente > historial — ver Parte A sección 4. Sin cambio respecto al principio ya seguido en las Fases 2-4 ("información vigente > histórica"), ahora formalizado con los 5 niveles explícitos.
- **G. Estrategia de consumo de contexto:** sin cambio — el propio Proyecto ya carga bajo demanda; el Bootstrap se diseña corto a propósito.
- **H. Arquitectura final del Runtime:** sin cambio, ver `FASE4_C_RUNTIME_PERMANENTE.md`.
- **I. Papel de modelos locales:** sin cambio, ver `FASE4_D_MODELOS_LOCALES_Y_MULTIAGENTE_V2.md`.
- **J. Papel de cada proveedor:** sin cambio, ver `FASE4_F_PERFILES_Y_APROVECHAMIENTO.md`.
- **K. Router:** sin cambio, ver `FASE4_E_ROUTER_V3.md`.
- **L. Proyectos/chats (de IAs externas, no confundir con el Proyecto de claude.ai):** sin cambio, ver `FASE4_G_PROYECTOS_CONVERSACIONES.md`.
- **M. PC Control:** sin cambio, ver `FASE4_H_PC_CONTROL_Y_CLAUDE_GENERAL.md`.
- **N. Watchdog/fallback:** sin cambio, ver `FASE4_I_WATCHDOG_FALLBACK_OBSERVABILIDAD_METRICAS.md`.
- **O. Observabilidad:** sin cambio, misma referencia que N.
- **P. Seguridad:** sin cambio, ver `FASE4_J_WAKE_SEGURIDAD_AUTONOMIA.md`. Sigue siendo pieza 0 del roadmap.
- **Q. Roadmap por dependencias:** el orden de la Fase 4 se mantiene (pieza 0 = seguridad, pieza 1 = estado vivo + evidencia...). Se añade una pieza nueva, de bajo riesgo y sin tocar código de producción, para el Bootstrap — ver más abajo.

## Roadmap: dónde encaja el Bootstrap

No cambia el orden de las piezas 0-12 de la Fase 4. El Bootstrap se añade como pieza independiente, de riesgo mínimo (solo documentación, no toca `ARCHIVOS_BLINDADOS` ni ningún código), que puede hacerse en paralelo a la pieza 0 sin bloquearla ni ser bloqueada por ella:

| Pieza | Nombre | Prerequisito | Qué desbloquea | Riesgo |
|---|---|---|---|---|
| 0 | Seguridad (L1/REQ-070) | Ninguno | Todo lo demás con seguridad garantizada | Alto (toca archivos blindados, requiere tu aprobación en el momento) |
| **0-bis** | **Bootstrap/Constitución** (`claude/00-bootstrap.md` + copia en el repo) | Ninguno (usa lo que ya existe) | Que un chat nuevo adjunto al Proyecto entre en modo Nexo sin pegar contexto | Ninguno (solo documentación) |
| 1 | Estado vivo + registro de evidencia | Pieza 0 | Router, fallback, observabilidad, perfiles, autonomía | Medio |

La pieza 0-bis no compite con la 0: son independientes, y su bajo riesgo permite hacerla cuando convenga sin que afecte al orden de seguridad-primero.

## Chequeo de los 5 criterios de éxito (sin cambios respecto a la Fase 4)

Esta fase no toca la arquitectura interna, así que las 5 respuestas de la Fase 4 siguen siendo válidas ("sí, con camino claro" en las 5). No se repiten aquí para no duplicar contenido — ver `FASE4_00_INDICE.md`.

## NEXT_DECISION_REQUIRED

1. **¿Confirmas que la auditoría de contexto persistente no cambia el roadmap y que la siguiente acción es la PIEZA 0 (seguridad L1/REQ-070)?** Seguirá necesitando tu aprobación explícita en el momento antes de tocar `nucleo/permisos.py` o `manos/servidor_mcp.py`.
2. **¿Quieres que cree ya el documento Bootstrap (pieza 0-bis)?** Es solo documentación (sin riesgo, no toca código), y puede hacerse antes, después o en paralelo a la Pieza 0 — dime si lo hago ahora o lo dejas para después.
3. **Si confirmas el Bootstrap:** ¿quieres que además rellenes tú, a mano, el campo "instrucciones del proyecto" en la configuración del Proyecto NEXO (hoy vacío) con un par de líneas que apunten a `claude/00-bootstrap.md`? Yo no tengo forma de escribir ese campo — solo tú puedes hacerlo desde la interfaz de claude.ai. Si quieres, te doy el texto exacto para pegar cuando llegue el momento.
