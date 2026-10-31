# C. Resultados de Qwen — 5 casos especiales (Fase 3 acotada)

Consulta ejecutada el 12/09/2026 vía `proveedores.QwenProvider` (modelo `qwen2.5:7b`, local, gratis). Las 5 respuestas se capturaron limpiamente y en el orden correcto (Qwen no tiene el problema de desalineación que sí afectó a Gemini/ChatGPT, ver `G_SINTESIS_MULTI_IA.md`).

## A. Despertar de Claude bajo demanda
> No hay forma oficial documentada de reducir la latencia o permitir varios turnos de Claude Code en paralelo sin riesgo de pisado de memoria. La solución actual es la más cercana a la demanda, pero no cumple con la necesidad de respuesta rápida o paralelismo. Se recomienda evaluar alternativas como optimizar el flujo de trabajo existente o buscar soluciones de terceros no documentadas por Anthropic, siempre respetando las ToS.

**Lectura**: coincide con Claude — no hay atajo oficial, y advierte (correctamente) contra buscar soluciones no documentadas que violen las restricciones ya fijadas.

## B. Detección de límites/disponibilidad de Claude
> Se podría aproximar la disponibilidad de cuota a través de análisis de patrones en los códigos de error y cabeceras de las respuestas del endpoint de disparo de rutinas. Se podría implementar un script que envíe solicitudes de rutinas de prueba con intervalos regulares y registrar los códigos de error y cabeceras de respuesta [...] un código de error 429 podría indicar que se está cerca del límite. Sin embargo, esto es una aproximación y podría no ser preciso en todos los casos.

**Lectura**: propone algo más activo (disparar rutinas de prueba a intervalos) que Claude y las otras dos IAs no recomiendan — ver discrepancia en `G_SINTESIS_MULTI_IA.md` (gastar plan para medir cuánto plan queda es contraproducente).

## C. Model Router
> 1. Categorización de tareas (dificultad/importancia). 2. Priorización automática. 3. Decisiones iniciales: tarea simple y barata → Qwen; barata pero puede requerir más tiempo → Gemini/ChatGPT; alta dificultad/importancia → Claude. 4. Gestión de Claude: modelo básico para tareas simples, modelo de razonamiento avanzado para las complejas "siempre con la aprobación de Damián". 5. Monitoreo de recursos. 6. Feedback y ajustes.

**Lectura**: coincide en la estructura por niveles con Gemini y ChatGPT. Es la única de las tres que menciona explícitamente "siempre con la aprobación de Damián" para tocar el modelo de Claude — coincide con el bloqueo de plataforma ya confirmado por esta auditoría.

## D. Comunicación entre IAs / protocolo
> Archivos JSON como cola, con candado. Estructura de mensaje: `sender, receiver, task_id, message_type, payload, context, priority, timestamp, status, result, error` [exactamente los campos pedidos]. Proceso: Qwen resume → Gemini investiga → ChatGPT redacta → Claude revisa, cada uno leyendo/escribiendo su archivo. Candados para concurrencia. Archivo de registro para monitorear.

**Lectura**: coincide punto por punto con la propuesta de Claude en `F_ANALISIS_CLAUDE.md` (mismo patrón que `canal/buzon.py`) y reproduce literalmente los campos de la especificación maestra.

## E. Autonomía completa
> Actualizar `siguiente_turno` en `estado.json` con subtareas y sus estados tras cada turno. Nueva función en `nucleo/tareas.py` que cargue pendientes de `siguiente_turno` y las asigne a Claude. Modificar `canal/vigilante.py` para que, además de relanzar el bot, compruebe si hay tareas pendientes en `siguiente_turno`, las asigne, monitoree su estado, pida autorización humana si hace falta, y registre el resultado.

**Lectura**: coincide con la propuesta de Claude de usar `canal/vigilante.py` como base (ya vive siempre en el PC), pero va más lejos: Qwen propone que el vigilante ASIGNE y EJECUTE tareas, mientras que la recomendación de Claude es más conservadora (que el vigilante solo AVISE por Telegram, no actúe solo). Discrepancia real, ver síntesis.
