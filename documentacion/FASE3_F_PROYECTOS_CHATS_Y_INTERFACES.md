# FASE 3 — F. Gestión de proyectos/chats y una abstracción más rica sobre Gemini/ChatGPT

## La jerarquía (se mantiene de la Fase 2, sin cambios de fondo)

```
PROVEEDOR -> PROYECTO -> CHAT -> TAREA -> CONTEXTO -> RESULTADO
```

Campos de "proyecto de IA" (ya listados en FASE2_C, reafirmados aquí tal como los repite Damián): id, título, objetivo, prompt principal, instrucciones permanentes, documentación, archivos, memoria, tareas, chats asociados, proveedor preferido, modelos preferidos, reglas, estado, historial.

**Qué vive en local vs. qué vive dentro de cada proveedor:** el objetivo, las instrucciones permanentes y el registro de qué chat corresponde a qué proyecto viven en local (`memoria/` o un nuevo `proyectos_ia.json`) porque son el "índice" que Nexo necesita para decidir dónde escribir; el contenido de la conversación en sí (historial de mensajes) puede quedarse donde ya vive de forma nativa (el propio historial de Gemini/ChatGPT), evitando duplicar terabytes de texto que el proveedor ya guarda — Nexo solo necesita saber "qué conversación es esta" y "cuándo se tocó por última vez", no una copia completa.

## Cómo evitar que un chat acumule contexto irrelevante durante semanas (pregunta explícita de Damián)

Tres mecanismos, combinables:
1. **Un chat por objetivo concreto, no por proveedor genérico** — la propia jerarquía ya lo impone: "proyecto Nexo → chat de diseño de arquitectura" es distinto de "proyecto Nexo → chat de depuración de navegador.py". Mezclar objetivos en un mismo chat es la causa raíz de la acumulación irrelevante, y se evita por diseño si el Router sabe "a qué chat pertenece esta tarea" antes de escribir.
2. **Vencimiento por inactividad** — si un chat no se usa en N días y el objetivo asociado ya se dio por cerrado (estado del proyecto = terminado), se marca como archivado en el índice local: no se borra nada en el proveedor (eso no está en manos de Nexo ni es deseable), pero Nexo deja de proponerlo como destino por defecto.
3. **Resumen periódico, no relectura completa** — igual que la Política 1 de economía de uso (FASE2_G): antes de retomar un chat inactivo, usar un resumen (generado por Qwen o por el propio proveedor si lo ofrece) en vez de mandarle todo el historial de nuevo como contexto.

## Qué debería existir conceptualmente en una versión más rica de `navegador.py`

Damián pide diseñar, no implementar, las siguientes capacidades nuevas sobre la base de Playwright/CDP ya en uso:

- **Crear conversación** — navegar al botón "nuevo chat" del sitio, o directamente a la URL raíz (`chatgpt.com/`, `gemini.google.com/app`) que abre un chat limpio (ver hallazgo de la consulta, más abajo).
- **Seleccionar conversación existente por título** — requiere poder leer la lista de conversaciones del sitio (leer el DOM de la barra lateral) y hacer clic en la que coincida con el título registrado en el índice local del proyecto, **o, preferiblemente, navegar directamente a la URL de esa conversación si se guarda su identificador** (ver hallazgo de la consulta).
- **Detectar conversación/proyecto actual** — leer el DOM (o la propia URL activa) para saber en qué conversación/carpeta está la pestaña antes de escribir, comprobando varias señales independientes a la vez (URL, título del proyecto, nombre de conversación, un elemento del DOM inequívoco) antes de escribir — si no coinciden, no escribir.
- **Trabajar dentro de un proyecto/carpeta** (ChatGPT tiene esto de forma más madura que Gemini, según la experiencia de Damián) — navegar a la carpeta antes de crear o seleccionar el chat.
- **Subir/usar contexto cuando corresponda** — adjuntar un archivo a la conversación cuando la tarea lo requiera, reutilizando el mismo tipo de interacción de UI que ya usa `navegador.py` para escribir texto.
- **Verificar que se está trabajando en el espacio correcto** — combinación de las dos anteriores: antes de cualquier envío, comprobar proyecto+conversación actual contra lo esperado, y abortar/avisar si no coincide en vez de escribir en el sitio equivocado.

## Hallazgos de la consulta multi-IA de esta fase (ver FASE3_L_CONSULTA_MULTIIA.md)

Dos aportes concretos que no estaban en el diseño original de esta sección:

1. **Navegación por URL directa, más estable que clicar la barra lateral.** Gemini señaló que tanto ChatGPT (`chatgpt.com/c/{id}`) como Gemini (`gemini.google.com/app/{id}`) exponen la conversación activa en la propia URL — navegar directamente a esa URL para "seleccionar conversación" es más robusto que depender de selectores CSS de la barra lateral, que cambian con más frecuencia. Se adopta como método PREFERENTE para seleccionar una conversación ya conocida (guardando su identificador en el índice local del proyecto), reservando la lectura de la barra lateral solo para el caso de "buscar por título" cuando no se conoce todavía el identificador.
2. **Patrón `ConversationManager`.** ChatGPT propuso estructurar esto como una capa propia con métodos abstractos (`list_projects`, `select_project`, `list_chats`, `select_chat`, `new_chat`, `assert_context`, `send`) y un adaptador independiente por proveedor debajo — es una forma limpia de organizar exactamente las capacidades listadas arriba, y se adopta como la forma concreta de estructurar esta ampliación de `navegador.py` cuando se implemente (ver roadmap, sección N).

## Riesgos y límites, honestos (actualizado con la consulta de esta fase)

Todo lo anterior depende de leer el DOM (o, en el mejor caso, solo la URL) de interfaces web de terceros que Anthropic no controla y que cambian sin aviso — es un riesgo de mantenimiento, no de condiciones de uso para Anthropic (T038 sigue siendo el caso distinto de claude.ai). **Dato nuevo a tener en cuenta, con honestidad:** la consulta a ChatGPT citó el texto concreto de las condiciones de uso de OpenAI, que prohíben expresamente la extracción automática/programática de datos o resultados — más específico que la referencia genérica a "riesgo de ToS" que ya constaba en la Fase 1/2. Esto no cambia por sí solo la decisión ya tomada por Damián de automatizar Gemini/ChatGPT con su propia sesión (un riesgo que él ya asumía de forma consciente, distinto del caso de Anthropic), pero es información más concreta que antes y se traslada tal cual para que la tenga presente — sin que esta revisión decida nada al respecto por su cuenta (ver NEXT_DECISION_REQUIRED del índice). La recomendación de tratar esta capa como "adaptador experimental sustituible, no como dependencia fundamental" (también sugerida por ChatGPT) se adopta como principio de diseño: cualquier ampliación de `navegador.py` debe seguir funcionando (en un modo más limitado) si esta capa concreta se rompe por un cambio de interfaz o de política.

## Recomendación de orden

No implementar esta capa completa de una vez. Empezar por la función más barata y de mayor valor: "detectar conversación/proyecto actual y verificar antes de escribir" (con navegación por URL cuando sea posible) — es la que previene el error más caro (escribir en el chat equivocado), y no requiere todavía "crear/seleccionar" para dar valor. El resto se añade de forma incremental, cada pieza con su propia prueba real antes de la siguiente (disciplina ya fijada por Damián para todo el roadmap).
