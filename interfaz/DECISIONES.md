# Decisiones ya tomadas (pre-respuestas para Claude Code)

Para que la fase de "OK absoluto de entendimiento" sea rápida: aquí van respuestas a las dudas previsibles.
Si algo no encaja al implementar, proponlo a Damián antes de cambiarlo.

## Estructura de archivos (propuesta base)
- Paquete `interfaz/`: `app.py` (crea la app FastAPI y monta todo), `rutas/` (un módulo por pantalla:
  centro, ordenes, tareas, proveedores, logs, parada, sse), `plantillas/` (Jinja2 + HTMX), `estatico/`
  (CSS con tokens, un poco de JS Alpine), `seguridad.py` (token, cookie de sesión, CSRF), `eventos.py`
  (bus SSE + buffer), `tests/`.
- **Reemplaza a `interfaz_local.py`**: cuando la nueva funcione, archivar la v1 (a `_archivo/`), no borrarla.
  **Hecho el 25/09**: v1 en `_archivo/interfaz_v1/` (fuera de git; el historial la conserva). Puerto 8765 definitivo.

## Servidor
- Puerto **8765** (como la v1). Host **127.0.0.1** solamente.
- Arranque: `.venv\Scripts\python.exe -m uvicorn interfaz.app:app --host 127.0.0.1 --port 8765`.

## Autenticación (un solo usuario, local)
- **Token por arranque** como la v1 (se genera al arrancar y se guarda en `memoria/` / se imprime en consola;
  reusa el patrón que tenía la v1, `interfaz_local.py`). Al validar el token una vez → **cookie de sesión**
  HttpOnly + SameSite=Strict (Secure cuando haya HTTPS por Tailscale). No arrastrar el token en cada request.
- **CSRF** en todos los POST con token por-sesión inyectado en las peticiones HTMX (`hx-headers`).

## Realtime / SSE (sin tocar el core)
- La web observa cambios de ficheros que el core ya escribe: `mtime` de `memoria/tareas.json` y de la bandera
  `memoria/PARADA_NEXO`, y las líneas nuevas de `registros/*.jsonl`. Con eso **emite eventos SSE** (tarea
  cambiada, parada on/off, nueva línea de log). Buffer de eventos en memoria con `id` incremental para
  soportar `Last-Event-ID` y replay (un solo usuario, suficiente).
- Extensión `sse` de HTMX para pintar sin recargar. Banner "conexión perdida" si el stream cae.

## Órdenes
- POST `/orden` → `nucleo.ordenes.procesar(texto, canal="web", trabajar=...)`.
  - **Instantánea**: `trabajar=True` (triaja y, si es delegable, hace borrador ya).
  - **Bloque para más tarde**: `trabajar=False` (solo la da de alta y la triaja; no la trabaja).
- Mostrar el dict de respuesta (tarea, categoría, estado, veredicto, enlace al borrador si lo hay).

## Tareas
- Lista/tablero desde `nucleo.tareas.cargar()/ordenadas()/listar()`. Filtros por estado/depende/etiqueta.
- Acciones: crear (`anadir`), anotar (`anotar`), completar (`completar`), verificar (`verificar`),
  editar campos (`actualizar`). Mostrar `estado_real` y `testeado`.
- **Estados en el MVP**: se muestran los reales del core (pendiente/en_curso/hecha/bloqueada). La taxonomía
  canónica de 11 estados es para cuando el core tenga "runs"/ejecuciones (siguiente hito); no forzarla ahora.

## Proveedores
- Salud: instanciar cada proveedor de `proveedores` y leer `.estado()`; enfriamiento con
  `nucleo.enfriamiento.enfriado(nombre)`. Uso: `nucleo.uso_proveedores.resumen(dias)`.

## PARADA
- POST `/parada` → `nucleo.parada.activar(motivo, "damian")`; POST `/seguir` → `desactivar()`. Doble
  confirmación en la UI. Estado real desde `parada.activa()`. Botón visible en todas las pantallas.

## Tema y accesibilidad
- Tema por defecto: seguir el sistema (`prefers-color-scheme`), con conmutador manual. Tokens CSS en `:root`.
- Cada vista con loading/empty/error; foco de teclado; `aria-live` para cambios de estado (WCAG 2.2 AA 4.1.3).

## Autoarranque (producción, tras el MVP funcional)
- Script que registra una **Tarea Programada** "NEXO interfaz" al iniciar sesión del usuario que lanza uvicorn
  con `pythonw`. Watchdog externo (proceso aparte o segunda tarea) que comprueba `/salud` y reinicia; respeta
  un flag de "parada solicitada" (si Damián paró a propósito, no relevantar).
- **Hecho (incremento 9)**: la tarea lanza el vigía (`interfaz/vigia.py`), que arranca la web y la relanza.
  "Parada solicitada" = `memoria/INTERFAZ_DETENIDA` (`parar_interfaz.bat` / `seguir_interfaz.bat`).
  **La PARADA de NEXO NO impide relanzar la web** (decisión de Damián, 25/09): la web es donde se pulsa
  "Seguir" y con PARADA ya bloquea las órdenes. Si otro programa ocupa el puerto (la v1), no lanza nada.
  Registrar la tarea con disparador "al iniciar sesión" puede pedir administrador una vez (ver 11/09 en
  `canal/vigilante.py`); la tarea corre después como Damián, sin elevar.

## Tests
- `pytest` con `fastapi.testclient.TestClient`: órdenes (mockeando `ordenes.procesar`), tareas (contra un
  `tareas.json` de prueba), parada (activar/desactivar), proveedores (mock de `.estado()`), y CSRF/сookie.
- Comprobación manual: `curl` al endpoint SSE + captura de cada pantalla.

## Qué NO hacer en el MVP
- No construir la bandeja de aprobaciones HITL persistente (T077) ni el modelo de Run/Evidence: solo **dejar
  diseñado su contrato** (ver `../contexto/proyectos/nexo/contrato-datos-nexo.md`). No PWA/Push/Tailscale/voz aún.

## Estado final del MVP (25/09/2026): CERRADO
Detalle por pieza, con commits y evidencia, en `SPEC.md` → "ESTADO FINAL DEL MVP". Decisiones que se tomaron
al implementar y que el siguiente hito debe respetar:
- **Core tocado solo con diff aprobado**: `nucleo/ordenes.py` (ENCOLADA con `trabajar=False`, 694dc51) y
  `nucleo/uso_proveedores.totales(dias)` (datos para la web; `resumen()` da el mismo texto a Telegram, 2aeaa64).
- **Secretos**: `interfaz/ocultar.py` se aplica a toda línea de registro antes de que salga hacia el navegador
  (pantalla de Logs, eventos SSE y trazas del Centro), ocultando siempre antes de recortar.
- **Vigía**: la PARADA de NEXO no impide relanzar la web; solo la impide `memoria/INTERFAZ_DETENIDA`. Solo
  mata el PID que lanzó, y solo si su línea de comando es exactamente la de la web.
- **Procesos** (regla del CLAUDE.md raíz): nunca matar por patrón ni por nombre.
- **Visto el 25/09**: el disparador "al iniciar sesión" arrancó el vigía solo en un inicio de sesión real
  (arranque del PC 16:00:53, vigía en marcha 16:01:38 y web levantada 16:01:49).

## Siguiente hito (PLANIFICADO, nada empezado)
Por orden. Cada uno empieza con el método de siempre: leer, dudas, propuesta y OK de Damián.
1. **Bandeja de aprobaciones HITL persistente (T077)**: primero la cola en el core (entidad Approval con estados
   proposed → awaiting_approval → approved/denied/edited → executing → completed/failed) y después su pantalla.
   Punto de partida: detallar el contrato de Approval, ahora solo esbozado en `contrato-datos-nexo.md`.
2. **Run/Ejecución y Evidence estructurada** (traza tipo Langfuse: run_id, actor, tool, input, output, status,
   duración): sustituiría a la evidencia en texto de las notas y a la lectura cruda de `registros/*.jsonl`.
   Con Runs, las tareas podrán pasar a la taxonomía canónica de 11 estados.
3. **PWA + Web Push + Tailscale Serve** (acceso desde el móvil). Con HTTPS, la cookie de sesión pasa a `Secure`.
Fuera también, sin fecha: voz, memoria/búsqueda del vault y revisor automático de acciones ámbar.

## Hito móvil (PWA + push + Tailscale Serve) — decisiones del 25/09/2026
Spec: `HITO_MOVIL.md`. Se va rellenando por incrementos.
- **Serve persistente**: `scripts\activar_movil.bat` (`tailscale serve --bg --https=443 http://127.0.0.1:8765`),
  una vez; Tailscale lo recuerda. `quitar_movil.bat` quita solo el 443. El vigía NO lo pone ni lo quita: cada ~5 min
  avisa en su log si falta o si hay un funnel. Nunca `funnel`.
- **Host y dueño** se leen de `tailscale status --json` al arrancar (`interfaz/tailnet.py`). Sin Tailscale en marcha
  o sin certificado, la web queda solo en local. `NEXO_TAILNET_DUENO` cambia el login aceptado.
- **Qué hace Serve** (comprobado con un eco): conserva el Host, conecta desde 127.0.0.1, añade `X-Forwarded-Proto:
  https` y `Tailscale-User-Login`, y sustituye un login falsificado por el real. uvicorn aplica proxy-headers por
  defecto (reescribe client/scheme): `por_serve()` acepta las dos formas sin cambiar la línea de arranque que el
  vigía reconoce.
- **Entrada por identidad**: automática si llega por Serve con el login del dueño (sesión `via="tailnet"`, cookie
  Secure). Otro login → 403. "Salir" oculto en esas sesiones (se volvería a entrar al recargar). En el PC, token.
- **Riesgo aceptado por Damián**: un programa del propio PC podría conectar a 127.0.0.1:8765 fingiendo ser Serve.
  Es el mismo nivel que hoy (ese programa ya podría leer `memoria/interfaz_token.txt`). Desde fuera del PC no se
  puede: la web solo escucha en 127.0.0.1 y Serve reescribe la cabecera.
- **Notificaciones**: tipo + id + frase corta (título de la tarea, pasada por `ocultar.py`) y el motivo de la
  PARADA, visibles en la pantalla de bloqueo (OK de Damián). Anti-spam: máx. 1 push por orden y 1 resumen por
  turno nocturno; si llegan más de 5 en un minuto, se agrupan.
- **Refresco de la tailnet** (fallo real del 26/09): la web arranca al iniciar sesión, a veces antes de que
  Tailscale tenga el usuario cargado; se quedaba sin dueño y el móvil recibía 401. Ahora `app.py` vuelve a
  preguntar en segundo plano (60 s si falta algo, 10 min si no) y el log dice `tailnet: host=…, dueno=si/NO`.
- **Tablas apilables** también en Tareas y en el historial de Órdenes (a 375 px se cortaban).
- **El navegador del panel de Claude Code** no sirve para probar la dirección de la tailnet (bloquea sus
  subrecursos) ni service workers/notificaciones: la prueba real de la PWA y el push es en el móvil.

## Pestaña Grafo (T251, 28/09/2026)
- **Librería**: vis-network 9.1.6, la misma que fija Graphify en su `graph.html` (allí desde unpkg; aquí
  vendorizada con SHA-256 en `estatico/vendor/VERSIONES.txt`). Licencia Apache-2.0/MIT.
- **CSP**: su build standalone mete 7 `<style>`. Se permiten SOLO esos textos por hash (`seguridad.ESTILOS_VIS_NETWORK`),
  más el hash del `<style>` vacío (vis lo inserta vacío y Chrome lo comprueba así; visto en la prueba real).
  Nunca `unsafe-inline`. `test_grafo.py` recalcula los hashes desde el fichero y falla si cambian.
- **Datos**: `interfaz/grafo.py` (solo lectura) da node-link de NetworkX, el formato de `graph.json` de Graphify
  (T250). Aristas solo de relaciones guardadas (T252); un `bloqueada_por` en texto libre no crea arista.
- **Rendimiento**: `/grafo/datos` se pide una vez; se coloca con física (forceAtlas2) y después la física se apaga:
  filtrar solo oculta/muestra (~30 ms con 428 nodos). Filtros en la URL; `?nodo=T150` abre su ficha.
- **Sueltos**: por defecto se ocultan los que no tienen NINGUNA relación guardada (196 de 428 el 28/09).
