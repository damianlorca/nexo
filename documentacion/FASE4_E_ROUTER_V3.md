# FASE 4 — E. El Router como cerebro de recursos (no un if/else)

## Qué cambia respecto a FASE3_E

FASE3_E ya definía las 10 decisiones y el pipeline de 7 pasos — se mantienen sin cambios de fondo. Esta fase añade dos cosas que Damián pide explícitamente: (1) la lista completa de SEÑALES de entrada que el Router debe evaluar (más rica que "dificultad/riesgo/capacidades" de la Fase 3), y (2) remarcar sin ambigüedad que el Router debe soportar tanto la ruta con pasos intermedios como el salto directo, como dos caminos igual de válidos, no uno por defecto y otro de excepción.

## Señales de entrada (ampliado)

Tarea, dificultad, riesgo, criticidad, capacidades necesarias, disponibilidad del recurso, **rendimiento observado** (nuevo: viene del registro de evidencia, ver más abajo), **uso/cuota actual** (nuevo: cuánto se ha gastado ya hoy de cada proveedor, para no acercarse a un límite como el que causó T042), contexto, herramientas necesarias, latencia tolerable, necesidad de verificación. Todas menos "rendimiento observado" y "uso/cuota" ya estaban implícitas en el diseño de la Fase 3; se hacen explícitas aquí porque son las dos que convierten al Router de "reglas fijas" a "cerebro que usa evidencia real del propio sistema, no solo características estáticas de la tarea".

## Las 10 decisiones (reafirmadas sin cambios, ver FASE3_E para el detalle completo)

Proveedor, modelo, esfuerzo, contexto, herramientas, segunda opinión, verificación, timeout, máximo de pasos, fallback.

## Dos caminos igual de válidos, no un default y una excepción

```
LOCAL -> EXTERNO ADECUADO -> CLAUDE      (cuando cada paso intermedio reduce riesgo/coste)
LOCAL -> CLAUDE                          (cuando la tarea es claramente de las que solo Claude
                                           resuelve bien, y meter un paso intermedio solo
                                           añadiria latencia y una oportunidad más de error)
```

El Router decide cuál de los dos aplica ANTES de empezar a delegar, no como una recuperación de que el camino largo falló — es una clasificación previa (parte de "capacidades necesarias" y "dificultad" en las señales de entrada), no un fallback. Ejemplo concreto ya usado en FASE3_C: una petición de "rediseña este módulo de permisos" no pasa por Qwen ni por Gemini primero — el Router la reconoce como Claude-directo desde el principio.

## Regla explícita de "mínimo recurso suficiente" (no "mínimo recurso a cualquier precio")

Ejemplo dado por Damián, adoptado tal cual como tabla de referencia (no exhaustiva, orientativa):

| Tipo de tarea | Recurso por defecto |
|---|---|
| Trivial (formatear, calcular, mover un archivo) | Local determinista (ni siquiera un modelo) |
| Mecánica (clasificar, extraer un dato) | Tool o modelo local pequeño |
| Moderada (resumir, redactar algo sencillo) | Modelo local mediano |
| Necesidad de búsqueda concreta | Proveedor con búsqueda nativa (Gemini/ChatGPT/futuro Perplexity) |
| Difícil (razonamiento multi-paso, código no trivial) | Claude |
| Crítica (afecta a datos importantes, es difícil de revertir) | Recurso fuerte (normalmente Claude) + verificación obligatoria |

## Aprendizaje por evidencia (reafirmado de FASE3_E, con el formato de registro más explícito que pide Damián)

Se registra, por cada decisión ejecutada: tipo de tarea, proveedor, modelo, resultado (éxito/fallo), tiempo, errores, reintentos, si necesitó intervención humana, si hubo verificación y su resultado. Uso de esta evidencia: reglas de umbral simples y auditables (si un proveedor falla más de una fracción configurable de las veces para una categoría, se retira como opción por defecto hasta revisión manual; si una categoría se resuelve bien en local de forma consistente, baja el umbral de escalado para ella). Nada de esto es machine learning — es una tabla legible que Damián puede abrir y entender línea por línea, y revertir a mano si hace falta. Se implementa DESPUÉS de que el Router básico exista y genere datos reales (ver roadmap).

## Perfiles de capacidad como entrada del Router (ver FASE4_F para el diseño completo)

El Router no evalúa "qué puede hacer Gemini" a mano, cablado en el código — consulta la ficha de capacidades de cada proveedor (FASE3_D, ampliada en FASE4_F para ser extensible). Esto es lo que permite añadir un proveedor nuevo sin tocar el Router: el Router siempre pregunta al perfil, nunca contiene un "if proveedor == gemini" para decidir qué sabe hacer.
