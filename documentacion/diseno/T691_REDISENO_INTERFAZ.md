# T691 · Plan del rediseño a fondo de la interfaz de NEXO (épica T690)

Estado: **PLANIFICADO** (solo documento; nada implementado). Autor: Claude (Opus 5.5), noche 05/10/2026.
Maqueta estática: [`maqueta_t691.html`](maqueta_t691.html) (ábrela en el navegador del PC o del móvil; no carga
nada de fuera).

## 1. De dónde partimos (inventario real, 05/10)
- Web en `interfaz/`: FastAPI + Jinja + htmx + Alpine (CSP estricta, librerías vendorizadas con SHA-256), SSE con
  replay, PARADA siempre visible, PWA instalable con push (hito móvil, 26/09; probado en el POCO F7 por Tailscale).
- 8 entradas de menú planas: Centro, Órdenes, Tareas, Grafo, Turnos, Proveedores, Logs, Ajustes.
- El Centro ha crecido por acumulación: **14 paneles** apilados (resumen, turnos, IAs, freno F0, tribunal, riesgo,
  descartadas, revisión, auditoría, estado, proveedores, tareas, acciones, trazas). En el móvil hay que hacer
  scroll largo para llegar a lo que pide una decisión.
- 64 plantillas, 94 rutas, ~1550 tests (suite en ~3,5 min).
- Pendientes de interfaz que este plan absorbe sin duplicar: T230 (filtrar/ordenar y lenguaje claro), T140 (app de
  órdenes), T263 (presentador, aparcada hasta el 11/10), T116 (ancla "tipo Jarvis": información útil, no
  decorativa), T693 (tarjetas de radares).

## 2. Problemas que resuelve
1. **Qué me toca ahora** no se ve de un vistazo: las bandejas (tribunal, riesgo R1/R2, revisión, escalados del chat,
   decisiones) están repartidas en paneles distintos del Centro.
2. Mucho texto para IA (ids, etiquetas `cat:`/`prov:`) en primer plano; la capa técnica debería ir detrás.
3. Móvil: menú de 8 entradas arriba, paneles largos, botones pequeños.
4. Los radares (T692) no tienen sitio: necesitan pestañas propias con tarjetas.

## 3. Navegación nueva
Cinco destinos principales (barra inferior en el móvil, lateral en el PC) y el resto en "Más":

| Destino | Qué tiene | Sustituye a |
|---|---|---|
| **Centro** | Una frase de estado ("NEXO funciona; 3 cosas te esperan"), la PARADA, el turno en marcha y el próximo, y como mucho 3 tarjetas "te toca". | Los 14 paneles actuales (pasan a sus sitios o a "Detalle técnico") |
| **Tareas** | Lista con filtros en la URL (T230), ficha con chat (T290), vista "Descartadas" (T688) como filtro. | Tareas + panel de descartadas |
| **Órdenes** | Escribir una orden (grande, arriba) + historial; aviso de descarte previo (T688). | Órdenes |
| **Bandejas** | Todo lo que necesita una decisión de Damián, en una sola cola ordenada por urgencia: tribunal (Aprobar/Rechazar/Mandar a Claude), riesgo R1/R2, investigaciones por decidir, escalados del chat, decisiones del informe de la noche. Contador en el icono. | Paneles tribunal, riesgo, revisión del Centro |
| **Radares** | Una pestaña por radar (oportunidades, cursos, viajes, monetización, novedades del vigía), tarjetas con me gusta / guardar / descartar y ajustes por pestaña (motor de T693). | Nuevo (y el informe del vigía) |
| Más → | Turnos, Proveedores (con "Inicializar"), Grafo, Logs, Ajustes, Detalle técnico (paneles del Centro de hoy, tal cual). | — |

Reglas que se mantienen: PARADA visible en todas las pantallas; estados con nombre propio; color nunca como única
señal; teclado y lector de pantalla (WCAG 2.2 AA); tema claro/oscuro; nada de "optimistic update" en acciones de
autoridad.

## 4. Móvil primero (POCO F7: 1080×2400, ~393×873 CSS px a densidad 2,75)
- Diseño a 360-400 px primero; el PC es la versión ancha, no al revés.
- Barra inferior fija con 5 iconos + texto (zona del pulgar), respetando `env(safe-area-inset-bottom)`.
- Objetivos táctiles ≥ 44×44 px; acciones de decisión con confirmación en la propia tarjeta (no `confirm()`).
- Tarjetas en una columna; tablas solo en el PC (en el móvil, `tabla-apilable` ya existente).
- Push (ya funciona) lleva directo a la tarjeta de la bandeja (`/bandejas#<id>`).

## 5. ¿Se queda htmx + Jinja o se cambia de base?
**Recomendación: se queda.** Motivos:
1. Funciona y está probado: 94 rutas y ~1550 tests; reescribir en React/Next tiraría esa red de seguridad.
2. Seguridad: CSP estricta sin `unsafe-eval`, sin CDN en tiempo de ejecución, sin build ni Node en el PC de NEXO; una
   SPA con bundler mete cadena de suministro npm (justo lo que T133/T492-T496 quieren acotar).
3. Un solo usuario, red local/Tailscale: el problema es de **información y navegación**, no de rendimiento ni de
   interactividad compleja. htmx + Alpine dan tarjetas, pestañas, swipe sencillo y actualizaciones por SSE.
4. Coste: el rediseño es CSS + plantillas + 3-4 rutas nuevas; con cambio de base serían semanas y un periodo con
   dos webs.

Consecuencia: **Blkit (T178) y kokonutui (T179) siguen descartados** (son React/Tailwind o gráficos que no encajan
sin cambiar de base, que es la condición que Damián puso el 04/10 para revalorarlos). Si algún día se cambiara de
base, se revaloran entonces.

Qué SÍ se adopta de esas librerías: la idea visual (tarjetas limpias, jerarquía tipográfica clara, espaciado
generoso), reimplementada con CSS propio y tokens.

## 6. Fases (cada una con tests y prueba de Damián en el móvil antes de la siguiente)

| Fase | Qué | Esfuerzo estimado | Riesgo |
|---|---|---|---|
| 0 | Damián mira la maqueta en el POCO F7 y dice qué cambia (bloqueante). | 15 min de Damián | — |
| 1 | Esqueleto: barra inferior/lateral con 5 destinos + "Más"; rutas viejas siguen vivas; tests de navegación y PARADA en cada pantalla. | 1 sesión Sonnet (~2-3 h) | Bajo (solo plantillas/CSS) |
| 2 | **Bandejas**: cola unificada (lee tribunal, riesgo, investigación, chat escalados) con acciones en la tarjeta; contador en el icono y en el push. | 1 sesión Opus (~3-4 h) | Medio (acciones de autoridad: CSRF, sin optimismo) |
| 3 | Centro nuevo: frase de estado + 3 tarjetas "te toca" + turno; los 14 paneles a "Detalle técnico" sin perder ninguno. | 1 sesión Sonnet | Bajo |
| 4 | Tareas y Órdenes: filtros en la URL y lenguaje claro (cierra T230); Descartadas como filtro. | 1-2 sesiones Sonnet | Bajo |
| 5 | Radares: pestañas y tarjetas sobre el motor de T693 (depende de T693 fase 1). | 1 sesión Opus + 1 Sonnet | Medio |
| 6 | Pulido: tema, accesibilidad (revisión WCAG), rendimiento en el móvil, `/code-review` del bloque. | 1 sesión Sonnet | Bajo |

Total aproximado: 6-8 sesiones de Code a lo largo de 2-3 semanas, con prueba de Damián entre fases.

## 7. Criterios de hecho (por fase)
- Tests de endpoints y de plantillas (cada destino responde, PARADA presente, sin regresiones en la suite).
- Captura del móvil (360-400 px) y del PC en el informe de la fase.
- Damián prueba en el POCO F7 y da el OK; sin su OK no se pasa de fase.

## 8. Decisiones que son de Damián
- Visto bueno a la navegación de 5 destinos (o cuáles cambia) tras ver la maqueta.
- Qué radares quiere de verdad en la primera versión (orden de T692).
