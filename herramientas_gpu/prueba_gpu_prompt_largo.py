# -*- coding: utf-8 -*-
"""T132: CPU (:11434) vs iGPU (:11435) con un prompt LARGO (~3000 tokens),
que es la carga real de resumir/revisar. 2 repeticiones, qwen2.5:7b."""
import json
import os
import statistics
import subprocess
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
texto = (RAIZ / "router.py").read_text(encoding="utf-8")[:11000]
PROMPT = "Resume en 5 puntos que hace este codigo:\n\n" + texto
MODELO = "qwen2.5:7b"
res = {}
for nombre, puerto in (("cpu", 11434), ("igpu", 11435)):
    filas = []
    for r in range(2):
        cuerpo = {"model": MODELO, "stream": False, "keep_alive": "1m",
                  "options": {"num_ctx": 4096, "temperature": 0, "num_predict": 200},
                  "messages": [{"role": "user", "content": PROMPT}]}
        t0 = time.time()
        d = httpx.post(f"http://127.0.0.1:{puerto}/api/chat", json=cuerpo, timeout=600).json()
        filas.append({"total_s": round(time.time() - t0, 1),
                      "prompt_tokens": d.get("prompt_eval_count"),
                      "prompt_s": round(d.get("prompt_eval_duration", 0) / 1e9, 1),
                      "gen_s": round(d.get("eval_duration", 0) / 1e9, 1),
                      "gen_tokens": d.get("eval_count")})
        print(nombre, r, filas[-1], flush=True)
    subprocess.run(["ollama", "stop", MODELO], capture_output=True,
                   env={**os.environ, "OLLAMA_HOST": f"127.0.0.1:{puerto}"})
    time.sleep(2)
    res[nombre] = {"mediana_total_s": statistics.median(f["total_s"] for f in filas), "filas": filas}
print(json.dumps(res, indent=1))
(RAIZ / "registros" / "prueba_gpu_prompt_largo.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
