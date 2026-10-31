# I.5 DAMIAN_TASKS

Cuándo usar cada marcador, y la regla de seguridad que nunca se salta.

## USER_ACTION_REQUIRED

Cuando la siguiente acción es mecánica y solo la puede hacer Damián con acceso físico o a una cuenta que no es de Nexo: pegar un token en `secretos.toml`, entrar en la BIOS, aprobar un `pip install`, cambiar el modelo de su propia Rutina desde su Claude Code. Ver `K_ACCIONES_DAMIAN.md` para la lista viva.

## USER_DECISION_REQUIRED

Cuando hay una elección de diseño o de riesgo entre varias opciones razonables, y ninguna es obviamente correcta: cerrar o no un agujero de permisos (T016), qué vía usar para encender el PC en remoto (T037), qué alcance darle al Model Router primero. Ver `M_DECISIONES_ARQUITECTONICAS_PENDIENTES.md`.

## Regla de seguridad que nunca se salta

**Nunca pedir a Damián que mande una contraseña, token, código 2FA o cualquier credencial por Telegram, chat o cualquier canal que pase por Nexo.** Todas las credenciales las introduce él directamente en el sitio real (BotFather, claude.ai/code/routines, la BIOS, etc.). Si una tarea necesita una credencial, el marcador es `USER_ACTION_REQUIRED` con instrucciones de DÓNDE introducirla él mismo, nunca `envíamela`.

## Formato recomendado de una petición a Damián

Corto, con la acción concreta primero, el motivo después, y sin bloquear el resto del turno esperando su respuesta si no hace falta (seguir con lo que sí se puede hacer mientras tanto).
