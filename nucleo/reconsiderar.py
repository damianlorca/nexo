# -*- coding: utf-8 -*-
"""E1 de la epica T686 (05/10): reconsiderar con el tribunal (T667) lo que la auditoria de cierres (T687) marco como
posible idea perdida, sin reabrirlo todo de golpe ni saltarse el freno F0 (T666).

Entran dos clases de filas del ultimo memoria/investigacion/auditoria_cierres_*.json:
  - "propuestas": propuestas descartadas por BORRADOR malo cuya idea no volvio y cuya origen esta cerrada
    (propuesta 'reabrir'); un lote = las de una misma tarea origen.
  - "vigia": candidatos de los lotes del vigia sin rastro o con rastro solo en descartes por borrador
    ('revisar a mano'); un lote = los de un mismo lote del vigia. Se saltan los que ya van en un lote de propuestas.

Cada lote es un EXPEDIENTE del tribunal ("reconsiderar_<origen>" / "reconsiderar_vigia_<lote>") con el campo
"reconsiderar"; el tribunal vota cada fila APROBAR (reabrir: la idea vale) o RECHAZAR (el descarte vale).
Aplicar (tribunal unanime, parcial o Damian):
  - RECHAZAR -> la propuesta sigue descartada con nota "Descartada (idea rechazada por el tribunal ...)": desde ahi
    cuenta como descarte de IDEA (registro de T688). Un candidato del vigia rechazado queda como tarea descartada
    con su motivo, para que el registro de descartes lo encuentre si alguien lo vuelve a pedir.
  - APROBAR -> vuelve a estado 'propuesta' (o se crea la propuesta del candidato) SOLO si cabe bajo
    freno.LIMITE_PROPUESTAS; lo que no cabe espera en el expediente (fase 'espera_freno') y se suelta en ciclos
    siguientes.
Ritmo: como mucho MAX_VIVOS lotes vivos a la vez y ninguno nuevo con el freno superado.

CLI: .venv\\Scripts\\python.exe -m nucleo.reconsiderar lotes | encolar [--max 2] | soltar
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from nucleo import freno
from nucleo import tareas as T

MAX_VIVOS = 2
PRE = "reconsiderar_"
FASE_FRENO = "espera_freno"
ET_ORIGEN = "origen:reconsiderar"
def _informe(ruta: Path | None = None) -> dict:
    from nucleo import auditoria_cierres as AC
    if ruta is None:
        cand = sorted(AC.INFORMES.glob("auditoria_cierres_*.json"))
        if not cand:
            return {}
        ruta = cand[-1]
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def lotes(informe: dict | None = None) -> list[dict]:
    """Los lotes a reconsiderar, en orden: primero los de propuestas (mas grandes primero), luego los del vigia."""
    inf = _informe() if informe is None else informe
    por_origen: dict[str, list[dict]] = {}
    for f in inf.get("propuestas_descartadas", []):
        if f.get("propuesta") == "reabrir":
            por_origen.setdefault(f["origen"], []).append(
                {"clave": f["id"], "texto": f.get("titulo", ""), "motivo": f.get("motivo", "")})
    ya = {i["clave"] for l in por_origen.values() for i in l}
    por_lote: dict[str, list[dict]] = {}
    for f in inf.get("candidatos_lotes", []):
        if f.get("propuesta") != "revisar a mano" or (f.get("rastro") and set(f["rastro"]) <= ya):
            continue
        por_lote.setdefault(f["lote"], []).append(
            {"clave": f"V:{f['candidato']}", "texto": f"{f['candidato']} ({f.get('url', '')}): {f.get('descripcion', '')}",
             "motivo": f.get("por_que", ""), "url": f.get("url", ""), "candidato": f["candidato"]})
    out = [{"nombre": f"{PRE}{o}", "clase": "propuestas", "origen": o, "items": l}
           for o, l in sorted(por_origen.items(), key=lambda x: (-len(x[1]), x[0]))]
    out += [{"nombre": f"{PRE}vigia_{o}", "clase": "vigia", "origen": o, "items": l}
            for o, l in sorted(por_lote.items(), key=lambda x: (-len(x[1]), x[0]))]
    return out


def _texto_item(i: dict, clase: str) -> str:
    if clase == "propuestas":
        p = T.buscar(i["clave"])
        det = " | ".join(x.strip() for x in ((p or {}).get("detalle") or "").splitlines()[:4] if x.strip())
        return (det or i["texto"]) + f" | DESCARTADA POR: {i['motivo'][:200]}"
    return i["texto"]


def expediente(lote: dict) -> dict:
    from nucleo import tribunal
    origen = T.buscar(lote["origen"])
    titulo = (origen or {}).get("titulo", "") if origen and origen["id"] == lote["origen"] else ""
    contexto = ("Ideas descartadas de la tarea " if lote["clase"] == "propuestas" else "Candidatos del lote del vigia ") \
        + f"{lote['origen']} ({titulo[:150]}). Cada propuesta lleva el motivo por el que se descarto."
    return {"nombre": lote["nombre"], "origen": lote["origen"], "revision": "", "titulo": f"Reconsiderar: {titulo[:120]}",
            "tipo": "reconsideracion", "es_inv": False, "autor": "", "modelos_autor": [],
            "propuestas": [i["clave"] for i in lote["items"]],
            "textos_propuestas": [_texto_item(i, lote["clase"]) for i in lote["items"]], "texto": contexto,
            "fase": "tribunal", "motivo": "", "dictamenes": {"tribunal": [], "apelacion": []}, "fallos": [],
            "resumen": "", "decision": None, "decision_tribunal": None, "quien": None, "vigilado": False,
            "calibracion": None, "creado": tribunal._ahora(), "actualizado": tribunal._ahora(),
            "reconsiderar": {"clase": lote["clase"], "items": {i["clave"]: i for i in lote["items"]},
                             "reabiertas": [], "confirmadas": [], "espera_freno": []}}


def vivos(exps: dict | None = None) -> list[str]:
    from nucleo import tribunal
    exps = tribunal.expedientes() if exps is None else exps
    return [n for n, e in exps.items() if e.get("reconsiderar") and e["fase"] != "resuelto"]


def encolar(maximo: int = MAX_VIVOS, informe: dict | None = None) -> dict:
    """Mete lotes nuevos en el tribunal hasta tener `maximo` vivos, solo si el freno F0 no esta superado."""
    from nucleo import tribunal
    cola = freno.estado_cola()
    if cola["superado"]:
        return {"encolados": [], "motivo": "freno F0: " + "; ".join(cola["motivos"])}
    nuevos = []
    with tribunal._editar() as exps:
        hueco = maximo - len(vivos(exps))
        for l in lotes(informe):
            if hueco <= 0:
                break
            if l["nombre"] in exps:
                continue
            exps[l["nombre"]] = expediente(l)
            nuevos.append(l["nombre"])
            hueco -= 1
    return {"encolados": nuevos, "motivo": "" if nuevos else "sin hueco o sin lotes nuevos"}


def candidatas(exps: dict) -> int:
    """Trabajo que el turno del tribunal puede hacer aqui sin llamar a nadie: lotes que caben y aprobadas en espera."""
    if freno.estado_cola()["superado"]:
        return 0
    espera = sum(1 for e in exps.values() if e.get("fase") == FASE_FRENO) if _hueco_freno() > 0 else 0
    hueco = MAX_VIVOS - len(vivos(exps))
    try:
        nuevos = sum(1 for l in lotes() if l["nombre"] not in exps) if hueco > 0 else 0
    except (OSError, ValueError):
        nuevos = 0
    return espera + min(max(hueco, 0), nuevos)


# ------------------------------------------------------------------ aplicar
def _hueco_freno() -> int:
    return freno.LIMITE_PROPUESTAS - freno.estado_cola()["propuestas"]


def _confirmar(e: dict, clave: str, motivo: str, quien: str) -> None:
    r = e["reconsiderar"]
    item = r["items"][clave]
    nota = f"Descartada (idea rechazada por {quien} en la reconsideracion {e['nombre']}): {motivo[:300]}"
    if r["clase"] == "propuestas":
        T.anotar(clave, nota)
    else:
        t = T.anadir(f"[Candidato del vigia {e['origen']}] {item['candidato']}",
                     detalle=f"{item['texto']}\nReconsiderado por {quien} ({e['nombre']}): no aporta a NEXO.",
                     estado="descartada", depende="ia", importancia=2, urgencia=1, dificultad=1, coste=1,
                     etiquetas=["cat:propuesta", ET_ORIGEN, f"tarea_origen:{e['origen']}"])
        T.anotar(t["id"], nota)
    r["confirmadas"].append(clave)


def _reabrir(e: dict, clave: str, motivo: str, quien: str) -> bool:
    if _hueco_freno() <= 0:
        if clave not in e["reconsiderar"]["espera_freno"]:
            e["reconsiderar"]["espera_freno"].append(clave)
        return False
    r = e["reconsiderar"]
    item = r["items"][clave]
    if r["clase"] == "propuestas":
        T.actualizar(clave, estado="propuesta")
        T.anotar(clave, f"Reabierta como propuesta por {quien} (reconsideracion {e['nombre']}): {motivo[:300]}")
        tid = clave
    else:
        t = T.anadir(f"[Propuesta de {e['origen']}] Investigar {item['candidato']}",
                     detalle=f"{item['texto']}\nRescatado por {quien} en la reconsideracion {e['nombre']}: {motivo[:300]}",
                     estado="propuesta", depende="ia", importancia=3, urgencia=2, dificultad=2, coste=1,
                     etiquetas=["cat:propuesta", ET_ORIGEN, f"tarea_origen:{e['origen']}"])
        tid = t["id"]
    r["reabiertas"].append(tid)
    if clave in r["espera_freno"]:
        r["espera_freno"].remove(clave)
    return True


def aplicar(e: dict, aprobar: list[str], rechazar: list[str], motivo: str, quien: str) -> None:
    """Aplica las filas decididas; el expediente queda resuelto o en espera del freno."""
    for c in rechazar:
        _confirmar(e, c, motivo, quien)
    for c in aprobar:
        _reabrir(e, c, motivo, quien)
    pend = e["reconsiderar"]["espera_freno"]
    e.update(fase=FASE_FRENO if pend else "resuelto", quien=quien,
             motivo=(f"{len(pend)} aprobada(s) esperan hueco bajo el freno F0" if pend else f"aplicado por {quien}"))


def soltar() -> dict:
    """Reabre lo aprobado que esperaba al freno, mientras haya hueco."""
    from nucleo import tribunal
    sueltas = []
    with tribunal._editar() as exps:
        for e in sorted(exps.values(), key=lambda x: x["creado"]):
            if e["fase"] != FASE_FRENO or not e.get("reconsiderar"):
                continue
            for c in list(e["reconsiderar"]["espera_freno"]):
                if not _reabrir(e, c, "aprobada antes; esperaba hueco bajo el freno F0", e.get("quien") or "tribunal"):
                    break
                sueltas.append(c)
            if not e["reconsiderar"]["espera_freno"]:
                e.update(fase="resuelto", motivo="aplicado (tras esperar al freno)")
    return {"sueltas": sueltas}


def _cli(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = argv[0] if argv else "lotes"
    if cmd == "lotes":
        for l in lotes():
            print(f"{l['nombre']}: {len(l['items'])} ({l['clase']})")
    elif cmd == "encolar":
        m = int(argv[argv.index("--max") + 1]) if "--max" in argv else MAX_VIVOS
        print(json.dumps(encolar(m), ensure_ascii=False))
    elif cmd == "soltar":
        print(json.dumps(soltar(), ensure_ascii=False))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(_cli(sys.argv[1:]))
