# Prompts y uso de modelos de IA

## Lo práctico

<!-- guia:inicio (se genera solo: nucleo/reels_destino.py; no editar dentro) -->
Lo práctico, en una línea cada cosa. Fuentes públicas; nada de esto está probado en NEXO salvo que se diga.

- **AI copy**: Definir voice & tone guide en NEXO y pasar linter (ej. Vale) en CI para detectar frases hechas, repeticiones y tono corporativo hueco
- **ASD-STE100**: Configura ASD-STE100 en CLAUDE.md: frases cortas, una idea por frase, vocabulario común y sin jerga. Obliga a Claude a responder en este formato para explicaciones 100x más claras y reducir ambigüedades
- **Define what done looks like**: Define explícitamente el formato y criterios de finalización esperados en el prompt para evitar ambigüedades en la salida
- **Drop 'think carefully'**: Evita decir 'piensa cuidadosamente'; deja que el modelo gestione su esfuerzo interno para reducir latencia y sobreanálisis
- **em dashes**: Incluir en prompts: 'usa guiones cortos (-) o reescribe sin guiones largos (—)' para copy más natural
- **If deleting a line does not cause Claude to make an immediate mistake, just delete it**: Aplicar la regla de eliminación: si borrar una línea de la instrucción no causa errores inmediatos en el output, debe eliminarse para mantener la prompt ligera
- **Mensaje de instalación para Claude**: Prompt de bootstrap para que Claude instale HyperFrames y Whisper y configure el entorno local de edicion de video automaticamente
- **Opus 5.5 prompting guide**: Guía completa de prompting para Opus 5.5 con técnicas avanzadas para aplicar en agentes y proyectos de IA
- **Para que un sitio web generado con IA no parezca 'vibe coded', hay que pasarle a Claude un prompt…**: Pasar a Claude un prompt negativo exhaustivo (17+ anti-patrones visuales/de contenido) y lista de requisitos obligatorios (dominio, favicon, legal, assets reales) antes de generar sitio
- **Patrón 1: Todo queda atado (cierre total, sin cabos sueltos, final con lazo)**: Evita cierres narrativos perfectos; instruye al modelo a dejar cabos sueltos o hilos argumentales abiertos para romper el patrón de 'cierre total' que delata a la IA (detectado en 93% casos StoryScope)
- **Patrón 2: Explica la moraleja (77% IA vs 52% humanos)**: Prohíbe al modelo explicar la moraleja final; los humanos la omiten casi la mitad de las veces (52%) frente al 77% de la IA, siendo una señal fuerte de detección
- **Patrón 3: Tics por modelo (Claude frena tensión, ChatGPT usa cotilleos, Gemini pinta gris)**: Personaliza el prompt según el modelo: en Claude exige que la tensión suba sin frenos, en ChatGPT veta chismes o cotilleos narrativos, en Gemini pide descripciones ricas en color y contraste para evitar el tono grisáceo
- **Pedir menu de opciones**: Cuando dudes del método, pide a Claude que presente 5-10 alternativas recomendadas para abordar la tarea. Evalúa viabilidad técnica rápidamente, elige una, varias o combina enfoques sin adivinar la mejor ruta
- **Post: Getting the most out of Opus 5.5 in Claude and Claude Code (9 min)**: Artículo/vídeo de 9 min sobre aprovechar Opus 5.5 en Claude y Claude Code; mejorar prompts y flujos para tareas complejas de NEXO
- **Prompt cinemático para motion graphics**: Estructura prompts para video cinemático especificando: tipo de pieza (product launch, logo reveal, animated stats, app showcase), estilo visual (premium, dark glossy), y movimientos de cámara suaves. Usar como plantilla base en NEXO para assets de video consistentes
- **Prompt compression (opcional)**: Activa compresión de prompt opcional antes de enviar al modelo para ahorrar tokens y reducir latencia en proveedores con cuotas ajustadas
- **Prompt de auditoría de vídeo y generación de dashboard HTML**: Ejecuta el prompt en Claude o en un modelo local, alimentando los últimos 10 vídeo con sus métricas. El prompt extrae patrones de éxito, sugiere hooks y compila un archivo HTML con secciones de diagnóstico, ideas de guion y visualizaciones simples. Usa una plantilla estática y guarda el resultado en un bucket accesible
- **Prompt de edición (Mi prompt de edición)**: Prompt de estilo para edicion: titular cada 2-3 segundos, insertar logo de lo nombrado, revisar fotogramas antes de exportar y auto-corregir; usalo como plantilla base para vídeo tecnicos consistentes
- **Prompt estructura: assembled → exploded view**: En Google Flow usar prompt: 'Frame 1: foto estudio producto ensamblado centrado. Frame 2: vista explotada técnica componentes separados en eje ordenado, misma iluminación, cámara y fondo'. Genera keyframes coherentes para cualquier gadget/PCB sin prueba-error
- **Prompt exacto para coloring book KDP (ages 2-5)**: Usa en ChatGPT/Claude/Ollama con Higgs Field Astra: 'Crea portada original libro colorear infantil KDP edades 2-5: animales lindos, dinosaurios, vehículos, objetos simples. Contornos negros gruesos, formas grandes simples, colores brillantes, fondo blanco'. Adapta temática a tu nicho manteniendo estilo contornos gruesos/fondo blanco
- **Prompt para que Claude Code llame**: Indicar a Claude Code: 'Leé la key de Bland del .env y llamame al +5989...' para que inicie la llamada y anote cambios dictados por teléfono mientras estás lejos del teclado
- **prompt-pack.pdf**: Consolidar todos los prompts utilitarios en un único repositorio o proyecto central para garantizar su reutilización inmediata y coherencia en nuevos trabajos
- **Referentes de copywriting: Krug, Priestley, Hormozi**: Crear plantillas de prompt en NEXO basadas en frameworks de copywriting probados: 'Don't Make Me Think' (Krug), 'Oversubscribed' (Priestley), '$100M Offers' (Hormozi) para reescribir salidas con copy efectivo
- **SKILL.md**: Usar este archivo como prompt base para que un agente IA (Claude Code, Graft, etc.) reescriba textos marcados como 'slop' adaptándolos a la audiencia y usando un modelo de distinta familia al generador original
- **Start on medium effort**: Configura el nivel de razonamiento en 'medio' (medium effort) para equilibrar velocidad y calidad en respuestas del agente
- **Think step by step**: Pedir siempre al modelo que resuelva los problemas desglosándolos en pasos pequeños y ordenados para mejorar su capacidad de razonamiento
- **Tres reglas anti-detección para prompts**: Añade siempre este bloque al inicio de prompts de relatos: 1) Deja algo sin cerrar. 2) No expliques la moraleja. 3) Deja crecer el conflicto. Rompe así los 3 patrones narrativos que StoryScope usa para detectar IA con 93% precisión
- **Usar vocabulario tecnico preciso en prompts**: Emplea vocabulario técnico exacto del dominio (ej. 'vignette' en edición de vídeo) en vez de descripciones coloquiales ('haz los bordes más oscuros'). Cada término técnico comprime un proceso entero; cuántos más conozcas, mejor explicas la tarea y mejores resultados obtienes
- **vague hero text**: Exigir propuesta de valor concreta en textos hero; evitar frases vagas tipo 'Transforma tu negocio con IA'. Añadir regla en prompts de NEXO
<!-- guia:fin -->
