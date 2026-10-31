# -*- coding: utf-8 -*-
"""Comprueba, con evidencia, que el parche T112 y la instalacion de Graft (T125)
quedaron bien. Se ejecuta DESPUES de instalar_graft.ps1 + parche_shell_t112.ps1
y de reiniciar Claude Desktop. No cambia nada: solo mira."""
import json
import os
import shutil
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ok_total = True


def comprobar(nombre, cond, detalle=""):
    global ok_total
    ok_total &= bool(cond)
    print(("  OK    " if cond else "  FALLO ") + nombre + (f"  -> {detalle}" if detalle else ""))


print("T112 -- encoding de PowerShell")
shell = (RAIZ / "manos" / "shell.py").read_text(encoding="utf-8")
comprobar("manos/shell.py contiene _FIJAR_ENCODING", "_FIJAR_ENCODING" in shell)
comprobar("existe la copia manos/shell.py.bak_t112", (RAIZ / "manos" / "shell.py.bak_t112").is_file())
r = subprocess.run(["git", "diff", "--stat", "--", "manos/shell.py"], cwd=RAIZ, capture_output=True, text=True)
comprobar("git ve el cambio en manos/shell.py (sin commit todavia)", "shell.py" in r.stdout, r.stdout.strip())

print("\nT125 -- Graft")
HERR = Path(r"C:\Users\damia\Desktop\AI\herramientas")
cli = HERR / "graft" / "node_modules" / "@nanonets" / "graft" / "dist" / "cli.js"
node22 = HERR / "node22" / "node.exe"
comprobar("graft instalado (Node 22 portatil en AI/herramientas)", cli.is_file() and node22.is_file(), str(cli))
comprobar("grafo construido (carpeta graft/ en el repo)", (RAIZ / "graft").is_dir())
gi = (RAIZ / ".gitignore").read_text(encoding="utf-8") if (RAIZ / ".gitignore").is_file() else ""
comprobar("graft/ esta en .gitignore", "graft" in gi)
cfg_path = Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json"
raw = cfg_path.read_bytes()
comprobar("claude_desktop_config.json sin BOM", not raw.startswith(b"\xef\xbb\xbf"))
cfg = json.loads(raw.decode("utf-8"))
srv = cfg.get("mcpServers", {})
comprobar("servidor 'graft' registrado", "graft" in srv, str(list(srv)))
comprobar("'agente-local' sigue registrado", "agente-local" in srv)
if "graft" in srv:
    g = srv["graft"]
    comprobar("graft con DO_NOT_TRACK=1", g.get("env", {}).get("DO_NOT_TRACK") == "1")
    comprobar("graft apunta al repo de NEXO", str(RAIZ) in " ".join(g.get("args", [])), g.get("args"))
if cli.is_file():
    node = str(node22)
    t = subprocess.run([node, str(cli), "telemetry", "status"], capture_output=True, text=True, env={**os.environ, "DO_NOT_TRACK": "1"})
    comprobar("telemetria de graft apagada", "off" in (t.stdout + t.stderr).lower(), (t.stdout + t.stderr).strip()[:120])
    a = subprocess.run([node, str(cli), "ask", "donde se decide el proveedor de fallback en el router", str(RAIZ)],
                       capture_output=True, text=True, env={**os.environ, "DO_NOT_TRACK": "1"}, timeout=60)
    comprobar("consulta real al grafo menciona router.py", "router.py" in a.stdout, a.stdout[:200])

print("\n" + ("TODO VALE" if ok_total else "HAY FALLOS (ver arriba)"))
print("Recuerda: el servidor 'graft' solo aparece en las sesiones de Claude tras cerrar Claude Desktop del todo y reabrirlo.")
