# -*- coding: utf-8 -*-
"""Clasificador de tareas (paso previo del turno T079 y de las ordenes T140).

Pedido por Damian 23/09: antes de delegar, una pasada de CATEGORIZACION para
saber de que tipo es cada tarea y que IA le conviene. Qwen local (gratis)
decide la categoria; la tabla PROVEEDOR_POR_CATEGORIA propone quien la haria.
Esa tabla es PROVISIONAL: se sustituira por la matriz medida (T134/T085).

No cambia estado ni prioridad de nada. Solo anade etiquetas "cat:<x>" y
"prov:<y>" (y nota) si se llama con aplicar=True. Por defecto informa.

Uso:
    .venv\\Scripts\\python.exe -m nucleo.clasificador            # informa
    .venv\\Scripts\\python.exe -m nucleo.clasificador --aplicar  # etiqueta
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from nucleo import tareas as T

RAIZ = Path(__file__).resolve().parent.parent

CATEGORIAS = [
    "codigo",          # escribir/arreglar codigo de NEXO
    "investigacion",   # buscar/auditar informacion externa, repos, herramientas
    "redaccion",       # documentos, protocolos, textos
    "resumen",         # resumir/extraer de un texto dado
    "arquitectura",    # decisiones de diseno o seguridad importantes
    "operacion_pc",    # instalar, configurar, hardware, control del PC
    "personal",        # cosas de la vida de Damian (becas, videos, casa)
]

# PROVISIONAL hasta tener la matriz medida (T134/T085).
PROVEEDOR_POR_CATEGORIA = {
    "codigo": "claude",            # locales <=8B no pasan el banco de codigo (T134)
    "investigacion": "gemini",     # web con busqueda; borrador revisado despues
    "redaccion": "gemini_api",
    "resumen": "qwen",
    "arquitectura": "claude",
    "operacion_pc": "claude",      # toca el sistema: permisos + supervision
    "personal": "damian",
}

# Ojo: NO "master" (salta con MASTER_REQUIREMENTS_CHECKLIST: fallo medido en T078/T084 el 23/09).
PALABRAS_PERSONALES = ("beca", "explicalodamian", "google home", "waver", "parity", "monetizacion")

INSTRUCCION = (
    "Clasifica esta tarea de un proyecto de software (asistente personal con IA) en UNA categoria. "
    "codigo = programar o arreglar codigo; investigacion = buscar o auditar informacion, repos o herramientas; "
    "redaccion = escribir documentos o protocolos; resumen = resumir o extraer datos de un texto; "
    "arquitectura = decisiones de diseno o seguridad; operacion_pc = instalar, configurar, hardware; "
    "personal = asuntos personales del usuario (estudios, becas, videos, casa)."
)


def _texto(t: dict) -> str:
    return f"{t['titulo']}\n{(t.get('detalle') or '')[:600]}"


def clasificar(t: dict) -> str:
    # depende=damian NO implica personal: tambien marca "necesita su aprobacion" (T077). Solo palabras claras.
    if any(k in _texto(t).lower() for k in PALABRAS_PERSONALES):
        return "personal"
    from extremidades import qwen
    cat = qwen.clasificar(INSTRUCCION + "\n\nTAREA:\n" + _texto(t), CATEGORIAS, por_defecto="investigacion")
    if cat == "personal":
        # Revisor por regla (medido 23/09): Qwen mete tareas de NEXO en "personal". Sin palabra personal
        # clara, se repregunta sin esa opcion.
        sin_personal = [c for c in CATEGORIAS if c != "personal"]
        cat = qwen.clasificar(INSTRUCCION + "\nEsta tarea es del proyecto de software, NO personal."
                              "\n\nTAREA:\n" + _texto(t), sin_personal, por_defecto="arquitectura")
    return cat


def revisar(filas: list[dict]) -> dict:
    """Revisor: Gemini por API mira TODAS las clasificaciones de una vez y dice
    solo las que cambiaria. Devuelve {id: categoria_propuesta}. No aplica nada."""
    from proveedores import GeminiAPIProvider
    lineas = "\n".join(f"{f['id']} | {f['cat']} | {f['titulo']}" for f in filas)
    prompt = (INSTRUCCION + "\n\nRevisa estas clasificaciones (ID | categoria | titulo). Responde SOLO con las que "
              "estan MAL, una por linea, formato exacto: ID categoria_correcta. Si todas estan bien responde: TODAS_BIEN\n\n" + lineas)
    r = GeminiAPIProvider().enviar(prompt)
    if not r.ok:
        return {"_error": r.detalle}
    cambios = {}
    for linea in r.texto.splitlines():
        partes = linea.replace("|", " ").split()
        if len(partes) >= 2 and partes[0].startswith("T") and partes[1] in CATEGORIAS:
            cambios[partes[0]] = partes[1]
    return cambios


def pasada(aplicar: bool = False) -> list[dict]:
    vivas = [t for t in T.cargar()["tareas"] if t["estado"] in ("pendiente", "en_curso", "esperando")]
    filas = []
    for t in vivas:
        if any(e.startswith("cat:") for e in t.get("etiquetas") or []):
            continue
        cat = clasificar(t)
        prov = PROVEEDOR_POR_CATEGORIA.get(cat, "claude")
        filas.append({"id": t["id"], "cat": cat, "prov": prov, "titulo": t["titulo"][:80]})
        print(f"{t['id']} {cat:<13} {prov:<10} {t['titulo'][:70]}", flush=True)
        if aplicar:
            et = list(t.get("etiquetas") or []) + [f"cat:{cat}", f"prov:{prov}"]
            T.actualizar(t["id"], etiquetas=et)
    cambios = revisar(filas) if filas else {}
    print("REVISOR gemini_api propone cambiar:", cambios, flush=True)
    for f in filas:
        f["revisor"] = cambios.get(f["id"], "ok")
    salida = RAIZ / "registros" / f"clasificacion_{datetime.now():%Y%m%d_%H%M}.json"
    salida.write_text(json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")
    print("registro:", salida)
    return filas


REFERENCIA = RAIZ / "memoria" / "clasificacion_referencia.json"


def medir(filas: list[dict]) -> dict:
    ref = json.loads(REFERENCIA.read_text(encoding="utf-8"))
    comunes = [f for f in filas if f["id"] in ref]
    cat_ok = sum(f["cat"] == ref[f["id"]] for f in comunes)
    prov_ok = sum(f["prov"] == PROVEEDOR_POR_CATEGORIA[ref[f["id"]]] for f in comunes)
    fallos = [(f["id"], f["cat"], ref[f["id"]]) for f in comunes if f["cat"] != ref[f["id"]]]
    return {"n": len(comunes), "categoria_ok": cat_ok, "proveedor_ok": prov_ok, "fallos": fallos}


def aplicar_referencia() -> list[str]:
    """Aplica la referencia revisada por Claude (cuando el automatico no llega al 90 %)."""
    ref = json.loads(REFERENCIA.read_text(encoding="utf-8"))
    hechas = []
    for tid, cat in ref.items():
        if not tid.startswith("T"):
            continue
        t = T.buscar(tid)
        if not t or any(e.startswith("cat:") for e in t.get("etiquetas") or []):
            continue
        T.actualizar(tid, etiquetas=list(t.get("etiquetas") or []) + [f"cat:{cat}", f"prov:{PROVEEDOR_POR_CATEGORIA[cat]}"])
        hechas.append(tid)
    return hechas


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    a = sys.argv[1:]
    if "--aplicar-referencia" in a:
        print("etiquetadas:", aplicar_referencia())
    else:
        filas = pasada(aplicar="--aplicar" in a)
        if REFERENCIA.is_file():
            print("MEDIDA:", medir(filas))
