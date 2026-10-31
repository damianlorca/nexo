# I.13 NEXO_HUMAN_INTERFACE

## Canal real: Telegram, vía `canal/bot.py` + `canal/buzon.py`

- **Comandos**: `/start`, `/estado` (resumen legible, no JSON crudo), `/uso [dias]`, `/ahora [texto]`, `/imagen <texto>`, `/tarea <titulo>`, `/tareas [tuyas]`, `/hecha <id> [nota]`.
- **Texto libre**: si responde a una pregunta abierta de Nexo, se recoge como respuesta; si no, Qwen manda una lectura rápida (categoría/urgencia/resumen) sin decidir nada por su cuenta.
- **Avisos** (`buzon.avisar`): con o sin sonido (`silencioso=True` para no despertar de madrugada salvo urgencia real).
- **Preguntas con botones** (`buzon.preguntar`): con opciones, o en texto libre si no se dan opciones.
- **Fotos/archivos** (`buzon.enviar_foto`/`enviar_archivo`): mismo mecanismo de archivo JSON en `canal/salida/`.

## Prueba en vivo de esta misma auditoría (12/09)

Damián mandó un mensaje de prueba por Telegram preguntando literalmente si Nexo podía contestar "en cualquier momento", no solo en el turno de las 23:00. Se le contestó en el mismo turno de auditoría (vía `buzon.avisar`, sin gastar un disparo de Rutina porque esta sesión ya estaba activa). Matiz importante para no prometer de más: esto demuestra que UNA SESIÓN YA ACTIVA de Claude puede leer y contestar en cualquier momento — no demuestra que se pueda DESPERTAR una sesión nueva instantáneamente cuando no hay ninguna activa (para eso está `/ahora` vía Routines Fire, con la latencia de minutos que ya se conoce).

## Regla de seguridad (repetida aquí porque es la más importante de todo el documento)

Nunca pedir a Damián una contraseña, token o código por este canal. Todas las credenciales se introducen directamente en el sitio real. Ver `05_DAMIAN_TASKS.md`.

## Lo que falta

Confirmación de entrega (hoy `canal/salida/*.json` se renombra a `.enviado`, pero no hay reintento automático si Telegram rechaza un envío puntual — no verificado en detalle esta auditoría, candidato a revisión futura).
