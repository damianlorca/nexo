# SPEC — Interfaz web de NEXO (MVP v1)

Especificación autocontenida para construir la interfaz con Claude Code. Fuente de diseño completa:
vault `especificaciones-interfaz-nexo-v1.md`, `contrato-datos-nexo.md`. Aquí va SOLO el MVP.

## Objetivo
Una web local para que Damián (único usuario) trabaje con NEXO **sin depender de Claude**: escribir órdenes,
ver y controlar el trabajo, y parar. Es un **command-center, NO un chat**.

## Stack FIJADO (no cambiar, no inventar otro)
FastAPI + SSE (EventSourceResponse nativo o sse-starlette) + HTMX + Alpine.js, servido por el propio FastAPI.
Sin bundler, sin Node, sin React. CSS propio con tokens (claro/oscuro). Vive en `interfaz/` dentro del repo
`agente` e **importa el core** (no reimplementa nada). Reemplaza a la v1 `interfaz_local.py`
(archivada el 25/09 en `_archivo/interfaz_v1/`; la web nueva queda en el puerto 8765 definitivo).

## Core que se usa (contrato real — NO inventar API; ver contrato-datos-nexo.md)
- Órdenes: `nucleo.ordenes.procesar(texto, canal="web", trabajar=True) -> dict` (da de alta tarea, triaja, y si
  es delegable hace borrador). Estados: BORRADOR/SIN_BORRADOR/PARA_DAMIAN/ESCALADO/VACIA.
- Tareas: `nucleo.tareas` → `cargar()`, `listar(estado,depende)`, `ordenadas()`, `buscar()`, `anadir()`,
  `actualizar()`, `anotar()`, `completar()`, `verificar()`, `render_md()`. Campos: id,titulo,detalle,importancia,
  urgencia,dificultad,coste,depende,estado,limite,etiquetas[],bloqueada_por,testeado,notas[],creada,actualizada.
- Proveedores: `proveedores` (Qwen/Gemini/ChatGPT/Claude/GeminiAPI/Groq: `.nombre`,`.disponible()`,`.estado()`);
  uso: `nucleo.uso_proveedores.resumen(dias)`; enfriamiento: `nucleo.enfriamiento.enfriado(nombre)`.
- Parada: `nucleo.parada` → `activa()`, `activar(motivo,quien)`, `desactivar()`, `cierre_pedido()`.
- Logs: leer `registros/*.jsonl` y `memoria/borradores/*.md`.

## Pantallas del MVP (progressive disclosure; nada de volcar todo a la vez)
1. **Command Center** (home): estado global (activo/parado + motivo), resumen de proveedores (salud), nº de
   tareas por estado, últimas acciones. Botón de PARADA siempre visible.
2. **Órdenes**: cuadro de texto para escribir una orden → POST que llama a `ordenes.procesar`. Muestra el
   resultado (tarea creada, categoría, si hizo borrador y su veredicto). Distingue orden **instantánea** vs
   **bloque para más tarde** (misma vía; el bloque solo se triaja y encola).
3. **Tareas**: tablero/lista desde `tareas`, filtrable por estado/depende/etiqueta; ver detalle (notas,
   evidencia); crear/editar/anotar. Mostrar estado real y `testeado`.
4. **Proveedores**: salud de cada uno (disponible/enfriamiento/motivo) + uso a N días (`resumen`).
5. **Logs**: ver en directo (SSE) las líneas nuevas de los registros y los borradores generados.

## Realtime (SSE)
- Un endpoint SSE que emite eventos de cambio (tarea creada/actualizada, parada on/off, nueva línea de log).
- Eventos con `id`; soportar `Last-Event-ID` y **replay** desde un buffer en memoria. HTMX extensión `sse`.
- **Banner de "conexión perdida"** si el SSE cae; reconciliar al reconectar. Nada de optimistic update en PARADA.

## PARADA de emergencia
- Botón visible en todas las pantallas, con **doble confirmación**. POST → `parada.activar(motivo,"damian")`.
  Botón "Seguir" → `parada.desactivar()`. Refleja el estado real (bandera `memoria/PARADA_NEXO`).

## Seguridad (imprescindible en el MVP)
- Token por arranque (como v1) + **cookie de sesión** HttpOnly+Secure+SameSite=Strict tras validar el token.
- **CSRF en TODOS los POST** (incl. órdenes y PARADA) con header vía `hx-headers`.
- **CSP estricta**, `X-Content-Type-Options`, `Referrer-Policy=no-referrer`. **CORS denegado** por defecto.
- Backend escuchando SOLO en `127.0.0.1`. Nada de secretos en logs. Rate-limit en el login/token.

## Estados de UI (obligatorio en cada vista)
loading (skeleton) · empty · error (con reintento) · y los de negocio cuando apliquen (blocked, awaiting…).
`loading` NUNCA para esconder un estado de negocio. Color no como única señal. Accesible por teclado (WCAG 2.2 AA,
4.1.3 status messages: anunciar cambios sin mover el foco). Tema claro/oscuro. Responsive a ancho de móvil.

## Autoarranque y robustez
- **Tarea Programada en la sesión del usuario** al iniciar sesión (NO servicio/NSSM: NEXO usa la GUI). Script de
  registro incluido. Watchdog externo que reinicia si cae y respeta un flag de "parada solicitada" (no relevanta
  tras PARADA intencionada). Healthcheck en `/salud`. Log rotado.

## ESTADO FINAL DEL MVP (25/09/2026): CERRADO
Incrementos 0-9 hechos, con `/code-review` por bloques (1-3, 4-6, 7-9) y sus arreglos. `pytest interfaz/`: 205 passed.
| Pieza | Estado | Evidencia |
|---|---|---|
| Esqueleto seguro (token+cookie+CSRF+CSP+Host/Origin, sin CORS, solo 127.0.0.1) | HECHO Y TESTEADO | 4f7279b, test_seguridad |
| PARADA (doble confirmación, estado real, también la de Telegram) | HECHO Y TESTEADO | 39a01d2, df1233b |
| SSE (id + Last-Event-ID + replay, banner, reconciliar, `logs_perdidos`) | HECHO Y TESTEADO | df1233b, 78ac85f, 47ba8c5 |
| Command Center | HECHO Y TESTEADO | 9145643 |
| Órdenes (instantánea / bloque, resultado por SSE) | HECHO Y TESTEADO | e4ecaff, 694dc51 |
| Tareas (filtros, ficha, crear/editar/anotar/completar/verificar) | HECHO Y TESTEADO | 7d8ea27, c297f79 |
| Proveedores (salud + uso real a 1/7/30 días vía `uso_proveedores.totales`) | HECHO Y TESTEADO | 2aeaa64 |
| Logs (filtros, límite, secretos ocultos también en el SSE, borradores) | HECHO Y TESTEADO | 47ba8c5, 034e541 |
| Vigía (relanza si cae, respeta `parar_interfaz.bat`, no mata PIDs ajenos) | HECHO Y TESTEADO | 1291179, 034e541; prueba real en 8766 |
| Tarea Programada "NEXO interfaz" | HECHO Y TESTEADO al arrancarla a mano (Running, vigía y web vivos en 8765); **el disparador de inicio de sesión queda por ver en un inicio de sesión real** | 25/09 10:45 |
| Navegador: claro, oscuro y 375 px (Centro, Proveedores, Logs en el bloque 7-9) | HECHO Y TESTEADO; las capturas se revisaron en el panel, **no se guardaron como ficheros** | 1291179 |
| v1 `interfaz_local.py` | ARCHIVADA en `_archivo/interfaz_v1/`; 8765 es el puerto definitivo | 034e541 |

## FUERA del MVP (siguiente hito, no ahora)
Estado al cerrar el MVP: todo lo de esta lista está **PLANIFICADO**. Los contratos de Approval, Run y Evidence
están esbozados (entidades y estados) en `contrato-datos-nexo.md`, pero **sin detallar**: detallarlos es el primer paso.
- Bandeja de aprobaciones HITL persistente (T077) con su entidad (proposed→awaiting_approval→…) — requiere
  construir la cola en el core primero. **Diseñar el contrato de Approval, pero no implementarlo en el MVP.**
- Modelo de Run/Ejecución y Evidence estructurada (traza estilo Langfuse) — diseñar el contrato, implementar después.
- PWA + Web Push + Tailscale Serve. Voz. Memoria/búsqueda del vault. Revisor automático de acciones ámbar.

## Definition of Done del MVP
- Las 5 pantallas funcionan contra el core real; órdenes crean tareas y borradores de verdad; PARADA para y
  reanuda de verdad; SSE actualiza sin recargar y avisa si se cae.
- Estados loading/empty/error en cada vista; accesible por teclado; tema claro/oscuro; responsive.
- Seguridad: token+cookie+CSRF+CSP+CORS-denegado; solo localhost; sin secretos en logs.
- Autoarranque por Tarea Programada probado + watchdog que reinicia y respeta la PARADA.
- Tests: pytest de los endpoints (órdenes, tareas, parada, proveedores) + `curl` al SSE; captura de cada pantalla.
- **Verificación con EVIDENCIA** (salida de tests + capturas), no "hecho". `/code-review` contra esta SPEC al cerrar cada pieza.

## Método (obligatorio)
Antes de codear: leer el core y esta SPEC, preguntar dudas (OK absoluto de entendimiento), y PROPONER la
estructura de archivos + plan por incrementos, esperando OK. Incrementos pequeños, commit por incremento verde.
