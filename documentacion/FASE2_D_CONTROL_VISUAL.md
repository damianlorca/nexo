# FASE 2 — D. Control visual del PC como capa central (diseño, no implementación)

Damián propone esta capa como algo que "puede solucionar muchos problemas actuales de una sola vez". Evaluación: es cierto para varios de los problemas de esta revisión (comprobar visualmente el uso de Claude, cambiar de chat en Gemini/ChatGPT cuando el selector CSS falla, recuperar una automatización atascada), pero es una pieza de infraestructura transversal, no una solución de un solo problema — se diseña aquí como tal.

## Jerarquía de métodos (tal como la pidió Damián, confirmada como el orden correcto)

```
1. Método estructurado/semántico (API oficial, o el propio contrato de proveedores.py)
2. Playwright / automatización web estructurada, cuando la web lo permita
3. UI Automation / accesibilidad de Windows (para aplicaciones de escritorio)
4. Visión por computador local (OCR, detección de elementos en una captura)
5. Coordenadas de pantalla — último recurso, el más frágil
```

Esta jerarquía ya está parcialmente aplicada de facto en el proyecto sin haberse formalizado: `navegador.py` usa Playwright (nivel 2) porque es más fiable que clicar a ciegas, y cuando falla (un overlay tapa la caja de texto), la solución encontrada (`_cerrar_overlays`, pulsar Escape) es ya un primer paso hacia "recuperación estructurada antes que visión" — encaja con el espíritu de esta jerarquía sin haberla seguido a propósito.

## Qué NO existe hoy en el proyecto para los niveles 3, 4 y 5

Nada. `manos/shell.py` ejecuta PowerShell; no hay ninguna librería de UI Automation (pywinauto, FlaUI, o similar) integrada, ni captura de pantalla con reconocimiento de elementos, ni un mecanismo de coordenadas. Todo lo que hoy "ve" el sistema es texto (`inner_text` de Playwright) o el resultado de comandos. La sección de permisos (`nucleo/permisos.py`) tampoco tiene ningún concepto de "acción visual" o "clic en una aplicación": está pensada solo para rutas de archivo y líneas de comando de PowerShell.

## Casos de uso concretos que Damián pidió, mapeados a nivel de la jerarquía

| Caso | Nivel esperado | Por qué |
|---|---|---|
| Comprobar visualmente el uso/límite de Claude | 4 (visión) o 2 si `claude.ai/settings/usage` es raspable con Playwright | Es una página web: se debería intentar primero con Playwright/lectura de texto antes de recurrir a una captura |
| Cambiar el modelo o el nivel de razonamiento en la interfaz | 2 (Playwright) si el selector es estable | No hace falta visión para esto si el DOM es accesible |
| Seleccionar/crear un chat | 2, con fallback a 4 si el panel lateral es difícil de mapear por selector | Ver sección C |
| Trabajar con aplicaciones de Windows sin API útil | 3 (UI Automation) primero, 4 como fallback | Es exactamente para lo que existe UI Automation: aplicaciones de escritorio sin API |
| Recuperar una UI que ha cambiado | 4 (visión), porque por definición el método estructurado ya falló | Última red de seguridad, no primera opción |

## Seguridad — no negociable antes de dar ningún permiso de este tipo

El sistema de permisos actual (`nucleo/permisos.py`) es puramente textual: regex sobre rutas y sobre líneas de comando. No tiene ningún concepto de "aplicación", "ventana" o "acción de UI". Antes de dar a Nexo la capacidad de hacer clic en cualquier cosa de la pantalla, hace falta extender el modelo de permisos con, como mínimo:

- **Lista blanca de aplicaciones** con las que se permite interactuar visualmente (Chrome del perfil dedicado, y poco más al principio — nunca el explorador de archivos completo ni el Chrome personal de Damián).
- **Lista de acciones sensibles que siempre son ámbar/rojo** independientemente de en qué aplicación ocurran: cualquier diálogo de confirmación del sistema, cualquier ventana que pida credenciales, cualquier acción de borrado.
- **Kill switch**: una forma de que Damián corte cualquier sesión de control visual al instante desde el móvil (un comando de Telegram, por ejemplo `/parar`), no solo cerrando la app de escritorio.
- **Registro de acciones**: cada clic/tecla que se envíe queda trazado (extendiendo `nucleo/registro.py::traza()`, que ya existe y ya se usa para otras cosas) — sin esto, un fallo de control visual es indepurable.
- **Confirmación humana** para cualquier acción que la lista blanca no cubra explícitamente — por defecto denegar, no por defecto permitir.

Esto se retoma en detalle en FASE2_J_SEGURIDAD_PERMISOS.md, porque es la extensión de permisos más grande que exige toda esta revisión.

## Procesamiento visual en LOCAL

Pedido explícito de Damián: no mandar la pantalla completa a un proveedor externo si se puede evitar. Esto es coherente con la sección A (aprovechar el hardware local): un modelo de visión pequeño corriendo en local (vía Ollama, si el modelo lo soporta, o una librería de OCR clásica como Tesseract para el caso más simple de "leer un número de la pantalla") cubre buena parte de los casos sin mandar nada fuera. Reservar el envío de una captura a Gemini/ChatGPT/Claude solo para cuando el caso sea de verdad ambiguo y la visión local no baste — mismo principio de "mínimo envío externo suficiente" que se aplica al texto en la sección B/G.

## No implementar todavía

Esta es, de todas las piezas de esta revisión, la que más superficie de riesgo nueva introduce (control real del ratón/teclado). Se recomienda que sea de las ÚLTIMAS en implementarse, no de las primeras, y solo después de que la extensión de permisos (sección J) y la observabilidad (sección F) — que son las que la hacen segura de operar — ya existan. Ver dependencias en FASE2_L_ROADMAP.
