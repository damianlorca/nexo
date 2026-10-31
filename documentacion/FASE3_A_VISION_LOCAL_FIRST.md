# FASE 3 — A. Replanteamiento de la premisa: Nexo como orquestador local-first

## Crítica honesta a cómo se pensó la Fase 2

Damián tiene razón en el diagnóstico: la Fase 1 y la Fase 2, aunque identificaron correctamente la infrautilización de Qwen, seguían pensando la arquitectura desde el centro de gravedad de Claude — "Claude + herramientas + proveedores auxiliares que le ahorran trabajo a Claude". Se ve en tres decisiones concretas de la Fase 2 que esta fase corrige:

1. **FASE2_A trataba a Qwen como un abaratador de Claude**, no como un centro operativo por derecho propio — el marco era "qué puede quitarle a Claude", no "qué puede hacer Nexo entero sin que Claude se entere".
2. **FASE2_D relegaba el control visual del PC al último lugar del roadmap** por ser "la pieza más nueva y arriesgada" — una decisión razonable bajo la premisa antigua (Claude como cerebro, todo lo demás como periferia prescindible), pero que esta fase reconsidera: si el PC es el centro operativo, la capacidad de que Nexo actúe sobre su propio PC no es un lujo final, es infraestructura (ver sección G).
3. **Ninguna sección de la Fase 2 se preguntó si el propio proceso de "clasificar y decidir" podía vivir permanentemente en local** — el Model Router de FASE2_B estaba diseñado como una función que Claude consultaría, no como un proceso que corre indefinidamente sin que Claude intervenga en cada decisión.

Esta corrección no invalida el contenido de la Fase 2 — el Model Router, los hallazgos de seguridad, el control visual, todo sigue siendo válido como pieza técnica — pero cambia dónde vive el centro de decisión: de "Claude decide y delega" a "Nexo local decide, resuelve lo que puede, y escala solo lo necesario".

## La pregunta correcta, tal como la plantea Damián

> "¿Qué parte del trabajo total de Nexo debería poder resolver localmente antes de gastar una llamada externa?"

Esta pregunta no tiene una respuesta única y fija — depende de qué tan capaz sea el modelo/arquitectura local en cada momento (por eso las secciones B y C de esta fase estudian los modelos y la arquitectura multiagente por separado). Pero sí se puede fijar el **principio de diseño**, que es lo que pide este apartado: el sistema debe estar construido de forma que, según mejore la capacidad local, la proporción de trabajo resuelto sin tocar una IA de pago pueda crecer sin rediseñar nada — es decir, la frontera "qué hace local vs. qué se escala" tiene que ser un parámetro del Model Router (sección E de esta fase), no una decisión grabada en el código.

## Evaluación seria de la hipótesis del punto 24

**Hipótesis planteada:** un sistema de (modelos locales + Claude Pro + ChatGPT + Gemini + otras IAs especializadas + herramientas locales + memoria + router + observabilidad + automatización del PC) puede ser más potente, flexible y versátil que intentar convertir una única IA Pro en el cerebro absoluto.

**Qué parte es cierta:**
- **Capacidad global agregada:** cierto, y no es controvertido — un sistema que combina varios recursos especializados cubre más superficie de tareas que uno solo, siempre que el coste de coordinarlos no se coma la ganancia (ver el matiz de complejidad abajo).
- **Autonomía:** cierto en la medida en que el sistema local no depende de que Damián tenga cuota de Claude disponible, ni de que una sesión de Claude Code esté corriendo, para hacer el trabajo mecánico del día a día (triaje, vigilancia, tareas repetitivas).
- **Eficiencia de uso de IAs externas:** cierto — es matemáticamente imposible gastar menos cuota externa sin resolver más localmente primero; esto es casi una tautología, no una apuesta arriesgada.
- **Fiabilidad:** cierto solo SI se implementa con los controles de la sección J (seguridad/autonomía) y H (observabilidad) de esta fase — un sistema con más piezas sin esos controles es objetivamente MENOS fiable, no más (más piezas = más puntos de fallo). La hipótesis es correcta condicionada a que se construya bien, no automáticamente.

**Qué parte NO es automáticamente cierta (los riesgos reales):**
- **Complejidad de coordinación:** un orquestador local que decide entre 4+ proveedores y varios roles internos es, en sí mismo, una pieza de software nueva y no trivial que puede fallar de formas que hoy no existen (un router mal calibrado puede escalar de más, escalar de menos, o quedarse indeciso). Esto no se resuelve solo queriéndolo — se resuelve midiendo (sección H) y limitando el alcance de cada paso de implementación.
- **"Más potente" no es gratis:** cada proveedor nuevo, cada agente local nuevo, es una superficie más que mantener, versionar y asegurar (ver sección J). La ganancia de capacidad debe superar ese coste de mantenimiento en la práctica, no solo en el diseño en papel.
- **El local no sustituye a Claude en todo, y no debería intentarlo:** hay tareas (arquitectura de software compleja, razonamiento profundo multi-paso, código no trivial) donde ningún modelo local disponible en este hardware compite hoy con Claude — la sección B lo cuantifica. La hipótesis de Damián no dice lo contrario ("no quiero que Claude solo programe" apunta en la misma dirección), pero conviene decirlo explícitamente para no sobre-corregir hacia "todo local siempre".

**Conclusión de esta sección:** la hipótesis es correcta como dirección estratégica, y esta fase la adopta como premisa de diseño. No es correcta como promesa incondicional — su éxito depende enteramente de la calidad del Model Router (sección E), de la observabilidad (sección H) y de que la seguridad (sección J) se resuelva antes de ampliar autonomía, exactamente como Damián mismo condiciona en su punto 17. El resto de esta fase desarrolla la arquitectura necesaria para que la hipótesis se cumpla en la práctica, no solo en el diseño.

## El principio que gobierna el resto de esta fase (punto 25, tal cual)

No es "usar la IA más potente posible en cada tarea". Es "usar el conjunto de recursos disponible de la forma más inteligente posible" — local cuando basta, proveedor externo específico cuando aporta una capacidad concreta, Claude cuando su razonamiento adicional merece de verdad la cuota, varias IAs cuando la combinación mejora el resultado, verificación cuando el riesgo lo justifica, y nunca trabajo innecesario. Este principio es el criterio con el que se evalúa cada decisión de diseño en el resto de los documentos de esta fase.
