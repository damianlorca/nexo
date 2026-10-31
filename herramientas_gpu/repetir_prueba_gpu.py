# -*- coding: utf-8 -*-
"""Repite prueba_gpu_ollama.py N veces por modelo y resume medianas (T132)."""
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
MODELOS = ["llama3.2:3b", "qwen2.5:7b"]
N = 3

for i in range(20):
    try:
        v = httpx.get("http://127.0.0.1:11435/api/version", timeout=3).json()
        print("instancia igpu viva", v); break
    except Exception:
        time.sleep(2)
else:
    print("ABORTADO: la instancia :11435 no responde"); sys.exit(1)

resumen = {}
for m in MODELOS:
    filas = []
    for r in range(N):
        p = subprocess.run([sys.executable, "prueba_gpu_ollama.py", m], cwd=RAIZ, capture_output=True, text=True, timeout=900)
        f = RAIZ / "registros" / f"prueba_gpu_{m.replace(':', '_')}.json"
        if p.returncode != 0 or not f.is_file():
            print(m, r, "FALLO", p.stdout[-300:], p.stderr[-300:]); continue
        d = json.loads(f.read_text(encoding="utf-8"))
        filas.append(d)
        print(m, r, {k: (d.get(k) or {}).get("gen_tok_s") for k in ("cpu", "igpu")},
              {k: (d.get(k) or {}).get("prompt_tok_s") for k in ("cpu", "igpu")},
              "vram", (d.get("igpu") or {}).get("vram_gb"))
    def med(k, c):
        xs = [(x.get(k) or {}).get(c) for x in filas if isinstance((x.get(k) or {}).get(c), (int, float))]
        return round(statistics.median(xs), 1) if xs else None
    resumen[m] = {k: {c: med(k, c) for c in ("gen_tok_s", "prompt_tok_s", "carga_s", "segundos_total")} for k in ("cpu", "igpu")}
    resumen[m]["repeticiones"] = len(filas)

print(json.dumps(resumen, indent=1))
(RAIZ / "registros" / "prueba_gpu_resumen_repeticiones.json").write_text(json.dumps(resumen, indent=1), encoding="utf-8")
