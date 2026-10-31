# FASE 2 — K. Consulta selectiva multi-IA (Qwen local + Gemini + ChatGPT)

Dos preguntas, elegidas porque son las únicas de todo este análisis donde: (a) hay varias alternativas razonables, y (b) el conocimiento propio de Claude puede estar desactualizado (corte enero 2026) frente a lanzamientos de modelos o librerías posteriores. No es un barrido — es exactamente lo que Damián pidió: selectivo, con valor real esperado.

Metodología: Qwen local primero (rápido), luego Gemini y ChatGPT vía `extremidades/navegador.py` con pausas de 20s antes de cada pregunta y 75s entre preguntas (lección de la Fase 3: pausas cortas mezclan respuestas de conversaciones distintas). Script: `consulta_fase2.py`, en segundo plano. Resultados completos en `registros/fase2_arquitectura.json`/`.txt`.

---

## Pregunta 1 — Modelos locales dado el hardware real

**Contexto dado a las tres IAs:** Ryzen AI 9 HX 370 (12 núcleos/24 hilos), 31 GB RAM, iGPU Radeon 890M (~3 GB utilizables vía DirectML, sin CUDA), uso actual qwen2.5:7b (obrero) + qwen3:14b (criterio), tolerancia a que el PC trabaje muchas horas si eso ahorra cuota de pago. Se pidió recomendación para: (a) triaje/clasificación, (b) vigilar/verificar otro agente, (c) resumir contexto largo, (d) planificación preliminar.

| | Qwen (local) | Gemini | ChatGPT |
|---|---|---|---|
| (a) Triaje | Phi-3-mini 3.8B / Llama-3-8B | Qwen2.5/Qwen3 3B-7B, o Phi-4-mini 3.8B | Qwen3-4B (o 1.7B si hace falta más velocidad) |
| (b) Vigilar/verificar | Phi-3-medium 13B / Mistral-7B | DeepSeek-R1-Distill-Qwen-14B / -Llama-8B | Qwen3-8B (thinking off) / Qwen3-14B para errores sutiles |
| (c) Resumir contexto largo | Phi-3-medium 13B / Gemma-2-9B | Qwen2.5/3-14B, o Gemma 3 12B/27B (Q4) | Gemma 3 12B (128K contexto) |
| (d) Planificación preliminar | Llama-3-8B / DeepSeek-V2-7B | DeepSeek-R1-Distill-Qwen-32B (Q4_K_M, ~20GB RAM) | Qwen3-14B |
| Veredicto propio | Sustituir Qwen por Phi/Llama | Qwen sigue siendo la base + sumar DeepSeek-R1 para supervisión/planificación | Qwen3 (familia actualizada) + Gemma3-12B como complemento |

**Coincidencias:** Gemini y ChatGPT coinciden en mantener Qwen como base (actualizando a la familia Qwen3, no la generación qwen2.5/qwen3 mezclada que hay hoy) y en usar Gemma 3 12B para contexto largo. Ambos sugieren DeepSeek-R1-Distill como pieza nueva específicamente para razonamiento/verificación paso a paso.

**Discrepancia:** Qwen local recomienda abandonar su propia familia por Phi/Llama/Mistral. Se interpreta con cautela: es la respuesta de un modelo evaluándose a sí mismo con conocimiento propio probablemente más limitado sobre lanzamientos recientes — el mismo sesgo que se anticipó al diseñar esta consulta. No se sigue esta parte de la respuesta.

**Conclusión (ver también sección A):** no sustituir el stack, actualizarlo dentro de la familia Qwen3 (4B/8B/14B según papel) y añadir DeepSeek-R1-Distill-Qwen-14B como candidato nuevo para el papel de auditor/verificador de razonamiento. Gemma 3 12B como alternativa a evaluar para resúmenes largos.

**Decisión pendiente de Damián:** ninguna decisión de implementación todavía — esto es una lista de candidatos a medir en su propio hardware antes de tocar `config.toml`, no una sustitución decidida.

---

## Pregunta 2 — Control visual/desktop híbrido en Windows

**Contexto dado a las tres IAs:** jerarquía deseada (estructurado/API primero → UI Automation/accesibilidad → automatización de escritorio general → visión/coordenadas como último recurso), pregunta sobre qué librerías Python son estado del arte en 2026 y si existe ya un framework pensado para "agentes de IA que controlan un PC".

| | Qwen (local) | Gemini | ChatGPT |
|---|---|---|---|
| Nivel API/UIA | `pywin32`/`ctypes` | Windows UI Automation directo | — |
| Nivel accesibilidad | `pywinauto`, `FlaUI`, `uiautomation` | `pywinauto` (backend=uia), `comtypes`/`pywin32`, FlaUI vía Pythonnet | `pywinauto` (ya no "el futuro"), **FlaUI (UIA3)** como mejor backend, `uiautomation` como alternativa Python pura |
| Nivel escritorio/coordenadas | `pyautogui`, `keyboard`, `mss` | `PyAutoGUI` | `PyAutoGUI`; Appium+Windows driver existe pero no recomendado como núcleo |
| Framework "agente que controla un PC" | Ninguno conocido; combinar a mano | **Windows-Use** (extrae árbol de accesibilidad vía UIA, solo cae a visión si falla); adaptadores Windows de Anthropic Computer Use / OS-World | **winapp ui** de Microsoft (comandos orientados a agentes: inspect/search/click/invoke/set-value/screenshot sobre UIA); proyectos **Windows-MCP** y **FlaUI-MCP** que exponen estos backends como herramientas de agente |

**Coincidencias:** las tres apuntan a lo mismo que ya se había concluido sin consulta externa: UI Automation/accesibilidad antes que visión, `pywinauto`/FlaUI como opciones maduras, y visión solo como último recurso. Esto **confirma** (no cambia) la jerarquía de 5 niveles ya propuesta en FASE2_D.

**Aporte nuevo real (esto es lo que justificó la consulta):** Gemini y ChatGPT nombran frameworks concretos que Claude no tenía identificados con precisión — **Windows-Use**, **winapp ui** (Microsoft) y **Windows-MCP/FlaUI-MCP** — proyectos pensados específicamente para que un agente de IA controle Windows combinando UIA con vision como fallback, en vez de construir esa combinación desde cero con `pywinauto` + `pyautogui` + `OpenCV` sueltos. ChatGPT propone explícitamente para Nexo el mismo orden ya diseñado: `Playwright/API → UIA3/FlaUI → pywinauto/uiautomation → PyAutoGUI → visión/OCR`.

**Discrepancia:** ninguna sustancial. Pequeña diferencia de énfasis: Gemini prioriza `pywinauto`, ChatGPT lo considera "ya no la opción más futura" frente a FlaUI/winapp-ui — diferencia de matiz, no de arquitectura.

**Conclusión:** la jerarquía de FASE2_D queda confirmada y se añade una nota de investigación futura: antes de escribir código de control visual (que ya está planificado como última prioridad de implementación, ver FASE2_D y FASE2_L), vale la pena evaluar **winapp ui** y **Windows-MCP/FlaUI-MCP** como posible capa ya construida en vez de ensamblar `pywinauto`+`pyautogui`+`OpenCV` a mano — pero esto no cambia el orden de prioridades: sigue siendo la pieza a implementar en último lugar.

**Decisión pendiente de Damián:** ninguna todavía — es evidencia para cuando llegue el turno de implementar control visual, no una decisión a tomar ahora.

---

## Nota de fiabilidad

Esta consulta se apoyó en `navegador.py` (automatización Playwright/CDP de las cuentas personales de Gemini/ChatGPT ya autorizadas, sin nuevas credenciales), respetando las pausas ya documentadas para evitar el bug de extracción de respuestas encontrado en la Fase 3. `WebFetch` alcanzó su límite de sesión durante este mismo periodo de trabajo, así que no se pudo contrastar en profundidad con documentación oficial de cada librería mencionada (por ejemplo, la página de GitHub de Windows-Use o winapp-ui) — los nombres están recogidos tal cual los dieron las IAs consultadas, no verificados página por página. Si alguno de estos frameworks se convierte en candidato real de implementación, se recomienda verificar antes que sigue mantenido y es lo que dice ser.
