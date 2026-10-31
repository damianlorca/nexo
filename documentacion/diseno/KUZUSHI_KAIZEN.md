# Kuzushi y Kaizen (T1011): diseño del coordinador

v3, 20/10 15:05: v2 (los 15 puntos que Damián aprobó) + 7 ajustes del segundo repaso del coordinador (marcados R2).
Validado por el coordinador; va a Code detrás de T1027, fase a fase.
26/10 (Bloque 22): fase 1 hecha (apartado 7) y fila nueva en 1.1, "decisiones automáticas de NEXO".

Definición de Damián (17/10): Kuzushi observa absolutamente todo y encuentra y clasifica mejoras, con debate entre
personalidades para no entrar en bucles; Kaizen las implementa en el orden que propone Kuzushi; juntos llegan al
"OK absoluto"; sirven para NEXO y para cualquier otra cosa (libro de sudokus, TFG...).

## 0. Principios
- **Sustituye, no suma** (punto 1). Kuzushi absorbe el TURNO vigía (`nucleo/vigia.py`, T272) y los turnos de revisión
  de código y de documentación, que están en pausa; esos turnos se retiran cuando Kuzushi esté en marcha.
  (R2) NO se toca el vigía de la web (`interfaz/vigia.py`, el que relanza la web si se cae), ni los avisos urgentes
  de `nucleo/avisos.py` (disco bajo, sin turno...): Kuzushi mira una vez por noche y eso tiene que avisar al momento. Los radares siguen en pausa
  y, si vuelven, lo hacen como una fuente más de Kuzushi.
- **Nunca se toca a sí mismo ni a la seguridad** (punto 7). Cualquier propuesta sobre el guardián, la puerta, el
  tribunal, el riesgo, los permisos, el freno, Kuzushi o Kaizen es R3: la hace Claude y la ve Damián. Nada se
  automatiza ahí.
- **Datos privados** (punto 2). Las pruebas pasan por `auditor.tapar` antes de salir del PC. Lo del ámbito personal
  (reels, perfil_privado, chats, el vault privado) solo lo debate la IA local (Qwen 7B, nunca más de 8B).

## 1. Kuzushi: encuentra y clasifica

### 1.1 Observa (sin IA, gratis)
Cada noche recoge señales de lo que ya registra NEXO:
| Fuente | Qué busca |
|---|---|
| Tareas (tareas.json, historial) | tareas que rebotan (≥2 rechazos), atascadas >7 días, cerradas sin evidencia, duplicadas |
| Implementador y puerta | fallos repetidos y su causa (tests ajenos en rojo, modelo vacío, contrato mal escrito) |
| Turnos y planificador | turnos colgados o que pasan el tope, turnos que no producen nada |
| Prompts enviados a las IAs | prompts largos, contexto repetido, restricciones raras (T1021) |
| Proveedores y cuota | errores, bloqueos, gasto por resultado útil |
| Permisos (guardián) | lo que llega a Damián y podía haberse decidido solo |
| Tests | tests que fallan a ratos, tests que dependen de la fecha o la hora |
| Git | reversiones, arreglos que vuelven a romperse |
| Turno vigía (lo que hacía T272) | tendencias de salud: procesos, disco, web (lo urgente sigue en avisos) |
| **Decisiones automáticas de NEXO** (26/10, tras T844) | (a) tarea cerrada (cierre_auto o a mano) cuya evidencia (commit) se revirtió, ya no existe o cuyos tests citados ya no pasan → grave, propone reabrirla; si ya se reabrió pero conserva el cierre viejo, "cierre rancio"; (b) aprobaciones del guardián o el tribunal que luego se denegaron o deshicieron; (c) rechazos de la puerta (o marchas atrás) que eran infraestructura |
Salida: lista de **hallazgos**, cada uno con su evidencia concreta (rutas, IDs, números).
Por qué la fila nueva: el 25/10 a las 21:41 cierre_auto dio T844 por "HECHO Y TESTEADO" con la evidencia del commit
7ecfc17, que era el Revert de su propia fusión (arreglado en c517403). Ningún componente revisaba sus decisiones.

### 1.2 Filtra y presupuesta (puntos 6 y 11)
- Hallazgos obvios con arreglo conocido (un test que depende de la fecha, un proceso sin CREATE_NO_WINDOW) van
  directos a tarea, **sin debate**.
- El resto se ordena por impacto/esfuerzo. Se debaten como mucho tantos como permita la cuota del día
  (`nucleo/cuota.py`), compartida con el tribunal, que tiene preferencia.
- **Como mucho 3 tareas nuevas por noche.** Lo demás queda en una lista de espera (`memoria/kuzushi/espera.jsonl`)
  que se repasa cada semana. Respeta el freno.

### 1.3 Debate (puntos 3 y 10)
Tres personalidades, cada una de una familia de IA distinta (APIs gratuitas primero, como el tribunal):
- **Reformista**: qué cambiar y por qué; propone la solución.
- **Conservador**: obligado a defender "no tocarlo", con riesgos concretos y su coste.
- **Damián**: ¿le quita trabajo o se lo da?, ¿es más simple?, ¿lo entendería sin preguntar? Solo se apoya en lo que
  Damián ha dicho y está en el repo (CLAUDE.md, decisiones registradas en las tareas). (R2) Nada de la memoria
  personal de Damián sale a una IA externa. Si no tiene base, no lo supone: la pregunta sube a Damián.
Reglas:
- **Primera ronda a ciegas**: cada una opina sin ver a las otras. En la segunda ronda ven las tres opiniones.
- Como mucho dos rondas. Un **juez** de otra familia resume: decisión, **alternativa descartada y por qué**, y
  métrica de éxito más métrica de guarda (punto 4).
- Sin acuerdo tras dos rondas: queda "a decidir" para Claude, o para Damián si es suyo.
- (R2) Si las APIs gratuitas no responden, esa noche no hay debate: los hallazgos esperan. Nunca se tira de Claude
  para debatir.
- Se mide **cuánto discrepan**. Si en un mes coinciden en más del 90 % de los casos, el debate no aporta y se pasa a
  una sola opinión más el juez.

### 1.4 Clasifica y apunta
Importancia, prioridad, esfuerzo y riesgo (R0-R3, con `riesgo.py`). (R2) Sus tareas no pasan de prioridad media
salvo seguridad o pérdida de datos: no pueden desplazar a las tareas de Damián. Crea la tarea v2 con origen "kuzushi" y en
`hecho_cuando` la métrica de éxito y la de guarda.

### 1.5 Contra el bucle (punto 8)
- Registro de decisiones vigentes (`memoria/kuzushi/decisiones.jsonl`): cada decisión con su motivo, la alternativa
  descartada y la evidencia que la sostenía.
- Reabrir una decisión **solo por opinión** no se puede antes de 14 días. **Con evidencia nueva de daño**
  (seguridad, pérdida de datos, fallo que se repite) se reabre al momento. (R2) "Nueva" se comprueba sin IA: un
  hallazgo con evidencia distinta (otra huella) y etiqueta de gravedad; la opinión de una IA no cuenta como evidencia.
- Un hallazgo no se propone dos veces: se compara con lo vigente y lo descartado (como el filtro F0).

## 2. Kaizen: implementa y mide
- Coge las tareas de Kuzushi en su orden (las que no dependen unas de otras pueden ir en paralelo) y las manda por el
  camino que ya existe: código con tests → implementador (los tests dados los escribe Claude); prompts, config o
  documentación → borrador + tribunal; R3 o archivos blindados → Claude, con diff para Damián.
- **Métricas** (punto 4): toda mejora lleva una métrica de éxito y otra de guarda ("los prompts -30 %, y la nota del
  tribunal no baja").
- **Medición limpia** (punto 5): un solo cambio a la vez en cada zona; ventana de antes y de después con un mínimo de
  casos (R2: al menos 20 casos o 7 días, lo que llegue después). Si no se puede medir, la tarea queda "no medible", nunca "mejorada".
- **Revertir** (punto 9): si empeora, se revierte por la puerta, pero solo si sale limpio; si hay commits encima, se
  crea una tarea para Claude. Queda anotado en el registro de decisiones.
- **OK absoluto** (punto 15): una mejora está "OK absoluto" cuando (a) cumple su `hecho_cuando` con evidencia
  ejecutada, (b) la métrica de guarda no ha empeorado, (c) el juez o el tribunal está de acuerdo y (d) lleva 7 días
  sin regresiones. Sustituye a la definición vaga actual del protocolo.

## 3. Se vigila a sí mismo (puntos 12 y 13)
- **Puntuación de Kuzushi**: qué parte de sus propuestas se adoptaron y mejoraron de verdad. Por debajo del 40 %,
  baja a 1 tarea por noche hasta recuperarse. (R2) Solo cuenta a partir de 10 propuestas cerradas: antes es ruido.
- **Calibración la primera semana**: en la fase 1, Claude repasa los hallazgos y marca útil / no útil antes de dejar
  que se debata solo.

## 4. Lo que ve Damián (punto 14)
Un **resumen semanal** en el Centro: "esta semana Kuzushi vio X, se arreglaron Y, se descartaron Z y por qué", con
enlace a cada caso. Nada de hallazgos sueltos, salvo lo que de verdad le toca decidir (va por Te toca).

## 5. Para cualquier cosa, no solo NEXO
Cada "ámbito" (nexo, libro de sudokus, TFG...) define sus fuentes de observación, su camino de implementación y si es
personal (entonces, solo IA local). Se empieza solo con NEXO.

## 6. Fases
1. **Kuzushi observa** (sin IA): señales, filtro y presupuesto, el resumen semanal y la calibración con Claude.
   Retirar el vigía y los turnos de revisión. Primer encargo: T1021 (prompts a las IAs).
2. **Debate y tareas**: personalidades a ciegas, juez, registro de decisiones y medición de la discrepancia.
3. **Kaizen**: caminos de implementación, métricas con guarda, medición limpia, reversión y OK absoluto.
4. **Otros ámbitos**: libro y TFG.
Cada fase se prueba y se repasa con Damián antes de la siguiente.

## 7. Fase 1 tal como está hecha (Bloque 22, 26/10)
- Código `nucleo/kuzushi.py`; tests `tests/test_kuzushi.py` y `interfaz/tests/test_t1011_kuzushi_web.py`.
- Un observador por fila de 1.1 (`obs_tareas`, `obs_decisiones`, `obs_implementador`, `obs_tests`, `obs_turnos`,
  `obs_proveedores`, `obs_guardian`, `obs_git`, `obs_salud`, `obs_prompts`), todos sin IA y sobre lo que NEXO ya
  guarda (tareas e historial, `evidencias.jsonl`, `aprobaciones.json`, `guardian_decisiones.jsonl`,
  `memoria/implementador/`, la línea base, `registros/turno_nexo_*.json`, `uso_proveedores.jsonl`, avisos, git).
  Un observador roto no tapa a los demás ni da por resuelto lo suyo.
- Cada hallazgo: fuente, tipo, título, gravedad, evidencia, `arreglo` si es conocido, zona y una **huella** (fuente +
  tipo + clave estable). Registro en `memoria/kuzushi/hallazgos.json` (ids K0001...), en espera en `espera.jsonl`,
  estado y muestras de disco en `estado.json`. Todo lo guardado pasa por `auditor.tapar`. Nada sale del PC.
- (a) se comprueba con git (el commit es un Revert, se deshizo después, o ya no existe; un revert del revert lo
  devuelve a la vida) y **ejecutando** los tests citados de los cierres de los últimos 7 días (tope 8 juegos por
  noche); la línea base NO cuenta como prueba (depende del entorno del worktree).
- Encaminado: la primera semana todo a la cola de calibración de Claude; después, R3 (Kuzushi, Kaizen, guardián,
  puerta, tribunal, riesgo, permisos, freno) → Claude; sin arreglo conocido → espera; con arreglo → tarea v2
  (origen `prov: kuzushi`, `quien` claude, prioridad 3, 4 si es seguridad o pérdida de datos, `hecho_cuando` con la
  métrica de éxito y la de guarda), como mucho 3 por día y nunca con el freno F0 puesto. Lo que deja de verse pasa
  a "resuelto" (cuenta como arreglado); si vuelve, "reaparece". Lo descartado (no útil) no vuelve nunca.
- Turno `kuzushi` (04:35, 15 min, sin aviso); retirados y archivados (no borrados) el vigía de novedades (T272) y
  los de revisión de código y de documentación. `interfaz/vigia.py` y los avisos urgentes de `nucleo/avisos.py`, igual.
- Centro: franja "Kuzushi esta semana" bajo las cuatro columnas, pintada con la página (no es un panel más del
  Centro v2); enlaces a `/kuzushi#Kxxxx`, donde está cada caso con su evidencia.
- T1021 (primer encargo): `memoria/kuzushi/T1021_prompts.json` con el inventario de plantillas de prompt (archivo,
  línea, tamaño, restricciones numéricas), frases repetidas entre plantillas, tamaño real enviado por proveedor
  (mediana, p90, máximo) y prompts por borrador. Solo medición: no se ha cambiado ningún prompt.
- Primera pasada real (26/10 17:04): 58 hallazgos (30 media, 28 baja), todos en calibración.
