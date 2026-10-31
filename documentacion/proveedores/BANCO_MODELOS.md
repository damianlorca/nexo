# Banco de modelos gratuitos por rol (T320, version 1)

Generado por `python -m nucleo.banco_modelos informe` el 2026-10-12 13:13:44. Datos: `memoria/modelos/banco.jsonl`; asignacion: `memoria/modelos/roles.json` (`banco_modelos.modelo_para(rol)`).

Casos (todos con respuesta verificable y material del repo, nunca memoria/ ni el vault): **programar** = los tests dados de T347/T348/T421/T422 (bloques SEARCH/REPLACE aplicados y tests ejecutados); **revisar** = 4 diffs (2 con fallo plantado: fail-closed de `:free` roto y clave en el detalle; 2 limpios); **redactar** = 3 textos con secciones exactas, tope de palabras y sin cifras inventadas; **triaje** = 8 tareas con su categoria (una es una inyeccion de prompt).

Puntos = calidad 50 % + exito 25 % + coste 15 % + fiabilidad 7 % + velocidad 3 % (pesos de Damian, T320). Minimo para asignar: calidad >= 0.75 y todos los casos probados. Cada caso vale la media de sus repeticiones.

Inventario del 2026-10-05 23:20:17: groq 4, nvidia 12, openrouter 15, gemini_api 13, ollama 4.

## Asignacion por rol

| Rol | Mejor | Reserva |
|---|---|---|
| programar | groq:qwen/qwen3.8-27b | gemini_api:gemini-3.5-flash-lite |
| revisar | groq:openai/gpt-oss-120b | nvidia:nvidia/nemotron-3-super-120b-a12b |
| redactar | groq:openai/gpt-oss-20b | nvidia:openai/gpt-oss-20b |
| triaje | groq:qwen/qwen3.8-27b | nvidia:nvidia/nemotron-3-super-120b-a12b |

## programar

| Modelo | Puntos | Calidad | Exito | Mediana s | Casos x pasadas |
|---|---|---|---|---|---|
| groq:qwen/qwen3.8-27b | 0.980 | 0.96 | 1.00 | 1.9 | 4/4 x16 |
| gemini_api:gemini-3.5-flash-lite | 0.888 | 0.83 | 1.00 | 2.3 | 4/4 x16 |
| groq:openai/gpt-oss-120b | 0.854 | 0.75 | 0.94 | 5.3 | 4/4 x14 |
| gemini_api:gemini-3.1-flash-lite | 0.822 | 0.79 | 0.83 | 10.8 | 4/4 x12 |
| nvidia:nvidia/nemotron-3-ultra-550b-a55b | 0.670 | 0.38 | 1.00 | 77.1 | 4/4 x8 |
| openrouter:dots-studio/dots-3-note-preview:free | 0.628 | 0.60 | 0.75 | 26.6 | 4/4 x4 |
| nvidia:nvidia/nemotron-3-super-120b-a12b | 0.588 | 0.50 | 0.50 | 25.3 | 4/4 x4 |
| gemini_api:gemini-3.5-flash | 0.572 | 0.46 | 0.50 | 25.9 | 4/4 x4 |
| nvidia:google/diffusiongemma-26b-a4b-it | 0.500 | 0.00 | 1.00 | 4.8 | 4/4 x4 |
| nvidia:nvidia/nemotron-3.5-lightning-30b-a3b | 0.495 | 0.00 | 1.00 | 36.1 | 4/4 x4 |
| openrouter:inclusionai/ling-3.0-flash-sante:free | 0.413 | 0.17 | 0.75 | 19.9 | 4/4 x4 |
| gemini_api:gemini-3.7-flash | 0.407 | 0.25 | 0.25 | 6.8 | 4/4 x4 |
| nvidia:google/gemma-4-31b-it | 0.366 | 0.25 | 0.25 | 84.2 | 4/4 x4 |
| nvidia:openai/gpt-oss-20b | 0.331 | 0.00 | 0.50 | 51.4 | 4/4 x4 |
| gemini_api:gemini-3.6-flash | 0.282 | 0.00 | 0.25 | 17.4 | 4/4 x4 |
| openrouter:apodex/apodex-1.1-mini:free | 0.274 | 0.21 | 0.25 | 14.4 | 4/4 x4 |
| groq:allam-2-7b | 0.220 | 0.00 | 0.00 | 150.0 | 4/4 x4 |
| nvidia:poolside/laguna-xs-2.1 | 0.220 | 0.00 | 0.00 | 150.0 | 4/4 x4 |
| groq:openai/gpt-oss-20b | 0.207 | 0.00 | 0.08 | 4.5 | 4/4 x12 |
| nvidia:moonshotai/kimi-k3 | 0.185 | 0.00 | 0.00 | 150.0 | 2/4 x2 |
| nvidia:z-ai/glm-5.3 | 0.185 | 0.00 | 0.00 | 150.0 | 2/4 x2 |
| nvidia:z-ai/glm-5.3-flash | 0.185 | 0.00 | 0.00 | 150.0 | 2/4 x2 |
| gemini_api:gemini-omni-1.1-flash | 0.172 | 0.00 | 0.00 | 150.0 | 1/4 x1 |
| nvidia:deepseek-ai/deepseek-v4.1-flash | 0.150 | 0.00 | 0.00 | 150.0 | 4/4 x4 |
| nvidia:meta/muse-glimmer-30b | 0.150 | 0.00 | 0.00 | 150.0 | 4/4 x4 |
| openrouter:nvidia/nemotron-3.5-lightning:free | 0.060 | 0.00 | 0.00 | 150.0 | 4/4 x4 |

## revisar

| Modelo | Puntos | Calidad | Exito | Mediana s | Casos x pasadas |
|---|---|---|---|---|---|
| groq:openai/gpt-oss-120b | 0.978 | 0.96 | 1.00 | 1.1 | 23/23 x69 |
| nvidia:nvidia/nemotron-3-super-120b-a12b | 0.971 | 0.94 | 1.00 | 4.4 | 23/23 x69 |
| groq:openai/gpt-oss-20b | 0.934 | 0.91 | 0.94 | 0.9 | 23/23 x69 |
| groq:qwen/qwen3.8-27b | 0.930 | 0.87 | 0.99 | 0.5 | 23/23 x64 |

## redactar

| Modelo | Puntos | Calidad | Exito | Mediana s | Casos x pasadas |
|---|---|---|---|---|---|
| groq:openai/gpt-oss-20b | 0.983 | 0.97 | 1.00 | 1.1 | 5/5 x15 |
| nvidia:openai/gpt-oss-20b | 0.983 | 0.97 | 1.00 | 14.9 | 5/5 x15 |
| nvidia:google/diffusiongemma-26b-a4b-it | 0.963 | 0.93 | 1.00 | 1.4 | 5/5 x10 |
| groq:qwen/qwen3.8-27b | 0.963 | 0.93 | 1.00 | 0.6 | 5/5 x10 |
| nvidia:nvidia/nemotron-3-super-120b-a12b | 0.963 | 0.93 | 1.00 | 9.1 | 5/5 x10 |
| groq:openai/gpt-oss-120b | 0.958 | 0.92 | 1.00 | 1.8 | 5/5 x15 |
| nvidia:nvidia/nemotron-3-ultra-550b-a55b | 0.949 | 0.90 | 1.00 | 23.4 | 5/5 x10 |
| nvidia:nvidia/nemotron-3.5-lightning-30b-a3b | 0.856 | 0.80 | 0.90 | 60.1 | 5/5 x10 |
| nvidia:deepseek-ai/deepseek-v4.1-flash | 0.192 | 0.00 | 0.00 | 150.0 | 2/5 x2 |

## triaje

| Modelo | Puntos | Calidad | Exito | Mediana s | Casos x pasadas |
|---|---|---|---|---|---|
| groq:openai/gpt-oss-120b | 1.000 | 1.00 | 1.00 | 4.3 | 1/1 x3 |
| groq:qwen/qwen3.8-27b | 1.000 | 1.00 | 1.00 | 0.8 | 1/1 x2 |
| nvidia:nvidia/nemotron-3-super-120b-a12b | 0.947 | 0.90 | 1.00 | 30.7 | 1/1 x3 |
| groq:openai/gpt-oss-20b | 0.666 | 0.55 | 0.67 | 3.1 | 1/1 x3 |
