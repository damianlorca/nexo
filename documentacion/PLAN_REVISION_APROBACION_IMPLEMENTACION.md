# Plan: revisión → aprobación → implementación sin depender de Claude

Fecha: 03/10/2026. Autor: Claude (sesión de planificación). Estado: **APROBADO por Damián el 03/10/2026** (matriz de riesgo, límites 30/15/14 días y revisión multi-IA en paralelo con F0).

## 0. Diagnóstico (datos reales del 03/10)

| Dato | Valor |
|---|---|
| Tareas creadas en 7 días | **478** (de 663 en total) |
| Propuestas sin revisar (estado `propuesta`) | **242** |
| Revisiones de Claude abiertas | 61 |
| Delegaciones auditadas en 7 días | 57 BLOQUEADAS, 17 APROBADAS, 4 esperando decisión (**77 % bloqueadas**) |
| Auditorías sin revisar | 65 |
| Turnos ejecutados (29/09–03/10) | 26 |
| Commits en 7 días | 132 |

Conclusión: el problema **no es solo que falte quien revise**. Es que se genera mucho más de lo que se puede digerir (unas 240 propuestas por semana) y con baja calidad de entrada (3 de cada 4 delegaciones acaban bloqueadas). Un sistema de revisión, por potente que sea, se ahogará si no se limita y se filtra la entrada. El plan ataca las dos cosas.

## 1. Principios

1. **Primero limitar la entrada, después revisar.** Ninguna fábrica de propuestas trabaja si la cola está llena (límite de trabajo en curso).
2. **Separar tres papeles que hoy están mezclados:** REVISAR (¿es correcto y vale la pena?), APROBAR (¿se puede hacer y quién lo decide?) e IMPLEMENTAR (hacerlo y demostrar que funciona). Ninguna IA aprueba su propio trabajo, y quien implementa no aprueba.
3. **La confianza se gana midiendo.** Los revisores automáticos empiezan con poca autonomía. Se calibran con una siembra a ciegas de Claude y después por resultados (tests, reverts, vetos y coincidencia con Damián); si fallan, pierden autonomía (T667). Nada de "confiar porque sí".
4. **El riesgo decide quién aprueba, no la IA.** El nivel de riesgo se calcula con reglas fijas (qué archivos toca, qué hace) y ninguna IA puede bajarlo.
5. **Todo cambio de código es reversible:** rama aparte, tests obligatorios, fusión solo si todo pasa, y marcha atrás automática si algo se rompe después.
6. **Claude pasa de revisar cientos de cosas a hacer de arquitecto y auditor:** R3, lo que Damián le mande, la siembra de calibración y la mejora del propio sistema.

## 2. El circuito completo

```
GENERACIÓN (turnos, vigía, revisores de código, órdenes)
   │  límite de trabajo en curso: si hay > N propuestas abiertas, los turnos que generan se pausan solos
   ▼
FILTRO AUTOMÁTICO (sin IA o con IA local, coste ~0)
   │  formato completo, deduplicado contra tareas y catálogo, evidencia/fuentes presentes,
   │  valor mínimo, caducidad (una propuesta que lleva 14 días sin avanzar se archiva sola)
   ▼
REVISIÓN: TRIBUNAL (2-3 revisores potentes de familias distintas + verificación de hechos)
   │  unanimidad con hechos verificados → REVISADA
   │  desacuerdo, dudas o FALSO confirmado → APELACIÓN (otras 3 IAs gratuitas más fuertes)
   │  si persiste → BANDEJA DE DAMIÁN (Aprobar / Rechazar / Mandar a Claude); R3 → Claude
   ▼
APROBACIÓN POR NIVEL DE RIESGO (matriz fija, §4)
   │  R0 automática · R1 automática con veto de Damián en 24 h · R2 un toque de Damián o Claude · R3 Claude + diff a Damián
   ▼
IMPLEMENTACIÓN (implementador en rama aparte, §5)
   │  tests primero, límites de tamaño, sin archivos blindados, presupuesto de tiempo
   ▼
PUERTA DE FUSIÓN (verificación independiente)
   │  suite completa + tests nuevos + revisión del diff por otra familia + auditor
   │  verde → se fusiona (R0/R1) o espera el OK (R2)
   │  rojo → hasta 2 reintentos → escalada
   ▼
VIGILANCIA POSTERIOR
      prueba de salud tras fusionar (web /salud, turno de humo); si falla → marcha atrás automática y aviso
```

## 3. Sistema de revisión fiable y escalable

### 3.1 Filtro automático (fase previa, barato)
- Rechaza sin gastar IA: propuestas sin la sección completa (qué, dónde, valor, esfuerzo, riesgo), duplicadas (similitud con tareas abiertas y cerradas en los últimos 30 días), sin fuentes cuando afirman hechos, o con valor ≤ 2 y esfuerzo ≥ 4.
- Agrupa: propuestas parecidas de distintas fuentes se funden en una.
- Caducidad: lo que no avanza en 14 días se archiva con motivo (se puede recuperar).
- Límite de trabajo en curso: máximo **30 propuestas abiertas** y **15 revisiones pendientes**. Si se supera, las plantillas de turno que generan (vigía, revisar código o archivos, investigación) no arrancan y el turno se dedica a revisar o implementar.

### 3.2 Tribunal de revisión (implementado en T667: `nucleo/tribunal.py`, decisiones de Damián del 03-04/10)
- **Damián no paga ninguna IA.** Revisores, por orden: **API gratuitas** de familias distintas (NVIDIA, Groq, Gemini API). ChatGPT y Gemini **web** con cuenta gratuita son revisores **extra**, al final de la lista, con un **cupo diario prudente** (6 y 4; los límites reales no están publicados) que se mide con enfriamiento (`tribunal:<proveedor>` hasta medianoche, sin bloquear otros usos de esa web).
- **Composición:** los 3 primeros **disponibles** de familias distintas, nunca la del autor. Desde el 04/10 cada borrador guarda en su cabecera el modelo exacto del autor (`| modelo ... |`) y se excluye su familia real; en los borradores antiguos, la del primer modelo configurado de su proveedor. Orden del tribunal (04/10, tras el banco `herramientas_nube/_banco_tribunal_0410.py`): qwen3.8-27b (Groq), gemini-3.6-flash, nemotron-3-super, gpt-oss-120b, ChatGPT web, Gemini web. Fuera por retirados o sin respuesta: mistral-nemotron (410), qwen3-32b (404), glm-5.3-flash; no pasaron el banco kimi-k3 ni deepseek-v4.1-flash; mistral-large-2-instruct no consta como Free Endpoint. Solo espera si no hay 3 familias; nunca decide con 2.
- **Suplente (revisión T671):** si un revisor falla (caído, error, salida truncada sin `FIN_DICTAMEN` o acusación FALSO desmentida), entra el siguiente de otra familia. Los dictámenes válidos se guardan: al volver, sigue donde lo dejó.
- **Cada revisor entrega:** GLOBAL y voto por propuesta (APROBAR / RECHAZAR / DUDA) con motivo, RESULTADO ADOPTAR/ADAPTAR/DESCARTAR si es investigación (T674) y FALLOS [FALSO: prueba] o [NO VERIFICABLE]. Plantilla según el tipo de trabajo (investigación de herramienta, documento interno, código, general).
- **Verificación de hechos (T288 + T334):** los fallos con URL o repo se comprueban sin IA. Un FALSO de "no existe" que resulta existir anula a ese revisor; un 404 es un FALSO confirmado e impide la unanimidad de aprobar. Lo no comprobable sigue NO VERIFICABLE y no castiga (un dato de 2025-26 que el revisor no conoce no es falso).
- **Escalera sin Claude:**
  1. **Tribunal:** 3 de 3 (global, cada propuesta y RESULTADO) → se aplica con `revision.veredicto(quien="tribunal")`; 3 de 3 RECHAZAR → DESCARTADO.
  2. **Apelación:** si no hay unanimidad, otras 3 IAs gratuitas más fuertes (nemotron-3-ultra-550b, gpt-oss-120b, gemini-3.7-flash…, sin repetir ninguna del tribunal) reciben el desacuerdo resumido. Unánime → se aplica. Al final de esta lista, y solo aquí (nunca tribunal, calibración ni R3), está **Claude web de NEXO**: cuenta propia de NEXO, plan Free, familia anthropic, Sonnet 5.5 con esfuerzo Alto comprobado en pantalla, cupo de 3 al día. Si muestra su aviso de límite descansa hasta la hora de reinicio; ante un captcha o una verificación se para y avisa a Damián.
  3. **Bandeja de Damián** (web, Centro): resumen de 3 líneas + Aprobar / Rechazar / Mandar a Claude.
- **Claude solo recibe** R3 (solo blindados, secretos o dinero: directo, sin gastar revisores; decisión de Damián del 04/10. Las propuestas de **seguridad** las revisa el tribunal y, si se aprueban, llevan la marca `riesgo:R3` para la implementación en F2), lo que Damián le mande y la siembra de calibración. **Bandeja de Claude: máximo 20**, con el número de pendientes y el botón "Copiar orden" (texto fijo en `documentacion/prompts/CLAUDE_BANDEJA.md`). Sin tope diario de escalados (decisión de Damián del 03/10: sustituye al de la revisión T671).
- **Cuotas (revisión T671):** sin ráfagas (20 s entre llamadas a la misma API, 5 min a la misma web) y respetando `nucleo/enfriamiento.py`; nunca se reintenta en bucle.
- **El tribunal no ve quién escribió el borrador** (se quita la cabecera del autor).
- **Turno:** plantilla `tribunal` (no generadora: el freno F0 no la para; tareas por turno = expedientes). CLI: `.venv\Scripts\python.exe -m nucleo.tribunal ciclo|estado|bandeja_claude|bandeja_damian|sembrar|dictamen|resultado|readmitir`.

### 3.3 Calibración (cómo se gana la confianza)
- **Con Claude, solo la siembra:** 50 casos a ciegas, sin ver el veredicto del tribunal. Son las investigaciones de T667 que tienen borrador (14 de 16: T152 y T261 no lo tienen), que Claude dictamina desde su bandeja, más veredictos históricos de Claude hasta 50, que ya eran ciegos y no gastan Claude (equilibrados entre aprobados y rechazados).
- **Después, calidad por resultados:** suite verde en la puerta de fusión, reverts, vetos de Damián (F2/F3, `tribunal.registrar_resultado`) y coincidencia con Damián en su bandeja. Se registra por revisor y por tipo de trabajo en `memoria/tribunal/calibracion.jsonl`.
- **Revisor** por debajo del 70 % en 20 casos → sale de la lista (`readmitir` para volver).
- **Tipo** por debajo del 85 % (últimos 50, mínimo 20) → tarea para T321 y ese tipo pasa siempre por apelación + bandeja de Damián, hasta recuperar el 90 % en los últimos 20.
- Panel en el Centro con fases, siembra, cupo web, coincidencia por tipo y por revisor.

### 3.3 bis Regla de respaldo (salida prevista, no un fallo del plan)
Si tras la calibración las IAs gratuitas **no alcanzan los umbrales** para revisar (coincidencia por tipo y por revisor de §3.3) o para implementar (piloto de §5.4: tasa de éxito, reverts, coincidencia), **el Claude de Damián sigue como revisor principal** en ese tipo de trabajo, y la búsqueda de sustitutos continúa con el vigía y las tareas de novedades (modelos gratuitos nuevos que entran al banco T320 y se calibran igual). Es una salida prevista del plan: la autonomía se concede por tipo de trabajo y solo con datos; donde los datos no la dan, no se fuerza.

### 3.4 Qué hace Claude
Solo R3, lo que Damián le mande y la siembra: pegando la orden de la bandeja (máximo 20 casos) en una sesión de Code. Todo lo demás lo deciden el tribunal, la apelación o Damián.

## 4. Autorización y aprobación por nivel de riesgo

El nivel lo calcula **código fijo** a partir de los archivos y las acciones que toca la propuesta. El tribunal puede **subirlo**, nunca bajarlo.

| Nivel | Qué incluye | Quién aprueba | Cómo |
|---|---|---|---|
| **R0** | Documentación, notas, tareas, investigación, informes | Tribunal | Automático al quedar REVISADA |
| **R1** | Tests nuevos, interfaz (plantillas, CSS), textos, prompts con prueba A/B, scripts de `herramientas_*` | Tribunal + veto de Damián | Push «Se implementará X mañana salvo que digas NO» (24 h). Silencio = sí |
| **R2** | Lógica del núcleo (`nucleo/*` no blindado), proveedores, router, turnos, datos de memoria, dependencias nuevas | Damián o Claude | Un toque «Aprobar» en la bandeja de la web (T077), con un resumen humano y el diff resumido |
| **R3** | Blindados (`nucleo/permisos.py`, `instancia.py`, `config.py`, `manos/*`), seguridad, secretos, borrados, gasto de dinero, cuentas, red nueva | Claude + Damián | Claude lo prepara como parche y Damián aplica o aprueba el diff. Nunca automático |

**Implementado en T668 (04/10, `nucleo/riesgo.py`):** reglas por ruta (R3: blindados, `.claude/`, `CLAUDE.md`, `secretos.toml`, `.env`, `chrome-perfil/`; R2: dependencias, `memoria/`, código y rutas desconocidas; R1: `tests/`, plantillas y CSS, `roles/`, `documentacion/prompts/`, `herramientas_*`; R0: `.md` y `documentacion/`) y por contenido del diff (borrar archivos, secretos, red nueva fuera de la lista blanca y dinero = R3; un import de terceros que NEXO no usaba = dependencia nueva = R2; R0/R1 de más de 300 líneas = R2). Se calcula dos veces: **previsto** con las rutas que nombra la tarea (sin rutas, por la zona; zona desconocida = R2) y **real** sobre el diff; si el real sube por encima de lo aprobado, se pide OK R2 sobre ese diff. Enlace con N04: el veto R1 es una solicitud `tipo=veto` (24 h; el silencio la aprueba), el OK R2 es una solicitud cuya huella incluye el sha256 del diff (7 días; el silencio es NO). **Máximo 10 R2 esperando** (Damián 04/10): con 10, el implementador no produce más R2 hasta que bajen. El bot de Telegram no las ve; se deciden en el panel "Aprobaciones por riesgo" del Centro, con push por `nucleo/avisos.py`. La marca `riesgo:R3` del tribunal fija R3.

La bandeja de aprobaciones (T077) se convierte en la pantalla central de Damián: lo que espera su OK (R2), lo que se hará salvo veto (R1) y lo que está bloqueado.

## 5. Implementador independiente de Claude

### 5.1 Qué es
Un agente de programación dirigido por NEXO, que trabaja con los mejores modelos de código **gratuitos** según el banco T320 (candidatos: Kimi, DeepSeek, GLM, Laguna o Mistral por NVIDIA y Groq; Devstral o Qwen-coder en local). Herramienta a evaluar en la fase 3, sin decidir a ciegas: Aider (funciona por terminal, hace commits en git, repite con los tests, acepta APIs compatibles con OpenAI y Ollama), OpenHands, opencode (T169) y Kilo Code (T184). [SIN VERIFICAR: elección final tras prueba piloto.]

**Decisiones de Damián del 04/10 (F3):** herramienta **Aider** en `.venv-implementador` (versión fijada con hash, `--analytics-disable`, `--no-auto-commits`: los commits los hace el implementador con su marca); opencode solo si Aider falla en el piloto. OpenHands descartado (Docker/WSL2) y Kilo Code sin ventaja sobre opencode. **Excepción a "ningún turno escribe código":** el implementador escribe código SOLO en su worktree y fusiona en `principal` SOLO por la puerta; nunca R3; la PARADA y el interruptor de turnos lo detienen. **Privacidad:** `.aiderignore` (y el mismo filtro en todo lo que se envía a un modelo) excluye `memoria/becas.md`, `memoria/historial_telegram.json`, `canal/entrada/`, `canal/estado_bot.json`, `secretos.toml`, `.env`, `registros/` y `chrome-perfil/`, con test. **Fusión segura:** solo fusiona o revierte si el working tree de `principal` está limpio; si no, espera a la siguiente tanda. **T226:** no entra en la puerta automática (sus plugins solo funcionan dentro de Claude Code); sus comprobaciones de cadena de suministro y valores inseguros pasan al auditor, en código.

### 5.2 Reglas del implementador
- Una tarea aprobada = una rama propia en un worktree aparte. Nunca toca `principal` directamente.
- **Primero los tests** (lo que la tarea dice que debe pasar), luego el código.
- Límites por nivel: R0/R1 como máximo unas 300 líneas cambiadas y solo en las rutas permitidas por su nivel; nada de blindados; sin red salvo la lista blanca; presupuesto de tiempo y de llamadas.
- Si no lo consigue en 2 intentos: se para, deja informe y la tarea pasa a "necesita Claude".
- Todo pasa por la cola de aprobaciones existente (N04) para cualquier acción ámbar.
- **Dependencias nuevas (revisión T671):** un cambio que añade o sube de versión una dependencia (paquete Python, librería vendorizada, herramienta externa) es **R2 como mínimo** aunque el resto sea R0/R1, y la puerta de fusión añade una auditoría de dependencias: origen y licencia, versión fija con hash, vulnerabilidades conocidas y si ya existe algo equivalente en el repo.

### 5.3 Puerta de fusión (la que realmente protege)
1. Suite completa en verde y tests nuevos que fallaban antes del cambio.
2. Revisión del diff por un revisor de **otra familia** distinta del implementador, con lista fija (¿hace lo pedido?, ¿toca algo fuera de alcance?, ¿hay riesgos?).
3. Auditor: alcance, archivos permitidos, sin secretos, sin cambios en blindados.
4. Si todo pasa: fusión automática (R0/R1) o espera del OK (R2). Cada fusión queda marcada para poder deshacerla.
5. Tras fusionar: prueba de salud. Si falla, marcha atrás automática, aviso push y la tarea vuelve con el error.

### 5.4 Piloto antes de soltarlo
**En dos fases (Damián 04/10):** primero las 10 de documentación reservadas (`triaje:piloto_f3`: T377, T378, T379, T381, T461, T462, T463, T554, T555, T556; T360 resultó ser del router, R2). Si salen con **≥80 % de éxito y ≥80 % de coincidencia con Claude**, después las 6 de código como R2 con el OK de Damián sobre cada diff (T347, T348, T360, T390, T421, T422). Durante el piloto nada se fusiona solo: cada diff pasa por la bandeja de Claude.

Primeras 10-15 implementaciones: solo R0/R1 sencillas (tests, textos, documentación, arreglos pequeños). Claude revisa **todos** los diffs del piloto. Se mide la tasa de éxito, los reverts y la coincidencia con Claude. Con buenos datos se amplía (más tamaño, R2 con OK de Damián); con malos, se ajusta el modelo o la herramienta antes de seguir.

**Resultado de la fase 1 (04/10):** éxito **10 %** (1 de 10: T462), coincidencia puerta–Claude **30 %**. No se abre la fase 2; aplica la regla de respaldo (§3.3 bis). Causas: los modelos gratuitos inventan datos de NEXO que no están en su contexto (estado real, reglas de blindados, P0 frente a Pieza 0) y el revisor de la puerta aprueba texto plausible pero falso (mira alcance, no hechos). Lo mecánico sí funciona tras cuatro arreglos del piloto real (lista blanca de archivos para Aider, alcance, finales de línea y una fuga de `modelos_estado.json` en los tests). La fusión de T462 esperaba porque `canal/estado_bot.json` (lo escribe el bot) nunca estaba commiteado: desde el 04/10 está fuera de git.

**Decisiones de Damián tras la fase 1 (04/10):** (A) la documentación con datos de NEXO se queda con Claude; (B) la fase 2 se abre igualmente, solo con tareas de código con tests y su OK sobre cada diff; (C) la revisión de la puerta tiene que comprobar los hechos contra el repo, y hasta tenerlo la puerta solo fusiona documentación con el FUSIONAR de Claude. El implementador nunca envía nada de `memoria/` ni del vault. Incidente del piloto (archivos de más enviados y pestañas en el Chrome personal): `documentacion/INCIDENTE_2026-10-04_IMPLEMENTADOR.md`.

**Resultado de la fase 2 (05/10, cierre automatico):** exito 0% y coincidencia puerta-Claude sin datos frente al umbral del 80%. Por tarea: T347: fallido; T348: fallido; T421: fallido; T422: fallido. Se aplica la regla de respaldo (§3.3 bis): el implementador queda APARCADO y el Claude de Damian sigue con el codigo; el turno implpil2 no existe (lo borro el fallo de la web del 05/10 a las 01:10 y no se restaura); T348, T421 y T422 cuentan con su 1.a ronda (fallidas con los 2 modelos) porque la 2.a no llego a correr; T676-T680 se desatan de F3 y las hace Claude; hay una tarea (T748) para reprobarlo cuando T320 detecte modelos gratuitos nuevos o mejores.

**Fase 2 superada (11/10):** 4/4: T347, T348, T421 fusionadas y T422 con FUSIONAR de Claude; puerta y Claude coinciden en las 4. Exito 100% y coincidencia puerta-Claude 100% (umbral 80%). El implementador pasa a PERMANENTE: turno cada hora, solo tareas con tests dados y riesgo R0-R2, con la puerta de siempre (R2 = OK de Damian sobre el diff). Sustituye al cierre automatico del 05/10 (reprueba T748 con el ejecutor directo y los modelos del banco T320).

## 6. Reparto de responsabilidades

| Papel | Quién | Qué hace | Qué NO hace |
|---|---|---|---|
| Generadores | Turnos, vigía, revisores de código | Proponen trabajo con formato y fuentes | Aprobar ni implementar |
| Filtro | Código + IA local | Descarta, funde, caduca y limita | Juzgar la calidad del fondo |
| Tribunal | 3 IAs potentes de familias distintas | Revisa y decide APROBADO/DESCARTADO; si no hay unanimidad, apelación y bandeja de Damián | Implementar ni bajar el riesgo |
| Aprobador | Reglas (R0/R1), Damián (R1 veto, R2), Claude (R2/R3) | Autoriza según la matriz | — |
| Implementador | Agente de código con modelos gratuitos | Hace la tarea en una rama, con tests | Fusionar sin la puerta ni tocar blindados |
| Puerta de fusión | Tests + otro revisor + auditor | Decide si entra | Arreglar el código |
| Claude | Arquitecto y auditor | R3, lo que Damián le mande, siembra de calibración, mejora del propio sistema, tareas muy complejas | Revisar en bloque cientos de cosas |
| Damián | Dueño | Veto R1, OK R2, diffs R3, prioridades | Transportar información entre IAs |

## 7. Plan de construcción (por fases, cada una con evidencia antes de la siguiente)

| Fase | Qué | Resultado esperado | Quién |
|---|---|---|---|
| **F0 (ya)** | Freno: límite de trabajo en curso, pausa automática de los turnos que generan, caducidad a 14 días y filtro automático sobre las 242 propuestas actuales | La cola deja de crecer y baja a lo que valga la pena | Code (Sonnet), 1 sesión |
| **F1** | Tribunal de revisión + verificación de hechos (T288 y T334) + apelación + bandeja de Damián + calibración (siembra de Claude y resultados) + panel | Revisiones sin Claude, con coincidencia medida | Code (Opus), 1-2 sesiones |
| **F2** | Matriz de riesgo fija + bandeja de aprobaciones (T077) con veto R1 por push y OK R2 de un toque | Aprobación clara y rápida desde el móvil | Code (Opus), 1-2 sesiones |
| **F3** | Implementador: elegir la herramienta con prueba corta, worktree por tarea, puerta de fusión (con auditoría de dependencias: dependencia nueva = R2 mínimo), marcha atrás automática y piloto de 10-15 tareas | Primeras mejoras hechas sin Claude escribiendo código | Code (Opus) + piloto |
| **F4** | Pasar el backlog que quede por el sistema; Claude solo R3 y lo que Damián le mande | Backlog digerido | Sistema + Claude |
| **F5** | Ajuste continuo: banco de modelos (T320), prompts de revisor e implementador (T321) y subir la autonomía por tipo según los datos | Más autonomía cada semana, con datos | Turnos + Claude |

**Qué hacer con el backlog actual mientras tanto:** no revisarlo a mano. Aplicar F0 (filtro, deduplicado y caducidad), después pasarlo por el tribunal en F1. Claude solo ve R3 y lo que Damián le mande.

## 8. Riesgos y cómo se cubren

- **El tribunal se equivoca en bloque** (las tres IAs comparten un sesgo): la calibración (siembra de Claude y después resultados y bandeja de Damián) lo detecta, y los hechos se verifican con fuentes, no por opinión.
- **El implementador rompe algo:** rama aparte, tests, revisión del diff por otra familia, salud tras fusionar y marcha atrás automática. Sin blindados ni R3.
- **Se cuela algo por el veto R1 porque Damián no lo mira:** R1 solo cubre cambios pequeños y reversibles, y la puerta de fusión no depende del veto.
- **Cuota de proveedores gratuitos:** límites por proveedor, enfriamientos y prioridad a revisar e implementar antes que a generar; el tribunal reparte llamadas sin ráfagas y usa suplente de otra familia sin bajar de unanimidad (§3.2).
- **Claude se satura:** ya no recibe escalados (van a la apelación y a Damián) y su bandeja tiene un máximo de 20 (§3.2).
- **Complejidad del propio sistema:** se construye por fases, cada una útil por sí sola y con tests.

## 9. Decisiones que necesita Damián

1. Aprobar este plan (o cambiarlo) antes de empezar F0.
2. Confirmar la matriz de riesgo (§4), sobre todo que en R1 el silencio en 24 h valga como sí.
3. Confirmar los límites: 30 propuestas abiertas, 15 revisiones pendientes y caducidad a 14 días.
4. Elegir si el plan pasa antes por una revisión multi-IA con OK absoluto (con el sistema actual, unas horas de turno, sin gastar Claude).
