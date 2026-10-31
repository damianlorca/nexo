# FASE 3 — G. Reconsideración: el control del PC como infraestructura transversal, no como última pieza

## Qué cambia respecto a FASE2_D

La Fase 2 (FASE2_D) proponía la misma jerarquía de 5 niveles (estructurado/API → UI Automation/accesibilidad → automatización de escritorio → visión → coordenadas) pero la situaba **al final del roadmap**, tratándola como la pieza más nueva y arriesgada, a construir solo después de que todo lo demás estuviera maduro. Damián pide reconsiderar esto: si el PC es el centro operativo de Nexo (sección A), la capacidad de actuar sobre el propio PC no es un lujo — es la infraestructura que hace posible varias de las otras piezas de esta misma fase:

- **Gestión de chats de Gemini/ChatGPT (sección F)** ya depende de acciones tipo UI Automation (seleccionar conversación, verificar proyecto activo) — no es "control visual" en el sentido más ambicioso (clicar cualquier ventana), pero es la misma jerarquía de niveles aplicada a un caso concreto y ya necesario.
- **Cambiar el nivel de razonamiento o el modelo en una interfaz web** (mencionado en el punto 9 y el punto 12) es, en la práctica, una acción de UI Automation sobre un desplegable — otra vez la misma infraestructura.
- **Observar el uso/límites de Claude visualmente** (mencionado explícitamente por Damián en la Fase 2 original como caso de uso) también requiere esta capa.

**Conclusión: no se trata de "control visual como funcionalidad aislada al final", sino de una capa de infraestructura (niveles 1-3 de la jerarquía, sobre todo) que varias piezas de esta fase necesitan de forma parcial y anticipada.** Esto NO significa construir la versión completa y ambiciosa (nivel 4-5, visión y coordenadas sobre cualquier aplicación) antes de tiempo — significa que los niveles 1-3, aplicados a los casos concretos ya identificados (Gemini/ChatGPT, el propio Claude cuando aplique), pueden y deben adelantarse en el roadmap, mientras que el nivel más genérico y arriesgado (controlar cualquier aplicación de Windows con visión) sigue esperando a que la seguridad (sección J) esté lista.

## La jerarquía híbrida, reafirmada

1. API/CLI oficial cuando exista.
2. DOM/Playwright — ya en uso para Gemini/ChatGPT; se amplía en la sección F.
3. Accesibilidad/UI Automation (Windows) — pywinauto/FlaUI/uiautomation, confirmado por la consulta multi-IA de la Fase 2 (FASE2_K) como el estado del arte 2026, con frameworks orientados a agentes ya identificados (Windows-Use, winapp-ui, Windows-MCP/FlaUI-MCP) pendientes de verificar en profundidad.
4. Automatización de escritorio general (PyAutoGUI) — último recurso estructurado.
5. Visión/coordenadas — solo cuando nada de lo anterior resuelve el caso.

## Qué resuelve esta capa, más allá de "clicar cosas"

Tal como pide Damián en el punto 12, esta infraestructura es la base común para: gestión de chats (sección F), control de Gemini/ChatGPT/Claude cuando la interacción lo requiera, observación de límites/estado de cada proveedor, cambio de modelo/razonamiento cuando la interfaz lo permita, interacción con aplicaciones de Windows sin API, y procesos sin API en general. Es decir: no es una pieza que sirve solo a "un caso de uso visual", es la capa que subyace a media docena de necesidades ya identificadas en esta misma fase.

## Los cuatro (cinco) calificativos que pide Damián, aplicados con rigor

Para cualquier técnica candidata de esta capa, distinguir siempre:

- **Técnicamente posible** — casi todo lo listado aquí lo es, incluida visión sobre cualquier ventana.
- **Fiable** — depende del nivel: los niveles 1-3 son notablemente más fiables que 4-5 porque no dependen de que un elemento esté en una posición de píxel concreta; la fiabilidad de la automatización de Gemini/ChatGPT ya demostrada (con el bug de extracción ya resuelto) es evidencia real de que el nivel 2 (DOM/Playwright) es viable en producción para estos casos.
- **Seguro** — depende enteramente de que el sistema de permisos (sección J) tenga ya el concepto de "aplicación/ventana permitida" antes de dar acceso — sin eso, cualquier nivel es inseguro por definición, no por la técnica en sí.
- **Mantenible** — los niveles 1-2 son más mantenibles que 3, que a su vez es más mantenible que 4-5 (un cambio de interfaz rompe menos cosas cuanto más estructurado es el método).
- **Permitido por las condiciones de uso** — ya resuelto de forma diferenciada: Gemini/ChatGPT vía navegador (nivel 2) es aceptable (terceros, sesión propia, ya en uso); claude.ai vía navegador NO lo es (T038, se mantiene cerrada); aplicaciones de Windows propias del PC de Damián no tienen esta restricción en absoluto (es su propio equipo).

**Nota de la consulta multi-IA (ver documento de consulta):** Qwen local advirtió explícitamente sobre el riesgo de términos de uso al automatizar Gemini/ChatGPT vía DOM en vez de API — esta advertencia es correcta como principio general, pero ya fue evaluada en la Fase 2 (T038 la distingue explícitamente de navegador.py) y Damián ya asumió ese riesgo de forma consciente para Gemini/ChatGPT (no para Claude). No cambia la decisión ya tomada, pero se registra la advertencia por transparencia, y refuerza que cualquier ampliación de la automatización de Gemini/ChatGPT (sección F) debe seguir siendo proporcionada (lo mínimo necesario), no una réplica completa de sus interfaces.

## Recomendación de secuenciación (no un "todo o nada" al final)

1. **Ya (adelantado respecto a FASE2_D):** nivel 2 aplicado a la gestión de chats de Gemini/ChatGPT (sección F) — extensión natural de lo que ya funciona, sin nueva superficie de riesgo de seguridad significativa (sigue siendo Playwright sobre una sesión ya autorizada).
2. **Después de cerrar seguridad base (L1/REQ-070, sección J):** nivel 3 (UI Automation) para casos concretos y acotados por una lista blanca explícita — empezar por observar (leer estado, ej. cuota de Claude visible en pantalla), no por actuar, para minimizar riesgo mientras se gana confianza.
3. **Al final, como ya proponía FASE2_D:** niveles 4-5 (automatización de escritorio general y visión) para el caso genérico "controlar cualquier aplicación de Windows" — este SÍ sigue siendo el más arriesgado y el que más espera a que el resto de controles (permisos, observabilidad) estén maduros.
