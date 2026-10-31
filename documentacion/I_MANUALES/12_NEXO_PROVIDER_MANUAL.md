# I.12 NEXO_PROVIDER_MANUAL

Ver contrato completo en `proveedores.py` (T046, VERIFIED). Este manual es la referencia rápida de uso, no repite el código.

## Contrato común

Todo proveedor (`QwenProvider`, `GeminiProvider`, `ChatGPTProvider`, `ClaudeProvider`) cumple: `nombre: str`, `disponible() -> bool`, `estado() -> dict`, `enviar(tarea: str) -> Resultado`, `capacidades() -> dict`. `Resultado` tiene `estado` (`OK`/`NOT_AVAILABLE`/`BLOCKED`/`ERROR`), `texto`, `detalle`.

## Diferencias reales entre proveedores (no ocultarlas tras el contrato común)

| | Qwen | Gemini/ChatGPT | Claude |
|---|---|---|---|
| Coste | Cero, local | Cero, pero riesgo de bloqueo de cuenta si se abusa | Gasta el plan Claude Code |
| Latencia | 15-40s | Decenas de segundos, variable | Minutos (turno completo) |
| Razonamiento | Débil (obrero 7B) | Fuerte | Fuerte, con herramientas del PC |
| Devuelve la respuesta en la misma llamada | Sí | Sí (con matiz, ver abajo) | **No** — solo confirma que se pidió un turno |
| Herramientas del PC | No | No | Sí (únicas manos reales sobre el sistema) |

## Limitación descubierta en esta auditoría (Fase 3, 12/09): fiabilidad de `GeminiProvider`/`ChatGPTProvider` en conversaciones largas

Al encadenar varias preguntas seguidas en la MISMA pestaña/conversación (como se hizo en la consulta multi-IA de esta auditoría), la extracción de `navegador.py::preguntar()` puede capturar una respuesta ANTES de que termine de generarse del todo, y la pregunta siguiente "hereda" el resto de la respuesta anterior — un desajuste real, no solo lentitud. Con preguntas sueltas y espaciadas (como en `prueba_proveedores_vivo.py`, un "hola") no se manifiesta. **Recomendación operativa**: para preguntas largas/analíticas a Gemini/ChatGPT encadenadas, dejar al menos 45-60s de margen entre una y la siguiente, o (mejor, no implementado todavía) abrir una pestaña/conversación nueva por pregunta en vez de reutilizar la misma. Ver evidencia completa en `G_SINTESIS_MULTI_IA.md`.

## Cuándo usar cada uno (resumen de `F_ANALISIS_CLAUDE.md` caso C)

Mecánico y corto → Qwen. Necesita razonar pero no tocar el PC ni gastar plan → Gemini/ChatGPT. Necesita herramientas del sistema o el criterio completo de un turno → Claude (vía `/ahora`, sabiendo que la respuesta llega después, no en la misma llamada).
