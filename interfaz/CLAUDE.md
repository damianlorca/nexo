# Interfaz de NEXO — reglas para Claude Code

## Qué es
Web local de control de NEXO (agente personal multi-IA, Windows, local-first). Un solo usuario (Damián).
Vive en `interfaz/` dentro del repo `agente` e **importa el core**: `nucleo.ordenes`, `nucleo.tareas`,
`proveedores`, `nucleo.parada`, `nucleo.uso_proveedores`, `nucleo.enfriamiento`. **NO reimplementes esa lógica;
úsala.** La spec del MVP está en `interfaz/SPEC.md` — léela entera antes de empezar.

## Stack FIJADO (no lo cambies, no inventes otro)
FastAPI + SSE (EventSourceResponse o sse-starlette) + HTMX + Alpine.js servidos por el propio FastAPI.
Sin bundler, sin Node, sin React. CSS propio con tokens (claro/oscuro). NO añadas dependencias sin decirlo y
sin fijar versión; **no inventes paquetes**: verifica que existen antes de usarlos.

## Cómo se arranca / prueba (Windows)
- Python del venv: `.venv\Scripts\python.exe` (NO el del sistema).
- Arrancar: `.venv\Scripts\python.exe -m uvicorn interfaz.app:app --host 127.0.0.1 --port 8765` (8765 es el
  puerto definitivo). En producción la arranca y vigila `interfaz/vigia.py` (Tarea Programada "NEXO interfaz");
  parar a propósito: `interfaz\scripts\parar_interfaz.bat`, volver: `seguir_interfaz.bat`.
- Probar: `pytest interfaz/` (tests de endpoints) + `curl` al endpoint SSE y a los POST.
- Autoarranque de producción: Tarea Programada al iniciar sesión del usuario (NO servicio/NSSM: NEXO usa la GUI).

## Reglas de producto (resumen de SPEC.md)
- Command-center, NO un chat. Pantallas MVP: Command Center, Órdenes, Tareas, Proveedores, Logs. PARADA siempre visible.
- Estados de negocio con nombre propio; `loading` NUNCA esconde un estado de negocio; color no como única señal.
- PARADA: doble confirmación; POST; refleja el estado real.
- Seguridad: token por arranque + cookie sesión HttpOnly/SameSite=Strict; CSRF en TODOS los POST (incl. PARADA);
  CSP estricta; CORS denegado; solo `127.0.0.1`; nada de secretos en logs.
- Realtime: eventos con `id` + `Last-Event-ID` + replay; banner "conexión perdida"; reconciliar tras reconexión;
  nada de optimistic update en acciones de autoridad.
- Cada vista: loading/empty/error; accesible por teclado (WCAG 2.2 AA, 4.1.3); responsive; tema claro/oscuro.

## Método (obligatorio)
1. Lee `interfaz/SPEC.md`, este archivo y los módulos del core que vas a usar (la v1, `interfaz_local.py`,
   está archivada en `_archivo/interfaz_v1/`).
2. Pregunta TODAS las dudas (política de OK absoluto de entendimiento) ANTES de escribir código.
3. PROPÓN estructura de archivos + plan por incrementos y espera OK.
4. Incrementos pequeños, pocos ficheros por vez, commit por incremento verde.
5. Verifica con EVIDENCIA (tests + curl + captura), no con "hecho". `/code-review` contra SPEC.md al cerrar cada pieza.
6. Usa primero las skills nativas (`/debug`, `/code-review`, `/verify`, `/run-skill-generator`) antes de instalar externas.

## Qué NO tocar
- El core (`nucleo/`, `proveedores.py`) salvo que la tarea lo pida explícitamente y lo apruebe Damián.
- Los blindados (`nucleo/permisos.py`, `nucleo/instancia.py`, `nucleo/config.py`, `manos/*`): NUNCA sin diff aprobado.
- `secretos.toml`: jamás leerlo ni volcarlo.

## Procesos
- Nunca matar procesos por patrón ni por nombre: solo el PID exacto que lanzaste, comprobando antes que su
  línea de comando es exactamente la que lanzaste (regla del CLAUDE.md raíz).

## Regla de borrado
- En código versionado vale `git rm`: el historial de git es el archivo.
- Los ficheros y datos NO versionados se archivan en `_archivo/` y no se borran.

## Ahorro de tokens (cumplir siempre)
- Probar en el navegador solo al final de cada bloque (tras el incremento 9).
- Durante un incremento, ejecutar solo los tests del módulo tocado; la suite completa, una vez antes del commit.
- `/code-review` solo por bloques.
- Usar Graft para buscar código en vez de leer archivos enteros.
- No releer archivos que no hayan cambiado.
- Resúmenes finales de 10 líneas como máximo: qué hiciste, tests, commit y qué necesitas de Damián.
