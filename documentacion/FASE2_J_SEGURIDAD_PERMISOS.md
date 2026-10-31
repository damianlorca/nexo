# FASE 2 — J. Seguridad y permisos frente a más autonomía y control visual

**No se implementa ningún arreglo en esta sección — solo se integra en la arquitectura y se prioriza, tal como pidió Damián explícitamente.**

## Punto de partida: lo que ya se sabía y sigue sin arreglar

- **L1 (de la auditoría Fase 1):** `ejecutar_python` permite un bypass del sistema de permisos — código Python arbitrario ejecutado ahí no pasa por `nivel_de_comando()`. Sigue sin arreglarse. Sigue siendo la vulnerabilidad más seria conocida del sistema.
- **REQ-070 (de la auditoría Fase 1):** `nivel_de_ruta()` marca como VERDE (sin aprobación) leer cualquier ruta fuera del proyecto, salvo que el nombre de archivo sea literalmente `secretos.toml` — es decir, `leer()` puede leer cualquier otro archivo sensible del sistema (otro proyecto, documentos personales, configuración de otra app) sin pedir permiso, mientras no se llame `secretos.toml`. Sigue sin arreglarse.

Ambos hallazgos se reafirman sin cambios en esta revisión (ver FASE2_M) — no hay evidencia nueva que los invalide ni los agrave, solo el hecho de que la superficie de ataque potencial crece con cada capa nueva de autonomía que se añada sin cerrarlos antes.

## Por qué esto importa más ahora, no menos

`permisos.py` es hoy puramente textual/basado en rutas: no tiene ningún concepto de "aplicación", "ventana" o "acción visual". Cada pieza nueva de este diseño (control visual, multi-agente, Model Router con más proveedores, más autonomía) añade una superficie que ese modelo de permisos no cubre en absoluto:

- **Control visual (sección D):** hacer clic o escribir en una ventana no es "leer una ruta" ni "ejecutar un comando" — hoy no hay ningún nivel VERDE/ÁMBAR/ROJO definido para "esta aplicación se puede controlar sin preguntar" vs. "esta acción concreta dentro de esta aplicación necesita confirmación" (p. ej.: mover el ratón dentro del navegador de Gemini = bajo riesgo; escribir en un formulario bancario visible en pantalla = alto riesgo, aunque técnicamente sea "el mismo tipo de acción": clic + tecleo).
- **Multi-agente (Model Router, sección B):** enviar datos a un proveedor externo nuevo (o a uno ya usado pero con un contenido más sensible del habitual) no pasa hoy por ningún control de qué se le puede mandar a quién.
- **Ejecución local ampliada:** si Qwen empieza a proponer planes o comandos con más frecuencia (sección A/I), la superficie de "algo generado por una IA se ejecuta directamente" crece — y hoy nada distingue "un comando que Claude decidió ejecutar" de "un comando que una IA externa sugirió y Claude simplemente repitió", que es justo la distinción que preocupa a Damián (sección F, "origen de la orden").

En resumen: **ampliar autonomía sin cerrar primero L1 y REQ-070, y sin extender el modelo de permisos a acciones visuales/multi-agente, convierte un problema de autonomía en un problema de seguridad mayor** — cuantas más manos (Qwen, otro proveedor, una acción visual) puedan disparar una acción, más grave es que exista una vía sin control (`ejecutar_python`) o una lectura sin restricción (REQ-070).

## Cómo debería verse el modelo de permisos ampliado (diseño, no código)

- **Extender el concepto de "nivel" (VERDE/ÁMBAR/ROJO) a tres nuevas dimensiones de acción**, no solo comando y ruta: **aplicación/ventana** (lista blanca explícita de qué se puede controlar visualmente sin preguntar, todo lo demás ÁMBAR por defecto), **proveedor externo** (qué tipo de contenido se le puede mandar a cada proveedor sin confirmación — nunca secretos, nunca datos fuera de alcance como becas/UPV/Waver/Parity/explicalodamian), y **origen de la orden** (una acción sugerida por una IA externa y no revisada por Claude debería, por defecto, requerir un nivel de aprobación igual o mayor que si la hubiera decidido Claude directamente — nunca menor).
- **Cerrar L1 y REQ-070 antes de ampliar la autonomía de forma sustancial** — no es necesario cerrarlos antes de terminar esta revisión de arquitectura, pero sí antes de activar cualquier pieza nueva de autonomía (sección I) o control visual (sección D) en producción. Se marca como condición de entrada al roadmap, no como tarea aislada sin prioridad (ver FASE2_L).
- **Kill switch y lista blanca, explícitos desde el diseño de control visual**, no añadidos después — tal como ya proponía FASE2_D: por defecto, ninguna aplicación nueva es controlable visualmente hasta añadirse a una lista blanca, y existe un mecanismo para cortar cualquier automatización visual en curso sin depender de que el propio agente "decida" pararse.
- **Registro de acciones sensibles**, reutilizando la infraestructura ya existente de `nucleo/registro.py` (sección F) en vez de crear un sistema de auditoría nuevo — cada acción ÁMBAR/ROJA ejecutada queda trazada con su origen (Damián/turno/IA externa) para que la observabilidad (F) y una revisión posterior puedan reconstruir qué pasó y por qué.

## Recomendación

1. Priorizar el cierre de L1 (`ejecutar_python`) y REQ-070 **antes** de implementar cualquier pieza que amplíe la autonomía (sección I) o el control visual (sección D) — no antes de seguir documentando, pero sí antes de que cualquiera de esas piezas entre en producción.
2. Diseñar la extensión de `permisos.py` (aplicación/ventana, proveedor, origen de la orden) como parte del mismo trabajo que introduce el control visual — no como una fase separada posterior, para no repetir el patrón de "construir la función primero, el permiso después" que ya se dio con `ejecutar_python`.
3. No implementar nada de esto todavía — queda reflejado en el orden de FASE2_L como una de las primeras piezas de código a tocar, antes de D e I.
