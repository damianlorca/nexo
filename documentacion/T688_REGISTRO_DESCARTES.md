# T688 · Registro de descartes (épica T686)

Estado: piezas 1-4 HECHAS Y TESTEADAS (05/10: tests/test_t688_descartes.py, tests/test_t688_piezas_2_4.py,
interfaz/tests/test_t688_descartadas_web.py).

## El problema
Caso real 04/10: Damián volvió a pedir Blkit (T178), kokonutui (T179), Manus (T180), Fast-jev (T289) y Colibri
(T108). Los cinco ya estaban DESCARTADOS con motivo y nada se lo avisó. Un descarte bien hecho se pierde si
nadie lo consulta al re-proponer; y un descarte mal etiquetado (borrador malo contado como idea mala) pierde una
idea que nunca se juzgó (ver `nucleo/auditoria_cierres.py`, T687).

## Qué cuenta como descarte
Solo lo descartado por una razón de **idea**, con motivo:

| causa | de dónde sale |
|---|---|
| `resultado` | investigación con RESULTADO DESCARTAR (T674) |
| `idea` | propuesta "descartada por Claude al aprobar el borrador" |
| `superado` | el trabajo se hizo por otra vía |

Quedan fuera: lo descartado por **borrador malo** (la idea no se juzgó), lo descartado sin motivo (va a
"revisar a mano" de T687), lo fundido (la idea sigue viva en otra tarea) y los lotes de turno.

## Piezas
1. **HECHA** `nucleo/descartes.py` + detector de parecidas.
   - `registro()`: id, texto, causa, motivo, quién, cuándo, informe.
   - `buscar(texto, registro)`: sin IA. "Mismo nombre" (lo que queda al quitar verbos de encargo: "Investigar
     Blkit" → `blkit`; hace falta un nombre distintivo: 2+ palabras o una de 5+ letras) o "misma idea" (Jaccard
     de raíces, el de `freno.parecido`).
   - `freno.pares_semanticos` (T435, bge-m3 local, coste 0) compara además cada propuesta abierta contra el
     registro y escribe la sección "Propuesta ~ DESCARTADO" con el **motivo anterior**. Sigue siendo SOLO
     informe: el tribunal o Damián deciden "el descarte sigue valiendo" o "revalorar".
2. **HECHA** Panel "Descartadas (con motivo)" del Centro (`/centro/descartadas?causa=`): qué, causa, motivo,
   quién, cuándo e informe; filtrable por causa, lo más reciente primero (máximo 200). `descartes.vista()`; solo lee.
3. **HECHA** Aviso en la entrada (`descartes.avisar`, léxico; los embeddings siguen en el informe del freno):
   - orden de Damián (`nucleo/ordenes.py`): nota + etiqueta `aviso:descartado_antes` y el motivo anterior en la
     respuesta ("Ya se descartó algo parecido: ...");
   - propuestas nuevas de un borrador (`revision.registrar_borrador`): nota + etiqueta en cada una;
   - candidatos del vigía (`vigia.crear_lote` / `texto_lote`): nota en el lote y "YA DESCARTADO ANTES: Txxx (motivo)"
     junto al candidato en el texto que lee la IA.
   No bloquea nunca; si el aviso falla, la entrada se registra igual (solo queda un warning en el log).
4. **HECHA** Guardia de cierre en `tareas.actualizar` (autorizada por Damián 05/10: no es blindado) para
   `cat:propuesta`: descartar exige `causa=` (idea, borrador, superado, sustituida, fundida, archivada, duplicada) y
   `motivo=` de 15+ caracteres, guardados en el campo `descarte`; una propuesta SIN aprobar (estado `propuesta`) no
   se cierra hecha: primero el veredicto la convierte en tarea de implementación (estado pendiente +
   `propuesta:aprobada`), que se cierra y se verifica como cualquier otra. Error `T.CierrePropuesta` (hereda de
   `RevisionPendiente`: web, chat y bot ya la capturan). En el chat: "descártala porque ...". Lo que hoy hace el
   código: `revision.veredicto` (APROBADO→idea, DESCARTADO/REHACER→borrador, SUPERADO→superado), la revisión
   parcial (idea), la sustitución de borrador (sustituida); el filtro F0 archiva por su cuenta (no pasa por aquí).

## Límites conocidos
- "Mismo nombre" falla con erratas (Colibri ≠ "calibri project" en T108, que además es una tarea compuesta):
  eso lo cubren los embeddings, no el léxico.
- `buscar` no mira lo archivado por el filtro F0 (`archivada:filtro`): tiene su propio registro recuperable.
