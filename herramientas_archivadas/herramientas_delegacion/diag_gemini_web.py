# -*- coding: utf-8 -*-
"""T066/T147: Gemini y ChatGPT web en conversacion NUEVA y modo Pro/Pensar, con el prompt de investigacion."""
import logging
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
for ruidoso in ("httpx", "httpcore", "urllib3", "asyncio"):
    logging.getLogger(ruidoso).setLevel(logging.WARNING)
from nucleo import trabajo  # noqa: E402
from proveedores import ChatGPTProvider, GeminiProvider  # noqa: E402

t = {"id": "T999", "titulo": "Evaluar Open WebUI como interfaz", "detalle": "Prueba de diagnostico: di que es Open WebUI."}
prompt = trabajo.INSTRUCCION["investigacion"] + f"\n\nTAREA {t['id']}: {t['titulo']}\nDETALLE: {t['detalle']}"
for prov in (GeminiProvider(), ChatGPTProvider()):
    t0 = time.time()
    r = prov.enviar(prompt)
    txt = r.texto or r.detalle
    print(f"== {prov.nombre} {r.estado} ({time.time()-t0:.0f}s) eco/negativa={trabajo._es_eco(prompt, txt)} ->", repr(txt[:250]), flush=True)
    time.sleep(15)
