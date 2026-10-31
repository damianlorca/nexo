# FASE 4 — F. Perfiles de capacidad extensibles y aprovechamiento real de cada IA

## De ficha estática a perfil actualizable

FASE3_D ya definió los campos de una ficha de capacidades (modelos, capacidades, limitaciones, coste/quota, disponibilidad, contexto, visión, búsqueda, coding, razonamiento, herramientas, archivos, proyectos, memoria, automatización, fiabilidad, método de acceso). Damián pide ahora que esto deje de ser un documento markdown fijo y se piense como una **estructura de datos actualizable** que el Router (FASE4_E) consulta en tiempo real:

```
PerfilProveedor
├── modelos: [...]
├── capacidades: {razonamiento, coding, busqueda, vision, ...}
├── limitaciones: [...]
├── disponibilidad: activa/caida/desconocida (actualizado por sondas, como ya hace extremidades/base.py)
├── metodo_de_acceso: api | navegador | rutina_programada
├── contexto: tamano aproximado de ventana
├── cuota: consumo conocido hoy / limite conocido (alimentado por el registro de evidencia, FASE4_E)
├── fiabilidad_observada: tasa de exito reciente (alimentado por el registro de evidencia)
└── ...
```

**La diferencia clave con FASE3_D:** `disponibilidad`, `cuota` y `fiabilidad_observada` no se escriben a mano en un documento — se actualizan solas a partir de las sondas de salud ya existentes (`extremidades/base.py`) y del registro de evidencia del Router (FASE4_E). El resto de campos (capacidades, límites, método de acceso) sí son mayormente estáticos y se editan a mano cuando cambian de verdad (p. ej. si Gemini añade una capacidad nueva).

## El patrón para añadir un proveedor futuro, formalizado

Damián lo pide explícito: añadir un proveedor debe significar `adapter + capability profile + tests`, no reescribir el Router. Concretamente:

1. **Adapter** — una clase que cumple el contrato ya existente de `proveedores.py` (`nombre/disponible/estado/enviar/capacidades`), añadiendo lo que haga falta para la capa de tools (FASE4_A) si el proveedor se accede vía navegador.
2. **Capability profile** — el `PerfilProveedor` de arriba, rellenado a mano para lo estático y dejado a completarse solo para lo dinámico.
3. **Tests** — una prueba real (no simulada) de que el adapter responde, en línea con la disciplina ya exigida en todo el proyecto ("nada se considera funcional sin prueba real").

Con esto, el Router nunca necesita saber "cómo es" un proveedor nuevo — solo lee su perfil. Esto ya es, en espíritu, lo que intentó `proveedores.py` (T046) — esta sección lo completa formalizando la parte que faltaba (`capacidades()` sin consumidor real todavía).

## Aprovechar de verdad cada plataforma, no solo "enviar texto"

Punto explícito de Damián: hoy Gemini/ChatGPT se usan como `abrir chat → enviar texto → extraer respuesta`, desaprovechando conversaciones persistentes, proyectos, archivos, búsqueda nativa, visión, memoria propia del proveedor. Esto no es una funcionalidad nueva aislada — es la extensión natural de la gestión de proyectos/chats ya diseñada (FASE3_F, `ConversationManager`) más el reconocimiento explícito, dentro del propio `PerfilProveedor`, de qué capacidades de cada plataforma Nexo puede invocar y cuáles no.

**Ejemplos concretos de lo que hoy se desaprovecha, por proveedor:**
- **Gemini/ChatGPT:** búsqueda web nativa de la interfaz (Nexo le manda texto y espera que razone con su conocimiento interno, en vez de pedirle explícitamente "busca X" cuando la tarea lo necesita); memoria propia entre conversaciones (no se sabe si está activada ni si Nexo debería depender de ella — pendiente de decidir); subida de archivos como contexto (la tool de `navegador.py` ya sabe escribir texto, no adjuntar un archivo).
- **Claude:** ya es el más explotado de los cuatro dentro de esta misma sesión (herramientas MCP, memoria del proyecto, archivos) — el desaprovechamiento aquí es al revés: se le pide trabajo mecánico que no necesita ese nivel de capacidad (ver FASE3_C, "cuándo NO gastar Claude").
- **Qwen:** cubierto en detalle en FASE3_B/FASE4_D — su "capacidad desaprovechada" es de rol (verificación, planificación preliminar), no de función de plataforma como en los otros dos.

**Regla para decidir qué desarrollar primero de esta lista:** cada capacidad nueva que se explote de un proveedor se justifica solo si resuelve algo que hoy pasa por un recurso más caro (p. ej., activar la búsqueda nativa de Gemini para preguntas factuales simples, en vez de que esas preguntas lleguen a Claude por defecto) — no se añade "porque existe".

## Proveedores adicionales: mismo patrón, sin prisa

Perplexity, Copilot, Grok, nuevos modelos locales — todos entran por el mismo patrón (`adapter + capability profile + tests`) cuando (y solo cuando) resuelvan una capacidad concreta que la tabla de perfiles muestre como débil o ausente en los proveedores actuales (reafirmando FASE3_D: no añadir por cantidad). Perplexity sigue siendo el candidato más claro (búsqueda con fuentes, capacidad hoy débil en el resto).
