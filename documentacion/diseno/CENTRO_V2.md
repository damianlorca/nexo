# Centro v2: la vista para Damián (T230, paso 5 del modo foco)

Aprobado por Damián el 18/10 a las 12:43 ("me vale, aplícalo"). Maqueta (ordenador y móvil) en el canvas de claude.ai
`https://claude.ai/artifact/VCj9yNxZsjXrEYs6MRXUS8`; copia del artboard de ordenador en `CENTRO_V2_maqueta.dc.html`
(misma carpeta; es HTML de maqueta, solo para ver forma y textos; NO se copia tal cual a la web).

Parte del Centro actual (opción A, 12/10: frase + Te toca + En marcha + Hecho hoy + Radares). No es un rediseño:
son cuatro cambios sobre lo que ya hay. Colores y tipografía: los de `interfaz/estatico/nexo.css` (sin cambios).

## Distribución
- Ordenador: arriba saludo + frase + "Tu última visita: hoy a las 00:25". Debajo, dos columnas (3fr | 2fr):
  izquierda **Te toca** y **Hecho desde tu última visita**; derecha **En marcha** y **Avisos**; al final la línea
  "El texto pensado para las IAs... está detrás de cada «Abrir» y en Más → Detalle técnico".
- Móvil (≤860 px): una columna en este orden: Te toca, Hecho, En marcha, Avisos. Botones ≥48 px de alto.

## 1. Te toca
- Las decisiones (permiso ámbar, R1, R2, chat, tribunal) en tarjeta con: chip llano ("Pide permiso"), plazo en
  palabras ("Si no dices nada, caduca mañana a las 12:22"), título que diga QUÉ se hace de verdad, una frase de quién
  lo pide y por qué pide permiso, y los botones de decidir EN la tarjeta (Aprobar / Denegar / Ver el cambio para
  ámbar; los mismos endpoints que ya usa Bandejas: `/ambar/decidir`, `/riesgo/decidir`, `/tribunal/decidir`).
- Bug a arreglar a la vez: `revisor.explicar` describió un `git add ... ; git commit ...` como "Aplicar un parche".
  Un commit es "Guardar en el historial (git) un cambio"; un `git apply` sí es aplicar un parche.
  "Lo pide: Una sesión de Claude (el coordinador u otra) que usa las «manos» de NEXO desde fuera" → "Lo pide Claude".
- Debajo, **Tus tareas**: filas de una línea (título llano + "Abrir"), sin el detalle largo. El título llano además
  quita el prefijo "Para Damian:" y el contador final "(5)". Si ninguna tiene fecha límite, la frase de arriba lo dice
  ("ninguna con prisa"); si alguna la tiene, sale primero con la fecha.

## 2. Hecho desde tu última visita (sustituye a "Hecho hoy"; absorbe T319 Novedades)
- "Última visita" = la anterior carga del Centro separada de la actual por más de 30 min (para que refrescar no la
  mueva). Se guarda en `memoria/interfaz_visita.json` (`anterior`, `actual`). Sin dato: las últimas 24 h.
- Agrupado por lo que cambia para Damián: tareas cerradas del mismo commit o de la misma épica/tema salen como un
  grupo ("Imágenes (ComfyUI) más seguras · 4 arreglos"). Máximo 6 grupos y "Ver las N".
- Cada línea: frase corta en llano (qué cambia para él) + una segunda frase opcional + "✓ Probado" si
  `estado_real` es HECHO Y TESTEADO. Si una cierre deja algo que él puede usar ya, sale "Nuevo para ti" y la frase
  dice dónde probarlo.
- De dónde sale la frase: campo nuevo opcional `cierre.para_damian` (frase llana) y `cierre.novedad` (bool), que
  rellena quien cierra (Claude/Code). Si falta, se genera con Qwen local (qwen2.5:7b, num_ctx 4096, num_predict 80)
  a partir de título + objetivo + evidencia y se guarda en `tareas_detalle/<id>.json` (nunca pisa el detalle). Si
  Qwen no está, se usa `llano(titulo)` cortado por palabra, nunca a media palabra.

## 3. En marcha
- Igual que ahora, en tres líneas: Ahora / Después · hora / En cola. El nombre del turno en llano
  ("Revisar los borradores pendientes con tres IAs distintas (si hay alguno)"). Botones "Trabajar ahora" y
  "Controlar los turnos" (el plegable de siempre).

## 4. Avisos (sustituye a la fila de Radares, que están en pausa)
- Solo los avisos que piden una respuesta de Damián, agrupados por tipo. Vacío: "Ninguno te pide nada ahora."
- Los informativos siguen en Detalle técnico; los radares, en /radares y en Detalle técnico.

## Hecho cuando
- Tests nuevos en `interfaz/tests/` para: título llano sin prefijos, agrupado de hechas, última visita (refresco <30
  min no la mueve), descripción de commit vs apply en `revisor.explicar`, avisos solo con respuesta pendiente.
- Suite completa en verde. Captura del Centro en ordenador y en móvil (390 px) en `documentacion/diseno/`.
- Después: Damián lo usa una semana (segundo "hecho cuando" de T230).

## Estado (18/10, Bloque 14)
HECHO Y TESTEADO el código de las cuatro piezas y T1016 (tests en `interfaz/tests/test_t230_centro_v2.py`, suite completa
en verde). Capturas con datos de demostración (inventados, servidor aparte en otro puerto, nunca la memoria real):
`CENTRO_V2_captura_ordenador.jpg` y `CENTRO_V2_captura_movil_390.jpg`. Falta el segundo «hecho cuando»: que Damián lo use
una semana (por eso T230 sigue abierta).

Cómo está hecho (para quien lo toque):
- Te toca: `presentar.te_toca_llano` (decisiones con `plazo_llano`; «Tus tareas» aparte). Los botones de la tarjeta hacen
  POST a `/ambar/decidir`, `/riesgo/decidir` y `/tribunal/decidir` con `desde=centro` y la respuesta repinta `#te-toca`.
  El chat de una tarea sigue siendo un enlace a su ficha (su OK se da allí).
- Hecho: `presentar.hecho_desde_visita` + `interfaz/hecho_llano.py` (frase: `cierre.para_damian` → detalle guardado →
  Qwen local → título cortado por palabra). Última visita en `memoria/interfaz_visita.json`; cada carga de `/` cuenta,
  una a menos de 30 min de la anterior no la mueve. Agrupa por commit citado en la evidencia, luego épica y luego tema.
  Quien cierra una tarea con Claude/Code puede pasar `cierre={"estado_real", "evidencia", "para_damian": "...", "novedad": True}`.
- En marcha: `presentar.turno_llano` traduce los nombres de las plantillas de `nucleo/turnos.py`; un turno nuevo sin
  traducción sale con su nombre propio (el test avisa si se añade una plantilla sin traducir).
- Avisos: `presentar.avisos_pendientes`, solo tipos de `nucleo/avisos.py` que piden respuesta de Damián
  (`TIPOS_AVISO_RESPUESTA`) de los últimos 3 días; los avisos no llevan «resuelto», así que uno sin atender caduca a los 3 días.
- «Trabajar ahora» en el Centro es un enlace a `/turnos#trabajar` (allí está el formulario con las horas y la confirmación).
