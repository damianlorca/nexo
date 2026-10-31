# FASE 3 — J. Seguridad antes que autonomía, y niveles de autonomía con límites explícitos

## El principio rector, tal como lo fija Damián

**CAPACIDAD SIN CONTROL = NO.** Esta fase no relaja en ningún punto lo ya establecido en FASE2_J: L1 (`ejecutar_python` sin permisos) y REQ-070 (lectura sin restricción fuera del proyecto) siguen siendo los dos agujeros más graves conocidos, y condicionan la concesión de CUALQUIER capacidad nueva de esta fase (más proveedores, control del PC, multiagente local, mayor autonomía). No se repite aquí el análisis técnico de ambos (ya está completo en FASE2_J) — se reafirma la conclusión: cerrarlos es un prerrequisito, no una tarea paralela de prioridad similar a las demás.

## Qué añade esta fase al modelo de permisos

FASE2_J ya proponía extender `permisos.py` a tres dimensiones nuevas: aplicación/ventana, proveedor externo, origen de la orden. Esta fase añade una cuarta, derivada directamente del Model Router v2 (sección E) y de la arquitectura local-first (sección A):

- **Nivel de autonomía de la decisión del Router:** no toda decisión del Router tiene el mismo riesgo — decidir "esto va a Qwen para triaje" es de bajísimo riesgo; decidir "voy a ejecutar este comando que Gemini propuso, sin que Claude lo revise" es de riesgo alto. El sistema de permisos debe poder distinguir entre "el Router decide qué proveedor consultar" (bajo riesgo, es solo una lectura/consulta) y "el Router decide ejecutar una acción sugerida por un proveedor externo sin revisión humana ni de Claude" (alto riesgo, requiere el nivel ÁMBAR/ROJO correspondiente según lo que la acción en sí ya dictaría).

## Autonomía por niveles, con límites explícitos en cada etapa

```
OBSERVAR -> PROPONER -> DELEGAR -> EJECUTAR -> VERIFICAR -> RECUPERAR -> REPORTAR -> MEJORAR
```

Respecto al ciclo de FASE2_I, esta fase añade el paso **MEJORAR** (alimentar el aprendizaje por evidencia de la sección E) y exige que CADA etapa tenga, de forma explícita y no implícita:

| Etapa | Límite | Permiso | Observabilidad | Rollback/criterio de parada |
|---|---|---|---|---|
| OBSERVAR | Ninguna acción sobre el mundo, solo lectura — sigue sujeto a REQ-070 (no leer fuera del proyecto sin control) | VERDE siempre que respete REQ-070 corregido | Se registra qué se observó y por qué | No aplica (no hay nada que revertir) |
| PROPONER | Solo genera una propuesta, no la ejecuta | VERDE | Se registra la propuesta y su origen (cadena de procedencia, sección H) | Descartar la propuesta si no se aprueba |
| DELEGAR | Elegir a quién se delega no ejecuta nada por sí mismo | VERDE si el destino es Qwen/local; ÁMBAR si es un proveedor externo con coste o exposición de datos | Se registra la decisión de delegación (una de las 10 del Router, sección E) | Revertir la delegación si el destino falla (fallback, sección E) |
| EJECUTAR | Sujeto íntegramente al nivel de permiso de la acción concreta (`permisos.py`, sin excepción por venir de un ciclo "autónomo") | VERDE/ÁMBAR/ROJO según la acción | Traza completa en el estado vivo (sección H), con timeout y máximo de pasos (Router, sección E) | Kill switch (sección G para el caso visual; terminación de proceso para lo local) |
| VERIFICAR | Obligatorio para ÁMBAR/ROJO; opcional pero recomendable para VERDE de alto volumen | VERDE (es una lectura/comparación) | Resultado de verificación registrado como evidencia (sección E) | Si la verificación falla, no se avanza a REPORTAR sin marcarlo como fallo |
| RECUPERAR | Reintentos acotados por el máximo de pasos del Router; nunca reintentos infinitos | VERDE si el reintento es igual o menor riesgo que el intento original; ÁMBAR si escala de proveedor sin revisión | Se registra cada intento de recuperación | Tope explícito: tras N recuperaciones fallidas, se detiene y se reporta como bloqueado, nunca sigue reintentando indefinidamente |
| REPORTAR | Informar a Damián | VERDE siempre | Es la propia observabilidad (sección H) | No aplica |
| MEJORAR | Actualizar la evidencia del Router (sección E) | VERDE (son datos, no acciones sobre el mundo) | El propio registro de evidencia es la traza | Revertir un ajuste de umbral es tan simple como editar el archivo legible (sección E) |

## El Caso E (discrepancia 3-vs-1), replanteado de nuevo, no resuelto por decreto

Sigue sin resolverse por decreto, tal como se prometió en FASE2_M y se reafirmó en FASE2_I. Con esta arquitectura más completa, la pregunta se puede formular con más precisión: **¿en qué etapa del ciclo de arriba pasa la autonomía de "requiere aprobación humana antes de EJECUTAR" a "puede EJECUTAR directamente si ya pasó por OBSERVAR-PROPONER-DELEGAR con evidencia suficiente"?** Los tres consultados en la Fase 1 (Qwen/Gemini/ChatGPT) proponían un vigilante que ya delega/ejecuta sin ese paso intermedio; el análisis propio de Claude proponía uno que solo avisa. Esta fase no zanja cuál es correcto — fija el umbral como un parámetro explícito y visible (una de las decisiones pendientes de Damián, ver índice), no como algo que el código decida por su cuenta a medida que gane "confianza" implícita.

## Qué NO hace esta fase

No cierra L1 ni REQ-070 (siguen pendientes de implementación, con prioridad máxima si se retoma el roadmap). No amplía ninguna capacidad real todavía — solo el diseño de cómo debería condicionarse cuando se implemente.
