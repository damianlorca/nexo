# FASE 4 — H. PC Control Layer como capa transversal, y la pregunta general sobre Playwright

## La capa, formalizada como parte de la capa C (Tools)

```
PC CONTROL LAYER (dentro de la capa C: Tools/Ejecucion)
  1. API/CLI
  2. DOM/Playwright
  3. UI Automation/accesibilidad
  4. automatizacion de escritorio
  5. vision
  6. coordenadas
```

Sin cambios respecto a la jerarquía híbrida ya fijada en FASE2_D/FASE3_G — lo que esta fase aporta es encajarla explícitamente como UNA capa de tools compartida, no una funcionalidad aislada de "control visual". Esto ya se venía apuntando en FASE3_G (adelantar los niveles 1-2), pero ahora queda dicho con la terminología de capas: la PC Control Layer es la tool que resuelve simultáneamente varios casos de uso ya identificados por separado en fases anteriores — gestión de chats de Gemini/ChatGPT (FASE3_F, nivel 2 de esta jerarquía), observar el estado/cuota de un proveedor en su interfaz (nivel 3), y, más adelante, aplicaciones Windows sin API (niveles 3-5).

**Regla de uso, reafirmada:** usar siempre el método más estructurado disponible, caer al siguiente solo cuando el anterior no sirve — nunca "visión para todo" ni "coordenadas por defecto".

## La pregunta general sobre Playwright, separada de T038

Damián tiene razón en distinguir dos preguntas que las fases anteriores mezclaban parcialmente:

1. **¿Se automatiza claude.ai con Playwright como sustituto de una integración oficial, para sortear T039?** — Esto es T038, y sigue cerrada. No se reabre. El motivo no cambia: no es la tecnología (Playwright) lo que está mal, es usarla para suplantar la interfaz de producción de Anthropic en la propia sesión de Damián como atajo frente a una limitación de producto.
2. **¿Es Playwright, en general, la tecnología correcta para el nivel 2 (DOM) de la PC Control Layer, cuando corresponda y sea compatible con las condiciones de cada sitio?** — Esta pregunta sigue abierta y NO tiene una respuesta única para todos los casos. Ya se usa hoy, con éxito medido, para Gemini/ChatGPT (nivel 2, sesión propia de Damián, sin objeción previa salvo el aviso de ToS de OpenAI ya trasladado en FASE3_F/L). Para una aplicación de Windows sin interfaz web, Playwright no aplica en absoluto — ahí entran los niveles 3 (UI Automation) en adelante.

**Conclusión: Playwright no está "prohibido" ni "adoptado" como principio general — es una herramienta más dentro de la PC Control Layer, correcta donde el objetivo es una página web de un proveedor que lo permite (Gemini/ChatGPT), incorrecta donde el objetivo es sustituir una integración oficial existente (claude.ai) o donde el objetivo no es una página web en absoluto (una app de Windows).** Esto no es una guerra "Routines vs. Playwright" — son herramientas para problemas distintos: Routines es cómo se dispara Claude; Playwright (nivel 2) es cómo se interactúa con una web cuando no hay mejor opción estructurada disponible para esa web en concreto.

## Qué resuelve esta capa, listado de forma completa (tal como pide Damián)

Gemini, ChatGPT, Claude (solo en el sentido de "observar su estado/cuota en pantalla" — nunca de sustituir su integración oficial, eso sigue vetado por T038), otras webs, aplicaciones Windows, selección de chats, cambio de ventanas, comprobación visual de resultados, recuperación de UI cuando una interfaz cambia. Es, efectivamente, una sola capa de infraestructura al servicio de varios casos de uso — no seis features distintas.

## Los cinco calificativos, reafirmados sin cambios

Técnicamente posible / fiable / mantenible / seguro / permitido por las condiciones del servicio correspondiente — se evalúan SIEMPRE por caso concreto (proveedor + nivel de la jerarquía), nunca como una propiedad de "Playwright" o de "control visual" en abstracto. Esto ya estaba en FASE2_D/FASE3_G; se reafirma explícitamente aquí porque Damián lo pide de nuevo con énfasis.

## Sin implementación en esta fase

La secuenciación (niveles 1-2 adelantados, 4-5 al final, tras seguridad) se mantiene sin cambios respecto a FASE3_N — ver el roadmap consolidado en el índice de esta fase.
