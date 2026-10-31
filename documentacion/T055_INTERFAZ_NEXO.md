# T055 — Interfaz de Nexo: auditoría + diseño completo

Alcance fijado por Damián el 13/09 (tercera ronda de seguimiento): auditar y
diseñar la interfaz completa de Nexo — conversaciones, proyectos, tareas,
memoria/contexto, estados, evidencias, ejecuciones, logs, aprobaciones,
proveedores/modelos, notificaciones, configuración, escritorio, móvil,
Telegram, Claude/ChatGPT/demás — partiendo de una hipótesis a validar, no a
dar por buena: *"interfaz local = centro de mando; Telegram = móvil y
notificaciones; proveedores = entornos especializados"*.

Solo auditoría y diseño. Ningún archivo tocado, ningún código nuevo escrito
en producción.

## 1. Auditoría — qué existe HOY, confirmado leyendo el código real

No por notas anteriores: releídos `canal/bot.py`, `router.py`,
`consumidor_router.py`, `nucleo/tareas.py`, `config.toml` y el listado
completo del repo (`listar('*.py')`) el 14/09, para esta auditoría.

| Bloque pedido | Estado real hoy | Evidencia |
|---|---|---|
| **Telegram** | Completo y en producción. `/tarea`, `/tareas`, `/tareas tuyas`, `/hecha`, `/estado`, `/uso`, `/ahora`, `/imagen`; preguntas con botones; mensajes sueltos con triaje Qwen + intento real del Router (T073, solo resumen). | `canal/bot.py` |
| **Móvil** | Cubierto al 100% por Telegram — no hay ni falta ninguna otra vía. | — |
| **Conversaciones** | Viven en dos sitios sin unificar: Telegram (`canal/entrada/`, `canal/salida/`, historial en `memoria/historial.md`) y las sesiones de Claude (claude.ai/Claude Code). No hay un log unificado de "todo lo que se ha hablado con Nexo". | `canal/bot.py`, `memoria/historial.md` |
| **Proyectos** | No existe gestor propio. Diseñado en `FASE3_F_PROYECTOS_CHATS_Y_INTERFACES.md` (patrón `ConversationManager`, navegación por URL directa a chats de Gemini/ChatGPT) pero nunca implementado. | Fase 3 |
| **Tareas** | Fuente de verdad `memoria/tareas.json`, vista legible autogenerada `memoria/tareas.md`, CLI completa (`-m nucleo.tareas lista\|mias\|tuyas\|siguiente\|anadir\|hecha\|estado\|nota\|render`), comandos de Telegram. Bien cubierto, salvo que todo es texto. | `nucleo/tareas.py` |
| **Memoria/contexto** | `memoria/estado.json` (máquina) + `/estado` en Telegram (ya da un resumen legible, ver `_texto_estado()`). | `canal/bot.py` |
| **Estados** | Igual que memoria/contexto — es el mismo archivo (`estado.json`), sin un histórico visual de cómo ha cambiado el estado en el tiempo (solo `hechos[]`, en texto). | `nucleo/estado.py` |
| **Evidencias** | `registrar_evidencia()`/`leer_evidencia()` (Pieza 1) ya escriben y saben reconstruir cadenas por `execution_id`, pero **no hay ningún visor** — solo se lee con Python a mano o pidiéndoselo a Claude. Hueco real. | `nucleo/registro.py` |
| **Ejecuciones** | Mismo archivo que evidencias (`registros/evidencia.jsonl`, fase `tool`/`ejecucion`) — mismo hueco de visor. | `nucleo/registro.py` |
| **Logs** | `registros/trazas.jsonl` (histórico, desde antes de Pieza 1) sin visor tampoco. | `nucleo/registro.py` |
| **Aprobaciones** | Ocurren solo *dentro* de una conversación de Claude Code en el momento en que una tool blindada devuelve `NECESITA APROBACION` — no hay ninguna cola ni registro de "qué se ha pedido aprobar y cuándo" fuera de esa conversación puntual. Hueco real de visibilidad. | `nucleo/permisos.py` (por notas; no releído completo en esta ronda) |
| **Proveedores/modelos** | Contrato común en `proveedores.py` (T046): cada proveedor sabe decir si está `disponible()`. Sin vista que lo muestre junto — hoy hay que preguntarlo por separado a cada uno. | `proveedores.py` |
| **Notificaciones** | Solo Telegram (mensajes con o sin sonido, fotos/documentos). No hay push nativo de Windows ni email. Suficiente para el uso actual. | `canal/bot.py` |
| **Configuración** | `config.toml` (texto plano, editado a mano o vía Claude) + `secretos.toml` (nunca expuesto). Sin UI de configuración. | `config.toml` |
| **Escritorio** | **No existe nada.** Confirmado por `listar('*.py')` en todo el repo: no hay Flask/FastAPI/tkinter/PyQt/Electron ni ningún servidor local — la única librería relacionada con "ver algo" es `playwright`, y es para controlar Chrome, no para servir una interfaz propia. | `listar('*.py')`, `pip` (Fase 6) |
| **Claude/ChatGPT/demás** | Cada proveedor se usa en su propio sitio: Claude en claude.ai/Claude Code, Gemini/ChatGPT vía `navegador.py` en un Chrome dedicado, Qwen vía Ollama local. Nexo orquesta por debajo (`proveedores.py`, `router.py`) sin intentar unificar sus interfaces — así lo fijó la Fase 4 (capa D: "el proveedor no controla la arquitectura interna de Nexo"). | `proveedores.py`, `extremidades/navegador.py` |

## 2. La hipótesis de partida, contrastada

- **"Telegram = móvil y notificaciones"** → **CONFIRMADA**, sin ajuste. Ya
  funciona así en producción y cubre el 100% del caso de uso móvil.
- **"Proveedores = entornos especializados"** → **CONFIRMADA**, sin ajuste.
  Coincide con la arquitectura de 4 capas ya fijada en la Fase 4 y con cómo
  se han integrado Gemini/ChatGPT/Qwen hasta ahora. No hay ninguna señal de
  que unificar sus interfaces aporte algo — al contrario, complicaría cada
  integración sin necesidad.
- **"Interfaz local = centro de mando"** → **CONFIRMADA EN EL FONDO, PERO
  NO EN LA FORMA.** Hoy el centro de mando de facto ya existe y funciona:
  es literalmente esta conversación (Claude Code + claude.ai, con el
  Proyecto NEXO como memoria compartida). Cada decisión importante de este
  proyecto se ha tomado así. Pero como "centro de mando local" en el
  sentido que pedía la hipótesis — algo que Damián pueda abrir en su propio
  PC sin necesidad de hablar con Claude — **no existe todavía**. Y usar un
  chat de Claude para consultas puramente mecánicas (¿qué tarea toca?,
  ¿qué ha hecho Nexo hoy?, ¿qué evidencia dejó tal ejecución?) choca con el
  principio de "mínimo recurso suficiente" de la Constitución: son
  preguntas que un archivo ya sabe responder sin gastar ningún proveedor.

  **Ajuste propuesto**: mantener a Claude como el canal para lo que de
  verdad necesita razonamiento (decisiones, diseño, código, lo que ya se
  hace hoy) y añadir, como pieza nueva, una interfaz local de **solo
  lectura y coste cero** — sin gastar Qwen, Gemini, ChatGPT ni Claude —
  que muestre lo que ya producen Pieza 1 y el resto de piezas existentes.

## 3. Diseño propuesto (sin implementar)

### 3.1 Qué es

Una página web servida **solo en `localhost`** (nunca expuesta a la red),
que Damián abre con su navegador normal en el propio PC — no el Chrome
dedicado de Nexo (`chrome-perfil`), ese sigue siendo solo para
Gemini/ChatGPT. Lee directamente los archivos que ya existen; no necesita
ningún proveedor de IA para funcionar, así que no compite por cuota ni por
tiempo de Claude/Qwen.

### 3.2 Qué NO es (v1)

- No es un chat. No sustituye a Telegram ni a Claude.
- No escribe nada — v1 es **de solo lectura**, sin ningún endpoint que
  modifique `tareas.json`, `estado.json`, `config.toml` ni ningún otro
  archivo. Menor riesgo posible: ni un solo archivo blindado se toca ni se
  necesita tocar para esta v1.
- No gestiona proyectos/chats de proveedores — eso sigue siendo un hueco
  aparte (ya documentado en Fase 3), fuera de esta v1.
- No sustituye las aprobaciones AMBAR de `nucleo.permisos` — solo las haría
  *visibles* si en el futuro se decide dejar constancia de ellas en algún
  sitio legible (ver 3.4).

### 3.3 Qué muestra, bloque a bloque

- **Tareas**: tabla a partir de `memoria/tareas.json` — mismo cálculo de
  puntuación que ya usa `nucleo.tareas` (reutilizado, no reimplementado),
  filtrable por `depende`/`estado`.
- **Estado/memoria**: la misma información que ya arma `_texto_estado()`
  en `canal/bot.py` (última acción, resultado, qué se espera), reutilizando
  esa lógica en vez de duplicarla.
- **Evidencias/ejecuciones**: lista de las últimas N entradas de
  `registros/evidencia.jsonl`, con reconstrucción de cadena por
  `execution_id` usando `leer_evidencia()` tal cual existe.
- **Logs**: últimas N líneas de `registros/trazas.jsonl`, filtrables por
  evento.
- **Proveedores/modelos**: un `disponible()` por proveedor (`proveedores.py`,
  ya construido), mostrado junto en vez de por separado.
- **Configuración**: `config.toml` en texto de solo lectura (nunca
  `secretos.toml`).
- **Conversaciones**: no un chat completo — un resumen de la última
  actividad de `memoria/historial.md` y de `canal/entrada/`/`canal/salida/`,
  para tener una foto rápida sin abrir Telegram ni Claude.

### 3.4 Huecos identificados que esta v1 NO resuelve (quedan para decisión futura)

- **Aprobaciones sin rastro fuera de la conversación**: hoy, si Damián no
  está mirando el chat de Claude Code en el momento exacto en que algo
  pide aprobación, no hay forma de enterarse desde fuera. Resolverlo de
  verdad significaría que `nucleo/permisos.py` (ARCHIVO_BLINDADO) dejara
  constancia en algún sitio legible cada vez que exige aprobación — eso
  es un cambio de código en un blindado, fuera del alcance de "solo
  diseño" de esta ronda y necesitaría su propio turno con autorización
  explícita de Damián.
- **Gestión de proyectos/chats de proveedores** (Fase 3): sigue sin
  implementar, sin cambios respecto a lo ya documentado.
- **Notificaciones más allá de Telegram** (push nativo, email): no hay
  necesidad detectada hoy: Telegram ya cubre el caso de uso.

### 3.5 Coste/riesgo de implementarlo (si Damián lo autoriza más adelante)

- Servidor local mínimo — puede hacerse con `http.server` de la librería
  estándar de Python (cero dependencias nuevas) o, si hace falta algo más
  cómodo de mantener, Flask (una dependencia nueva, a decidir por Damián).
- Cero archivos blindados tocados en la v1 (todo lectura).
- Cero coste de proveedor: no llama a Qwen/Gemini/ChatGPT/Claude para
  nada, solo lee archivos ya existentes.
- Riesgo de seguridad: si se sirve en `0.0.0.0` en vez de `127.0.0.1`
  quedaría expuesto a toda la red local — debe fijarse a localhost desde
  el primer commit, sin excepción.

## 4. Conclusión

La hipótesis de Damián se confirma en dos de sus tres partes (Telegram,
proveedores) y se refina en la tercera: el "centro de mando local" no debe
ser un chat de Claude por defecto (eso ya existe y seguirá existiendo para
lo que de verdad lo necesite) sino una interfaz de solo lectura y coste
cero sobre lo que Pieza 1 y el resto del sistema ya producen. No cambia el
roadmap por dependencias de la Fase 4 — es una capa de observación pura,
sin dependencias nuevas hacia atrás.

Nueva tarea creada para cuando Damián decida implementarla: **T075**
(interfaz local de solo lectura, v1, servida en localhost). Sin
implementar en esta ronda — auditoría y diseño únicamente, tal y como
pidió Damián para T055.
