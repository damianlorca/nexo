# -*- coding: utf-8 -*-
"""T837: quien hara cada tarea, y que ninguna se quede esperando para siempre con depende=ia.

Diagnostico (12/10): trabajo.candidatas() solo coge depende=ia de categoria investigacion/redaccion/resumen y el
implementador solo las que tienen tests dados. ~108 tareas pendientes depende=ia eran de categorias que NINGUN turno
ejecuta (propuesta, codigo, arquitectura, integracion...): esperaban para siempre y "depende=ia" enganaba.

- destino(t): {"quien", "por_que"} con quien en turno | implementador | revision | claude | damian | externo |
  nadie | cerrada. Lo usa la ficha de la web ("quien la hara").
- enrutar(id): al aprobar una propuesta (nucleo.revision) y en la migracion: una tarea depende=ia sin tests dados de
  una categoria que ningun turno ejecuta pasa a depende=claude con su triaje (las piezas con tests dados siguen
  para el implementador). Nunca cambia el estado ni cierra nada.
- migrar(aplicar): enruta las actuales y deja un informe con el recuento por destino en memoria/enrutado/.
- avisar_sin_turno(): aviso en el Centro (una vez al dia) si hay tareas vivas que llevan > 7 dias sin que ningun
  turno pueda cogerlas. Lo llama el planificador.

CLI: .venv\\Scripts\\python.exe -m nucleo.enrutado destino Txxx | migrar [--aplicar] | sin_turno
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timedelta

from nucleo import tareas as T
from nucleo.config import RAIZ

CARPETA = RAIZ / "memoria" / "enrutado"
DELEGABLES = ("investigacion", "redaccion", "resumen")   # = trabajo.DELEGABLES (lo que hacen los turnos)
TESTS_DADOS = "tests:dados"
TRIAJE_OPUS = ("arquitectura",)
DIAS_SIN_TURNO = 7


def _cat(t: dict) -> str:
    return next((e[4:] for e in t.get("etiquetas") or [] if e.startswith("cat:")), "")


def _sin_turno(t: dict) -> bool:
    """depende=ia, pendiente, sin tests dados y de una categoria que ningun turno ejecuta."""
    return (t.get("depende") == "ia" and t.get("estado") in ("pendiente", "en_curso")
            and TESTS_DADOS not in (t.get("etiquetas") or []) and _cat(t) not in DELEGABLES)


def destino(t: dict, vivas: set[str] | None = None) -> dict:
    est, dep, et = t.get("estado"), t.get("depende"), t.get("etiquetas") or []
    if est in T.CERRADOS:
        return {"quien": "cerrada", "por_que": f"ya esta {est}"}
    if est == "propuesta":
        return {"quien": "revision", "por_que": "propuesta: la decide el tribunal o Damian en el Centro"}
    if est == "aparcada":
        return {"quien": "nadie", "por_que": "aparcada hasta su fecha"}
    if T.esta_bloqueada(t, vivas):
        return {"quien": "nadie", "por_que": f"bloqueada por {t.get('bloqueada_por')} (sigue viva)"}
    if dep == "damian":
        return {"quien": "damian", "por_que": "depende de Damian"}
    if dep == "externo":
        return {"quien": "externo", "por_que": "espera algo externo"}
    if dep == "claude" or "necesita:claude" in et:
        return {"quien": "claude", "por_que": "la hace Claude en una sesion de Code"}
    if TESTS_DADOS in et:
        from nucleo import piloto_serie
        motivo = piloto_serie.apta(t)
        if motivo is None:
            return {"quien": "implementador", "por_que": "pieza con tests dados: la programa el implementador (una por hora)"}
        return {"quien": "nadie", "por_que": f"tests dados, pero el implementador no la coge: {motivo}"}
    cat = _cat(t)
    if cat in DELEGABLES:
        if any(e.startswith("borrador:") for e in et):
            return {"quien": "revision", "por_que": "ya tiene borrador: espera su revision"}
        if est not in ("pendiente", "en_curso"):
            return {"quien": "nadie", "por_que": f"estado {est}"}
        return {"quien": "turno", "por_que": f"{cat}: la trabaja un turno de NEXO (borrador + revisor)"}
    return {"quien": "nadie", "por_que": f"categoria '{cat or 'sin categoria'}' con depende=ia: ningun turno la ejecuta "
                                         "(hay que partirla en piezas con tests dados o pasarla a Claude)"}


def enrutar(tid: str, motivo: str = "al aprobarla") -> dict | None:
    """Si la tarea esta atascada (ver _sin_turno), la pasa a Claude con su triaje. Devuelve los cambios o None."""
    t = T.buscar(tid)
    if not t or t["id"] != tid or not _sin_turno(t):
        return None
    if _cat(t) == "personal":       # lo personal es de Damian, nunca de Claude
        T.actualizar(tid, depende="damian")
        T.anotar(tid, f"T837 enrutado ({motivo}): tarea personal con depende=ia; ningun turno la hace: pasa a Damian.")
        return {"tarea": tid, "depende": "damian", "triaje": ""}
    et = list(t.get("etiquetas") or [])
    if not any(e.startswith("triaje:") for e in et):
        et.append("triaje:opus" if _cat(t) in TRIAJE_OPUS else "triaje:sonnet")
    T.actualizar(tid, depende="claude", etiquetas=et)
    T.anotar(tid, f"T837 enrutado ({motivo}): categoria '{_cat(t) or '-'}' sin tests dados; ningun turno la ejecuta, "
                  "asi que pasa a Claude (depende=claude). Si se parte en piezas con tests dados, va al implementador.")
    return {"tarea": tid, "depende": "claude", "triaje": next(e for e in et if e.startswith("triaje:"))}


def recuento(tareas: list[dict] | None = None) -> Counter:
    tareas = T.cargar()["tareas"] if tareas is None else tareas
    vivas = {x["id"] for x in tareas if x.get("estado") in T.VIVOS}
    return Counter(destino(t, vivas)["quien"] for t in tareas if t.get("estado") in T.VIVOS)


def migrar(aplicar: bool = False, ahora: datetime | None = None) -> dict:
    ahora = ahora or datetime.now()
    antes = recuento()
    atascadas = [t for t in T.cargar()["tareas"] if _sin_turno(t)]
    por_cat = Counter(_cat(t) or "-" for t in atascadas)
    hechas = [enrutar(t["id"], "migracion del 13/10") for t in atascadas] if aplicar else []
    despues = recuento() if aplicar else None
    md = [f"# Enrutado de tareas atascadas (T837) - {'APLICADO' if aplicar else 'SIMULACION'} {ahora:%d/%m/%Y %H:%M}", "",
          f"{len(atascadas)} tareas depende=ia que ningun turno ejecuta, por categoria: "
          + ", ".join(f"{c} {n}" for c, n in por_cat.most_common()), "",
          "## Tareas vivas por destino (antes)", ""] + [f"- {q}: {n}" for q, n in antes.most_common()]
    if despues is not None:
        md += ["", "## Despues", ""] + [f"- {q}: {n}" for q, n in despues.most_common()]
    md += ["", "## Tareas", ""] + [f"- {t['id']} ({_cat(t) or '-'}) {t['titulo'][:90]}" for t in atascadas]
    CARPETA.mkdir(parents=True, exist_ok=True)
    ruta = CARPETA / f"migracion_{ahora:%Y%m%d_%H%M}.md"
    ruta.write_text("\n".join(md) + "\n", encoding="utf-8")
    return {"atascadas": len(atascadas), "por_categoria": dict(por_cat), "antes": dict(antes),
            "despues": dict(despues or {}), "enrutadas": len([h for h in hechas if h]), "informe": str(ruta)}


def sin_turno(ahora: datetime | None = None, dias: int = DIAS_SIN_TURNO) -> list[dict]:
    """Vivas con destino 'nadie' cuya ultima actualizacion tiene mas de `dias` dias."""
    ahora = ahora or datetime.now()
    limite = ahora - timedelta(days=dias)
    tareas = T.cargar()["tareas"]
    vivas = {x["id"] for x in tareas if x.get("estado") in T.VIVOS}
    out = []
    for t in tareas:
        if t.get("estado") not in ("pendiente", "en_curso", "esperando", "bloqueada"):
            continue
        d = destino(t, vivas)
        if d["quien"] != "nadie":
            continue
        try:
            cuando = datetime.strptime((t.get("actualizada") or t.get("creada") or "")[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if cuando < limite:
            out.append({"id": t["id"], "titulo": t["titulo"], "por_que": d["por_que"], "desde": cuando.strftime("%Y-%m-%d")})
    return out


def avisar_sin_turno(ahora: datetime | None = None) -> int:
    """Un aviso al dia en el Centro con cuantas llevan > 7 dias sin turno que las pueda coger. Nunca rompe."""
    ahora = ahora or datetime.now()
    try:
        lista = sin_turno(ahora)
        if lista:
            from nucleo import avisos
            clave = f"sin_turno:{ahora:%Y-%m-%d}"
            if avisos.ya_emitido(clave):    # T890: emitir() solo frena 1 h (salian 19 al dia); esto, un dia entero
                return len(lista)
            ej = "; ".join(f"{x['id']} ({x['por_que'][:60]})" for x in lista[:3])
            avisos.emitir("sin_turno", f"{len(lista)} tarea(s) llevan más de {DIAS_SIN_TURNO} días sin que nadie pueda cogerlas",
                          ej, ruta="/tareas", clave=clave, urgencia="normal")
        return len(lista)
    except Exception:
        return 0


def _cli(argv: list[str]) -> int:
    from nucleo import ayuda
    ayuda.atender(__doc__, argv)
    if not argv:
        print(__doc__)
        return 0
    if argv[0] == "destino" and len(argv) > 1:
        t = T.buscar(argv[1])
        print(destino(t) if t else "no existe")
        return 0
    if argv[0] == "migrar":
        print(migrar(aplicar="--aplicar" in argv))
        return 0
    if argv[0] == "sin_turno":
        for x in sin_turno():
            print(f"{x['id']} desde {x['desde']}: {x['por_que']} | {x['titulo'][:70]}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # noqa: E702  (incidente 05/10: --help antes de nada)
    sys.exit(_cli(sys.argv[1:]))
