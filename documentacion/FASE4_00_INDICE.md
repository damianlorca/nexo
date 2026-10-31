# FASE 4 — Índice: consolidación arquitectónica final

Esta fase consolida las Fases 2 y 3 en una arquitectura objetivo formal: capas (Runtime/Modelos/Tools/Proveedores), la cadena de ejecución que impide que un modelo actúe por el simple hecho de proponerlo, y un roadmap por dependencias en vez de por lista de features. **No se ha implementado nada.**

## Documentos de esta fase

| Archivo | Contenido |
|---|---|
| `FASE4_A_ARQUITECTURA_EN_CAPAS.md` | Las 4 capas (Runtime, Modelos, Tools, Proveedores) y su relación con lo ya construido |
| `FASE4_B_CADENA_DE_EJECUCION.md` | Propuesta→validación→permisos→tool→ejecución→verificación→resultado, formalizada |
| `FASE4_C_RUNTIME_PERMANENTE.md` | Nexo como servicio permanente — qué existe hoy de cada componente, qué falta |
| `FASE4_D_MODELOS_LOCALES_Y_MULTIAGENTE_V2.md` | 4 opciones de arquitectura local comparadas (A/B/C/D), sin adoptar framework |
| `FASE4_E_ROUTER_V3.md` | Router como cerebro de recursos, señales ampliadas, dos caminos igual de válidos |
| `FASE4_F_PERFILES_Y_APROVECHAMIENTO.md` | Perfiles de proveedor extensibles, patrón adapter+profile+tests, aprovechamiento real de cada IA |
| `FASE4_G_PROYECTOS_CONVERSACIONES.md` | Diseño de FASE3_F releído en el modelo de capas |
| `FASE4_H_PC_CONTROL_Y_CLAUDE_GENERAL.md` | PC Control Layer transversal + Playwright como pregunta general, separada de T038 |
| `FASE4_I_WATCHDOG_FALLBACK_OBSERVABILIDAD_METRICAS.md` | Cadena de fallo formal, observabilidad con origen, métricas de eficiencia |
| `FASE4_J_WAKE_SEGURIDAD_AUTONOMIA.md` | Cadena de wake del PC, seguridad transversal (permisos de la acción, no del modelo), autonomía gradual |

## Revisión explícita: dónde la Fase 3 contradecía o se quedaba corta del nuevo principio (sección 24)

Damián pidió señalar esto sin suavizarlo. Cuatro puntos reales, ninguno grave, todos de encuadre más que de contenido técnico:

1. **FASE3_C hablaba de "el orquestador local" de forma ambigua** — a veces como código de decisión, a veces sugiriendo que un modelo local decide. Con la separación de capas de esta fase (FASE4_A), queda corregido sin ambigüedad: la orquestación es SIEMPRE código de la capa A (Runtime); un modelo (capa B) solo propone, nunca orquesta. Esto no cambia ninguna conclusión de FASE3_C, la precisa.
2. **`navegador.py` se venía tratando como "el proveedor Gemini/ChatGPT"** en FASE3_D/F, cuando en realidad es una TOOL (capa C) que la capa D (proveedor) usa. Corregido explícitamente en FASE4_A y FASE4_G. Sin impacto en el diseño ya hecho, sí en cómo se organizará el código cuando se implemente.
3. **FASE3_B solo comparó 2 opciones** (multiagente vs. modelo único) cuando el espacio real de diseño tiene al menos 4 (A/B/C/D de FASE4_D). La conclusión no cambia (la Opción D, híbrida, es la versión más precisa de lo que FASE3_B ya recomendaba), pero la comparación estaba incompleta, no equivocada.
4. **Las fichas de proveedor de FASE3_D eran estáticas** (un documento markdown) sin conexión explícita a datos que cambian solos (disponibilidad, cuota, fiabilidad observada). Corregido en FASE4_F: el perfil se piensa ahora como una estructura parcialmente autoalimentada por las sondas y el registro de evidencia, no un documento a mantener a mano.

**Lo que NO contradecía el principio y se reafirma sin cambios:** el cierre de T038 y T039, la prioridad máxima de L1/REQ-070, la recomendación (ya aplicada) de pausar el turno de noche, el Caso E de autonomía sin resolver por decreto, y el contenido técnico del Model Router, la observabilidad y la seguridad de la Fase 3 — todo eso ya estaba alineado con el principio, solo le faltaba la organización en capas que esta fase añade.

## Roadmap por dependencias (sustituye la lista de 13 pasos de FASE3_N)

**El cimiento transversal mínimo, identificado explícitamente (lo que pide la sección 25 de Damián):** no es la seguridad por sí sola (esa es una condición de entrada, un candado que hay que quitar, no algo que active capacidades nuevas) — es **el estado vivo + el registro de evidencia, construidos como una sola pieza desde el principio**. Justificación: esa única pieza alimenta directamente el Router (necesita evidencia para aprender), el fallback (necesita saber qué está fallando ahora mismo), la observabilidad (es literalmente esta pieza), los perfiles de proveedor dinámicos (fiabilidad/cuota vienen de aquí), y las etapas REPORTAR/MEJORAR de la autonomía. Construir esta pieza pronto, aunque parezca "solo instrumentación", es lo que evita que cada pieza siguiente tenga que inventar su propio mini-registro suelto.

| # | Pieza | Qué necesita antes | Qué desbloquea | Riesgo principal | Cómo se prueba |
|---|---|---|---|---|---|
| 0 | Cerrar L1 (`ejecutar_python`) y REQ-070 | Nada (aprobación explícita de Damián para tocar archivos blindados) | Es la condición de entrada para TODO lo demás — "capacidad sin control = no" | Romper algo que hoy depende del comportamiento actual de `ejecutar_python` | Repetir los casos que demostraron el bypass/lectura sin restricción, confirmar que ahora se bloquean |
| 1 | Estado vivo + registro de evidencia (una sola estructura) | Pieza 0 | Router (2), fallback/watchdog (4), perfiles dinámicos (5), observabilidad, métricas | Diseñar el esquema de datos demasiado rígido y tener que rehacerlo pronto | Generar datos reales durante unos días de uso normal del bot/triaje, verificar que el `/estado` los lee bien |
| 2 | Capa de tool común (formalizar `manos/`, `extremidades/imagen.py`, `navegador.py` bajo una interfaz de capa C) | Pieza 0 | La cadena de ejecución formal (FASE4_B) tiene dónde enganchar VALIDACIÓN/PERMISOS de forma uniforme | Refactor amplio si se hace de golpe — mejor incremental, tool por tool | Cada tool migrada sigue pasando sus pruebas existentes antes de tocar la siguiente |
| 3 | Model Router v1 (proveedor + modelo + contexto, sin las 10 decisiones completas) | Piezas 1, 2 | Ampliar Qwen (4), fichas conectadas (5), el resto de decisiones del Router de forma incremental | Un Router mal calibrado escala de más o de menos | Comparar sus decisiones contra lo que un humano habría elegido, en una muestra de tareas reales |
| 4 | Ampliar Qwen (verificador barato) + vigilante de bucles | Piezas 1, 3 | Verificación real dentro de la cadena de ejecución (FASE4_B); primera reducción medible de trabajo mecánico en Claude | Elegir mal el modelo verificador sin medir | Medir en el hardware real antes de fijarlo en `config.toml` |
| 5 | Perfiles de proveedor conectados al Router (capacidades + campos dinámicos) | Piezas 1, 3 | Añadir proveedores futuros sin tocar el Router (patrón adapter+profile+tests) | Perfil desactualizado dando información falsa al Router | Confirmar que el Router cambia de comportamiento cuando el perfil cambia (prueba deliberada) |
| 6 | Extensión ligera de `navegador.py`: detectar/verificar conversación actual (URL directa) | Piezas 0, 2 | Base para `ConversationManager` completo (10); evita el error más caro (escribir en el chat equivocado) | Cambios de interfaz de Gemini/ChatGPT rompiendo la detección | Prueba real navegando a varias conversaciones y confirmando la detección antes de escribir |
| 7 | Aprendizaje por evidencia v1 (umbrales auditables sobre los datos de la pieza 1/3) | Piezas 1, 3 (con volumen real de datos ya acumulado) | Router más preciso con el tiempo, métricas de eficiencia con sentido | Ajustar umbrales sin suficientes datos todavía | Revisar a mano los primeros ajustes propuestos antes de dejarlos automáticos |
| 8 | Permisos ampliados (aplicación/ventana, proveedor, origen de la orden, nivel de autonomía) | Pieza 0 | Control visual acotado (9); autonomía incremental (11) | Un modelo de permisos mal diseñado que dé una falsa sensación de control | Casos de prueba explícitos por cada nueva dimensión de permiso |
| 9 | UI Automation acotada (nivel 3, solo lectura, lista blanca) | Piezas 1, 8 | Observar cuota/estado de proveedores visualmente; primer paso real del control del PC | Acceso a una aplicación fuera de la lista blanca por error | Probar solo sobre las aplicaciones ya autorizadas (Chrome, VS Code) |
| 10 | `ConversationManager` completo (crear/seleccionar, patrón de adaptador) | Pieza 6 | Gestión de proyectos/chats completa (FASE3_F/FASE4_G) | Mismo riesgo de mantenimiento ya señalado en FASE3_F/L | Prueba real creando y seleccionando conversaciones en Gemini y ChatGPT por separado |
| 11 | Autonomía incremental completa (ciclo de 8 etapas con límites reales) | Piezas 1, 3, 4, 8 | El objetivo final del proyecto: trabajo desatendido con control | Ampliar autonomía antes de que las piezas anteriores estén maduras | Empezar con tareas de bajo riesgo, medir con las métricas de la pieza 1 antes de ampliar el alcance |
| 12 | Control visual genérico (niveles 4-5, cualquier aplicación) | Piezas 8, 9, 11 | El caso de uso más ambicioso, deliberadamente el último | El más arriesgado de todos — máxima superficie de fallo y de seguridad | Casos de prueba acotados, uno por aplicación nueva, nunca "acceso general" de entrada |

**Nada de esto se implementa en esta fase.** El orden es una recomendación basada en dependencias reales, no una promesa de calendario.

## Respuestas finales (sección 26, A-R)

**A. Arquitectura objetivo:** 4 capas (Runtime/Orquestador, Modelos/Agentes, Tools/Ejecución, Proveedores), con la cadena PROPUESTA→VALIDACIÓN→PERMISOS→TOOL→EJECUCIÓN→VERIFICACIÓN→RESULTADO como regla única para cualquier acción, sin importar qué modelo la propuso (FASE4_A, FASE4_B).

**B. Mínimo sistema a construir primero:** seguridad base (L1/REQ-070) como condición de entrada, y el estado vivo + registro de evidencia como el cimiento transversal que de verdad desbloquea el resto (tabla de roadmap arriba).

**C. Papel del Runtime:** estado, memoria, cola, scheduler, router, permisos, watchdog, observabilidad, recuperación, comunicación con Damián — hoy existe de forma dispersa, esta fase lo reconoce como una sola arquitectura y marca qué falta (FASE4_C).

**D. Papel de los modelos locales:** ejecutar roles especializados (triaje, verificación, resumen) bajo orquestación de código determinista — arquitectura híbrida (Opción D de FASE4_D), sin arquitectura multiagente plena.

**E. Papel de Claude:** arquitecto, razonador profundo, programador, analista, verificador final — reservado por el Router para donde su valor es máximo, nunca el destino por defecto (FASE3_C, FASE4_E).

**F. Papel de Gemini y ChatGPT:** proveedores con capacidades propias más allá de "enviar texto" (búsqueda nativa, proyectos, archivos), organizados bajo `ConversationManager`, elegidos por el Router según su ficha de capacidades (FASE4_F).

**G. Proveedores adicionales:** Perplexity (búsqueda con fuentes, capacidad hoy débil) como el más claro; Copilot/Grok/nuevos modelos locales solo si su ficha de capacidades muestra una carencia real que cubrir — nunca por cantidad (FASE3_D, FASE4_F).

**H. Representación de capacidades:** `PerfilProveedor` extensible, con campos estáticos (editados a mano) y campos dinámicos (alimentados por sondas y por el registro de evidencia) — permite añadir un proveedor con `adapter + capability profile + tests`, sin tocar el Router (FASE4_F).

**I. Cómo funciona el Router:** evalúa tarea/dificultad/riesgo/criticidad/capacidades/disponibilidad/rendimiento observado/cuota/contexto/herramientas/latencia/verificación, y decide 10 cosas (proveedor, modelo, esfuerzo, contexto, herramientas, segunda opinión, verificación, timeout, pasos máximos, fallback), soportando tanto el camino con pasos intermedios como el salto directo a Claude, con la regla de mínimo recurso suficiente (FASE3_E, FASE4_E).

**J. Proyectos y conversaciones:** jerarquía PROVEEDOR→PROYECTO→CHAT→TAREA→CONTEXTO→RESULTADO, índice local + contenido nativo del proveedor, `ConversationManager` como tool de capa C (FASE3_F, FASE4_G).

**K. PC Control Layer:** jerarquía híbrida de 6 niveles (API/CLI, DOM/Playwright, UI Automation, escritorio general, visión, coordenadas) como tool transversal de la capa C, resolviendo a la vez gestión de chats, observación de proveedores y, más adelante, aplicaciones Windows — Playwright evaluado caso por caso, nunca como principio general ni como sustituto de T038 (FASE4_H).

**L. Observabilidad, watchdog y fallback:** una sola cadena FALLO→DETECCIÓN→RECUPERACIÓN→FALLBACK→CONTINUACIÓN/ESCALADO aplicada uniformemente a los cuatro proveedores y a las tools, con timeout/reintentos/detección de bucles siempre acotados, y el estado vivo con cadena de origen como fuente única de verdad (FASE4_I).

**M. Medición de ahorro y eficiencia:** métricas agregadas sobre el mismo registro de evidencia — porcentaje de tareas resueltas localmente vs. escaladas, porcentaje que llega a Claude, motivo del escalado, coste evitado estimado — sin necesitar un experimento aparte (FASE4_I).

**N. Crecimiento de autonomía sin perder control:** ciclo de 8 etapas (se añade MEJORAR) con permiso/límite/observabilidad/rollback en cada una, coincidiendo exactamente con la cadena de ejecución de FASE4_B aplicada a escala de tarea completa (FASE3_J, FASE4_J).

**O. Seguridad a resolver antes:** L1 (`ejecutar_python`) y REQ-070, sin excepción, antes de cualquier ampliación de autonomía o control del PC — y el principio transversal de que los permisos pertenecen a la acción y a la tool, nunca al modelo que la propuso (FASE4_J).

**P. Qué cambia de la arquitectura anterior:** los cuatro puntos de la sección de revisión de arriba (orquestador ambiguo, `navegador.py` mal clasificado, comparación multiagente incompleta, fichas estáticas) — el resto de la Fase 2/3 se mantiene y se organiza dentro de las 4 capas.

**Q. Orden de implementación óptimo:** la tabla de 13 piezas por dependencias de arriba, empezando por seguridad y el par estado-vivo/registro-de-evidencia.

**R. Decisiones que necesito de Damián:** ver NEXT_DECISION_REQUIRED, abajo.

## Prueba de calidad conceptual (sección 27)

- **¿Si Claude desapareciera 24h, seguiría Nexo siendo útil?** Hoy, parcialmente: el bot, la cola de tareas y el triaje de Qwen siguen funcionando sin Claude. Con el Router y el runtime formalizados (piezas 1-5 del roadmap), la respuesta pasa de "parcialmente" a "sí para la mayoría del trabajo mecánico" — el diseño de esta fase apunta exactamente a eso, y es coherente con la arquitectura, no un añadido posterior.
- **¿Podemos integrar un proveedor nuevo sin rehacer la arquitectura?** Sí, por diseño, una vez implementado el patrón `adapter + capability profile + tests` (FASE4_F) — hoy todavía no, porque el Router que consumiría ese perfil no existe.
- **¿Puede Nexo detectar una acción incorrecta de una IA externa antes de ejecutarla?** Sí, por diseño, gracias al eslabón VALIDACIÓN de la cadena de ejecución (FASE4_B) — hoy no, porque esa cadena no está implementada; es la primera vez que esta pregunta tiene una respuesta de diseño clara, antes no la tenía.
- **¿Puede Nexo recuperarse si una herramienta se rompe, sin quedar bloqueado?** Sí, por diseño, con la cadena de fallo formal de FASE4_I — hoy solo parcialmente (el vigilante relanza el bot, `navegador.arrancar()` recupera Chrome, pero no hay una política uniforme para las demás tools).
- **¿Podemos demostrar con métricas que usamos mejor a Claude?** No todavía — es la pieza que más depende de que el registro de evidencia (pieza 1 del roadmap) lleve tiempo funcionando. Es, con diferencia, la respuesta más débil de las cinco, y por eso esa pieza se marca como cimiento transversal y no como algo tardío.

Las cinco preguntas tenían margen de mejora hoy; las cinco tienen ya una respuesta de diseño concreta en esta fase (no todas implementadas todavía, pero todas con un camino claro, no un vacío).

---

## NEXT_DECISION_REQUIRED

No se ha implementado nada. Las decisiones que necesito de ti para empezar la siguiente implementación:

1. **¿Confirmas empezar por la pieza 0 (seguridad: `ejecutar_python` y REQ-070)?** Es la única que toca archivos blindados (`nucleo/permisos.py`, `manos/servidor_mcp.py`) y necesita tu aprobación explícita en el momento, como siempre.
2. **¿Confirmas que la pieza 1 (estado vivo + registro de evidencia, unificados) es el siguiente paso, antes que el Router?** Es el cambio de orden más relevante de esta fase respecto al roadmap anterior — antes trataba observabilidad y evidencia como cosas separadas y más tardías.
3. Todo lo demás (qué modelo local medir primero, si se usa LangGraph, qué proveedor futuro estudiar, el detalle del Caso E de autonomía) no bloquea el arranque — se confirma cuando el roadmap llegue a esa pieza.

No hay ninguna otra pregunta pendiente: el turno de noche ya está pausado y no hace falta volver a preguntar por T039.
