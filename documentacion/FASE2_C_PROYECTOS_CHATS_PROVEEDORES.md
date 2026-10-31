# FASE 2 — C. Sistema de proyectos/chats/contextos por proveedor

## Evidencia real: qué hace `navegador.py` hoy

Leído completo. `preguntar(sitio, prompt, espera)`:
1. Busca, entre las pestañas ya abiertas del Chrome dedicado, la PRIMERA que coincida con el dominio (`gemini.google.com` o `chatgpt.com`).
2. Si no hay ninguna, abre una pestaña nueva en la raíz del sitio.
3. Escribe el prompt en la caja de texto que encuentre visible y espera a que el texto de la página deje de crecer.

No hay ningún concepto de: qué conversación es esa, si es la conversación correcta para la tarea, si existe ya una conversación mejor para continuar, ni de proyectos (Gemini y ChatGPT tienen "Gems"/"Proyectos" propios en sus interfaces, que este código no toca en absoluto). Cada llamada a `preguntar()` reutiliza "la primera pestaña que haya", que es exactamente el problema que describe Damián: si Nexo ya tenía una pestaña abierta de una tarea anterior, la siguiente tarea entra ahí sin comprobar si pertenece a la misma conversación.

## La abstracción pedida

```
PROVEEDOR  →  PROYECTO  →  CHAT/CONVERSACIÓN  →  TAREA  →  CONTEXTO  →  RESULTADO
```

Diseño de cada nivel:

**PROVEEDOR** — ya existe como concepto (`proveedores.py`, T046). No cambia.

**PROYECTO** — concepto NUEVO, a formalizar. Cada proyecto de IA tendría, conceptualmente (Damián los listó y se recogen todos):
`id, nombre, título visible, objetivo, prompt/contexto principal, instrucciones permanentes, archivos, documentación, tareas asociadas, conversaciones asociadas, proveedor preferido, modelos preferidos, memoria asociada, estado, historial, reglas específicas, prioridad`.

Ejemplo real ya existente sin formalizar: el propio proyecto "NEXO" en claude.ai (donde vive esta conversación) ya cumple ese papel para Claude — tiene documentos, memoria y contexto propios. Lo que falta es el equivalente para Gemini y ChatGPT, y un registro LOCAL (en `memoria/`) que sepa que existen y a qué corresponden.

**CHAT/CONVERSACIÓN** — un proyecto puede tener varias conversaciones abiertas (una por sub-objetivo, para no mezclar contextos, como pide Damián). Nexo necesita poder: crear una nueva, seleccionar una existente por su título/objetivo, y detectar en qué conversación está la pestaña que tiene delante ahora mismo — ninguna de estas tres operaciones existe hoy en `navegador.py`.

**TAREA → CONTEXTO → RESULTADO** — ya existe el concepto de tarea (`nucleo/tareas.py`). Lo que falta es la relación explícita: qué proyecto/conversación le corresponde a una tarea dada, y dónde se guarda el resultado cuando vuelve (hoy no vuelve a ningún sitio estructurado: la respuesta de `preguntar()` se devuelve como texto y quien la llamó decide qué hacer con ella, caso por caso).

## Qué vive en archivos locales vs. qué vive dentro de cada proveedor

Pregunta explícita de Damián. Propuesta:

| Vive en LOCAL (`memoria/`) | Vive DENTRO del proveedor |
|---|---|
| El registro de qué proyectos/conversaciones existen y para qué (un índice, no el contenido) | El historial real de la conversación (Gemini/ChatGPT ya lo guardan ellos; duplicarlo localmente es trabajo y desincronización sin beneficio) |
| Qué tarea de Nexo corresponde a qué conversación | Instrucciones permanentes de ESE proyecto específico (mejor vivir donde el proveedor las aplica automáticamente a cada mensaje, que es para lo que existen "Gems"/"Proyectos" de esas plataformas) |
| El resultado final que Nexo necesita usar (resumen o texto completo, según el caso) | El razonamiento intermedio o los intentos fallidos de esa conversación — ruido para Nexo, útil solo si el humano quiere auditar esa IA en concreto |
| Reglas y prioridad del proyecto (esto es criterio de Nexo, no de Gemini/ChatGPT) | — |

Regla general: **el índice y la decisión de a qué conversación ir son de Nexo; el contenido de la conversación en sí es del proveedor.** Esto evita duplicar memoria y mantiene la separación de contextos que Damián pide sin inventar una sincronización compleja.

## Cómo sabría Nexo "en qué chat está" y si es el correcto

Tres piezas necesarias, ninguna existe hoy:
1. **Identificar la conversación activa.** Gemini y ChatGPT no exponen un ID de conversación limpio en la URL de forma consistente en todos los casos (ChatGPT sí lo hace en la URL tras el primer mensaje; Gemini lo hace de forma menos predecible). Fallback: leer el título de la conversación (ambos lo muestran en la interfaz) y compararlo contra el registro local.
2. **Decidir si hace falta una conversación nueva.** Regla simple: si la tarea pertenece a un proyecto sin conversación abierta reciente, o si la conversación abierta ya lleva muchos turnos de un objetivo distinto, se abre una nueva. Se prioriza abrir nueva sobre arriesgarse a mezclar contexto — es más barato una conversación de más que una respuesta contaminada.
3. **Recordar cuál es cuál entre sesiones.** El registro local de proyectos (arriba) guarda, por proyecto, la URL o el título de su conversación activa más reciente, para poder volver a ella en vez de crear una nueva cada vez.

## Relación con el control visual (sección D)

Cuando Playwright no baste para "encontrar la pestaña correcta" (por ejemplo, si hace falta abrir el panel lateral de conversaciones y leer títulos que no son fáciles de seleccionar por selector CSS estable), esta capa es la primera candidata a apoyarse en UI Automation/visión como fallback — ver sección D para la jerarquía de métodos.

## No implementar todavía

Este diseño no se traduce en código en esta fase. El primer paso de implementación razonable, cuando toque, sería: (1) un registro mínimo de proyectos en `memoria/proyectos_ia.json` (formato JSON, similar a `tareas.json`), (2) extender `navegador.py` para leer el título de la conversación activa antes de escribir, sin tocar todavía la lógica de apertura de pestañas. Registrado como P1 en el roadmap (FASE2_L).
