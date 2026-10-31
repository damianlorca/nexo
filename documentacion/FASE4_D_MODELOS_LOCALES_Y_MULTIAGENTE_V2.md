# FASE 4 — D. Arquitectura local: 4 opciones comparadas, sin dogma de framework

## No repetir la Fase 3, sino corregir su foco

FASE3_B ya comparó modelos concretos (Qwen3:4b/8b/14b, Gemma3:12b, DeepSeek-R1-Distill) y evaluó "multiagente sí/no" con una tabla de criterios — ese contenido no se repite aquí, se da por válido. Lo que pide Damián ahora es distinto: comparar explícitamente **4 opciones de arquitectura**, no 2, y hacerlo sin comprometerse a un framework todavía (ni siquiera LangGraph, pese a que dos de tres IAs consultadas lo recomendaron de forma espontánea) — la arquitectura manda, el framework es secundario.

## Las 4 opciones

**Opción A — Un solo modelo local con distintos roles.** Un único modelo (p. ej. Qwen3:14b) recibe distintos prompts de sistema según la llamada (triaje, verificación, resumen). Es lo más simple de construir y depurar. Limitación real: un modelo de 14B no es igual de bueno en las 3 tareas — usar el mismo modelo para triaje rápido y para verificación de razonamiento es forzar un compromiso de tamaño/velocidad en ambos sentidos.

**Opción B — Varios agentes locales especializados.** Modelos/instancias distintos por rol (uno pequeño para triaje, otro para verificar, otro para resumir), cada uno con su propio ciclo de vida. Máxima especialización, máximo consumo de RAM si están todos cargados a la vez, máxima complejidad de coordinación y depuración (ya evaluado en detalle en FASE3_B, tabla de criterios).

**Opción C — Un modelo local + orquestación determinista por código.** La recomendación ya adoptada en FASE3_B: el "rol" lo decide un prompt distinto sobre el mismo modelo (como en A), pero la DECISIÓN de a qué rol llamar, en qué orden, con qué reintentos, la lleva código Python explícito — no otro LLM. Es, en esencia, A + una capa de control explícita encima.

**Opción D — Arquitectura híbrida.** Combinación deliberada: modelo único para la mayoría de roles (triaje, resumen) + un modelo DISTINTO solo donde la especialización aporta un beneficio medible (p. ej. DeepSeek-R1-Distill solo para verificación de razonamiento, cargado bajo demanda, no residente) — todo coordinado por el mismo código determinista de la Opción C.

## Comparación con los criterios pedidos

| Criterio | A (modelo único) | B (multiagente) | C (único + código) | D (híbrida) |
|---|---|---|---|---|
| Complejidad | Baja | Alta | Baja-media | Media |
| Coste (RAM/tiempo de carga) | Bajo | Alto si residentes; medio si bajo demanda | Bajo | Medio (un modelo extra solo bajo demanda) |
| Consumo sostenido (horas) | Bajo, predecible | Alto y variable | Bajo, predecible | Medio, predecible por diseño |
| Robustez | Punto único de fallo | Un rol cae sin tirar el resto, pero más piezas que pueden fallar | Punto único de fallo del modelo, pero el código de control es robusto y fácil de testear aparte | Fallo aislado del modelo especializado no tira el resto |
| Mantenimiento | Mínimo | Alto (varios modelos/prompts que mantener sincronizados) | Bajo | Medio (dos configuraciones de modelo, un solo código de control) |
| Paralelización | Limitada (un modelo, llamadas en cola) | Alta en teoría (procesos separados), cara en RAM | Limitada, igual que A | Alta donde importa (el modelo especializado puede correr en paralelo al principal si hay RAM) |
| Depuración | Fácil | Difícil (rastrear qué agente decidió qué) | Fácil (el código de control es determinista y trazable) | Fácil-media (el código sigue siendo determinista; el modelo extra es una llamada más a rastrear) |
| Beneficio real esperado | Suficiente para el volumen actual de trabajo local | Alto solo si la especialización de modelo aporta de verdad (ver D) | Igual que A, más el control explícito que falta hoy | El mayor beneficio real: especialización SOLO donde se ha medido que importa |

## Recomendación, sin adoptar framework

**Opción D (híbrida) es la que mejor cumple "calidad + autonomía + fiabilidad + ahorro de recursos externos" sin caer en la complejidad de B.** No es una elección nueva respecto a la Fase 3 — es la versión más precisa de lo que FASE3_B ya apuntaba ("2-3 configuraciones de modelo especializadas, coordinadas por código determinista") ahora nombrada como una opción explícita comparable con las otras tres, tal como pide Damián.

**Sobre el framework (LangGraph u otro):** no se adopta nada en esta fase. La arquitectura (Opción D) es independiente de si el "código determinista" se escribe a mano, con una máquina de estados simple, o con LangGraph — esa decisión se toma cuando se implemente el Router (FASE3_E) y se pueda medir si la complejidad de un framework aporta algo (checkpoints, recuperación) que el código propio no daría con menos esfuerzo, no antes. La consulta de la Fase 3 dio evidencia de que LangGraph es una opción seria y validada externamente (2 de 3 IAs, de forma espontánea) — se mantiene como candidato documentado, no como decisión.

## Estudio ampliado de modelos, más allá de Qwen (sin elegir todavía)

Reafirmando FASE3_B con el marco de las 4 opciones: para la Opción D, los candidatos concretos a medir son los ya identificados (Qwen3:4b/8b para triaje/verificación ligera, Qwen3:14b o Gemma3:12b como modelo principal de rol general, DeepSeek-R1-Distill-Qwen-14b como el "modelo especializado bajo demanda" de la Opción D para verificación de razonamiento). No se elige ganador — se marca como el primer experimento real a hacer cuando se implemente el Model Router (ver roadmap).
