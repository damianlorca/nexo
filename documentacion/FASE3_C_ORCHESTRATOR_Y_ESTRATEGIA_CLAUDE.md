# FASE 3 — C. El orquestador local como primer filtro, y cuándo sí ir directo a Claude

## La arquitectura propuesta por Damián, evaluada con realismo

```
DAMIÁN → NEXO LOCAL → ENTENDER → CLASIFICAR → PLANIFICAR
       → RESOLVER LOCALMENTE LO QUE PUEDA → DELEGAR SOLO LO NECESARIO
       → VERIFICAR → SINTETIZAR → DAMIÁN
```

Esto es, en esencia, el Model Router de la Fase 2 (FASE2_B) puesto en el centro del flujo en vez de como una consulta que Claude hace de pasada. El cambio de fondo: hoy, cuando Damián manda un mensaje por Telegram, la ruta por defecto es Qwen (triaje) → nada más, salvo que se abra una sesión de Claude. En la arquitectura propuesta, **el propio Nexo local decide activamente si necesita a Claude, y solo entonces lo invoca** (vía las rutinas/`/ahora`, ver sección I). Es una diferencia real: pasar de "Qwen informa, Claude decide todo lo demás" a "Qwen/el Router deciden lo que pueden, Claude entra solo cuando hace falta".

**Es viable con lo que ya existe hoy, con una pieza nueva:** `extremidades/triaje.py` ya clasifica y `proveedores.py` ya unifica el envío a cada proveedor — falta la pieza intermedia que decide y ejecuta el plan, que es exactamente el Model Router (no implementado). No es una arquitectura especulativa: es la extensión natural de piezas que ya existen.

**El límite realista que hay que reconocer:** un "orquestador local" que decide "¿necesito visión? ¿necesito Claude? ¿necesito intervención humana?" con las preguntas que lista Damián en el punto 4 es, en el fondo, una tarea de clasificación con muchas categorías posibles y zonas grises. Un modelo local de 7-14B puede acertar en los casos claros (esto es una tarea de un paso, mecánica, VERDE) pero fallará en los límites difusos (¿esto necesita "una segunda opinión" o no?). **Esto no es un motivo para no construirlo — es el motivo por el que necesita verificación y un histórico de evidencia (sección E) desde el primer día, no confianza ciega desde el principio.**

## Diseño concreto: qué preguntas resuelve el orquestador y con qué

Aterrizando la lista del punto 4 de Damián a algo implementable (sin implementar todavía):

| Pregunta que debe responder el orquestador | Cómo se resuelve hoy (si existiera) |
|---|---|
| ¿Puedo resolverlo yo (localmente)? | Clasificación por Qwen/router: tarea mecánica, de bajo riesgo, sin necesidad de razonamiento profundo ni de datos externos → sí |
| ¿Necesito código? | Si la tarea es "ejecutar/verificar un script ya existente" → local (Python + Qwen para interpretar el resultado). Si es "escribir código nuevo no trivial" → normalmente Claude (ver más abajo) |
| ¿Necesito buscar? | Búsqueda web simple y factual → candidato a Gemini/ChatGPT/Perplexity (con capacidad de búsqueda nativa) antes que Claude, ver sección D |
| ¿Necesito visión? | Depende de si es visión sobre la pantalla del propio PC (sección G, control visual) o sobre una imagen aportada — ninguno de los modelos locales actuales de Nexo tiene visión activada; sería Gemini/ChatGPT/Claude según el caso |
| ¿Necesito Gemini/ChatGPT/Claude? | Aquí decide el Model Router (sección E) según la ficha de capacidades de cada proveedor (sección D) |
| ¿Necesito varios agentes? | Rara vez, con la arquitectura recomendada en la sección B (few especializaciones, no multiagente pleno) — se reserva para tareas donde de verdad conviene contrastar (ver "segunda opinión" abajo) |
| ¿Necesito una segunda opinión? | Regla ya fijada en FASE2_G y reafirmada aquí: solo si (a) hay más de una alternativa razonable, (b) el coste de equivocarse es alto, y (c) el conocimiento del primer resolutor tiene una razón concreta para ser insuficiente |
| ¿Necesito intervención humana? | Determinado por el nivel de permiso de la acción (AMBAR/ROJO, sección J), no por el orquestador decidiéndolo libremente |

## Cuándo ir LOCAL → CLAUDE directo, sin pasos intermedios

Damián pide explícitamente no forzar siempre una etapa intermedia — a veces LOCAL → EXTERNO ADECUADO → CLAUDE solo añade coste y errores. Regla propuesta:

**Ir directo a Claude (saltándose Gemini/ChatGPT/verificación local) cuando se cumple cualquiera de:**
- La tarea es, por su naturaleza, de las que ya se sabe que solo Claude resuelve bien en este sistema (arquitectura de software, cambios de código no triviales, análisis que requiere mantener mucho contexto propio del proyecto Nexo — Claude es quien tiene ese contexto real, no los otros proveedores).
- Es una tarea de un solo paso donde meter un intermediario (clasificar con Qwen, consultar Gemini) claramente no cambiaría la decisión final, solo añadiría latencia — el propio Damián lo pide así en el punto 5 ("cuando la tarea es claramente lo bastante compleja como para que una etapa intermedia solo añada coste y errores").
- Ya existe evidencia histórica (sección E) de que para ese tipo concreto de tarea, los pasos intermedios fallan o no aportan.

**Pasar por local/externo adecuado primero, en todos los demás casos** — que es, por volumen, la mayoría del trabajo mecánico y repetitivo de Nexo.

## Qué debe seguir haciendo Claude (para no caer en "Claude solo programa")

Explícitamente, y sin ambigüedad: arquitecto, razonador profundo, programador, analista, diseñador de soluciones, verificador final de decisiones importantes, solucionador de problemas difíciles — tal como pide Damián en el punto 5. La regla de esta fase no reduce el ROL de Claude, reduce el VOLUMEN de trabajo trivial que hoy llega a Claude sin haber pasado antes por un filtro barato. Un ejemplo concreto que ya se identificó en FASE2_A y sigue vigente: Claude sigue siendo quien decide el diseño del propio Model Router (esta misma revisión es un ejemplo), pero no debería ser quien revisa si un JSON es válido.
