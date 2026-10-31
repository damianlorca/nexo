"""Relleno de Fase 3: solo los 4 huecos que quedaron sin capturar
limpiamente en consulta_fase3.py (Gemini D y E, ChatGPT D y E),
por un desajuste real de extraccion en navegador.py cuando la pestana
ya tiene conversacion previa (la respuesta se captura antes de que
termine de generarse del todo, y se lee la respuesta ANTERIOR en la
siguiente pregunta). Aqui se espera mucho mas entre pregunta y
pregunta (60s) para dar tiempo de sobra a que la respuesta anterior
se asiente antes de mandar la siguiente. No se toca navegador.py.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import logging  # noqa: E402
logging.disable(logging.INFO)

import proveedores  # noqa: E402
from extremidades import navegador  # noqa: E402


SALIDA_JSON = RAIZ / "registros" / "fase3_relleno.json"
SALIDA_TXT = RAIZ / "registros" / "fase3_relleno.txt"
SALIDA_JSON.parent.mkdir(parents=True, exist_ok=True)

lineas: list[str] = []


def anotar(texto: str = "") -> None:
    print(texto, flush=True)
    lineas.append(str(texto))
    SALIDA_TXT.write_text("\n".join(lineas), encoding="utf-8")


CASOS = json.loads(Path("registros/fase3_multi_ia.json").read_text(encoding="utf-8"))["casos"]
FALTAN = {c["id"]: c for c in CASOS if c["id"] in ("D_comunicacion_entre_ias", "E_autonomia_completa")}

resultados: dict[str, dict] = {}

anotar(f"RELLENO FASE 3  {time.strftime('%Y-%m-%d %H:%M:%S')}")
anotar("=" * 70)

if not navegador.activo():
    navegador.arrancar()
    time.sleep(5)


def preguntar_proveedor(proveedor, caso: dict) -> dict:
    contexto = json.dumps({k: v for k, v in caso.items() if k != "id"}, ensure_ascii=False, indent=2)
    prompt = (
        "Contexto tecnico compacto de un requisito pendiente de un proyecto "
        "personal de automatizacion con IA (Nexo). Responde en espanol, "
        "de forma concreta y breve (maximo 200 palabras): como se podria "
        "implementar o aproximar esto, dadas las restricciones. No hace "
        "falta que repitas el contexto.\n\n" + contexto
    )
    inicio = time.time()
    try:
        r = proveedor.enviar(prompt)
        return {"estado": r.estado, "texto": r.texto, "detalle": r.detalle,
                "segundos": round(time.time() - inicio, 1)}
    except Exception as e:
        return {"estado": "ERROR", "texto": "", "detalle": f"{type(e).__name__}: {e}",
                "segundos": round(time.time() - inicio, 1)}


gemini = proveedores.GeminiProvider()
chatgpt = proveedores.ChatGPTProvider()

for nombre_prov, proveedor in (("gemini", gemini), ("chatgpt", chatgpt)):
    anotar(f"\n--- {nombre_prov.upper()} ---")

    # Espera larga ANTES de empezar con este proveedor, para que
    # cualquier respuesta pendiente de la tanda anterior (consulta_fase3.py)
    # ya este asentada del todo.
    time.sleep(20)

    for caso_id, caso in FALTAN.items():
        anotar(f"\n[{caso_id}] preguntando a {nombre_prov}...")

        r = preguntar_proveedor(proveedor, caso)

        resultados.setdefault(caso_id, {})[nombre_prov] = r

        anotar(f"  estado={r['estado']}  {r['segundos']}s")
        anotar(f"  {r['texto'][:800] if r['texto'] else r['detalle']}")

        SALIDA_JSON.write_text(
            json.dumps({"resultados": resultados}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Espera larga TRAS cada pregunta antes de mandar la siguiente,
        # para no repetir el desajuste de consulta_fase3.py.
        anotar("  esperando 60s a que se asiente del todo antes de seguir...")
        time.sleep(60)

anotar("\n" + "=" * 70)
anotar("FIN_RELLENO")
