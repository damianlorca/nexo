# FASE 3 — N. Qué cambia del roadmap de la Fase 2, y el nuevo orden recomendado

## Qué partes de la Fase 2 se corrigen o modifican (respuesta directa a la pregunta S de Damián)

1. **El papel de Qwen/local deja de ser "abaratador de Claude" y pasa a ser "centro operativo por derecho propio"** (sección A) — FASE2_A seguía siendo válida en sus hallazgos concretos (qué hace hoy, qué modelos medir), pero su marco de referencia estaba subordinado a Claude. Esta fase no descarta ese contenido, lo reencuadra.
2. **El control del PC (FASE2_D) deja de ser "la última pieza del roadmap" y pasa a tener una parte adelantada** (sección G) — los niveles 1-2 de su jerarquía (ya en uso para Gemini/ChatGPT) se amplían antes, mientras los niveles 4-5 (visión/coordenadas genéricas) siguen esperando al final, como ya proponía la Fase 2.
3. **El Model Router (FASE2_B) se amplía de "selector de proveedor" a "10 decisiones"** (sección E), incorporando timeout/pasos máximos/fallback que antes vivían solo en la observabilidad (FASE2_F), ahora conectados explícitamente.
4. **La observabilidad (FASE2_F) se amplía con la cadena de origen de cada decisión** (sección H) — necesaria porque ahora hay más eslabones entre "Damián pide algo" y "se ejecuta algo".
5. **Se añade una etapa nueva al ciclo de autonomía**, MEJORAR (sección J), conectada al aprendizaje por evidencia (sección E) que no existía en la Fase 2.
6. **Se reafirman sin cambios:** T038 cerrada, T039 cerrada del todo, L1/REQ-070 como prioridad máxima, la recomendación de pausar el turno de noche, y el Caso E de autonomía sigue sin resolverse por decreto.

## Roadmap actualizado (sustituye al de FASE2_L)

Sigue la disciplina exacta pedida por Damián: **ANÁLISIS → IMPLEMENTACIÓN → PRUEBA REAL → VERIFICACIÓN → DOCUMENTACIÓN → SIGUIENTE**, una pieza cada vez.

1. **Seguridad base: cerrar L1 (`ejecutar_python`) y REQ-070.** Sin esto, nada de lo demás es seguro de construir. Sin cambios respecto a la Fase 2 en este punto — sigue siendo el primer paso.
2. **Observabilidad mínima con cadena de origen** (sección H): `memoria/estado_actual.json` + `/estado` en Telegram, incluyendo el campo `origen` desde el diseño inicial (más barato añadirlo ahora que después).
3. **Model Router v1 (sin aprendizaje todavía):** implementar el pipeline de la sección E como código determinista + Qwen para la parte de clasificación en lenguaje natural — sin las 10 decisiones completas de golpe: empezar por proveedor + modelo + contexto (las 3 más urgentes y ya semi-resueltas por piezas existentes), añadiendo el resto (esfuerzo, herramientas, timeout, pasos, fallback) en iteraciones sucesivas.
4. **Ampliar Qwen con el rol de verificador** (sección B) — medir en el hardware real antes de decidir el modelo definitivo.
5. **Vigilante ligero de bucles** (código determinista, no un LLM, sección B) — alimenta la observabilidad del paso 2.
6. **Extensión de `navegador.py`: detectar y verificar conversación/proyecto actual** (sección F, la función más barata de la lista) — antes de "crear/seleccionar", que se añade después.
7. **Fichas de capacidades por proveedor conectadas al Router** (sección D) — hasta ahora `capacidades()` existe en el contrato pero nadie lo consulta; conectarlo es lo que hace útil el Router del paso 3.
8. **Aprendizaje por evidencia v1** (sección E) — solo cuando el Router del paso 3 lleve ya un tiempo generando datos reales que registrar.
9. **Permisos ampliados a aplicación/ventana/proveedor/origen/nivel de autonomía del Router** (sección J, la parte que falta tras el paso 1).
10. **UI Automation acotada (nivel 3, lista blanca) para observar estado/límites de proveedores** (sección G) — antes de cualquier acción, solo lectura.
11. **Extensión completa de `navegador.py`: crear/seleccionar conversación** (sección F, resto de funciones).
12. **Autonomía incremental completa** (ciclo con las 8 etapas de la sección J) — última pieza, cuando todo lo anterior está probado por separado.
13. **Control visual genérico (niveles 4-5)** — sigue siendo, de forma deliberada, de las últimas piezas, tal como ya proponía la Fase 2 para el caso más arriesgado.

**Diferencia clave respecto al orden de FASE2_L:** el trabajo sobre `navegador.py` (antes en el puesto 7 de 10) se adelanta y se divide en dos pasos (6 y 11) porque es la pieza de menor riesgo de seguridad nueva (reutiliza una automatización ya probada) y de mayor valor inmediato (evita el error más caro: escribir en el chat equivocado). El control visual genérico se mantiene al final por las mismas razones que en la Fase 2.

## Sobre la compra/decisión de wake del PC (sección I)

No forma parte del orden de implementación de software — es una decisión y posiblemente una compra que Damián puede resolver en paralelo, sin bloquear ni ser bloqueada por el roadmap de arriba.
