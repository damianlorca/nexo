# FASE 3 — Índice: replanteamiento profundo de la arquitectura de Nexo

Esta fase reencuadra la arquitectura de Nexo a partir de la premisa que plantea Damián: no "Claude + herramientas + proveedores auxiliares", sino "NEXO = orquestador local + multiagente + multi-IA + herramientas + memoria + control del PC". **No se ha implementado nada de lo descrito aquí.** Es análisis, comparación y diseño, sobre la base ya construida en la Fase 1 y la Fase 2, que no se descarta — se reencuadra donde correspondía y se corrige donde la evidencia lo pide (ver sección S).

## Documentos de esta fase

| Archivo | Contenido |
|---|---|
| `FASE3_A_VISION_LOCAL_FIRST.md` | Crítica a la premisa anterior, evaluación seria de la hipótesis "sistema combinado > una sola IA Pro" |
| `FASE3_B_MODELOS_LOCALES_Y_MULTIAGENTE.md` | Comparación ampliada de modelos locales + evaluación de arquitectura multiagente vs. modelo único |
| `FASE3_C_ORCHESTRATOR_Y_ESTRATEGIA_CLAUDE.md` | El orquestador local como primer filtro, y cuándo ir directo a Claude |
| `FASE3_D_PROVEEDORES_FICHAS_Y_USO_INTELIGENTE.md` | Fichas de capacidades por proveedor (Claude/Gemini/ChatGPT/Qwen + candidatos futuros) y uso inteligente de planes gratuitos |
| `FASE3_E_ROUTER_V2_Y_APRENDIZAJE.md` | Model Router de 10 decisiones + aprendizaje basado en evidencia (sin ML todavía) |
| `FASE3_F_PROYECTOS_CHATS_Y_INTERFACES.md` | Gestión de proyectos/chats + abstracción rica sobre Gemini/ChatGPT (`ConversationManager`) |
| `FASE3_G_CONTROL_PC_TRANSVERSAL.md` | Reconsideración: control del PC como infraestructura transversal, no última pieza |
| `FASE3_H_OBSERVABILIDAD_V2.md` | Observabilidad ampliada, con cadena de origen (Nexo vs. sugerencia de otra IA) |
| `FASE3_I_PUENTE_MOVIL_PC_Y_WAKE.md` | Nexo como puente móvil↔PC, y comparación de opciones de "wake" del PC |
| `FASE3_J_SEGURIDAD_AUTONOMIA_V2.md` | Seguridad antes que autonomía, ciclo de 8 etapas con límites/permisos/rollback en cada una |
| `FASE3_K_ECONOMIA_USO_V2.md` | Economía de uso extendida a todos los proveedores, no solo Claude |
| `FASE3_L_CONSULTA_MULTIIA.md` | Consulta selectiva (2 preguntas) a Qwen/Gemini/ChatGPT sobre multiagente local y gestión de chats |
| `FASE3_M_TURNO_DE_NOCHE.md` | Recomendación reafirmada: pausa temporal (sin tocarlo) |
| `FASE3_N_ROADMAP_Y_CORRECCIONES.md` | Qué cambia respecto a la Fase 2, y el nuevo orden de 13 pasos |

## Respuestas a las preguntas A-T de Damián

**A. ¿Papel de Nexo local?** Centro operativo real, no un simple abaratador de Claude — recibe la petición, clasifica, resuelve localmente lo que pueda, delega solo lo necesario (sección A, C).

**B. ¿Papel de Claude?** Arquitecto, razonador profundo, programador, analista, verificador final de lo importante — reservado explícitamente para donde su valor es máximo, no eliminado del triaje por decreto sino porque ya no hace falta que lo toque (sección C).

**C. ¿Qué debería hacer Qwen/local?** Triaje (ya), verificación mecánica y de razonamiento (nuevo), resumen (nuevo), planificación preliminar de fondo (nuevo) — nunca decidir por sí solo (sección A/Fase 2, B).

**D. ¿Arquitectura multiagente local?** No se justifica todavía con la evidencia disponible — mejor un modelo local reutilizado con roles distintos + orquestación por código determinista, confirmado 2-contra-1 por la consulta externa (sección B, L).

**E. ¿Qué modelos locales probar?** Qwen3:4b/8b/14b (según rol), Gemma3:12b (resumen), DeepSeek-R1-Distill-Qwen-14b (verificación de razonamiento) — candidatos a MEDIR, no elegidos todavía (sección B).

**F. ¿Papel de Gemini y ChatGPT?** Proveedores reales con capacidades propias (no solo "texto"), organizados en `ConversationManager` con navegación por URL preferente; papel concreto decidido por el Router según la ficha de cada uno (sección D, F).

**G. ¿Qué proveedores adicionales estudiar?** Perplexity (búsqueda con fuentes, candidato claro para el paso "¿necesito buscar?"); Copilot y Grok sin diferencial claro identificado todavía — no añadir por cantidad (sección D).

**H. ¿Cómo representar capacidades/limitaciones?** Ficha estándar por proveedor (modelos, capacidades, limitaciones, coste/quota, disponibilidad, contexto, visión, búsqueda, coding, razonamiento, herramientas, archivos, proyectos, memoria, automatización, fiabilidad, método de acceso) — sección D.

**I. ¿Cómo debería funcionar el Model Router?** Pipeline de 7 pasos decidiendo 10 cosas (proveedor, modelo, esfuerzo, contexto, herramientas, segunda opinión, verificación, timeout, pasos máximos, fallback), con la regla "mínimo recurso suficiente" salvo cuando el riesgo exige el mejor disponible (sección E).

**J. ¿Cómo debería funcionar la gestión de proyectos/chats?** Jerarquía PROVEEDOR→PROYECTO→CHAT→TAREA→CONTEXTO→RESULTADO, índice local + contenido nativo del proveedor, con vencimiento por inactividad para evitar acumulación de contexto (sección F).

**K. ¿Cómo debería funcionar la interacción con el PC?** Jerarquía híbrida de 5 niveles, con los niveles 1-2 adelantados (ya aplicables a Gemini/ChatGPT) y los niveles 4-5 (visión/coordenadas genéricas) al final, tras cerrar seguridad (sección G).

**L. ¿Qué infraestructura común crear?** El contrato `proveedores.py` ya existente, ampliado con las fichas de capacidades (D) y consumido de verdad por el Router (E) — no una reescritura, una conexión de piezas que hoy existen sueltas.

**M. ¿Cómo monitorizar/controlar al agente local?** Estado vivo + `/estado` en Telegram, con cadena de origen explícita para distinguir "lo que hace Nexo" de "lo que sugirió otra IA sin revisar" (sección H).

**N. ¿Cómo minimizar el uso de Claude?** Router con recurso mínimo suficiente + las tres políticas de economía extendidas a todos los proveedores, no solo a Claude (sección E, K).

**O. ¿Cómo aprovechar planes gratuitos?** Fichas de capacidad + Router decidiendo "esto va gratis a Gemini/ChatGPT/Perplexity" cuando baste, sin generar volumen artificial ni intentar burlar límites (sección D).

**P. ¿Cómo despertar el PC/recursos?** Comparación de 4 opciones de wake, con el enchufe inteligente + BIOS como la más fiable técnicamente (sin decidir compra); despertar proveedores externos ya resuelto por diseño existente (sección I).

**Q. ¿Cómo aumentar autonomía sin perder control?** Ciclo de 8 etapas (añadiendo MEJORAR) con límites/permisos/observabilidad/rollback explícitos en cada una, nunca autonomía como "acceso ilimitado" (sección J).

**R. ¿Qué implementar primero?** Seguridad (L1/REQ-070) → observabilidad mínima → Model Router v1 → Qwen verificador → vigilante de bucles → extensión ligera de `navegador.py` → fichas de proveedores conectadas al Router → aprendizaje por evidencia → permisos ampliados → UI Automation acotada (solo lectura) → extensión completa de `navegador.py` → autonomía incremental completa → control visual genérico (sección N, 13 pasos).

**S. ¿Qué partes de la Fase 2 cambian?** El marco de referencia (de "Claude decide, todo lo demás ahorra" a "Nexo local decide, Claude se reserva"); la prioridad del control del PC (parcialmente adelantada); el alcance del Model Router (de selector de proveedor a 10 decisiones); la observabilidad (con cadena de origen); se añade la etapa MEJORAR a la autonomía. Se reafirman sin cambios: T038 cerrada, T039 cerrada del todo, L1/REQ-070 como prioridad máxima, recomendación de pausar el turno de noche, Caso E sin resolver por decreto (sección N).

**T. ¿Qué decisiones necesita tomar Damián?** Ver NEXT_DECISION_REQUIRED, abajo.

## Evaluación final de la hipótesis del punto 24

Sí, con condiciones: un sistema combinado puede superar a "una sola IA Pro haciéndolo todo" en capacidad global, autonomía y eficiencia de uso externo — pero esa ganancia depende enteramente de construir primero el Model Router, la observabilidad con cadena de origen, y de cerrar la seguridad base ANTES de ampliar autonomía o proveedores. Sin esas tres piezas, más componentes significa más superficie de fallo, no más capacidad neta. La hipótesis se adopta como dirección, no como garantía automática (desarrollo completo en `FASE3_A_VISION_LOCAL_FIRST.md`).

---

## NEXT_DECISION_REQUIRED

No se ha implementado nada de esta fase. Las decisiones que necesito de ti para poder seguir:

1. **¿Confirmas el reencuadre de fondo** — Nexo local como centro de decisión que resuelve lo que puede y escala solo lo necesario, con Claude reservado para arquitectura/razonamiento profundo/código no trivial — como la dirección a seguir en el roadmap? Si no, dime qué parte de esa dirección no encaja con lo que tienes en mente.
2. **¿Retomamos implementación por el nuevo orden de 13 pasos de `FASE3_N_ROADMAP_Y_CORRECCIONES.md`** (seguridad L1/REQ-070 primero, igual que en la Fase 2, con la extensión ligera de `navegador.py` adelantada al puesto 6)?
3. **¿Pauso el turno de noche de esta noche?** (recomendación reafirmada: sí, temporalmente — sección M). Sin tu confirmación, sigue activo tal cual.
4. **Aviso, no decisión bloqueante:** la consulta a ChatGPT citó el texto concreto de sus condiciones de uso prohibiendo la extracción automática de datos — más específico que lo ya sabido. No cambia por sí solo la automatización de Gemini/ChatGPT que ya tienes en marcha (fue una decisión tuya consciente, distinta de T038/claude.ai), pero quería que lo tuvieras con el detalle exacto antes de ampliarla (ver `FASE3_F` y `FASE3_L`). Dime si quieres que esto cambie algo del alcance de esa ampliación.
5. Las demás decisiones de detalle (qué modelos locales medir primero, si LangGraph se adopta o se sigue evaluando, si se estudia Perplexity) no bloquean el arranque de la implementación de seguridad — se confirman cuando lleguemos a esa pieza del roadmap.
