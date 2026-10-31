# -*- coding: utf-8 -*-
"""Banco corto de modelos OpenRouter :free como revisores del tribunal (T162, Damian 04/10).

Mismos dos casos y mismo criterio que herramientas_nube/_banco_tribunal_0410.py (prompt REAL del tribunal: un
borrador con un error de hecho y uno limpio; vale si responde en plazo, el dictamen se lee entero y en el caso con
error no aprueba sin mas). SOLO ids que terminan en ':free' (fail-closed, igual que OpenRouterProvider). Candidatos:
familias que NO tenemos (el 04/10 no hay DeepSeek, Llama ni Kimi con :free en OpenRouter). La clave la lee
OpenRouterProvider y no se imprime nunca. Cada modelo pasa por el proveedor real (anota nucleo/modelos_estado.py).
Resultado en herramientas_nube/_banco_openrouter_0410_resultado.json.

  .venv\Scripts\python.exe herramientas_nube\_banco_openrouter_0410.py [modelo:free ...]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import proveedores  # noqa: E402
from nucleo import tribunal  # noqa: E402
from herramientas_nube._banco_tribunal_0410 import CASOS, prompt  # noqa: E402

CANDIDATOS = ["thinkingmachines/inkling:free", "thinkingmachines/inkling-small:free", "poolside/laguna-s-2.1:free",
              "cohere/north-mini-code:free", "apodex/apodex-1.1-mini:free", "dots-studio/dots-3-note-preview:free"]
FAMILIA = {"thinkingmachines": "thinkingmachines", "poolside": "poolside", "cohere": "cohere", "apodex": "apodex",
           "dots-studio": "dots-studio"}


def probar(modelo: str) -> dict:
    p = proveedores.OpenRouterProvider(modelos=(modelo,), timeout=120.0, rondas=1)
    if not p.modelos:
        return {"vale": False, "error": "no es :free: no se llama"}
    filas = {}
    for caso, texto in CASOS.items():
        inicio = time.time()
        r = p.enviar(prompt(texto))
        seg = round(time.time() - inicio, 1)
        if not r.ok:
            filas[caso] = {"ok": False, "error": r.estado, "segundos": seg}
            continue
        d = tribunal.parsear(r.texto, 1, es_inv=False)
        filas[caso] = {"ok": not d["error"], "error": d["error"], "segundos": seg, "global": d["global"],
                       "fallos": d["fallos"]}
    err = filas["con_error"]
    detecta = bool(err.get("ok") and (err["global"] != "APROBAR" or any(f[0] == "FALSO" for f in err["fallos"])))
    return dict(filas, vale=all(f.get("ok") for f in filas.values()), detecta_error=detecta)


def main(modelos: list[str]) -> int:
    if not proveedores.OpenRouterProvider()._clave():
        print("Falta una clave valida en secretos.toml [openrouter] api_key")
        return 1
    salida = {}
    for m in modelos or CANDIDATOS:
        salida[m] = probar(m)
        f = salida[m]
        print(f"{m:45s} vale={f.get('vale')!s:5} detecta_error={f.get('detecta_error')!s:5} "
              + " | ".join(f"{c}: {'OK' if v.get('ok') else v.get('error')} {v.get('segundos')}s {v.get('global', '')}"
                           for c, v in f.items() if isinstance(v, dict)))
        time.sleep(5)
    (RAIZ / "herramientas_nube" / "_banco_openrouter_0410_resultado.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    sys.exit(main([a for a in sys.argv[1:] if a.endswith(":free")]))
