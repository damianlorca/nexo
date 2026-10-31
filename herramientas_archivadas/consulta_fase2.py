"""Consulta selectiva multi-IA para la revision de arquitectura (Fase 2).

SOLO dos preguntas, donde de verdad hay varias alternativas razonables
y el conocimiento de otras IAs puede aportar algo que Claude no tenga
de primera mano (modelos locales muy recientes, frameworks concretos
de automatizacion de escritorio). NO es un barrido masivo: es
selectivo, como pidio Damian.

Va en segundo plano (lanzar()) porque Gemini/ChatGPT tardan y hay que
espaciar las preguntas (leccion de la Fase 3: pausas cortas mezclan
respuestas). Pausas de 75s entre preguntas a la misma IA.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import logging  # noqa: E402
logging.disable(logging.INFO)

from extremidades import qwen, navegador  # noqa: E402


SALIDA_JSON = RAIZ / "registros" / "fase2_arquitectura.json"
SALIDA_TXT = RAIZ / "registros" / "fase2_arquitectura.txt"
SALIDA_JSON.parent.mkdir(parents=True, exist_ok=True)

lineas: list[str] = []


def anotar(texto: str = "") -> None:
    print(texto, flush=True)
    lineas.append(str(texto))
    SALIDA_TXT.write_text("\n".join(lineas), encoding="utf-8")


PREGUNTAS = {
    "modelos_locales": (
        "Tengo un portatil Windows con CPU AMD Ryzen AI 9 HX 370 (12 nucleos, "
        "24 hilos), 31 GB de RAM, y GPU integrada AMD Radeon 890M (solo unos "
        "3 GB utilizables via DirectML, sin CUDA). Hoy uso Ollama con "
        "qwen2.5:7b para tareas mecanicas rapidas (clasificar mensajes) y "
        "qwen3:14b para tareas con mas criterio. No me importa que el PC "
        "trabaje muchas horas al dia si eso ahorra cuota de un modelo de "
        "pago. Pregunta concreta: dado este hardware (mucha RAM y CPU, poca "
        "VRAM), en 2026 cual es el mejor modelo o combinacion de modelos "
        "locales para: (a) triaje/clasificacion rapida, (b) vigilar y "
        "verificar resultados de otro agente, (c) resumir contexto largo, "
        "(d) planificacion preliminar antes de llamar a un modelo caro. "
        "Sigue siendo Qwen la mejor opcion o hay alternativas mejores "
        "(Llama, Mistral, Phi, Gemma, DeepSeek...) para este caso. Responde "
        "con nombres y tamanos concretos, en menos de 250 palabras."
    ),
    "control_visual": (
        "Estoy disenando como un agente de IA pueda controlar un PC Windows "
        "cuando haga falta: ver la pantalla, hacer clic, escribir, cambiar "
        "de ventana, y recuperar situaciones donde una automatizacion "
        "estructurada (Playwright) se haya quedado atascada o la interfaz "
        "haya cambiado. Quiero una jerarquia: primero metodos "
        "estructurados/API cuando existan, despues UI Automation/accesibilidad "
        "de Windows, despues automatizacion de escritorio general, y solo "
        "como ultimo recurso vision por computador o coordenadas de pantalla. "
        "Pregunta concreta: que librerias o frameworks Python actuales en "
        "2026 son el estado del arte para esto en Windows (UI Automation, "
        "pywinauto, FlaUI, o alternativas), y si existe ya algun framework "
        "pensado especificamente para 'agentes de IA que controlan un PC' que "
        "combine estos niveles en vez de depender solo de vision. Responde "
        "con nombres concretos de librerias, en menos de 250 palabras."
    ),
}

resultados: dict[str, dict] = {}


anotar(f"CONSULTA FASE 2 - ARQUITECTURA  {time.strftime('%Y-%m-%d %H:%M:%S')}")
anotar("=" * 60)

# --------------------------------------------------------------- Qwen
anotar("\n=== QWEN (local) ===")

for clave, pregunta in PREGUNTAS.items():
    anotar(f"\n--- {clave} ---")

    try:
        respuesta = qwen.pedir(pregunta, criterio=True, max_tokens=1200)
        anotar(respuesta)
        resultados.setdefault(clave, {})["qwen"] = respuesta
    except Exception:
        anotar("EXCEPCION:")
        anotar(traceback.format_exc())
        resultados.setdefault(clave, {})["qwen"] = None

    SALIDA_JSON.write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8"
    )

# --------------------------------------------------------- Gemini/ChatGPT
if not navegador.activo():
    anotar("\nChrome no estaba activo, arrancando...")
    navegador.arrancar()

for sitio in ("gemini", "chatgpt"):
    anotar(f"\n=== {sitio.upper()} ===")

    for clave, pregunta in PREGUNTAS.items():
        anotar(f"\n--- {clave} ---")
        anotar("(esperando 20s antes de preguntar, para no pillar la pagina "
               "a medio redibujar)")
        time.sleep(20)

        try:
            respuesta = navegador.preguntar(sitio, pregunta, espera=150)
            anotar(respuesta)
            resultados.setdefault(clave, {})[sitio] = respuesta
        except Exception:
            anotar("EXCEPCION:")
            anotar(traceback.format_exc())
            resultados.setdefault(clave, {})[sitio] = None

        SALIDA_JSON.write_text(
            json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        anotar("(pausa de 75s antes de la siguiente pregunta, leccion de "
               "la Fase 3: pausas cortas mezclan respuestas)")
        time.sleep(75)


anotar("\nFIN_CONSULTA_FASE2")
