# FASE 2 — I. Diseño incremental de autonomía

## Los dos extremos a evitar

(A) Sistema pasivo que depende de Damián para todo — contradice el objetivo original del proyecto ("trabaje autónomo para conseguir objetivos pedidos... aunque no esté yo en casa"). (B) Sistema que actúa por su cuenta sin controles suficientes — el riesgo que ya señaló la sección H para el turno de noche durante esta fase, y el que motivan directamente los hallazgos de seguridad de la sección J (bypass de `ejecutar_python`, REQ-070).

## El ciclo propuesto

`OBSERVAR → PROPONER → DELEGAR → EJECUTAR → VERIFICAR → RECUPERAR → REPORTAR`

- **OBSERVAR**: recoger el estado actual (colas, mensajes entrantes, resultado de la última acción) — hoy ya existe parcialmente (`triaje.py`, `memoria/estado.json`); con la sección F se vuelve más rico (estado vivo, no solo eventos pasados).
- **PROPONER**: generar una propuesta de qué hacer a continuación — hoy lo hace Claude directamente; con el Model Router (sección B) y Qwen como "planificador preliminar" (sección A), una parte de esta propuesta puede generarse más barato antes de que Claude decida.
- **DELEGAR**: decidir QUIÉN ejecuta — Claude, Qwen, un script determinista, o (más adelante) el propio agente actuando sobre la pantalla (sección D). Esta es la pieza que hoy no existe como decisión explícita: todo pasa por Claude por defecto.
- **EJECUTAR**: la acción en sí, sujeta en todo momento al sistema de permisos vigente (`permisos.py`) — sin excepción por el hecho de venir de un ciclo más autónomo.
- **VERIFICAR**: comprobar que la acción tuvo el efecto esperado — hoy esto lo hace Claude "a ojo" releyendo la salida; la sección A propone delegar la verificación mecánica a Qwen o a un modelo verificador dedicado.
- **RECUPERAR**: qué hacer si algo falla o se atasca — hoy no hay una política explícita (se confía en que Claude lo note y reintente); la sección F (límites de reintentos, detección de bucle) y la sección D (recuperación visual de una automatización atascada) son las piezas que dan a este paso algo concreto que hacer.
- **REPORTAR**: informar a Damián — hoy existe vía Telegram para lo que el bot decide contar; con la sección F, el reporte puede ser bajo demanda (`/estado`) además de por iniciativa del sistema.

## Qué puede ser automático y qué requiere aprobación

La frontera correcta no es "todo lo nuevo requiere aprobación" ni "todo lo automatizable se automatiza" — es la que ya existe en `permisos.py`, extendida a los nuevos tipos de acción que traen las secciones D (visual) y B (routing multi-proveedor):

- **Automático sin aprobación (nivel VERDE):** observar, proponer, delegar a Qwen/scripts deterministas, verificar mecánicamente, reportar por Telegram. Nada de esto cambia estado del mundo real ni gasta dinero.
- **Automático pero con límites duros (sigue VERDE, pero con freno):** ejecutar tareas de la cola ya aprobadas por Damián en algún momento anterior (dar de alta la tarea fue la aprobación), encadenando varias, siempre que existan los límites de pasos/reintentos/tiempo de la sección F — sin esos límites, no debería ampliarse la autonomía aquí, es la razón concreta de la recomendación de pausar el turno de noche (sección H) durante esta fase.
- **Requiere aprobación explícita (ÁMBAR/ROJO, sin cambios respecto a hoy):** cualquier acción irreversible, cualquier gasto de dinero, cualquier envío de mensaje en nombre de Damián a un tercero, cualquier cambio a los archivos blindados, y — nuevo, a añadir cuando exista el control visual — cualquier acción visual sobre una aplicación que no esté en una lista blanca explícita (ver sección J).

## El caso E (discrepancia 3-vs-1 de la Fase 3) sigue abierto

Tal como se prometió en FASE2_M, esta sección no resuelve esa discrepancia por decreto. Con las piezas nuevas de este diseño (Model Router, observabilidad, límites de pasos), la discrepancia se puede replantear como una pregunta más simple: "¿bajo qué condiciones EXACTAS el ciclo OBSERVAR→PROPONER puede saltarse la aprobación y pasar directo a EJECUTAR?" — pero seguir sin una única respuesta correcta sin que Damián decida el umbral de riesgo que le resulta cómodo. Se deja explícitamente como una de las decisiones pendientes (ver sección S / FASE2_00_INDICE).

## Relación con el resto del diseño

Depende de: Model Router (B), papel de Qwen (A), observabilidad (F) y seguridad/permisos (J) — las cuatro deben tener al menos su diseño confirmado antes de que ampliar la autonomía (más allá de lo que ya existe hoy) sea prudente. Es, por diseño, de las últimas piezas en el orden de implementación (ver FASE2_L).
