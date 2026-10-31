# Guardián de aprobaciones (pedido por Damián el 18/10, 17:22)

## Por qué
Damián recibe aprobaciones que no entiende ("A0064 · ejecutar comando", "Riesgo: sin clasificar") y que casi siempre
son inofensivas (lecturas). Lo dicho por él: no quiere dar él las aprobaciones salvo cuando de verdad le toque; todo
lo que tenga que ver con borrar contenido o pida aprobación pasa antes por un agente/herramienta que lo confirme; si
ese agente de verdad no puede decidir, se lo redacta y se lo explica bien, con un minichat para preguntar.

## Qué es
Un módulo `nucleo/guardian.py` que mira cada solicitud nueva de la cola (`aprobaciones.py`: ámbar, R1, R2) en cuanto
entra (gancho en `solicitar` + barrido del planificador cada minuto por si el gancho falla) y hace tres cosas:

### 1. Explicar (siempre)
Ficha en llano guardada en la solicitud (`extra.explicacion`, no entra en la huella):
- **Qué hace**, en una frase ("Lee el archivo de ejemplo de configuración de MiroFish").
- **Sobre qué** (rutas/archivos, con su papel: "plantilla sin claves", "archivo de control de NEXO").
- **Tipo**: solo lee / escribe con respaldo / archiva / borra de verdad / ejecuta código / sale a internet.
- **¿Se puede deshacer?** sí/no y cómo.
- **Quién lo pide y para qué** (el `motivo` de la solicitud; si no lo trae, "no lo ha dicho").
- **Recomendación** del guardián y por qué.
Análisis determinista primero (lexer de comandos de `permisos.py` reutilizado, rutas, verbos); Qwen local
(qwen2.5:7b, num_ctx 4096, num_predict 120) solo para redactar la frase. Nada de la explicación sale de NEXO si
contiene rutas o datos privados (pasa por `auditor.tapar`).

### 2. Decidir (cuando puede)
Orden de reglas; la primera que encaja manda:
1. **Siempre de Damián** (nunca decide el guardián): tocar archivos blindados o controles R3, secretos o
   credenciales, dinero o cuentas, perfil_privado hacia fuera del PC, borrar de verdad contenido de Damián que no se
   puede recuperar, R3. Le llega con la ficha completa, la recomendación del tribunal y el minichat.
2. **Aprueba solo** (registrado, `quien=guardian`): acciones de SOLO LECTURA dentro del repo o de
   `herramientas_externas`, que no lean secretos (`secretos.toml`, `.env` real, claves), ni `memoria/perfil_privado/`,
   ni el vault privado; incluye `Select-String`, `Get-Content`, `git log/status/diff` y `python -c` que solo lee
   (comprobado por el lexer: sin escritura, sin red, sin subprocesos). Un `.env.example` es plantilla: se lee.
3. **Tribunal** (3 familias distintas, como R1 desde el 17/10): escrituras con respaldo, archivar en `_archivo/`,
   borrar lo regenerable (cachés, temporales, salidas de build), ejecutar scripts del repo, y las **R2** (diff con
   la puerta en verde). Unanimidad = decide; división o proveedores caídos = a Damián con todo explicado.
4. Lo que no encaje en nada: a Damián, explicado.
Cada decisión del guardián queda en el historial de aprobaciones con su motivo y en el Centro ("Hecho desde tu
última visita", grupo "Permisos que ha resuelto NEXO"), con enlace a la ficha.

### 3. Minichat (cuando llega a Damián)
Botón "Preguntar" en la tarjeta: chat sobre ESA solicitud (historial en `memoria/chats_aprobaciones/<id>.jsonl`),
contexto solo la ficha + la solicitud; contesta NVIDIA nemotron-3-super (como el chat de tareas), reserva Groq/Gemini
API, Claude solo si Damián pulsa "Escalar". Sin acciones: el chat solo explica; decidir es con los botones.

## Arreglo de raíz (blindado, diff para Damián)
`manos/servidor_mcp.py`: cada herramienta que puede pedir aprobación acepta `motivo` (para qué) y lo guarda en la
solicitud; sin motivo la ficha dice "no lo ha dicho" y el guardián no aprueba solo nada que escriba.

## Límites
- El guardián es control R3: solo lo cambia Claude. No toca `permisos.py` (no rebaja ningún rojo ni ámbar: decide
  sobre la cola, después).
- Nada de esto vale para rojo: lo rojo sigue bloqueado.
- Interruptor en Ajustes para apagar las decisiones automáticas (vuelve todo a Damián, con ficha y minichat).

## Hecho cuando
- Tests: cada regla con casos reales (A0064-A0066 del 18/10 = aprobación automática; un `Remove-Item` de contenido
  = Damián; un `git apply` sobre un blindado = Damián; archivar = tribunal), fichas sin "sin clasificar", minichat.
- Una semana sin que a Damián le llegue nada que el guardián podía decidir.
