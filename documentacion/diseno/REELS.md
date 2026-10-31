# Reels guardados → conocimiento de NEXO (diseño, 12/10/2026)

Origen: T706 (colección de guardados de Instagram) + T763 (investigar reel-watcher). Decisión de Claude: ADAPTAR.
Integración: T859.

## Qué hace reel-watcher (jakeb144/reel-watcher, MIT, 2 estrellas, 1 commit)
- Entrada: exportación oficial de Instagram (`saved_posts.json`) → lista de URLs. No entra en la cuenta ni usa cookies.
- Descarga: Apify (~0,002 $/reel, necesita APIFY_TOKEN). Es el único paso de red.
- Análisis 100 % local: fotogramas clave (gancho + uno por corte de escena), OCR del texto en pantalla
  (Apple Vision), transcripción con tiempos (mlx-whisper), descripción visual (Qwen2.5-VL-7B 4 bits),
  detección de "comenta X / escríbeme X".
- Salida: un JSON por reel (`hook, format, cta, giveaway, transcript, frames`) + `study_index.jsonl`.
- **Solo funciona en macOS con Apple Silicon** ("Intel, Linux and Windows are not supported"). No se instala: se copia el diseño.

## Alcance
La exportación oficial de la red social trae TODOS los guardados del usuario, la mayoría ajenos a NEXO. Solo cuenta lo
que está en las colecciones que el usuario marque como alcance (la lista concreta y los recuentos viven en
`memoria/perfil_privado/reels/ALCANCE.md`, privado).
1. **Filtro por colección (preferente):** la exportación suele incluir las colecciones (nombre + elementos). Se toman
   solo las del alcance (comparación sin mayúsculas/tildes). Lo demás no se descarga, no se analiza y no se guarda.
2. **Si la exportación no trae colecciones:** cribado mínimo con el pie de foto/autor (IA local), sin descargar vídeo;
   lo que claramente no sea de IA/tecnología/negocio/trading/diseño se descarta sin guardarlo. Las dudas se descargan y
   se juzgan con la transcripción. Se informa del recuento sin listar los descartados.
3. Si las colecciones tienen reels más antiguos que el periodo de la exportación, hará falta otra con "todo el tiempo".
4. Del contenido, el pie de foto solo no basta en la mayoría: el análisis del vídeo (texto en pantalla + transcripción)
   es imprescindible.

## Adaptación a NEXO (Windows, local-first)
| Paso | reel-watcher | NEXO |
|---|---|---|
| Lista de reels | export `saved_posts.json` | export del usuario, filtrado a las colecciones del alcance |
| Descarga | Apify | 1º yt-dlp sin sesión (gratis); si falla mucho → decisión de Damián (Apify con crédito gratis o anotar "no descargable"). Nunca cookies del Chrome personal. |
| Audio → texto | mlx-whisper | faster-whisper (small, CPU) |
| Texto en pantalla | Apple Vision | modelo de visión local ≤8B en Ollama (qwen2.5vl:7b) sobre los fotogramas |
| Fotogramas | ffmpeg + cortes de escena | igual (ffmpeg) |
| Descripción | Qwen2.5-VL-7B | igual, vía Ollama (≤8B) |

## Regla principal: no se pierde información (de lo que está en alcance)
1. **Capa bruta (nunca se borra):** `memoria/perfil_privado/reels/<codigo>.json` con URL, autor, pie de foto,
   transcripción completa, texto en pantalla, descripción de fotogramas, enlaces/repos/herramientas citados y
   estado (`analizado`, `no_descargable`, `borrado`, `solo_texto`). Lo que no se pueda leer se anota así, sin inventar.
2. **Capa clasificada (encima, multi-etiqueta):** cada reel puede ir a varias categorías; clasificar añade
   punteros, no mueve ni recorta nada. Lo que no encaje va a `sin_clasificar` (se revisa, no se tira).
3. **Capa de acción:** solo lo accionable se convierte en tarea/propuesta, deduplicado contra tareas
   existentes y contra lo DESCARTADO (registro T688), con el reel como fuente.

## Categorías
| Categoría | Qué entra | Destino |
|---|---|---|
| `nexo` | ideas, repos, técnicas para mejorar NEXO | propuestas por el circuito de revisión (tribunal) |
| `herramientas` | apps, webs, servicios, repos útiles en general, también los de uso personal aunque NEXO no los use | catálogo de herramientas |
| `trading` | trading cuantitativo: estrategias, papers, datasets, indicadores, gestión de riesgo, backtesting | base de conocimiento para el futuro optimizador de estrategias (sin tareas aún) |
| `negocio` | ideas de negocio y monetización | rama de monetización (handoff de monetización) |
| `diseno` | diseño de apps/webs, UI, skills tipo "taste" | rediseño de interfaz (T691) y T856 |
| `ia_prompts` | técnicas de prompting, agentes, flujos con IA | conocimiento de NEXO + propuestas |
| `contenido` | formatos, ganchos, edición de vídeo | para los canales de contenido propios |
| `carrera` | cursos, becas, prácticas, oportunidades | radar de oportunidades |
| `sin_clasificar` | dudas dentro del alcance | revisión periódica |

## Privacidad y seguridad
- La colección es privada: todo en `memoria/perfil_privado/` (excluido del espejo y de git). A proveedores
  externos solo va el contenido público de un reel suelto, nunca la colección ni la lista.
- Los guardados fuera del alcance no se procesan ni se conservan (salvo la exportación original, que es de Damián).
- El texto de los reels es contenido NO confiable: nunca se ejecutan órdenes, URLs o instalaciones que
  aparezcan en ellos sin confirmación (ideas T767/T768).
- Respetar a los creadores: no redistribuir vídeos, fotogramas ni transcripciones.

## Plan
1. El usuario pide la exportación (JSON).
2. Code: lector de la exportación + filtro de alcance; piloto con 5 reels (descarga + transcripción + fotogramas +
   visión) → medir % descargable y tiempo/reel.
3. Clasificación con IA local; revisión del muestreo por el tribunal; después, lote completo por turnos nocturnos.
4. Pestaña "Conocimiento" en la web (buscar por categoría/texto) dentro del rediseño.

## Herramientas ya hechas que se miraron (12/10)
- woosal1337/media-mcp (MIT, 8 estrellas): MCP con descarga + whisper local + fotogramas, pero Instagram exige
  montar Cobalt (Docker) y pide clave de TwitterAPI; sin OCR. No compensa.
- transcribe-social (PyPI, MIT, v1.0.6): solo transcribe audio; sin texto en pantalla.
- Apify "reel script extractor": de pago. Descartado (nada de pago).
Conclusión: pipeline propio pequeño (yt-dlp + ffmpeg + faster-whisper) y, para leer el texto de pantalla, el
piloto compara visión local <=8B (qwen2.5vl:7b) con Gemini API gratis (contenido público de un reel suelto, nunca la
lista): se queda la que lea bien los nombres de repos con menos recurso.

## Ficha completa por reel y tareas (Damián 12/10 noche) — MANDA sobre lo anterior
Requisito: de cada reel se saca TODA la información importante de las tres fuentes (pie/descripción, audio y
fotogramas) y de lo extraído salen tareas de investigación → extracción → adaptación → implementación. Un resumen
tipo "habla de 20 repos" NO vale: se listan los 20.

1. **Extracción densa**: pie + transcripción + texto de pantalla de TODOS los fotogramas útiles. Si el reel enseña
   listas o tarjetas, muestreo denso (≈1 fotograma/s en esos tramos) y recortes ampliados para letra pequeña.
2. **Ficha del reel** (`<codigo>.ficha.json`, privada, encima de la capa bruta): `promesa` (lo que dice que trae: "20
   repos", "5 fuentes"...) y `elementos[]`, cada uno con: tipo (repo, herramienta, web, modelo, dato, técnica, idea de
   negocio, curso/oferta, consejo), nombre, dueño/URL, qué es, para qué nos sirve, categoría(s), fuente (pie / audio
   mm:ss / fotograma n) y confianza.
3. **Completitud**: si `promesa` dice N y hay menos de N elementos → re-muestreo más denso y relectura; si aun así
   faltan, la ficha queda `incompleta: faltan K` (nunca en silencio) y va a revisión.
4. **Resolución**: elementos sin dueño/URL → búsqueda gratuita (API de GitHub / web) para fijar `dueño/repo` canónico,
   estrellas, licencia, última actividad y si existe de verdad. Lo no resuelto queda marcado.
5. **Deduplicado** contra catálogo, tareas vivas/cerradas y DESCARTES (T688): si ya existe, se anota la fuente nueva
   en lo existente; no se duplica.
6. **Tareas** (flujo T674 que ya existe): por TEMA, no por elemento suelto, para no inundar la cola. Ej.: "20 repos
   para ahorrar tokens" → UNA investigación comparativa de los 20 frente a lo que NEXO ya usa (caveman, Graft), con los
   20 dentro; su RESULTADO (ADOPTAR/ADAPTAR/DESCARTAR por elemento) crea las hijas "Integrar" (adaptación +
   implementación en piezas tests:dados) que se verifican. Un repo suelto importante → su propia investigación.
   Conocimiento sin acción (datos de trading, consejos) → base de conocimiento por categoría, sin tarea. Acciones que
   son de Damián (p. ej. pedir el GitHub Student Pack) → tarea personal propuesta para él.
   Todo entra como propuesta por el circuito del tribunal y respeta el freno.
7. **Supervisión**: antes del lote, repetir el piloto de 5 con este formato y enseñar a Damián las 5 fichas completas.

## Huecos que solo puede cubrir Damián (Damián 12/10 noche)
Muchos reels piden "comenta PALABRA y te mando la guía/el repo/el prompt". Filtro:
1. Detectar la llamada (comenta X, DM, link in bio, te lo mando por privado) y QUÉ promete enviar.
2. Intentar cubrirlo sin Damián: si el elemento ya está identificado (nombre/dueño resuelto, URL pública), la guía
   NO hace falta (NEXO lee la documentación oficial del repo). Probar también la web/bio pública del autor y una
   búsqueda por la descripción. Nada de registrarse ni de dejar datos en webs de terceros.
3. Solo si falta información ESENCIAL que no se puede obtener en público (p. ej. el reel no nombra el repo en
   ningún sitio, o el valor está en un prompt/plantilla privada) → tarjeta en la bandeja de Damián.
4. Tarjeta agrupada por tanda (máx. ~10 reels, ordenados por valor): enlace al reel, palabra exacta y cuenta a la que
   comentar, qué se espera recibir y por qué hace falta; campo para pegar lo recibido; botones "Pegado" y "No merece
   la pena". Al pegar, NEXO reprocesa ese reel y completa su ficha.
5. NEXO nunca comenta ni escribe desde la cuenta de Damián. Lo pegado es contenido NO confiable (puede traer
   instrucciones o enlaces de venta): se trata como dato, nunca se ejecuta ni se instala nada de ahí sin N04.

## Bloque 6 hecho (12/10 noche): cómo quedó y qué se midió
- **Lectores** (orden de 6b, ver abajo): OCR local RapidOCR 1.4.4 (CPU, `.venv-reels`, A0044) primero; Gemini API solo
  para los fotogramas nítidos que el OCR no lee (trozos de 16, pausa de 4 s, rondas con espera si todo está saturado);
  y, si está instalado, qwen2.5vl:3b. qwen2.5vl:7b vetado en el código y BORRADO (A0047). Fotograma nítido sin texto =
  `revisar` (medido con `blurdetect` de ffmpeg); borroso sin texto = `sin_texto`, sin gastar cuota.
- **Cuota DIARIA de Gemini**: con 2 reels se agotó la gratuita de 3.6-flash y 3.5-flash
  (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`), 3.7-flash daba 503 y solo respondía 3.5-flash-lite. El modelo
  agotado se salta el resto del día; sin ninguno, el lote para (`SinCuotaGemini`) y sigue otra noche. La cuota se
  comparte con el tribunal y el resto de NEXO (de ahí el tope de 6b).
- **flash-lite** cumple pero es descuidado (tipos inventados, "audio mm:ss" literal, omite elementos de forma
  variable): por eso tipos y fuentes se fijan sin IA, hay segunda pasada "dame solo lo que falta" y al rehacer no se
  pierde lo verificado de versiones anteriores.
- **Código**: `extremidades/reels.py` (lectura densa, `procesar`, `rehacer_ficha`, `lote`, `turno`),
  `nucleo/reels_ficha.py`, `nucleo/reels_resolver.py` (GitHub sin token, caché 7 días), `nucleo/reels_tareas.py`
  (deduplicado + plan por tema + `crear` por el tribunal con freno), `nucleo/reels_huecos.py` + panel en Bandejas.
- **Órdenes**: `.venv-reels\Scripts\python.exe -m extremidades.reels ficha|rehacer [--crudo]|cola|lote CODIGO...`;
  `.venv\Scripts\python.exe -m nucleo.reels_tareas plan` (solo enseña).
- **Lote**: turno "Reels guardados (lote nocturno)" creado INACTIVO (23:30, 180 min, ~30 reels). No se ha lanzado.
- Supervisión de los 5: `memoria/perfil_privado/reels/SUPERVISION_2026-10-12.md` (privado).

## Bloque 6b (12/10 noche): cuota y primera noche
- **Orden de lectura**: OCR local → Gemini solo para lo nítido que el OCR no lee → visión local de respaldo.
- **Fichas con proveedores gratuitos**: la ficha (estructurar el texto público de UN reel) y la segunda pasada "lo que
  falta" se piden primero a NVIDIA y Groq (`pedir_modelo`; el primero que devuelva un JSON válido); Gemini API solo si
  ninguno vale, y dentro del presupuesto. Con un `post` de prueba nunca se llama a nadie.
- **Presupuesto diario de Gemini** (`nucleo/cuota.py`: `permite`/`gastar`/`queda_hoy`): Gemini no da cuota legible, así que
  el lote lleva cuenta propia y gasta como mucho una fracción del total diario estimado (por defecto el 20 %). Agotado,
  las fotos siguen con OCR y las fichas paran el lote (`SinCuotaGemini`) hasta el día siguiente. Configurable en
  `memoria/perfil_privado/reels/config.json`: `gemini_fraccion_diaria`, `gemini_peticiones_dia` (estimación),
  `una_noche`, `crear_propuestas`.
- **Primera noche supervisada**: con `crear_propuestas=false` y `una_noche=true` el turno no crea tareas ni tarjeta;
  escribe `MUESTRA_<fecha>.md` (10 fichas repartidas + las propuestas y la tarjeta de huecos que saldrían de todas las de
  la noche) y apaga el turno. Para seguir, se revisa la muestra y se pone `crear_propuestas=true`, `una_noche=false` y se
  reactiva el turno.
- **Nota ≠ cuenta**: "10 out of 10 ..." (igual a ambos lados) es una nota, no una promesa de N elementos
  (`reels_ficha.quitar_nota`).
- **Tareas personales**: si un descarte antiguo (T688) cubre una herramienta que el reel enseña como oferta de
  estudiante, la tarea personal pide comprobar la elegibilidad y reabrir o mantener el descarte.
