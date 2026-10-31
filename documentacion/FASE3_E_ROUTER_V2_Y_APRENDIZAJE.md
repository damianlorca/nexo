# FASE 3 — E. Model Router v2 (10 decisiones) y aprendizaje basado en evidencia

## Por qué el Router de la Fase 2 se queda corto

FASE2_B diseñaba el Router como un clasificador de "a qué proveedor/modelo mandar esto". Damián pide ahora que decida, cuando proceda, hasta 10 cosas: proveedor, modelo, nivel de razonamiento/esfuerzo, contexto, herramientas, necesidad de segunda opinión, necesidad de verificación, timeout, número máximo de pasos, y fallback. Es una ampliación real, no cosmética — las últimas cuatro (timeout, pasos máximos, fallback, herramientas) conectan directamente con la observabilidad y el control de ejecución (sección H), que en la Fase 2 vivían en un documento aparte sin conexión explícita con el Router.

## Las 10 decisiones, una por una

1. **Proveedor** — Claude / Gemini / ChatGPT / Qwen-local / (futuro) Perplexity — según la ficha de capacidades de la sección D y la regla de "recurso mínimo suficiente" (ver más abajo).
2. **Modelo dentro del proveedor** — p. ej. qwen2.5:7b vs. qwen3:14b vs. el candidato de verificación (sección B); en Claude, ya viene fijado por la rutina/sesión, no es una decisión del Router hoy (limitación conocida, T034).
3. **Nivel de razonamiento/esfuerzo** — aplicable sobre todo en local (activar/desactivar "thinking" en Qwen3) y, cuando la interfaz lo permita, en los otros proveedores (relacionado con la sección G de control del PC: cambiar el nivel de razonamiento en una interfaz web es una acción visual/estructurada, no una llamada de API en el caso de Gemini/ChatGPT).
4. **Contexto** — cuánto se manda: resumen de Qwen vs. historial completo, según la Política 1 de FASE2_G ("contexto mínimo suficiente"), que se conserva sin cambios en esta fase.
5. **Herramientas** — si la tarea necesita function-calling/búsqueda/archivos, filtra directamente qué proveedores son candidatos (ver ficha de capacidades, sección D) antes incluso de comparar calidad.
6. **Necesidad de segunda opinión** — regla ya fijada (FASE2_G, reafirmada en FASE3_C): solo si hay varias alternativas razonables + coste de error alto + motivo concreto de insuficiencia del primer resolutor.
7. **Necesidad de verificación** — determinada por el nivel de riesgo/permiso de la acción (sección J), no por el volumen de trabajo — una acción ÁMBAR/ROJA siempre verifica, aunque cueste más.
8. **Timeout** — límite de tiempo por paso, alimenta directamente al vigilante de bucles (sección H) y a la recuperación (sección J).
9. **Número máximo de pasos** — evita que una tarea delegada a un proveedor/agente se quede reintentando indefinidamente; se registra en el estado vivo (sección H) para poder pausarla o matarla desde fuera.
10. **Fallback** — qué hacer si el proveedor elegido falla, está bloqueado, o supera un límite de uso (el caso real ya observado en T042): degradar a un proveedor más disponible en vez de fallar en seco, con un tope de degradaciones para no acabar mandando todo a Claude "por si acaso" cuando el problema era puntual.

## "Mejor modelo posible" vs. "modelo mínimo suficiente"

Es la distinción central que pide Damián, y conviene fijarla como regla explícita del Router, no como intuición: el objetivo del Router **no es maximizar la calidad esperada de cada respuesta individual** (eso siempre apuntaría a Claude) — es maximizar la calidad **suficiente para el riesgo de esa tarea concreta, al menor coste total**. Concretamente:

- Si el nivel de permiso de la acción es VERDE y la tarea es mecánica → el modelo mínimo suficiente que ya la resuelve bien (medido, no supuesto) es la elección correcta, aunque exista un modelo "mejor" disponible.
- Si el nivel de permiso es ÁMBAR/ROJO, o la tarea es de las que el propio Damián reserva para Claude (arquitectura, código no trivial, análisis complejo del propio proyecto) → el "mejor disponible" es el mínimo suficiente, porque el riesgo de un resultado mediocre es alto.
- La frontera entre ambos casos es precisamente lo que el aprendizaje por evidencia (más abajo) debería ir afinando con el tiempo, en vez de quedar fija para siempre en una tabla escrita hoy.

## Pipeline actualizado

```
TAREA
  -> DIFICULTAD (estimada por Qwen/router, o heredada del peso de nucleo.tareas.modelo_sugerido)
  -> RIESGO (nivel de permiso, seccion J)
  -> CAPACIDADES NECESARIAS (busqueda / codigo / vision / razonamiento profundo / herramientas)
  -> RECURSO MAS BARATO/LOCAL QUE SEA SUFICIENTE (segun fichas de la seccion D)
  -> ESCALADO SI NO BASTA (con tope de reintentos/pasos, punto 8-9 arriba)
  -> VERIFICACION (si el riesgo lo exige, seccion J)
  -> RESULTADO (registrado como evidencia, ver abajo)
```

## Aprendizaje basado en evidencia (no machine learning todavía)

Damián pide un sistema sencillo y auditable, no un modelo que aprenda de forma opaca. Diseño concreto:

**Qué registrar por cada decisión del Router** (ampliando lo que ya hace `nucleo/uso.py` para Claude, generalizándolo a todos los proveedores): tarea (tipo/categoría), proveedor elegido, modelo, resultado (éxito/fallo), tiempo, número de reintentos, si necesitó escalar a otro proveedor, si necesitó intervención humana, resultado de la verificación (si la hubo).

**Cómo se usa esa evidencia (reglas simples, no ML):**
- Si un proveedor falla o necesita reintento en más de una fracción configurable de las tareas de una categoría concreta (p. ej. "más de 1 de cada 3 en los últimos N intentos"), el Router deja de proponerlo por defecto para esa categoría hasta que alguien lo revise — una regla de umbral simple, auditable, reversible a mano.
- Si una categoría de tarea se resuelve con éxito de forma consistente en local, el umbral de "cuándo escalar" para esa categoría puede bajar (menos escalado, más confianza) — y al revés si empieza a fallar.
- Todo esto vive en un archivo legible (JSON o tabla), nunca en pesos de un modelo entrenado — cualquier ajuste que el sistema proponga debe poder leerse y revertirse por Damián sin necesitar entender un modelo de ML.

Esta pieza depende de que exista ya el Router básico (sin aprendizaje) funcionando y generando datos reales — no tiene sentido diseñar el aprendizaje antes de tener nada que aprender de verdad (ver orden en el roadmap, sección N).
