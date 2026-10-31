# Cómo arrancar la construcción con Claude Code de escritorio

1. Abre Claude Code de escritorio en la carpeta del repo `agente`
   (C:\Users\damia\Desktop\AI\agente).
2. Copia y pega el TEXTO de este primer mensaje (el bloque de abajo). NO pegues los otros
   archivos ni los subas: Claude los lee él mismo porque el prompt le dice sus nombres.

---
Vas a construir la interfaz web de NEXO. Antes de escribir código:
1) Lee interfaz/SPEC.md, interfaz/CLAUDE.md y interfaz/DECISIONES.md, y los módulos del core que
   vas a usar (nucleo/ordenes.py, nucleo/tareas.py, proveedores.py, nucleo/parada.py,
   nucleo/uso_proveedores.py). La v1 (interfaz_local.py) está archivada en _archivo/interfaz_v1/ desde el 25/09.
2) Hazme por AskUserQuestion TODAS las dudas que tengas hasta no tener ninguna
   (política de OK absoluto de entendimiento): no empieces a construir hasta tener el OK.
3) Cuando lo tengas, propón la estructura de archivos y el plan por incrementos y espera mi OK.
No cambies el stack (FastAPI+SSE+HTMX+Alpine), no añadas dependencias sin decirlo ni inventes
paquetes, y no reimplementes el core: impórtalo.
---

3. Responde a sus preguntas, aprueba el plan, y deja que construya por incrementos
   (cada pieza: propone → apruebas → implementa → verifica con evidencia → commit).

Notas:
- Claude Code de escritorio usa los tokens de Claude Pro de Damian. Los 100 $ de credito son 'creditos de sesion en la nube' (se gastan en sesiones en la nube como las de orquestacion), caducan el 5/11/2026 y al agotarse se vuelve al uso normal del plan (sin cargos extra: 'extender limites de uso' desactivado).
---

# NEXO en el móvil (hito móvil, 26/09/2026)

Dirección: **https://tu-equipo.tu-tailnet.ts.net** — solo funciona con Tailscale conectado en el móvil
(no está abierta a internet: es `tailscale serve`, nunca `funnel`). Desde el móvil se entra sin token:
la web reconoce tu usuario de Tailscale.

## Una vez, en el PC
- `interfaz\scripts\activar_movil.bat` publica la web en la tailnet (Tailscale lo recuerda tras reiniciar).
- Para dejar de publicarla: `interfaz\scripts\quitar_movil.bat` (quita solo el puerto 443).
- El vigía avisa en su log si el serve desaparece o si alguien pone un funnel.

## Una vez, en el móvil (Android, Chrome)
1. Abrir la dirección en Chrome con Tailscale conectado.
2. Menú ⋮ → **Instalar aplicación** (o "Añadir a pantalla de inicio").
3. En la app: **Ajustes → Activar notificaciones** → permitir → **Enviar prueba**.

## Si el móvil se queda sin internet con Tailscale activo
Ajustes de Android → Conexión y compartir → **DNS privado** → **Automático** o **Desactivado**.
Con un DNS privado fijo (p. ej. dns.google), MagicDNS de Tailscale choca y el móvil se queda sin internet
(ya nos ha pasado).

## Si los avisos llegan tarde o no llegan (Xiaomi / HyperOS, POCO F7)
HyperOS mata las apps en segundo plano. Para **Chrome** (las notificaciones de la app instalada van por Chrome):
1. Ajustes → Aplicaciones → Administrar aplicaciones → Chrome → **Notificaciones**: activadas.
2. Mismo sitio → **Inicio automático**: activado.
3. Mismo sitio → **Ahorro de batería**: **Sin restricciones**.
4. Opcional: en Recientes, mantener pulsada la tarjeta de Chrome → candado, para que no la cierre al limpiar.

## Qué avisa y cuánto
Órdenes lanzadas desde la web al terminar o fallar, PARADA activada/quitada y fallos reales del turno nocturno.
Texto: tipo + id + frase corta (sin secretos). Máximo 1 por orden y 1 por turno; más de 5 por minuto se agrupan.
