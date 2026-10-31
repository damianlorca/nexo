# -*- coding: utf-8 -*-
"""Prueba corta de banco para los revisores del tribunal (T667, Damian 04/10).

Sustitutos de los modelos retirados (mistral-nemotron HTTP 410, groq qwen3-32b HTTP 404) y recomprobacion de
glm-5.3-flash (timeout en el primer uso). Dos casos con el PROMPT REAL del tribunal (nucleo.tribunal.prompt):
un borrador con un error de hecho y uno limpio. Vale si responde en el plazo, el dictamen se lee entero
(tribunal.parsear: GLOBAL, P1 y FIN_DICTAMEN) y en el caso con error no aprueba sin mas.
HTTP directo (como herramientas_nube/_banco_nvidia_2809.py): no toca memoria/enfriamiento.json. Las claves las lee
el codigo de proveedores y no se imprimen. Resultado en herramientas_nube/_banco_tribunal_0410_resultado.json.

  .venv\\Scripts\\python.exe herramientas_nube\\_banco_tribunal_0410.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import httpx  # noqa: E402

import proveedores  # noqa: E402
from nucleo import tribunal  # noqa: E402

TIMEOUT = 120.0
MAX_TOKENS = 4096
URLS = {"groq": "https://api.groq.com/openai/v1/chat/completions", "nvidia": proveedores.NvidiaProvider.URL}
CANDIDATOS = [("groq", "qwen/qwen3.8-27b"), ("nvidia", "moonshotai/kimi-k3"), ("nvidia", "deepseek-ai/deepseek-v4.1-flash"),
              ("nvidia", "z-ai/glm-5.3-flash"), ("nvidia", "mistralai/mistral-nemotron"), ("groq", "qwen/qwen3-32b")]
PROP = "QUE: Usar Python para el script de copias | DONDE: documentacion | VALOR: 3 | ESFUERZO: 1 | RIESGO: bajo"
CASOS = {
    "con_error": "Python fue creado por Guido van Rossum y se publico por primera vez en 1995. Recomiendo usarlo "
                 "para el script de copias de seguridad de NEXO porque ya esta instalado en el PC.",
    "limpio": "Python ya esta instalado en el PC de NEXO (.venv). Recomiendo usarlo para el script de copias de "
              "seguridad: evita una dependencia nueva y los tests ya corren con pytest.",
}


def _clave(prov: str) -> str:
    return (proveedores.GroqProvider() if prov == "groq" else proveedores.NvidiaProvider())._clave()


def prompt(texto: str) -> str:
    e = {"texto": texto, "textos_propuestas": [PROP], "es_inv": False, "tipo": "general",
         "titulo": "Elegir lenguaje para el script de copias"}
    return tribunal.prompt(e, "tribunal")


def llamar(prov: str, modelo: str, texto: str) -> dict:
    inicio = time.time()
    try:
        r = httpx.post(URLS[prov], headers={"Authorization": f"Bearer {_clave(prov)}", "Accept": "application/json"},
                       json={"model": modelo, "messages": [{"role": "user", "content": prompt(texto)}],
                             "max_tokens": MAX_TOKENS}, timeout=TIMEOUT)
    except Exception as e:
        return {"ok": False, "error": type(e).__name__, "segundos": round(time.time() - inicio, 1)}
    s = round(time.time() - inicio, 1)
    if r.status_code != 200:
        return {"ok": False, "error": f"HTTP {r.status_code}", "segundos": s}
    try:
        contenido = r.json()["choices"][0]["message"]["content"] or ""
    except Exception:
        contenido = ""
    d = tribunal.parsear(contenido, 1, es_inv=False)
    return {"ok": not d["error"], "error": d["error"], "segundos": s, "global": d["global"],
            "fallos": d["fallos"], "texto": contenido[-600:]}


def main() -> int:
    salida = {}
    for prov, modelo in CANDIDATOS:
        filas = {caso: llamar(prov, modelo, texto) for caso, texto in CASOS.items()}
        err = filas["con_error"]
        detecta = err.get("ok") and (err["global"] != "APROBAR" or any(f[0] == "FALSO" for f in err["fallos"]))
        vale = all(f.get("ok") for f in filas.values())
        salida[f"{prov}:{modelo}"] = dict(filas, vale=vale, detecta_error=bool(detecta))
        print(f"{prov}:{modelo:40s} vale={vale!s:5} detecta_error={bool(detecta)!s:5} "
              + " | ".join(f"{c}: {'OK' if f.get('ok') else f.get('error')} {f.get('segundos')}s {f.get('global', '')}"
                           for c, f in filas.items()))
    (RAIZ / "herramientas_nube" / "_banco_tribunal_0410_resultado.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    sys.exit(main())
