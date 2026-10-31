# FASE 3 — L. Consulta selectiva multi-IA (replanteamiento de arquitectura)

Dos preguntas, elegidas porque son las dos decisiones de esta fase donde de verdad hay alternativas técnicas concretas y el conocimiento de otras IAs puede aportar algo que Claude no tenga de primera mano: patrones de orquestación multiagente local en 2026, y automatización de gestión de conversaciones/proyectos sobre interfaces web. Mismo método que en la Fase 2 (Qwen local primero, Gemini/ChatGPT después vía `navegador.py` con pausas largas). Script: `consulta_replanteamiento.py`. Resultados completos en `registros/replanteamiento_arquitectura.json`/`.txt`.

---

## Pregunta 1 — ¿Multiagente local o un modelo único con orquestación por código?

| | Qwen (local) | Gemini | ChatGPT |
|---|---|---|---|
| Recomendación | Opción (a): varios agentes locales especializados, con AutoGen/CrewAI/LangGraph | Opción (b): un solo modelo local + orquestación determinista en Python | Opción (b): un solo modelo local + orquestación determinista en Python |
| Framework señalado | AutoGen (flexibilidad de roles), LangGraph (estados complejos) | **LangGraph** (recomendación principal), PydanticAI (ligero); desaconseja CrewAI/AutoGen para este caso | **LangGraph** (primera elección); Microsoft Agent Framework (si interesa integración Windows); desaconseja AutoGen/CrewAI como núcleo |
| Argumento contra el multiagente pleno | (no se plantea, Qwen lo recomienda) | Sobrecarga de tokens/RAM, indeterminismo: "un LLM decidiendo si llama a otro LLM falla con frecuencia" | Varios modelos grandes residentes desperdician RAM/CPU y complican la concurrencia sin necesidad |

**Coincidencia clara 2 contra 1:** Gemini y ChatGPT, de forma independiente, recomiendan lo mismo que ya proponía el análisis propio de Claude en `FASE3_B_MODELOS_LOCALES_Y_MULTIAGENTE.md` ANTES de conocer esta consulta: **un modelo local reutilizado con distintos prompts/roles + orquestación determinista en código, no un "agente orquestador" que sea él mismo un LLM con ciclo de decisión propio.** Ambas señalan además el mismo framework concreto para la parte de estado/flujo: **LangGraph** (grafos de estado, checkpoints, recuperación de errores, soporte nativo para Ollama) — no mencionado en el análisis original de esta fase, y que se incorpora ahora como candidato concreto a evaluar quando llegue el turno de implementar el Model Router (sección E/N).

**Discrepancia:** Qwen local recomienda el camino contrario (multiagente con AutoGen/CrewAI) — de nuevo, con la misma cautela ya aplicada en la Fase 2: es la respuesta de un modelo evaluándose a sí mismo, con el sesgo de recomendar el escenario donde "varios Qwen" tendrían más protagonismo. No se sigue esta recomendación.

**Conclusión (ya adoptada en FASE3_B, ahora reforzada 2-contra-1 por evidencia externa):** orquestación por código determinista, un modelo local reutilizado con distintos prompts según el rol, y **LangGraph como candidato concreto a evaluar** para la parte de gestión de estado/flujo cuando se implemente el Model Router.

---

## Pregunta 2 — Gestión de conversaciones/proyectos sobre Gemini/ChatGPT vía navegador

| | Qwen (local) | Gemini | ChatGPT |
|---|---|---|---|
| ¿Existe ya una librería que resuelva esto? | No | No (mismo diagnóstico) | No de forma estable — hay proyectos parciales |
| Alternativa señalada | Construir a mano leyendo el DOM | **Navegación por URL directa** (`chatgpt.com/c/{id}`, `gemini.google.com/app/{id}`) en vez de clicar la barra lateral — más estable que depender de selectores | Proyectos de referencia a estudiar (no adoptar tal cual): `chatgpt-mcp` (Playwright persistente con `select_project`/`new_chat`), `gemini-web-automater` (más básico) |
| Patrón de diseño sugerido | (no se detalla) | (no se detalla) | Capa propia `ConversationManager` con métodos abstractos (`list_projects`, `select_project`, `list_chats`, `select_chat`, `new_chat`, `assert_context`, `send`) y un adaptador por proveedor debajo |
| Riesgo de ToS | Menciona el riesgo en general | Menciona fragilidad de selectores + riesgo de ToS/Cloudflare en general | **Cita el texto concreto**: las condiciones de OpenAI prohíben expresamente la extracción automática/programática de datos o resultados y eludir límites/protecciones — recomienda tratar esto como "adaptador experimental sustituible", no como dependencia fundamental |

**Aporte nuevo real (justifica la consulta):** la navegación por URL directa a una conversación concreta (en vez de clicar en la barra lateral) es una idea concreta y útil que no estaba en el diseño original de `FASE3_F_PROYECTOS_CHATS_Y_INTERFACES.md` — se incorpora ahí como método preferente (más estable que leer el DOM de la barra lateral) para "seleccionar conversación existente". El patrón `ConversationManager` con un adaptador por proveedor de ChatGPT también es una buena forma concreta de estructurar lo ya diseñado en la sección F, y se referencia allí.

**Advertencia que Damián debería conocer, con honestidad (no es un cambio de recomendación, es información nueva):** ChatGPT citó el texto de sus propias condiciones de uso como algo que prohíbe explícitamente la extracción automática de datos — más concreto que la referencia genérica a "riesgo de ToS" que ya constaba en la Fase 1/2. Esto no cambia la decisión ya tomada por Damián (Gemini/ChatGPT sí se automatizan, a diferencia de claude.ai) porque esa decisión ya asumía un riesgo de este tipo de forma consciente — pero al ser una cita más concreta que antes, se registra aquí explícitamente para que Damián la tenga presente, sin que esta revisión decida nada por su cuenta al respecto (ver nota en el índice).

---

## Nota de fiabilidad

Mismo método y mismas limitaciones que en la consulta de la Fase 2: pausas largas para evitar el bug de extracción ya conocido de `navegador.py`, y los nombres de librerías/proyectos citados (chatgpt-mcp, gemini-web-automater, Microsoft Agent Framework) no se han verificado en profundidad por acceso limitado a `WebFetch` durante esta sesión — antes de adoptar cualquiera como dependencia real, comprobar que sigue mantenido.
