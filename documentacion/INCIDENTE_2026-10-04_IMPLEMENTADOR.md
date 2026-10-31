# Incidente 04/10/2026: el implementador (T669) envió archivos de más y abrió el Chrome personal

Estado: **CERRADO** (arreglos hechos y testeados; ver al final). Fuente: historiales de Aider en
`memoria/implementador/Txxx/aider_*.md` (solo en local) y la revisión de Claude del 04/10.

## Qué pasó

En el primer piloto real de F3 (04/10, 14:02-14:46), Aider se lanzaba con `--yes-always`. Esa opción hace dos cosas
que nadie pidió:

1. **Añade al chat cualquier archivo que el modelo nombre** ("Add file to the chat? y") y lo manda al proveedor.
2. **Acepta "Open URL for more info?"** tras cada error de cuota o de modelo y abre la URL con el navegador por
   defecto: unas **30 pestañas** (24 "Open URL" + 6 "Open documentation url") en el **Chrome personal** de Damián
   (consola de Groq, límites de la API de Gemini, documentación de Aider).

## Qué salió y a quién

Los archivos de la lista privada de Damián (`memoria/becas.md`, `memoria/historial_telegram.json`, `canal/entrada/`,
`canal/estado_bot.json`, `secretos.toml`, `.env`, `registros/`, `chrome-perfil/`) **no salieron**: no estaban en el
disco del worktree (sparse-checkout) y `.aiderignore` los tapaba. Ninguna clave salió.

| Tareas | Archivos añadidos al chat | Proveedor (modelo) | ¿Llegó a procesarse? |
|---|---|---|---|
| T377, T378, T381 | `nucleo/permisos.py` (blindado), `docs/ARRANQUE.md` | Groq (gpt-oss-120b), Google (gemini-3.6-flash), NVIDIA (nemotron-3-super) | **Sí**: hay respuestas con 7-12 k tokens enviados |
| T379 | `herramientas_nube/publicar_nube.py`, `canal/bot.py`, `nucleo/instancia.py` (blindado), `prueba_instancia.py`, `docs/ARRANQUE.md`, `docs/TELEGRAM.md`, `nucleo/permisos.py` | Groq (gpt-oss-120b), Google (gemini-3.6-flash) | En parte: Groq cortó la grande por tamaño; Gemini procesó ~10 k tokens |
| T461, T462, T463 | `memoria/tareas.json`, `memoria/historial.md`, `memoria/altavoz.md`, `memoria/auditoria.md`, `memoria/claude_organizacion.md`, `memoria/cola.md`, `documentacion/B_AUDITORIA_REAL.md`, `K_ACCIONES_DAMIAN.md`, `MASTER_REQUIREMENTS_CHECKLIST.md`, `docs/TELEGRAM.md`, `docs/ARRANQUE.md` | Groq (gpt-oss-120b y qwen3.8-27b), Google (gemini-3.6-flash) | **Enviado pero rechazado**: ~540 k tokens; Groq respondió "reduce the length" y Gemini, límite de cuota (429). No hubo respuesta sobre ese contenido |

Lo procesado es código del repo (sin secretos; el mismo código va al espejo de GitHub, con los tokens sustituidos). Lo
de `memoria/` (tareas, historial narrativo, organización) llegó a Groq y a Google aunque lo rechazaran por tamaño:
con cuentas gratuitas, sus condiciones pueden permitir guardar o usar lo enviado.

## Arreglos (todos con test en `tests/test_t669_implementador.py`)

- **Lista blanca por ejecución** (`aiderignore_tarea`): Aider solo ve los archivos de la tarea; lo privado, lo R3
  (blindados, `.claude/`, `CLAUDE.md`), `memoria/` y `contexto/` quedan ignorados al final, siempre.
- **Nada de `memoria/` ni del vault (`contexto/`)**, ni rutas fuera del repo, aunque la tarea lo pida
  (`no_enviable`): ni como archivo, ni en solo lectura, ni en el prompt del revisor de la puerta; el auditor rechaza
  cualquier diff que los toque.
- **Si Aider cambia un archivo que no se le dio**, el intento falla (fuera de alcance).
- **Nunca un navegador**: el proceso de Aider carga `nucleo/sin_navegador/sitecustomize.py`, que sustituye
  `webbrowser` por una función que solo anota la URL en `memoria/implementador/urls_bloqueadas.log`; además
  `BROWSER=nexo-sin-navegador`, `--no-show-model-warnings`, `--no-check-update` y `--no-show-release-notes`.
  Prueba real: Aider intentó abrir `https://aider.chat/docs/llms/warnings.html`, quedó en el registro y Chrome
  siguió con los mismos procesos.
- Comprobado: el código de NEXO no abre el navegador en ningún sitio (solo `nucleo/guardia_python.py` lo menciona,
  para bloquearlo).

## Lección

Una opción de "sí a todo" en una herramienta de terceros no es neutral: decide por ti cosas que no son la tarea.
Antes de usar una herramienta externa en modo desatendido hay que leer qué preguntas responde ese "sí".
