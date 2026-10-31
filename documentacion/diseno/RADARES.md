# T693 · Motor común de radares (épica T692) — DISEÑO

Estado: **PLANIFICADO** (solo documento). Claude (Opus 5.5), noche 05/10/2026. Se implementa por piezas con tests
después de que Damián lo revise. Encaja con el rediseño T691 (destino "Radares", una pestaña por radar).

## 1. Qué es
Un radar es un **turno de búsqueda periódico** que trae artículos de fuentes fijas, los filtra contra el perfil de
Damián **en local**, y los pinta como **tarjetas** en su pestaña, donde Damián marca *me gusta*, *guardar* o
*descartar*; esas marcas ajustan el filtro. Un radar nuevo = un archivo de configuración (fuentes + criterios),
no código nuevo.

Radares previstos (T692): oportunidades (prácticas, trabajo; diario), cursos y certificaciones (semanal), viajes
(cada cierto tiempo), monetización (el "Buscador de ideas" de `documentacion/monetizacion/PROTOCOLO.md`, semanal) y
novedades del vigía (T272, diario; pasa a ser un radar más).

## 2. Lo aprendido con el vigía (T272) que el motor hereda
| Lección (vigía, 28/09-05/10) | Regla del motor |
|---|---|
| Fuentes leídas con código, no con IA: nada inventado | Cada fuente es un **lector** (`api`, `rss`, `json`, `html` con selector) que devuelve dicts con url, título, fecha, texto. La IA nunca "busca": solo valora lo que trajo un lector |
| Primera lectura de fuentes sin fecha = solo línea base | Igual: la primera pasada guarda lo visto y no publica nada |
| 30 candidatos del vigía se "perdieron" sin rastro (auditoría T687) | **Cada artículo queda en el almacén con su estado**; nada vive solo dentro del texto de un borrador |
| La IA inflaba el VALOR (todo 5) | La nota la pone un **filtro local determinista** (perfil + reglas); la IA solo resume y explica "por qué te lo enseño", y su opinión nunca sube la nota |
| Damián volvió a pedir cosas ya descartadas | Antes de publicar, `descartes.buscar` (T688) y los descartes del propio radar |
| Un lote por día y tope de candidatos | Tope por radar (artículos/día) y freno global |

## 3. Piezas
### 3.1 Configuración por radar — `memoria/radares/<radar>/config.json`
```json
{"id": "oportunidades", "nombre": "Oportunidades", "activo": true,
 "turno": {"dias": ["lunes", "...", "domingo"], "horas": ["08:15"], "max_minutos": 15},
 "fuentes": [{"id": "ejemplo_api", "tipo": "api", "url": "https://...", "campos": {"titulo": "title", "url": "link"},
              "terminos": "API pública / RSS oficial: comprobado el AAAA-MM-DD"}],
 "filtros": {"palabras_si": ["..."], "palabras_no": ["..."], "precio_max": null, "fechas": null, "idiomas": ["es", "en"]},
 "por_dia": 5, "caducidad_dias": 30}
```
- `terminos`: cada fuente lleva anotado **cómo se respeta su web** (API, RSS o alertas oficiales; nunca scraping de
  páginas que lo prohíban; nunca con la sesión de Damián). Sin esa línea, el lector no se activa.
- Los ajustes de la pestaña (artículos al día, frecuencia, filtros como precio o fechas) editan este archivo desde la
  web con validación (igual que la tabla de turnos T231).

### 3.2 Turno `radar` (sobre el planificador T231)
Una plantilla nueva `radar` con parámetro `radar=<id>`; la tabla de turnos ya admite días/horas/topes. Pasos:
1. **Leer** todas las fuentes del radar (código, con timeout y pausas; una fuente caída no tumba el resto).
2. **Deduplicar** por URL normalizada (sin parámetros de rastreo) y por parecido de título contra el almacén, los
   descartes del radar y el registro T688.
3. **Filtrar en local** contra el perfil (3.3) → nota 0-100 determinista. Se quedan los `por_dia` mejores por encima
   del umbral del radar.
4. **Resumir** (opcional, IA gratis/local; para radares con texto largo): 2 frases + "por qué te lo enseño". El prompt
   lleva solo el texto público del artículo y los criterios genéricos del radar — **nunca el perfil privado**.
5. **Publicar** tarjetas en el almacén (estado `nueva`) y, si el radar avisa, un push con el número (nunca el
   contenido de las tarjetas en el push).
- No es generador de propuestas: no le afecta el freno F0, pero sí la PARADA y el interruptor de turnos.

### 3.3 Perfil privado, filtrado en local
- `memoria/radares/perfil.json` (privado, como todo `memoria/`; no se publica en el espejo de GitHub) con lo que
  Damián quiera: estudios, intereses, ciudad o países, fechas libres, presupuesto de viaje, idiomas.
- La nota se calcula **en el PC**: coincidencias de palabras y raíces (como `freno.parecido`), reglas duras (precio,
  fechas, plazo vencido) y, si Ollama está, similitud de embeddings con bge-m3 (ya usado en T435) contra los artículos
  que Damián marcó *me gusta*. Coste cero y nada sale del PC.
- El perfil **nunca** viaja a ninguna IA externa ni a ninguna fuente.

### 3.4 Almacén de artículos — `memoria/radares/<radar>/articulos.jsonl` (+ índice)
Campos: `id`, `url`, `fuente`, `titulo`, `fecha`, `resumen`, `motivo` (por qué se enseña), `nota`, `estado`
(`nueva` | `vista` | `me_gusta` | `guardada` | `descartada` | `caducada`), `cuando`, `marcas` (historial).
Caducan a los `caducidad_dias` salvo guardadas. Archivar, nunca borrar (regla de NEXO).

### 3.5 Tarjetas y acciones (en la pestaña del radar, rediseño T691)
- Tarjeta: título, fuente con enlace, fecha, 2 frases, "por qué te lo enseño", y tres botones: **me gusta**,
  **guardar** (va a "Guardadas" de esa pestaña), **descartar** (pide motivo opcional de un toque: "no me interesa",
  "caro", "fechas", "ya lo vi").
- Acciones por POST con CSRF; sin optimismo (la tarjeta cambia cuando el servidor confirma).

### 3.6 Aprendizaje (sencillo y explicable)
- *Me gusta* y *guardar*: suben el peso de sus palabras/raíces y entran como ejemplos positivos de embeddings.
- *Descartar*: baja el peso; el motivo de un toque se convierte en regla (p. ej. "caro" ajusta `precio_max`
  propuesto, que Damián confirma en Ajustes; nunca se cambia un filtro duro sin que lo vea).
- Pesos en `memoria/radares/<radar>/aprendizaje.json`, con un botón "olvidar lo aprendido". Pantalla de ajustes
  muestra en claro qué ha aprendido ("te enseño más de: …, menos de: …").

## 4. Fases de implementación (cada una con tests y sin red en los tests)
| Fase | Qué | Esfuerzo |
|---|---|---|
| R1 | Lectores (`api`, `rss`, `json`) + almacén + deduplicado + turno `radar` en modo simular; el vigía migra a radar con sus mismas fuentes | 1 sesión Opus |
| R2 | Perfil y nota local (léxica + reglas duras); tarjetas en una pestaña provisional | 1 sesión Sonnet |
| R3 | Acciones me gusta/guardar/descartar + aprendizaje léxico + ajustes por pestaña | 1 sesión Sonnet |
| R4 | Embeddings bge-m3 (si Ollama está) y resumen IA opcional | 1 sesión Sonnet |
| R5 | Radares reales uno a uno: cada fuente con sus términos comprobados por Claude (web oficial) antes de activarla | 1 sesión por radar |

## 5. Decisiones de Damián
1. Qué radares quiere primero y qué datos pone en su perfil privado (solo los que quiera).
2. Si algún radar debe avisar por push (por defecto, ninguno).
