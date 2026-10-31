# FASE 2 — B. Diseño del Model Router (no implementado todavía)

El Model Router no existe hoy. `proveedores.py` (T046) da un contrato común a los cuatro proveedores, pero nada decide todavía cuál usar ni con qué configuración — eso lo sigue decidiendo Claude "a ojo" en cada turno. Este documento diseña qué debería decidir, con qué información, y con qué política — sin escribir código.

## Las siete decisiones que separa el enunciado de Damián

El Router debe resolver, en este orden, para cada encargo:

```
TAREA
  → A. CLASIFICACIÓN          (qué tipo de trabajo es, cuánto importa acertar)
  → B. PROVEEDOR               (Claude / Qwen / Gemini / ChatGPT / ninguno)
  → C. MODELO DENTRO DEL PROVEEDOR   (solo aplica si el proveedor es Claude)
  → D. ESFUERZO / RAZONAMIENTO       (bajo/medio/alto, o "thinking" sí/no)
  → E. CONTEXTO MÍNIMO         (qué hace falta mandar, qué se omite)
  → F. VERIFICACIÓN            (¿hace falta que algo revise el resultado?)
  → G. SEGUNDA OPINIÓN         (¿vale la pena consultar a otra IA además?)
  → RESULTADO
```

Nótese que (B) "qué proveedor" y (C) "qué modelo/nivel de esfuerzo dentro de Claude" son deliberadamente pasos separados — la separación que ya señalaron las 4 IAs en la Fase 3 sigue siendo correcta y se conserva aquí, pero se completa con (D), (E), (F) y (G), que la revisión anterior no detalló.

## A. Clasificación de la tarea

Antes de decidir nada, el Router necesita saber, del encargo:

| Señal | Cómo se obtiene hoy | Cómo se obtendría |
|---|---|---|
| Complejidad | No se mide | Heurística barata: longitud del encargo, número de archivos que toca, si es "leer y responder" vs "diseñar/decidir" |
| Criticidad | No se mide | Explícita: quién lo pide (Damián en directo vs. cola automática) y si toca algo blindado/permisos |
| ¿Necesita herramientas? | Se sabe por el propio prompt | Igual — pero el Router debería poder descartar proveedores que no tienen esa herramienta (Gemini/ChatGPT vía navegador no tienen acceso al PC) |
| ¿Necesita visión? | No aplica hoy | Con la capa de control visual (sección D), sí será una señal real |
| ¿Necesita navegador? | Implícito en qué extremidad se llama | Explícito: si la tarea requiere Gemini/ChatGPT, eso ya fija parte de (B) |
| Longitud de contexto necesaria | No se mide | Estimación: cuánto de `memoria/`, `canal/entrada/`, historial de la tarea hace falta releer |
| Latencia tolerable | No se mide | Explícita por tipo de tarea: un `/ahora` de Telegram tolera menos espera que el turno de noche |
| Disponibilidad de cuota | Parcial (T029 mide uso, no bloquea) | El Router debería poder leer `memoria/uso_diario.json` antes de decidir |
| Historial de errores del proveedor | No existe | Ver sección F (observabilidad): un proveedor que ha fallado las últimas N veces baja de prioridad temporalmente |
| Disponibilidad de un modelo local capaz | No se evalúa | El Router debería preguntar primero "¿esto lo puede hacer Qwen (o el modelo mediano nuevo de la sección A) igual de bien y gratis?" antes de mirar proveedores de pago |

## B. Proveedor

Regla de partida, en orden de preferencia por defecto (se puede saltar si la clasificación lo justifica):

1. **Ninguno (código determinista).** Si la tarea es puramente mecánica (parsear JSON, comprobar que un archivo existe, calcular una puntuación con una fórmula ya escrita), no hace falta ningún modelo. Esta opción falta hoy del todo en el sistema — todo lo que no es un comando de bot pasa, como mínimo, por Qwen o por Claude.
2. **Qwen / modelo local.** Si es clasificación, resumen, verificación mecánica, o planificación preliminar de bajo riesgo (ver sección A).
3. **Claude.** Si hace falta código, decisión, criterio real, o tocar el propio sistema de Nexo.
4. **Gemini/ChatGPT.** Solo cuando la tarea específicamente se beneficia de ese proveedor (ej. generación de imagen con Gemini, una segunda opinión externa) — no como sustituto barato de Claude.

## C. Modelo/esfuerzo dentro de Claude

Esto es lo que hoy bloquea la plataforma para rutinas atadas a un dispositivo (T034: no se puede cambiar `model` por API). El Router puede decidir esto para sesiones interactivas (donde Damián sí puede cambiarlo él mismo, o donde en el futuro exista una vía), pero **no puede aplicarlo automáticamente a las rutinas programadas hoy** — es una limitación de plataforma, no de diseño. El Router debería, aun así, calcular y registrar qué habría recomendado, para que quede evidencia de cuánto se estaría ahorrando o perdiendo por no poder aplicarlo — información útil para decidir si vale la pena que Damián cambie el modelo de la rutina a mano.

## D. Esfuerzo / razonamiento

Aplica tanto a Claude como a Qwen (recuérdese: qwen3 "piensa" y eso cuesta tokens igual que un nivel de esfuerzo alto). Regla propuesta: el esfuerzo se fija por la clasificación (A), no por el proveedor — una tarea de bajo criterio pide esfuerzo bajo sea cual sea el modelo que la resuelva.

## E. Contexto mínimo

Política explícita, pedida por Damián: **"mínimo contexto suficiente"**. Se propone:

- Nunca releer un archivo entero de `memoria/` si ya existe un resumen reciente (Qwen puede generarlo, ver sección A).
- Preferir `nucleo.tareas siguiente/mias/tuyas` (ya filtra) antes que leer `tareas.json` completo.
- Para tareas de seguimiento (una nota más sobre T037, por ejemplo), mandar solo la nota nueva relevante y un resumen de las anteriores, no las notas completas de nuevo — este es justo el problema que la sección G (economía de tokens) detalla con ejemplos reales encontrados en este proyecto.

## F. Verificación

Regla: **verificar cuando el coste de estar equivocado supera el coste de verificar.** Concretamente:
- Cambios a archivos blindados, permisos, o código que toca el canal de Telegram: verificación obligatoria (ejecutar, comprobar) antes de dar por cerrada la tarea — esto ya es una norma del proyecto, aquí se formaliza como parte del Router en vez de depender de que cada prompt lo recuerde.
- Cambios de bajo riesgo en una extremidad aislada (ej. un texto de log): verificación opcional, puede delegarse a Qwen (revisar que el archivo sigue siendo Python válido) en vez de gastar un ciclo de Claude en ello.

## G. Segunda opinión — cuándo consultar a otra IA

Regla explícita pedida por Damián: **"segunda opinión solo cuando el valor esperado lo justifique"**. Se propone un criterio de tres condiciones, las tres necesarias:
1. Hay una decisión real con alternativas razonables (no una pregunta con una respuesta objetivamente verificable).
2. El coste de equivocarse es alto (toca arquitectura, seguridad, o algo caro de deshacer).
3. No se ha consultado ya sobre exactamente esto sin que hayan cambiado las circunstancias (evita volver a preguntar lo mismo, como pidió Damián explícitamente en el punto 8 de su mensaje).

Esto es, en la práctica, la misma regla que ya se aplicó a mano en la Fase 3 (los 5 casos especiales) y en esta misma Fase 2 (dos preguntas, no un barrido) — aquí se formaliza para que el Router la aplique sin que haga falta que Damián la recuerde cada vez.

## Cuándo NO merece la pena gastar Claude — la regla que Damián pidió explícitamente

Propuesta concreta, para que sea accionable y no una vaguedad:

**No llamar a Claude cuando TODAS estas condiciones se cumplan:**
- La tarea es determinista o de clasificación/resumen (cabe en lo que Qwen o código ya hacen bien).
- No toca ningún archivo blindado ni el sistema de permisos.
- No requiere memoria de conversación previa más allá de lo que ya está en `memoria/`.
- Un fallo es barato de detectar y corregir (no es una acción irreversible).

Ejemplo real ya detectado en este proyecto: comprobar si `estado.json` cambió de marca de tiempo antes de empezar a trabajar (ya se hace, pero a veces lo hace el propio turno de Claude leyendo y decidiendo "puede haber otro turno trabajando" — eso es una comparación de timestamps, no necesita criterio).

## Dependencias de este diseño

El Model Router necesita, para funcionar de verdad: (1) el "verificador barato" de la sección A, (2) datos de uso/cuota ya existentes (`nucleo/uso.py`, T029) conectados como entrada, (3) el historial de errores por proveedor que hoy no se registra en ningún sitio estructurado (depende de la observabilidad, sección F). No depende de la capa de proyectos/chats (sección C) ni del control visual (sección D) para su primera versión — puede diseñarse e implementarse antes que esas dos piezas.
