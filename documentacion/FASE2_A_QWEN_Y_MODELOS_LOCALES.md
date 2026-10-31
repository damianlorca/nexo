# FASE 2 — A. Qwen local: papel actual, papel recomendado, y modelos alternativos

## Evidencia real (no supuesta): qué hace Qwen HOY

Grep sobre todo el proyecto (`Select-String -Pattern 'qwen\.'` excluyendo `.venv`) confirma que las únicas llamadas vivas a `extremidades/qwen.py` están en:

- **`extremidades/triaje.py`** (`triar()`): dos clasificaciones (categoría: tarea/dato/respuesta/charla; urgencia: urgente/no urgente) + un resumen de una frase, por cada mensaje suelto de Telegram. Es el ÚNICO consumidor de trabajo real.
- **`canal/bot.py`** (`_texto_triaje()`): llama a `triaje.triar()` para la lectura rápida que se manda como segundo mensaje cuando llega un mensaje suelto. Es el mismo trabajo que el punto anterior, vía el bot.
- **`extremidades/base.py`** (`_sonda_qwen()`): solo `qwen.disponible()`, un ping de salud para el inventario. No le pide trabajo.
- **`proveedores.py`** (`QwenProvider`, T046): envoltorio del mismo `pedir()`, usado hasta ahora solo en la demo en vivo (`demo_en_vivo.py`) y en la prueba (`prueba_proveedores_vivo.py`) — todavía no conectado a nada que lo llame en producción.

Eso es todo. Qwen **no** interviene hoy en: verificar resultados de otros agentes, planificar antes de llamar a Claude, resumir el contexto que se le manda a Claude, detectar bucles, vigilar procesos, ni actuar como primer filtro de nada salvo los mensajes sueltos de Telegram. La sospecha de Damián de que está infrautilizado **es correcta y se confirma con evidencia, no con impresión**.

## Dónde se está llamando a Claude cuando Qwen podría bastar

Revisando el flujo completo del sistema, hay al menos tres puntos donde hoy se paga un turno de Claude (interactivo o de rutina) para trabajo que es mecánico y que Qwen ya demostró poder hacer (o casi):

1. **Leer y resumir `canal/entrada/` al arrancar un turno.** El prompt de la rutina de noche ya usa `memoria/triaje.json` cuando existe (medida T032), pero solo cubre mensajes sueltos — no aplica el mismo filtro a respuestas a preguntas abiertas ni a los archivos `.json.enviado` que hay que cruzar para saber qué sigue pendiente. Ahí Claude sigue leyendo y cruzando datos a mano que un script determinista (ni siquiera Qwen: Python puro) podría dejar ya resuelto antes de que Claude entre.
2. **Comprobar que un cambio de código no ha roto nada obvio antes de que Claude lo revise.** Hoy, tras cualquier `escribir()` de un módulo, la verificación ("ejecútalo y compruébalo") la hace el propio turno de Claude. Una primera pasada de sintaxis/import/ejecución de las pruebas existentes es exactamente el tipo de tarea mecánica que Qwen (o directamente un script) puede hacer antes de gastar contexto de Claude en interpretar un traceback.
3. **Resumir el estado de una tarea larga (`memoria/tareas.json`, notas largas) antes de decidir qué hacer con ella.** Las notas de T037/T039 han crecido mucho; Claude las relee enteras cada vez que las toca. Un resumen de Qwen de "qué se sabe ya, qué falta, qué se descartó y por qué" ahorraría releer 400+ palabras de historial cada vez.

## Qué debería hacer Qwen de forma permanente vs. solo cuando haga falta

**Permanente (ya lo hace o cuesta poco añadir):**
- Triaje de mensajes sueltos (ya existe).
- Sonda de salud de las extremidades (ya existe, dentro de `inventario()`).
- **Nuevo candidato de bajo riesgo:** un "vigilante" ligero que, cada pocos minutos mientras un turno de Claude está trabajando, lee `registros/trazas.jsonl` y detecta patrones simples (misma acción repetida N veces seguidas, un proceso lanzado hace más de X minutos sin traza de fin) y dejaría una nota en `memoria/triaje.json` o similar — no para actuar, solo para que la capa de observabilidad (sección F) tenga una señal barata de "esto puede ser un bucle" sin que Claude tenga que darse cuenta solo releyendo su propio historial.

**Solo cuando haga falta (bajo demanda, no como daemon):**
- Resumir notas largas de una tarea antes de que Claude decida sobre ella.
- Verificación mecánica de una salida (¿el JSON es válido? ¿el archivo tiene el tamaño esperado? ¿el código importa sin excepción?) antes de que Claude interprete un resultado más caro de leer.
- Planificación preliminar: dado un encargo en lenguaje natural, proponer (nunca decidir) una lista de pasos o qué proveedor tocaría, para que el Model Router (sección B) tenga un borrador barato que Claude solo tiene que confirmar o corregir, en vez de generarlo desde cero.
- Primer filtro de **peticiones rutinarias** (dar de alta una tarea, marcar una hecha, formatear una respuesta) — esto ya lo hacen los comandos del bot sin pasar ni por Qwen ni por Claude, que es el nivel correcto; Qwen entra solo cuando hace falta lenguaje natural de por medio.

**Qué NO debe hacer Qwen (límite explícito, coherente con lo ya decidido en T030/triaje.py):** decidir, dar de alta tareas por su cuenta, ni aprobar ninguna acción ambar/roja del sistema de permisos. Sigue siendo un obrero que informa y propone, nunca un decisor — eso no cambia con más autonomía de sistema, cambia el volumen y variedad de lo que se le pide, no su nivel de autoridad.

## El hardware real cambia la conversación sobre "qué modelo local"

Medido hoy mismo en el equipo (`Get-CimInstance`), no en abstracto:

- **CPU:** AMD Ryzen AI 9 HX 370 — 12 núcleos, 24 hilos. Es una CPU de portátil de gama alta 2025/2026 (familia "Strix Point"), con NPU dedicada que Ollama/DirectML hoy no aprovecha (no hay soporte de runtime de inferencia LLM sobre esa NPU en el ecosistema Ollama a fecha de esta revisión).
- **RAM:** 33.413.771.264 bytes ≈ **31 GB**.
- **GPU:** Radeon 890M integrada, memoria dedicada reportada 512 MB, pero con acceso a memoria compartida — ya medido en `extremidades/imagen.py` que DirectML solo deja usar de forma fiable unos 3 GB de eso para modelos de imagen.
- **Disco libre en C:** ≈ 599 GB.

Esto es un hardware **notablemente más capaz de lo que "poca VRAM" sugiere por sí solo**. La limitación real no es la memoria total (31 GB es holgado) sino el **ancho de banda y cómputo de la iGPU**, que hace que un modelo grande corriendo ahí sea lento. Pero con 31 GB de RAM del sistema y 24 hilos de CPU, correr un modelo de 14B en cuantización q4 (~8-9 GB) o incluso de 32B en q4 (~18-20 GB) **en CPU**, sin depender de la GPU en absoluto, es perfectamente viable en términos de memoria — el coste es tiempo por token, no si cabe o no. Dado que a Damián no le importa que el PC trabaje muchas horas para tareas que no son interactivas (vigilancia, verificación, resúmenes en segundo plano), esto abre una opción que la configuración actual (`config.toml`) no contempla: **modelos más grandes en CPU para tareas no urgentes, modelos pequeños en la iGPU para tareas que si necesitan respuesta rápida.**

## ¿Sigue Qwen siendo la opción correcta?

Con la información disponible hasta el corte de conocimiento de Claude (enero 2026) más lo verificado hoy:

- **Para triaje/clasificación rápida (obrero):** qwen2.5:7b ya está medido y funciona bien en este hardware (15,9s, 0 respuestas vacías). No hay evidencia concreta de que cambiarlo aporte algo — es una tarea de bajo margen de mejora (clasificar en 2-4 categorías no exige un modelo mejor, exige uno que responda rápido y sin alucinar la categoría, que es justo lo que ya está medido).
- **Para juicio/verificación (criterio):** qwen3:14b es razonable, pero el hallazgo de que "razona antes de responder y ese razonamiento gasta el mismo presupuesto de tokens" (documentado en la cabecera de `qwen.py`) es una fricción real para un papel de "vigilante que verifica en segundo plano constantemente" — cada verificación paga el coste de un razonamiento completo aunque la pregunta sea simple ("¿este JSON es válido?"). Esto es exactamente donde vale la pena comparar con un modelo NO razonador de tamaño similar (ej. una variante de Llama 3.x o Gemma de 8-14B sin modo "thinking"), que podría verificar más barato y más rápido para las tareas de vigilancia de bajo criterio, dejando qwen3:14b (o algo mayor, dado que cabe en RAM) solo para cuando el juicio de verdad lo requiere.
- **Arquitectura de varios modelos especializados:** tiene sentido dado el hardware. Una combinación razonable a explorar (no implementar todavía): (1) un modelo pequeño de 3-4B sin razonamiento en la iGPU para triaje instantáneo (lo que ya hay, sin cambios); (2) un modelo mediano de 8-14B sin razonamiento en CPU para verificación mecánica rápida (JSON válido, código importa, formato correcto) sin pagar el coste del "pensar"; (3) qwen3:14b o un modelo de hasta 32B en CPU, invocado solo bajo demanda, para resúmenes largos y planificación preliminar donde sí conviene que piense.

Esta sección se complementa con las respuestas de la consulta selectiva a Qwen/Gemini/ChatGPT sobre alternativas concretas de 2026 (ver FASE2_K_CONSULTA_MULTI_IA.md) — la comparación de nombres de modelos exactos de 2026 se apoya en esa consulta y en búsqueda web, no solo en el conocimiento propio de Claude, que tiene fecha de corte de enero 2026 y puede no conocer lanzamientos posteriores.

## Contraste con la consulta multi-IA (Qwen/Gemini/ChatGPT, ver sección K para el detalle completo)

Las tres IAs coinciden en un punto que corrige la comparación anterior: **la alternativa real a Qwen en 2026 no es "salir de la familia Qwen", es actualizar DENTRO de la familia Qwen (Qwen3) y sumar UN modelo de otra familia para razonamiento/verificación**, no sustituir el stack entero:

- **Qwen (local) recomendó salir de familia** (Phi-3/Llama-3/Mistral/Gemma-2) — pero esto pesa poco: es la respuesta de un modelo con conocimiento propio más antiguo/limitado sobre sí mismo y sobre lanzamientos recientes, exactamente el sesgo que se anticipó al diseñar la consulta. Se registra por transparencia, no se sigue.
- **Gemini y ChatGPT coinciden, con más matiz y mejor anclado en lanzamientos reales:** mantener Qwen como base (Qwen3, no la generación anterior), en tamaños **4B/8B** para triaje/verificación ligera y **14B** para juicio/planificación; añadir **Gemma 3 12B** como alternativa concreta para resumir contexto largo (128K nativos); y para el papel de "verificador que razona paso a paso" ambas IAs (sobre todo Gemini) señalan la familia **DeepSeek-R1-Distill** (variantes Qwen-14B o Llama-8B) como la pieza que hoy falta en el stack — un modelo pensado específicamente para razonamiento tipo cadena-de-pasos, útil para auditar la salida de otro agente, no solo para generarla.
- **Ninguna de las tres propone abandonar Ollama** ni cambiar de motor de inferencia local — el consenso es sobre qué pesos cargar, no sobre la infraestructura.

Esto **corrige y concreta** el punto 2 de la recomendación de más abajo: en vez de "un modelo mediano sin razonamiento" en abstracto, los candidatos concretos a medir son **Qwen3:8b (thinking desactivado) o Gemma3:12b** para verificación barata, y **DeepSeek-R1-Distill-Qwen-14b** como candidato específico para el papel de auditor/verificador de criterio (sección F, observabilidad) — todos caben cómodamente en los 31 GB de RAM disponibles en CPU. Sigue sin haber evidencia de banco de pruebas real en este hardware: es una lista de candidatos a medir, no una decisión.

## Recomendación (no implementar todavía)

1. Mantener qwen2.5:7b como obrero de triaje — no cambiar sin evidencia concreta de un problema.
2. Medir (con datos reales en este hardware, no solo teoría) **Qwen3:8b sin razonamiento** o **Gemma3:12b** como candidatos a "verificador barato", y **DeepSeek-R1-Distill-Qwen-14b** como candidato a "auditor de razonamiento" — ambos roles nuevos, dentro del Model Router (sección B) y de la observabilidad (sección F).
3. Aprovechar la RAM disponible para permitir explícitamente en `config.toml` un tercer nivel de modelo local ("verificador", además de "obrero" y "criterio"), en vez de forzar todo el trabajo no urgente sobre qwen3:14b.
4. No mover nada a la NPU todavía: no hay ruta de Ollama/DirectML confirmada para aprovecharla a fecha de esta revisión: sería una vía de investigación aparte, de bajo valor inmediato.
