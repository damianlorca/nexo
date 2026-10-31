"""Consulta selectiva multi-IA para el replanteamiento profundo de arquitectura
(local-first, multiagente local, gestion de proyectos/chats en Gemini/ChatGPT).

SOLO dos preguntas, elegidas porque hay alternativas reales y el
conocimiento de otras IAs puede aportar algo que Claude no tenga de
primera mano (patrones concretos de orquestacion multiagente local en
2026, y automatizacion de gestion de proyectos/conversaciones en
interfaces web). NO es un barrido.

Mismo patron que consulta_fase2.py: Qwen local primero, luego
Gemini/ChatGPT via navegador.py con pausas largas (leccion ya aprendida
dos veces: pausas cortas mezclan respuestas).
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


SALIDA_JSON = RAIZ / "registros" / "replanteamiento_arquitectura.json"
SALIDA_TXT = RAIZ / "registros" / "replanteamiento_arquitectura.txt"
SALIDA_JSON.parent.mkdir(parents=True, exist_ok=True)

lineas: list[str] = []


def anotar(texto: str = "") -> None:
    print(texto, flush=True)
    lineas.append(str(texto))
    SALIDA_TXT.write_text("\n".join(lineas), encoding="utf-8")


PREGUNTAS = {
    "multiagente_local": (
        "Tengo un PC potente (12 nucleos/24 hilos, 31GB RAM, iGPU con poca "
        "VRAM) corriendo modelos locales via Ollama (familia Qwen). Estoy "
        "disenando un asistente personal donde un 'orquestador local' "
        "reciba la peticion del usuario, decida si la puede resolver el "
        "mismo, delegue a un 'worker' local, a un 'verificador' local, o "
        "escale a una IA de pago (Claude/Gemini/ChatGPT) solo si hace "
        "falta. Pregunta concreta: en 2026, para un asistente personal que "
        "corre muchas horas sin supervision, tiene mas sentido (a) varios "
        "modelos/instancias locales con roles separados (orquestador, "
        "worker, verificador, vigilante) coordinados por codigo propio, o "
        "(b) un unico modelo local razonablemente grande con distintos "
        "prompts/roles segun la llamada, delegando la orquestacion real a "
        "codigo determinista en vez de a otro modelo. Que frameworks o "
        "patrones concretos existen ya para orquestar varios agentes "
        "LLM locales en la misma maquina (LangGraph local, CrewAI local, "
        "AutoGen local, u otros). Responde con nombres concretos y tu "
        "recomendacion, en menos de 250 palabras."
    ),
    "gestion_chats_proveedores": (
        "Tengo un script Python con Playwright que automatiza mi propia "
        "sesion de Chrome ya autenticada en Gemini y ChatGPT (a traves de "
        "CDP), enviando un prompt y extrayendo la respuesta. Hoy solo sabe "
        "abrir la primera pestana que encuentra de cada sitio y escribir "
        "en el chat que este activo -- no distingue proyectos ni "
        "conversaciones. Quiero ampliarlo para que pueda: crear una nueva "
        "conversacion, seleccionar una conversacion existente por titulo, "
        "detectar en que proyecto/carpeta esta trabajando, y verificar que "
        "esta en el espacio correcto antes de escribir. Pregunta concreta: "
        "en 2026, existe ya algun patron, libreria o proyecto open-source "
        "que resuelva 'gestion de conversaciones/proyectos' sobre las "
        "interfaces web de Gemini o ChatGPT via automatizacion de "
        "navegador (no via su API oficial), o hay que construirlo a mano "
        "leyendo el DOM de cada sitio. Si conoces limitaciones o riesgos "
        "concretos de esto (cambios frecuentes de interfaz, terminos de "
        "uso), dilo. Responde en menos de 250 palabras."
    ),
}

resultados: dict[str, dict] = {}


anotar(f"CONSULTA REPLANTEAMIENTO ARQUITECTURA  {time.strftime('%Y-%m-%d %H:%M:%S')}")
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

        anotar("(pausa de 75s antes de la siguiente pregunta, leccion "
               "aprendida: pausas cortas mezclan respuestas)")
        time.sleep(75)


anotar("\nFIN_CONSULTA_REPLANTEAMIENTO")
