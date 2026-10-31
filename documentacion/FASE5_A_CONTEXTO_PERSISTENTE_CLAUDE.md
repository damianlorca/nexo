# FASE 5 — Parte A: contexto persistente de Nexo en Claude

Objetivo de este documento: auditar, con evidencia real (no supuestos), qué mecanismos de persistencia de contexto existen de verdad en el entorno de Damián, y diseñar sobre esa base — no sobre lo que otro producto de Claude podría tener — una arquitectura de "Bootstrap/Constitución" que permita que un chat nuevo entre en modo Nexo sin que Damián tenga que pegar contexto a mano.

**No se ha implementado nada de lo que sigue.** Es análisis y diseño, tal y como se pidió.

---

## 1. Auditoría real de mecanismos (evidencia, no suposición)

Se comprobaron en vivo, dentro de esta misma sesión, los tres mecanismos candidatos. Resultado:

### 1.1. Memoria de cuenta (`mcp__memory__*`)

- Es real, persiste entre sesiones y **se comparte entre superficies de Claude** (esta sesión de Claude Code, el chat normal de claude.ai, Cowork) — no es específica de Claude Code.
- Ya existe un archivo relevante: `/areas/agente-multi-ia.md`, con descripción "Proyecto de agente personal multi-IA en su PC Windows..." y alias `[agente local, Damián AI Agent, proyecto IA, orquestador multi-IA]`. Esto significa que **el mecanismo de reconocimiento que pides en el punto J ya existe parcialmente**: en cualquier chat nuevo de Damián (esté o no adjunto el Proyecto NEXO), el listado de memoria incluye esta entrada, y las reglas de memoria le dicen a Claude que la lea si la conversación parece tratar de esto.
- **Hallazgo importante (probado ahora mismo, no supuesto):** esta sesión concreta está vinculada al Proyecto NEXO de claude.ai, y **eso restringe la escritura de memoria**: al intentar tocar `/areas/agente-multi-ia.md` la herramienta responde que ese archivo está *fuera* del subárbol de este proyecto y que, para registrar un cambio desde aquí, tendría que crear una **copia distinta** en `/projects/<id-del-proyecto>/areas/agente-multi-ia.md`. Es decir: **una sesión atada a un Proyecto no puede mantener sincronizado el archivo de memoria de cuenta general** — solo puede escribir en su propio subárbol de proyecto. La lectura sí es de cuenta completa (puede leer el archivo general), pero la escritura no.
- Consecuencia práctica ya visible: `/areas/agente-multi-ia.md` está **desactualizado** respecto a la arquitectura real de hoy (habla de "Claude Pro como cerebro/orquestador y ChatGPT/Gemini/Qwen como proveedores", de la carpeta antigua `..\pruebas`, de LM Studio en el puerto 1234 — todo superado por las Fases 2-4). Nadie lo ha corregido porque las sesiones que sí conocen el estado real (como esta) no pueden escribirlo directamente.

### 1.2. Proyecto de claude.ai (herramienta `Projects`)

- Comprobado con `project_info` real: el Proyecto "NEXO" tiene una `description` (el texto que Damián escribió al crearlo), un campo `instructions` que **existe pero está vacío** (`""`), y **5 documentos** (`claude/00-indice.md`, `claude/historial-turnos.md`, `claude/tareas-cola.md`, `claude/gestor-ias.md`, `claude/incidencias-y-mejoras.md`), ocupando 16.5 KB de un límite de 2 MB — hay mucho margen para más documentación.
- El campo `instructions` (instrucciones del proyecto) **no es editable por mí con las herramientas de que dispongo** — `Projects` solo permite leer/escribir/borrar documentos y memoria, no ese campo. Solo Damián puede rellenarlo, a mano, desde la configuración del Proyecto en claude.ai.
- **Hallazgo clave, y esto es lo más importante de toda la auditoría:** cualquier sesión que se adjunte al Proyecto NEXO recibe automáticamente, sin que Damián pegue nada, un aviso del sistema con el nombre del proyecto, su descripción, la lista de documentos, y la instrucción explícita de leerlos antes de responder sobre lo que contienen. **Esto ya está pasando en esta misma conversación** (es literalmente el mecanismo por el que sé qué documentos existen sin haberlos leído todavía). Es decir: el mecanismo de "entrar en modo Nexo sin pegar prompt" **ya existe y ya funciona**, con una única condición: que Damián adjunte el chat nuevo al Proyecto NEXO al crearlo.

### 1.3. Instrucciones generales de Claude (nivel cuenta, fuera de cualquier proyecto)

- Existen como funcionalidad de claude.ai (preferencias/instrucciones personalizadas en Ajustes), pero **no tengo ninguna herramienta que las lea ni las escriba** desde este entorno. Lo más parecido y sí accesible es la memoria de cuenta (1.1), que cumple un papel equivalente para efectos prácticos (se aplica en todo chat, esté o no en un proyecto) pero con la limitación de escritura ya descrita.

### 1.4. Mecanismo específico de Claude Code: `CLAUDE.md`

- Si Damián alguna vez abre Claude Code directamente sobre la carpeta del repo (`C:\Users\damia\Desktop\AI\agente`) en vez de usar esta vía de sesión remota con herramientas MCP, un archivo `CLAUDE.md` en la raíz del repo se cargaría automáticamente como contexto de ese proyecto de código. Hoy ese archivo no existe en el repo. Es un mecanismo real pero **distinto y adicional** al de los Proyectos de claude.ai — solo se activa si se usa Claude Code de esa forma concreta, no en esta vía de trabajo actual (bot de Telegram + sesiones remotas). Se documenta por completitud, no se propone usarlo ahora porque no es como Damián trabaja con Nexo hoy.

### Resumen de la auditoría (tabla)

| Mecanismo | ¿Existe de verdad aquí? | Alcance | ¿Escribible por mí desde aquí? | ¿Se carga solo? |
|---|---|---|---|---|
| Memoria de cuenta | Sí, comprobado | Toda superficie de Claude, todo chat | Solo mi propio subárbol de proyecto, NO el archivo de cuenta general | Sí, siempre (listado + lectura bajo demanda) |
| Proyecto — documentos | Sí, comprobado | Solo chats adjuntos a "NEXO" | Sí | Sí, en cuanto el chat está adjunto al proyecto |
| Proyecto — instrucciones | Existe, vacío hoy | Solo chats adjuntos a "NEXO" | No (solo Damián, en la interfaz) | Sí, en cuanto el chat está adjunto al proyecto |
| Instrucciones generales de cuenta | Existe como función del producto | Todo chat | No | Sí (pero no verificable por mí) |
| `CLAUDE.md` en el repo | No existe todavía | Solo si se abre Claude Code directo sobre esa carpeta | Sí (no aplicado, fuera de alcance de esta vía de trabajo) | Sí, solo en ese modo de uso |

---

## 2. Diseño de los 4 niveles (auditado contra lo que realmente hay)

Tu propuesta original de 4 niveles es correcta en concepto. Ajustada a los mecanismos reales:

### NIVEL 1 — Memoria de cuenta (no "instrucciones generales", que no puedo tocar)
Contenido: una entrada corta y estable que diga qué es Nexo, dónde vive de verdad la información (Proyecto NEXO + PC), y una regla explícita de "no inventar el estado si no lo has leído". **No** debe contener arquitectura, decisiones técnicas ni nada que cambie con las fases — eso es justo lo que hoy está desactualizado en `/areas/agente-multi-ia.md`, y es la prueba de por qué este nivel debe ser mínimo y estable.

Limitación real a aceptar: como una sesión atada al Proyecto no puede escribir el archivo de cuenta general, mantener este nivel al día requiere que, de vez en cuando, una sesión **sin** el Proyecto adjunto (o el propio Damián, pidiéndolo explícitamente fuera del contexto de proyecto) actualice `/areas/agente-multi-ia.md`. Alternativa más simple: reducir su contenido a algo tan estable que casi nunca necesite tocarse (ver Bootstrap más abajo).

### NIVEL 2 — Bootstrap / Constitución (documento de Proyecto, nuevo, no creado todavía)
Un documento nuevo en el Proyecto, propuesto como `claude/00-bootstrap.md`, corto (objetivo: menos de 1 página), con:
- Qué es Nexo y su objetivo en una frase.
- Las 4 capas (Runtime/Orquestador, Modelos/Agentes, Tools/Ejecución, Proveedores) en un párrafo, sin detalle.
- La cadena de ejecución obligatoria (una línea).
- El principio de seguridad transversal (una línea: "los permisos son de Nexo y de la tool, no del modelo").
- El ciclo de autonomía (una línea, con nombre de las 8 etapas).
- Jerarquía de autoridad (ver sección 4).
- Una tabla de "para esto, lee este documento" que apunte al resto de documentos del proyecto según el tema (seguridad → FASE4_J, Router → FASE4_E, etc.) — así el Bootstrap no repite nada, solo indexa.
- Dónde está el estado vivo real (`memoria/estado.json` en el PC) y qué hacer si el chat no tiene el PC enlazado (pedir a Damián el dato, no inventarlo).

Este documento **no se ha creado todavía** (ver sección 7, más abajo, sobre por qué).

### NIVEL 3 — Proyecto (ya existe, ya funciona)
Los 5 documentos actuales más los que se han ido creando en fases anteriores en el repo del PC (`documentacion/FASE*.md`) son candidatos a subirse también como documentos de Proyecto si Damián quiere que sean consultables sin el PC enlazado — hoy solo viven en el PC. Esto es una decisión de alcance, no una necesidad técnica (ver NEXT_DECISION_REQUIRED).

### NIVEL 4 — Estado vivo
Fuente de verdad real: `memoria/estado.json` en el PC — **solo alcanzable si el chat tiene el PC enlazado**. Para un chat sin PC enlazado (por ejemplo, Damián preguntando algo de Nexo desde el móvil sin la sesión remota activa), no hay forma de leerlo directamente. Opciones, sin implementar ninguna todavía:
- (a) aceptar la limitación: un chat sin PC enlazado no tiene estado vivo, solo Bootstrap + Proyecto, y debe decírselo a Damián en vez de inventar.
- (b) mantener un espejo condensado (últimas 5-10 líneas de `estado.json`: fase actual, próxima decisión, bloqueos) como documento de Proyecto, actualizado en cada cierre de fase (como ya hago con `claude/incidencias-y-mejoras.md`) — barato, ya es casi el patrón actual.

Recomiendo (b) porque ya es casi lo que hago sin llamarlo así.

---

## 3. Contenido exacto del Bootstrap (qué SÍ / qué NO)

**Sí:** identidad, objetivo, arquitectura en 4 capas (resumen), cadena de ejecución, principio de seguridad, ciclo de autonomía (resumen), jerarquía de autoridad, índice de qué documento leer según el tema, ubicación del estado vivo real y su espejo.

**No:** tareas, historial, manuales paso a paso, logs, roadmap detallado, fichas de proveedor completas, cualquier dato que cambie con cada fase. Todo eso vive en Nivel 3 y se referencia, no se copia.

Extensión objetivo: que quepa entero en un vistazo (orientativamente medio folio a un folio de texto).

---

## 4. Jerarquía de autoridad

Orden, de mayor a menor peso cuando hay conflicto:

1. **Decisión explícita de Damián en la conversación actual** (siempre gana, incluso sobre el Bootstrap).
2. **Estado vivo** (`estado.json` o su espejo) — es lo más reciente y operativo.
3. **Bootstrap** — si no contradice lo anterior.
4. **Documentación de Proyecto vigente** — la fase más reciente (hoy, Fase 4; con esta, Fase 5) prevalece sobre fases anteriores en cualquier punto donde una fase posterior corrija o reencuadre a una anterior (patrón que ya se sigue: cada índice de fase señala explícitamente qué corrige de la anterior).
5. **Historial** — solo para entender el porqué de una decisión pasada, nunca para invalidar una vigente.

Regla explícita para evitar que un documento antiguo contradiga una decisión posterior: **cada documento de fase debe seguir señalando explícitamente, como ya se ha hecho en las Fases 2, 3 y 4, qué corrige de la fase anterior** — nunca reescribir en silencio. Esto ya es la práctica seguida; se formaliza aquí como regla del Bootstrap.

---

## 5. Versionado del Bootstrap

- Vive como documento de Proyecto (`claude/00-bootstrap.md`) y, en paralelo, como archivo en el repo del PC (`documentacion/00-bootstrap.md` o similar) bajo Git — así tiene una única fuente de verdad versionada (Git) y una copia consultable sin el PC enlazado (Proyecto).
- Cada cambio de arquitectura relevante (como el de esta misma fase) debe actualizar ambas copias en el mismo turno — igual que ya hago con `claude/incidencias-y-mejoras.md` y el repo.
- Propuesta de autoría: solo se actualiza al cerrar una fase de arquitectura (no en caliente durante el trabajo diario), para que no acabe con contenido a medias.

---

## 6. Coste de contexto

- Bootstrap corto (menos de 1 página) — coste de lectura mínimo, y solo se lee cuando hace falta (project_search dirigido), no en cada mensaje.
- El Proyecto ya funciona "bajo demanda": el sistema no vuelca los 5 documentos completos en cada turno, solo su lista de nombres — la lectura completa ocurre solo cuando la pregunta lo requiere. Esto ya minimiza el consumo sin que haga falta ningún cambio.
- La memoria de cuenta (Nivel 1) ya sigue el mismo patrón: solo se lee el archivo si el listado sugiere que es relevante.
- Conclusión: **el consumo de contexto de esta arquitectura ya es bajo por diseño del propio producto** — el trabajo que falta es de contenido (crear el Bootstrap, mantenerlo corto) más que de mecanismo.

---

## 7. Por qué el Bootstrap no se crea en este mismo turno

Aunque el diseño ya está claro, crear el documento real es una pieza de trabajo aparte (con su propia comprobación: que quede corto, que no duplique nada, que enlace bien al resto). Siguiendo la instrucción de esta fase de auditar antes de implementar, se deja como una pieza más del roadmap (ver índice de Fase 5), no como parte de esta auditoría.

---

## 8. Respuestas directas A-J

**A. ¿Es recomendable esta arquitectura?** Sí. Además, gran parte de los mecanismos que hacen falta (Proyecto con documentos + carga automática al adjuntar un chat) **ya existen y ya funcionan hoy**, comprobado en esta misma sesión. Lo que falta es contenido (el Bootstrap en sí) y una pieza de mantenimiento (mantener sincronizado el nivel de memoria de cuenta, con la limitación real descrita en 1.1).

**B. ¿Qué mecanismo real usarías?** Documentos de Proyecto para Bootstrap + documentación extensa (Nivel 2 y 3); memoria de cuenta para el reconocimiento mínimo (Nivel 1); `estado.json` del PC + espejo condensado en Proyecto para estado vivo (Nivel 4). No hay ningún mecanismo de "instrucciones generales" al que pueda escribir yo mismo.

**C. ¿Qué en Nivel 1 (memoria de cuenta)?** Solo reconocimiento: qué es Nexo, dónde está la información real, y la regla de no inventar el estado. Nada de arquitectura ni decisiones.

**D. ¿Qué en el Bootstrap?** Ver sección 3.

**E. ¿Qué solo en Proyecto?** Toda la documentación de fases (FASE1-5), manuales, historial, incidencias, roadmap detallado, tareas — como ya está.

**F. ¿Qué en estado vivo?** `estado.json` real en el PC (fuente de verdad) + espejo condensado en un documento de Proyecto para cuando no hay PC enlazado.

**G. ¿Cómo se resuelve la autoridad?** Ver sección 4: conversación actual > estado vivo > Bootstrap > documentación de proyecto vigente > historial, con la regla de que cada fase debe señalar explícitamente qué corrige de la anterior.

**H. ¿Cómo se evita la duplicación?** El Bootstrap indexa, no copia; el estado vivo tiene una sola fuente real y un único espejo condensado (no una copia completa); las fases antiguas no se reescriben, se marcan como superadas en el índice más reciente.

**I. ¿Cómo se minimiza el consumo?** Ya es bajo por cómo funciona el producto (carga bajo demanda); mantener el Bootstrap corto es la única disciplina adicional necesaria.

**J. ¿Puede un chat nuevo entrar en modo Nexo sin pegar un prompt enorme?** **Sí, si Damián adjunta el chat nuevo al Proyecto NEXO al crearlo** — eso ya activa automáticamente el acceso a documentos y (en cuanto exista) al Bootstrap, sin pegar nada. Si el chat **no** está adjunto al Proyecto, el único reconocimiento disponible es la entrada de memoria de cuenta (ya existe, pero hoy desactualizada) — suficiente para que Claude sepa "esto es Nexo, hay que consultar el Proyecto o el PC", pero no para tener el contenido completo sin que Damián dé el paso de adjuntar el Proyecto o abrir la sesión correspondiente. Esta limitación es del producto, no evitable por diseño nuestro.

---

## Conclusión: ¿cambia esto alguna decisión arquitectónica de la Fase 4?

**No.** Esta auditoría añade una capa "de fuera hacia dentro" (cómo Claude, como uno de los modelos de la capa B, entra en contexto de Nexo) que es ortogonal a las 4 capas internas de Nexo (Runtime/Modelos/Tools/Proveedores) definidas en la Fase 4. No cambia el orden del roadmap por dependencias ni invalida ninguna pieza. Ver el índice de esta fase para el detalle de "qué cambia y qué no".
