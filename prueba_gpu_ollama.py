# -*- coding: utf-8 -*-
"""Compara CPU (Ollama normal, :11434) con la iGPU Radeon 890M (instancia de prueba
en :11435 con OLLAMA_IGPU_ENABLE=1). Mismo modelo, mismo prompt, API nativa,
num_ctx 4096, tope de salida. Guardas: RAM libre >= 8 GB y ollama stop al final.
Uso: python prueba_gpu_ollama.py [modelo]   (por defecto llama3.2:3b)"""
import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx


class _MEM(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def ram():
    m = _MEM(); m.dwLength = ctypes.sizeof(_MEM)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 2**30


MODELO = sys.argv[1] if len(sys.argv) > 1 else "llama3.2:3b"
PROMPT = "Explica en unas 150 palabras, en espanol, como funciona una cola de tareas con prioridades."
res = {"modelo": MODELO, "ram_inicio_gb": round(ram(), 1)}
if res["ram_inicio_gb"] < 8:
    print("ABORTADO: poca RAM libre", res); sys.exit(1)

for nombre, puerto in (("cpu", 11434), ("igpu", 11435)):
    cuerpo = {"model": MODELO, "stream": False, "keep_alive": "1m",
              "options": {"num_ctx": 4096, "temperature": 0, "num_predict": 250},
              "messages": [{"role": "user", "content": PROMPT}]}
    t0 = time.time()
    try:
        d = httpx.post(f"http://127.0.0.1:{puerto}/api/chat", json=cuerpo, timeout=300).json()
    except Exception as e:
        res[nombre] = {"error": str(e)}; continue
    ps = httpx.get(f"http://127.0.0.1:{puerto}/api/ps", timeout=10).json().get("models", [])
    res[nombre] = {
        "segundos_total": round(time.time() - t0, 1),
        "carga_s": round(d.get("load_duration", 0) / 1e9, 1),
        "prompt_tok_s": round(d.get("prompt_eval_count", 0) / max(d.get("prompt_eval_duration", 1) / 1e9, 1e-9), 1),
        "gen_tok_s": round(d.get("eval_count", 0) / max(d.get("eval_duration", 1) / 1e9, 1e-9), 1),
        "tokens_generados": d.get("eval_count"),
        "vram_gb": round(sum(m.get("size_vram", 0) for m in ps) / 2**30, 2),
        "tamano_gb": round(sum(m.get("size", 0) for m in ps) / 2**30, 2),
        "ram_libre_gb": round(ram(), 1),
        "inicio_respuesta": (d.get("message", {}).get("content") or "")[:120],
    }
    subprocess.run(["ollama", "stop", MODELO], capture_output=True, env={"OLLAMA_HOST": f"127.0.0.1:{puerto}", **__import__("os").environ})
    time.sleep(2)

out = Path("registros") / f"prueba_gpu_{MODELO.replace(':', '_')}.json"
out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=1))
