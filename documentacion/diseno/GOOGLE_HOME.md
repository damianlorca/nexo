# T697 · Google Home mini "Damián" hablando con NEXO — qué permite Google hoy y vía propuesta

Estado: **INVESTIGADO** (solo documento; no se ha reproducido nada en el altavoz: las pruebas, solo con Damián
delante, casa compartida). Claude (Opus 5.5), noche 05/10/2026, con búsqueda web; fuentes al final.

## 1. Lo que hay hoy (octubre 2026)
1. **No existe forma oficial de que un agente propio converse por un altavoz Google.** Las *Conversational Actions*
   ("Ok Google, habla con X") se cerraron el 13/06/2023; su sustituto, *App Actions*, solo funciona en Android
   (móvil, reloj, TV, coche), **no en altavoces ni pantallas** [1][2]. No hay que suponer que existen (lo pedía
   T697).
2. **Gemini para Home ya está en España y en español** (abril 2026) y sustituye al Asistente en los altavoces; el
   Nest Mini (2.ª gen) y el Home Mini (1.ª gen) están en la lista de compatibles (firmware Cast ≥ 3.76) [3][4][5].
   Gemini contesta él, no NEXO.
3. **Rutinas de Google Home con editor de scripts**: un iniciador por voz con frase fija
   (`assistant.event.OkGoogle`, p. ej. "brief de NEXO") y acciones sobre dispositivos o del asistente
   (`assistant.command.Broadcast`, `assistant.command.OkGoogle`) [6][7]. **No hay acción "llamar a una URL"**: una
   rutina no puede avisar a NEXO directamente.
4. **IFTTT** con Google Assistant (V2, desde 2022): solo "activar escena" con frase fija, sin texto variable ni
   respuesta hablada; y hay informes de que se rompe con el cambio a Gemini (de segunda mano) [8].
5. **Puentes con interruptores virtuales** (SmartThings, Google Home Playground, Matter Virtual Device, Hubitat,
   Node-RED SmartNORA...): un interruptor virtual que una rutina enciende y que NEXO lee. Todos piden una cuenta o
   proyecto de desarrollador y algunos usuarios dicen que el disparo no es fiable [9][10]. Cloud-to-cloud tiene
   cambios de vinculación de cuentas antes del 30/10/2026 [10].
6. **Cast al altavoz desde el PC** (lo que NEXO ya tiene: T025, pychromecast + Piper instalados): el PC manda audio
   al Nest Mini por la red local. No depende de cuentas de Google ni de Gemini.

## 2. Vía viable y gratuita (propuesta)
**A. NEXO habla → altavoz por Cast (sin cuentas nuevas, local, coste 0). RECOMENDADA.**
- NEXO compone el brief en texto: noticias (radar "novedades" / fuentes fijas), lo importante que hizo NEXO (registro
  de turnos y tareas cerradas con evidencia) y las tareas de Damián (bandeja). Texto corto (≤ 90 s de audio).
- Voz: Piper en local, voz en español (T117). Altavoz: el de nombre exacto **"Damián"**, nunca el Nest Hub
  "marina" (regla de T697/T025); si no lo encuentra por nombre exacto, no reproduce nada.
- Disparadores posibles, todos gratis:
  1. **Hora fija**: turno `brief` en la tabla de turnos (planificador T231), p. ej. 08:30 de lunes a viernes,
     desactivable desde la web.
  2. **Botón en la web/móvil** ("Cuéntamelo ahora", en el Centro o en la PWA del POCO F7): POST con CSRF que lanza
     el brief.
  3. (Opcional) Volumen fijo y "no molestar" por horas en Ajustes.
- Límites: el PC tiene que estar encendido y en la misma red; no es una conversación (Damián escucha, no pregunta).

**B. Voz → NEXO (frase fija) → A. Solo si Damián lo quiere: necesita un puente con cuenta.**
- "Ok Google, brief de NEXO" → rutina de Google Home (editor de scripts) → enciende un interruptor virtual →
  NEXO lo detecta y lanza A.
- El puente gratis más sencillo es un interruptor virtual de SmartThings (cuenta Samsung) o de Google Home
  Playground; NEXO lo leería con un token personal. **Crear esa cuenta y dar el token es decisión de Damián**; y su
  fiabilidad con Gemini hay que probarla con él delante.

**Lo que no se puede (hoy):** pedir algo libre por voz al altavoz y que conteste NEXO. Para preguntas libres, la vía
es el chat de NEXO en el móvil (web/PWA), no el altavoz.

## 3. Plan de prueba (con Damián delante)
1. Comprobar que el altavoz "Damián" aparece por Cast desde el PC (descubrimiento, sin reproducir).
2. Brief de prueba de 10 s con volumen bajo, Damián presente.
3. Si da el OK: turno `brief` a la hora que elija y botón en la web.
4. Solo si quiere la vía B: decide la cuenta del puente; se prueba igual, con él delante.

## 4. Decisiones de Damián
1. Hora del brief (o solo botón) y qué secciones quiere.
2. Si quiere la vía B (voz con frase fija), que exige una cuenta de puente (SmartThings u otra) y un token.

## Fuentes
1. Google Developers, *Conversational Actions sunset overview*: https://developers.google.com/assistant/ca-sunset
2. Android Police, *Google is shutting down Assistant's Conversational Actions in favor of App Actions for Android*:
   https://www.androidpolice.com/google-shutting-down-assistant-conversational-actions-app-actions-for-android/
3. Ayuda de Google Nest, *Información sobre el asistente de voz de Gemini para Home*:
   https://support.google.com/googlehome/answer/16618650?hl=es-
4. Infobae (08/04/2026), *Gemini para el hogar ya llega a España*:
   https://www.infobae.com/tecno/2026/04/08/gemini-para-el-hogar-ya-llega-a-espana-asi-cambia-el-asistente-de-voz-de-google/
5. Google Blog, *Gemini for Home launch*: https://blog.google/products-and-platforms/devices/google-nest/gemini-for-home-launch/
6. Ayuda de Google Home, *Write scripted automations with the script editor*:
   https://support.google.com/googlehome/answer/13460475
7. Google Home Developers, *Action (schema)*: https://developers.home.google.com/automations/schema/reference/standard/action
8. 9to5Google, *Google Assistant's IFTTT integration is changing*: https://9to5google.com/2022/08/02/google-assistant-ifttt/
   e IFTTT, *Google Assistant changes*: https://ifttt.com/explore/google-assistant-changes
9. Google Nest Community, *Virtual Switch Creation*: https://www.googlenestcommunity.com/t5/Home-Automation/Virtual-Switch-Creation/td-p/674738
10. Google Home Developers, *Cloud-to-cloud* y *Matter Virtual Device*: https://developers.home.google.com/cloud-to-cloud ·
    https://developers.home.google.com/tools/virtual-device
