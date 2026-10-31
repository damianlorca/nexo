# FASE 3 — D. Fichas de capacidades por proveedor y uso inteligente de planes gratuitos

## Por qué esto hace falta

Hoy, `proveedores.py` trata a cada IA como una caja con cuatro métodos (`disponible/estado/enviar/capacidades`) — un contrato de software correcto, pero `capacidades()` no está siendo usado por nada todavía porque no existe un Model Router que lo consuma. El punto 6 de Damián pide ir más allá de "proveedor = texto de entrada, texto de salida" y documentar qué puede hacer CADA plataforma de verdad, para que el Router (sección E) pueda decidir con esa información, no solo con "está disponible / no está disponible".

## Ficha de capacidades — plantilla

```
PROVEEDOR
  MODELOS         -- que modelos concretos ofrece, y cual usa Nexo por defecto
  CAPACIDADES      -- razonamiento / coding / busqueda / vision / archivos / voz / imagen
  LIMITACIONES     -- que NO puede o no debe hacerse con este proveedor
  COSTE/QUOTA      -- de pago, gratuito, limite diario/semanal conocido
  DISPONIBILIDAD   -- requiere navegador abierto, sesion iniciada, token, etc.
  CONTEXTO         -- ventana de contexto aproximada
  VISION           -- si soporta imagenes de entrada
  BUSQUEDA         -- si tiene busqueda web nativa integrada
  CODING           -- calidad relativa para codigo
  RAZONAMIENTO     -- calidad relativa para razonamiento profundo
  HERRAMIENTAS     -- function calling / tools nativas
  ARCHIVOS         -- si acepta subir archivos/documentos
  PROYECTOS        -- si tiene concepto de "proyecto" o carpeta de conversaciones
  MEMORIA          -- si tiene memoria propia entre conversaciones
  AUTOMATIZACION   -- via API oficial / via navegador (Playwright-CDP) / via rutina programada
  FIABILIDAD       -- estabilidad observada en el uso real de Nexo hasta ahora
  METODO DE ACCESO -- API, navegador automatizado, rutina programada, etc.
```

## Fichas reales, con lo que se sabe hoy (sin inventar lo que no se ha probado)

**CLAUDE**
- Modelos: familia Claude vía Claude Code (rutinas programadas con modelo fijo por rutina; hoy Opus en el turno de noche).
- Capacidades: razonamiento profundo, coding avanzado, uso de herramientas (MCP), acceso al propio código y memoria del proyecto Nexo.
- Limitaciones: no hay API de disparo remoto disponible en la cuenta de Damián (T039, cerrado); sin control de modelo por API en rutinas atadas a dispositivo (T034).
- Coste/quota: plan Pro, con límites de uso por sesión/día ya observados (T042, rutina FAILED por probable límite).
- Disponibilidad: requiere el ordenador encendido si la rutina exige dispositivo, o sesión interactiva abierta.
- Contexto: el mayor de los cuatro, con memoria del proyecto vía MCP local.
- Visión: sí (no explotada activamente en Nexo todavía).
- Búsqueda: sí (WebSearch), con límites de sesión observados (esta misma revisión los sufrió).
- Coding: el más fuerte de los cuatro para este proyecto (es quien mantiene el propio código de Nexo).
- Razonamiento: el más fuerte de los cuatro.
- Herramientas: las más ricas — MCP completo, acceso a archivos, shell, navegador.
- Archivos/proyectos: gestión completa vía Claude Code + Project de claude.ai.
- Memoria: sí, vía `memoria/` local + Project.
- Automatización: rutinas programadas (cron) + `/ahora` bajo demanda dentro de una sesión ya activa — NO vía API externa.
- Fiabilidad: alta cuando corre, con al menos un fallo observado por límite de uso (T042).
- Método de acceso: Claude Code (rutinas/sesión interactiva), nunca navegador automatizado (T038 cerrada).

**GEMINI**
- Modelos: el que sirva la interfaz web de consumo bajo la cuenta `nexoclaude@sepio.net`.
- Capacidades: razonamiento general, generación de imágenes (ya usada, con reintentos de descarga), probable búsqueda nativa integrada en la interfaz web (no verificado explícitamente si Nexo lo aprovecha).
- Limitaciones: sin gestión de proyectos/conversaciones desde `navegador.py` todavía (sección F); dependiente de que la sesión de Chrome siga autenticada.
- Coste/quota: cuenta gratuita — límites de uso diario del plan gratuito, no cuantificados aún.
- Disponibilidad: requiere Chrome con el perfil `chrome-perfil` y CDP en el puerto 9333 activo.
- Contexto: probablemente amplio en la interfaz web moderna, no medido por Nexo.
- Visión: sí, incluida generación de imágenes.
- Búsqueda: probablemente sí de forma nativa en la interfaz — no explotado explícitamente por Nexo hoy (se le manda texto, no se le pide "busca X").
- Coding: razonable, no comparado en profundidad con Claude en este proyecto.
- Razonamiento: bueno, por detrás de Claude para las tareas más complejas del propio proyecto Nexo.
- Herramientas: las de la interfaz web (generación de imágenes ya usada); function-calling no aplicable vía navegador.
- Archivos/proyectos: la interfaz de Gemini SÍ tiene conceptos de conversación e historial — no explotado desde `navegador.py` (sección F lo aborda).
- Memoria: memoria propia de Gemini entre conversaciones (Google), no confirmado si está activada en esta cuenta ni si Nexo debería depender de ella.
- Automatización: Playwright/CDP sobre sesión ya autenticada — sin token, sin coste de API.
- Fiabilidad: alta desde que se resolvió el bug de extracción (pausas largas); descarga de imágenes puede fallar si se llama demasiado pronto.
- Método de acceso: navegador automatizado (aceptable, es un tercero, distinto de T038/claude.ai).

**CHATGPT**
- Modelos: el que sirva la interfaz web de consumo bajo la misma cuenta.
- Capacidades, limitaciones y método de acceso: análogos a Gemini — mismo mecanismo (`navegador.py`), misma cuenta, mismo tipo de fiabilidad tras corregir el overlay de bienvenida y el pie de disclaimer.
- Diferencia observada: la interfaz de ChatGPT tiene un concepto explícito de "Proyectos" (carpetas de conversaciones) más maduro que el de Gemini en la experiencia de Damián — candidato natural para probar primero la gestión de proyectos de la sección F.
- Coste/quota: cuenta gratuita, límites no cuantificados.
- Fiabilidad: alta tras los arreglos de T045; el mismo bug de extracción con pausas cortas aplica igual que en Gemini (es un problema del propio `navegador.py`, no de un sitio en concreto).

**QWEN / LOCAL**
- Modelos: qwen2.5:7b (worker), qwen3:14b (criterio); candidatos nuevos en estudio (sección B).
- Capacidades: triaje, clasificación, resumen, verificación mecánica — ampliable según sección B.
- Limitaciones: sin búsqueda web propia, sin visión (salvo que se añada un modelo multimodal local, no evaluado), razonamiento y coding muy por debajo de las IAs de pago.
- Coste/quota: cero coste externo — el único límite es tiempo de cómputo del propio PC, que Damián ha dicho explícitamente que no le importa gastar.
- Disponibilidad: depende de que Ollama esté corriendo en el PC — máxima disponibilidad de las cuatro mientras el PC esté encendido, cero disponibilidad si está apagado (de ahí la importancia de la sección sobre "wake" del PC).
- Contexto: limitado por RAM/tiempo, no por una cuota externa — puede ampliarse simplemente esperando más tiempo por respuesta.
- Automatización: total — es la única de las cuatro sin ninguna capa de automatización de terceros por medio, es una llamada de función directa.
- Fiabilidad: alta y ya medida (15,9s, 0 respuestas vacías para el caso de uso actual).
- Método de acceso: llamada directa a Ollama vía `extremidades/qwen.py`.

## Proveedores adicionales a estudiar (no implementar todavía)

- **Perplexity:** su valor diferencial es búsqueda con cita de fuentes en tiempo real — candidato natural para el paso "¿necesito buscar?" del orquestador (sección C), en vez de gastar Claude en una búsqueda simple. Tiene plan gratuito con límites.
- **Microsoft Copilot:** valor potencial si Damián usa el ecosistema Microsoft (Office, Windows) de forma intensiva — no hay evidencia todavía de que aporte algo que Gemini/ChatGPT no cubran ya para este proyecto; estudiar solo si aparece una tarea concreta que lo justifique.
- **Grok:** sin diferencial claro identificado todavía para el caso de uso de Nexo (asistente personal + PC); no se le ve una capacidad única que falte hoy.
- **Otros modelos locales:** cubiertos en la sección B.

**Regla explícita, tal como pide Damián: NO añadir proveedores por cantidad.** Un proveedor nuevo se añade solo cuando resuelve una capacidad concreta que hoy falta (ver la tabla de fichas: la columna vacía o débil de un proveedor existente es la que justifica añadir otro, no la mera existencia del proveedor).

## Uso inteligente de planes gratuitos

La combinación de (modelos locales + planes gratuitos de Gemini/ChatGPT/Perplexity + Claude Pro + automatización) puede cubrir mucho más trabajo total que intentar que Claude Pro lo haga todo — esto es cierto de forma casi aritmética: cada tarea resuelta por un plan gratuito es una tarea que no consume ni tiempo ni cuota de Claude. La condición explícita de Damián se mantiene sin ambigüedad: **usar inteligentemente lo disponible, nunca generar volumen artificial ni intentar burlar límites de uso** — esto excluye, por diseño, cualquier automatización que dispare más llamadas de las que la propia tarea necesita, o que intente rotar cuentas/sesiones para esquivar un límite. El Model Router (sección E) es el mecanismo concreto que decide "esto va a Gemini gratis" vs. "esto necesita Claude", no una explotación de cuotas.
