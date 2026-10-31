# Programar con IA (vibe coding, agentes de código)

## Lo práctico

<!-- guia:inicio (se genera solo: nucleo/reels_destino.py; no editar dentro) -->
Lo práctico, en una línea cada cosa. Fuentes públicas; nada de esto está probado en NEXO salvo que se diga.

- **/motion**: Usar '/motion' en Claude adjuntando PDF/CSV/JSON y describir la animacion deseada; Claude genera codigo fotograma a fotograma editable. Integrar en NEXO como skill invocable desde cualquier fuente de datos local
- **ARCHITECTURE.md**: Incluye un ARCHITECTURE.md que describa la relación entre componentes, proporcionando una visión de alto nivel que ayude a que la IA genere código coherente y conecte correctamente los módulos de NEXO
- **Brief de diseño**: Especificar paleta, tipografía, componentes y aspecto de cada pantalla en un brief para que el agente genere UI fiel sin inventar estilos
- **CHANGELOG.md**: Utiliza un CHANGELOG.md para registrar cada modificación del proyecto, facilitando la reversión de errores y el seguimiento de la evolución del agente NEXO
- **Commit after every single task**: Realizar un commit tras cada tarea individual completada para facilitar la reversión de errores y evitar la pérdida de trabajo parcial
- **COMPACT**: Ejecuta /compact en Claude Code para resumir la conversación larga y ahorrar millones de tokens, preservando solo el contexto esencial para seguir trabajando
- **Contenido destacado: Building with Claude Sonnet 5.5**: Vídeo de 9 min sobre desarrollo con Sonnet 5.5; estudiar capacidades y patrones de uso para integrar el modelo en NEXO vía Ollama o API
- **Cuatro complementos gratuitos (Ponytail, OmniRoute, Graphify, Agent Skills) solucionan los cuatro…**: Usar 4 plugins gratuitos para corregir vicios de Claude Code: Ponytail (reduce código 53% y coste 26%), OmniRoute (rota modelos para evitar límites), Graphify (crea mapas de proyecto sin gastar tokens) y Agent Skills (fuerza flujo de trabajo ordenado). Instalarlos como complementos en Claude Code
- **custom domain**: Automatizar verificación de DNS apuntando a dominio propio antes de merge; bloquear deploy en subdominios de proveedores
- **Código de animación por fotogramas (scene, title, number, bars, ease)**: Patron de codigo: scene(id, inicio->fin), title(texto), number(valor), bars(array), ease(tipo, duracion). Replicable en NEXO con Manim, Motion Canvas o Remotion para visualizar datos cuantitativos (trading, metricas) de forma determinista y editable
- **DECISIONS.md**: Mantén un DECISIONS.md donde se explique el porqué de cada decisión tecnológica, preservando el contexto y los trade‑offs (p. ej., elección de PostgreSQL) para futuras iteraciones de NEXO
- **Dun Skybridge / Vortexink**: Probar prompts de Dun Skybridge y Vortexink en NEXO para expandir biblioteca de patrones cinematicos validados
- **DynamicIsland**: Integrar el componente DynamicIsland (réplica de Apple) en dashboards o apps para notificaciones/toasts con animaciones complejas ya resueltas; instalable vía shadcn CLI
- **El problema casi nunca es la IA, es la falta de contexto. Si el agente tiene que adivinar, adivina…**: El fallo principal al programar con IA no es el modelo, sino la falta de contexto; si el agente tiene que adivinar, falla. Estos 6 documentos eliminan la improvisación
- **Esquema del backend**: Definir tablas, columnas, relaciones y flujo de autenticación para que el agente construya backend y API correctamente sin improvisar el esquema
- **Explore, write a spec, then code**: Ejecutar tres fases: explorar el código, escribir una especificación clara y solo entonces codificar, optimizando así el uso del contexto
- **Flujo de edición en 4 pasos (Instalar → Cortar → Explicar → Revisar)**: 1) Dar repo a Claude e instalar dependencias. 2) Añadir Whisper y pasar clips crudos para limpieza (silencios, muletillas). 3) Definir estilo: titulares cada 2-3s, logos. 4) Revisar fotogramas antes de exportar y guardar como skill reutilizable
- **Flujo de la app**: Describir fases, navegación, recorrido de usuario e interacciones por pantalla para que el agente entienda el comportamiento completo de la app
- **Guía para crear y publicar la app con Claude Code y Expo**: Usa Claude Code para generar el código de la app (ej. finanzas) y Expo (EAS Build/Submit) para compilar, firmar y subir a la App Store automatizando certificados y perfiles; sigue una guía estructurada para evitar errores de configuración nativa
- **Guía paso a paso: prompt + KATANA setup + MCP + workflow**: Workflow replicable en NEXO: 1) Concepto en LLM razonador, 2) Generar prompt cinemático estructurado, 3) Configurar Higgsfield KATANA (cámara, estilo, duración), 4) Conectar vía MCP para llamada a herramienta, 5) Iterar y renderizar final. Permite crear assets de video bajo demanda sin keyframes
- **HazeOver**: Instala HazeOver en macOS y activa el modo automático; las ventanas de fondo se atenuarán, reduciendo distracciones y permitiendo enfocarte en la ventana activa
- **HOOKS**: Programa hooks que se activen automáticamente al ejecutarse tareas específicas, permitiendo encadenar acciones y reaccionar a eventos sin intervención manual en tu flujo de trabajo
- **Instalación Cult-ui vía shadcn CLI**: Usar `pnpm dlx shadcn@latest add <url-componente>` para instalar componentes remotos de Cult-ui (ej. Dynamic Island) en proyectos shadcn/ui y automatizar scaffoldings
- **Instalación en Claude Code / Codex (npx skills add)**: En Claude Code/Codex: ejecuta `npx skills add https://github.com/vercel-labs/skills --skill find-skills` para instalar find-skills y luego añadir skills de tests, refactor o CI/CD
- **LOOPS**: Escribe bucles (loops) en lugar de prompts simples para que Claude complete una tarea al 100% antes de iniciar la siguiente, asegurando flujos de trabajo automatizados y robustos en NEXO
- **made with AI tag**: Añadir regla que limpie metadatos y UI de atribución a IA en builds de producción
- **Make No Mistakes**: Activar 'strict mode' en system prompt de NEXO: la lista de anti-patrones es requisito mínimo, no opcional; ejecución impecable
- **Mercury Magma Ferrofluid**: Analizar el prompt de Mercury Magma Ferrofluid (y variantes Cobalt) para integrar shaders tipo ferrofluido/magma en la UI de NEXO
- **Never edit files in /generated**: Prohibir la edición manual de archivos en directorios /generated para evitar sobrescribir cambios automáticos del pipeline
- **Pipeline creativo "Claude edita por mí"**: Pipeline semanal: 1) Añadir endpoint MCP de Higgsfield en conectores de Claude. 2) Instalar plugin Higgsfield en After Effects. 3) Escribir órdenes en lenguaje natural (ej. 'haz un reframe vertical', 'quita el fondo', 'añade zoom con keyframes'). 4) Revisar y renderizar en AE. Libera horas de edición manual para vídeo/tutoriales
- **PLAN**: Activa el modo plan (/plan) para que Claude Code muestre paso a paso la ejecución de tareas complejas, permitiéndote revisar y corregir el plan antes de lanzar la ejecución
- **Post: Using Claude Code: The unreasonable effectiveness of HTML (9 min)**: Artículo/vídeo sobre uso efectivo de HTML en Claude Code; aprovechar salidas HTML estructuradas para interfaces o reporting de NEXO
- **PRD**: Crear un PRD detallado con funcionalidades, alcance exacto y resumen de la idea para que el agente no tenga que adivinar qué construir
- **Protect your context window**: Mantener la ventana de contexto limpia y controlada, evitando acumular código o planes obsoletos que degraden la eficacia del modelo
- **README.md**: Mantén un README.md que explique la finalidad del proyecto, el stack tecnológico, cómo instalarlo, sus principales funcionalidades y la organización de los archivos
- **ROADMAP.md**: Crea un ROADMAP.md que detalle los hitos previstos, de modo que el agente NEXO no genere ideas aleatorias y el equipo se mantenga enfocado en el MVP y futuras integraciones
- **Run the tests before you commit**: Ejecutar la suite completa de pruebas antes de crear cualquier commit para asegurar que el código cumple los requisitos funcionales
- **side_quest_app (my life is boring and i want to do a side quest but don't know what)**: Analizar side_quest_app como ejemplo de sitio generado por IA (Manus.im) con tracking SEO, analytics y backend funcional para entender capacidades del vibe coding autónomo
- **site favicon**: Crear script que genere favicon.ico, apple-touch-icon, manifest.json, maskable icon desde SVG maestro y verifique en build
- **SKILL**: Crea 'skills' (habilidades) en Claude Code para tareas recurrentes: enséñale una vez a ejecutarlas y reúsalas automáticamente sin dar instrucciones repetidas cada vez
- **Spikeson**: Probar el prompt de la plantilla Spikeson en NEXO para obtener resultado visual inmediato y extraer patrones de diseno cinematico
- **Stilwater Beacon**: Probar el prompt de Stilwater Beacon (y variante Stiwinter) en NEXO para validar componentes y transiciones cinematicas
- **Summit**: Testear el prompt de la plantilla Summit en NEXO para comparar estructura y animaciones con otras plantillas cinematicas
- **The vídeo lists five essential markdown files—Security, Auth, Data Security, Threat Model, and…**: Crea fichas markdown (Security, Auth, Data, Threat Model, Checklist) para que la IA aplique seguridad antes de programar
- **too much scroll animations**: Definir presupuesto de animaciones (máx. 2 por página) y preferir CSS nativo para evitar lentitud y distracción
- **TRD**: Definir un TRD con decisiones de stack, herramientas y APIs para que el agente implemente sin improvisar arquitectura técnica
- **Wetackwhat**: Probar el prompt Wetackwhat en NEXO para validar salida y reutilizar patrones de layout cinematico
<!-- guia:fin -->
