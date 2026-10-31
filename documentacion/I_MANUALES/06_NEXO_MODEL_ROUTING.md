# I.6 NEXO_MODEL_ROUTING

Objetivo: maximizar resultado por unidad de cuota/tokens/tiempo. Claude Pro/Code es el recurso premium: se usa con criterio, no por defecto para todo.

## Estado real (verificado, ver `A_MATRIZ_REQUISITOS.md` REQ-010)

Existe la sugerencia (`nucleo/tareas.py::modelo_sugerido()`), no existe la decisión automática. Existe el adaptador común (`proveedores.py`), no existe quién decide a cuál llamar.

## Diseño propuesto (síntesis de Claude + Qwen + Gemini + ChatGPT, ver `G_SINTESIS_MULTI_IA.md` caso C — las 4 coincidieron en la estructura por niveles)

```
Tarea nueva
   │
   ▼
Nivel 0 — Qwen (local, gratis)
   si: mecánica, corta, sin razonamiento fuerte necesario
   │ si no cumple, siguiente nivel
   ▼
Nivel 1 — Gemini/ChatGPT (navegador, gratis, con rate-limit/cooldown)
   si: necesita razonar pero no tocar el PC ni gastar plan de Claude,
       y la latencia de decenas de segundos es aceptable
   │ si no cumple, siguiente nivel
   ▼
Nivel 2 — Claude (dispara Rutina, gasta plan)
   si: necesita herramientas del sistema, o es crítico,
       o los niveles anteriores fallaron
```

**Límite confirmado, no un diseño pendiente**: el Router puede decidir DISPARAR una Rutina de Claude, pero NO puede decidir el modelo/nivel de razonamiento dentro de ella — eso requiere que Damián lo cambie desde su propio Claude Code. Mitigación barata sugerida por Gemini: inyectar en el propio prompt una instrucción de concisión cuando se quiera ahorrar presupuesto, ya que no se puede cambiar el parámetro real.

## Registro de decisiones (propuesta de ChatGPT, razonable)

Guardar tarea → decisión → resultado → coste/latencia, para poder sustituir las reglas fijas por algo mejor informado más adelante, sin necesidad de aprendizaje automático real todavía.

## No implementar todavía

Este manual es diseño (Fase 5), no una tarea aprobada para implementar. Ver `J_ROADMAP_PRIORIZADO.md` P1.1 para el orden recomendado.
