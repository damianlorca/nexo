# Canal móvil — crear el bot

Cinco minutos, gratis, sin tarjeta y sin tienda de aplicaciones.

## 1. Crear el bot

En Telegram, en tu móvil:

1. Busca **@BotFather** (el que tiene la marca de verificado).
2. Escríbele `/newbot`.
3. Te pide un nombre visible: **Nexo**.
4. Te pide un usuario, tiene que acabar en `bot`: **nexo_damian_bot**
   (si está cogido: `nexo_dl_bot` o `nexo_agente_bot`).
5. Te devuelve un **token**, algo como `8123456789:AAH...`.

## 2. Guardar el token

En el PC, copia `secretos.ejemplo.toml` como `secretos.toml` y pega el
token dentro. Ese archivo está en `.gitignore` y no sale de tu equipo.

```toml
[canal]
token_telegram = "8123456789:AAH..."
```

## 3. Arrancar el bot

```powershell
cd C:\Users\damia\Desktop\AI\agente
python canal\bot.py
```

Se queda corriendo. Déjalo.

## 4. Presentarte

En Telegram, abre tu bot y escríbele **`/start`**.

Ahí aprende tu `chat_id` y lo guarda solo. A partir de ese momento el
canal está abierto en los dos sentidos.

## Qué puedes hacer desde el móvil

| Tú haces | Pasa esto |
|---|---|
| `/start` | Abre el canal, aprende quién eres |
| `/estado` | Te devuelve en qué anda el agente ahora mismo |
| Escribir un texto | Si había una pregunta abierta, cuenta como respuesta. Si no, queda como recado |
| Tocar un botón | Respuesta inmediata, sin escribir |

## Qué recibes

- **Avisos** cuando termina algo o hay novedad.
- **Preguntas con botones**: «¿Instalo ComfyUI?» → *Sí* / *No* / *Luego*.
- **Capturas** de lo que está haciendo el equipo.
- **Archivos**: el documento o el gráfico recién hecho.

## Por qué Telegram y no una app propia

Una app propia pide tienda, firma, cuenta de desarrollador y
mantenimiento. Telegram da hoy y gratis lo mismo que pedías: chat en
ambos sentidos, fotos, botones de respuesta y notificación nativa en el
móvil. Si algún día hace falta algo más, el buzón ya está separado del
bot y se le puede enchufar otro canal sin tocar el resto.
