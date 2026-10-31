# Índice maestro — Auditoría y diseño de Nexo (12/09/2026)

> **Documento histórico.** Es la foto de la auditoría del 12/09/2026, ampliada el 13/09 (Fases 2-6 y Master Requirements Checklist). No describe el estado actual de NEXO: el estado vivo está en `memoria/tareas.json` (`python -m nucleo.tareas siguiente`) y en el README.

Este es el índice de la auditoría completa pedida por Damián: inventario de requisitos, auditoría real del código, consulta a las 4 IAs para los 5 casos especiales, síntesis, arquitectura maestra, 14 manuales operativos, y roadmap. **No incluye implementación de nada nuevo**: esta fase es exclusivamente inventario → auditoría → consulta → síntesis → documentación → roadmap, tal y como se pidió.

No se borra ni se duplica documentación previa. Ver la sección "Documentación previa" al final para lo que ya existía y sigue vigente.

## Deliverables A-M (nomenclatura de Damián)

- **[A. Matriz completa de requisitos](A_MATRIZ_REQUISITOS.md)** — todo lo pedido alguna vez para Nexo, con estado real evidenciado.
- **[B. Auditoría real](B_AUDITORIA_REAL.md)** — evidencia línea a línea, reconciliación con la auditoría en frío del 10-11/09.
- **[C. Resultados de Qwen](C_RESULTADOS_QWEN.md)**
- **[D. Resultados de Gemini](D_RESULTADOS_GEMINI.md)**
- **[E. Resultados de ChatGPT](E_RESULTADOS_CHATGPT.md)**
- **[F. Análisis propio de Claude](F_ANALISIS_CLAUDE.md)**
- **[G. Síntesis multi-IA](G_SINTESIS_MULTI_IA.md)** — coincidencias, discrepancias, conclusión técnica y decisión pendiente por cada caso especial.
- **[H. Arquitectura maestra de Nexo](H_NEXO_MASTER_ARCHITECTURE.md)** — manual 1 de 14.
- **I. Manuales operativos** (manuales 2-14, carpeta [`I_MANUALES/`](I_MANUALES/)):
  - [02 · Operación diaria](I_MANUALES/02_NEXO_DAILY_OPERATIONS.md)
  - [03 · Turno de noche](I_MANUALES/03_NEXO_NIGHT_SHIFT.md)
  - [04 · Gestión de tareas](I_MANUALES/04_NEXO_TASK_MANAGEMENT.md)
  - [05 · Tareas de Damián](I_MANUALES/05_DAMIAN_TASKS.md)
  - [06 · Enrutado de modelos](I_MANUALES/06_NEXO_MODEL_ROUTING.md)
  - [07 · Protocolo multi-agente](I_MANUALES/07_NEXO_MULTI_AGENT_PROTOCOL.md)
  - [08 · Recuperación de errores](I_MANUALES/08_NEXO_ERROR_RECOVERY.md)
  - [09 · Auto-mejora](I_MANUALES/09_NEXO_SELF_IMPROVEMENT.md)
  - [10 · Seguridad y permisos](I_MANUALES/10_NEXO_SECURITY_AND_PERMISSIONS.md)
  - [11 · Memoria y estado](I_MANUALES/11_NEXO_MEMORY_AND_STATE.md)
  - [12 · Manual de proveedores](I_MANUALES/12_NEXO_PROVIDER_MANUAL.md)
  - [13 · Interfaz humana](I_MANUALES/13_NEXO_HUMAN_INTERFACE.md)
  - [14 · Mantenimiento](I_MANUALES/14_NEXO_MAINTENANCE.md)
- **[J. Roadmap priorizado](J_ROADMAP_PRIORIZADO.md)** — P0 a P4. «P0» es la prioridad 0 del roadmap; no confundir con la «Pieza 0» (seguridad, L1/REQ-070). A 12/09 no había nada implementado del roadmap; la Pieza 0 se implementó y cerró el 13/09 con aprobación de Damián (ver el pie).
- **[K. Lista de acciones de Damián](K_ACCIONES_DAMIAN.md)**
- **[L. Lista de bloqueos](L_BLOQUEOS.md)**
- **[M. Decisiones arquitectónicas pendientes](M_DECISIONES_ARQUITECTONICAS_PENDIENTES.md)**

## Fases posteriores de revisión de arquitectura (12-13/09/2026)

- **[Fase 2 — revisión de arquitectura](FASE2_00_INDICE.md)**
- **[Fase 3 — replanteamiento profundo](FASE3_00_INDICE.md)**
- **[Fase 4 — consolidación arquitectónica final](FASE4_00_INDICE.md)** — arquitectura en capas, cadena de ejecución formal, roadmap por dependencias de 13 piezas (**vigente**).
- **[Fase 5 — contexto persistente de Claude](FASE5_00_INDICE.md)** — Bootstrap/Constitución.
- **[Fase 6 — auditoría técnica de recursos](FASE6_00_INDICE.md)** — evidencia de código real, sin cambios al roadmap.
- **[Bootstrap/Constitución de Nexo](00-bootstrap.md)** — cerrado, en uso en Project Instructions de claude.ai.
- **[Requisito: turno nocturno adaptativo](REQ_TURNO_NOCTURNO_ADAPTATIVO.md)** — documentado, no implementado.
- **[MASTER REQUIREMENTS CHECKLIST](MASTER_REQUIREMENTS_CHECKLIST.md)** — inventario completo de todo lo pedido para Nexo desde el origen del proyecto, clasificado por tipo/estado, con detección de huecos y duplicados, grafo de dependencias, y re-evaluación de la Pieza 1 (13/09/2026). **Es el índice de referencia de requisitos — no sustituye a los documentos técnicos de arriba, los enlaza.**

## Documentación previa (no duplicada, sigue vigente, enlazada)

### Documentos vigentes
- `docs/ARRANQUE.md` — arranque paso a paso.
- `docs/TELEGRAM.md` — configuración del bot.
- `memoria/auditoria.md` — auditoría en frío original (10-11/09). Reconciliada con el código actual en `B_AUDITORIA_REAL.md` sección B.1 (5 de sus hallazgos estaban desactualizados, corregido ahí).
- `memoria/historial.md` — historial narrativo día a día.
- `memoria/claude_organizacion.md` — organización de proyectos/chats de Claude.
- `memoria/altavoz.md` — investigación del Google Home Mini.

### Documentos sustituidos / históricos
- `memoria/cola.md` — cola de prioridades original del 11/09, superseded por `memoria/tareas.json` pero conservada como referencia de trazabilidad.

## NEXT_DECISION_REQUIRED

Ver el NEXT_DECISION_REQUIRED del `MASTER_REQUIREMENTS_CHECKLIST.md` (vigente, 13/09/2026) para las decisiones actuales. Las decisiones originales de esta Fase 1 (12/09) ya fueron resueltas: Pieza 0 (L1/REQ-070) cerrada, Bootstrap cerrado.

## USER_ACTION_REQUIRED

Ver lista completa y priorizada en `K_ACCIONES_DAMIAN.md`.

---

*Auditoría realizada el 12/09/2026, ampliada con las Fases 2-6 y el Master Requirements Checklist (13/09/2026). No se ha implementado ninguna funcionalidad nueva de arquitectura durante estas fases de auditoría/diseño — solo la Pieza 0 (seguridad) se implementó, con aprobación explícita de Damián en cada paso.*
