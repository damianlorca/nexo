# Nexo

Agente personal de Damián. Un cerebro, muchas extremidades.

Se llama Nexo porque es el punto donde se juntan Damián, el equipo y
las demás IAs. No es un chatbot: es lo que las conecta.

## La regla

**Solo el cerebro piensa.** El cerebro es Claude Pro. Todo lo demás recibe una
orden concreta, la ejecuta y devuelve el resultado tal cual. Ninguna
extremidad decide, ninguna reinterpreta, ninguna cambia la misión.

## Mapa

```
nucleo/         config y permisos; cola de tareas; turnos y planificador; tribunal, riesgo,
                implementador y puerta; banco de modelos; avisos, cuota, parada
manos/          archivos, shell y procesos del PC (servidor MCP)
extremidades/   CAPACIDADES locales: qwen (Ollama), navegador (Chrome de NEXO), voz y
                altavoz, imagen, vídeo, papers
proveedores.py  PROVEEDORES de IA: Qwen, Gemini y ChatGPT web, Claude web, Gemini API,
                Groq, NVIDIA, OpenRouter (con failover y cuota)
router.py       a quién va cada petición (Qwen -> ChatGPT -> Gemini -> escalado)
interfaz/       la web/app (Centro, Tareas, Turnos, bandejas) y su vigía
canal/          bot de Telegram (sin desarrollo nuevo desde el 27/09)
roles/          prompts de cada rol
memoria/        estado vivo: tareas, turnos, informes (privado, no se publica)
registros/      logs y trazas
```

Una extremidad es algo que NEXO hace en el PC; un proveedor es una IA a la que NEXO
pregunta. Ninguno de los dos decide: ejecutan lo que se les pide.

## Niveles de permiso

| Nivel | Qué | Quién decide |
|---|---|---|
| verde | leer, escribir y ejecutar dentro del proyecto | el agente, sin preguntar |
| ambar | instalar paquetes, tocar archivos fuera, procesos persistentes | Damián |
| rojo | borrar, cuentas, pagos, publicar, mensajes en su nombre | nadie, no se hace |

Codificado en `nucleo/permisos.py`. No es documentación: es control.

**Archivos blindados** (`nucleo/permisos.py`, `nucleo/instancia.py`, `nucleo/config.py`,
`manos/*`): ni NEXO ni Claude los cambian sin que Damián vea antes el diff. Es la única
excepción al nivel verde dentro del proyecto. El implementador automático tampoco toca sus
propios controles (puerta, matriz de riesgo, aprobaciones, parada): son R3 en
`nucleo/riesgo.py`.

## Arranque

```powershell
cd C:\Users\damia\Desktop\AI\agente
.\instalar.ps1
```

Luego `docs/ARRANQUE.md`.

## Estado

**Estado del proyecto** (11/10/2026): en uso diario. La web/app (`interfaz/`) es el canal
principal; los turnos los lanza su planificador cada hora (tribunal, revisiones, vigía,
radares, implementador, banco de modelos); el implementador permanente fusiona código con
tests a través de la puerta (R2 con OK de Damián). La cola viva está en
`memoria/tareas.json` (`python -m nucleo.tareas siguiente`). Lo que funciona y con qué
evidencia se apunta en cada tarea (HECHO Y TESTEADO / HECHO SIN TESTEAR / EN PROCESO...).

**Procedimiento de arranque** (equipo nuevo): `docs/ARRANQUE.md`; la web,
`interfaz/ARRANQUE.md`.
