# FASE 3 — B. Estudio ampliado de modelos locales y arquitectura multiagente local

## Parte 1 — Comparación ampliada de modelos locales (no elegir por fama)

Criterios pedidos por Damián: calidad de razonamiento, coding, seguimiento de instrucciones, contexto, velocidad, consumo RAM/VRAM, estabilidad, herramientas/function calling, capacidad de trabajo prolongado, capacidad de actuar como router, capacidad de verificar, capacidad de resumir, capacidad de trabajar con contexto local.

**Aviso de fiabilidad, honesto:** lo que sigue combina (a) el conocimiento propio de Claude con corte enero 2026, (b) la consulta selectiva a Qwen/Gemini/ChatGPT de la Fase 2 (modelos locales en general) y de esta Fase 3 (rol de orquestador/function-calling, ver sección de consulta), y (c) búsqueda web parcial. Ningún dato de esta tabla está medido en el hardware real de Damián — son estimaciones cualitativas para decidir QUÉ MEDIR primero, no una clasificación definitiva.

| Familia / tamaño | Razonamiento | Coding | Instrucciones | Contexto | Velocidad en este HW (CPU/RAM) | RAM aprox. (Q4) | Function calling | Rol sugerido |
|---|---|---|---|---|---|---|---|---|
| Qwen2.5:7b (ya en uso) | Medio | Medio | Bueno | 32-128K según variante | Rápido (medido: 15,9s) | ~5 GB | Básico | Worker/triaje — ya validado, no tocar sin motivo |
| Qwen3:14b (ya en uso) | Bueno, pero razona siempre (gasta tokens pensando) | Bueno | Bueno | 32-128K | Medio-lento por el razonamiento obligatorio | ~9 GB | Sí (nativo) | Criterio/planificación, no verificación barata |
| Qwen3:4b/8b (nuevo candidato) | Medio (8b) | Medio | Bueno | 32-128K | Rápido | 3-6 GB | Sí, con "thinking" desactivable | Triaje más fino, verificación barata (thinking off) |
| Gemma3:12b (nuevo candidato) | Medio-bueno | Medio | Bueno | 128K nativo | Medio | ~7-8 GB | Limitado/variable según build | Resumen de contexto largo |
| DeepSeek-R1-Distill-Qwen-14b (nuevo candidato) | Bueno, especializado en cadena de razonamiento | Medio-bueno | Medio (tiende a "pensar en voz alta" largo) | Heredado de Qwen | Lento (mucho texto de razonamiento) | ~9 GB | No es su punto fuerte | Auditor/verificador de razonamiento, NO orquestador de tiempo real |
| DeepSeek-R1-Distill-Qwen-32b (candidato de alto coste) | Bueno-alto | Bueno | Medio | Heredado | Lento en CPU (~20GB RAM) | ~20 GB | No es su punto fuerte | Planificación preliminar de fondo, nunca interactivo |
| Modelos especializados en function-calling (p.ej. variantes "tool-use" de Llama/Hermes) | Medio | Medio | Muy bueno en seguir un esquema de herramientas | Variable | Rápido-medio | 5-9 GB | Su especialidad | Candidato específico para el rol de ORQUESTADOR (ver Parte 2) — a validar con la consulta de esta fase |

**Lectura de la tabla, honesta sobre los límites:** ningún modelo local disponible hoy compite con Claude en razonamiento profundo multi-paso o en coding no trivial — esto no cambia con esta revisión, y es coherente con el punto 5 de Damián (Claude sigue siendo el recurso a reservar para donde su valor sea máximo). Lo que sí cambia es la ambición del "techo" de lo local: antes se pensaba en un solo modelo obrero + un modelo de criterio; ahora tiene sentido evaluar **tres roles de modelo, no dos**: orquestación (necesita sobre todo seguimiento de instrucciones fiable y function-calling, no necesariamente el razonamiento más profundo), ejecución mecánica (lo que ya cubre qwen2.5:7b) y verificación (lo que hoy no existe, candidatos: Qwen3:8b sin razonamiento o DeepSeek-R1-Distill para verificación de razonamiento).

**No se elige ganador en este documento.** Se marca como pendiente de medición real en el propio hardware de Damián (ver roadmap, sección N) antes de tocar `config.toml`.

## Parte 2 — ¿Tiene sentido una arquitectura multiagente local?

Damián pide evaluar explícitamente: complejidad, consumo, robustez, mantenimiento, latencia, facilidad de depuración, beneficio real — no asumir que "varios agentes" es mejor por defecto.

**El escenario multiagente (5 roles: orquestador, worker, researcher, verifier, watchdog) evaluado con honestidad:**

| Criterio | Multiagente (varios modelos/instancias con roles fijos) | Modelo único multi-rol (un modelo, distintos prompts según llamada) |
|---|---|---|
| Complejidad de construcción | Alta — cada rol es un proceso o llamada distinta, con su propio prompt, su propio manejo de errores, su propia cola de trabajo | Baja-media — un solo cliente Ollama, un solo punto de configuración, el "rol" es solo el prompt de sistema que se le pasa |
| Consumo de recursos | Mayor si varios modelos están cargados en memoria a la vez (Ollama puede descargar/cargar modelos bajo demanda, pero eso añade latencia de intercambio) | Menor — un modelo cargado, reutilizado para todo, sin intercambios de memoria |
| Robustez | Un fallo de un rol (p.ej. el verificador no responde) es más fácil de aislar y recuperar sin tirar todo el sistema | Un fallo del único modelo local tira toda la capacidad local a la vez — punto único de fallo |
| Mantenimiento | Más piezas que versionar y mantener sincronizadas (varios prompts, posiblemente varios modelos a actualizar por separado) | Un solo modelo que mantener y medir |
| Latencia | Mayor si hay intercambio de modelos en memoria (Ollama recarga si el modelo activo cambia); menor si cada rol tiene su propio proceso Ollama dedicado (pero eso sube el consumo de RAM simultáneo) | Menor y más predecible — no hay intercambio, solo cambia el prompt |
| Facilidad de depuración | Más difícil — hay que rastrear qué "agente" tomó qué decisión, con el riesgo señalado por Damián en observabilidad (sección H): confundir "qué hizo Nexo" con "qué le sugirió otro agente sin revisar" se vuelve MÁS probable cuantos más agentes hay hablando entre sí | Más fácil — una sola fuente de decisiones locales, más fácil de trazar |
| Beneficio real esperado | Alto SOLO si los roles realmente se benefician de modelos distintos (p. ej. un verificador que necesita razonamiento tipo DeepSeek-R1 y un worker que necesita velocidad tipo Qwen 4B) — el beneficio es de ESPECIALIZACIÓN DE MODELO, no de "tener varios agentes" en sí | Suficiente para la mayoría de los roles de bajo riesgo (triaje, resumen, verificación mecánica) donde el modelo importa menos que el prompt |

**Recomendación (ni construir 5 agentes, ni forzar 1 modelo para todo):** un **punto intermedio pragmático**, no los cinco roles completos de golpe ni un monolito:

1. **Orquestación = código determinista + UN modelo local con buen function-calling**, no un "agente" separado con su propio ciclo de vida. La orquestación (recibir la petición, clasificar, decidir a quién delegar) es, en su mayor parte, lógica que no necesita ser un LLM aparte — es exactamente el papel del Model Router (sección E), que puede ser código Python con un modelo local metido dentro para la parte de clasificación en lenguaje natural, no un "agente orquestador" con personalidad propia.
2. **Ejecución = el mismo Qwen2.5:7b de hoy**, sin cambios — ya validado.
3. **Verificación = un modelo o modo distinto** (candidato: Qwen3:8b con razonamiento desactivado, o una llamada separada del mismo Qwen3:14b con un prompt de verificación) — esto SÍ justifica un modelo/config distinto, porque el objetivo (barato, rápido, sin "pensar de más") es opuesto al del worker.
4. **Vigilancia de bucles = un proceso ligero de Python, no un LLM** — detectar "misma acción N veces seguidas" no necesita inteligencia, necesita un contador. Meter un LLM aquí sería exactamente el tipo de complejidad innecesaria que Damián pide evitar.
5. **Researcher (preparar contexto) = función del worker existente**, no un rol nuevo — es el mismo tipo de tarea que ya hace Qwen al resumir/triar, con un prompt distinto.

En resumen: **la arquitectura multiagente completa no se justifica todavía con la evidencia disponible** — el beneficio real viene de tener 2-3 configuraciones de modelo especializadas (worker, verificador, y opcionalmente un planificador de fondo tipo DeepSeek-R1 para tareas no interactivas), coordinadas por código determinista (el Model Router), no por un "agente orquestador" que sea él mismo un LLM con su propio ciclo de decisión. Si con el tiempo el volumen de trabajo local lo justifica, migrar de "código determinista + modelos especializados" a "agentes con estado propio" es un paso posterior, no el punto de partida — se revisita cuando haya evidencia real de que el código determinista se queda corto (ver sección E, aprendizaje por evidencia).

**Confirmación externa (ver FASE3_L_CONSULTA_MULTIIA.md):** esta misma recomendación se planteó ANTES de consultar a otras IAs, y la consulta selectiva de esta fase la confirma 2 contra 1 — Gemini y ChatGPT, de forma independiente, recomiendan exactamente "código determinista + un modelo local reutilizado con distintos prompts", y ambos señalan de forma espontánea el mismo framework concreto para la parte de gestión de estado/flujo: **LangGraph** (grafos de estado con checkpoints y recuperación de errores, con soporte nativo para Ollama) — se incorpora como candidato concreto a evaluar cuando se implemente el Model Router (sección E), sin comprometerse todavía a adoptarlo sin probarlo. Solo Qwen local (con el sesgo ya señalado de recomendarse a sí mismo un escenario donde tendría más protagonismo) propuso lo contrario.
