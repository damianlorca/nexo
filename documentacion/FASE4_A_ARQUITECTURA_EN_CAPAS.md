# FASE 4 — A. Arquitectura objetivo en capas

## El principio, ahora como regla de diseño, no solo de comportamiento

Las Fases 2 y 3 ya establecieron el reencuadre: Claude deja de ser el centro obligatorio, el recurso mínimo suficiente gana por defecto, se escala solo cuando aporta valor real. Esta fase da un paso más: ese principio se traduce en una **separación de capas explícita**, para que ninguna decisión futura de implementación pueda volver a colapsar "proveedor" y "arquitectura interna" en la misma cosa — que es, con honestidad, lo que pasó en la Fase 1/2: al no haber una capa de Runtime separada del propio Claude, era fácil que cada pieza nueva se pensara "como algo que Claude hace" en vez de "como algo que Nexo hace, usando a Claude quando corresponde".

## Las cuatro capas

```
A. NEXO RUNTIME / ORQUESTADOR
   estado, cola, routing, permisos, memoria, planificacion,
   delegacion, limites, recuperacion, observabilidad,
   comunicacion con Damian

B. MODELOS / AGENTES
   razonar, analizar, planificar, generar, revisar, sintetizar
   (modelos locales, Claude, Gemini, ChatGPT, futuros proveedores)

C. TOOLS / EJECUCION
   archivos, Python, PowerShell, navegador, Windows, vision,
   aplicaciones, imagenes, video, papers, etc.

D. PROVEEDORES
   acceso a cada ecosistema/modelo
   (Qwen/local, Claude, Gemini, ChatGPT, futuros)
```

**Regla explícita, la más importante de este documento: el proveedor (D) no controla la arquitectura interna de Nexo (A).** Hoy esto ya se viola parcialmente sin querer: `canal/bot.py` tiene lógica de decisión (`_texto_triaje`, `_cmd_ahora`) mezclada con lógica de acceso a proveedores concretos — funciona, pero es exactamente el patrón que esta capa prohíbe hacia adelante. No se corrige ahora (no se implementa nada en esta fase), se marca como deuda a resolver cuando se construya el Runtime real (ver FASE4_C).

## Cómo se relacionan las capas con lo ya diseñado en Fase 2/3

| Capa | Piezas ya diseñadas que caen aquí |
|---|---|
| A. Runtime/Orquestador | Model Router (FASE3_E), observabilidad (FASE3_H), permisos (FASE2_J/FASE3_J), ciclo de autonomía (FASE3_J), gestión de proyectos/chats como índice local (FASE3_F) |
| B. Modelos/Agentes | Qwen y candidatos (FASE3_B), Claude/Gemini/ChatGPT como "quien razona" (no como "cómo se accede a ellos") |
| C. Tools/Ejecución | `manos/archivos.py`, `manos/shell.py`, `extremidades/imagen.py`, la futura extensión de `navegador.py` como TOOL de "escribir en un chat", no como el proveedor en sí |
| D. Proveedores | `proveedores.py` (ya existe, es la pieza más cercana a esta capa hoy) + fichas de capacidades (FASE3_D) |

**Corrección importante respecto a cómo se venía hablando de `navegador.py`:** hasta ahora se trataba como "el proveedor Gemini/ChatGPT". Con esta separación de capas, `navegador.py` es en realidad una **TOOL** (capa C: sabe cómo interactuar con una página web) que la capa D (proveedor Gemini/ChatGPT) usa para hablar con el modelo — la distinción importa porque una tool de "controlar un navegador" puede reutilizarse para otras cosas (leer una página cualquiera, no solo hablar con una IA), mientras que un "proveedor" siempre representa el acceso a un modelo/ecosistema concreto. Esta relectura no cambia ningún comportamiento hoy — cambia cómo se organiza el código cuando se implemente el Runtime (FASE4_C), evitando que la lógica de "cómo interactuar con Chrome" quede enterrada dentro de la lógica de "cuándo usar Gemini".

## Por qué esta separación no es burocracia

Sin ella, cada capacidad nueva (un proveedor, una tool, un modelo local) obliga a tocar el mismo código que decide "qué hacer" — el patrón que ya generó, en la Fase 1, el bypass de permisos de `ejecutar_python` (una tool sin capa A por encima que la sujete) y el propio T039 (una integración de proveedor que se coló donde debía estar el Router). Formalizar las capas ahora, antes de implementar el Runtime, es la forma concreta de que la sección 24 de Damián (revisar si la Fase 3 contradice el principio) tenga una vara de medir objetiva: cualquier diseño de la Fase 3 que mezcle capas se marca aquí como algo a corregir cuando se implemente (ver FASE4_00_INDICE, sección de revisión).
