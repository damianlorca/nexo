# -*- coding: utf-8 -*-
"""T091: pasa las suites existentes A TRAVES de la guardia para ver que se rompe."""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SUITES = ["prueba_parada.py", "prueba_catalogo.py", "prueba_roles.py", "prueba_frescura.py",
          "prueba_comandos_bot.py", "prueba_router_chatgpt.py", "prueba_extraer_respuesta.py"]
for s in SUITES:
    if not (RAIZ / s).is_file():
        print("NO EXISTE", s); continue
    r = subprocess.run([sys.executable, str(RAIZ / "nucleo" / "guardia_python.py"), s], cwd=RAIZ,
                       capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace")
    bloqueos = sorted({l.strip()[:170] for l in (r.stdout + r.stderr).splitlines() if "GUARDIA NEXO" in l})
    print(("OK " if r.returncode == 0 else "MAL"), s, "rc", r.returncode, "| bloqueos:", len(bloqueos), flush=True)
    for b in bloqueos[:4]:
        print("     ", b)
