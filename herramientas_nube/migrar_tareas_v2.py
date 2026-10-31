"""Migra la cola de tareas al formato v2 (T1010 paso 2, Damian 17/10).

    .venv\\Scripts\\python.exe herramientas_nube\\migrar_tareas_v2.py --simular
    .venv\\Scripts\\python.exe herramientas_nube\\migrar_tareas_v2.py --aplicar [--aunque-haya-turno]

Que hace
--------
  1. (--aplicar) copia previa de memoria/tareas.json y tareas.md en _archivo/AAAAMMDD/migracion_tareas_v2/.
  2. Abre TODAS las tareas con la API (nucleo.tareas.cargar) y las guarda en el formato nuevo:
       memoria/tareas.json            solo las NO cerradas, registros compactos v2
       memoria/tareas_historial.jsonl las cerradas (hecha/descartada), con resumen de 1 linea
       memoria/tareas_detalle/<id>.json notas antiguas (solo quedan las 5 ultimas), conversaciones,
                                      descarte y fallos_turno
  3. Mapeo: depende -> quien, cat:X -> tipo, importancia+urgencia -> prioridad, dificultad -> esfuerzo,
     limite -> fecha_limite, bloqueada_por -> depende_de (si es solo ids). El `coste` viejo (escala 1-5) NO pasa
     a coste_eur, que queda vacio. tema/epica/riesgo/tests/suyo siguen siendo etiquetas. Las etiquetas de
     rastreo (prov, tarea_origen, de_borrador, borrador, revisado, auditoria...) pasan a `origen`.
  4. Comprueba que no se pierde nada (titulo, estado, detalle, etiquetas, notas, conversaciones, descarte...). Si algo
     no cuadra, restaura la copia y aparta lo creado a _archivo/ (no se borra nada).
  5. Informe de cuanto pesa antes y despues.

--simular hace lo mismo en una carpeta temporal y no toca nada real. Hay que lanzar --aplicar con la web y los
turnos en la version nueva del codigo y SIN turno en marcha (un proceso con el codigo viejo en memoria no sabe
leer el formato nuevo).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo import tarea_v2 as V          # noqa: E402
from nucleo import tareas as T            # noqa: E402
from nucleo import tareas_almacen as AL   # noqa: E402
from nucleo.candado import bloqueo        # noqa: E402

EXTRAS_IGUALES = ("resultado", "resumen_humano", "aparcada_hasta", "estado_antes_de_aparcar", "borradores_malos")
CAMPOS_IGUALES = ("titulo", "estado", "detalle", "depende", "limite", "bloqueada_por", "pregunta_id", "testeado",
                  "creada", "actualizada", "cerrada", "dificultad")


def kb(n: int) -> str:
    return f"{n / 1024:,.0f} KB".replace(",", ".")


def _colapsar(t: dict) -> None:
    """La migracion es la unica que colapsa importancia+urgencia en una prioridad y descarta el coste 1-5 viejo."""
    p = V.prioridad_de(t.get("importancia"), t.get("urgencia"))
    t["importancia"] = t["urgencia"] = p
    t["coste"] = T.DEFECTOS["coste"]


def comparar(antes: list[dict], despues: list[dict]) -> list[str]:
    """Lo que no cuadra entre las tareas de antes (registro crudo del v1) y las de despues (cargar(detalle=True))."""
    fallos: list[str] = []
    a = {r["id"]: r for r in antes}
    d = {t["id"]: t for t in despues}
    if set(a) != set(d):
        fallos.append(f"ids distintos: faltan {sorted(set(a) - set(d))[:5]}, sobran {sorted(set(d) - set(a))[:5]}")
    for tid, r in a.items():
        t = d.get(tid)
        if t is None:
            continue
        for c in CAMPOS_IGUALES:
            if r.get(c) != t.get(c):
                fallos.append(f"{tid}.{c}: {str(r.get(c))[:40]!r} -> {str(t.get(c))[:40]!r}")
        if sorted(r.get("etiquetas") or []) != sorted(t.get("etiquetas") or []):
            fallos.append(f"{tid}.etiquetas: {sorted(r.get('etiquetas') or [])[:4]} -> {sorted(t.get('etiquetas') or [])[:4]}")
        notas = (t.get("notas_antiguas") or []) + (t.get("notas") or [])
        if (r.get("notas") or []) != notas:
            fallos.append(f"{tid}.notas: {len(r.get('notas') or [])} antes, {len(notas)} despues")
        if len(t.get("notas") or []) > V.MAX_NOTAS:
            fallos.append(f"{tid}: mas de {V.MAX_NOTAS} notas vigentes")
        for c in V.DETALLE_CAMPOS:
            if c != "notas_antiguas" and r.get(c) != t.get(c):
                fallos.append(f"{tid}.{c} distinto")
        for c in EXTRAS_IGUALES:
            if r.get(c) != t.get(c):
                fallos.append(f"{tid}.{c} distinto")
    return fallos


def migrar(carpeta_memoria: Path, copia: Path | None = None) -> dict:
    """Migra el almacen que apunta nucleo.tareas.ALMACEN (ya redirigido a `carpeta_memoria`). Devuelve el informe."""
    almacen = T.ALMACEN
    antes = json.loads(almacen.read_text(encoding="utf-8"))
    if int(antes.get("version", 1) or 1) >= 2:
        return {"estado": "ya_migrado"}
    crudas = antes["tareas"]
    tam_antes = AL.tamanos(almacen)
    vivas_antes = [t for t in T.cargar()["tareas"] if t["estado"] in T.VIVOS]
    orden_antes = {t["id"]: T.puntuacion(t) for t in vivas_antes}

    if copia is not None:
        copia.mkdir(parents=True, exist_ok=True)
        shutil.copy2(almacen, copia / "tareas.json")
        if T.VISTA.is_file():
            shutil.copy2(T.VISTA, copia / "tareas.md")

    datos = T.cargar()
    for t in datos["tareas"]:
        _colapsar(t)
    datos["version"] = 2
    T.guardar(datos)

    despues = T.cargar(detalle=True)
    fallos = comparar(crudas, despues["tareas"])
    tam_despues = AL.tamanos(almacen)

    cambios = []
    for t in despues["tareas"]:
        if t["estado"] in T.VIVOS and t["id"] in orden_antes and abs(T.puntuacion(t) - orden_antes[t["id"]]) > 1.0:
            cambios.append((t["id"], orden_antes[t["id"]], T.puntuacion(t)))
    _, hist = AL.leer_historial(almacen)
    informe = {
        "estado": "ok" if not fallos else "fallos",
        "fallos": fallos,
        "tareas": len(crudas),
        "vivas": len(json.loads(almacen.read_text(encoding="utf-8"))["tareas"]),
        "cerradas": len(hist),
        "con_detalle": tam_despues["tareas_detalle_archivos"],
        "antes": tam_antes, "despues": tam_despues,
        "puntuacion_cambia_mas_de_1": len(cambios), "ejemplos_puntuacion": sorted(cambios, key=lambda c: -abs(c[1] - c[2]))[:5],
        "total_antes": tam_antes["tareas.json"],
        "total_despues": tam_despues["tareas.json"] + tam_despues["tareas_historial.jsonl"] + tam_despues["tareas_detalle"],
    }
    return informe


def texto_informe(i: dict, titulo: str) -> str:
    if i.get("estado") == "ya_migrado":
        return f"{titulo}: el almacen ya esta en formato v2, no hay nada que migrar."
    a, d = i["antes"], i["despues"]
    lineas = [
        f"{titulo}",
        f"  tareas: {i['tareas']} ({i['vivas']} vivas en tareas.json, {i['cerradas']} cerradas en el historial)",
        f"  tareas.json (lo que se lee a cada paso): {kb(a['tareas.json'])} -> {kb(d['tareas.json'])}",
        f"  tareas_historial.jsonl: {kb(d['tareas_historial.jsonl'])}",
        f"  tareas_detalle/: {kb(d['tareas_detalle'])} en {d['tareas_detalle_archivos']} archivos",
        f"  total en disco: {kb(i['total_antes'])} -> {kb(i['total_despues'])}",
        f"  vivas cuya puntuacion cambia mas de 1 punto por colapsar importancia+urgencia en prioridad: "
        f"{i['puntuacion_cambia_mas_de_1']}",
    ]
    for tid, p0, p1 in i["ejemplos_puntuacion"]:
        lineas.append(f"      {tid}: {p0} -> {p1}")
    lineas.append(f"  comprobacion: {'TODO CUADRA' if not i['fallos'] else str(len(i['fallos'])) + ' DIFERENCIAS'}")
    lineas += [f"      {f}" for f in i["fallos"][:15]]
    return "\n".join(lineas)


def simular() -> int:
    origen = T.ALMACEN
    with tempfile.TemporaryDirectory(prefix="migrar_tareas_v2_") as tmp:
        carpeta = Path(tmp)
        shutil.copy2(origen, carpeta / "tareas.json")
        guardados = (T.ALMACEN, T.VISTA, T.VISTA_VAULT, T.CANDADO)
        T.ALMACEN, T.VISTA, T.VISTA_VAULT, T.CANDADO = (carpeta / "tareas.json", carpeta / "tareas.md",
                                                        carpeta / "vault" / "tareas.md", carpeta / ".candado")
        try:
            informe = migrar(carpeta)
        finally:
            T.ALMACEN, T.VISTA, T.VISTA_VAULT, T.CANDADO = guardados
    print(texto_informe(informe, "SIMULACION (no se ha tocado nada real)"))
    return 0 if informe.get("estado") in ("ok", "ya_migrado") else 1


def aplicar(aunque_haya_turno: bool, raiz: Path = RAIZ) -> int:
    en_marcha = raiz / "memoria" / "turno_en_marcha.json"
    if en_marcha.is_file() and not aunque_haya_turno:
        print(f"HAY UN TURNO EN MARCHA ({en_marcha.name}): un proceso con el codigo viejo no sabe leer el formato "
              "nuevo. Espera a que acabe o usa --aunque-haya-turno si sabes lo que haces.")
        return 2
    copia = raiz / "_archivo" / datetime.now().strftime("%Y%m%d") / "migracion_tareas_v2"
    with bloqueo(T.CANDADO):
        informe = migrar(T.ALMACEN.parent, copia)
        if informe.get("estado") == "ya_migrado":
            print(texto_informe(informe, "MIGRACION"))
            return 0
        (copia / "NOTA.md").write_text(
            "Copia previa a la migracion de la cola de tareas al formato v2 (T1010 paso 2).\n"
            "tareas.json y tareas.md tal como estaban. Para volver atras: copiar tareas.json aqui sobre "
            "memoria/tareas.json y apartar memoria/tareas_historial.jsonl y memoria/tareas_detalle/.\n",
            encoding="utf-8")
        if informe["estado"] != "ok":
            apartado = copia / "creado_por_el_intento_fallido"
            apartado.mkdir(parents=True, exist_ok=True)
            shutil.copy2(copia / "tareas.json", T.ALMACEN)
            for nombre in ("tareas_historial.jsonl", "tareas_detalle"):
                p = T.ALMACEN.parent / nombre
                if p.exists():
                    shutil.move(str(p), str(apartado / nombre))
            T.guardar(T.cargar())
            print(texto_informe(informe, "MIGRACION FALLIDA: restaurada la copia, lo creado esta en " + str(apartado)))
            return 1
    texto = texto_informe(informe, "MIGRACION APLICADA")
    (copia / "INFORME.md").write_text(texto + "\n", encoding="utf-8")
    print(texto)
    print(f"  copia previa: {copia}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--simular", action="store_true", help="migra una copia temporal y cuenta lo que pasaria")
    g.add_argument("--aplicar", action="store_true", help="migra de verdad (con copia previa en _archivo/)")
    ap.add_argument("--aunque-haya-turno", action="store_true", help="no se niega si hay un turno en marcha")
    a = ap.parse_args(argv)
    return simular() if a.simular else aplicar(a.aunque_haya_turno)


if __name__ == "__main__":
    raise SystemExit(main())
