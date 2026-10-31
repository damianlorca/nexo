# Hito 2 — NEXO en el móvil (PWA + push) — SPEC

Estado: HECHO Y TESTEADO (26/09) salvo el push de PARADA desde el móvil (sin evidencia en el log). Code-review hecho.
Detalle por pieza al final ("Estado por pieza"). Decisiones: `DECISIONES.md` → "Hito móvil".
Método igual que el MVP: preguntar hasta OK absoluto → proponer plan por incrementos → construir
→ verificar con evidencia → commit. Mismas reglas de interfaz/CLAUDE.md (incluido ahorro de tokens).

## Datos reales del entorno (comprobados 25/09)
- Tailscale 1.102.4 en el PC, estado Running. Nombre del PC en la red: `tu-equipo.tu-tailnet.ts.net`.
- Móvil de Damián: **Android (POCO F7)**, conectado a la misma red Tailscale. Navegador: Chrome.
  → Web Push sin las limitaciones de iOS.
- MagicDNS activo. **Certificados HTTPS: Damián los está activando** en el panel de Tailscale
  (sin eso, `tailscale serve` no puede dar HTTPS). Comprobar con `tailscale status --json` (CertDomains).

## Objetivo
La web del MVP, usable desde el móvil como una app instalada, con notificaciones push. Sin abrir
nada a internet: solo por la red privada de Tailscale.

## Piezas
1. **Exposición**: `tailscale serve` del 127.0.0.1:8765 por HTTPS dentro de la tailnet. La web sigue
   escuchando SOLO en 127.0.0.1. Integrarlo con el autoarranque/vigía (que el serve quede activo; o
   `tailscale serve --bg` persistente) y documentar cómo quitarlo. NUNCA `tailscale funnel` (público).
2. **Host/Origin**: aceptar además el host de la tailnet (leerlo de `tailscale status --json`, no
   hardcodearlo) y su origen https. Cookie de sesión con `Secure` cuando la petición llega por HTTPS.
3. **Entrar desde el móvil sin token**: si la petición llega por Tailscale Serve con la cabecera
   `Tailscale-User-Login` y ese login es el del dueño de la tailnet (configurable; por defecto el
   del propio PC según `tailscale status --json`), crear sesión. Serve elimina esa cabecera si viene
   falsificada; aun así, SOLO aceptarla si la conexión viene del propio Serve (127.0.0.1) y el Host es
   el de la tailnet. En el PC sigue `abrir_nexo.bat` con token.
4. **PWA**: `manifest.webmanifest` (nombre NEXO, iconos 192/512, display standalone, colores del
   tema), service worker (caché del esqueleto + estáticos; pantalla "sin conexión"; NUNCA cachear
   respuestas con datos privados ni el SSE), instalable en Chrome Android.
5. **Push**: claves VAPID generadas una vez y guardadas fuera de git (memoria/ o secretos, no el
   repo); `pywebpush` (verificar que existe y fijar versión); endpoint de suscripción (POST con CSRF);
   almacén de suscripciones; envío desde el bus de eventos para: **orden terminada/error**, **PARADA
   activada/quitada**, **error en el turno nocturno** (si se detecta en logs). Payload SOLO título +
   ruta, sin secretos ni contenido. Pantalla de Ajustes: activar/desactivar y "enviar prueba".
   Gestionar suscripciones caducadas (410) borrándolas.
6. **Móvil usable**: revisar que las 5 pantallas se ven bien a 375-412 px (ya hay tablas apilables).

## Fuera de este hito
Bandeja de aprobaciones HITL (T077), evidencia estructurada, voz, Telegram Mini App (descartada salvo necesidad).

## Definition of Done
- Desde el POCO F7 (4G y wifi): abrir `https://tu-equipo.tu-tailnet.ts.net`, entrar sin token, instalar
  como app, recibir push de "orden terminada" y de "PARADA", y abrir la pantalla correcta al tocarlo.
- Tests de: Host/Origin tailnet, login por identidad (acepta el dueño, rechaza otro login y la cabecera
  falsificada desde fuera de Serve), suscripción con CSRF, envío push (mock), SW sin cachear datos privados.
- /code-review al final del hito. Seguridad revisada: nada expuesto fuera de la tailnet.

## Lo que hace Damián
- Activar HTTPS en el panel de Tailscale (en curso).
- Al final: abrir la dirección en el móvil, "Instalar app" y aceptar notificaciones.

## Estado por pieza (26/09/2026)
| Pieza | Estado | Evidencia / commit |
|---|---|---|
| 1. Exposición (Serve 443, scripts, aviso del vigía) | HECHO Y TESTEADO | 57bdf7d; Serve sobrevivió al reinicio; log del vigía |
| 2. Host/Origin + cookie Secure | HECHO Y TESTEADO | 57bdf7d; curl por Serve: Secure; local: no; Host ajeno 400 |
| 3. Entrar sin token por identidad | HECHO Y TESTEADO | bdc0054 + 78d7b51; POCO F7 entra sin token (log 26/09) |
| 4. PWA (manifest, SW, sin conexión, iconos) | HECHO Y TESTEADO | 28f1a70; instalada en el POCO F7 (Damián, 26/09) |
| 5. Push (VAPID, suscripción, anti-spam, turnos, Ajustes) | HECHO Y TESTEADO (prueba y orden); PARADA sin evidencia | fe5898e, 87ee571, 0e36803; suscripción FCM 14:26, 2 pruebas y orden W1 desde el móvil sin errores del servidor push; Damián: "funciona bien". No hay POST /parada del móvil en el log |
| 6. Móvil usable a 375-412 px | HECHO Y TESTEADO | 78d7b51; 6 pantallas sin desbordar; tablas apilables |

Arreglos del code-review: 0e36803 (hallazgos 1-7 y 9); hallazgo 8 → T187.
