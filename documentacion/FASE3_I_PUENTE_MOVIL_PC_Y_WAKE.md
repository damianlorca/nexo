# FASE 3 — I. Nexo como puente móvil↔PC, y el problema de "despertar" recursos

## La arquitectura de puente permanente

```
MÓVIL <-> NEXO (Telegram) <-> PC (procesos locales) <-> IAs <-> HERRAMIENTAS
```

Esto ya es, en gran medida, lo que existe hoy: Telegram como canal, el bot y el vigilante como procesos permanentes en el PC, `proveedores.py` como capa hacia las IAs. Lo que falta, tal como lo plantea Damián, es la secuencia completa cuando el PC NO está disponible: Damián escribe desde el móvil → Nexo (¿dónde vive "Nexo" si el PC está dormido?) → decide qué hacer → ejecuta localmente → despierta otro proceso si hace falta → consulta otra IA → espera → verifica → responde.

**El punto débil real, ya identificado en la Fase 1/2 y que esta fase no resuelve por sí sola:** si el PC está completamente apagado o dormido, NO hay ningún proceso de Nexo corriendo para recibir el mensaje de Telegram en primer lugar — el bot vive en el propio PC. Esto significa que "despertar el PC a demanda desde el móvil" (sección T037) es un prerrequisito de esta arquitectura, no una mejora incremental sobre ella: sin eso, un mensaje de Telegram mandado con el PC apagado simplemente no lo recibe nadie hasta que alguien enciende el PC a mano.

## Qué debe permanecer activo, y qué puede dormir

- **Debe permanecer activo mientras el PC esté encendido:** el bot de Telegram y su vigilante (ya lo hacen). Es el único punto de entrada real desde el móvil hoy.
- **Puede dormir/no estar cargado hasta que haga falta:** los modelos locales (Ollama puede cargar un modelo bajo demanda, con el coste de latencia de la primera respuesta), ComfyUI (ya se arranca/reinicia solo), Chrome con el perfil de Gemini/ChatGPT (se arranca cuando `navegador.py` lo necesita).
- **El PC entero:** este es el caso límite que cubre T037/la sección de wake — si el PC está completamente apagado o en suspensión profunda, nada de lo anterior importa.

## Wake del PC — la pregunta ampliada de Damián

No es solo "¿funciona Wake-on-LAN?", es "¿cuál es la arquitectura más fiable para que Nexo pueda disponer del PC cuando lo necesite?". Comparación de las opciones ya identificadas en la Fase 1/2, con fiabilidad/coste/seguridad/limitaciones explícitos, sin decidir compra todavía:

| Opción | Fiabilidad esperada | Coste | Seguridad | Limitación principal |
|---|---|---|---|---|
| Wake-on-LAN clásico (S5, paquete mágico) | Baja en este equipo — sin adaptador Ethernet, solo Wi-Fi (MediaTek MT7925), y WOL sobre Wi-Fi en apagado completo suele no estar soportado por el hardware | Cero (ya integrado) | Alta si se limita a la red local; expuesto si se abre a internet sin VPN | Requiere que el router reenvíe el paquete y que la NIC lo soporte en S5 — ya descartado como poco fiable en este equipo concreto |
| Wake-on-WLAN en S3 (suspensión ligera) | Media — depende de que el adaptador Wi-Fi soporte despertar por paquete en S3, no confirmado en este equipo | Cero | Alta en red local | El PC debe quedarse en S3 (más consumo que S5) en vez de apagado del todo |
| "Red conectada" en reposo S0 (Connected Standby) | Media-alta si el equipo lo soporta bien (ya identificado como investigado en la Fase 1) | Cero, pero más consumo en reposo que S3/S5 | Alta en red local | Hoy deshabilitado por una directiva del sistema; activar tiene el coste de batería que ya se señaló |
| Enchufe inteligente + "Restore on AC Power Loss" en BIOS | **La más fiable de las cuatro**, porque no depende de ningún protocolo de red ni de que el hardware soporte wake remoto — corta y reconecta la alimentación, y la BIOS enciende el equipo automáticamente al recibir corriente | Bajo (un enchufe inteligente, coste único pequeño) | Depende de la seguridad del propio enchufe inteligente/su app — superficie nueva a evaluar, pero no toca la red del PC | Es un apagado/encendido "duro" (no una suspensión) — más lento para estar operativo (arranque completo de Windows) que despertar de suspensión |
| Asistentes de terceros (Google Home/Alexa/IFTTT) combinados con lo anterior | Depende enteramente de la opción de base que activen (normalmente el enchufe inteligente) | Bajo si ya se tiene el ecosistema (Damián ya tiene Chromecasts en casa) | Depende de la cuenta del asistente — otra superficie a considerar | Añade una dependencia externa más (servicio en la nube del asistente) |

**Sin decisión de compra en este documento.** El enchufe inteligente + BIOS parece la opción técnicamente más fiable de las cuatro (no depende de wake remoto por red, que es justo el punto débil de este hardware), pero la decisión final —incluyendo si merece la pena el coste y el tiempo de arranque completo frente a una suspensión— es de Damián (ver NEXT_DECISION_REQUIRED del índice).

## Cómo despertar/activar proveedores externos cuando exista un mecanismo permitido

Distinto de "despertar el PC": una vez el PC está encendido, "despertar" a Gemini/ChatGPT es simplemente relanzar Chrome con el perfil correcto (ya lo hace `navegador.py` con `arrancar()`); "despertar" a Claude es, hoy, arrancar una rutina programada o esperar a la siguiente — no hay mecanismo de despertar Claude bajo demanda desde fuera de una sesión ya autenticada (T039, cerrado). Esto no cambia con esta fase; se reafirma tal cual quedó en FASE2_E.
