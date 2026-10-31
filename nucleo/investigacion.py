# -*- coding: utf-8 -*-
"""T674 (Damian 03/10): una investigacion no se da por acabada solo con decir si algo esta bien o mal.

  INVESTIGACION = tarea con cat:investigacion que NO es un lote de turno (turno:lote: vigia, revisar codigo o
  archivos; su salida son hallazgos y propuestas, no adoptar/descartar una herramienta).

  1. RESULTADO obligatorio para cerrarla: ADOPTAR / ADAPTAR / DESCARTAR + motivo (`fijar_resultado`, `decidir`).
     La guardia esta en tareas.actualizar (por ahi pasan completar, la web, el chat, el bot y evidencias.cerrar):
     a 'hecha' solo con DESCARTAR (bien hecha y concluye "no usarlo") o con ADOPTAR/ADAPTAR y la hija de
     integracion VERIFICADA; a 'descartada' (ya no interesa investigarlo) solo con DESCARTAR. Si no:
     tareas.ResultadoPendiente.
  2. BORRADOR MALO != HERRAMIENTA DESCARTADA: el veredicto DESCARTADO o REHACER de un borrador no cierra la
     investigacion; vuelve a pendiente (`borrador_malo`). Tras LIMITE_REHACER seguidos pasa a 'esperando' con
     depende=claude y una nota, para que no se reintente cada noche.
  3. ADOPTAR/ADAPTAR crea la hija "Integrar: ..." (cat:integracion, integra:Txxx) en pendiente, con la importancia
     de la investigacion, el enlace al informe y el checklist; la investigacion queda 'esperando' con
     integracion:Tyyy. ADOPTAR NO da permiso: instalar o configurar algo externo pasa por la cola de
     aprobaciones (N04) hasta que exista F2. Al verificarse la hija (`hija_verificada`, desde tareas.verificar)
     la investigacion se cierra sola, hecha y testeada; si la hija se descarta, vuelve a pendiente.
  4. AUDITORIA (`auditar`): todas las investigaciones cerradas con su estado real y una propuesta (reabrir /
     crear integracion / descarte valido / revisar a mano). Solo informe: no cambia nada.

CLI:
  .venv\\Scripts\\python.exe -m nucleo.investigacion decidir T203 ADOPTAR|ADAPTAR|DESCARTAR "motivo" [--informe ruta]
  .venv\\Scripts\\python.exe -m nucleo.investigacion auditar
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from nucleo import tareas as T
from nucleo.candado import bloqueo

RAIZ = Path(__file__).resolve().parent.parent
INFORMES = RAIZ / "memoria" / "investigacion"

DECISIONES = ("ADOPTAR", "ADAPTAR", "DESCARTAR")
MIN_MOTIVO = 15
LIMITE_REHACER = 2
ET_INV = "cat:investigacion"
ET_LOTE = "turno:lote"
ET_HIJA = "cat:integracion"
PRE_INTEGRA = "integra:"          # en la hija: de que investigacion sale
PRE_INTEGRACION = "integracion:"  # en la investigacion: su hija
F0 = ("T203", "T083", "T168", "T289", "T178", "T179", "T121", "T122", "T085", "T090", "T123", "T108", "T109",
      "T167", "T180", "T127")
CHECKLIST = (
    "[ ] 1. Instalar o configurar. Si es algo EXTERNO (descarga, cuenta, servicio, dependencia nueva) pasa por la "
    "cola de aprobaciones (N04, nucleo/aprobaciones.py): ADOPTAR no da permiso implicito.",
    "[ ] 2. Documentar en el archivo que corresponda (CLAUDE.md, catalogo memoria/catalogo.json, documentacion/...).",
    "[ ] 3. Tests (los de la suite: .venv\\Scripts\\python.exe -m pytest tests interfaz\\tests -q).",
    "[ ] 4. Verificar con evidencia (.venv\\Scripts\\python.exe -m nucleo.tareas testeada Tyyy \"que se probo y "
    "que salio\"): al verificarse, la investigacion se cierra sola.",
)


def _et(t: dict, prefijo: str) -> str:
    return next((e[len(prefijo):] for e in t.get("etiquetas") or [] if e.startswith(prefijo)), "")


def es_investigacion(t: dict | None) -> bool:
    et = (t or {}).get("etiquetas") or []
    return ET_INV in et and ET_LOTE not in et


def _hija(t: dict, todas: list[dict]) -> dict | None:
    hid = _et(t, PRE_INTEGRACION)
    return next((x for x in todas if x["id"] == hid), None) if hid else None


# ------------------------------------------------------------------ 1) la guardia (la llama tareas.actualizar)
def motivo_bloqueo(t: dict, nuevo_estado: str, todas: list[dict]) -> str:
    """'' si `t` puede pasar a `nuevo_estado` (cerrado); si no, por que no."""
    if not es_investigacion(t) or nuevo_estado not in T.CERRADOS or t.get("estado") in T.CERRADOS:
        return ""
    r = t.get("resultado") or {}
    dec = r.get("decision")
    como = (f"fija el resultado: .venv\\Scripts\\python.exe -m nucleo.investigacion decidir {t['id']} "
            "ADOPTAR|ADAPTAR|DESCARTAR \"motivo\"")
    if dec not in DECISIONES:
        return f"{t['id']} es una investigacion: solo se cierra con RESULTADO ADOPTAR / ADAPTAR / DESCARTAR y motivo ({como})"
    if nuevo_estado == "descartada" and dec != "DESCARTAR":
        return f"{t['id']} tiene resultado {dec}: no se descarta; si ya no interesa, cambia el resultado a DESCARTAR ({como})"
    if nuevo_estado == "hecha" and dec in ("ADOPTAR", "ADAPTAR"):
        h = _hija(t, todas)
        if h is None:
            return f"{t['id']} tiene resultado {dec} pero no tiene tarea de integracion ({como})"
        if not (h.get("estado") == "hecha" and h.get("testeado")):
            return (f"{t['id']} ({dec}) espera su integracion {h['id']}: se cierra sola cuando {h['id']} "
                    "este hecha y verificada con evidencia")
    return ""


# ------------------------------------------------------------------ resultado y decision
def _validar(decision: str, motivo: str) -> tuple[str, str]:
    d = (decision or "").strip().upper()
    if d not in DECISIONES:
        raise ValueError(f"resultado desconocido {decision!r}: {', '.join(DECISIONES)}")
    m = " ".join((motivo or "").split())
    if len(m) < MIN_MOTIVO:
        raise ValueError(f"el resultado necesita un motivo de verdad (minimo {MIN_MOTIVO} caracteres)")
    return d, m


def fijar_resultado(tarea_id: str, decision: str, motivo: str, quien: str = "claude") -> dict:
    d, m = _validar(decision, motivo)
    with bloqueo(T.CANDADO):
        datos = T.cargar()
        t = next((x for x in datos["tareas"] if x["id"].lower() == tarea_id.strip().lower()), None)
        if t is None:
            raise ValueError(f"la tarea {tarea_id} no existe")
        if not es_investigacion(t):
            raise ValueError(f"{t['id']} no es una investigacion (cat:investigacion sin turno:lote)")
        ahora = T._ahora()
        t["resultado"] = {"decision": d, "motivo": m, "quien": quien, "cuando": ahora}
        t.setdefault("notas", []).append({"cuando": ahora, "texto": f"RESULTADO {d} ({quien}): {m}"})
        t["actualizada"] = ahora
        T.guardar(datos)
        return t


def decidir(tarea_id: str, decision: str, motivo: str, informe: str = "", evidencia: dict | None = None,
            quien: str = "claude") -> dict:
    """Fija el resultado y actua: DESCARTAR cierra la investigacion (hecha); ADOPTAR/ADAPTAR crea la hija de
    integracion y la deja 'esperando'. Devuelve {"investigacion", "hija", "estado_real"}."""
    d, m = _validar(decision, motivo)
    t = T.buscar(tarea_id)
    if t is None or t["id"].lower() != tarea_id.strip().lower():
        raise ValueError(f"la tarea {tarea_id} no existe")
    if t["estado"] in T.CERRADOS:
        raise ValueError(f"{t['id']} ya esta cerrada ({t['estado']}): reabrela antes de decidir")
    if not es_investigacion(t):
        raise ValueError(f"{t['id']} no es una investigacion (cat:investigacion sin turno:lote)")
    vieja = T.buscar(_et(t, PRE_INTEGRACION)) if _et(t, PRE_INTEGRACION) else None
    if vieja is not None and vieja["estado"] in T.VIVOS:
        raise ValueError(f"{t['id']} ya tiene la integracion {vieja['id']} en marcha")
    fijar_resultado(t["id"], d, m, quien)
    informe = informe or _et(t, "informe:")
    if d == "DESCARTAR":
        nota = f"Investigacion cerrada: RESULTADO DESCARTAR. {m}"
        if evidencia:
            from nucleo import evidencias
            evidencias.cerrar(t["id"], nota, evidencia=evidencia)
        else:
            T.completar(t["id"], nota, despues="nada: investigacion descartada, no se usa",   # T1010
                        cierre=T.cierre_ok(evidencia=nota))
        final = T.buscar(t["id"])
        return {"investigacion": final, "hija": None, "estado_real": T.estado_real(final)}
    titulo = re.sub(r"^(?i:investiga\w*|evaluar|estudiar)\s*[:\-]?\s*", "", t["titulo"]).strip() or t["titulo"]
    hija = T.anadir(
        f"Integrar: {titulo[:110]} (de {t['id']}, {d})",
        detalle=(f"Integracion de la investigacion {t['id']} con RESULTADO {d}: {m}\n"
                 f"Informe: {informe or '(ver notas de ' + t['id'] + ')'}\n\nChecklist:\n" + "\n".join(CHECKLIST)),
        estado="pendiente", depende="ia", importancia=t.get("importancia", 3), urgencia=t.get("urgencia", 3),
        dificultad=3, coste=2,
        etiquetas=[ET_HIJA, "prov:claude", f"{PRE_INTEGRA}{t['id']}"] + ([f"informe:{informe}"] if informe else []))
    et = [e for e in t.get("etiquetas") or [] if not e.startswith(PRE_INTEGRACION)] + [f"{PRE_INTEGRACION}{hija['id']}"]
    T.actualizar(t["id"], estado="esperando", etiquetas=et)
    T.anotar(t["id"], f"RESULTADO {d}: espera la integracion {hija['id']}; se cierra sola cuando se verifique.")
    if evidencia:
        from nucleo import evidencias
        evidencias.registrar(t["id"], evidencia.get("detalle", m), tipo=evidencia.get("tipo", "revision"),
                             fuente=evidencia.get("fuente", "investigacion.decidir"))
    final = T.buscar(t["id"])
    return {"investigacion": final, "hija": T.buscar(hija["id"]), "estado_real": T.estado_real(final)}


# ------------------------------------------------------------------ 2) borrador malo (lo llama revision.veredicto)
def borrador_malo(tarea_id: str, decision: str, motivo: str) -> dict | None:
    """El borrador no valia (DESCARTADO/REHACER): la investigacion sigue viva. Cuenta los seguidos; al llegar a
    LIMITE_REHACER pasa a 'esperando' (depende=claude) en vez de volver otra vez a pendiente."""
    with bloqueo(T.CANDADO):
        datos = T.cargar()
        t = next((x for x in datos["tareas"] if x["id"] == tarea_id), None)
        if t is None:
            return None
        n = int(t.get("borradores_malos") or 0) + 1
        t["borradores_malos"] = n
        ahora = T._ahora()
        if n >= LIMITE_REHACER:
            t["estado"], t["depende"] = "esperando", "claude"
            texto = (f"{n} borradores seguidos sin valer ({decision}: {motivo[:200]}). No vuelve a la cola de NEXO: "
                     "espera a Claude (cambiar el encargo, partirlo o decidir el RESULTADO).")
        else:
            t["estado"] = "pendiente"
            texto = f"Borrador {decision} ({n}/{LIMITE_REHACER}): la investigacion sigue viva y vuelve a la cola."
        t["cerrada"] = None
        t.setdefault("notas", []).append({"cuando": ahora, "texto": texto})
        t["actualizada"] = ahora
        T.guardar(datos)
        return t


def borrador_bueno(tarea_id: str) -> None:
    """Un borrador aprobado corta la racha de borradores malos."""
    with bloqueo(T.CANDADO):
        datos = T.cargar()
        t = next((x for x in datos["tareas"] if x["id"] == tarea_id), None)
        if t is not None and t.pop("borradores_malos", None) is not None:
            T.guardar(datos)


# ------------------------------------------------------------------ 3) la hija (ganchos de tareas.py)
def hija_verificada(hija: dict) -> dict | None:
    """La llama tareas.verificar: si `hija` es una integracion hecha y testeada, cierra su investigacion."""
    origen = _et(hija, PRE_INTEGRA)
    if not origen or not (hija.get("estado") == "hecha" and hija.get("testeado")):
        return None
    t = T.buscar(origen)
    if t is None or t["id"] != origen or t["estado"] in T.CERRADOS or _et(t, PRE_INTEGRACION) != hija["id"]:
        return None
    T.completar(origen, f"Integracion {hija['id']} verificada: la investigacion queda cerrada "
                        f"(RESULTADO {(t.get('resultado') or {}).get('decision')}).",
                despues=hija["id"],                                                   # T1010: la siguiente ES la integracion
                cierre=T.cierre_ok(evidencia=f"Integracion {hija['id']} hecha y verificada"))
    ultima = next((n["texto"] for n in reversed(hija.get("notas") or []) if n["texto"].startswith("[verificado]")), "")
    return T.verificar(origen, f"Integracion {hija['id']} hecha y verificada con evidencia: "
                               f"{ultima[len('[verificado] '):] or 'ver ' + hija['id']}")


def hija_descartada(hija: dict) -> dict | None:
    """La llama tareas.actualizar: si se descarta la integracion, la investigacion vuelve a pendiente para decidir."""
    origen = _et(hija, PRE_INTEGRA)
    t = T.buscar(origen) if origen else None
    if t is None or t["id"] != origen or t["estado"] in T.CERRADOS or _et(t, PRE_INTEGRACION) != hija["id"]:
        return None
    with bloqueo(T.CANDADO):
        datos = T.cargar()
        x = next(y for y in datos["tareas"] if y["id"] == origen)
        r = x.pop("resultado", None) or {}
        x["etiquetas"] = [e for e in x.get("etiquetas") or [] if not e.startswith(PRE_INTEGRACION)]
        x["estado"] = "pendiente"
        ahora = T._ahora()
        x.setdefault("notas", []).append({"cuando": ahora, "texto": (
            f"La integracion {hija['id']} se descarto: el RESULTADO {r.get('decision')} ({r.get('motivo', '')[:200]}) "
            "queda sin efecto y la investigacion vuelve a pendiente para decidir de nuevo.")})
        x["actualizada"] = ahora
        T.guardar(datos)
        return x


# ------------------------------------------------------------------ 4) auditoria (solo informe)
def _como_cerrada(t: dict) -> str:
    et = t.get("etiquetas") or []
    for e in ("revisado:aprobado", "revisado:descartado", "revisado:superado"):
        if e in et:
            return "veredicto " + e.split(":")[1].upper()
    return "a mano o por otra via"


def auditar(ahora: datetime | None = None, tareas: list[dict] | None = None, escribir: bool = True) -> dict:
    ahora = ahora or datetime.now()
    tareas = T.cargar()["tareas"] if tareas is None else tareas
    cerradas = [t for t in tareas if es_investigacion(t) and t["estado"] in T.CERRADOS]
    lotes = sum(1 for t in tareas if ET_INV in (t.get("etiquetas") or []) and ET_LOTE in t["etiquetas"]
                and t["estado"] in T.CERRADOS)
    filas = []
    for t in cerradas:
        mias = [p for p in tareas if "cat:propuesta" in (p.get("etiquetas") or []) and _et(p, "tarea_origen:") == t["id"]]
        aprob = [p for p in mias if "propuesta:aprobada" in p["etiquetas"]]
        hechas = [p for p in aprob if p["estado"] == "hecha"]
        como = _como_cerrada(t)
        if (t.get("resultado") or {}).get("decision"):
            prop, por = "descarte valido", f"ya tiene RESULTADO {t['resultado']['decision']}"
        elif como == "veredicto DESCARTADO":
            prop, por = "reabrir", "se cerro por un borrador malo: el contenido nunca se decidio"
        elif como == "veredicto SUPERADO":
            prop, por = "descarte valido", "el trabajo se hizo por otra via (SUPERADO); falta fijar RESULTADO"
        elif aprob and len(hechas) < len(aprob):
            prop = "crear integracion"
            por = f"aprobada con {len(aprob)} propuesta(s) y solo {len(hechas)} hecha(s); falta RESULTADO e integracion"
        elif aprob:
            prop, por = "descarte valido", f"aprobada y sus {len(aprob)} propuesta(s) estan hechas; falta fijar RESULTADO"
        elif como == "veredicto APROBADO":
            prop, por = "revisar a mano", "aprobada sin ninguna propuesta aprobada: falta decidir ADOPTAR/ADAPTAR/DESCARTAR"
        else:
            prop, por = "revisar a mano", f"cerrada {t['estado']} sin revision ni resultado"
        filas.append({"id": t["id"], "titulo": t["titulo"][:100], "estado_real": T.estado_real(t), "como": como,
                      "cerrada": t.get("cerrada") or "", "aprobadas": [p["id"] for p in aprob],
                      "aprobadas_hechas": [p["id"] for p in hechas], "propuesta": prop, "por_que": por,
                      "f0": t["id"] in F0})
    filas.sort(key=lambda f: (not f["f0"], f["propuesta"], T.clave_id(f["id"])))
    res = {"cuando": f"{ahora:%Y-%m-%d %H:%M}", "cerradas": len(filas), "lotes_excluidos": lotes, "filas": filas}
    if escribir:
        from collections import Counter
        cuenta = Counter(f["propuesta"] for f in filas)
        md = [f"# Auditoria de investigaciones cerradas (T674) - {ahora:%d/%m/%Y %H:%M}", "",
              f"Investigaciones cerradas: **{len(filas)}** (se excluyen {lotes} lotes de turno: vigia y revisiones "
              "de codigo/archivos). SOLO INFORME: no se ha reabierto ni cambiado nada.", "",
              "| Propuesta | Cuantas |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(cuenta.items())] + [""]
        for titulo, sel in (("Las 16 de F0", [f for f in filas if f["f0"]]), ("El resto", [f for f in filas if not f["f0"]])):
            md += [f"## {titulo} ({len(sel)})", "", "| Tarea | Estado real | Como se cerro | Propuestas aprobadas (hechas) | "
                   "Propuesta | Por que |", "|---|---|---|---|---|---|"]
            md += [f"| {f['id']} {f['titulo'][:60]} | {f['estado_real']} | {f['como']} | "
                   f"{', '.join(f['aprobadas']) or '-'} ({len(f['aprobadas_hechas'])}) | **{f['propuesta']}** | {f['por_que']} |"
                   for f in sel]
            md.append("")
        INFORMES.mkdir(parents=True, exist_ok=True)
        base = INFORMES / f"auditoria_{ahora:%Y%m%d_%H%M}"
        base.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
        base.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        res["informe"] = str(base.with_suffix(".md"))
    return res


# ------------------------------------------------------------------ CLI
def _cli(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[0] == "decidir":
        informe = argv[argv.index("--informe") + 1] if "--informe" in argv else ""
        r = decidir(argv[1], argv[2], argv[3], informe=informe)
        print(f"{r['investigacion']['id']}: {r['estado_real']}" + (f"; integracion {r['hija']['id']}" if r["hija"] else ""))
        return 0
    if argv[:1] == ["auditar"]:
        r = auditar()
        print(f"{r['cerradas']} investigaciones cerradas auditadas. Informe: {r['informe']}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    sys.exit(_cli(sys.argv[1:]))
