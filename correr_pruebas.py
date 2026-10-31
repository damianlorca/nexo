# -*- coding: utf-8 -*-
"""Ejecuta suites de prueba A TRAVES de la guardia y resume: rc + ultimas lineas.
Uso: .venv\\Scripts\\python.exe correr_pruebas.py prueba_a.py prueba_b.py ..."""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
malas = 0
for s in sys.argv[1:]:
    r = subprocess.run([sys.executable, str(RAIZ / "nucleo" / "guardia_python.py"), s], cwd=RAIZ, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=600)
    lineas = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()]
    malas += r.returncode != 0
    print(("OK " if r.returncode == 0 else "MAL"), s, "rc", r.returncode, flush=True)
    for l in ([l for l in lineas if l.startswith(("MAL", "[MAL", "FALLO", "Traceback", "GUARDIA"))][:5] + lineas[-2:]):
        print("    ", l[:220])
print("SUITES MAL:", malas)
