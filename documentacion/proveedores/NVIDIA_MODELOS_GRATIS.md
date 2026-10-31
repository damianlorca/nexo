# NVIDIA build.nvidia.com: modelos con "Free Endpoint" (lista de Damián, 27/09/2026)

Fuente: catálogo de build.nvidia.com copiado por Damián el 27/09/2026. Clave en `secretos.toml [nvidia] api_key`.
Endpoint compatible con OpenAI: `https://integrate.api.nvidia.com/v1`. Prueba real del 27/09: `/models` → 82 modelos;
gpt-oss-20b responde en 11–50 s, a veces más de 120 s.
**Regla de Damián: solo modelos gratuitos.** El estado "Free Endpoint" y los ids exactos se comprueban con `/models` antes de usarlos.

| Modelo | Autor | Tipo | Posible uso en NEXO |
|---|---|---|---|
| nemotron-3-super-120b-a12b | NVIDIA | MoE, contexto de 1M, agentes, código y planificación | Revisor/autor de otra familia; tareas con mucho contexto (listas de tareas, código) |
| nemotron-3-ultra-550b-a55b | NVIDIA | MoE, contexto de 1M, agentes | Revisor fuerte de otra familia (latencia por medir) |
| nemotron-3.5-lightning-30b-a3b | NVIDIA | MoE rápido, agentes | Revisor rápido (candidato contra la latencia de gpt-oss) |
| gpt-oss-20b | OpenAI | MoE de razonamiento, solo texto | Revisor (conectado en T227; latencia variable) |
| nemotron-3-nano-omni-30b-a3b-reasoning | NVIDIA | Omnimodal: imagen, vídeo, voz y texto | Visión/voz (T027 pantalla, T159 voz) |
| gemma-4-31b-it | Google | Denso 31B, código y agentes | Autor/revisor de familia Google sin gastar Gemini |
| diffusiongemma-26b-a4b-it | Google | LLM de difusión, muy rápido | Tareas rápidas (clasificar, resumir) |
| llama-3.2-90b-vision-instruct / 11b-vision | Meta | Visión y lenguaje | Leer capturas de pantalla (T027) |
| muse-glimmer-30b | Meta | Multimodal con razonamiento y herramientas | **Posible "Muse" de T201**: comprobar |
| mistral-nemotron | Mistral | Agentes, código y llamadas a funciones | Revisor de otra familia |
| deepseek-v4.1-flash | DeepSeek | MoE 552B (8B activos), multimodal | Autor/revisor de otra familia |
| glm-5-3 / glm-5-3-flash | Z.ai | MoE grande, razonamiento y herramientas | Revisor de otra familia |
| kimi-k3 | Moonshot | MoE enorme, código de largo recorrido y agentes | Revisor de código difícil |
| laguna-xs-2.1 | Poolside | MoE 33B, código y terminal | Tareas de código mecánico (T184) |
| nemotron-3-embed-1b | NVIDIA | Embeddings | **RAG y memoria (T181, T144)** |
| riva-translate-4b-instruct v1_1 / v2 | NVIDIA | Traducción (12 y 37 idiomas) | Traducir fuentes |
| magpie-tts-zeroshot, nemotron-voicechat, Studio Voice, Background Noise Removal | NVIDIA | Voz: TTS, chat de voz y limpieza de audio | Voz de NEXO (T025, T159) |
| nemotron-3.5-content-safety, llama-guard-4-12b, llama-3.1-nemotron-safety-guard-8b-v3 | NVIDIA/Meta | Clasificadores de seguridad | Filtro anti-inyección de prompts (T158) |
| synthetic-video-detector, Active Speaker Detection | NVIDIA | Vídeo | Proyecto de vídeos (T007/T129), baja prioridad |
| cosmos3-nano, cosmos3-nano-reasoner, cosmos-transfer2.5-2b | NVIDIA | Mundo físico, vídeo | Sin uso claro |
| paligemma | Google | Visión | Sin uso claro (hay mejores) |
| Kumo Relational | NVIDIA | Predicción sobre tablas | Sin uso claro |
| ising-calibration-*, streampetr, bevformer, sparsedrive | NVIDIA | Cuántica y conducción autónoma | No aplica |

## Evaluación T261 (28/09/2026, sesión nocturna sin Damián)

`/models` (82 modelos, misma cuenta que el 27/09) confirma que **`openai/gpt-oss-120b` ya NO aparece**
en el catálogo hoy (solo `openai/gpt-oss-20b`); la lista blanca lo conserva por si vuelve, pero
`secretos.toml [nvidia] modelos` no debería depender solo de él.

Mini-banco (script `herramientas_nube/_banco_nvidia_2809.py`, llamadas HTTP directas para no tocar
`memoria/enfriamiento.json` del proveedor real): 3 casos por rol — **revisor** (formato
FALLOS/OMISIONES/GRAVEDAD/VEREDICTO de `roles/revisor_borrador.md`, con un borrador con error de hecho,
uno limpio y uno con omisión), **autor de investigación** (informe corto de 150 palabras, 3 temas) y
**clasificador rápido** (urgencia, categoría de tarea, detección de inyección de prompt, con la
respuesta esperada conocida). `max_tokens=500`, `timeout=45s` por llamada.

| Modelo | Familia | Revisor (3) | Autor (3) | Clasificador (3, aciertos) | Latencia tipica | Veredicto |
|---|---|---|---|---|---|---|
| nemotron-3-super-120b-a12b | NVIDIA | 3/3 OK | 3/3 OK | 3/3 OK, 3/3 aciertos | 1–13 s | **Añadido**: rápido y fiable en los tres roles |
| mistral-nemotron | Mistral | 3/3 OK | 3/3 OK | 1/3 OK (1 acierto), 2 timeout a 45 s | 4–19 s (clasificador más lento) | **Añadido** para revisor/autor; de clasificador no fiar todavía |
| glm-5.3-flash | Z.ai | 0/3 a 45 s | 0/3 a 45 s | 0/3 a 45 s | con 500 tokens no llega: es modelo de razonamiento (`reasoning_content`) y se queda sin `content` (`finish_reason: length`) antes de responder; repetido a mano con `max_tokens=1000` respondió bien en 62 s | **Añadido**, pero solo sirve con el `max_tokens` por defecto del proveedor (4096), no con presupuestos pequeños |
| nemotron-3.5-lightning-30b-a3b | NVIDIA | 3/3 OK (3–17 s) | 1/3 OK, 2 timeout a 45 s | 2/3 OK+acierto, 1 timeout | inconsistente a pesar del nombre | No añadido: 1 de cada 3 llamadas se queda a medias |
| kimi-k3 | Moonshot | 0/9 a 45 s | — | — | repetido a mano sin límite de tokens: 128 s para responder "hola" | No añadido: demasiado lento para un rol síncrono |
| deepseek-v4.1-flash | DeepSeek | 0/9 a 45 s | — | — | repetido a mano con 170 s de plazo: sin respuesta | No añadido: sin servicio ahora mismo pese a estar en `/models` |
| gemma-4-31b-it | Google | 0/9 a 45 s | — | — | repetido a mano con 170 s de plazo: sin respuesta | No añadido: sin servicio ahora mismo pese a estar en `/models` |

**Lista blanca ampliada** (`proveedores.MODELOS_NVIDIA_GRATIS`, T261): se añaden `nvidia/nemotron-3-super-120b-a12b`,
`mistralai/mistral-nemotron` y `z-ai/glm-5.3-flash` — los tres de otra familia que gpt-oss (independencia
real de revisión, pedido de Damián). `secretos.toml [nvidia] modelos` sigue siendo quien decide cuáles
usa la cascada de verdad; esto solo amplía qué se le permite elegir.

**Sin añadir hoy** (relistar en un próximo banco, la disponibilidad gratuita cambia): `nemotron-3.5-lightning-30b-a3b`
(inconsistente), `kimi-k3`, `deepseek-v4.1-flash`, `gemma-4-31b-it` (sin respuesta hoy pese a estar en
`/models`). `openai/gpt-oss-120b` sigue en la lista pero ya no está en el catálogo: no depender solo
de él.

**No evaluados en este banco** (necesitan otro tipo de llamada, no chat de texto — quedan como
candidatos de la tabla de arriba para tareas futuras, sin comprobar todavía): `nemotron-3-embed-1b`
(RAG/memoria, T181/T144), los clasificadores de seguridad (`nemotron-3.5-content-safety`,
`llama-guard-4-12b`, `llama-3.1-nemotron-safety-guard-8b-v3`, T158), visión (`llama-3.2-90b/11b-vision-instruct`,
T027) y voz (T025/T159: `magpie-tts-zeroshot`, `nemotron-voicechat`, Studio Voice, Background Noise
Removal — estos cuatro de voz **no aparecen en `/models`** hoy; puede que se sirvan por otra vía, revisar
antes de dar por buena la lista de voz).

Siguiente paso: relistar los modelos "sin añadir hoy" en un próximo banco (la disponibilidad gratuita
de NVIDIA cambia de un día a otro) y comprobar por separado los candidatos de RAG/seguridad/visión/voz
con el tipo de llamada que les corresponde.
