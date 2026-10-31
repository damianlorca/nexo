# T675 - Repaso de los turnos de NEXO y sus prompts (04/10/2026)
Datos: `registros/turno_nexo_*.json` (79 registros, 23/09-04/10), `registros/uso_proveedores.jsonl` (901 llamadas), `memoria/tareas.json`, `memoria/borradores/` (103), `memoria/freno/`.

## 1. Que producen los turnos
| Turno | Registros | Duracion media | Resultado |
|---|---|---|---|
| Tareas de la cola | 14 | 36 min | 34 filas, 32 con archivo (94 %) |
| Revisar el codigo | 11 | 22 min | 20 filas, 17 con archivo |
| Revisar archivos | 7 | 8 min | 14 filas, 6 con archivo |
| Vigia de novedades | 10 | 10 min | 4 de 10 abortados "sin candidatas", 6 filas |
| Solo correcciones de errores | 6 | 6 min | 4 de 6 abortados "sin candidatas" |
| (sin nombre: pruebas/simulados) | 30 | - | 24 simulados |
Los abortos "sin candidatas" son baratos (no despiertan a ninguna IA): el diseno de T156 funciona. Errores de paso reales en turnos: 3 (todos en pruebas).

## 2. Valor real
- **Propuestas: 303 generadas -> 230 descartadas (76 %), 37 aprobadas por veredicto (12 %), 2 hechas (0,7 %).** Lo que se genera supera con mucho lo que se implementa.
- **Veredictos de Claude: 165** (DESCARTADO 63, APROBADO 50, SUPERADO 38, REHACER 14): se aprueba el 30 %.
- **Borradores: 103.** OK absoluto 19 (18 %), FALLO_MEJORA 23, ESCALAR 15, TOPE_SIN_OK 9, otros 37. Mas de la mitad no llega a OK por su cuenta.
- **El 03/10 el filtro F0 archivo 32 propuestas** por "contradice una decision de Damian": todas tocaban Telegram (congelado el 27/09) y salian de revisar `canal/bot.py` (7 lotes) y `canal/aprobaciones_bot.py`.
- Coste por proveedor (uso real): chatgpt 322 llamadas, 72 % OK (86 ERROR); gemini web 262, 65 % OK (90 ERROR, 6,5 h de espera); nvidia 135, 84 %; gemini_api 88, 66 %; groq 81, 84 % (11 BLOCKED). **Los dos proveedores web fallan 1 de cada 3 veces y concentran 12 h de espera**; las API gratuitas (nvidia, groq) son las mas fiables.

## 3. Fallos de prompt/proceso (T671/T672)
1. Salida truncada a mitad de frase (groq) sin que nadie lo detectara. **Aplicado (fase 1).**
2. La plantilla de investigacion de herramientas externas (identidad, URL oficial, licencia) se aplicaba a documentos internos y sacaba "URL no confirmada" y [SIN VERIFICAR] sobre el propio plan. **Aplicado (fase 1): plantilla `investigacion_interna` con `material:interno`.**
3. Los turnos de revision recorrian Telegram, generando propuestas que el filtro archiva. **Aplicado (fase 1).**
4. Los revisores groq/nvidia marcaban [FALSO] datos ciertos de 2025-2026 sin prueba (T334). **Aplicado ya (commit bdb78f2).**

## 4. Fase 1 aplicada (con tests, `tests/test_t675_turnos.py`)
- `trabajo._truncado()` + `Delegacion.trabajar()`: una salida cortada (ultima linea sin cerrar, o propuesta sin RIESGO) no se acepta como borrador y se prueba con el siguiente proveedor; queda en `exp["truncados"]`.
- `INSTRUCCION["investigacion_interna"]`: cuando la tarea es `cat:investigacion` + `material:interno`, el encargo pide analizar SOLO el material entregado (ids y archivos citados), sin URL ni licencia, y con RESULTADO ADOPTAR/ADAPTAR/DESCARTAR.
- `plantillas_turno.SIN_TELEGRAM_DIRS/ARCHIVOS`: `revisar_codigo`/`revisar_archivos` ya no recorren `canal/` ni `docs/TELEGRAM.md` (reversible vaciando las constantes).

## 5. Fases siguientes (propuestas; no aplicadas)
- **Fase 2 - menos propuestas, mejores.** El tope de 5 propuestas por borrador alimenta el 76 % de descarte. Probar tope 3 en los turnos de revision y exigir en cada una el ARCHIVO/LINEA y un test que la comprueba; las que no lo traigan no se crean (el auditor `h_propuestas` ya valida el formato, no el contenido). Medir en 2 semanas propuestas/aprobadas.
- **Fase 3 - proveedores.** Orden de autor para borradores largos: nvidia/groq (84 %) antes que las web (65-72 %), dejando las web para cuando se necesite busqueda real. Hoy `_generadores` empieza por ChatGPT web. Medir tiempo y OK antes de cambiar. (Toca `router.py`/`trabajo._generadores`: decision de Damian.)
- **Fase 4 - vigia.** 4 de 10 turnos del vigia abortan sin candidatas: bajar su frecuencia a la que realmente produce, y que la plantilla del vigia use `investigacion_interna` cuando compare con el propio backlog.
- **Fase 5 - coordinar con T321/T682 y F1 (T667):** los prompts del tribunal ya distinguen `documento` vs `investigacion`; falta que los de generacion (esta fase 1) y revision usen la misma tipologia.

## 6. Fase 2 aplicada (04/10, `tests/test_t675_fase2.py`)
- `trabajo.PROPUESTAS_FORMATO_CODIGO`: los turnos `revisar_codigo` y `revisar_archivos` piden como maximo 3 propuestas, cada una con `DONDE: archivo:linea` y `TEST: <prueba que la comprueba>`. Investigaciones y demas turnos siguen con el formato de siempre (maximo 5).
- `revision.extraer_propuestas(texto, evidencia=True)` (solo cuando la tarea origen es de esas plantillas): las propuestas sin archivo:linea o sin TEST NO se crean (quedan anotadas en la tarea origen con el motivo) y las que pasan del tope de 3 tampoco. Reversible: `TOPE_CON_EVIDENCIA` y la lista de plantillas en `registrar_borrador`.
- Medir en 2 semanas propuestas generadas/aprobadas de esos turnos (hoy 12 % aprobadas en global).
- Quedan como propuesta para Damian: fase 3 (orden de proveedores, toca `trabajo._generadores`) y fase 4 (frecuencia del vigia, `memoria/turnos_config.json`).
