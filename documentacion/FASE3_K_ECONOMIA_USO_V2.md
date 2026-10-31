# FASE 3 — K. Economía de uso, revisada para una arquitectura multi-proveedor

## Qué se mantiene de FASE2_G

Las tres políticas (contexto mínimo suficiente, segunda opinión solo si el valor esperado la justifica, no repreguntar lo que ya se sabe) siguen siendo correctas y se mantienen sin cambios de fondo. Lo que cambia es el ALCANCE: antes se aplicaban sobre todo a "cuándo gastar Claude"; ahora se aplican a las llamadas a CUALQUIER proveedor externo (Gemini/ChatGPT también consumen cuota gratuita limitada, y una llamada innecesaria a Gemini, aunque no cueste dinero, sigue costando tiempo y arriesga acercarse a un límite de uso diario).

## La regla explícita de Damián, ya no ambigua

> Si una tarea difícil necesita Claude, se usa Claude. Si una tarea fácil necesita solo local, no se gasta Claude. Si una tarea requiere una capacidad específica de otro proveedor, se usa ese proveedor.

Esto formaliza lo que el Model Router v2 (sección E) ya implementa como "recurso mínimo suficiente" — se registra aquí como la regla de economía explícita porque Damián pide que quede escrita sin ambigüedad, no solo implícita en el diseño del Router.

## Minimizar, en concreto, sobre la arquitectura ampliada

- **Claude:** solo cuando el Router determina que ninguna alternativa local o externa más barata es suficiente para el riesgo/dificultad de la tarea (regla ya fijada en la sección E).
- **Llamadas externas en general (Gemini/ChatGPT incluidos):** sujetas a la misma política de "recurso mínimo suficiente" — no se sustituye "gastar Claude" por "gastar Gemini de forma igual de alegre"; el criterio es siempre local-primero, externo-si-hace-falta, dentro de los externos el más barato/adecuado primero.
- **Contexto repetido:** política 1 sin cambios (usar resúmenes de Qwen en vez de historial completo salvo que el resumen sea insuficiente o esté obsoleto).
- **Prompts innecesarios / respuestas excesivamente largas:** nuevo, explícito en esta fase — el propio Router debería fijar un tamaño de respuesta esperado según el tipo de tarea (una clasificación de triaje no necesita una respuesta de 500 palabras) y pedirlo explícitamente en el prompt, evitando gastar tiempo/tokens en verbosidad no solicitada — aplica tanto a Qwen como a los proveedores externos.
- **Consultas redundantes / segundas opiniones inútiles:** regla del punto 7 (sección E) sin cambios.
- **Reintentos:** acotados por el máximo de pasos del Router (sección E) y por el tope de recuperaciones de la sección J — nunca reintentos indefinidos.

## Relación con el aprendizaje por evidencia (sección E)

La economía de uso deja de ser solo un conjunto de reglas fijas en el momento en que existe el registro de evidencia: si un tipo de tarea empieza a mostrar más reintentos o escalados de los esperados, eso es una señal tanto de "puede que el modelo local elegido sea insuficiente" (ajustar el Router) como de "puede que se esté gastando de más sin necesidad" (si el escalado resulta innecesario tras verificar). Ambas lecturas se derivan del mismo dato, sin necesitar un sistema de análisis aparte.
