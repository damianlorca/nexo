# -*- coding: utf-8 -*-
"""T134: test de modelos locales de 05:00 a 06:00 con SUPERVISOR (autorizado por Damian 23/09).

- Un modelo cada vez, en orden de interes. Banco completo (revisor, verificador, codigo) con
  banco_roles_v2.py, bajo la guardia de Python.
- SUPERVISOR (hilo aparte, cada 3 s):
    * RAM libre < 2,5 GB  -> descarga el modelo y mata el banco (protege el PC);
    * modelo con mas de TOPE_MODELO min -> se corta y se pasa al siguiente;
    * 05:55 -> ultimo aviso: no se empieza ningun modelo mas; 05:58 -> corte duro;
    * parada de emergencia (/parar) -> corta todo.
- Antes de cada modelo: si no hay RAM para su tamano (+3 GB), se salta.
- Al final: resumen en registros/test_modelos_<fecha>.json, nota en el vault y en T134.
Uso: python herramientas_modelos/modelos_supervisado.py [--hasta=05:58] [--simular]

N01 (H05): antes se llamaba test_modelos_supervisado.py. Con el prefijo test_ y todo el
codigo a nivel de modulo, un `pytest` a secas lo importaba y arrancaba el test de verdad.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from nucleo import parada  # noqa: E402

# (modelo, GB en RAM aprox) en orden de interes: MoE rapidos primero, densos grandes al final.
MODELOS = [
    ("gpt-oss:20b", 13.5), ("qwen3-coder:30b", 18.5), ("gemma4:12b", 8.0), ("qwen3.5:9b", 7.0),
    ("qwen3:14b", 9.5), ("devstral-small-2:24b", 15.5), ("qwen3.8:27b", 17.5),
]
TOPE_MODELO = 14 * 60
RAM_CORTE = 2.5
args = sys.argv[1:]
HASTA = next((a.split("=", 1)[1] for a in args if a.startswith("--hasta=")), "05:58")
SIMULAR = "--simular" in args


class _MEM(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def ram_libre() -> float:
    m = _MEM(); m.dwLength = ctypes.sizeof(_MEM)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 2**30


def limite_epoch(hhmm: str) -> float:
    h, m = map(int, hhmm.split(":"))
    ahora = datetime.now()
    obj = ahora.replace(hour=h, minute=m, second=0, microsecond=0)
    return obj.timestamp() if obj > ahora else obj.timestamp() + 86400


FIN = limite_epoch(HASTA)
ULTIMO_INICIO = FIN - 3 * 60
instalados = subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout
log = []


def anotar(msg: str) -> None:
    linea = f"{datetime.now():%H:%M:%S} {msg}"
    log.append(linea)
    print(linea, flush=True)


def supervisar(proc, modelo: str, t0: float, estado: dict) -> None:
    while proc.poll() is None:
        motivo = None
        if ram_libre() < RAM_CORTE:
            motivo = f"RAM libre {ram_libre():.1f} GB < {RAM_CORTE}"
        elif time.time() - t0 > TOPE_MODELO:
            motivo = f"tope de {TOPE_MODELO // 60} min por modelo"
        elif time.time() > FIN:
            motivo = f"hora limite {HASTA}"
        elif parada.activa():
            motivo = f"parada de emergencia ({parada.activa()})"
        if motivo:
            estado["corte"] = motivo
            anotar(f"SUPERVISOR corta {modelo}: {motivo}")
            proc.kill()
            subprocess.run(["ollama", "stop", modelo], capture_output=True)
            return
        time.sleep(3)


def cerrar_chrome_nexo() -> None:
    """Libera RAM: cierra SOLO el Chrome de NEXO (perfil propio, CDP 9333). El turno de las 03:30 ya ha acabado."""
    try:
        import httpx
        httpx.get("http://127.0.0.1:9333/json/version", timeout=3)
        from playwright.sync_api import sync_playwright
        from extremidades import navegador
        # T193: con el candado del Chrome, para no cerrarlo a mitad de una pregunta de otro proceso.
        with navegador.en_exclusiva("cerrar el Chrome de NEXO (modelos_supervisado)", espera=300), \
                sync_playwright() as pw:
            b = pw.chromium.connect_over_cdp("http://127.0.0.1:9333")
            b.new_browser_cdp_session().send("Browser.close")
        anotar("Chrome de NEXO cerrado para liberar RAM")
    except Exception as e:
        anotar(f"Chrome de NEXO no estaba abierto o no se pudo cerrar ({type(e).__name__})")


resultados = []
if not SIMULAR:
    cerrar_chrome_nexo()
    time.sleep(5)
anotar(f"inicio; hasta {HASTA}; RAM libre {ram_libre():.1f} GB; simular={SIMULAR}")
for modelo, gb in MODELOS:
    if parada.activa() or time.time() > ULTIMO_INICIO:
        anotar(f"no se empiezan mas modelos ({'parada' if parada.activa() else 'cerca de la hora limite'})")
        break
    if modelo.split(":")[0] + ":" + modelo.split(":")[1] not in instalados and modelo not in instalados:
        anotar(f"{modelo}: no instalado, se salta")
        resultados.append({"modelo": modelo, "estado": "no instalado"})
        continue
    libre = ram_libre()
    if libre < gb + 1.5:
        anotar(f"{modelo}: SALTADO, necesita ~{gb + 1.5:.0f} GB libres y hay {libre:.1f}")
        resultados.append({"modelo": modelo, "estado": f"saltado por RAM ({libre:.1f} GB)"})
        continue
    if SIMULAR:
        anotar(f"{modelo}: (simulado) se probaria con {libre:.1f} GB libres")
        resultados.append({"modelo": modelo, "estado": "simulado"})
        continue
    anotar(f"{modelo}: empieza (RAM libre {libre:.1f} GB)")
    t0 = time.time()
    env = dict(os.environ, BANCO_RAM_MINIMA=str(gb + 1))
    proc = subprocess.Popen([sys.executable, str(RAIZ / "banco_roles_v2.py"), modelo], cwd=RAIZ, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    estado: dict = {}
    hilo = threading.Thread(target=supervisar, args=(proc, modelo, t0, estado), daemon=True)
    hilo.start()
    salida = proc.communicate()[0] if proc.poll() is None else ""
    hilo.join(timeout=5)
    subprocess.run(["ollama", "stop", modelo], capture_output=True)
    json_b = sorted((RAIZ / "registros").glob("banco_roles_v2_*.json"), key=lambda f: f.stat().st_mtime)[-1]
    filas = [f for f in json.loads(json_b.read_text(encoding="utf-8")).get("filas", []) if f["modelo"] == modelo]
    por = defaultdict(lambda: [0, 0, 0.0])
    for f in filas:
        k = f"{f['rol']}/{f['prompt']}"
        por[k][0] += 1; por[k][1] += bool(f["acierto"]); por[k][2] += f.get("segundos", 0)
    res = {"modelo": modelo, "estado": estado.get("corte", "completo"), "minutos": round((time.time() - t0) / 60, 1),
           "aciertos": {k: f"{a}/{n}" for k, (n, a, s) in por.items()},
           "seg_por_caso": round(sum(s for n, a, s in por.values()) / max(sum(n for n, a, s in por.values()), 1), 1),
           "registro": json_b.name}
    anotar(f"{modelo}: {res['estado']} en {res['minutos']} min; {res['aciertos']}; {res['seg_por_caso']} s/caso")
    resultados.append(res)
    time.sleep(10)  # dejar respirar la RAM entre modelos

salida = RAIZ / "registros" / f"test_modelos_{datetime.now():%Y%m%d_%H%M}.json"
salida.write_text(json.dumps({"resultados": resultados, "log": log}, ensure_ascii=False, indent=1), encoding="utf-8")
if not SIMULAR:
    vault = RAIZ.parent / "contexto" / "proyectos" / "nexo" / "handoffs-turno" / f"test_modelos_{datetime.now():%Y%m%d}.md"
    try:
        vault.parent.mkdir(parents=True, exist_ok=True)
        lineas = [f"# Test de modelos locales supervisado — {datetime.now():%d/%m/%Y}", "",
                  "| Modelo | Estado | Min | Aciertos | s/caso |", "|---|---|---|---|---|"]
        for r in resultados:
            lineas.append(f"| {r['modelo']} | {r['estado']} | {r.get('minutos', '')} | {r.get('aciertos', '')} | {r.get('seg_por_caso', '')} |")
        lineas += ["", "Log:", "```", *log, "```"]
        vault.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        from nucleo import tareas as T
        T.anotar("T134", f"Test supervisado {datetime.now():%d/%m %H:%M}: " + "; ".join(
            f"{r['modelo']}={r['estado']} {r.get('aciertos', '')}" for r in resultados) + f". Detalle: {vault.name}")
    except Exception as e:
        anotar(f"no pude escribir el resumen: {e}")
print("FIN", salida)
