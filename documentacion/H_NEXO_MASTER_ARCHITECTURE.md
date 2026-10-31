# H. NEXO_MASTER_ARCHITECTURE

Manual 1 de 14 de la Fase 5. Describe cómo encajan las piezas HOY (arquitectura real, verificada) y cómo deberían encajar cuando se construyan las piezas que faltan (diseño, no implementado todavía). No repite el detalle de cada módulo: para eso están `A_MATRIZ_REQUISITOS.md` (qué existe) y `B_AUDITORIA_REAL.md` (evidencia).

## 1. Vista general (lo que existe hoy, verificado)

```
Damián (móvil, Telegram)
        │
        ▼
canal/bot.py  ←────────────┐  (proceso Windows, siempre vivo gracias a
   │  comandos: /tarea      │   canal/vigilante.py, relanzado por acceso
   │  /hecha /tareas /uso   │   directo en la carpeta de Inicio)
   │  /imagen /ahora        │
   │  texto libre → Qwen    │
   ▼                        │
canal/salida/ , canal/entrada/   (archivos JSON con candado/atómicos,
   │                              nucleo/escritura.py + nucleo/candado.py)
   │
   ├── /ahora → POST Routines Fire API → dispara un turno de Claude Code
   │            (T039, funciona, requiere token en secretos.toml)
   │
   └── texto libre → extremidades/qwen.py (Ollama local, qwen2.5:7b)
                       → extremidades/triaje.py (clasifica, NO decide)

Un turno de Claude (este tipo de sesión) tiene manos propias:
  manos/servidor_mcp.py → manos/archivos.py (permisos OK)
                        → manos/shell.py (permisos OK, salvo vivo() B5)
                        → ejecutar_python (SIN permisos, T016/L1, abierto)

extremidades/ (invocadas por un turno de Claude, no automáticamente):
  qwen.py, navegador.py (Gemini/ChatGPT vía CDP), imagen.py (ComfyUI),
  voz.py (Piper), video.py (FFmpeg), papers.py (OpenAlex/S2/arXiv)

proveedores.py (T046): contrato común para invocar a los 4 (Qwen,
  Gemini, ChatGPT, Claude) con el mismo enviar()/estado()/capacidades().
  Es un ADAPTADOR, no un router: alguien (hoy, un turno de Claude a
  mano) tiene que decidir a cuál llamar.

memoria/: estado.json (misión en curso, atómico, con recuperación),
  tareas.json (cola con candado), uso_diario.json (gasto de plan).
```

## 2. Lo que NO existe todavía como componente real (huecos de diseño)

- **Model Router**: no hay ningún componente que reciba una tarea y decida a qué proveedor mandarla. Hoy lo decide un turno de Claude, a mano, cada vez.
- **Message Bus / protocolo entre IAs**: no hay encadenamiento automático Qwen→Gemini→ChatGPT→Claude. Propuesta de diseño en `M_DECISIONES_ARQUITECTONICAS_PENDIENTES.md` punto 4 y en `G_SINTESIS_MULTI_IA.md` caso D.
- **Planner**: nadie divide un objetivo grande en subtareas automáticamente.
- **Máquina de 10 estados de tareas**: hoy son 5 (`nucleo/tareas.py`). No tocar sin decisión explícita de Damián (ya lo pidió así).
- **Bucle de autonomía sostenido más allá de un turno**: ver propuesta mínima en `F_ANALISIS_CLAUDE.md` caso E (vigilante que avisa, no que actúa solo).

## 3. Hechos de infraestructura que hay que conocer para no perder tiempo re-investigándolos

Esta sección existe porque ya ha pasado dos veces que el mismo hecho se redescubre desde cero en turnos distintos. Se deja aquí como referencia única, enlazada, para que no vuelva a pasar una tercera vez.

- **"Proceso duplicado" del bot/vigilante NO es un bug**: Windows/venv reejecuta `.venv\Scripts\python.exe` como lanzador de un proceso hijo con el intérprete real (`pyvenv.cfg::home`). 2-3 filas en `Get-CimInstance Win32_Process` = 1 bot lógico. Documentado primero en `docs/ARRANQUE.md`, confirmado de nuevo por evidencia independiente (comparando `pyvenv.cfg` con `ParentProcessId`) en esta auditoría del 12/09.
- **El bot corre como `pythonw.exe`, no `python.exe`**: buscarlo filtrando por `Name='python.exe'` no lo encuentra y parece muerto estando vivo (susto real documentado en `_cerrar2.py`/hechos de `memoria/estado.json`, turno del 12/09 madrugada).
- **`ejecutar()`/`lanzar()` en `manos/shell.py` clasifican por REGEX sobre la línea ENTERA de PowerShell**, no solo la orden — ver T024/L6. Comillas y argumentos cuentan.
- **ComfyUI sobre DirectML en la Radeon 890M**: solo de fiar recién arrancado; reiniciar antes de cada encargo (13s) es más barato que dejar que se atasque (150s). Ver `extremidades/imagen.py`.
- **`nivel_de_ruta()` da VERDE sin preguntar para LECTURA de cualquier ruta fuera del proyecto** (salvo `secretos.toml`) — hallazgo nuevo de esta auditoría (REQ-070), no confundir con K1 (que ya está cerrado).

## 4. Mantener esta arquitectura sincronizada con el código (propuesta, no implementada)

`memoria/auditoria.md` se desincronizó del código en 5 de sus ~33 hallazgos simplemente porque nadie volvió a editarla al cerrar cada uno. Propuesta para el futuro (decisión pendiente, ver `M` punto 7): que cada hallazgo cerrado se registre también como una entrada corta y estructurada (por ejemplo un JSON o una tabla, no solo prosa) para poder comprobar en segundos qué sigue abierto sin releer todo el histórico. No se implementa en esta auditoría porque es una mejora de proceso, no un requisito pedido por Damián para esta fase.

## 5. Enlaces a lo que ya existe (no se duplica aquí)

- Arranque paso a paso: `docs/ARRANQUE.md`.
- Configuración de Telegram: `docs/TELEGRAM.md`.
- Auditoría en frío original (10-11/09): `memoria/auditoria.md`.
- Historial detallado día a día: `memoria/historial.md`.
- Organización de proyectos/chats de Claude: `memoria/claude_organizacion.md`.
- Cola de prioridades original (11/09, superseded por `memoria/tareas.json`): `memoria/cola.md`.
