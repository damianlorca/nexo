# FASE 2 — Índice: Revisión integral de la arquitectura operativa de Nexo

Este es el documento maestro de la revisión de arquitectura pedida por Damián tras el cierre de T039. **Nada de lo descrito aquí se ha implementado.** Es análisis, comparación y diseño — el código de producción (`nucleo/`, `extremidades/`, `canal/`, `manos/`) no se ha tocado en esta fase, salvo `memoria/estado.json` y `memoria/tareas.json` (estado y notas, no lógica).

## Documentos de esta fase

| Archivo | Contenido |
|---|---|
| `FASE2_M_CORRECCIONES.md` | Correcciones explícitas a la auditoría anterior (Fase 1), incluyendo el cierre completo de T039 |
| `FASE2_A_QWEN_Y_MODELOS_LOCALES.md` | Auditoría de Qwen, papel recomendado, hardware real, alternativas de modelo local |
| `FASE2_B_MODEL_ROUTER.md` | Diseño del Model Router (proveedor / modelo / esfuerzo / contexto / verificación) |
| `FASE2_C_PROYECTOS_CHATS_PROVEEDORES.md` | Gestión de proyectos/chats en Gemini/ChatGPT, formalización de "proyecto de IA" |
| `FASE2_D_CONTROL_VISUAL.md` | Diseño de control visual/desktop híbrido, jerarquía de 5 niveles, seguridad |
| `FASE2_E_CLAUDE_ESTRATEGIA.md` | Estrategia de integración con Claude: rutinas actuales vs. API Routines vs. Playwright vs. visual |
| `FASE2_F_OBSERVABILIDAD.md` | Observabilidad y control del agente local en tiempo casi real |
| `FASE2_G_ECONOMIA_USO.md` | Auditoría de economía de tokens/recursos y tres políticas de ahorro |
| `FASE2_H_TURNO_DE_NOCHE.md` | Recomendación sobre el turno de noche durante esta fase de reorganización |
| `FASE2_I_AUTONOMIA_INCREMENTAL.md` | Diseño incremental de autonomía (ciclo OBSERVAR→...→REPORTAR) |
| `FASE2_J_SEGURIDAD_PERMISOS.md` | Seguridad/permisos frente a más autonomía y control visual (L1, REQ-070) |
| `FASE2_K_CONSULTA_MULTI_IA.md` | Consulta selectiva a Qwen/Gemini/ChatGPT (2 preguntas) — log completo |
| `FASE2_L_ROADMAP_Y_DEPENDENCIAS.md` | Dependencias entre piezas y orden recomendado de implementación |

## A) Problemas reales encontrados

- Qwen infrautilizado, confirmado por grep (no por impresión) — sección A.
- Ausencia total de un criterio explícito para elegir proveedor/modelo/esfuerzo — sección B.
- `navegador.py` no distingue proyectos ni conversaciones dentro de Gemini/ChatGPT — sección C.
- Cero infraestructura de control visual, y `permisos.py` no tiene ningún concepto de "aplicación" o "acción visual" — secciones D y J.
- T039 se apoyaba en una API real pero de un producto distinto al que Damián tiene — sección M/E, ya cerrada.
- Cero observabilidad de "qué está haciendo Nexo ahora mismo" más allá de un log de eventos pasado — sección F.
- Gasto de contexto/tokens en trabajo que Qwen o un script podrían resolver — sección G.
- L1 (`ejecutar_python` sin control de permisos) y REQ-070 (lectura sin restricción fuera del proyecto) siguen abiertos y se agravan con más autonomía — sección J.

## B) Elementos que funcionan bien y se mantienen

- El propio sistema de niveles VERDE/ÁMBAR/ROJO de `permisos.py` — el modelo es correcto, solo falta extenderlo a nuevas dimensiones de acción (no rehacerlo).
- El patrón de sonda de salud en `extremidades/base.py` (un proveedor caído no rompe el inventario entero).
- El triaje de Qwen para mensajes sueltos — ya funciona bien, no se toca.
- El watchdog de `canal/vigilante.py` (uso correcto de `ctypes`/`OpenProcess`, nunca `os.kill`) — patrón a reutilizar para cualquier control de proceso nuevo.
- `navegador.py` como base técnica de automatización — las carencias son de gestión de conversación/proyecto (sección C), no del mecanismo Playwright/CDP en sí.
- La disciplina "una implementación → prueba real → verificación → documentación" ya seguida en fases anteriores — se mantiene como regla para todo lo que sigue (sección L).

## C) Arquitectura actual a mantener

Rutinas programadas actuales como único mecanismo de arranque autónomo (sección E); Qwen vía Ollama como motor local (sección A, con ampliación de tamaños/roles, no de motor); Telegram como canal móvil (base de la observabilidad recomendada, sección F); estructura de `memoria/`, `nucleo/registro.py` y `permisos.py` como cimientos a extender, no a sustituir.

## D) Arquitectura a cambiar

Ampliar `permisos.py` a acciones visuales/multi-proveedor/origen-de-orden (J); introducir un Model Router explícito en vez de "todo por defecto a Claude" (B); dar a Qwen un tercer nivel de modelo local para verificación barata (A); introducir un archivo de estado vivo + comando `/estado` (F); formalizar el concepto de "proyecto de IA" en `navegador.py` (C).

## E-L) Ver los documentos individuales listados arriba

Cada sección E a L de la petición original de Damián corresponde uno a uno con el archivo del mismo nombre en la tabla de arriba.

## Q) Dependencias entre todas las piezas

Ver `FASE2_L_ROADMAP_Y_DEPENDENCIAS.md` para el mapa completo. Resumen: seguridad (J, la parte de L1/REQ-070) y observabilidad (F) son independientes y van primero; Qwen ampliado (A) y Model Router (B) dependen de esas dos; gestión de proyectos (C) depende del Router; control visual (D) depende de permisos ampliados a lo visual (J, la otra parte); autonomía incremental (I) depende de todo lo anterior y va al final.

## R) Orden recomendado de implementación

1. Seguridad: cerrar L1 y REQ-070.
2. Observabilidad mínima (`estado_actual.json` + `/estado` en Telegram).
3. Ampliar Qwen (resumen + verificación bajo demanda).
4. Vigilante ligero de bucles.
5. Model Router.
6. Políticas de economía de uso.
7. Gestión de proyectos/chats.
8. Permisos ampliados a lo visual/multi-agente.
9. Control visual.
10. Autonomía incremental.

(Detalle completo, con justificación de cada dependencia, en `FASE2_L_ROADMAP_Y_DEPENDENCIAS.md`.)

## S) Decisiones que requieren la aprobación de Damián

1. **Turno de noche:** confirmar si se pausa temporalmente durante esta fase de reorganización (recomendación: sí, opción C) — ver `FASE2_H_TURNO_DE_NOCHE.md`. Sin esta confirmación, la rutina sigue activa tal cual.
2. **Orden de implementación:** confirmar si se retoma implementación siguiendo el orden de `FASE2_L_ROADMAP_Y_DEPENDENCIAS.md`, empezando por seguridad (L1/REQ-070), o si Damián prefiere otro punto de partida.
3. **Alcance del Model Router (sección B) y del papel ampliado de Qwen (sección A):** confirmar que el diseño propuesto (tercer nivel de modelo local "verificador", candidatos Qwen3:8b/Gemma3:12b/DeepSeek-R1-Distill-Qwen-14b a medir) es el que se quiere llevar a implementación, antes de tocar `config.toml`.
4. **T038 (Playwright sobre claude.ai):** confirmar que se mantiene cerrada tal como estaba — esta revisión no encontró motivo para reabrirla, pero es una decisión previa de Damián, no solo de esta auditoría.
5. **Caso E (autonomía, discrepancia 3-vs-1 de la Fase 3):** sigue sin resolver por decreto — Damián debe fijar el umbral de riesgo que le resulta cómodo para que el ciclo OBSERVAR→PROPONER pueda pasar a EJECUTAR sin aprobación previa (ver `FASE2_I_AUTONOMIA_INCREMENTAL.md`).
6. **Interfaz de observabilidad:** confirmar que Telegram (`/estado`) como interfaz principal es suficiente, frente a invertir además en una web local (recomendación: empezar solo con Telegram).

## T) Principales riesgos técnicos

- **Implementar autonomía o control visual antes de cerrar L1/REQ-070** — repetiría el patrón que generó ambos hallazgos (funcionalidad antes que control).
- **Que el turno de noche corra sin pausa mientras estas decisiones siguen abiertas** y contradiga o duplique el propio trabajo de esta revisión (sección H).
- **Que la ampliación de Qwen no se mida de verdad** (banco de pruebas real en este hardware) y se acabe decidiendo por teoría, tanto propia como de las IAs consultadas — ninguna de las tres consultas incluyó una medición real en el equipo de Damián.
- **Dependencia de fuentes externas parcialmente verificadas** — el límite de sesión de `WebFetch` durante esta fase impidió contrastar en profundidad los frameworks nombrados en la consulta multi-IA (sección K); antes de adoptar cualquiera, verificar que sigue mantenido.
- **Repetir el error de T039** (aplicar una solución correcta a un objeto de producto equivocado) si en el futuro se reconsidera la API de Routines sin volver a comprobar primero, en la interfaz real de Damián, que esa vía existe para su cuenta.

---

## NEXT_DECISION_REQUIRED

No se ha implementado nada de esta revisión. Las decisiones que necesito de ti para poder seguir son las seis del apartado **S** de arriba — en concreto, y por orden de urgencia real:

1. **¿Pauso el turno de noche de esta noche mientras dura esta reorganización?** (recomiendo que sí — ver sección H). Sin tu confirmación, sigue activo tal cual.
2. **¿Retomamos implementación por el orden de la sección R (seguridad primero: `ejecutar_python` y la lectura sin restricción fuera del proyecto), o prefieres empezar por otra pieza?**
3. Las otras cuatro decisiones de la sección S (Model Router/Qwen, T038, caso E de autonomía, interfaz de observabilidad) no bloquean el arranque de la implementación de seguridad — puedes confirmarlas más adelante, cuando lleguemos a esa pieza del roadmap.
