# -*- coding: utf-8 -*-
"""T669, fase 2 del piloto del implementador: la serie la lleva NEXO solo (turno "Implementador (piloto fase 2)").

Decision de Damian (04/10): cada tanda del turno hace COMO MUCHO UNA accion sobre la primera tarea de la serie
(`fase2` de memoria/implementador/piloto.json: T347 -> T348 -> T421 -> T422) que no haya terminado:

  por hacer        -> implementa en su worktree y pasa la puerta (nucleo.implementador / nucleo.puerta).
  espera a Claude  -> NO hace nada: el diff esta en la bandeja de Claude (el Centro enciende el indicador) y hasta
                      que dictamine FUSIONAR|RECHAZAR (con su resumen de 3 lineas) no se mueve nada.
  con veredicto    -> vuelve a pasar la puerta: con FUSIONAR crea la tarjeta R2 de Damian (resumen + diff).
  espera a Damian  -> NO hace nada hasta que apruebe, rechace o caduque la tarjeta. Con su OK, la puerta fusiona
                      (solo con el arbol de principal limpio) y la siguiente tanda sigue la serie.

Respeta la PARADA, el interruptor de turnos y el arbol limpio (memoria/ no cuenta, ver puerta.arbol_limpio).

CIERRE AUTOMATICO al terminar la serie: calcula exito y coincidencia de la fase 2. Si alguno queda por debajo del
80 %, aplica por si mismo la regla de respaldo (plan §3.3 bis): aparca el implementador, desactiva el turno, crea
la tarea de reprobarlo cuando T320 detecte modelos gratuitos nuevos o mejores, anota el resultado en T669 y en el
plan (§5.4) y avisa a Damian. Si llega al 80 %, solo avisa y no cambia nada mas.

CLI:  .venv\\Scripts\\python.exe -m nucleo.piloto_serie estado | tanda [--simular] | cerrar_cortada [--aplicar]
      cerrar_cortada: si el turno desaparece o se desactiva con la serie a medias, cierra con las rondas archivadas.
      cerrar_superado "motivo": cierra la fase 2 como superada y deja el implementador en modo permanente.
      cola: tareas que cogeria el implementador permanente.
      devolver Txxx "motivo" [--quitar-cierre]: la tarea vuelve a la cola (sin necesita:claude ni su caso viejo).

MODO PERMANENTE (Damian 11/10, fase 2 superada 4/4): `permanente` en piloto.json. Sin serie: cada tanda hace UNA
accion sobre la cola de tareas con tests dados (etiqueta `tests:dados` y su test en tests_dados/), estado pendiente,
sin `necesita:claude` y con riesgo previsto R0-R2 (nunca R3 ni blindados). Primero repasa la puerta de lo ya
implementado que no espera el OK de Damian; si no, implementa la primera de la cola. La puerta es la de siempre
(R1 veto antes, R2 OK de Damian sobre el diff real). Lo fusionado se cierra con evidencia (commit + suite).
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from nucleo import implementador as I
from nucleo import puerta as P
from nucleo import tareas as T

TURNO_ID = "implpil2"
NOMBRE_TURNO = "Implementador (piloto fase 2)"
UMBRAL = I.UMBRAL_PILOTO
MAX_VACIOS = 12           # veces que una tarea puede quedarse sin informe (error, no autorizada...) antes de darla por fallida
PLAN = I.RAIZ / "documentacion" / "PLAN_REVISION_APROBACION_IMPLEMENTACION.md"
MARCA_PLAN = "**Resultado de la fase 2"
ESPERAS = ("espera_claude", "espera_damian")
MARCA_SUPERADA = "**Fase 2 superada"


# ================================================================ estado de cada tarea
def serie() -> list[str]:
    p = I._cargar_piloto()
    return list(p["fase2"]) if p.get("fase") == 2 else []


def _solicitud_estado(sid: str | None) -> str | None:
    if not sid:
        return None
    from nucleo import aprobaciones as ap
    try:
        return ap.ver(sid)["estado"]
    except Exception:
        return None


def fase_de(tid: str, p: dict | None = None) -> str:
    """por_hacer | espera_claude | puerta | espera_damian | terminal."""
    p = p or I._cargar_piloto()
    caso = p["casos"].get(tid) or {}
    if caso.get("final") or caso.get("fallo"):
        return "terminal"
    inf = I.cargar_informe(tid)
    if not caso or not inf or inf.get("estado") != "listo":
        return "por_hacer"
    if not caso.get("claude"):
        return "espera_claude"
    if caso.get("solicitud") and _solicitud_estado(caso["solicitud"]) == "pendiente":
        return "espera_damian"
    return "puerta"


def siguiente(p: dict | None = None) -> tuple[str | None, str]:
    p = p or I._cargar_piloto()
    for tid in serie():
        f = fase_de(tid, p)
        if f != "terminal":
            return tid, f
    return None, "terminal"


def accion_pendiente() -> str | None:
    """Que haria una tanda ahora mismo ('implementar', 'puerta', 'cerrar') o None si tiene que esperar."""
    p = I._cargar_piloto()
    if p.get("permanente") and not p.get("aparcado"):
        return _accion_cola(p)
    if p.get("aparcado") or p.get("cierre") or not p.get("activo") or I.detenido() or not serie():
        return None
    tid, fase = siguiente(p)
    if tid is None:
        return "cerrar"
    caso = p["casos"].get(tid) or {}
    if fase in ESPERAS:
        return None
    if fase == "puerta" and caso.get("claude") == "FUSIONAR" and not caso.get("resumen"):
        return None                      # falta el resumen de 3 lineas para la tarjeta de Damian
    if not P.arbol_limpio():
        return None
    return "implementar" if fase == "por_hacer" else "puerta"


def por_que_nada() -> str:
    p = I._cargar_piloto()
    if p.get("aparcado"):
        return "el implementador esta aparcado (la fase 2 no llego al 80 %; plan §3.3 bis)"
    if p.get("permanente"):
        return _por_que_nada_cola(p)
    if p.get("cierre"):
        return "la serie de la fase 2 ya termino y se cerro"
    m = I.detenido()
    if m:
        return m
    tid, fase = siguiente(p)
    caso = (p["casos"].get(tid) or {}) if tid else {}
    if fase == "espera_claude":
        return f"{tid} espera el veredicto de Claude (FUSIONAR/RECHAZAR) en su bandeja del Centro"
    if fase == "espera_damian":
        return f"{tid} espera el OK de Damian en la tarjeta R2 del Centro"
    if fase == "puerta" and caso.get("claude") == "FUSIONAR" and not caso.get("resumen"):
        return f"{tid} tiene el FUSIONAR de Claude pero falta su resumen de 3 lineas (--resumen)"
    if not P.arbol_limpio():
        return "principal tiene cambios sin commit (fuera de memoria/): se reintenta en la siguiente tanda"
    return "no hay nada que hacer en la serie"


def candidatas() -> int:
    return 1 if accion_pendiente() else 0


# ================================================================ una tanda
def _marcar(tid: str, **campos) -> None:
    def f(p):
        p["casos"].setdefault(tid, {"fase": 2, "puerta": None, "fallo": False, "claude": None}).update(campos)
    I._editar_piloto(f)


def _vacio(tid: str, motivo: str) -> bool:
    """Cuenta un intento sin informe; a los MAX_VACIOS la tarea se da por fallida. True si ya es terminal."""
    n = {"v": 0}

    def f(p):
        v = p.setdefault("vacios", {})
        v[tid] = v.get(tid, 0) + 1
        n["v"] = v[tid]
    I._editar_piloto(f)
    if n["v"] >= MAX_VACIOS:
        I.registrar_puerta(tid, pasa=False, fallo=True)
        _marcar(tid, final="sin_informe", motivo_final=motivo[:300])
        return True
    return False


def _avisar(titulo: str, cuerpo: str, clave: str) -> None:
    try:
        from nucleo import avisos
        avisos.emitir("implementador", titulo, cuerpo, ruta="/", clave=clave)
    except Exception:
        pass


def _usada_rehacer(estado: str | None, tid: str) -> bool:
    """Bloque 23: un OK 'usada' en una fusion que luego se deshizo no es final: riesgo.fusion abre otra solicitud en la
    siguiente pasada de la puerta y Damian vuelve a decidir (caso T844, A0097)."""
    if estado != "usada":
        return False
    from nucleo import riesgo
    return riesgo.fusion_deshecha(tid)


def _resolver_puerta(tid: str, g: dict) -> str:
    """Guarda el resultado de la puerta en el caso. Devuelve 'terminal' o 'espera'."""
    est = g.get("estado", "")
    if g.get("solicitud"):
        _marcar(tid, solicitud=g["solicitud"])
    if est in ("fusionada", "rechazada_claude", "rechazada", "revertida", "r3", "conflicto", "sin_implementacion"):
        _marcar(tid, final=est, motivo_final=(g.get("motivo") or "")[:300])
        return "terminal"
    if est == "espera_ok":
        s = _solicitud_estado(g.get("solicitud"))
        if s in ("denegada", "caducada", "usada") and not _usada_rehacer(s, tid):
            _marcar(tid, final=f"damian_{s}", motivo_final=g.get("motivo", "")[:300])
            return "terminal"
    return "espera"                      # espera_ok pendiente, espera_arbol_limpio


def tanda(simular: bool = False, ejecutar=None, limite: float | None = None) -> dict:
    """UNA accion sobre la primera tarea sin terminar. `ejecutar` = doble de Aider (tests). `limite` = hora (epoch) en
    que acaba la ventana del turno (solo la usa el modo permanente, Bloque 21)."""
    r = {"accion": "nada", "tarea": None, "motivo": "", "simular": simular, "aviso": False}
    if I._cargar_piloto().get("permanente"):
        return tanda_cola(simular, ejecutar, limite=limite)
    accion = accion_pendiente()
    p = I._cargar_piloto()
    if accion is None:
        r["motivo"] = por_que_nada()
        return r
    if accion == "cerrar":
        r.update(accion="cerrar", motivo="la serie termino")
        if not simular:
            r["cierre"] = cerrar()
            r["aviso"] = True
        return r
    tid, fase = siguiente(p)
    r["tarea"] = tid
    if accion == "implementar":
        r.update(accion="implementar", motivo=f"implementar {tid} desde principal actualizado")
        if simular:
            return r
        inf = I.implementar(tid, ejecutar=ejecutar)
        r["estado"] = inf["estado"]
        if inf["estado"] == "listo":
            g = P.pasar(tid, inf)
            r["puerta"] = g["estado"]
            r["motivo"] = f"{tid} implementada ({inf.get('modelo')}); puerta: {g['estado']}; espera el veredicto de Claude"
            r["aviso"] = True
            _avisar(f"{tid}: diff del piloto esperando a Claude",
                    f"La puerta dice {g['estado']}. Hay que dictaminar FUSIONAR/RECHAZAR (orden en CLAUDE_BANDEJA.md).",
                    f"piloto2:{tid}:claude")
        elif inf["estado"] == "fallido":
            _marcar(tid, final="fallido", motivo_final=(inf.get("motivo") or "")[:300])
            r["motivo"] = f"{tid} fallida tras {len(inf.get('intentos', []))} intentos: {(inf.get('motivo') or '')[:160]}"
            r["aviso"] = True
        else:                            # detenido, no_autorizado, error: no cuenta como intento
            terminal = inf["estado"] not in ("detenido", "sin_suite") and _vacio(tid, inf.get("motivo", ""))
            r["motivo"] = f"{tid}: {inf['estado']}: {(inf.get('motivo') or '')[:160]}" + (" (se da por fallida)" if terminal else "")
        return r
    caso = p["casos"].get(tid) or {}
    if caso.get("puerta") is False:      # la puerta ya dijo NO: el veredicto de Claude solo mide la coincidencia
        r.update(accion="puerta", motivo=f"{tid}: la puerta ya la rechazo; con el veredicto de Claude ({caso.get('claude')}) se cierra")
        if not simular:
            _marcar(tid, final="rechazada", motivo_final="la puerta no pasaba; Claude: " + str(caso.get("claude")))
            r["aviso"] = True
        return r
    r.update(accion="puerta", motivo=f"{tid}: vuelve a pasar la puerta con el veredicto de Claude")
    if simular:
        return r
    g = P.pasar(tid)
    res = _resolver_puerta(tid, g)
    r.update(puerta=g["estado"], motivo=f"{tid}: puerta {g['estado']}: {(g.get('motivo') or '')[:160]}")
    if g.get("solicitud") and g["estado"] == "espera_ok":
        r["aviso"] = True
        _avisar(f"{tid} espera tu OK en el Centro", "Tarjeta R2 con el resumen de Claude y el diff.", f"piloto2:{tid}:damian")
    if res == "terminal":
        r["aviso"] = True
    return r


# ================================================================ cierre
def metricas() -> dict:
    """Exito y coincidencia de la fase 2 SOLO con los casos de la serie (sin recurrir a los de la fase 1)."""
    p = I._cargar_piloto()
    exito, coinc = I._metricas([p["casos"][t] for t in serie() if t in p["casos"]])
    return {"exito": exito, "coincidencia": coinc}


def _pct(x) -> str:
    return "sin datos" if x is None else f"{x:.0%}"


def _parrafo_plan(m: dict, finales: dict) -> str:
    detalle = "; ".join(f"{t}: {f}" for t, f in finales.items())
    return (f"{MARCA_PLAN} ({datetime.now():%d/%m}, cierre automatico):** exito {_pct(m['exito'])} y coincidencia "
            f"puerta-Claude {_pct(m['coincidencia'])} frente al umbral del {UMBRAL:.0%}. Por tarea: {detalle}. "
            "Se aplica la regla de respaldo (§3.3 bis): el implementador queda APARCADO y el Claude de Damian sigue con el "
            "codigo; el turno esta desactivado y hay una tarea para reprobarlo cuando T320 detecte modelos gratuitos nuevos "
            "o mejores.")


def anotar_en_plan(texto: str, plan: Path | None = None, marca: str = MARCA_PLAN) -> bool:
    """Inserta el parrafo antes de '## 6.' del plan (una sola vez). Conserva los finales de linea."""
    plan = plan or PLAN
    if not plan.exists():
        return False
    s = plan.read_bytes().decode("utf-8")
    if marca in s:
        return False
    nl = "\r\n" if "\r\n" in s else "\n"
    i = s.find("## 6.")
    nuevo = texto + nl + nl
    plan.write_bytes((s[:i] + nuevo + s[i:] if i >= 0 else s.rstrip() + nl + nl + texto + nl).encode("utf-8"))
    return True


def cerrar(plan: Path | None = None) -> dict:
    """Calcula exito y coincidencia de la fase 2 y aplica el cierre. Idempotente (guarda `cierre` en el piloto)."""
    p = I._cargar_piloto()
    if p.get("cierre"):
        return p["cierre"]
    m = metricas()
    finales = {t: (p["casos"].get(t) or {}).get("final") or ("fallido" if (p["casos"].get(t) or {}).get("fallo") else "?")
               for t in serie()}
    por_debajo = (m["exito"] or 0) < UMBRAL or (m["coincidencia"] or 0) < UMBRAL
    cierre = {"cuando": datetime.now().isoformat(timespec="seconds"), **m, "finales": finales,
              "decision": "aparcado (§3.3 bis)" if por_debajo else "supera el umbral: sin cambios"}
    resumen = (f"Fase 2 del piloto del implementador terminada: exito {_pct(m['exito'])}, coincidencia "
               f"{_pct(m['coincidencia'])} (umbral {UMBRAL:.0%}).")
    if por_debajo:
        from nucleo import turnos
        def f(pl):
            pl["aparcado"] = True
            pl["cierre"] = cierre
        I._editar_piloto(f)
        try:
            turnos.poner_activo(TURNO_ID, False)
        except Exception as e:
            cierre["turno"] = f"no se pudo desactivar: {e}"
        t = T.anadir(
            "Reprobar el implementador independiente (T669) cuando T320 detecte modelos gratuitos nuevos o mejores",
            detalle=("QUE: repetir el piloto del implementador (nucleo/implementador.py + nucleo/puerta.py, plan §5.4) "
                     "con los modelos gratuitos nuevos o mejores que detecte el banco T320 (turno 'modelos'), empezando por "
                     "los de codigo y los que aguanten editar archivos con --edit-format diff.\n"
                     "CUANDO: solo si T320 registra un modelo gratuito nuevo o claramente mejor en codigo; hasta entonces "
                     "el Claude de Damian sigue con el codigo (plan §3.3 bis).\n"
                     "PARA REABRIR: quitar `aparcado` de memoria/implementador/piloto.json, reactivar el turno "
                     f"{TURNO_ID} en /turnos y, como T685, que la puerta compruebe los hechos del diff contra el repo.\n"
                     f"CONTEXTO: {resumen} Informe: memoria/implementador/piloto.json."),
            importancia=3, urgencia=1, dificultad=2, coste=1, depende="claude", estado="esperando",
            etiquetas=["tras:T320", "epica:T664"])
        cierre["tarea_reprobar"] = t["id"]
        if (T.buscar("T669") or {}).get("id") == "T669":
            T.anotar("T669", f"{datetime.now():%d/%m} CIERRE del piloto (fase 2): {resumen} Por debajo del umbral: "
                             f"implementador APARCADO, turno {TURNO_ID} desactivado, reprueba en {t['id']} (§3.3 bis).")
        cierre["plan"] = anotar_en_plan(_parrafo_plan(m, finales), plan)
        I._editar_piloto(lambda pl: pl.update(cierre=cierre))
        _avisar("Piloto del implementador: APARCADO", resumen + " Se aplica la regla de respaldo (§3.3 bis): "
                "el Claude de Damian sigue con el codigo.", "piloto2:cierre")
    else:
        I._editar_piloto(lambda pl: pl.update(cierre=cierre))
        _avisar("Piloto del implementador: supera el 80 %", resumen + " No he cambiado nada mas: decide Damian.",
                "piloto2:cierre")
    return cierre


def cortada(p: dict | None = None) -> bool:
    """La serie quedo a medias y nadie la va a mover: el turno no existe o esta desactivado (05/10: la web borro
    implpil2 a las 01:10 con tres tareas por rehacer y el cierre automatico no llego a saltar)."""
    p = p or I._cargar_piloto()
    if p.get("cierre") or p.get("aparcado") or not serie() or siguiente(p)[0] is None:
        return False
    from nucleo import turnos
    t = turnos.buscar(TURNO_ID)
    return not t or not t.get("activo", True)


def cerrar_cortada(aplicar: bool = False, plan: Path | None = None) -> dict:
    """Cierra una serie cortada: cada tarea sin terminar cuenta con su ultima ronda archivada
    (memoria/implementador/rondaN/Txxx.json) si fue 'fallido'; si alguna no tiene ronda fallida, no cierra nada."""
    p = I._cargar_piloto()
    r = {"cortada": cortada(p), "aplicar": aplicar, "marcar": {}, "sin_datos": []}
    if not r["cortada"]:
        r["motivo"] = "la serie no esta cortada (o ya se cerro): la lleva el turno"
        return r
    for tid in serie():
        if fase_de(tid, p) == "terminal":
            continue
        rondas = sorted(I.INFORMES.glob(f"ronda*/{tid}.json"))
        inf = json.loads(rondas[-1].read_text(encoding="utf-8")) if rondas else {}
        if inf.get("estado") == "fallido":
            r["marcar"][tid] = (f"{rondas[-1].parent.name}: fallido ({len(inf.get('intentos', []))} intentos); "
                                f"la ronda siguiente no llego a correr: {(inf.get('motivo') or '')[:200]}")
        else:
            r["sin_datos"].append(tid)
    if r["sin_datos"]:
        r["motivo"] = "hay tareas sin ronda fallida archivada: decide Claude/Damian a mano"
        return r
    if aplicar:
        for tid, motivo in r["marcar"].items():
            _marcar(tid, fallo=True, final="fallido", motivo_final=motivo[:300])
        r["cierre"] = cerrar(plan)
    return r


# ================================================================ modo permanente (Damian 11/10)
# Bloque 21: "sin_suite" = la suite no dio resultado (otra suite en marcha o se paso de tiempo): fallo de
# infraestructura, no de la tarea
NO_CUENTAN = ("detenido", "sin_modelo", "sin_suite")
FINALES_PUERTA = ("fusionada", "rechazada", "revertida", "r3", "conflicto", "sin_implementacion", "rechazada_claude")


def _rutas(t: dict) -> list[str]:
    return [str(r).replace("\\", "/") for r in (I.riesgo.previsto(t).get("rutas") or [])]


def apta(t: dict) -> str | None:
    """None si la tarea puede ir al implementador permanente; si no, el motivo."""
    et = t.get("etiquetas") or []
    if t.get("estado") != "pendiente":
        return f"estado {t.get('estado')}"
    if I.TESTS_DADOS not in et:
        return "sin tests dados"
    if "necesita:claude" in et:
        return "necesita a Claude"
    if T.esta_bloqueada(t):            # piezas encadenadas: espera a que se cierre la anterior
        return f"bloqueada por {t.get('bloqueada_por')}"
    if I.riesgo.previsto(t)["nivel"] == "R3":
        return "R3 (blindados, secretos, reglas de Claude...): nunca el implementador"
    if not any(r.startswith("tests/") and (I.REPO / I.CARPETA_TESTS_DADOS / Path(r).name).is_file() for r in _rutas(t)):
        return f"no hay su test en {I.CARPETA_TESTS_DADOS}/"
    return None


def cola(p: dict | None = None) -> list[dict]:
    """Tareas que el implementador permanente puede coger, en el orden de la cola. Sin las que ya ha tocado."""
    p = p or I._cargar_piloto()
    tocadas = set(p.get("cola") or {})
    return [t for t in T.ordenadas(T.cargar()["tareas"]) if t["id"] not in tocadas and apta(t) is None]


def devolver(tid: str, motivo: str, quitar_cierre: bool = False) -> dict:
    """Bloque 23 (29/10): devuelve una tarea a la cola del implementador permanente para otro intento (antes se hacia
    con scripts sueltos, herramientas_nube/_reintentar_impl_1025.py). Su caso pasa a historial_cola, se le quita
    `necesita:claude` y, con quitar_cierre, el cierre viejo de una evidencia que ya no vale (K0018: T844 conservaba
    el 'HECHO Y TESTEADO' de una fusion revertida). Lo R3 o sin tests dados sigue sin ser apto: se dice por que."""
    t = T.buscar(tid) or {}
    if t.get("id") != tid:
        return {"tarea": tid, "devuelta": False, "motivo": "no existe"}
    caso = (I._cargar_piloto().get("cola") or {}).get(tid)
    # Con su implementacion lista (informe "listo" y worktree), vuelve a la PUERTA sobre ella (la rama se pone al dia
    # con principal): T851/T855/T559 cayeron por infraestructura y T854/T857 por el revisor, no por el codigo.
    # Sin implementacion, el caso sale de la cola y la tarea se implementa de nuevo.
    a_puerta = (caso is not None and (I.cargar_informe(tid) or {}).get("estado") == "listo"
                and I.worktree_de(tid).exists())

    def mover(pl):
        if caso is not None:
            pl.setdefault("historial_cola", {}).setdefault(tid, []).append(
                {**caso, "archivado": datetime.now().isoformat(timespec="seconds"), "motivo_devolver": motivo[:200]})
        if a_puerta:
            c = pl["cola"][tid]
            for k in ("final", "motivo_final", "solicitud"):
                c.pop(k, None)
        else:
            (pl.get("cola") or {}).pop(tid, None)
    I._editar_piloto(mover)
    campos = {}
    et = [e for e in (t.get("etiquetas") or []) if e != "necesita:claude"]
    if et != (t.get("etiquetas") or []):
        campos["etiquetas"] = et
    if quitar_cierre and t.get("cierre"):
        campos["cierre"] = {}
    if campos:
        T.actualizar(tid, **campos)
    anterior = (caso or {}).get("motivo_final", "")[:200]
    T.anotar(tid, f"Vuelve a la cola del implementador: {motivo}" + (f" (antes: {anterior})" if anterior else ""))
    return {"tarea": tid, "devuelta": True, "siguiente": "puerta" if a_puerta else "implementar",
            "apta": apta(T.buscar(tid) or {}), "caso_anterior": caso}


def _esperan_ok(p: dict) -> list[str]:
    return [tid for tid, c in (p.get("cola") or {}).items() if not c.get("final") and c.get("solicitud")
            and _solicitud_estado(c["solicitud"]) == "pendiente"]


def _en_puerta(p: dict) -> list[str]:
    """Implementadas sin final que NO esperan el OK de Damian: les toca repasar la puerta."""
    esperan = set(_esperan_ok(p))
    return [tid for tid, c in (p.get("cola") or {}).items() if not c.get("final") and tid not in esperan
            and (I.cargar_informe(tid) or {}).get("estado") == "listo"]


def _accion_cola(p: dict) -> str | None:
    if I.detenido() or not P.arbol_limpio():
        return None
    if _en_puerta(p):
        return "puerta"
    return "implementar" if cola(p) else None


def _por_que_nada_cola(p: dict) -> str:
    m = I.detenido()
    if m:
        return m
    if not P.arbol_limpio():
        return "principal tiene cambios sin commit (fuera de memoria/): se reintenta en la siguiente tanda"
    esperan = _esperan_ok(p)
    extra = f" ({', '.join(esperan)} espera(n) el OK de Damian en el Centro)" if esperan else ""
    return f"no hay tareas con tests dados y riesgo R0-R2 por hacer{extra}"


def _marcar_cola(tid: str, **campos) -> None:
    I._editar_piloto(lambda p: p.setdefault("cola", {}).setdefault(tid, {}).update(campos))


def _cerrar_fusionada(tid: str, g: dict) -> None:
    from nucleo import evidencias
    fusion = (g.get("fusion") or "")[:10]
    rev = g.get("revisor") or {}
    detalle = (f"Implementador permanente (T669): fusionada en principal ({fusion}) por la puerta: suite completa en "
               f"verde en la rama con los tests dados, revisor {rev.get('revisor') or '-'} ({rev.get('familia') or '-'})"
               f" APROBAR, auditor OK; salud tras fusionar: {g.get('motivo') or '-'}")
    try:
        evidencias.cerrar(tid, evidencia={"detalle": detalle, "tipo": "test", "comando": f"puerta.pasar {tid}",
                                          "salida": f"fusionada {fusion}"})
    except Exception as e:            # cerrar no puede tumbar la tanda: queda la nota de la puerta
        T.anotar(tid, f"Implementador permanente: fusionada ({fusion}) pero no se pudo cerrar sola: {e}")


def _resolver_cola(tid: str, g: dict) -> str:
    est = g.get("estado", "")
    if g.get("solicitud"):
        _marcar_cola(tid, solicitud=g["solicitud"])
    if est in FINALES_PUERTA:
        _marcar_cola(tid, final=est, motivo_final=(g.get("motivo") or "")[:300])
        if est == "fusionada":
            _cerrar_fusionada(tid, g)
        elif est != "sin_implementacion":
            t = T.buscar(tid) or {}
            if t.get("id") == tid:
                T.actualizar(tid, etiquetas=list(dict.fromkeys(list(t.get("etiquetas") or []) + ["necesita:claude"])))
        return "terminal"
    s = _solicitud_estado(g.get("solicitud"))
    if est == "espera_ok" and s in ("denegada", "caducada", "usada") and not _usada_rehacer(s, tid):
        _marcar_cola(tid, final=f"damian_{s}", motivo_final=(g.get("motivo") or "")[:300])
        return "terminal"
    return "espera"                      # espera_ok pendiente, espera_arbol_limpio


MARGEN_PUERTA = 180         # s para el revisor y la fusion, ademas de las 2 suites de la puerta


def cabe_la_puerta(limite: float | None, ahora: float | None = None) -> bool:
    """Bloque 21: la puerta pasa 2 suites (la rama y la salud en principal). Tras implementar (1 suite mas), solo se
    sigue si caben en lo que queda de la ventana del turno; si no, la puerta va en la siguiente tanda (_en_puerta la
    recoge) y el turno acaba dentro de su tope sin chocar con el siguiente (test_t675_horario)."""
    if not limite:
        return True
    suite = I.duracion_suite() or I.TIMEOUT_SUITE / 2
    return (ahora or time.time()) + 2 * suite + MARGEN_PUERTA <= limite


def tanda_cola(simular: bool = False, ejecutar=None, limite: float | None = None) -> dict:
    """UNA accion del implementador permanente. `ejecutar` = doble del modelo (tests). `limite`: ver cabe_la_puerta."""
    r = {"accion": "nada", "tarea": None, "motivo": "", "simular": simular, "aviso": False, "modo": "permanente"}
    p = I._cargar_piloto()
    accion = _accion_cola(p)
    if accion is None:
        r["motivo"] = _por_que_nada_cola(p)
        return r
    if accion == "puerta":
        tid = _en_puerta(p)[0]
        r.update(accion="puerta", tarea=tid, motivo=f"{tid}: vuelve a pasar la puerta")
        if simular:
            return r
        g = P.pasar(tid)
    else:
        tid = cola(p)[0]["id"]
        r.update(accion="implementar", tarea=tid, motivo=f"implementar {tid} desde principal actualizado")
        if simular:
            return r
        inf = I.implementar(tid, ejecutar=ejecutar)
        r["estado"] = inf["estado"]
        if inf["estado"] != "listo":
            r["motivo"] = f"{tid}: {inf['estado']}: {(inf.get('motivo') or '')[:160]}"
            if inf["estado"] not in NO_CUENTAN:     # esos no cuentan: se reintenta en otra tanda
                _marcar_cola(tid, final=inf["estado"], motivo_final=(inf.get("motivo") or "")[:300])
                r["aviso"] = inf["estado"] == "fallido"
            return r
        _marcar_cola(tid, modelo=inf.get("modelo"))
        if not cabe_la_puerta(limite):
            r["motivo"] = (f"{tid} implementada ({inf.get('modelo')}); la puerta (2 suites) ya no cabe en esta ventana: "
                           f"va en la siguiente tanda")
            return r
        g = P.pasar(tid, inf)
    res = _resolver_cola(tid, g)
    r.update(puerta=g["estado"], motivo=f"{tid}: puerta {g['estado']}: {(g.get('motivo') or '')[:160]}")
    if g["estado"] == "espera_ok" and g.get("solicitud"):
        r["aviso"] = True
        _avisar(f"{tid} espera tu OK en el Centro", "Tarjeta R2 con el diff del implementador.", f"impl:{tid}:damian")
    if res == "terminal":
        r["aviso"] = True
    return r


def cerrar_superado(motivo: str, plan: Path | None = None) -> dict:
    """Cierra la fase 2 como SUPERADA y deja el implementador en modo permanente (Damian 11/10)."""
    p = I._cargar_piloto()
    exito, coinc = I._metricas([p["casos"][t] for t in p.get("fase2") or [] if t in p["casos"]])
    cierre = {"cuando": datetime.now().isoformat(timespec="seconds"), "exito": exito, "coincidencia": coinc,
              "decision": f"superada: {motivo}",
              "finales": {t: (p["casos"].get(t) or {}).get("final") or "FUSIONAR de Claude" for t in p.get("fase2") or []}}
    texto = (f"{MARCA_SUPERADA} ({datetime.now():%d/%m}):** {motivo}. Exito {_pct(exito)} y coincidencia "
             f"puerta-Claude {_pct(coinc)} (umbral {UMBRAL:.0%}). El implementador pasa a PERMANENTE: turno cada hora, "
             "solo tareas con tests dados y riesgo R0-R2, con la puerta de siempre (R2 = OK de Damian sobre el diff).")
    cierre["plan"] = anotar_en_plan(texto, plan, marca=MARCA_SUPERADA)
    I._editar_piloto(lambda pl: pl.update(activo=False, permanente=True, cierre=cierre))
    return cierre


def estado() -> dict:
    p = I._cargar_piloto()
    return {"serie": {t: fase_de(t, p) for t in serie()}, "siguiente": siguiente(p), "accion": accion_pendiente(),
            "por_que": por_que_nada() if accion_pendiente() is None else "", "aparcado": bool(p.get("aparcado")),
            "cortada": cortada(p), **metricas(), "cierre": p.get("cierre")}


def _cli(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    orden = argv[0] if argv else "estado"
    if orden == "tanda":
        print(json.dumps(tanda(simular="--simular" in argv), ensure_ascii=False, indent=1, default=str))
    elif orden == "cerrar_superado":
        print(json.dumps(cerrar_superado(" ".join(argv[1:]) or "decision de Damian"), ensure_ascii=False, indent=1))
    elif orden == "cola":
        for t in cola():
            print(f"{t['id']}  {t['titulo'][:90]}")
    elif orden == "devolver" and len(argv) >= 3:
        print(json.dumps(devolver(argv[1], argv[2], quitar_cierre="--quitar-cierre" in argv), ensure_ascii=False,
                         indent=1, default=str))
    elif orden == "cerrar_cortada":
        print(json.dumps(cerrar_cortada(aplicar="--aplicar" in argv), ensure_ascii=False, indent=1, default=str))
    else:
        print(json.dumps(estado(), ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(_cli(sys.argv[1:]))
