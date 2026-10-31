# FASE 4 — J. Disponibilidad del PC, seguridad transversal y autonomía gradual

## Wake del PC, como cadena formal (no solo comparación de opciones)

FASE3_I ya comparó las 4 opciones de wake (fiabilidad/coste/seguridad/limitaciones) — se mantiene sin cambios, incluida la ausencia de decisión de compra. Lo nuevo que pide Damián es formalizar la cadena completa de qué pasa cuando el PC no está disponible:

```
PC NO DISPONIBLE
  -> MECANISMO DE WAKE (el que Damian elija: enchufe+BIOS, WoWLAN, S0, etc.)
  -> COMPROBAR DISPONIBILIDAD (¿respondio el equipo? ¿cuanto se tarda en arrancar?)
  -> LEVANTAR RUNTIME (el bot, el vigilante -- ya lo hace la carpeta de Inicio de Windows, T009)
  -> LEVANTAR SERVICIOS (Ollama, Chrome con el perfil de Gemini/ChatGPT si hace falta -- bajo demanda, no todos a la vez)
  -> VERIFICAR ESTADO (las sondas ya existentes en extremidades/base.py)
  -> CONTINUAR LA TAREA que motivo el wake
```

Esta cadena es, en esencia, la misma cadena de fallo/recuperación de FASE4_I aplicada al caso límite "el propio PC es el recurso caído" — no es una pieza nueva de diseño, es la aplicación del mismo patrón. La única parte genuinamente nueva es el primer eslabón (el mecanismo de wake en sí), que depende de una decisión de Damián todavía pendiente (T037).

## Seguridad transversal: los permisos pertenecen a Nexo y a la tool, nunca al modelo

Este es el punto que Damián marca como más importante de esta sección, y encaja exactamente con la cadena de ejecución de FASE4_B: **un modelo no obtiene más permisos por ser "más inteligente".** Ni Claude, ni Gemini, ni Qwen tienen, por sí mismos, ningún nivel de permiso — el nivel de permiso lo determina la ACCIÓN concreta (vía `nivel_de_ruta()`/`nivel_de_comando()` y su extensión futura a lo visual/proveedor, FASE3_J), evaluada siempre en el eslabón PERMISOS de la cadena, sin importar qué modelo generó la PROPUESTA.

**Aplicación explícita a cada capa (reafirmando FASE3_J, ahora con el vocabulario de capas de FASE4_A):**
- Capa B (modelos/agentes): ninguno tiene autoridad de ejecución — todos solo proponen.
- Capa C (tools): cada tool aplica su propio nivel de permiso a la acción concreta que se le pide, sin importar quién la pidió.
- Capa D (proveedores): un proveedor nuevo no llega con permisos especiales — su ficha de capacidades (FASE4_F) describe qué PUEDE hacer técnicamente, no qué se le PERMITE hacer sin supervisión (eso lo decide siempre la capa A/C).

L1 (`ejecutar_python`) y REQ-070 siguen siendo los dos agujeros conocidos que violan este principio hoy (una tool que se salta el eslabón PERMISOS por completo, y una regla de permisos que da VERDE de más) — se reafirman como bloqueadores de máxima prioridad, sin cambios respecto a FASE2_J/FASE3_J.

## Autonomía gradual: el ciclo de 8 etapas, con la tabla de controles ya diseñada

Sin cambios respecto a FASE3_J: `OBSERVAR → PROPONER → DELEGAR → EJECUTAR → VERIFICAR → RECUPERAR → REPORTAR → MEJORAR`, con límite/permiso/observabilidad/rollback/criterio de parada en cada etapa (tabla completa en FASE3_J). Lo único que añade esta fase es la conexión explícita con la cadena de ejecución de FASE4_B: las etapas DELEGAR-EJECUTAR-VERIFICAR de este ciclo SON, literalmente, la cadena PROPUESTA→VALIDACIÓN→PERMISOS→TOOL→EJECUCIÓN→VERIFICACIÓN→RESULTADO de FASE4_B, vista a la escala de una tarea completa en vez de una sola acción. No son dos diseños distintos — es el mismo patrón en dos escalas (una acción individual, y el ciclo completo de una tarea), y esta fase lo deja dicho para que no se implementen como si fueran cosas separadas.

El Caso E (discrepancia 3-vs-1, umbral de cuándo pasar de "requiere aprobación" a "puede ejecutar directo") sigue exactamente donde estaba: sin resolver por decreto, pendiente de que Damián fije el umbral de riesgo que le resulta cómodo, ahora con la ventaja de que la cadena de FASE4_B da un punto de enganche más preciso para expresar ese umbral (a qué nivel de permiso, en qué eslabón, se exige confirmación humana).

## Sin implementación en esta fase

Todo lo anterior es formalización de diseño ya existente (Fase 2/3) más las conexiones nuevas que pide Damián — ningún archivo de código se toca en esta fase.
