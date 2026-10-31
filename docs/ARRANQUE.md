# Arranque

Los pasos de esta noche, en orden. Cada uno depende del anterior.

---

## 1. Matar los servidores zombis  ← empieza aquí

Este es el bloqueo de todo. Tenías **dos** servidores MCP corriendo a la
vez, y el viejo seguía atendiendo con el código antiguo. Cerrar la
ventana de Claude no los mata.

```powershell
# a) Sal de Claude por la BANDEJA del sistema (junto al reloj) → Salir

# b) Mata lo que quede
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*mcp_agente*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# c) Comprueba que no queda nada — debe salir VACÍO
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*mcp_agente*" } |
  Select-Object ProcessId, Name

# d) Abre Claude otra vez
```

---

## 2. Instalar

```powershell
cd C:\Users\damia\Desktop\AI\agente
.\instalar.ps1
```

Instala dependencias, crea el repositorio de git con el primer commit y
te dice qué extremidades responden.

Si avisa de que `python` apunta al alias de Microsoft Store, desactívalo:
**Configuración → Aplicaciones → Alias de ejecución de aplicaciones** →
apaga los dos de `python`. Ese alias fue el que colgó el servidor la
primera vez.

---

## 3. Apuntar Claude al servidor nuevo

En Claude Desktop, la extensión **Agente Local** apunta todavía a
`pruebas\mcp_agente.py`. Hay que cambiarla a:

```
C:\Users\damia\Desktop\AI\agente\manos\servidor_mcp.py
```

Si la extensión no deja cambiar la ruta, se desinstala y se vuelve a
añadir apuntando ahí.

**Comprobación:** en el chat, la primera herramienta que llamo es
`info_entorno`. Tiene que devolver la ruta nueva y un PID. Si devuelve
otra cosa, es que sigue vivo un zombi.

---

## 4. Abrir el canal móvil

Sigue `docs/TELEGRAM.md`: crear el bot con BotFather, pegar el token en
`secretos.toml`, arrancar `python canal\bot.py` y escribirle `/start`.

A partir de ahí te llegan avisos, preguntas con botones y capturas al
móvil, y puedes contestarme desde fuera de casa.

---

## 5. Archivar lo viejo

Solo cuando lo de arriba funcione. Lo anterior se mueve a `_archivo\`,
**no se borra**: eso lo decides tú con el material delante.

---

## Lo que queda pendiente de decidir

- **Cuánta RAM** tiene el equipo → decide qué modelo de Qwen ponemos y
  si ComfyUI puede convivir con él.
- **Cuenta secundaria de Google** → la creas tú, y luego inicias sesión
  en Gemini y ChatGPT desde el Chrome de pruebas.
- **Checkpoint de ComfyUI** → cuál instalar depende de la RAM.

---

## Aviso honesto

Nada de este código se ha ejecutado todavía. Está escrito con cuidado y
la sintaxis está comprobada módulo por módulo, y la extremidad de papers
sí está probada de verdad contra las APIs (arXiv devolvió resultados
correctos). El resto se prueba esta noche, en este orden, y lo que
falle lo arreglo sobre la marcha.

---

## Arranque automatico del bot

Escrito en el turno de noche del 11/09/2026. **Pendiente de que
Damian lo apruebe: crear tareas programadas es ambar.**

### Por que hace falta

El bot no solo se cae al apagar el equipo. **Se cae cada vez que
Claude Desktop reinicia el servidor MCP**, porque `lanzar()` lo crea
como hijo de ese servidor y Windows mata a toda la descendencia
cuando el Job del padre se cierra. Paso el 11/09 a las 03:15 y se
quedaron tres mensajes sin entregar.

### Lo que ya esta hecho

`nucleo/instancia.py` pone un candado (mutex global de Windows). Dos
bots no pueden coexistir: el segundo sale en 1 segundo diciendolo.
Probado con `prueba_instancia.py` y en caliente contra un bot real.

Eso es lo que hace segura la receta de abajo: **intentar arrancarlo
de mas no rompe nada.**

### El comando (ambar — no ejecutar sin su OK)

Al iniciar sesion:

```powershell
schtasks /Create /TN "Nexo - bot de Telegram" ^
  /TR "\"C:\Users\damia\Desktop\AI\agente\.venv\Scripts\python.exe\" \"C:\Users\damia\Desktop\AI\agente\canal\bot.py\"" ^
  /SC ONLOGON /RL LIMITED /F
```

Y el vigilante, que es lo que de verdad arregla el problema de
fondo: cada 10 minutos se intenta arrancar; si ya hay uno, el
candado lo rebota; si se ha caido, vuelve solo.

```powershell
schtasks /Create /TN "Nexo - vigilante del bot" ^
  /TR "\"C:\Users\damia\Desktop\AI\agente\.venv\Scripts\python.exe\" \"C:\Users\damia\Desktop\AI\agente\canal\bot.py\"" ^
  /SC MINUTE /MO 10 /RL LIMITED /F
```

Comprobar despues:

```powershell
schtasks /Query /TN "Nexo - bot de Telegram" /V /FO LIST
Get-Content C:\Users\damia\Desktop\AI\agente\registros\nexo_bot.pid
```

### El apano de mientras tanto

Esta noche lo he levantado asi, que lo saca del arbol de procesos
del servidor MCP y por tanto sobrevive a que se reinicie:

```powershell
$py='C:\Users\damia\Desktop\AI\agente\.venv\Scripts\python.exe'
$bot='C:\Users\damia\Desktop\AI\agente\canal\bot.py'
$log='C:\Users\damia\Desktop\AI\agente\registros\bot_nexo.log'
$cmd='cmd.exe /c ""'+$py+'" "'+$bot+'" >> "'+$log+'" 2>&1"'
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
  CommandLine=$cmd; CurrentDirectory='C:\Users\damia\Desktop\AI\agente'
}
```

Funciona, pero no se levanta solo al encender. Es un parche, no la
solucion.

### Como saber si el bot esta vivo

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*canal\bot.py*" } |
  Select-Object ProcessId, ParentProcessId
```

Salen **dos** procesos y esta bien: el `.venv\Scripts\python.exe`
es un lanzador y el `Python311\python.exe` es el bot de verdad, que
es hijo suyo. Un solo bot logico. El PID bueno es el que esta
escrito en `registros/nexo_bot.pid`.

---

## Web de NEXO siempre viva (T1028, 24/10)

La tarea programada **"NEXO interfaz"** lanza el vigía (`interfaz/vigia.py`), que arranca la web y la
relanza si cae. Desde el 24/10 salta **al iniciar sesión, al desbloquear la sesión (vuelta de suspender) y
cada 10 minutos**. Nunca hay dos vigías: el Programador ignora el disparo si el suyo sigue vivo
(`IgnoreNew`) y el vigía se retira si otro tiene el candado `nexo_interfaz_vigia`.

Un vigía arrancado desde la app de Claude muere con ella; el de la tarea no (cuelga del Programador de
tareas). Si el de Claude muere, el de la tarea toma el relevo en 10 minutos como mucho.

Registrar o actualizar la tarea (una vez; si da "Acceso denegado", en PowerShell como administrador):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\damia\Desktop\AI\agente\interfaz\scripts\registrar_autoarranque.ps1
```

Ver lo que registraría sin tocar nada: el mismo comando con `-Simular`.
