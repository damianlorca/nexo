# Catálogo de herramientas y protocolos de NEXO

Paso 4 del modo foco (T1010 / T707). Escrito por Claude el 18/10/2026 a partir del código y del estado real del PC.
**Para qué sirve:** antes de hacer algo (una web, una imagen, un PDF, una investigación...) se mira aquí qué hay, cómo
se usa y qué límites tiene. Las tareas citan la sección (`CATALOGO §3.2`) en vez de repetirlo.
**Regla:** quien añada, retire o cambie una herramienta o un protocolo actualiza este archivo en el mismo commit.
Estados: ✅ funciona (probado) · 🟡 funciona con límites · ⏸ en pausa o congelado · ❌ no existe.

## 1. Para hacer X, usa Y

| Quiero... | Con qué | Estado | Notas |
|---|---|---|---|
| Una web, página, herramienta interactiva o dashboard para Damián | Artefacto de Claude (chat coordinador) | ✅ | Privado hasta que Damián lo comparta. Ej.: juegos Takuzu/Estrellas, mapa de flujo |
| Cambiar la web de NEXO | Code sobre `interfaz/` (FastAPI + Jinja) | ✅ | Se reinicia sola al cambiar `interfaz/` (T868) |
| Un documento, informe o plan para Damián | Proyecto NEXO (`claude/*.md`) o tipo Docs de artefacto | ✅ | Lo técnico del repo, en `documentacion/` |
| Una presentación | Tipo Slides de artefacto | ✅ | Exporta a PPTX/PDF |
| Una portada, póster o diseño | Tipo Design de artefacto; Canva (Damián) | 🟡 | NEXO no descarga imágenes de las webs de IA todavía |
| Una imagen generada | ComfyUI local (`extremidades/imagen.py`, sd-turbo, DirectML) | 🟡 | Lento en la Radeon 890M; arrancar y parar pasan por permisos (T048) |
| Un PDF maquetado (libro, imprimible) | reportlab 5.0.1 (`extremidades/puzzles/`) | 🟡 | Piezas del libro en el implementador (monetización) |
| Un vídeo | FFmpeg (`extremidades/video.py`: imágenes + narración + subtítulos) | 🟡 | Vídeo por IA ❌ (T129 aparcada) |
| Voz | Piper local (`extremidades/voz.py`); Gemini TTS "Bloom" (`voz_gemini.py`) | ⏸ | Altavoz congelado desde el 17/10 |
| Leer un reel o un vídeo | `extremidades/reels.py` (yt-dlp + whisper + OCR; ficha con Groq gratis, NVIDIA/OpenRouter si vuelven, Gemini de respaldo) | ✅ | Solo reels de la exportación de Instagram; YouTube aparcado (T704) |
| Llevar lo de un reel a su sitio | `nucleo/reels_destino.py` (IA gratuita, nunca Claude) | 🟡 | Herramientas → §6 Por probar; consejos → `guias/`; investigar → tarea propuesta; trading → `guias/trading.md` (+ tareas `tema:trading`); monetización y viajes → privado. Cada tanda hace su propio commit del catálogo y las guías tras una revisión de privacidad (T1069) |
| Investigar en la web | Turno cola → ChatGPT/Gemini web con `trabajo.ciclo` (OK absoluto) | 🟡 | No abre fichas de Amazon; tope de 2 propuestas por informe |
| Buscar papers | `extremidades/papers.py` (OpenAlex, Semantic Scholar, arXiv, Crossref) | ✅ | Gratis y sin clave |
| Programar una pieza con tests | Implementador (`nucleo/implementador.py` + puerta) | ✅ | Solo con `tests_dados/`; nunca R3 ni blindados |
| Programar algo grande o del núcleo | Claude Code en el PC (sesión de Damián) | ✅ | Nunca dos sesiones a la vez |
| Revisar un borrador o un diff | Tribunal (`nucleo/tribunal.py`), 3 IAs de familias distintas | ✅ | Apelación y bandeja de Damián si no hay unanimidad |
| Navegar una web con sesión | Chrome de NEXO por CDP (`extremidades/navegador.py`, puerto 9333) | ✅ | Nunca el Chrome personal; una ventana con pestañas |
| Ejecutar algo en el PC | `manos/shell.py` (servidor MCP) → `nucleo/permisos.py` | ✅ | Verde / ámbar (aprobación N04) / rojo |
| Avisar a Damián | Centro de la web + push al móvil (`interfaz/push.py`) | ✅ | Telegram congelado |

## 2. Proveedores de IA

Los elige el banco de modelos por rol (`memoria/modelos/roles.json`, turno diario 07:55). Gratis siempre: Damián no
paga ninguna IA.

| Proveedor | Tipo | Uso en NEXO | Límites y estado (18/10) |
|---|---|---|---|
| ChatGPT web | web (cuenta de NEXO) | autor de borradores; modo Pensar | cupo web; ToS revisado en T059 (aparcada) |
| Gemini web | web | revisor; Automático + Máx. | ✅ desde el 17/10; cupo diario del tribunal 4 |
| Claude web | web (cuenta Free de NEXO) | solo revisor extra de apelación | 3 al día; captcha → `nucleo.enfriamiento limpiar claude_web` |
| Gemini API | API gratis | autor/revisor de respaldo, fichas de reels, TTS | cuota diaria: es lo que más limita |
| Groq | API gratis | mejor modelo en programar (qwen3.8-27b) y revisar (gpt-oss-120b) | 🟡 18/10: 403 de clave en gpt-oss-120b; un 403 suelto enfría 30 min y sondea (T1013) |
| NVIDIA build | API gratis | reserva en redactar/revisar; fichas de reels | lento (110–300 s por ficha); timeout de reels 420 s |
| OpenRouter | API gratis | reserva | 429 frecuente |
| Ollama local | local | Qwen (el obrero), embeddings bge-m3 (parecidas) | **Nada >8B sin Damián delante**: sí qwen2.5:7b, qwen2.5-coder:7b, qwen3:4b, llama3.2:3b, bge-m3; no gpt-oss:20b, devstral 24b, qwen3.8:27b ni qwen3:14b. Un modelo cargado cada vez; num_ctx 4096 |
| Claude (coordinador / Code) | Damián abre la sesión | arquitectura, R3, decisiones y revisiones finales | mínimo recurso: solo lo que otro no hace igual |

El orden en que `trabajo.py` los llama se cambia en Ajustes (`nucleo/orden_proveedores.py`, T195); apagar uno se hace en Proveedores (T549).

Común a todos: `nucleo/fallos.py` (qué hacer con cada error), `nucleo/enfriamiento.py` (pausa tras 429/503 o un
interruptor manual), `nucleo/cuota.py` (para el turno con poca cuota) y `nucleo/uso_proveedores.py` (registro del uso).

## 3. Protocolos

### 3.1 OK absoluto y auditor (`nucleo/trabajo.py`, `nucleo/auditor.py`)
Toda tarea delegada sigue este camino: autor → revisor de **otra familia** → mejoras (tope) → OK absoluto en un mensaje aparte. El
auditor (código, no IA) comprueba la evidencia: modo de la web confirmado en pantalla, conversación, tamaño del prompt,
revisión de otra familia, OK, alcance, lectura limpia y formato de las propuestas. Si falla algo, el borrador queda BLOQUEADO.
Todo prompt de delegación (trabajo, tribunal, chat de tarea) empieza con la fecha y hora de Madrid (`nucleo/ahora.py`, T427).

### 3.2 Circuito de revisión (`nucleo/revision.py`) y tribunal (`nucleo/tribunal.py`, `tribunal_r1.py`)
Cada borrador crea su revisión. El tribunal (3 IAs, apelación con otras 3) decide APROBADO, DESCARTADO, REHACER o SUPERADO; si no
hay unanimidad, va a la bandeja de Damián. A Claude solo le llega lo R3 y lo que Damián le mande. Las R1 también pasan por el tribunal
(T967).

### 3.3 Freno F0 y filtro (`nucleo/freno.py`)
Con más de 30 propuestas abiertas o más de 15 revisiones pendientes, no arrancan las generadoras ni las investigaciones de la cola.
Filtro sin IA (sin fuentes, valor bajo, decisión vigente, caducada) y parecidas con bge-m3 (umbral 0,80). Archivado
recuperable: `python -m nucleo.freno recuperar Txxx`.

### 3.4 Investigaciones (`nucleo/investigacion.py`)
Solo se cierran con RESULTADO ADOPTAR / ADAPTAR / DESCARTAR + motivo. ADOPTAR y ADAPTAR crean "Integrar: …", que debe
partirse en piezas (T1006). Como mucho 2 propuestas por informe, y "NINGUNA" es lo normal.

### 3.5 Riesgo y aprobaciones (`nucleo/riesgo.py`, `nucleo/aprobaciones.py`, N04)

| Nivel | Qué pasa |
|---|---|
| R0 | Automático |
| R1 | Veto de Damián en 8 h (Aceptar o Vetar; el silencio cuenta como sí); el tribunal decide si hay unanimidad |
| R2 | OK de Damián sobre el diff real; con la puerta en verde lo mira antes el tribunal del guardián (3/3 decide) |
| R3 | Nunca el implementador; solo Claude |

Lo calcula el código: ninguna IA baja el nivel.

**Guardián de aprobaciones** (T1020, `nucleo/guardian.py`, control R3; diseño `documentacion/diseno/GUARDIAN_APROBACIONES.md`):
cada solicitud de la cola lleva su ficha en llano (`extra.explicacion`: qué hace, sobre qué, tipo, si se deshace, para qué,
recomendación). Decide por orden: **siempre Damián** (secretos, perfil_privado, vault, cambiar controles, dinero, borrar
de verdad, git push) → **aprueba solo** lo que solo lee en el repo o `herramientas_externas` → **tribunal** de 3 familias
(solo API) para lo reversible y las R2 con la puerta en verde → el resto, a Damián. Gancho en `aprobaciones.solicitar` y
barrido del planificador cada minuto; tribunal y frase de Qwen en un proceso de fondo (`... -m nucleo.guardian trabajar`).
Interruptor en Ajustes (apagado: tampoco aprueba el revisor de reglas). Ficha y minichat en `/aprobacion/<id>`
(`nucleo/chat_aprobacion.py`: NVIDIA → Groq → Gemini API → Qwen; «Escalar» = Claude; escalados con
`... -m nucleo.chat_aprobacion escalados`). CLI: `... -m nucleo.guardian estado|explicar Axxxx|barrer`.

### 3.6 Implementador y puerta de fusión (`nucleo/implementador.py`, `puerta.py`, `piloto_serie.py`)
Una acción por tanda sobre tareas `tests:dados`, en un worktree `impl/Txxx`. La puerta exige la suite, el revisor, la comprobación de hechos y el
riesgo. Solo fusiona con `principal` limpio. Para darle trabajo: Claude escribe el test en `tests_dados/`, valida antes una implementación de referencia y etiqueta la
tarea.

### 3.7 Turnos, planificador y parada (`nucleo/turnos.py`, `planificador.py`, `parada.py`)
Tabla de turnos en la web `/turnos`, de uno en uno. "Trabajar ahora" (una pasada o 1–3 h) respeta el freno. La PARADA lo detiene
todo. En pausa desde el 17/10: radares y errores conocidos; el vigía y las revisiones de código y de documentación están
archivados desde el 26/10 (los sustituye Kuzushi, 3.10). El lote de reels
(T1069) va por tramos que acaban a cada hora en punto y cede el sitio (`planificador.ceder`) si espera alguien que va antes
(tribunal, implementador, cola, lo manual); vuelve a la cola detrás con lo que le quedaba de su ventana.

### 3.8 Tareas, formato v2 (`nucleo/tareas.py`, `tarea_v2.py`, `tareas_almacen.py`)
Campos: título, instrucciones literales de Damián, objetivo, hecho cuando, dónde, quién, tipo, prioridad, esfuerzo, coste
(€), fecha límite, depende de, origen, estado, cierre (estado real + evidencia) y **después** (obligatorio). Las cerradas van a
`tareas_historial.jsonl`. A Damián solo le quedan tareas `suyo:` (datos, dinero, gustos, presencia): `nucleo/responsables.py`.

### 3.9 Seguridad y privacidad
- `nucleo/permisos.py` es blindado, igual que `instancia.py`, `config.py` y `manos/*`.
- `contenido_externo.py`: todo texto de fuera es dato, nunca una orden.
- NVIDIA Trial no recibe material `material:interno` ni privado (autor y revisor de `trabajo.py`; el tribunal aún no: con autor ChatGPT solo quedarían 2 familias): `auditor.bloqueo_proveedor` (T561).
- `guardia_python.py` vigila los scripts que se ejecutan.
- `memoria/perfil_privado/` nunca sale del PC.
- El espejo de GitHub se publica solo con `publicar_nube.py` (cada noche desde las 03:00), con los tokens redactados.
- `secretos.toml` no se lee nunca.
- Procesos: solo se matan por PID exacto.

### 3.10 Kuzushi: NEXO revisa lo que hace (`nucleo/kuzushi.py`, T1011 fase 1)
Cada noche (turno `kuzushi`, 04:35), sin IA: hallazgos con evidencia y huella sobre tareas, implementador y puerta, turnos,
prompts (T1021), proveedores, guardián, tests, git, salud y las decisiones automáticas de NEXO (cierres con evidencia
revertida, aprobaciones deshechas, rechazos por infraestructura). Primera semana, calibración de Claude
(`python -m nucleo.kuzushi calibrar Kxxxx util|no_util "motivo"`); luego, como mucho 3 tareas al día y nunca con el freno.
Resumen semanal en el Centro y casos en `/kuzushi`. Para medir prompts: `memoria/kuzushi/T1021_prompts.json`.

## 4. Lado Claude
- **Chat coordinador (NEXO):** sistema, decisiones, artefactos y revisiones. **Chat de monetización:** su propio handoff,
  `claude/handoff-monetizacion-2026-10-17.md`.
- **Claude Code en el PC:** CLAUDE.md, skills superpowers y caveman (solo con `/caveman`), MCP Graft para localizar código y
  hook de comandos largos en segundo plano.
- **Tipos de artefacto:** Slides, Docs, Design, Design System y Dashboard.

## 5. Lo que NO tenemos (huecos)
- Vídeo generado por IA.
- App nativa. La web por Tailscale hace de app.
- Descargar imágenes generadas en las webs de IA.
- Voz que convenza a Damián.
- Radares activos (en pausa).
- Agentes Kuzushi y Kaizen (T1011).

## 6. Por probar

<!-- por-probar:inicio (se genera solo: nucleo/reels_destino.py; no editar dentro) -->
Herramientas vistas fuera (sin probar en NEXO). Antes de usar una: investigación o prueba, y lo externo pasa por N04. Si una se adopta, sube a la sección 1 y sale de aquí.

536 entradas.

| Herramienta | Para qué | Coste | Enlace | Quiero X → uso Y |
|---|---|---|---|---|
| /ai-seo | Generar contenidos y metaetiquetas optimizadas para buscadores | gratis | — | Quiero optimizar el SEO de mis webs informativas con IA → /ai-seo |
| /anti-ui-slop | Evitar estéticas genéricas en la generación de componentes e interfaces | gratis | — | Quiero evitar diseños genéricos en mis proyectos web → /anti-ui-slop |
| /content-strategy | Estructurar e idear estrategias de contenido completas para redes sociales | gratis | — | Quiero planificar la estrategia de mi canal divulgativo → /content-strategy |
| /find-skills | Buscar y descubrir nuevas skills o comandos disponibles | gratis | — | Quiero descubrir nuevas integraciones para mi agente → /find-skills |
| /video-lens | Extraer transcripciones y sintetizar vídeos de YouTube en chat | gratis | — | Quiero resumir tutoriales largos de desarrollo rápido → /video-lens |
| /video-use | Estructurar y optimizar la utilización de piezas de vídeo | gratis | — | Quiero organizar la producción de guiones de vídeo → /video-use |
| 21st.dev | Acelerar el prototipado y diseño frontend copiando componentes UI animados con IA | desconocido | https://21st.dev | Quiero usar componentes UI animados listos para copiar → 21st.dev |
| 3DEXPERIENCE ID | Crear identidad única gratis para desbloquear formación y servicios de Dassault Systèmes | gratis | — | Quiero crear mi 3DEXPERIENCE ID gratis para acceder a MySolidWorks → 3DEXPERIENCE ID |
| 9 AddyOsmaniSkills | 25 flujos de trabajo de nivel senior, desde especificaciones hasta despliegue de aplicaciones | gratis | — | Quiero automatizar flujos de desarrollo de nivel senior en mi proyecto → 9 AddyOsmaniSkills |
| Adobe After Effects | Ejecutar localmente las órdenes de Claude (Reframe, Remove BG, Upscale, Draw to Edit, Edit) y renderizar el resultado final | pago | — | Quiero tener el editor profesional donde la IA aplique ediciones técnicas directamente en la… → Adobe After Effects |
| affaan-m/ECC (Everything Claude Code) | Instalar capa base con 261 skills y 409 agentes (seguridad, testing, research, memory) en Claude Code | gratis | — | Quiero un sistema operativo de agentes listo para usar sin construir cada skill a mano → affaan-m/ECC (Everything Claude Code) |
| affaan-m/Everything Claude Code (ECC) | Harness multi-agente con 64 agentes, 261 skills y 84 hooks para Claude Code, Codex, Cursor y más | gratis | https://github.com/affaan-m/ECC | Quiero un harness multi-agente listo para usar sobre mi backend de IA local → affaan-m/Everything Claude Code (ECC) |
| Agent Reach | Ingerir datos de X, Reddit, Instagram y LinkedIn en tiempo real sin APIs oficiales | gratis | — | Quiero que mi agente lea contenido social en vivo sin pagar APIs ni gestionar claves → Agent Reach |
| AgentCloak | Inspiración de arquitectura para NEXO: sanitizar PII antes de enviar prompts a APIs de LLMs | gratis | — | Quiero usar AgentCloak para sanitizar datos al consultar LLMs → AgentCloak |
| Agente Financiero (JANUS) | Inspira módulo de trading cuantitativo / finanzas personales en NEXO con métricas reales y proyección | desconocido | — |  |
| AIChat | Analizar como caso de estudio sobre interfaces clickbait y evaluar si ofrece acceso gratuito a LLM | desconocido | https://ark.ai/agents?id=5af9dadb-bee2-4960-acbf-64a707cbe7b3 | Quiero probar la plataforma AIChat → AIChat |
| Ajax | Evaluar el comportamiento de un LLM sin restricciones de seguridad en tareas abiertas | gratis | — | Quiero probar un modelo local abliterado → Ajax |
| albertshiney/websitegenerator | Generar sitios web personalizados a partir de datos de Google Maps para prospección | gratis | https://github.com/albertshiney/websitegenerator | Quiero generar webs a medida automáticamente para hacer prospección masiva → albertshiney/websitegenerator |
| Alchemist Accelerator | Aceleradora enfocada en ayudar a startups SaaS a vender a grandes empresas y generar ingresos recurrentes (ARR) | pago | — | Quiero explorar Alchemist para monetizar NEXO vía ventas enterprise → Alchemist Accelerator |
| Alexaiupdates/Anti-AI | Elimina señales que indiquen que el texto fue generado por IA, haciendo el output más humano | gratis | — | Quiero ocultar indicios de generación IA -> uso Anti-AI → Alexaiupdates/Anti-AI |
| Alexaiupdates/FablePrompter | Aplica el mismo nivel de pulido a prompts para la versión Fable5 de Claude | gratis | — | Quiero pulir prompts para Claude Fable5 -> uso FablePrompter → Alexaiupdates/FablePrompter |
| Alexaiupdates/FreeSkilllibrary | Proporciona un conjunto preconstruido de habilidades para potenciar al agente NEXO | gratis | — | Quiero acceder a una biblioteca de habilidades gratuitas para Claude -> uso FreeSkilllibrary → Alexaiupdates/FreeSkilllibrary |
| Alexaiupdates/Hand Off | Facilita la transferencia de contexto entre conversaciones mediante un documento de handoff | gratis | — | Quiero pasar contexto entre chats sin perder información -> uso Hand Off → Alexaiupdates/Hand Off |
| Alexaiupdates/HowTo | Genera prompts que guían al modelo a describir procesos desconocidos | gratis | — | Quiero guiar al modelo a describir procesos desconocidos -> uso HowTo → Alexaiupdates/HowTo |
| Alexaiupdates/Optimizer4.8 | Optimiza prompts específicamente para el modelo Claude Opus 4.8 | gratis | — | Quiero pulir mis prompts para Claude Opus 4.8 -> uso Optimizer4.8 → Alexaiupdates/Optimizer4.8 |
| Alexaiupdates/WriteaSkill | Encapsula un prompt eficaz como una habilidad reutilizable dentro de NEXO | gratis | — | Quiero crear habilidades reutilizables a partir de prompts -> uso WriteaSkill → Alexaiupdates/WriteaSkill |
| alexgreensh/token-optimizer | Ayuda a identificar y eliminar tokens innecesarios para evitar la degradación del contexto | gratis | https://github.com/alexgreensh/token-optimizer | Quiero limpiar el contexto de ruido y mejorar su calidad → alexgreensh/token-optimizer |
| Alishahryar1/free-claude-code | Usar Claude Code gratis con modelos gratuitos (Nim, OpenRouter, Ollama) | gratis | https://github.com/Alishahryar1/free-claude-code | Quiero usar Claude Code sin pagar suscripción → Alishahryar1/free-claude-code |
| All-in-One composer | Proveer una experiencia integrada de edición con IA | gratis | — | Quiero probar All-in-One composer para una edición más fluida → All-in-One composer |
| Amazon KDP (Kindle Direct Publishing) | Publicar PDFs de coloring books y recibir regalías sin gestionar stock, impresión ni envíos | gratis | — | Quiero auto-publicar en Amazon KDP sin gestionar inventario ni logística → Amazon KDP (Kindle Direct Publishing) |
| Amoeba | Permite colaboración simultánea entre agentes de IA sin sobrescribir el trabajo de otros | gratis | — | Quiero usar Amoeba para coordinar varios agentes → Amoeba |
| anime.js | Crear animaciones fluidas e interactivas en la interfaz web de NEXO | gratis | — | Quiero usar anime.js para animar elementos de la UI → anime.js |
| Apify | Extraer automáticamente guiones y temas que funcionan en la competencia para replicar estructuras ganadoras | freemium | https://apify.com | Quiero scrapear transcripciones de videos virales para investigar mi nicho → Apify |
| AquaVoice | Capturar prompts extensos y chain-of-thought por voz en lugar de escribir, misma función que WisprFlow | desconocido | — | Quiero una alternativa a WisprFlow para dictar prompts y razonamientos a Claude Code por voz → AquaVoice |
| Archify | Diseñar arquitectura limpia y diagramas de flujo con IA | gratis | — | Quiero diagramas de arquitectura limpios con IA → Archify |
| ArchiveBox/ArchiveBox | Guardar snapshots permanentes de páginas (HTML, PDF, capturas) para auditoría e investigación | gratis | https://github.com/ArchiveBox/ArchiveBox | Quiero archivar páginas web completas en local para recuperar contenido si el enlace original muere → ArchiveBox/ArchiveBox |
| Arena Skill | Mejora calidad de respuestas de Claude sin reformular prompts, usando competencia de 100 subagentes | gratis | — | Quiero obtener la mejor respuesta de Claude automáticamente sin iterar prompts → Arena Skill |
| Astra | Producir ilustraciones listas para KDP con contornos negros gruesos, formas simples y fondo blanco limpio | freemium | — | Quiero generar ilustraciones coloring book con modelo Astra: líneas gruesas, formas simples, fondo… → Astra |
| Atom Code | Herramienta de coding (Atom Code) compatible con FreeLLMAPI para probar valor en stack de agentes | desconocido | — | Quiero probar Atom Code para ver si aporta valor a mis agentes de coding → Atom Code |
| Audacity | Edición y limpieza de audio para podcasts o videos | gratis | — | Quiero limpiar ruido de audios automáticamente → Audacity |
| Audio Tools | Convertir, comprimir o cortar notas de voz a formatos estándar para transcribirlas con Whisper | gratis | — | Quiero convertir notas de voz a MP3 para transcribirlas localmente → Audio Tools |
| AutoInvent | Explorar patentes abandonadas, modernizarlas con IA y generar solicitudes provisionales con diagramas para inspirar nuevas invenciones | desconocido | https://autoinvent.app/abandoned-patents | Quiero redescubrir tecnologías olvidadas y patentarlas con IA → AutoInvent |
| AWS Educate | Seguir rutas de aprendizaje gratuitas en computación en la nube e IA | gratis | https://aws.amazon.com/education/awseducate/ | Quiero formarme en AWS sin costo → AWS Educate |
| AWS Lambda | Ejecutar funciones por eventos sin servidor | gratis | — | Quiero ejecutar funciones serverless gratis con AWS Lambda → AWS Lambda |
| Azure | Iniciar cargas de trabajo en la nube con 200$ de creditos gratis sin tarjeta | gratis | https://azure.microsoft.com | Quiero probar Azure gratis con 200$ de creditos iniciales → Azure |
| Background Remover | Preparar iconos, capturas y documentación con fondo transparente sin herramientas de escritorio | gratis | — | Quiero eliminar fondos de imágenes para iconos y capturas → Background Remover |
| Barcode Generator | Crear códigos de barras EAN-13, Code 128 y otros para etiquetar activos, productos o documentos internos | gratis | — | Quiero etiquetar activos y productos con códigos de barras personalizados → Barcode Generator |
| BeFreed | Consumir resúmenes de libros de psicología y técnicos en audio de 15 min durante desplazamientos | freemium | — | Quiero aprender de libros de psicología en audio corto mientras me muevo → BeFreed |
| BigQuery integration | Escalar pronósticos de NEXO a terabytes de datos históricos almacenados en BigQuery | pago | — | Quiero escalar pronósticos a terabytes en BigQuery → BigQuery integration |
| BitNet | Cuantizar y ejecutar modelos en 1.58 bits con bajo consumo de memoria | gratis | — | Quiero experimentar con BitNet para agentes secundarios de NEXO → BitNet |
| Bland AI | Permite a NEXO iniciar llamadas salientes reales para notificar cambios o pedir confirmaciones sin notificaciones push | pago | https://bland.ai | Quiero hacer llamadas telefónicas automáticas con IA para notificaciones críticas → Bland AI |
| Blender | Modelado 3D y animación; generar assets visuales vía agent | gratis | — | Quiero generar modelos 3D usando un agente de IA → Blender |
| Blotato | Automatizar el envío de enlaces e incentivos a seguidores por comentario en redes sociales | desconocido | — | Quiero automatizar la respuesta a comentarios y mensajes directos con IA → Blotato |
| bndkt/sharemystack | Inspirarse en stacks de productividad y desarrollo ajenos para configurar entorno de NEXO | gratis | https://github.com/bndkt/sharemystack | Quiero descubrir stacks de herramientas de otros desarrolladores para inspirar mi entorno → bndkt/sharemystack |
| boykopovar/AnyPS5 | Portar ejecutables de PS5 a Linux/Windows automáticamente | gratis | https://github.com/boykopovar/AnyPS5 | Quiero portar juegos de PS5 a PC automáticamente → boykopovar/AnyPS5 |
| Braden1996/React Native Reproducibility | Reportar y reproducir bugs de compatibilidad si NEXO usa React Native en móvil | gratis | — | Quiero reproducir y depurar bugs de React Native en mi entorno móvil → Braden1996/React Native Reproducibility |
| BrainScaleS-2 | Ejecutar y benchmarkear algoritmos en chip analógico real | desconocido | — | Quiero usar BrainScaleS-2 para benchmarking en NEXO → BrainScaleS-2 |
| Browser Automation (Hermes) | Automatización web real integrada en el agente sin Playwright/Selenium externo; útil para scraping, testing y flujos RPA | gratis | — | Quiero automatización web nativa en mi agente sin dependencias externas → Browser Automation (Hermes) |
| BROWSERUSE | Agente IA que usa webs de forma autónoma (formularios, compras, scraping) para investigación o trading | gratis | — | Quiero automatizar interacciones web complejas con un agente IA → BROWSERUSE |
| Buffer MCP | Publicar vídeos short-form diarios en múltiples plataformas con un solo comando | freemium | — | Quiero publicar contenido en varias redes sociales desde una sola orden → Buffer MCP |
| Bytez | Acceso único a modelos de texto, imagen, video y audio sin gestionar múltiples APIs | gratis | — | Quiero una API única para miles de modelos open source gratis → Bytez |
| C/C++ completion | Ofrecer autocompletado de C/C++ | gratis | — | Quiero instalar C/C++ completion para acelerar la codificación → C/C++ completion |
| C0OLIFY | Desplegar apps (incluyendo NEXO) en servidor propio sin costes de nube | gratis | — | Quiero desplegar mis apps en mi propio servidor sin pagar cloud → C0OLIFY |
| cal.com | Calendario auto‑organizado con sincronización con Google/Outlook | gratis | — | Quiero programar reuniones sin usar SaaS → cal.com |
| CALENDARIO | Integración con Google Calendar u Outlook para permitir al agente leer y escribir eventos | gratis | — | Quiero que mi agente gestione mi calendario en tiempo real → CALENDARIO |
| calesthio/OpenMontage | Automatizar la edición y exportación de clips para videos divulgativos de informática en redes | gratis | https://github.com/calesthio/OpenMontage | Quiero automatizar la edición y exportación de clips para mis videos de informática → calesthio/OpenMontage |
| cap | Grabar pantalla con enlaces compartibles, límite de 5 min gratuito | gratis | — | Quiero crear tutoriales rápidos sin pagar → cap |
| Cerebras | Proveedor de inferencia wafer-scale (Cerebras) con cuota gratis y latencia ultrabaja para Llama vía FreeLLMAPI | gratis | — | Quiero aprovechar la latencia ultrabaja de Cerebras para modelos Llama en NEXO → Cerebras |
| ChatGPT Astra | Plataforma web que permite usar modelos de IA de forma gratuita y sin suscripción | gratis | — | Quiero acceder a múltiples modelos de IA sin costos → ChatGPT Astra |
| chatwoot | Suite de soporte con chat en vivo y correo en un solo lugar | gratis | — | Quiero ofrecer atención a usuarios de NEXO → chatwoot |
| clangd | Proporcionar IntelliSense y navegación para código C/C++ en Antigravity/VS Code | gratis | — | Quiero añadir clangd para autocompletar C/C++ → clangd |
| Class Central | Buscar y comparar cursos con certificado gratis de Harvard, Stanford, MIT, Google, Microsoft | gratis | https://classcentral.com | Quiero buscar y filtrar cursos gratuitos con certificado de universidades top → Class Central |
| Claude Code Open Agent Manager | Permite al creador lanzar un plan y que la IA lo ejecute repetidamente hasta completarlo | desconocido | — | Quiero activar Open Agent Manager para bucles automáticos → Claude Code Open Agent Manager |
| CLAUDE DESIGN | Generación de interfaces de usuario (UI) a partir de descripciones en texto usando Claude | desconocido | — | Quiero generar pantallas de control para mi agente → CLAUDE DESIGN |
| Claude for Startups | Obtener 5 cuentas Pro, 1.000$ API Claude, 5.000$ ClickHouse y 3 meses ElevenLabs | gratis | https://www.anthropic.com/startups | Quiero creditos gratis de Claude API, ClickHouse y ElevenLabs para mi startup → Claude for Startups |
| Claude Motion | Generar reportes animados automaticos (trading, metricas) exportando MP4 para contenido divulgativo | desconocido | — | Quiero transformar PDFs y datos en videos animados editables fotograma a fotograma → Claude Motion |
| Claude Opus | Usarlo en planificación, depuración y cambios multiarchivo, evitando gastar su cuota en tareas mecánicas como renombrar o leer logs | pago | — | Quiero usar Claude Opus para planificación, depuración y cambios multiarchivo → Claude Opus |
| Claude Opus 5.5 | Modelo LLM optimizado para desarrollo con Claude Code, ahorrando tokens y mejorando velocidad en tareas de código | desconocido | — | Quiero usar un modelo más rápido y eficiente para mi flujo de desarrollo agéntico → Claude Opus 5.5 |
| Claude-Fable | Redactar, analizar y generar código con la familia Claude mediante Poe | pago | — | Quiero Claude-Fable para redacción, análisis y coding dentro de Poe → Claude-Fable |
| claude-fable-5.1 | Tareas creativas, redacción y análisis en NEXO sin coste API | gratis | — | Quiero usar Fable 5.1 gratis para escritura creativa en NEXO → claude-fable-5.1 |
| claude-sonnet-5.5 | Tareas complejas de codificación y depuración en desarrollo de NEXO sin coste API | gratis | — | Quiero probar Sonnet 5.5 gratis para coding en NEXO → claude-sonnet-5.5 |
| claude.dev | Consultar blogs, playbooks, vídeos y recursos técnicos oficiales de Anthropic desde una terminal web | gratis | https://claude.dev | Quiero explorar contenido técnico oficial de Anthropic en una interfaz de consola → claude.dev |
| ClaudeVideo | Extrae value propositions y resúmenes de vídeos técnicos para base de conocimiento | desconocido | — | Quiero extraer conocimiento de vídeos de YouTube directamente en Claude Code → ClaudeVideo |
| Clerk | Auth gratuito para gestionar el inicio de sesión en NEXO | gratis | — | Quiero integrar Clerk para autenticación de usuarios en NEXO → Clerk |
| ClickHouse Cloud | Almacenar y consultar metricas, logs o datos de trading a gran escala con 5.000$ creditos | gratis | https://clickhouse.com/cloud | Quiero usar ClickHouse Cloud gratis para analitica de datos masiva → ClickHouse Cloud |
| Cline | Extensión VS Code de coding autónomo (Cline) compatible con FreeLLMAPI para agente en editor | gratis | — | Quiero integrar Cline en VS Code como agente de coding usando FreeLLMAPI → Cline |
| Clixad Agent VM | Ejecutar agentes locales (NEXO) orquestando modelos cloud (Opus, Fable, Gemini, DeepSeek) sin coste API propio | gratis | https://console.cloud.google.com/compute/instances/clixad-agent-vm?projectNumber=7610828240168 | Quiero usar modelos premium gratis en NEXO sin pagar API → Clixad Agent VM |
| Cloud Mem | Evita volver a explicar el proyecto cada día, manteniendo el contexto | desconocido | — | Quiero que Claude recuerde el contexto entre sesiones → Cloud Mem |
| Cloud Setup | Identifica carencias en el proyecto para mejorar la asistencia de Claude | desconocido | — | Quiero que Claude detecte faltas y sugiera mejoras en mi proyecto → Cloud Setup |
| Cloudflare Pages | Publicar sitios sin límite de tráfico | gratis | — | Quiero hostear un sitio estático sin límites → Cloudflare Pages |
| Cloudflare Workers | Deploy de código edge con baja latencia | gratis | — | Quiero desplegar workers edge gratis con Cloudflare → Cloudflare Workers |
| CloudflareR2 | Guardar staticos sin pagar ancho de salida | gratis | — | Quiero hosting de objetos gratis sin cargos de salida → CloudflareR2 |
| CloudFront | Distribuir contenido global gratis | gratis | — | Quiero un CDN gratuito con 1TB de tráfico → CloudFront |
| cobusgreyling/nemotron-3.5-lightning | Ejecutar tareas de codificación rápidamente en local | gratis | https://github.com/cobusgreyling/nemotron-3.5-lightning | Quiero automatizar código con máxima velocidad local → cobusgreyling/nemotron-3.5-lightning |
| code_execution (tool Hermes) | Tool de Hermes para ejecutar Python arbitrario; permite procesamiento de datos local sin sandbox externo | gratis | — | Quiero ejecutar código Python local dentro de skills de Hermes para procesamiento de datos → code_execution (tool Hermes) |
| Codex | Usar Codex para autogenerar, ejecutar y previsualizar código dentro del flujo de desarrollo de NEXO | pago | — | Quiero emplear Codex para autogenerar y ejecutar código automáticamente → Codex |
| CODEX CLI | Interactuar con modelos locales vía línea de comandos | gratis | — | Quiero manejar modelos locales con CODEX CLI → CODEX CLI |
| Composer | Facilitar edición y generación de código mediante IA | gratis | — | Quiero usar Composer para crear snippets automáticamente → Composer |
| Compress PDF | Reducir el peso de PDFs antes de indexarlos en la base de conocimiento local de NEXO o enviarlos por email | gratis | — | Quiero comprimir PDFs grandes antes de indexarlos en la base de conocimiento → Compress PDF |
| Conector personalizado de Claude | Conectar la interfaz de Claude a servidores MCP externos (ej. Composio) para exponer herramientas remotas al modelo | gratis | — | Quiero añadir un conector MCP personalizado en Claude para acceder a herramientas externas → Conector personalizado de Claude |
| Console (Anthropic Console) | Gestionar API keys, usage y workspaces de Anthropic para integración vía API | gratis | — | Quiero administrar claves de API de Anthropic para usar modelos en NEXO → Console (Anthropic Console) |
| Context Mode | Modo conciso que ahorra 98% tokens en consultas rápidas (precios, datos, definiciones) | desconocido | — | Quiero reducir drásticamente el uso de tokens en consultas rápidas → Context Mode |
| ControlNet QR Monster | Generar imágenes QR artísticas mediante IA | desconocido | — | Quiero crear códigos QR artísticos con ControlNet → ControlNet QR Monster |
| crccglobal.com | Explorar oportunidades de prácticas en Asia y Europa | desconocido | https://crccglobal.com | Quiero encontrar prácticas profesionales en el extranjero → crccglobal.com |
| Crush | Herramienta de coding (Crush) compatible con FreeLLMAPI para evaluar en flujo de trabajo local | desconocido | — | Quiero probar Crush para ver si encaja en mi stack de agentes de coding local → Crush |
| Cua Fleets | Permite desplegar múltiples instancias del agente NEXO en paralelo para pruebas de carga o trading | desconocido | — | Quiero desplegar NEXO con Cua Fleets → Cua Fleets |
| Cua SDK and CLl | Facilita la integración de Cua en el flujo de trabajo de desarrollo de NEXO | desconocido | — | Quiero integrar Cua SDK en mi flujo de desarrollo → Cua SDK and CLl |
| Cua Spaces | Provee un entorno aislado donde el agente NEXO puede operar sin tomar el mouse del usuario | desconocido | — | Quiero usar Cua Spaces para sandbox de NEXO → Cua Spaces |
| CUA-S1 | Mejora la capacidad de razonamiento del agente NEXO para acciones de automatización | desconocido | — | Quiero usar CUA-S1 para decisiones de automatización → CUA-S1 |
| CuaBench | Permite medir y mejorar el desempeño de NEXO en tareas de automatización | desconocido | — | Quiero benchmarkear NEXO con CuaBench → CuaBench |
| CuaDriver | Facilita la ejecución de tareas de prueba y validación para NEXO sin robar el foco | desconocido | — | Quiero automatizar UI con CuaDriver → CuaDriver |
| Cult-ui | Librería de componentes React/Next.js para landing pages con animaciones Framer Motion, accesibles, instalables vía shadcn CLI | gratis | https://cult-ui.com | Quiero componentes de landing listos para producción para generar páginas completas sin escribir… → Cult-ui |
| D4Vinci/Scrapling | Extraer datos web evadiendo Cloudflare y Captchas para alimentar agentes de IA | gratis | https://github.com/D4Vinci/Scrapling | Quiero scrapear sitios con captchas sin ser bloqueado → D4Vinci/Scrapling |
| dani-garcia/vaultwarden | Gestionar contraseñas, claves API y credenciales de trading en vault propio ligero y seguro (Rust) | gratis | https://github.com/dani-garcia/vaultwarden | Quiero guardar mis claves API y credenciales de trading en un gestor propio tipo Bitwarden → dani-garcia/vaultwarden |
| Dashlane | Analizar estructura de precios tiered (Essentials, Advanced, Premium, Family) como caso de estudio para aplicar modelo de precio decreciente | freemium | — | Quiero ver un ejemplo real de planes de suscripción escalonados en B2C → Dashlane |
| Davanni-Claude/Antigravity | Provee la plataforma donde se configura Claude Code y se ejecuta el bucle de trabajo continuo | gratis | — | Quiero usar Antigravity para ejecutar Claude Code → Davanni-Claude/Antigravity |
| debpalash/VoiceStudio | Clonación de voz y transcripción local (alternativa a ElevenLabs) para generar audio en contenido de NEXO | gratis | https://github.com/debpalash/VoiceStudio | Quiero clonar voces y transcribir vídeos localmente sin enviar datos a la nube → debpalash/VoiceStudio |
| DedSecInside/TorBot | Explorar y extraer sitios en la red Tor a partir de una dirección onion | gratis | https://github.com/DedSecInside/TorBot | Quiero probar TorBot para mapear enlaces onion → DedSecInside/TorBot |
| deepseek-v4-flash | Coding y razonamiento open-source gratis en NEXO; alternativa local-first | gratis | — | Quiero usar DeepSeek V4 Flash gratis como alternativa open en NEXO → deepseek-v4-flash |
| defaults/configure | Repo de configuración (posiblemente dotfiles o setup base) de 'defaults'; utilidad por determinar tras inspección | desconocido | https://github.com/defaults/configure | Quiero ver la configuración base del repo configure de defaults → defaults/configure |
| Dengzheng122/lemo-opuscar | Experimentar con estéticas cinematográficas programáticas para intros/outros | gratis | https://github.com/Dengzheng122/lemo-opuscar | Quiero aplicar estilos cinematográficos programáticos a mis videos → Dengzheng122/lemo-opuscar |
| Descript | Recibir MP4 de Claude Motion, editar voz/guion editando texto, publicar shorts/vídeo automaticamente en pipeline NEXO | freemium | https://descript.com | Quiero editar videos generados cortando y moviendo segmentos modificando solo la transcripcion → Descript |
| Developer Tools | Formatear JSON/XML, generar hashes y codificar Base64 para depurar payloads y logs de APIs | gratis | — | Quiero formatear JSON y codificar datos para depurar mis APIs → Developer Tools |
| DiagramDesign | Generar diagramas editoriales desde un solo prompt | gratis | — | Quiero crear diagramas editoriales rápido con IA → DiagramDesign |
| Dipsy | Backend gratuito para Claude Code vía OpenRouter | gratis | — | Quiero usar el modelo Dipsy gratis en Claude Code → Dipsy |
| Do I Make Myself Clear? | Aprender a editar y estructurar textos para que se entiendan a la primera lectura | pago | — | Quiero mejorar mi escritura técnica con las técnicas de Harold Evans → Do I Make Myself Clear? |
| Draw to Edit | Dar instrucciones visuales precisas a Claude (pintar zona a modificar) evitando prompts de texto complejos | freemium | — | Quiero indicarle a la IA qué editar pintando directamente sobre el vídeo en lugar de escribir… → Draw to Edit |
| drona23/claude-token-efficient | Fuerza respuestas más breves de Claude mediante un archivo de configuración markdown sencillo | gratis | https://github.com/drona23/claude-token-efficient | Quiero hace que Claude responda más corto sin cambiar código → drona23/claude-token-efficient |
| drumih/turbo-fieldfare | Ejecutar Gemma 4 26B-A4B manteniendo <2 GB RAM mediante streaming desde SSD | gratis | https://github.com/drumih/turbo-fieldfare | Quiero probar inferencia de Gemma 4 26B-A4B con turbo-fieldfare → drumih/turbo-fieldfare |
| DynamoDB | Almacenar datos flexibles sin coste inicial | gratis | — | Quiero una BD NoSQL gratuita con 25GB en AWS → DynamoDB |
| EasyGIF | Convertir clip de Google Flow a 30 fps y obtener carpeta de frames numerados listos para animación en canvas | gratis | — | Quiero convertir video a secuencia imágenes 30fps en ZIP sin previsualizar → EasyGIF |
| easymachineai | Comunidad en Skool con recursos y cursos de IA | pago | https://www.skool.com/easymachineai | Quiero acceder a comunidad y recursos de IA en Skool → easymachineai |
| ECC Pro + GitHub App | ECC hosted para repos privados con sync multi-harness, $19/seat/mes, evita self-host | pago | — | Quiero usar ECC en repos privados GitHub sin mantener infraestructura propia → ECC Pro + GitHub App |
| ecc.tools | Documentación oficial y referencia técnica para integrar el harness ECC en NEXO | gratis | https://ecc.tools | Quiero la documentación oficial de ECC para integrar su harness de agentes en NEXO → ecc.tools |
| Edit (Chat to create & edit) | Conversar con Claude en lenguaje natural dentro de AE para que aplique cortes, transiciones, efectos y keyframes | freemium | — | Quiero chatear con la IA dentro de After Effects para que monte el vídeo por mí paso a paso → Edit (Chat to create & edit) |
| EDIT-SOCIAL-GONZALO | Aplicar estilo de edicion consistente a vídeo tecnicos sin reescribir prompts | gratis | — | Quiero reutilizar un skill de edicion predefinido para vídeo tecnicos → EDIT-SOCIAL-GONZALO |
| El ojo de Dios | Visualizar vuelos, cámaras de seguridad y datos globales en vivo | gratis | — | Quiero ver vuelos y cámaras de seguridad globales en tiempo real → El ojo de Dios |
| ElevenLabs | Introducir capacidad de habla natural y salida de voz en texto para NEXO | freemium | — | Quiero que NEXO hable con voz natural usando ElevenLabs → ElevenLabs |
| eltelar.es | Ver demos integradas de las 5 herramientas antes de integrarlas | gratis | https://eltelar.es | Quiero ver ejemplos reales de las 5 tools antes de usarlas → eltelar.es |
| Emil Kowalski design skills | Dotar a NEXO de vocabulario y reglas de diseño coherentes (tipografía, espaciado, layouts, animaciones) al generar interfaces o frontends | gratis | https://emilkowal.ski | Quiero que NEXO genere frontends aplicando reglas de diseño profesionales coherentes → Emil Kowalski design skills |
| emilkowalski/skills | para que NEXO añada animaciones realistas a los sitios generados | desconocido | https://github.com/emilkowalski/skills | Quiero probar la skill en NEXO → emilkowalski/skills |
| Enlace en story y highlights de Opportunities Circle | Acceder a catálogo actualizado de cursos de Stanford con detalles de inscripción | gratis | — | Quiero encontrar cursos de Stanford centralizados → Enlace en story y highlights de Opportunities Circle |
| ENTER/SPACE | Repo 'SPACE' de ENTER; propósito desconocido sin revisar código (posiblemente framework agente/espacio) | desconocido | https://github.com/ENTER/SPACE | Quiero explorar el repo SPACE de la org ENTER → ENTER/SPACE |
| ENTER/SPACL | Repo 'SPACL' de ENTER; propósito desconocido sin revisar código (posiblemente ACL/permisos para SPACE) | desconocido | https://github.com/ENTER/SPACL | Quiero explorar el repo SPACL de la org ENTER → ENTER/SPACL |
| Entorno de recuperación de Windows (WinRE) | Entorno nativo de arranque avanzado para reparar Windows, acceder a símbolo del sistema offline y herramientas de recuperación sin credenciales | gratis | — | Quiero arrancar en modo recuperación para reparar el sistema sin contraseña → Entorno de recuperación de Windows (WinRE) |
| Este repositorio | Dar a NEXO búsqueda web en vivo y acceso a redes sin APIs de pago | gratis | — | Quiero buscar en internet y redes sociales en tiempo real sin pagar APIs → Este repositorio |
| EU Academy | Portal educativo oficial de la UE con cursos gratuitos y recursos de calidad | gratis | https://academy.europa.eu | Quiero acceder a cursos de idiomas gratuitos y certificados de la UE → EU Academy |
| excalidraw/excalidraw | Pizarra virtual colaborativa estilo dibujo a mano para diagramas y brainstorming, alternativa a Miro | gratis | https://github.com/excalidraw/excalidraw | Quiero una pizarra visual colaborativa autoalojada para diagramar sin depender de Miro → excalidraw/excalidraw |
| Excel | Exportar datos a Excel para que el usuario construya dashboards con el método enseñado, o usar Excel como motor de cálculo local | pago | — | Quiero analizar datos y crear dashboards en hoja de cálculo con IA → Excel |
| Expo | Crear, compilar y publicar apps nativas iOS/Android con React Native sin tocar Xcode ni código nativo | freemium | — | Quiero publicar una app React Native en la App Store sin configurar Xcode → Expo |
| Figma MCP | Integrar en NEXO un flujo design-to-code: la IA lee un archivo Figma y genera el frontend correspondiente sin copiar-medir a mano | gratis | — | Quiero que NEXO lea diseños de Figma y genere código frontend automáticamente → Figma MCP |
| Firestore | Tiempo real y sync para apps sin costo | gratis | — | Quiero BD en tiempo real gratis con Firestore → Firestore |
| Forage | Acceder a simulaciones de empleo reales de grandes empresas para validar habilidades y obtener certificados | gratis | https://www.theforage.com | Quiero hacer simulaciones de trabajo reales de empresas top para mejorar mi CV → Forage |
| founder-board | Añadir paso de revisión por board sintético que puntúe propuestas y genere criterios de aceptación | gratis | — | Quiero validar ideas de proyecto con un board sintético que vote y liste riesgos → founder-board |
| founder-competitors | Automatizar análisis de competencia física extrayendo pricing y quejas de reviews públicas | gratis | — | Quiero analizar competencia local de un negocio físico con precios y objeciones reales → founder-competitors |
| founder-consumer | Motor de simulación de user-personas que prueba ofertas y devuelve objeciones para refinar producto | gratis | — | Quiero testear mi oferta contra 100 perfiles sintéticos con ingresos y hábitos reales → founder-consumer |
| Free Claude Code | Utilizar como motor de programación autónomo integrado dentro del ecosistema de NEXO | gratis | — | Quiero integrar Claude Code como asistente de código en NEXO → Free Claude Code |
| Free domain hack | Reclamar subdominios gratuitos y permanentes con acceso DNS completo para proyectos personales o de pruebas | gratis | — | Quiero un subdominio gratuito y estable para mis proyectos side → Free domain hack |
| FreeCAD | Ejecutar Taiga-S1 y crear piezas mecánicas | gratis | — | Quiero usar FreeCAD para ejecutar Taiga-S1 → FreeCAD |
| FreeLLMAPI | Acceso gratuito a Gemini, Kimi y más con 7B tokens/mes y cambio de modelo automático al agotar cuota | gratis | https://velvetshark.com | Quiero usar modelos diversos en Claude Code gratis y sin gestionar cuotas manualmente → FreeLLMAPI |
| freellmapi.co/models | Catálogo web en vivo de 635 modelos con ventanas de contexto y presupuestos de tokens gratis para consultar disponibilidad y límites | gratis | https://freellmapi.co/models | Quiero consultar visualmente los modelos disponibles, sus context windows y cuotas gratuitas → freellmapi.co/models |
| fullyscholarships.com | Buscar y acceder a enlaces directos de cursos y becas gratuitas online | gratis | https://fullyscholarships.com/harvard-university-cybersecurity-free-online-course-2025/ | Quiero encontrar más cursos y becas gratuitas online → fullyscholarships.com |
| gbro/gbro-collage-broll | Crear B-roll estilo artesanal animado automáticamente con Gemini | gratis | — | Quiero generar B-roll animado estilo collage automáticamente → gbro/gbro-collage-broll |
| GCPe2-micro | Desarrollo o cargas ligeras sin gasto | gratis | — | Quiero una VM pequeña gratuita en GCP para pruebas → GCPe2-micro |
| Gemini 3 Flash Preview | Modelo de previsualización enfocado en velocidad para pruebas experimentales en NEXO | gratis | — | Quiero probar Gemini 3 Flash Preview para experimentos de velocidad → Gemini 3 Flash Preview |
| Gemini 3.1 Flash Lite | Modelo optimizado para alta velocidad y bajo consumo, complementa a Flash | gratis | — | Quiero usar Gemini 3.1 Flash Lite para tareas de bajo consumo en NEXO → Gemini 3.1 Flash Lite |
| Gemini 3.1Pro(High) | Usado para planificación y razonamiento complejo en modo planningmode | pago | — | Quiero probar Gemini 3.1Pro para tareas de planificación → Gemini 3.1Pro(High) |
| Gemini 3.5 Flash | Modelo principal de alta velocidad y contexto de 1M tokens para tareas agénticas | gratis | — | Quiero usar Gemini 3.5 Flash para razonamiento rápido en NEXO → Gemini 3.5 Flash |
| Gemini CLI | CLI de coding de Google compatible con FreeLLMAPI para usar modelos Gemini vía router local | gratis | — | Quiero usar Gemini CLI para coding con modelos Gemini a través de FreeLLMAPI → Gemini CLI |
| Gemini Flash | Modelo rápido y barato (Gemini Flash) de Google, fallback prioritario para coding rápido en NEXO | gratis | — | Quiero configurar Gemini Flash como modelo de fallback rápido para coding en NEXO → Gemini Flash |
| Gemini-3-Flash | Obtener respuestas rápidas y baratas en tareas simples o de alta frecuencia | pago | — | Quiero Gemini-3-Flash para respuestas rápidas y baratas en tareas simples → Gemini-3-Flash |
| gemini-3.5-flash-lite | Evaluar capacidades de razonamiento para análisis de estrategias trading | gratis | — | Quiero probar Gemini 3.5 Flash Lite gratis para análisis trading → gemini-3.5-flash-lite |
| gemini-3.8-flash | Comparar rendimiento con Gemini local vía Ollama para enrutamiento en NEXO | gratis | — | Quiero comparar Gemini 3.8 Flash gratis vs local para routing NEXO → gemini-3.8-flash |
| Gemma 4 12B Q6 | Ejecutar modelo denso capaz en 12GB VRAM sin MoE | gratis | — | Quiero un modelo denso de 12B para 12GB VRAM → Gemma 4 12B Q6 |
| Gemma 4 26B-A4B | Modelo rápido y eficiente para 16GB VRAM usando arquitectura MoE | gratis | — | Quiero un modelo MoE eficiente para 16GB VRAM → Gemma 4 26B-A4B |
| Generador de tarjeta de prueba (1 minuto) | Prototipar y validar la experiencia de usuario de la tarjeta de fidelización | gratis | — | Quiero generar una tarjeta de puerta para probar el flujo de fidelización → Generador de tarjeta de prueba (1 minuto) |
| getfreesnacks.com | Conseguir snacks gratis mensuales a cambio de reseñas u opiniones | gratis | https://getfreesnacks.com | Quiero recibir snacks gratis en casa para probar y dar feedback → getfreesnacks.com |
| getmaxun/maxun | Scraper sin código que convierte webs en APIs y hojas de cálculo para datos de trading o LLMs | gratis | https://github.com/getmaxun/maxun | Quiero extraer datos de webs sin programar para análisis o LLMs → getmaxun/maxun |
| GIMP | Edición de imágenes; procesar assets visuales masivamente | gratis | — | Quiero editar imágenes por lote mediante comandos → GIMP |
| Git | Controlar versiones del código de NEXO y coordinar cambios con agentes | gratis | — | Quiero usar Git para gestionar el versionado del proyecto → Git |
| GitHub Actions | Automatizar builds y tests | gratis | — | Quiero CI/CD gratuito con GitHub Actions → GitHub Actions |
| GitHub Student Developer Pack | Acceder a multitud de herramientas profesionales de desarrollo, hosting y dominios sin coste | gratis | https://education.github.com/pack | Quiero usar el GitHub Student Pack sin pagar → GitHub Student Developer Pack |
| GitHubPages | Publicar repos como sitios web | gratis | — | Quiero publicar mi portafolio desde GitHub → GitHubPages |
| giving-presentations | Asistir presentaciones en vivo con speaker notes, timing o teleprompter si NEXO actúa como presentador | gratis | — | Quiero asistir presentaciones en vivo con notas, timing o teleprompter → giving-presentations |
| GLM | Familia de modelos de lenguaje potente orientada a tareas complejas de procesamiento | desconocido | — | Quiero probar GLM para tareas de NLP avanzadas → GLM |
| GLM-5.3 | Ejecutar inferencias de LLM localmente sin dependencia de la nube ni suscripciones recurrentes | gratis | — | Quiero instalar y probar GLM-5.3 en mi stack actual → GLM-5.3 |
| Gmail | Cliente de correo para que NEXO lea, busque y extraiga información de emails vía API | gratis | — | Quiero acceder a mis emails programáticamente para que NEXO procese la bandeja de entrada → Gmail |
| Gmail MCP | Leer, organizar y responder emails automáticamente usando FAQs en markdown | gratis | — | Quiero automatizar la gestión y respuesta de mis emails de soporte → Gmail MCP |
| Goal | Añadir un carrusel de noticias locales de Austin en el panel de control y mantener a Claude trabajando hasta que un segundo modelo verifique la tarea | desconocido | — | Quiero alcanzar objetivos automáticos con Goal → Goal |
| Godot | Crear y gestionar proyectos de videojuegos | gratis | — | Quiero prototipar juegos con instrucciones de texto → Godot |
| goodnightooo/api-anything | Permite a agentes usar cualquier web como API sin API oficial, ahorra tiempo y coste | gratis | https://github.com/goodnightooo/api-anything | Quiero usar sitios web sin API oficial como APIs para mis agentes → goodnightooo/api-anything |
| goodnightooo/cstack | Pendiente de analisis la funcionalidad especifica del repo cstack | gratis | https://github.com/goodnightooo/cstack | Quiero explorar que utilidades ofrece cstack para mi stack tecnologico → goodnightooo/cstack |
| Google (Gemini API) | Proveedor Gemini API de Google con free tier integrado en FreeLLMAPI para cuota gratis de Flash/Pro | gratis | — | Quiero usar la cuota gratis de Gemini API vía router local en NEXO → Google (Gemini API) |
| Google AdSense | Monetizar las páginas web creadas mediante la inserción de anuncios y el cobro por impresiones o clics | gratis | — | Quiero monetizar mis sitios con AdSense → Google AdSense |
| Google AI Studio | Plataforma para crear claves API gratuitas e integrar Gemini en NEXO | gratis | https://ai.google.dev | Quiero usar Google AI Studio para crear claves API gratuitas → Google AI Studio |
| Google Cloud | Aprender habilidades de nube e IA y conseguir certificaciones sin coste | gratis | https://cloud.google.com/edu/students | Quiero entrenar en Google Cloud sin pagar → Google Cloud |
| Google Cloud for Startups | Programa de Google para startups que ofrece hasta 350k USD en créditos de cloud para infraestructura y modelos IA como Gemini | freemium | — | Quiero aplicar a Google Cloud for Startups para usar créditos en infraestructura → Google Cloud for Startups |
| Google Colab | Ejecutar notebooks de Python y GPU para entrenar adapters LoRA sin hardware | gratis | — | Quiero ejecutar el pipeline de fine-tuning gratis en la nube → Google Colab |
| Google Docs | Almacenar y visualizar los informes de nichos y palabras clave generados por la IA | gratis | — | Quiero almacenar informes de nichos en Google Docs → Google Docs |
| Google Flow | Generar frame inicial (producto ensamblado) y final (vista explotada) y crear video de transición entre ambos sin salir de la herramienta | gratis | https://labs.google/tools/flow | Quiero generar keyframes y video transición producto ensamblado-explotado con IA de Google → Google Flow |
| Google Maps | Obtener información de empresas locales y alimentar prompts que generen propuestas automatizadas | gratis | — | Quiero usar Google Maps para extraer datos de comercios sin sitio web → Google Maps |
| Google Search Console | Registrar e indexar proyectos web propios en Google | gratis | — | Quiero usar Google Search Console para indexar mis webs → Google Search Console |
| Google Sheets | Hoja de cálculo online para datos estructurados que NEXO puede leer/escribir vía API | gratis | — | Quiero una base de datos tabular simple accesible vía API para que NEXO analice datos → Google Sheets |
| Google Sheets integration | Permitir a usuarios no técnicos (equipo finanzas) generar pronósticos desde NEXO exportando a Sheets | gratis | — | Quiero hacer pronósticos en Google Sheets sin programar → Google Sheets integration |
| google-research/timesfm | Integrar pronósticos zero-shot en NEXO para datos locales (ventas, tráfico, energía) sin entrenar modelos propios | gratis | https://github.com/google-research/timesfm | Quiero integrar pronósticos zero-shot en mis datos locales sin entrenar modelos → google-research/timesfm |
| googleworkspace/cli | Acceder a skills de Google Workspace (Slides, Docs, Sheets) para integración nativa en NEXO | gratis | https://github.com/googleworkspace/cli | Quiero integrar skills de Google Workspace (Slides, Docs, Sheets) en NEXO → googleworkspace/cli |
| Goose | Agente de coding en terminal de Block (Goose) compatible con FreeLLMAPI para refactor y testing | gratis | — | Quiero probar Goose de Block como agente de coding en terminal vía FreeLLMAPI → Goose |
| GPT-5 | Resolver tareas generales de alta calidad con un modelo consolidado vía Poe | pago | — | Quiero GPT-5 en Poe como modelo generalista de alta calidad → GPT-5 |
| GPT-6-Astra | Resolver razonamiento complejo y generación de código mediante el bot premium de Poe | pago | — | Quiero GPT-6-Astra en Poe para razonamiento complejo y código difícil → GPT-6-Astra |
| gpt-6-sol | Alternativa OpenAI en NEXO para tareas donde rinda mejor que Claude/Gemini | gratis | — | Quiero probar GPT-6-Sol gratis como alternativa OpenAI en NEXO → gpt-6-sol |
| Grok Agent | Integrarlo en NEXO para automatizar la ejecución de tareas complejas en la nube | desconocido | — | Quiero integrar Grok Agent en NEXO para automatizar tareas → Grok Agent |
| Grok-4.7 | Procesar contextos largos y tareas con menos restricciones como opción adicional en NEXO | pago | — | Quiero Grok-4.7 en Poe para contexto largo y tareas poco filtradas → Grok-4.7 |
| GSAP | Biblioteca JavaScript para crear animaciones suaves, controladas y complejas en interfaces web y portafolios | gratis | — | Quiero animar letras y elementos del DOM con precisión y suavidad → GSAP |
| Guardián de archivos | Detecta sobrescritura simultánea en archivos compartidos | desconocido | — | Quiero usar Guardián de archivos para evitar conflictos → Guardián de archivos |
| HACKER/INTEL | Repositorio de inteligencia/OSINT para integrar análisis de vulnerabilidades, CVE y superficie de ataque en NEXO | gratis | https://github.com/HACKER/INTEL | Quiero el repo INTEL de HACKER para añadir capacidades OSINT y análisis de CVE a NEXO → HACKER/INTEL |
| HarnessRouter | API unificada para conectar e intercambiar entre diferentes frameworks de agentes (Codex, Claude Code, etc.) | gratis | — | Quiero agnosticidad de proveedores para orquestar agentes con un solo punto de entrada → HarnessRouter |
| harry0703/MoneyPrinterTurbo | Generar vídeos divulgativos de forma automatizada para redes sociales o inspirarse para crear flujos de automatización de medios en NEXO | gratis | https://github.com/harry0703/MoneyPrinterTurbo | Quiero generar vídeos automatizados con IA para redes sociales → harry0703/MoneyPrinterTurbo |
| harshvitra/personalvoice | Adapta el tono del prompt para que refleje tu estilo personal | gratis | https://github.com/harshvitra/personalvoice | Quiero que mis prompts suenen con mi estilo -> uso PersonalVoice → harshvitra/personalvoice |
| Hermes Desktop | Analizar su interfaz y conexión con LM Studio/Ollama para implementar funciones similares en NEXO | gratis | — | Quiero usar Hermes Desktop para probar su integración con modelos locales → Hermes Desktop |
| HermesAgent | Convierte asistentes de chat en agentes capaces de ejecutar acciones y herramientas | gratis | — | Quiero que mi IA ejecute acciones, no solo responda → HermesAgent |
| hesreallyhim/awesome-claude-code | Descubrir y utilizar herramientas o complementos adicionales para la orquestación de IA en NEXO | gratis | https://github.com/hesreallyhim/awesome-claude-code | Quiero ampliar las capacidades de NEXO con plugins → hesreallyhim/awesome-claude-code |
| heygen-com/hyperframes | Generar videos explicativos o demos automatizados a partir de plantillas HTML | gratis | https://github.com/heygen-com/hyperframes | Quiero renderizar HTML a MP4 con animaciones programáticas → heygen-com/hyperframes |
| Higgsfield | Generar miniaturas, imágenes de producto y clips de video directamente desde el chat de Claude o NEXO | desconocido | — | Quiero generar videos e imágenes con IA usando un conector MCP → Higgsfield |
| Higgsfield AI MCP | Integrar capacidades visuales mediante el protocolo MCP en el agente NEXO para orquestación de contenido | desconocido | — | Quiero usar Higgsfield AI MCP para crear páginas web automáticas con IA → Higgsfield AI MCP |
| Higgsfield KATANA | Crear animaciones profesionales (lanzamientos, logos, stats, apps) sin After Effects ni keyframes manuales | freemium | https://higgsfield.ai | Quiero generar motion graphics de calidad broadcast controlando cámara y estilo solo con prompts → Higgsfield KATANA |
| HKUDS/CLI-Anything | Convierte GUIs de cualquier software en CLI para que agentes como Claude las controlen directamente | gratis | https://github.com/HKUDS/CLI-Anything | Quiero que mi agente controle aplicaciones de escritorio sin interfaz gráfica → HKUDS/CLI-Anything |
| HKUDS/LightRAG | Indexar el código y docs de NEXO en grafo de conocimiento para consultas precisas sin alucinaciones | gratis | https://github.com/HKUDS/LightRAG | Quiero que mis agentes locales entiendan la arquitectura del proyecto sin leer todo el repo → HKUDS/LightRAG |
| Homebrew | Instalar dependencias como llama.cpp rápidamente en sistemas macOS/Linux | gratis | https://brew.sh | Quiero gestionar paquetes manualmente en mi terminal → Homebrew |
| Honcho | Gestión de memoria a largo para agentes de IA, permitiendo recordar interacciones | desconocido | — | Quiero que mi agente recuerde conversaciones previas → Honcho |
| Horus | Aprovechar su módulo Cryptotrace para seguimiento de transacciones y ejecutar utilidades de red desde NEXO | gratis | — | Quiero integrar Horus para centralizar investigaciones en la terminal → Horus |
| https://aws.amazon.com/free/ | Acceder a servicios cloud gratuitos para pruebas y despliegues | gratis | https://aws.amazon.com/free/ | Quiero usar AWS Free Tier para lanzar mis prototipos → https://aws.amazon.com/free/ |
| https://claude.ai/install.cmd-oinstall.cmd | Instalar Claude Code rápidamente en entornos Windows o Linux | desconocido | https://claude.ai/install.cmd-oinstall.cmd | Quiero instalar Claude Code en mi máquina → https://claude.ai/install.cmd-oinstall.cmd |
| https://cloud.google.com/free | Utilizar la capa gratuita de Google Cloud para alojar aplicaciones y APIs | gratis | https://cloud.google.com/free | Quiero probar Google Cloud Free para mis proyectos de IA → https://cloud.google.com/free |
| https://connect.composio.dev/mcp | Obtener acceso unificado a 1500+ integraciones (GitHub, Gmail, Notion, Stripe, etc.) mediante un único endpoint MCP público | freemium | — | Quiero conectar mi agente a 1500+ apps con una sola URL MCP → https://connect.composio.dev/mcp |
| Hugging Face | Descargar y gestionar modelos GGUF para ampliar el catálogo local de NEXO | gratis | https://huggingface.co | Quiero acceder a Hugging Face para obtener modelos locales → Hugging Face |
| Hunyuan HY3 | Integrar como LLM externo gratuito vía API para generación de código en NEXO | gratis | https://huggingface.co/tencent/Hy3 | Quiero generar código usando Hunyuan HY3 como LLM gratuito → Hunyuan HY3 |
| hydra-db/open-glean | Búsqueda de memorias y archivos citando fuentes en IA | gratis | https://github.com/hydra-db/open-glean | Quiero buscar contexto unificado con Open-glean → hydra-db/open-glean |
| HyperFrames | Exportar diseños web (hechos con Claude Design) directamente a clips de video sin paso manual de captura de pantalla | desconocido | — | Quiero convertir HTML/CSS a video MP4 automáticamente → HyperFrames |
| iamlukethedev/hermes3d | Visualizar, monitorizar e interactuar con agentes IA en entorno 3D navegable en vez de logs | gratis | https://github.com/iamlukethedev/hermes3d | Quiero visualizar y gestionar mis agentes IA en una oficina 3D navegable → iamlukethedev/hermes3d |
| ibelick/ui-skills | Aplicar pautas de espaciado, tipografía y accesibilidad cuando el agente genere interfaces frontend | gratis | https://github.com/ibelick/ui-skills | Quiero que NEXO genere frontends con mejor diseño visual → ibelick/ui-skills |
| IG Edits app | Añadir subtítulos dinámicos y formateo vertical en el último paso antes de publicar, sin escritorio | freemium | — | Quiero añadir subtítulos y formato vertical a vídeo/TikTok desde el móvil → IG Edits app |
| IHaveADHD | Configura a Claude para dar instrucciones numeradas y sin relleno, ideal para usuarios con ADHD o flujos rápidos | gratis | — | Quiero que mi agente entregue instrucciones más claras, numeradas y directas → IHaveADHD |
| Image Resizer | Adaptar miniaturas y capturas a las medidas exactas que piden YouTube, LinkedIn o el blog | gratis | — | Quiero redimensionar imágenes a las medidas de cada plataforma → Image Resizer |
| imputnet/cobalt | Descarga medios de TikTok, Instagram, YouTube, etc. sin marca de agua, login ni anuncios para datasets o archivado | gratis | https://github.com/imputnet/cobalt | Quiero descargar videos de redes sociales sin marca de agua ni API oficial para datasets → imputnet/cobalt |
| inematds/SlopMonster | Limpiar textos de patrones IA antes de publicar, integrando filtro automático en outputs de NEXO | gratis | https://github.com/inematds/SlopMonster | Quiero detectar y limpiar automáticamente el 'AI slop' en mis textos antes de publicarlos → inematds/SlopMonster |
| Inkscape | Crear y editar gráficos vectoriales para diseño | gratis | — | Quiero generar logos vectoriales con IA → Inkscape |
| Instagram Insights | Extraer métricas detalladas de alcance, guardados e interacciones para auditar contenido | desconocido | https://onboard.windsor.ai/app/instagram | Quiero extraer métricas de Instagram para auditar mi canal de divulgación → Instagram Insights |
| Interview Coder | Entender arquitectura de overlay indetectable para aplicar flags de privacidad en NEXO | pago | — | Quiero probar una app que oculta overlays en capturas de pantalla → Interview Coder |
| J.P. Morgan Investment Banking Job Simulation | Practicar tareas reales de analista junior en M&A y obtener certificado para CV financiero | gratis | — | Quiero simular trabajo de analista en banca de inversión para validar mis habilidades financieras → J.P. Morgan Investment Banking Job Simulation |
| jacky1903002/diagramdesign | Crea diagramas de arquitectura y flujos limpios en HTML/SVG para documentación técnica | gratis | https://github.com/jacky1903002/diagramdesign | Quiero generar diagramas de arquitectura profesionales desde mi agente → jacky1903002/diagramdesign |
| Jakeschincariol/arena-skill | Orquestar torneos de hasta 100 sub-agentes con estrategias diversas para obtener respuestas robustas sin modificar el repo local | gratis | https://github.com/Jakeschincariol/arena-skill | Quiero ejecutar torneos de sub-agentes en Claude Code para mejorar respuestas de código → Jakeschincariol/arena-skill |
| Jakeschincariol/replica-skill | Clonar, testear y mejorar aplicaciones analizando feedback negativo para comercializarlas | gratis | https://github.com/Jakeschincariol/replica-skill | Quiero clonar y mejorar apps usando estas skills → Jakeschincariol/replica-skill |
| JANUS CORE ORCHESTRATOR | Orquestador central que coordina agentes especializados (finanzas, contenido, seguridad) en local | desconocido | — | Quiero un orquestador multi-agente local que separe dominios bajo un núcleo central → JANUS CORE ORCHESTRATOR |
| JayPokale/Chisle | Reducir costes y latencia optimizando el contexto enviado a los LLMs, evitando divagaciones del agente | gratis | https://github.com/JayPokale/Chisle | Quiero reducir el consumo de tokens en las respuestas de NEXO → JayPokale/Chisle |
| jcode | Desarrollar software con agente autónomo, sesiones paralelas y bajo consumo | gratis | — | Quiero un agente de coding local, rápido y eficiente para mi codebase → jcode |
| Jellyfin | Organiza, transmite y reproduce bibliotecas de películas y series desde un servidor propio a cualquier dispositivo compatible | gratis | — | Quiero reproducir mis películas en streaming sin pagar suscripciones → Jellyfin |
| jellyfin/jellyfin | Servidor multimedia libre para streaming a TV, móvil y navegador sin cuotas ni tracking | gratis | https://github.com/jellyfin/jellyfin | Quiero un servidor de medios propio tipo Netflix/Plex pero libre y autoalojado → jellyfin/jellyfin |
| JetBrains | Suite IDEs JetBrains (IntelliJ, PyCharm) compatible con FreeLLMAPI vía plugins para autocompletado gratis | freemium | — | Quiero conectar mis IDEs JetBrains al router local para autocompletado y chat gratis → JetBrains |
| Jev | Enrutar intenciones del usuario o clasificar tareas repetitivas dentro del orquestador de NEXO de forma instantánea y a coste casi nulo | desconocido | — | Quiero enrutar intenciones de usuarios en NEXO de forma rápida y económica → Jev |
| JohnHeibel/ClaudeAnimationBase | Usar ilustraciones consistentes de la mascota Clawd en videos o documentación | gratis | https://github.com/JohnHeibel/ClaudeAnimationBase | Quiero ilustraciones listas de la mascota Clawd para mis videos → JohnHeibel/ClaudeAnimationBase |
| Johnson & Johnson MedTech Robotics & Controls Job Simulation | Demostrar motivación y habilidades específicas en robótica biomédica para aplicaciones en J&J | gratis | — | Quiero simular trabajo en robótica médica para destacar en ingeniería biomédica → Johnson & Johnson MedTech Robotics & Controls Job Simulation |
| JPG To PDF | Compilar capturas o fotos de documentos en un PDF único para luego aplicar OCR local con NEXO | gratis | — | Quiero juntar imágenes en un PDF para procesarlo con OCR → JPG To PDF |
| JPMorgan Chase Data & Analytics Virtual Job Simulation | Practicar análisis de datos financieros con herramientas reales y obtener certificado oficial para el perfil | gratis | — | Quiero hacer análisis de datos financieros reales con certificado JPMorgan → JPMorgan Chase Data & Analytics Virtual Job Simulation |
| JPMorgan Chase Software Engineering Virtual Job Simulation | Experimentar ciclo de desarrollo en entorno bancario real y certificar habilidades técnicas con respaldo de JPMorgan | gratis | — | Quiero simular desarrollo de software en banca con certificado oficial → JPMorgan Chase Software Engineering Virtual Job Simulation |
| Jules | Agente autónomo que escribe, prueba y valida código en segundo plano conectado a GitHub | gratis | — | Quiero automatizar tareas de codificación en GitHub con un agente autónomo → Jules |
| K2 Horizon 3.7B | Ejecutar en CPU sin GPU modelo fuerte en razonamiento y código | gratis | — | Quiero un modelo potente de 3.7B para solo CPU → K2 Horizon 3.7B |
| kanzitelli/rnn-starter | Acelerar prototipo móvil de NEXO si se decide por React Native | gratis | https://github.com/kanzitelli/rnn-starter | Quiero una plantilla React Native lista con navegación y UI para prototipar la app móvil de NEXO → kanzitelli/rnn-starter |
| karak/karak-claude-plugin | Instalar la skill de principios de diseño de Apple para auditar y mejorar la UI de sus proyectos web | gratis | https://github.com/karak/karak-claude-plugin | Quiero usar la skill apple-design en Claude Code para auditar UI → karak/karak-claude-plugin |
| KatrielMoses/MailAccess | Integrar como herramienta local en NEXO para auditar la huella digital y credenciales filtradas de correos electrónicos | gratis | https://github.com/KatrielMoses/MailAccess | Quiero usar MailAccess para rastrear correos y detectar filtraciones → KatrielMoses/MailAccess |
| kickbacks.ai | Monetizar el tiempo de carga de Claude mostrando anuncios y compartir ingresos para cubrir la suscripcion Pro | gratis | — | Quiero ganar dinero mientras espero respuestas de Claude para pagar mi suscripcion → kickbacks.ai |
| Kimi | Crear presentaciones con IA estilo McKinsey | desconocido | — | Quiero generar presentaciones profesionales con IA → Kimi |
| kimi-k2.5 | Probar capacidad contexto largo para analizar bases de código grandes o informes financieros | gratis | — | Quiero testear Kimi K2.5 gratis para contexto largo en NEXO → kimi-k2.5 |
| kimi-k2.7-code | Generación código especializada (plugins NEXO) cuando modelos locales fallen | gratis | — | Quiero usar Kimi K2.7 Code gratis para generar plugins NEXO → kimi-k2.7-code |
| kimi-k3 | Reservar para tareas difíciles desarrollo modelos trading cuantitativo requieran razonamiento premium | gratis | — | Quiero usar Kimi K3 gratis para razonamiento premium trading en NEXO → kimi-k3 |
| kimi-k3-in-c | Demostrar ejecución de modelos gigantes en C mediante streaming desde SSD | gratis | — | Quiero compilar y probar kimi‑k3‑in‑c para streaming de MoE → kimi-k3-in-c |
| Kimmy | Backend gratuito para Claude Code vía OpenRouter | gratis | — | Quiero usar el modelo Kimmy gratis en Claude Code → Kimmy |
| Kitesurf | Ejecutar navegación y scraping de agentes en el edge usando Cloudflare Workers y aislamiento V8 | freemium | https://blog.cloudflare.com/kitesurf | Quiero desplegar agentes de IA en el edge con aislamiento V8 → Kitesurf |
| Kling 01 | Producir footage realista o estilizado que Claude compone en el proyecto de After Effects | freemium | — | Quiero probar Kling v1 para generar vídeo realista y usarlo en mi pipeline de edición automática → Kling 01 |
| kokonut ui | Acelerar el desarrollo del panel de control con componentes UI animados y listos | gratis | — | Quiero emplear Kokonut UI para construir el panel de NEXO rápidamente → kokonut ui |
| Krita | Pintura digital; automatizar pinceladas o capas | gratis | — | Quiero automatizar tareas de ilustración digital → Krita |
| langflow-ai/langflow | Constructor visual de flujos de trabajo IA (agentes, RAG) exportable a API Python para NEXO | gratis | https://github.com/langflow-ai/langflow | Quiero crear pipelines de LLM complejos sin escribir código → langflow-ai/langflow |
| langgenius/dify | Plataforma todo-en-uno para construir apps IA, agentes, flujos y RAG autoalojables para NEXO | gratis | https://github.com/langgenius/dify | Quiero crear y desplegar aplicaciones IA completas en mi servidor → langgenius/dify |
| Learn Anything | Descubrir rutas estructuradas, guías y repos GitHub listos para clonar por tema | gratis | https://learn-anything.xyz | Quiero ver mapas de aprendizaje interactivos con recursos y repos para cualquier tema → Learn Anything |
| leejersey/OneTake | Grabar tutoriales o demos en una sola toma sin edición posterior | freemium | https://github.com/leejersey/OneTake | Quiero grabar videos en una sola toma sin cortes ni edición → leejersey/OneTake |
| leejet/ComfyUI-GGUF | Ejecutar modelos GGUF dentro de ComfyUI | gratis | https://github.com/leejet/ComfyUI-GGUF | Quiero ejecutar modelos GGUF en ComfyUI → leejet/ComfyUI-GGUF |
| letta-ai/claude-subconscious | Añadir persistencia de memoria a largo plazo entre diferentes sesiones de IA dentro de NEXO | gratis | https://github.com/letta-ai/claude-subconscious | Quiero que NEXO recuerde información entre sesiones → letta-ai/claude-subconscious |
| LeulAria/Aria-Icons | Integrar más de 380.000 íconos vectoriales programáticamente | gratis | https://github.com/LeulAria/Aria-Icons | Quiero buscar y añadir íconos SVG con Aria-Icons → LeulAria/Aria-Icons |
| LibreOffice | Crear y editar documentos, hojas y presentaciones automáticamente | gratis | — | Quiero que el agente genere reportes en PDF u Office → LibreOffice |
| LibreTranslate/LibreTranslate | Traducir textos en local y offline sin coste por carácter ni dependencia cloud para prompts y docs | gratis | https://github.com/LibreTranslate/LibreTranslate | Quiero traducir textos en local sin claves API ni coste para prompts multilingües → LibreTranslate/LibreTranslate |
| LiteRT-LM | Runtime on-device para inferencia offline de MiniCPM5-2B en Android/iOS | gratis | — | Quiero ejecutar MiniCPM5-2B en mi móvil sin conexión a internet → LiteRT-LM |
| Llama 70B | Modelo open source Llama 70B (Meta) vía Groq/Cerebras en FreeLLMAPI para razonamiento complejo | gratis | — | Quiero usar Llama 70B para razonamiento complejo cuando modelos propietarios agoten cuota → Llama 70B |
| localsend/localsend | Enviar archivos (modelos, datasets, logs) entre dispositivos en red local sin nube ni internet | gratis | https://github.com/localsend/localsend | Quiero transferir modelos y datasets entre mi PC, servidor y móvil en red local sin internet → localsend/localsend |
| Loop | Configurar una comprobación periódica cada dos horas para buscar noticias tecnológicas de última hora | desconocido | — | Quiero ejecutar comprobaciones cíclicas con Loop → Loop |
| Lume | Ofrece una VM ligera para que el agente NEXO realice tareas sin afectar el sistema host | desconocido | — | Quiero levantar Lume para pruebas de NEXO → Lume |
| lyogavin/airllm | Inferencia local de LLMs grandes (70B+) en GPU de 4-8GB VRAM sin cuantización ni destilación | gratis | https://github.com/lyogavin/airllm | Quiero ejecutar modelos de 70B parámetros en mi GPU de 4GB VRAM → lyogavin/airllm |
| Madhan230205/token-reducer | Comprime el contexto localmente para reducir más del 90% del uso de tokens en Claude Code | gratis | https://github.com/Madhan230205/token-reducer | Quiero comprimir el contexto para ahorrar tokens en Claude → Madhan230205/token-reducer |
| magheralex/StirlingPDF | Kit PDF local con 50+ funciones (unir, dividir, firmar, OCR) para informes y documentación | gratis | https://github.com/magheralex/StirlingPDF | Quiero procesar PDFs localmente con muchas funciones sin subir archivos → magheralex/StirlingPDF |
| MagicMirrorOrg/MagicMirror | Mostrar estado de agentes NEXO, métricas trading, alertas y logs en pantalla/espejo sin navegador | gratis | https://github.com/MagicMirrorOrg/MagicMirror | Quiero un dashboard siempre visible en mi escritorio para monitorizar agentes y trading sin abrir… → MagicMirrorOrg/MagicMirror |
| Make.com | Crear escenarios que conecten NotebookLM, Claude Code u otras APIs sin programar | freemium | — | Quiero automatizar flujos de trabajo entre apps de IA sin escribir código → Make.com |
| Manifest | Monitoriza gasto en APIs (Gemini, ChatGPT, Claude) y activa fallbacks a modelos locales | desconocido | — | Quiero monitorizar el coste en tiempo real de mis sesiones en Claude Code → Manifest |
| Mastery | Marco mental para planificar el aprendizaje a largo plazo y alcanzar maestría en habilidades técnicas y blandas | pago | — | Quiero un sistema mental para dominar cualquier habilidad a largo plazo → Mastery |
| MathWorks Academy | Portal oficial MathWorks para acceder a Onramps gratis, completarlos y descargar certificados PDF | gratis | — | Quiero una cuenta gratuita en la academia oficial de MathWorks para hacer cursos y bajar… → MathWorks Academy |
| MCP | Conectar Claude con WhatsApp, email y otros servicios para asistente personal integrado | gratis | — | Quiero conectar Claude con WhatsApp y email para un asistente personal integrado → MCP |
| memory (tool Hermes) | Tool de gestión de memoria persistente del agente; clave para agente personal local-first tipo NEXO | gratis | — | Quiero guardar contexto entre sesiones en mi agente local NEXO → memory (tool Hermes) |
| Merge PDF | Unir facturas, logs o reportes fragmentados en un único PDF antes de procesarlos con NEXO | gratis | — | Quiero unificar facturas y reportes en un solo PDF → Merge PDF |
| Meta Ads MCP | Consultar gasto y ROAS, lanzar y optimizar campañas desde el briefing | gratis | — | Quiero gestionar mis campañas de Meta Ads mediante un agente de IA → Meta Ads MCP |
| Microsoft Azure | Construir aplicaciones en la nube y usar tecnologías como Azure OpenAI de forma gratuita | gratis | https://azure.microsoft.com/en-us/free/students/ | Quiero crear apps en Azure sin gasto → Microsoft Azure |
| Microsoft for Startups | Escalar infraestructura con 5.000$ creditos Azure tras verificar la empresa | gratis | https://startups.microsoft.com | Quiero acceder a 5.000$ de creditos Azure para mi startup → Microsoft for Startups |
| microsoft/LLMLingua | Comprime prompts y caché KV hasta 20x con mínima pérdida de rendimiento para ahorrar costes | gratis | https://github.com/microsoft/LLMLingua | Quiero comprimir prompts y caché para reducir costes de inferencia → microsoft/LLMLingua |
| mifi/editly | Automatizar el montaje final (cortes, transiciones, superposición de subtítulos) mediante código en lugar de editor visual | gratis | https://github.com/mifi/editly | Quiero montar videos programáticamente con Node.js sin editor visual → mifi/editly |
| mikf/gallery-dl | Descargar en lote imágenes/vídeos de cientos de webs preservando metadatos para datasets de entrenamiento | gratis | https://github.com/mikf/gallery-dl | Quiero descargar masivamente galerías web con metadatos para crear datasets de imágenes → mikf/gallery-dl |
| MiMo-v2.6-Distill-9B Q4 | Ejecutar modelo compacto con visión en 8GB VRAM | gratis | — | Quiero un modelo multimodal de 9B para 8GB VRAM → MiMo-v2.6-Distill-9B Q4 |
| MiMo-V2.6-Pro | Modelo abierto multimodal masivo (1T parámetros) para evaluar capacidades en código y razonamiento complejo | gratis | — | Quiero evaluar este modelo abierto para tareas de código y agentes robustos → MiMo-V2.6-Pro |
| Mimoide | Agente de coding (Mimoide) compatible con FreeLLMAPI para evaluar en tareas específicas experimentales | desconocido | — | Quiero evaluar Mimoide como agente experimental de coding vía FreeLLMAPI → Mimoide |
| Mind Luster | Obtener certificados gratuitos de 300k+ cursos/MOOCs para CV y demostración de habilidades | gratis | https://mindluster.com | Quiero obtener certificados gratis de cursos online para mi CV → Mind Luster |
| MiniMaxM3 | Integrar como proveedor LLM local dentro del orquestador de NEXO en Windows | desconocido | — | Quiero usar MiniMaxM3 como LLM local en NEXO → MiniMaxM3 |
| miqdadbadjuber/anti-slop | Mantener la limpieza del código rechazando patrones redundantes o de baja calidad en la generación | gratis | https://github.com/miqdadbadjuber/anti-slop | Quiero código generador más limpio y sin patrones bobos → miqdadbadjuber/anti-slop |
| Mission Control | Tomar como referencia de interfaz o panel visual para la gestión de agentes locales en NEXO | desconocido | — | Quiero diseñar un dashboard similar a Mission Control para NEXO → Mission Control |
| MistralAl | Uso de modelos Mistral para procesamiento de tareas | freemium | — | Quiero usar Mistral AI para tareas de IA → MistralAl |
| MIT OpenCourseWare Collections | Navegar directo a asignaturas de programación/análisis datos sin perderse en catálogo completo | gratis | — | Quiero navegar colecciones MIT por tema para hallar proyectos Python rápido → MIT OpenCourseWare Collections |
| mksglu/context-mode | Optimiza la ventana de contexto y reduce drásticamente el peso de las herramientas en agentes de código | gratis | https://github.com/mksglu/context-mode | Quiero reducir el uso de tokens en mis agentes de código → mksglu/context-mode |
| ml-explore/mlx | Framework ML optimizado para Apple Silicon; correr MiniCPM5 en Mac/iPhone con máximo rendimiento energético | gratis | https://github.com/ml-explore/mlx | Quiero inferencia nativa y eficiente de MiniCPM5 en dispositivos Apple Silicon → ml-explore/mlx |
| mlx-lm | Ejecutar modelos de lenguaje en dispositivos con Apple Silicon | gratis | — | Quiero inferir modelos con mlx‑lm en Mac → mlx-lm |
| mmehmetisik/ai-text-to-image-generator | Generar imágenes personalizadas sin límites ni registro usando Stable Diffusion (mlx-t-image) | gratis | https://github.com/mmehmetisik/ai-text-to-image-generator | Quiero generar imágenes con Stable Diffusion en local sin límites ni registro → mmehmetisik/ai-text-to-image-generator |
| Modal | Ejecución de cargas pesadas de cómputo o modelos | freemium | — | Quiero usar Modal para cómputo serverless → Modal |
| Modo grabación | Oculta datos sensibles en grabaciones de pantalla en Claude Code | desconocido | — | Quiero usar Modo grabación para demos sin exponer datos → Modo grabación |
| MongoDB | Obtener créditos en Atlas y certificaciones gratuitas para el currículum | gratis | https://mongodb.com/students | Quiero usar MongoDB Atlas sin coste y certificarme → MongoDB |
| motion.dev | Añadir micro‑interacciones y transiciones al pasar el cursor en el frontend de NEXO | gratis | https://motion.dev | Quiero integrar motion.dev para transiciones y drag‑and‑drop → motion.dev |
| motiondivision/motion | Añadir animaciones fluidas a interfaces web y proyectos interactivos | gratis | https://github.com/motiondivision/motion | Quiero agregar animaciones fluidas a mis interfaces web → motiondivision/motion |
| mrousavy/Colorwaver | Mejorar UX visual de NEXO con transiciones fluidas de color en React Native | gratis | https://github.com/mrousavy/Colorwaver | Quiero añadir animaciones de color fluidas con Skia en la UI de React Native de NEXO → mrousavy/Colorwaver |
| muse-spark-app/muse-spark | Generar código en tiempo real sin latencia en local | gratis | https://github.com/muse-spark-app/muse-spark | Quiero codificar módulos localmente sin pagar → muse-spark-app/muse-spark |
| MuseCode | Agente de código de Meta potentialmente útil para generar o refacturar código fuente | desconocido | — | Quiero probar un agente de código alternativo a los actuales → MuseCode |
| musistudio/claude-code-router | Permite enrutar peticiones entre diferentes modelos de IA de forma local como plano de control | gratis | https://github.com/musistudio/claude-code-router | Quiero cambiar entre modelos de IA fácilmente desde Claude Code → musistudio/claude-code-router |
| MxCorpIn/Repolyze | Evaluar calidad, seguridad y arquitectura de repositorios | gratis | https://github.com/MxCorpIn/Repolyze | Quiero auditar repositorios automáticamente con Repolyze → MxCorpIn/Repolyze |
| MySolidWorks | Acceso a +400 lecciones, itinerarios y playlists oficiales de SolidWorks gratis tras registro | gratis | — | Quiero aprender SolidWorks gratis con contenido oficial de Dassault Systèmes → MySolidWorks |
| n8n | Ejecutar y configurar flujos de trabajo de automatización | gratis | — | Quiero que el agente lance flujos de trabajo complejos → n8n |
| N8N MCP | Conectar NEXO a n8n para crear flujos de automatización en lenguaje natural (CRM, email, scraping, alertas trading) | gratis | https://n8n.io/mcp | Quiero automatizar tareas complejas describiéndolas en lenguaje natural sin tocar código n8n → N8N MCP |
| Namecheap | Provee un dominio barato ($12/año) para el proyecto NEXO | pago | — | Quiero registrar un dominio con Namecheap para NEXO → Namecheap |
| Nano Banana 2 | Generar assets rápidos de bajo coste computacional para previsualizaciones en el flujo de trabajo con Claude | freemium | — | Quiero un modelo rápido y barato para hacer previsualizaciones de conceptos antes de usar los… → Nano Banana 2 |
| Nano Banana Pro | Crear imágenes profesionales para presentaciones | desconocido | — | Quiero generar imágenes ilimitadas con IA → Nano Banana Pro |
| NASA | Acceder a contenido multimedia de la NASA sin restricciones para proyectos educativos | gratis | — | Quiero integrar NASA para obtener footage científico gratuito → NASA |
| Nemotron 3 Nano | Opción ligera para tareas rápidas en NEXO sin coste de inferencia | gratis | — | Quiero un modelo pequeño y rápido de NVIDIA gratis → Nemotron 3 Nano |
| Nemotron-3-super-12ob-a12b | Modelo de NVIDIA calidad similar a Claude, gratis vía Nim | gratis | — | Quiero usar Nemotron 3 Super gratis como alternativa a Claude → Nemotron-3-super-12ob-a12b |
| NengoLoihi | Desarrollar y testear aplicaciones para Loihi sin adquirir el chip | gratis | — | Quiero usar NengoLoihi para crear prototipos en NEXO → NengoLoihi |
| Neo4j PARTNER | Almacenamiento estructurado de datos relacionales complejos | freemium | — | Quiero probar Neo4j Aura para datos → Neo4j PARTNER |
| net user | Comando nativo para gestionar usuarios; ejecutado como SYSTEM (tras el bypass) permite cambiar contraseña de cualquier cuenta local con 'net user usuario… | gratis | — | Quiero cambiar la contraseña de un usuario local teniendo privilegios SYSTEM → net user |
| Newsletter mensual de Anthropic | Recibir resumen curado mensual de actualizaciones, how-tos y community spotlights por email | gratis | — | Quiero suscribirme a actualizaciones oficiales de Anthropic sin monitorizar múltiples canales → Newsletter mensual de Anthropic |
| Next.js | Construir frontend React con SSR/SSG y desplegar fácilmente en Vercel para SaaS rápidos | gratis | — | Quiero un framework React full-stack para mi SaaS con buen SEO y rendimiento → Next.js |
| Niko1221/Strata | Ejecutar modelos masivos localmente en Windows sin costos de API | gratis | — | Quiero ejecutar modelos 125B localmente en GPU de 12GB → Niko1221/Strata |
| NikorasuDef/Perfil-personal-citas | Código fuente de un perfil personal con sistema de citas/reservas para estudiar o reutilizar | gratis | https://github.com/NikorasuDef/Perfil-personal-citas | Quiero ver un ejemplo de implementación de perfil personal con sistema de citas → NikorasuDef/Perfil-personal-citas |
| nizos/tdd-guard | Garantizar que los agentes de código en NEXO no confirmen cambios sin haber pasado las pruebas adecuadamente | gratis | https://github.com/nizos/tdd-guard | Quiero que NEXO solo acepte cambios probados → nizos/tdd-guard |
| Nnovoresume | Plantillas CV optimizadas ATS para roles F1 (Grid, Apex, Pod) con checker gratuito | freemium | — | Quiero plantillas de CV validadas por reclutadores F1 y checker ATS gratis para aplicar con mis… → Nnovoresume |
| NotebookLM | Subir documentos (PDF, audio, web) y sintetizar información con citas precisas | gratis | — | Quiero analizar y generar contenido a partir de mis archivos con IA de Google → NotebookLM |
| Notion | Planificar temas, guardar guiones, trackear estado de producción y enlazar assets finales en una sola vista kanban | freemium | https://notion.so | Quiero un calendario editorial y base de conocimiento unificada para mi contenido → Notion |
| ntop/ntopng | Observar tráfico de contenedores NEXO, detectar conexiones anómalas de modelos locales y depurar latencia en trading | gratis | https://github.com/ntop/ntopng | Quiero ver en tiempo real qué conexiones hacen mis modelos locales y contenedores para depurar red… → ntop/ntopng |
| Nvidia Nim | Obtener API key gratis para modelos Nemotron u otros de NVIDIA | gratis | — | Quiero una API key gratuita para modelos de NVIDIA → Nvidia Nim |
| NVIDIA/SkillSpector | Auditar las herramientas y habilidades de NEXO para prevenir fugas de datos o inseguridades en las integraciones | gratis | https://github.com/NVIDIA/SkillSpector | Quiero auditorías de seguridad automáticas en las skill de NEXO → NVIDIA/SkillSpector |
| NVIDIA/SkillSpector/ChefAssistantSkill | Skill de ejemplo con payload malicioso oculto en `scripts/helper.py`; validar que SkillSpector detecta la exfiltración de credenciales en NEXO | gratis | https://github.com/NVIDIA/SkillSpector | Quiero un skill de prueba con malware oculto para validar mi escáner de seguridad de skills → NVIDIA/SkillSpector/ChefAssistantSkill |
| OBS Studio | Grabar y transmitir video; automatizable vía CLI para procesos de NEXO | gratis | — | Quiero automatizar la grabación de pantallas para documentación → OBS Studio |
| Old Book Illustrations.com | Utilizar ilustraciones históricas de libros antiguos como referencias visuales o elementos gráficos en desarrollos propios | gratis | — | Quiero ilustraciones históricas de dominio público para mis diseños gráficos → Old Book Illustrations.com |
| Oopenproject | Gestión de proyectos con diagramas de Gantt y seguimiento de tiempo | gratis | — | Quiero organizar tareas de desarrollo de NEXO → Oopenproject |
| open-higgsfield | Generar videos AI usando modelos de imagen y video, 30 modelos | gratis | — | Quiero producir videos AI sin SaaS costoso → open-higgsfield |
| open-seo | Seguimiento de palabras clave, backlinks y auditorías de sitio para mejorar la visibilidad SEO | gratis | — | Quiero mejorar la visibilidad de mi contenido en buscadores → open-seo |
| openai/codex | Para generar código a partir de lenguaje natural con Claude Code/Codex | gratis | https://github.com/openai/codex | Quiero usar Codex como habilidad → openai/codex |
| OpenBMB/MiniCPM | Modelo híbrido sparse-linear attention para contexto de 1M tokens en local; investigación de arquitecturas eficientes | gratis | https://github.com/OpenBMB/MiniCPM | Quiero probar MiniCPM-SALA para contexto ultra-largo (1M tokens) en local → OpenBMB/MiniCPM |
| opencode/LongCat 2.5 Preview | Generar gráficos y componentes visuales sin pagar | gratis | — | Quiero crear UI localmente con IA gratuita → opencode/LongCat 2.5 Preview |
| OpenHands/OpenHands | Agente IA autónomo que escribe código, ejecuta comandos y navega web para desarrollar NEXO | gratis | https://github.com/OpenHands/OpenHands | Quiero un agente IA que programe y automatice tareas de desarrollo → OpenHands/OpenHands |
| OpenMuse | Agente local de código abierto (basado en Muse de Meta) para probar arquitecturas autónomas y control desde móvil | gratis | — | Quiero un agente que funcione localmente y sea controlable desde el móvil como referencia → OpenMuse |
| OpenVSX | Descargar e instalar extensiones en Antigravity | gratis | — | Quiero buscar extensiones en OpenVSX → OpenVSX |
| openwhispr | Transcripción offline de voz para programar o tomar notas | gratis | — | Quiero dictar código y notas sin conexión → openwhispr |
| Opus | Usar para tareas de alta dificultad y razonamiento complejo en NEXO donde se requiera máxima capacidad | pago | — | Quiero usar el modelo más potente de Claude para razonamiento complejo en NEXO → Opus |
| Opus 5.5 | Modelo de lenguaje grande de Anthropic para razonamiento complejo y generación de código | pago | — | Quiero un modelo potente para razonamiento complejo y código en NEXO → Opus 5.5 |
| OracleCloudArm | Ejecutar apps con recursos dedicados sin costos | gratis | — | Quiero una VM gratuita con 24GB RAM para mis proyectos → OracleCloudArm |
| oraios/serena | Toolkit MCP para recuperación semántica y edición de código en agents de programación | gratis | https://github.com/oraios/serena | Quiero herramientas MCP para recuperar y editar código semánticamente → oraios/serena |
| OSHA Outreach Courses | Encontrar proveedor legítimo y barato para sacar carnet OSHA en fin de semana | gratis | — | Quiero encontrar proveedor autorizado barato para curso OSHA online → OSHA Outreach Courses |
| OVINC-CN/OpenWebUI | Interfaz local tipo ChatGPT compatible con Ollama y OpenAI para interactuar con LLMs de NEXO | gratis | https://github.com/OVINC-CN/OpenWebUI | Quiero una UI local para chatear con modelos LLM privados → OVINC-CN/OpenWebUI |
| Paper | Diseñar e iterar interfaces web y elementos visuales interactivos mediante instrucciones de Claude | desconocido | — | Quiero diseñar sitios web con un lienzo interactivo y agentes de IA → Paper |
| PDF To JPG | Convertir páginas de PDF en imágenes JPG para alimentarlas a modelos de visión locales como LLaVA | gratis | — | Quiero pasar páginas de PDF a imágenes para modelos de visión → PDF To JPG |
| PDF To Word | Convertir PDFs en Word editable para editar plantillas o contratos antes de extraer sus datos | gratis | — | Quiero editar contratos y plantillas en Word tras extraerlos de PDF → PDF To Word |
| Perplexity-Pro-Search | Investigar en la web con respuestas citadas y trazables desde una sola plataforma | pago | — | Quiero Perplexity-Pro-Search para investigar con citas verificables → Perplexity-Pro-Search |
| Pexels | Obtener imágenes y vídeos libres de derechos para usar en los proyectos de NEXO | gratis | — | Quiero usar Pexels para buscar material visual gratuito → Pexels |
| Phi | Conocer modelos eficientes de pesos abiertos | gratis | — | Quiero probar el modelo Phi → Phi |
| Pi-hole | Intercepta y bloquea peticiones DNS maliciosas o de anuncios a nivel de red, mejorando la privacidad y el rendimiento de los dispositivos conectados | gratis | — | Quiero bloquear anuncios y rastreadores en mi red local → Pi-hole |
| pi-hole/pi-hole | Filtrar telemetría de IDEs, navegadores y contenedores; reducir ruido en capturas; aislar entorno de trading | gratis | https://github.com/pi-hole/pi-hole | Quiero eliminar trackers y telemetría de mis herramientas de desarrollo y trading en toda la red… → pi-hole/pi-hole |
| Pinecone | Vector DB gratuito para funciones de IA como embeddings en NEXO | gratis | — | Quiero utilizar Pinecone como base de vectores para IA en NEXO → Pinecone |
| PiRea | Agente (PiRea) compatible con FreeLLMAPI, uso por definir | desconocido | — | Quiero explorar PiRea como agente compatible con FreeLLMAPI → PiRea |
| pitch-deck | Crear pitch decks específicos para inversión/startups y business planning | gratis | — | Quiero crear pitch decks para inversión o planificación de negocio → pitch-deck |
| Plataforma de gestión de passes (interfaz mostrada) | Gestionar segmentación, programación y envío masivo de notificaciones en passes wallet | desconocido | — | Quiero gestionar y programar notificaciones en Wallet sin desarrollar app → Plataforma de gestión de passes (interfaz mostrada) |
| PNG To JPG | Comprimir capturas y diagramas técnicos cambiando PNG a JPG para reducir peso y mejorar carga web | gratis | — | Quiero convertir PNG a JPG para reducir el peso de las capturas → PNG To JPG |
| pnpm | Gestor de paquetes Node.js rápido que mejora las tiempos de instalación y reduce el espacio en disco en proyectos complejos | gratis | — | Quiero instalar dependencias más rápido y optimizar el espacio en disco de mis proyectos Node.js → pnpm |
| Pocket TTS | Clonación de voz y TTS en tiempo real bajando la latencia de la voz del agente | gratis | — | Quiero darle a NEXO una voz rápida y clonable → Pocket TTS |
| Poe | Acceder a bots y modelos premium de varias empresas desde una sola interfaz, sin gestionar claves propias | freemium | — | Quiero Poe como punto único de acceso a modelos premium con planes y puntos → Poe |
| PostHog | Analytics gratuito para rastrear el uso de NEXO | gratis | — | Quiero emplear PostHog para analizar métricas de NEXO → PostHog |
| presentation-creator | Generar diapositivas con enfoque distinto, posible integración nativa con Sentry (2.8K instalaciones) | gratis | — | Quiero generar diapositivas con una skill alternativa de Sentry → presentation-creator |
| presentation-deck | Alternativa genérica para crear decks de diapositivas, evaluar cobertura de necesidades específicas | gratis | — | Quiero crear decks de diapositivas con una skill genérica alternativa → presentation-deck |
| presentation-design | Enfoque en diseño visual y maquetación de diapositivas, complemento a generadores de contenido | gratis | — | Quiero diseñar el aspecto visual y maquetación de mis diapositivas → presentation-design |
| presentational-container-pattern | Generar código frontend (React/Vue) con separación contenedor/presentacional al desarrollar NEXO | gratis | — | Quiero generar código frontend con patrón contenedor/presentacional → presentational-container-pattern |
| Prisma | Gestionar la capa de datos de la aplicación de forma tipada y segura | gratis | — | Quiero gestionar mis bases de datos y migraciones con TypeScript → Prisma |
| PromptMotion | Fuente de patrones de prompting y codigo de animacion para adaptar en proyectos de NEXO o contenido divulgativo | gratis | — | Quiero ver ejemplos reales de prompts y codigo de animaciones hechas con Claude Opus 5.5 → PromptMotion |
| prompts.app | Obtener prompts validados para generar landing pages, portfolios y demos visuales con IA sin escribir codigo desde cero | freemium | https://prompts.app | Quiero prompts listos para crear sitios web cinematicos con IA rapidamente → prompts.app |
| Public Domain Review | Acceder a arte, relatos y música de dominio público para enriquecer contenido divulgativo o referencias culturales | gratis | — | Quiero obras de arte y música de dominio público para mis proyectos creativos → Public Domain Review |
| pypi/heretic-llm | Instala Heretic para eliminar lógica de rechazo en modelos locales con un comando | gratis | — | Quiero decensurar modelos LLM locales con un solo comando → pypi/heretic-llm |
| qiaoliang/mattpocockskills | Habilidades de TDD, code review y arquitectura para mejorar flujos de ingeniería | gratis | https://github.com/qiaoliang/mattpocockskills | Quiero mejorar las prácticas de testing y revisión de código en mis agentes → qiaoliang/mattpocockskills |
| QR Code Generator | Generar QR personalizados de URLs, texto o WiFi para compartir resultados o contactos de NEXO | gratis | — | Quiero generar códigos QR personalizados para compartir enlaces y contactos → QR Code Generator |
| Qwen 3.8 Coder (local) | Escribir código automáticamente en el PC sin suscripciones | gratis | — | Quiero usar un modelo coder local sin cuotas → Qwen 3.8 Coder (local) |
| Qwen 3.8-Max | Modelo gigante con 1M tokens de contexto para tareas que requieren analizar documentos extensos | desconocido | — | Quiero un backend con contexto masivo para análisis profundo → Qwen 3.8-Max |
| Qwen Code | CLI de coding de Alibaba (Qwen Code) compatible con FreeLLMAPI para modelos Qwen vía router local | gratis | — | Quiero usar Qwen Code para coding con modelos Qwen a través de FreeLLMAPI → Qwen Code |
| Qwen Coder | Modelo especializado en coding (Qwen Coder) de Alibaba en FreeLLMAPI para generación de código | gratis | — | Quiero configurar Qwen Coder como modelo de reserva optimizado para coding → Qwen Coder |
| Qwen/Qwen-3.5-9B | Servir como base estable para ejecutar tareas de IA localmente o crear variantes finetuneadas | gratis | — | Quiero usar Qwen como base para experimentos locales → Qwen/Qwen-3.5-9B |
| Qwen3.8-Flash-Next | Backend de inferencia local de alta capacidad para NEXO | desconocido | — | Quiero usar Qwen3.8-Flash-Next como motor de IA local → Qwen3.8-Flash-Next |
| RadixUI | Provides ready‑made primitives so the creator can avoid coding UI details from scratch when building NEXO or other apps | gratis | — | Quiero usar RadixUI para crear interfaces accesibles sin escribir código desde cero → RadixUI |
| Railway | Desplegar la aplicación backend de la startup de forma sencilla y rápida | freemium | — | Quiero desplegar el backend de mi app en la nube → Railway |
| Raspberry Pi | Ejecutar NEXO, Ollama, agentes y sensores 24/7 con bajo consumo y coste reducido | pago | — | Quiero un servidor casero barato y silencioso para correr IA local y automatizaciones siempre… → Raspberry Pi |
| razorback16/openjev | Obtener decisiones de modelos de IA con métricas de confianza | gratis | https://github.com/razorback16/openjev | Quiero orquestar decisiones con confianza usando Openjev → razorback16/openjev |
| react | Gives the creator access to pre‑built primitives to speed up UI development in NEXO | gratis | — | Quiero incorporar BaseUI para acelerar la construcción de la UI de NEXO → react |
| reactive-resume/reactive-resume | Generar y mantener currículos profesionales ilimitados, privados y sin suscripción en infraestructura propia | gratis | https://github.com/reactive-resume/reactive-resume | Quiero crear mi currículum profesional gratis y en privado sin depender de SaaS → reactive-resume/reactive-resume |
| recipe-create-presentation | Crear presentaciones con recetas predefinidas como alternativa a pptx (31.5K instalaciones) | gratis | — | Quiero crear presentaciones usando recetas predefinidas en lugar de pptx → recipe-create-presentation |
| Red Bull On-Premise Sales Job Simulation | Entrenar análisis de datos comerciales y gestión de objeciones en ventas con certificado | gratis | — | Quiero practicar ventas reales analizando datos y manejando objeciones como en Red Bull → Red Bull On-Premise Sales Job Simulation |
| Refero Styles | Biblioteca de 2000+ sistemas de diseño reales para alimentar agentes de IA con tokens de diseño, tipografía y paletas | gratis | https://styles.refero.design | Quiero referencias de diseño reales para que mi agente genere UI coherente → Refero Styles |
| REFRAME | Reencuadrar clips a formato vertical/horizontal al instante mediante orden a Claude, manteniendo el sujeto centrado | freemium | — | Quiero cambiar el aspecto de mis vídeos (16:9 a 9:16) automáticamente sin recortar manualmente → REFRAME |
| regedit (Editor del Registro) | Editor de registro nativo; en WinRE permite cargar hives offline (Archivo > Cargar subárbol) para modificar claves del sistema instalado | gratis | — | Quiero editar el registro de una instalación Windows que no arranca → regedit (Editor del Registro) |
| Remove BG | Aislar sujetos en movimiento para composiciones rápidas ordenadas por Claude sin rotoscopiado manual | freemium | — | Quiero quitar el fondo de mis clips de vídeo con un solo comando de voz/texto a la IA → Remove BG |
| Resend | Envío gratuito de emails para notificaciones de NEXO | gratis | — | Quiero usar Resend para enviar notificaciones por email en NEXO → Resend |
| reticlehq/reticle | Ejecutar pruebas automatizadas sobre la app real y obtener la línea exacta de código a corregir si falla | gratis | https://github.com/reticlehq/reticle | Quiero debugging automático que apunte la línea de error exacta → reticlehq/reticle |
| RevenueCat MCP | Obtener métricas de suscripciones e ingresos de apps móviles en el briefing diario | gratis | — | Quiero obtener métricas de ingresos y descargas de mi app automáticamente → RevenueCat MCP |
| rohitgo0/AI Engineering From Scratch | Bootcamp de IA open source para aprender a construir agentes y servidores MCP desde cero | gratis | — | Quiero aprender ingeniería de IA y agentes manualmente con este repo → rohitgo0/AI Engineering From Scratch |
| Roo Code | Fork de Cline con más features (Roo Code) compatible con FreeLLMAPI para coding autónomo mejorado | gratis | — | Quiero probar Roo Code como alternativa mejorada a Cline para coding autónomo → Roo Code |
| Rotate PDF | Corregir la orientación de PDFs escaneados antes del OCR para mejorar la extracción de texto | gratis | — | Quiero enderezar PDFs escaneados rotados antes de aplicar OCR → Rotate PDF |
| rtk | Comprimir salidas de terminal y trazas antes de enviarlas a Claude Code para ahorrar contexto y coste | gratis | — | Quiero reducir el consumo de tokens al pasar logs a Claude Code → rtk |
| Runway | Alternativa/complemento a Descript para efectos, upscale, lip-sync sobre MP4s de Claude Motion en flujo automatizado NEXO | freemium | https://runwayml.com | Quiero aplicar efectos generativos, upscale y lip-sync a videos generados por codigo en la nube → Runway |
| Rust | Desarrollar núcleos de agentes, CLI tools y sistemas embebidos con control de memoria | gratis | — | Quiero aprender Rust para construir herramientas de IA de alto rendimiento → Rust |
| rustdesk/rustdesk | Escritorio remoto open source para autoalojamiento, alternativa a TeamViewer | gratis | https://github.com/rustdesk/rustdesk | Quiero acceder a mis máquinas remotamente con mi propio servidor sin usar TeamViewer → rustdesk/rustdesk |
| Salt, Fat, Acid, Heat | Entender la ciencia básica de la cocina (sal, grasa, ácido, calor) para improvisar recetas sanas sin seguir instrucciones exactas | pago | — | Quiero cocinar bien entendiendo los fundamentos químicos, no solo recetas → Salt, Fat, Acid, Heat |
| Samba | Permite exponer discos del servidor como carpetas de red accesibles desde Windows, macOS y Linux, actuando como NAS básico | gratis | — | Quiero compartir archivos de mi servidor en la red local → Samba |
| Schedule | Automatizar la ejecución diaria a las 9 a.m. de un pipeline para revisar noticias y actualizar el calendario de su aplicación de escritorio | desconocido | — | Quiero programar la ejecución diaria de tareas con Schedule → Schedule |
| Scholarships - Explore our student and travel scholarships | Buscar y filtrar becas de conferencia y viaje para estudiantes de tecnología en un solo lugar | gratis | — | Quiero encontrar becas de conferencia y viaje para estudiantes de tecnología → Scholarships - Explore our student and travel scholarships |
| searxng/searxng | Búsqueda web privada y local sin seguimiento ni APIs de terceros, ideal para investigación y verificación | gratis | https://github.com/searxng/searxng | Quiero buscar en la web de forma privada y sin rastreo desde mi propio servidor → searxng/searxng |
| Security AuditSkill | Convierte al agente en auditor de seguridad con hallazgos verificados en el código | gratis | — | Quiero que mi agente realice auditorías de seguridad detalladas en mi código → Security AuditSkill |
| SecuritySweep | Audita automáticamente consultas SQL y código generado por IA antes de ejecutar | desconocido | — | Quiero auditar automáticamente vulnerabilidades en código generado por IA → SecuritySweep |
| Seedance 2.0 | Crear clips de vídeo de alta calidad y coherencia temporal para montajes en After Effects vía Claude | freemium | — | Quiero acceder a un modelo de vídeo chino de última generación para generar footage específico → Seedance 2.0 |
| Seedream 4.5 | Generar b-roll, backgrounds o assets visuales de alta calidad que Claude inserta en la timeline de After Effects | freemium | — | Quiero generar clips de vídeo realistas y coherentes con un modelo top para usarlos en mis montajes → Seedream 4.5 |
| Seedream 5.0 Lite | Iterar rápido conceptos visuales antes de escalar a modelos mayores dentro del pipeline automatizado por Claude | freemium | — | Quiero iterar ideas visuales a máxima velocidad con un modelo lite antes de renderear la versión… → Seedream 5.0 Lite |
| Sentry | Tracking gratuito de excepciones para mejorar la estabilidad de NEXO | gratis | — | Quiero usar Sentry para monitorizar errores en NEXO → Sentry |
| SerpApi | Extraer datos de búsqueda de Google para alimentar agentes o proyectos de scraping | freemium | — | Quiero integrar SerpApi para buscar datos web en tiempo real → SerpApi |
| sgl-project/sglang | Framework de serving con function calling nativo y baja latencia; complementa a Hermes para skills complejas | gratis | https://github.com/sgl-project/sglang | Quiero desplegar modelos con function calling nativo y radix attention para skills de agente → sgl-project/sglang |
| shadcn-ui/ui | Allows the creator to quickly add shadcn UI as a skill in their development environment, streamlining component usage | gratis | https://github.com/shadcn-ui/ui | Quiero ejecutar npx skills add https://github.com/shadcn/ui para instalar shadcn UI rápidamente → shadcn-ui/ui |
| Shader Gradient | Editor visual en navegador para crear fondos 3D animados (WebGL/Three.js) y exportar código React, vanilla o CSS ligero | gratis | — | Quiero generar hero sections impactantes con gradientes 3D sin escribir shaders → Shader Gradient |
| shakogegia/React Native WYSIWYG | Incorporar editor rico en NEXO para notas o prompts | gratis | — | Quiero un editor Markdown WYSIWYG listo para usar en React Native para notas y prompts de NEXO → shakogegia/React Native WYSIWYG |
| Siguientes pasos | Sugiere 3 acciones post-tarea para avanzar desarrollo | desconocido | — | Quiero activar Siguientes pasos para planificar tareas → Siguientes pasos |
| Sitio con 50 prompts virales + 1 semana gratis | Acceder a 50 prompts virales validados para generar creativos publicitarios y probar 7 días gratis la plataforma de generación | freemium | — | Quiero generar creativos de anuncios con prompts probados sin partir de cero → Sitio con 50 prompts virales + 1 semana gratis |
| skill desde la bóveda | Para que el usuario obtenga la skill adecuada sin buscar manualmente, ahorrando tiempo en programación, contenido u otras tareas | desconocido | — | Quiero probar la skill de Claude en mi proyecto → skill desde la bóveda |
| Skill-bus | Automatiza informes periódicos: extrae datos, visualiza y genera PDF, Notion, slides | desconocido | — | Quiero encadenar skills para automatizar generación de informes completos → Skill-bus |
| SkillEvaluator | Framework multi-nivel para certificar skills: quality gates deterministas, evaluación semántica, datasets sintéticos y firma. Estándar emergente para catálogo… | gratis | — | Quiero evaluar y certificar skills de agentes IA con quality gates deterministas y firma… → SkillEvaluator |
| skillfish | Instalar fácilmente nuevos plugins o skills en Claude Code desde la consola | gratis | — | Quiero ejecutar skillfish con npx para añadir nuevas skills a Claude Code → skillfish |
| skills.sh | Explorar catálogo abierto de skills, ver leaderboard, stats de instalaciones y agentes compatibles (Claude, Codex, etc.) | gratis | https://skills.sh | Quiero explorar y buscar skills para agentes IA en un catálogo abierto → skills.sh |
| SkillsBuild | Plataforma de IBM para credenciales verificadas en IA, datos y habilidades técnicas | gratis | — | Quiero obtener credenciales verificadas de IBM en IA y datos → SkillsBuild |
| Slack | Usar Slack como canal principal para enviar comandos y recibir respuestas de NEXO | desconocido | — | Quiero interactuar con NEXO enviando mensajes por Slack → Slack |
| SLAM-Lab/SANA-FE | Experimentar con redes neuronales pulsadas sin hardware físico | gratis | https://github.com/SLAM-Lab/SANA-FE | Quiero usar SANA-FE para probar SNN en NEXO → SLAM-Lab/SANA-FE |
| slides-generator | Generador genérico de slides para comparar salida con pptx y elegir la mejor integración en NEXO | gratis | — | Quiero generar diapositivas genéricas para comparar con pptx → slides-generator |
| SmolLM2-1.7B | Base para fine-tuning ligero en Google Colab con QLoRA y 200-500 ejemplos | gratis | — | Quiero un modelo pequeño para entrenar con datos propios sin gastos → SmolLM2-1.7B |
| smtg-ai/claude-squad | Coordinar múltiples agentes locales en paralelo para acelerar tareas de desarrollo en NEXO | gratis | https://github.com/smtg-ai/claude-squad | Quiero paralelizar agentes Claude para desarrollo rápido → smtg-ai/claude-squad |
| SOLIDWORKS | Diseño mecánico profesional, simulación y documentación para ingeniería y prototipos | pago | — | Quiero diseñar piezas y ensamblajes 3D paramétricos para proyectos de ingeniería → SOLIDWORKS |
| SolidWorks Certification Portal | Gestionar certificación SolidWorks y acceder ofertas prácticas de partners Dassault | gratis | — | Quiero gestionar mi certificación SolidWorks y ver ofertas de partners → SolidWorks Certification Portal |
| Soup | Permite afinar modelos locales sin necesidad de servidores costosos | desconocido | — | Quiero afinar modelos locales sin servidores costosos usando Soup → Soup |
| Split PDF | Extraer páginas concretas de informes largos para alimentar con la parte relevante al modelo local | gratis | — | Quiero extraer páginas sueltas de informes PDF largos → Split PDF |
| Spreadsheet PowerfulWebsites | Tener inventario curado de herramientas para automatizar tareas de NEXO o investigación | gratis | — | Quiero una hoja de cálculo curada con webs de IA, dev y diseño para automatizar investigación de… → Spreadsheet PowerfulWebsites |
| Startup Accelerators & Incubators Database | Hojas de cálculo y bases de datos que listan aceleradores e incubadores a nivel global con enlaces directos para aplicar | gratis | — | Quiero obtener la hoja de cálculo de aceleradores para aplicar masivamente → Startup Accelerators & Incubators Database |
| Startup School 2026 | Estudiar lecciones de fundadores top para aplicar a NEXO y proyectos propios de IA local-first | gratis | — | Quiero aprender de fundadores top sobre IA y startups → Startup School 2026 |
| Step 3.7 Flash | Conectarlo a Hermes Agent para ejecutar tareas de automatización gratuitamente | gratis | — | Quiero usar Step 3.7 Flash con Hermes Agent → Step 3.7 Flash |
| Stitch | Genera diseños completos de aplicaciones (UI/UX) a partir de descripciones en lenguaje natural o enlaces | gratis | — | Quiero prototipar interfaces de app rápidamente desde una idea o enlace → Stitch |
| storytold/artcraft | Motor de crafting intencional para artistas, diseñadores y cineastas | gratis | https://github.com/storytold/artcraft | Quiero un motor de crafting para proyectos creativos → storytold/artcraft |
| strata/qwen3.8-flash-next-code | Ejecutar código con Qwen optimizado para Strata | gratis | https://github.com/strata/qwen3.8-flash-next-code | Quiero probar Qwen Coder en local via Strata → strata/qwen3.8-flash-next-code |
| Supabase | Ofrece base de datos y autenticación gratuita para el backend de NEXO | gratis | — | Quiero usar Supabase como backend para NEXO → Supabase |
| supabase/supabase | Backend open-source (Postgres, auth, storage, realtime) para NEXO, alternativa a Firebase | gratis | https://github.com/supabase/supabase | Quiero un backend completo con base de datos y autenticación autoalojado → supabase/supabase |
| synk.today/intern | Registrarse en 1 minuto en pasantía Sync para añadir experiencia a LinkedIn/CV sin experiencia previa | gratis | https://synk.today/intern | Quiero añadir una pasantía de IA a mi LinkedIn/CV al instante sin experiencia previa → synk.today/intern |
| synsense/rockpool | Diseñar y validar arquitecturas neuromórficas sin hardware | gratis | https://github.com/synsense/rockpool | Quiero usar Rockpool para simular chips en NEXO → synsense/rockpool |
| synsense/sinabs | Crear modelos SNN listos para hardware neuromórfico | gratis | https://github.com/synsense/sinabs | Quiero usar Sinabs para entrenar SNN en NEXO → synsense/sinabs |
| t3-oss/create-t3-turbo | Base para construir interfaz web de NEXO con tipado end-to-end y TurboRepo | gratis | https://github.com/t3-oss/create-t3-turbo | Quiero un monorepo base con Next.js, tRPC, Prisma y TurboRepo para la web de NEXO → t3-oss/create-t3-turbo |
| Taiga-S1 | Genera piezas en FreeCAD localmente sin GPU ni conexión | gratis | — | Quiero usar Taiga-S1 para generar piezas CAD → Taiga-S1 |
| Tally | Crear formularios sin código y conectar respuestas a backends como Supabase o webhooks | freemium | — | Quiero formularios bonitos y funcionales sin programar frontend → Tally |
| tashfeenahmed/freellmapi | Router local open source que agrega 34 proveedores gratis en API compatible OpenAI/Anthropic para NEXO | gratis | https://github.com/tashfeenahmed/freellmapi | Quiero router local gratis que una proveedores IA y evite rate limits en Claude Code → tashfeenahmed/freellmapi |
| TaskObserver | Permite que Claude aprenda de mis correcciones y evite errores futuros | desconocido | — | Quiero que Claude ajuste su comportamiento según mis correcciones → TaskObserver |
| TasteSkill | Mejorar estética de interfaces generadas por IA evitando lo genérico | gratis | — | Quiero que mis UIs de IA tengan buen gusto visual → TasteSkill |
| tasteskill.dev | Consultar la API y catálogo de skills disponibles para añadirlos a la configuración de NEXO | gratis | https://tasteskill.dev | Quiero explorar y añadir skills de diseño curados a la configuración de NEXO → tasteskill.dev |
| Telnyx/Telnyx | Gestionar registros DNS y servicios de comunicación vía API, útil para automatizar infraestructura de red | freemium | — | Quiero una API fiable para gestionar DNS y SMS en mis backend → Telnyx/Telnyx |
| teng-lin/notebooklm-py | Acceso programático a NotebookLM para crear notebooks, generar audio, quizzes desde código | gratis | https://github.com/teng-lin/notebooklm-py | Quiero controlar NotebookLM desde Python o terminal para automatizar investigación → teng-lin/notebooklm-py |
| Text Observer | Analiza cómo trabajas con narrado en vivo y métricas semanales para adaptar flujos | desconocido | — | Quiero analizar mis patrones de uso en Claude Code para optimizar flujos → Text Observer |
| Text Tools | Normalizar, limpiar y contar palabras en textos antes de enviarlos al modelo local de NEXO | gratis | — | Quiero limpiar y normalizar textos antes de pasarlos al LLM → Text Tools |
| The Founder's Playbook: Building an AI-Native Startup | Referencia estructurada en 4 etapas (Idea, MVP, Launch, Scale) para fundadores que dirigen agentes IA | gratis | — | Quiero la guía oficial de Anthropic para crear startups IA-native en 2026 → The Founder's Playbook: Building an AI-Native Startup |
| The Laws of Human Nature | Profundizar en leyes del comportamiento humano para mejorar liderazgo, negociación y comprensión de usuarios | pago | — | Quiero entender la naturaleza humana con el marco de Robert Greene → The Laws of Human Nature |
| The Noun Project | Obtener iconos vectoriales gratuitos y curados por humanos para UI, presentaciones o prototipos funcionales | gratis | — | Quiero iconos vectoriales gratuitos y curados por humanos para mi interfaz → The Noun Project |
| The Psychology of Selling | Estudiar principios clásicos de psicología de venta aplicables a negociaciones y relaciones profesionales | pago | — | Quiero aprender los fundamentos de la venta con un clásico de Brian Tracy → The Psychology of Selling |
| Thinking Orbs | Pantalla de carga ligera para apps o webs | gratis | — | Quiero usar una animación de carga ligera en mi aplicación → Thinking Orbs |
| thruwire/foreman | Supervisa coding agents evaluando progreso, pruebas y requisitos | gratis | https://github.com/thruwire/foreman | Quiero supervisar mis agentes de código con Foreman → thruwire/foreman |
| timothymiller/Create T4 App | Arrancar rápido frontend/web full-stack type-safe con deploy en Cloudflare para NEXO | gratis | — | Quiero generar un proyecto full-stack type-safe con Expo, Next.js y Cloudflare rápido → timothymiller/Create T4 App |
| tirth8205/code-review-graph | Proporciona un grafo de inteligencia de código local-first para usar con MCP y CLI en review | gratis | https://github.com/tirth8205/code-review-graph | Quiero un mapa persistente e inteligente de mi codebase local → tirth8205/code-review-graph |
| toeverything/AFFiNE | Base de conocimiento local-first que combina docs, pizarras y bases de datos, alternativa a Notion y Miro | gratis | https://github.com/toeverything/AFFiNE | Quiero una app todo-en-uno local para notas, pizarras y bases de datos que reemplace a Notion → toeverything/AFFiNE |
| TogetherAl | Llamadas a LLMs y generación de contenido vía API | freemium | — | Quiero testear Together AI para inferencia → TogetherAl |
| Toolixy | Caja de utilidades web gratuitas para PDF, imágenes, QR, audio, vídeo y desarrollo sin instalar nada | gratis | https://toolixy.online | Quiero usar Toolixy para tareas de PDF, imágenes y formatos sin instalar nada → Toolixy |
| toon-format/toon | Proporciona un formato JSON compacto y legible por humanos para optimizar prompts de LLMs | gratis | https://github.com/toon-format/toon | Quiero un formato de datos más eficiente para mis prompts → toon-format/toon |
| Traspaso automático | Resume chat al 85% y transfiere a nuevo chat | desconocido | — | Quiero activar Traspaso automático para mantener rendimiento → Traspaso automático |
| trycua/Cua | Permite al creador probar y ejecutar su agente NEXO en un entorno aislado | desconocido | — | Quiero probar Cua en mi entorno de NEXO → trycua/Cua |
| Twilio | Enviar SMS programables y hacer llamadas para notificaciones y autenticación en apps | pago | — | Quiero enviar SMS y llamadas programables desde mi app → Twilio |
| Twingate | Permite conectar al servidor en casa desde cualquier lugar de forma segura mediante identidad, sin configuraciones complejas de VPN tradicionales | freemium | — | Quiero acceder a mi servidor en casa desde fuera de forma segura → Twingate |
| ui | Enables the creator to quickly assemble a design system and UI for NEXO using ready‑made primitives | gratis | — | Quiero integrar shadcn/ui para montar rápidamente el sistema de diseño de NEXO → ui |
| ui.shadcn.com | Provides the creator with a starting point to generate a design system project for NEXO | gratis | https://ui.shadcn.com | Quiero visitar ui.shadcn.com y generar el esqueleto de NEXO → ui.shadcn.com |
| UIUXProMax | Definir estilos, paletas y reglas de UX para cualquier UI con IA | gratis | — | Quiero un sistema de diseño completo para mis UIs con IA → UIUXProMax |
| unclecode/crawl4ai | Scraper IA que transforma webs con mucho JavaScript en datos limpios estructurados para LLMs | gratis | https://github.com/unclecode/crawl4ai | Quiero extraer datos limpios de webs dinámicas para alimentar LLMs → unclecode/crawl4ai |
| Unlock PDF | Acceder a PDFs propios protegidos por contraseña olvidada para indexarlos en NEXO | gratis | — | Quiero desbloquear PDFs propios cuando olvide la contraseña → Unlock PDF |
| uns1oth/Qwen3.5-9B-GGUF | Descargar la versión optimizada (GGUF) de Qwen 3.5 9B para correrla con llama.cpp | gratis | https://github.com/uns1oth/Qwen3.5-9B-GGUF | Quiero descargar el binario GGUF de Qwen 3.5 → uns1oth/Qwen3.5-9B-GGUF |
| uns1oth/Qwen3.8-27B-GGUF | Ejecutar un modelo más potente (27B) localmente si se dispone del hardware necesario | gratis | https://github.com/uns1oth/Qwen3.8-27B-GGUF | Quiero probar Qwen 27B en local → uns1oth/Qwen3.8-27B-GGUF |
| Upscale | Mejorar calidad de footage antiguo o de baja resolución antes de editar con Claude | freemium | — | Quiero escalar mis vídeos a 4K/8K con IA directamente dentro de mi timeline de edición → Upscale |
| v0.dev | Subir ZIP de frames y pedirle que construya secuencia imágenes vinculada al scroll en canvas reproduciendo frame a frame según desplazamiento | freemium | — | Quiero subir ZIP frames y generar código canvas scroll-linked para animación → v0.dev |
| Video Tools | Convertir, comprimir o recortar vídeos en el navegador y extraer fotogramas o audio para analizarlos | gratis | — | Quiero extraer audio y fotogramas de vídeos para analizarlos → Video Tools |
| visitstore.bio/solidworksedu | Página de enlace (linktree) con acceso directo al registro de certificaciones gratis para estudiantes | gratis | https://visitstore.bio/solidworksedu | Quiero acceder rápido al formulario de registro de la semana de certificaciones gratis → visitstore.bio/solidworksedu |
| VisualStudioCode | Alternativa donde se puede instalar la extensión Claude Code para usar el modelo de IA | gratis | — | Quiero programar con VisualStudioCode → VisualStudioCode |
| vllm-project/vllm | Motor de inferencia alto rendimiento con API OpenAI-compatible; servir MiniCPM5 como API local de producción | gratis | https://github.com/vllm-project/vllm | Quiero servir MiniCPM5 como API local de alto rendimiento compatible con OpenAI → vllm-project/vllm |
| Voice mode | Interactuar con el asistente JARVIS de forma manos-libres y ganar velocidad en el briefing matutino | pago | — | Quiero controlar mi asistente de IA por voz sin teclear → Voice mode |
| voicestudio | Clonación de voz local en 646 idiomas, sin conexión | gratis | — | Quiero crear voice‑overs sin pagar por servicios → voicestudio |
| Walmart Global Tech Advanced Software Engineering Job Simulation | Resolver desafíos de arquitectura de sistemas y debugging realistas para CV técnico | gratis | — | Quiero enfrentar retos de ingeniería de software reales de Walmart para mi portfolio → Walmart Global Tech Advanced Software Engineering Job Simulation |
| wckwan/qwen3.5-9b-base-eval-artifacts | Acceder a métricas y datos de evaluación del modelo base para comparar rendimiento | gratis | https://github.com/wckwan/qwen3.5-9b-base-eval-artifacts | Quiero ver los resultados de evaluación de Qwen → wckwan/qwen3.5-9b-base-eval-artifacts |
| WebsiteCloner | Clonar sitios web usando agentes de IA para desarrollo rápido | gratis | — | Quiero clonar cualquier web con agentes de IA → WebsiteCloner |
| weknora | Consultar documentos localmente con LLM sin conexión | gratis | — | Quiero crear una base de conocimientos local para NEXO → weknora |
| Windsor.ai | Integrar métricas de redes sociales en agentes locales y pipelines sin exportar datos manualmente | desconocido | https://mcp.windsor.ai | Quiero integrar métricas de Instagram en Claude usando Windsor.ai → Windsor.ai |
| WisprFlow | Dictar prompts y razonamientos complejos 3-4x más rápido que tecleando, preservando el chain-of-thought completo para instrucciones más ricas a Claude Code | desconocido | — | Quiero dictar prompts largos y pensamientos completos a Claude Code 3-4x más rápido que escribiendo → WisprFlow |
| Word To PDF | Normalizar entradas de usuarios en .docx para que NEXO solo tenga que parsear PDF | gratis | — | Quiero convertir documentos Word a PDF de forma automática → Word To PDF |
| WordPress | Plataforma CMS donde publicar de forma remota y directa los artículos generados por Claude a través de un conector | gratis | — | Quiero crear blogs de forma automática con WordPress y Claude → WordPress |
| Y Combinator | Aceleradora de inicio que ofrece 500k USD en financiación, mentoría y red de contactos para escalar startups pre-semilla y semilla | pago | — | Quiero postular a Y Combinator para obtener fondos y mentoría → Y Combinator |
| yamadashy/repomix | Empaqueta todo el repositorio en un único archivo optimizado para ser leído por modelos de IA | gratis | https://github.com/yamadashy/repomix | Quiero pasar mi repo completo a un LLM en un solo archivo → yamadashy/repomix |
| Zed | Editor colaborativo Zed con IA integrada, compatible con FreeLLMAPI para IDE principal con IA local gratis | gratis | — | Quiero usar Zed como IDE principal con IA gratis vía FreeLLMAPI → Zed |
| zeke/promptmaker | Transforma ideas confusas en especificaciones de tareas claras para Claude AI | gratis | https://github.com/zeke/promptmaker | Quiero transformar ideas confusas en tareas claras -> uso PromptMaker → zeke/promptmaker |
| zilliztech/claude-context | Sirve como MCP de búsqueda para hacer que todo el codebase sea parte del contexto del agente | gratis | https://github.com/zilliztech/claude-context | Quiero darle acceso a todo mi código a los agentes vía MCP → zilliztech/claude-context |
| zilliztech/GPTCache | Implementa caché semántica para reutilizar respuestas de LLMs y ahorrar llamadas repetidas | gratis | https://github.com/zilliztech/GPTCache | Quiero cachear respuestas de LLMs para ahorrar costes y latencia → zilliztech/GPTCache |
| Zoom | Videoconferencias; automatizar reuniones o gestión de llamadas | freemium | — | Quiero automatizar la gestión de reuniones de video → Zoom |
| Zotero | Organizar citas y bibliografía para investigaciones | gratis | — | Quiero gestionar mi bibliografía automáticamente → Zotero |
| ~/.claude/skills/Llamame/SKILL.md | Convierte la capacidad de llamada en una skill reutilizable invocable desde NEXO para automatizar notificaciones o trabajo nocturno 24/7 | gratis | — | Quiero tener una skill reutilizable en Claude Code para que me llame por teléfono y anote cambios → ~/.claude/skills/Llamame/SKILL.md |
<!-- por-probar:fin -->

## 7. Guías prácticas

<!-- guias:inicio (se genera solo: nucleo/reels_destino.py; no editar dentro) -->
Guías con lo práctico de cada tema (fuentes públicas). **Quien diseñe una app o web en NEXO lee antes `guias/diseno-apps.md`**; para prompts, SEO o programar con IA, la suya.

- [Agentes de IA y automatización](guias/agentes.md): 111 consejos
- [Aprender: cursos, estudio y carrera](guias/aprendizaje.md): 19 consejos
- [Contenido y redes](guias/contenido.md): 28 consejos
- [Diseñar apps y webs](guias/diseno-apps.md): 85 consejos
- [Otros consejos prácticos](guias/otros.md): 73 consejos
- [Prompts y uso de modelos de IA](guias/prompts.md): 29 consejos
- [SEO y posicionamiento](guias/seo.md): 10 consejos
- [Trading e inversión (lo que se ve fuera; no es consejo)](guias/trading.md): 76 entradas
- [Programar con IA (vibe coding, agentes de código)](guias/vibe-coding.md): 47 consejos
<!-- guias:fin -->
