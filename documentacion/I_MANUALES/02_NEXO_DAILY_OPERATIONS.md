# I.2 NEXO_DAILY_OPERATIONS

Qué pasa un día normal, sin que nadie mire.

## Flujo real hoy (verificado)

1. `canal/vigilante.py` vive siempre en el PC (acceso directo en Inicio). Cada 30s comprueba si `canal/bot.py` sigue vivo (por PID anotado, no por nombre de proceso — el bot corre como `pythonw.exe`, buscarlo como `python.exe` engaña). Si murió, lo relanza y espera 8s para confirmar.
2. `canal/bot.py` atiende Telegram: `/tarea`, `/tareas`, `/hecha`, `/estado`, `/uso`, `/imagen`, `/ahora`, y texto libre (que dispara una lectura de Qwen en segundo plano — categoría/urgencia/resumen — sin que Qwen decida ni dé de alta nada solo).
3. Cualquier mensaje libre que Damián mande se guarda en `canal/entrada/libre_*.json` y espera a un turno (o a que Qwen lo triara).
4. `nucleo/uso.py` registra cada turno de Claude que se dispara (modelo, origen), con candado, para medir el gasto real del plan (T029).

## Qué NO pasa solo todavía

- Nadie divide un objetivo grande en subtareas de forma automática (ver `H_NEXO_MASTER_ARCHITECTURE.md`, huecos de diseño).
- Nadie decide automáticamente qué proveedor usar para una tarea nueva (Model Router, ver `06_NEXO_MODEL_ROUTING.md`).
- Los mensajes libres de Telegram se acumulan hasta que un turno los lee; no hay un bucle que los procese solo más allá del aviso de Qwen.

## Checklist de "todo va bien" para un turno que empieza

1. `info_entorno()` — confirma raíz, PID del servidor, hora real.
2. `comando("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe'\" | Select ProcessId,ParentProcessId,CommandLine")` — para ver bot/vigilante vivos (recordar: 2-3 filas por proceso lógico es normal, ver `H`).
3. Revisar `memoria/estado.json::siguiente_turno` antes de nada más: es la memoria que une un turno con el siguiente.
4. Revisar `canal/entrada/` por mensajes libres sin procesar.
