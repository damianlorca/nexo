# -*- coding: utf-8 -*-
"""Turno de NEXO sin Claude (T079, aprobado por Damian 23/09; plantillas desde la web: T231, 28/09).

Lo lanza el planificador de NEXO (nucleo/planificador.py, dentro de la web) segun la TABLA de turnos de
/turnos, de uno en uno y en cola; "Lanzar ya" va a la misma cola. Tambien a mano. No usa Claude.
28/09: ya no lo lanza una Tarea Programada de Windows (con bateria se quedaba en cola sin arrancar).

QUE hace lo decide la PLANTILLA del turno (o sus instrucciones personalizadas) (nucleo/turnos.py; detalle en nucleo/plantillas_turno.py):
cola por orden, revisar el codigo, revisar archivos, solo investigacion, solo correcciones o vigia de
novedades (T272). Sea cual sea, el trabajo va SIEMPRE por nucleo.trabajo.ciclo(): OK absoluto (T183) +
auditor (T189) + circuito de revision de Claude (T192). Ningun turno escribe codigo: su salida son
borradores y tareas 'propuesta'. En las plantillas de solo lectura una guardia compara el hash de los
archivos del proyecto antes y despues y avisa si algo cambio.

28/09 (T231): salen del turno los pasos que NO pasaban por OK absoluto (mensajes sueltos de Telegram,
etiquetado router:auto, router que cerraba tareas solo y la primera pasada del catalogo). Siguen
disponibles a mano con sus CLIs (consumidor_libres, auto_etiquetado_router, consumidor_router).

Guardas: parada de emergencia (memoria/PARADA_NEXO), interruptor de turnos (nucleo.turnos), puerta de
candidatas (T156: si no hay trabajo, no arranca ni avisa), bloqueo de una tarea tras 3 fallos seguidos
(nucleo.tareas.fallo_turno), candado (nunca dos turnos a la vez), RAM libre minima y tope de minutos
del turno. Deja registro en registros/turno_nexo_*.json (lo pinta la web en /turnos)
y un aviso push al terminar (nucleo.avisos; nada de Telegram, Damian 27/09).

Uso:
  python turno_nexo.py --simular                 # no escribe nada en la cola: solo mira
  python turno_nexo.py --turno=noche              # un turno de la tabla (--manual: lanzado a mano)
  python turno_nexo.py --turno=X --fin=ISO        # vuelve tras ceder el sitio (T1069): tope hasta esa hora
  python turno_nexo.py                           # plantilla 'cola' suelta
  python turno_nexo.py --plantilla=revisar_codigo  # otra plantilla solo esta vez
  python turno_nexo.py --arrancar-chrome         # abre el Chrome de NEXO si esta cerrado (ChatGPT web)
  python turno_nexo.py --sin-web                 # no abre Chrome
  python turno_nexo.py --sin-aviso               # sin push
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from nucleo import parada  # noqa: E402
from nucleo import planificador  # noqa: E402
from nucleo import plantillas_turno  # noqa: E402
from nucleo import turnos  # noqa: E402

RAM_MINIMA_GB = 8.0
# El tope de cada turno es su max_minutos (tabla); el candado se da por huerfano pasado el maximo posible.
TOPE_SEGUNDOS = turnos.MAX_MINUTOS * 60
CANDADO = RAIZ / "memoria" / ".candado_turno_nexo.lock"
REGISTROS = RAIZ / "registros"  # constante para que los tests la lleven a tmp_path


class _MEM(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def ram_libre_gb() -> float:
    m = _MEM(); m.dwLength = ctypes.sizeof(_MEM)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return round(m.ullAvailPhys / 2**30, 1)


# El candado comun (nucleo.candado) esta pensado para escrituras de segundos:
# a los 30 s lo da por huerfano. Un turno dura minutos, asi que va uno propio:
# archivo con marca de tiempo, huerfano solo pasado el tope del turno + 5 min.
def _tomar_candado() -> bool:
    import os
    CANDADO.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(str(CANDADO), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {time.time()}".encode()); os.close(fd)
            return True
        except (FileExistsError, PermissionError):
            try:
                if time.time() - CANDADO.stat().st_mtime > TOPE_SEGUNDOS + 300:
                    CANDADO.unlink()
                    continue
            except OSError:
                continue
            return False
    return False


def _soltar_candado() -> None:
    try:
        CANDADO.unlink()
    except OSError:
        pass


# ------------------------------------------------------------------ pasos
def paso_preparar(ctx: dict, simular: bool) -> tuple[dict, list[dict]]:
    """Que tareas trabaja el turno (en revisar/vigia crea el lote del dia)."""
    lista = plantillas_turno.preparar(ctx, simular=simular)
    return {"tareas": [{"id": t["id"], "titulo": (t.get("titulo") or "")[:100]} for t in lista]}, lista


def paso_trabajo(ctx: dict, lista: list[dict], simular: bool, limite: float) -> dict:
    """OK absoluto + auditor + circuito T192 (nucleo/trabajo.py). Nunca cierra tareas."""
    from nucleo import trabajo
    def al_empezar(t: dict) -> None:   # para el bloque "Turnos" del Centro: que tarea va ahora
        if not simular:
            planificador.progreso(tarea=f"{t['id']} {(t.get('titulo') or '')[:70]}")
    return {"filas": trabajo.ciclo(max_tareas=ctx["max_tareas"], limite=limite, simular=simular, lista=lista,
                                   al_empezar=al_empezar)}


def _abrir_chrome() -> str:
    from extremidades import navegador
    if navegador.activo():
        return "ya abierto"
    navegador.arrancar(aprobado=True)
    time.sleep(8)
    return "abierto" if navegador.activo() else "no se pudo abrir (sigue por API)"


# ------------------------------------------------------------------ puerta
def candidatas(ctx: dict) -> dict[str, int]:
    """T156: cuanto trabajo hay para la plantilla, SIN cargar modelos, abrir Chrome ni crear nada."""
    return {ctx["plantilla"]: plantillas_turno.candidatas(ctx)}


def _hay_trabajo(reg: dict, ctx: dict) -> bool:
    try:
        reg["candidatas"] = candidatas(ctx)
    except Exception as e:  # la puerta nunca impide un turno por un fallo propio
        reg["candidatas_error"] = f"{type(e).__name__}: {e}"[:300]
        return True
    return any(reg["candidatas"].values())


def apagar_por_cola(ctx: dict, simular: bool = False) -> str:
    """T670 (05/10): un turno con `apagar_bajo` (el tribunal de dia) se apaga solo (activo=False en la tabla) en cuanto
    las propuestas abiertas bajan de ese numero. '' si debe trabajar; si no, la explicacion. Un lanzamiento manual
    no lo apaga."""
    umbral = ctx.get("apagar_bajo") or 0
    if not umbral or ctx.get("manual"):
        return ""
    from nucleo import freno
    n = freno.estado_cola()["propuestas"]
    if n >= umbral:
        return ""
    if ctx.get("turno_id") and not simular:
        turnos.poner_activo(ctx["turno_id"], False)
    return (f"quedan {n} propuestas abiertas (menos de {umbral}): el turno se apaga solo; "
            "se vuelve a encender en /turnos si la cola crece")


# ------------------------------------------------------------------ resumen y aviso
def _propuestas(filas: list[dict]) -> list[str]:
    return [p for f in filas for p in f.get("propuestas") or []]


def tribunal_silencioso(paso: dict) -> bool:
    """Noche 05/10: un turno del tribunal que no cambio nada (todo esperando revisores, nada encolado ni nuevo) se
    registra en silencio: sin aviso y fuera del Centro."""
    if not isinstance(paso, dict) or paso.get("error") or paso.get("simulado"):
        return False
    s = paso.get("sincronizado") or {}
    rec = s.get("reconsiderar") or {}
    return not (s.get("nuevos") or s.get("fuera") or s.get("a_claude") or rec.get("encolados") or rec.get("sueltas")
                or paso.get("a_damian") or paso.get("a_claude")
                or any(h.get("fase") != "espera" for h in paso.get("hechos") or []))


def _resumen(reg: dict) -> str:
    p = reg["pasos"]
    lin = [f"Turno NEXO {reg['inicio'][11:16]} · {reg.get('nombre_turno') or reg.get('nombre_plantilla', '?')} "
           f"({reg['duracion_s']} s){' SIMULADO' if reg['simular'] else ''}{' · lanzado a mano' if reg.get('manual') else ''}"]
    for nombre, r in p.items():
        if "error" in r:
            lin.append(f"- {nombre}: ERROR {r['error'][:120]}")
        elif nombre == "preparar":
            lin.append(f"- tareas: {', '.join(t['id'] for t in r['tareas']) or 'ninguna'}")
        elif nombre == "trabajo":
            lin.append("- trabajo: " + (", ".join(
                f"{f['tarea']}={f.get('veredicto', 'simulado' if f.get('simulado') else 'error')}"
                + (f" ({f['auditoria']})" if f.get("auditoria") else "") for f in r["filas"]) or "nada"))
            props = _propuestas(r["filas"])
            if props:
                lin.append(f"- propuestas para revisar: {', '.join(props)}")
        elif nombre == "implementador":
            lin.append(f"- implementador: {r.get('accion')} {r.get('tarea') or ''} · {r.get('motivo', '')[:160]}")
        elif nombre == "chrome":
            lin.append(f"- Chrome: {r.get('estado')}")
        elif nombre == "radar":
            from nucleo import radar
            lin.append("- " + radar.texto_resumen(r))
        elif nombre == "kuzushi":
            from nucleo import kuzushi
            lin.append("- " + kuzushi.texto_resumen(r))
        elif nombre == "tribunal":
            from nucleo.planificador import texto_tribunal
            lin.append("- " + texto_tribunal(r))
    sl = reg.get("solo_lectura")
    if sl:
        lin.append("- solo lectura: OK, el turno no escribio nada en el proyecto" if sl["ok"]
                   else f"- SOLO LECTURA VIOLADA: el turno escribio en {', '.join(sl['cambiados'][:5])}")
    if reg.get("abortado"):
        lin.append(f"ABORTADO: {reg['abortado']}")
    if reg.get("explicacion"):
        lin.append(f"Por que: {reg['explicacion']}")
    if reg.get("handoff"):
        lin.append(f"Handoff: {Path(reg['handoff']).name}")
    return "\n".join(lin)


def _avisar_push(reg: dict, texto: str, nombre_registro: str) -> None:
    from nucleo import avisos
    sl = reg.get("solo_lectura") or {}
    filas = (reg["pasos"].get("trabajo") or {}).get("filas", [])
    if reg.get("abortado"):
        titulo = f"{reg.get('nombre_turno') or 'Turno'}: no hizo nada"
        cuerpo = f"Por qué: {reg.get('explicacion') or reg['abortado']}."[:400]
    else:
        titulo = ("Turno: ALGO CAMBIO en archivos de solo lectura" if sl and not sl.get("ok") else
                  f"Turno terminado: {reg.get('nombre_turno') or reg.get('nombre_plantilla', '')}")[:120]
        cuerpo = (f"{len(filas)} tarea(s), {len(_propuestas(filas))} propuesta(s) para revisar. "
                  + " ".join(texto.splitlines()[1:])[:300])
    grave = (sl and not sl.get("ok")) or any("error" in r for r in reg["pasos"].values())
    avisos.emitir("turno", titulo, cuerpo, ruta="/turnos", clave=f"turno:{nombre_registro}",
                  urgencia="high" if grave else "normal")


# ------------------------------------------------------------------ turno
def _contexto(turno_id: str | None, plantilla: str | None, manual: bool) -> dict:
    """El turno de la tabla (--turno=) o una plantilla suelta (--plantilla=, o 'cola' por defecto)."""
    if turno_id:
        t = turnos.buscar(turno_id)
        if t is None:
            raise SystemExit(f"el turno {turno_id} no existe en la tabla")
        return turnos.contexto(t, manual=manual)
    return turnos.contexto(plantilla=plantilla, manual=manual or bool(plantilla))


def turno(simular=False, sin_web=False, arrancar_chrome=False, avisar=True, plantilla: str | None = None,
          turno_id: str | None = None, manual: bool = False, fin: str | None = None) -> dict:
    """T187 (Damian 04/10): el latido (un hilo, cada minuto) se para en un finally, con CUALQUIER salida: acabe bien,
    por excepcion o por un SystemExit. Un cuelgue lo detecta el planificador porque el turno deja de llamar a
    planificador.progreso() (30 min), no el latido."""
    latido = None if simular else planificador.iniciar_latido()
    try:
        return _turno(simular, sin_web, arrancar_chrome, avisar, plantilla, turno_id, manual, fin)
    finally:
        if latido is not None:
            latido.set()


def _turno(simular, sin_web, arrancar_chrome, avisar, plantilla, turno_id, manual, fin=None) -> dict:
    inicio = time.time()
    ctx = _contexto(turno_id, plantilla, manual)
    if fin:            # T1069: vuelve tras ceder el sitio; su tope es lo que le quedaba de la ventana
        ctx["max_minutos"] = planificador.minutos_hasta(fin, ctx["max_minutos"])
    limite = inicio + ctx["max_minutos"] * 60
    reg = {"inicio": datetime.now().isoformat(timespec="seconds"), "simular": simular,
           "turno_id": ctx["turno_id"], "nombre_turno": ctx["nombre"],
           "plantilla": ctx["plantilla"], "nombre_plantilla": ctx["nombre_plantilla"], "instrucciones": ctx["texto"],
           "personalizadas": ctx["personalizadas"], "tareas_pedidas": ctx["tareas"], "max_tareas": ctx["max_tareas"],
           "max_minutos": ctx["max_minutos"], "manual": ctx["manual"], "ram_inicio_gb": ram_libre_gb(), "pasos": {}}
    if not simular:
        planificador.progreso(pid_turno=os.getpid(), turno=ctx["turno_id"], nombre=ctx["nombre"], paso="comprobando",
                              max_minutos=ctx["max_minutos"], inicio=reg["inicio"])

    if parada.activa():
        reg["abortado"] = f"PARADA DE EMERGENCIA activa: {parada.activa()}"
        reg["explicacion"] = f"la PARADA de emergencia estaba puesta ({parada.activa()})"
    elif turnos.desactivados():
        reg["abortado"] = reg["desactivados"] = f"TURNOS DESACTIVADOS: {turnos.desactivados()}"
        reg["explicacion"] = f"todos los turnos estaban en pausa ({turnos.desactivados()})"
    elif not _hay_trabajo(reg, ctx):
        reg["abortado"] = reg["sin_candidatas"] = "sin candidatas para esta plantilla: no se despierta a nadie"
        reg["explicacion"] = plantillas_turno.por_que_nada(ctx)
    elif not _tomar_candado():
        reg["abortado"] = "ya hay otro turno en marcha (candado ocupado)"
        reg["explicacion"] = "había otro turno en marcha (nunca corren dos a la vez)"
    else:
        # Solo cuenta lo que escribe ESTE proceso (28/09: la foto antes/despues culpaba al turno de lo que
        # editaba otra sesion a la vez).
        guardia = plantillas_turno.GuardiaEscritura().__enter__() if ctx["solo_lectura"] else None
        try:
            if reg["ram_inicio_gb"] < RAM_MINIMA_GB:
                reg["abortado"] = f"RAM libre {reg['ram_inicio_gb']} GB < {RAM_MINIMA_GB}"
                reg["explicacion"] = f"el PC tenía poca memoria libre ({reg['ram_inicio_gb']} GB; hacen falta {RAM_MINIMA_GB})"
            else:
                lista: list[dict] = []

                def preparar():
                    nonlocal lista
                    r, lista = paso_preparar(ctx, simular)
                    return r

                pasos = []
                if arrancar_chrome and not sin_web and not simular:
                    pasos.append(("chrome", lambda: {"estado": _abrir_chrome()}))
                apagado = apagar_por_cola(ctx, simular) if ctx["plantilla"] == "tribunal" else ""
                if apagado:
                    reg["explicacion"] = apagado
                elif ctx["plantilla"] == "tribunal":   # T667: revisa borradores; no genera ni va por trabajo.ciclo
                    from nucleo import tribunal
                    pasos.append(("tribunal", lambda: tribunal.ciclo(limite=limite, simular=simular,
                                                                     max_expedientes=ctx["max_tareas"])))
                elif ctx["plantilla"] == "radar":   # T693: lee fuentes fijas y deja tarjetas; no va por trabajo.ciclo
                    from nucleo import radar
                    pasos.append(("radar", lambda: radar.turno(ctx["texto"], simular=simular)))
                elif ctx["plantilla"] == "modelos":   # T320: banco diario con poca cuota; no va por trabajo.ciclo
                    from nucleo import banco_modelos
                    pasos.append(("modelos", lambda: banco_modelos.turno_diario(progreso=lambda s: None, limite=limite)))
                elif ctx["plantilla"] == "kuzushi":   # T1011 fase 1: observa sin IA; no va por trabajo.ciclo
                    from nucleo import kuzushi
                    pasos.append(("kuzushi", lambda: kuzushi.turno(simular=simular, limite=limite)))
                elif ctx["plantilla"] == "implementador":   # T669 fase 2: una accion de la serie del piloto
                    from nucleo import piloto_serie
                    pasos.append(("implementador", lambda: piloto_serie.tanda(simular=simular, limite=limite)))
                elif ctx["plantilla"] == "reels":   # T859 bloque 6: una noche del lote de reels guardados
                    from extremidades import reels as R
                    # el tope es POR_NOCHE (~30 reels), no max_tareas (1-5 tareas); el tiempo, max_minutos
                    # T1069: entre tramos de una hora cede el sitio si en la cola espera alguien que va antes
                    ceder = (None if simular else
                             lambda: planificador.ceder(ctx["turno_id"], datetime.fromtimestamp(limite),
                                                        manual=ctx["manual"]))
                    pasos.append(("reels", lambda: R.turno(simular=simular, minutos=ctx.get("max_minutos") or 180,
                                                           ceder=ceder)))
                else:
                    pasos += [("preparar", preparar), ("trabajo", lambda: paso_trabajo(ctx, lista, simular, limite))]
                for nombre, fn in pasos:
                    if parada.activa():
                        reg["pasos"][nombre] = {"error": f"saltado: PARADA DE EMERGENCIA ({parada.activa()})"}; continue
                    if parada.cierre_pedido():
                        reg["pasos"][nombre] = {"error": f"saltado: cierre pedido ({parada.motivo_cierre() or 'vigilante'})"}; continue
                    if time.time() > limite:
                        reg["pasos"][nombre] = {"error": "saltado: tope de tiempo"}; continue
                    if ram_libre_gb() < RAM_MINIMA_GB - 3:
                        reg["pasos"][nombre] = {"error": f"saltado: RAM libre {ram_libre_gb()} GB"}; continue
                    if not simular:
                        planificador.progreso(paso=nombre, tarea="")
                    try:
                        reg["pasos"][nombre] = fn()
                    except Exception as e:
                        reg["pasos"][nombre] = {"error": f"{type(e).__name__}: {e}",
                                                "traza": traceback.format_exc()[-1500:]}
        finally:
            _soltar_candado()
            if guardia is not None:
                guardia.__exit__(None, None, None)
                reg["solo_lectura"] = {"ok": not guardia.escritos, "cambiados": guardia.escritos[:50],
                                       "metodo": "escrituras del propio turno"}

    if parada.cierre_pedido():   # "Parar" desde la web (o el vigilante): queda dicho en el registro
        reg["parado"] = parada.motivo_cierre() or "cierre pedido"
    filas = (reg["pasos"].get("trabajo") or {}).get("filas", [])
    if not reg.get("explicacion") and filas and not any(f.get("archivo") or f.get("simulado") for f in filas):
        errores = [i.get("error") for f in filas for i in f.get("intentos", []) if i.get("error")]
        reg["explicacion"] = ("ningún proveedor pudo hacer el trabajo"
                              + (f" (último fallo: {errores[-1][:160]})" if errores else ""))
    elif not reg.get("explicacion") and "preparar" in reg["pasos"] and not filas and not reg.get("abortado"):
        reg["explicacion"] = "no quedó ninguna tarea que trabajar"
    parada.limpiar_cierre()
    reg["duracion_s"] = round(time.time() - inicio)
    try:
        from nucleo import trabajo
        filas = (reg["pasos"].get("trabajo") or {}).get("filas", [])
        if not reg.get("abortado"):
            reg["handoff"] = str(trabajo.handoff(filas, origen="turno_simulado" if simular else "turno"))
    except Exception as e:
        reg["handoff_error"] = str(e)
    reg["ram_fin_gb"] = ram_libre_gb()
    # Cada turno de la tabla dice si avisa. T156: nada hecho, nada que avisar... salvo si Damian lo lanzo a mano.
    reg["aviso_push"] = bool(avisar and ctx["avisar"] and not simular
                             and (ctx["manual"] or not (reg.get("sin_candidatas") or reg.get("desactivados"))))
    if ctx["plantilla"] == "tribunal":   # T667 (Damian 04/10): solo si algo fue a la bandeja de Damian o de Claude
        paso = reg["pasos"].get("tribunal") or {}
        reg["aviso_push"] = bool(avisar and ctx["avisar"] and not simular
                                 and (paso.get("a_damian") or paso.get("a_claude")))
        reg["silencioso"] = tribunal_silencioso(paso) and not ctx["manual"]
    if ctx["plantilla"] == "implementador":   # T669: solo avisa si la tanda hizo algo (los avisos concretos los emite ella)
        reg["aviso_push"] = bool(avisar and ctx["avisar"] and not simular
                                 and (reg["pasos"].get("implementador") or {}).get("aviso"))
    REGISTROS.mkdir(parents=True, exist_ok=True)
    out = REGISTROS / f"turno_nexo_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(reg, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    reg["registro"] = str(out)
    if not simular:
        planificador.terminar()   # la cola puede lanzar el siguiente
    texto = _resumen(reg)
    print(texto)
    if reg["aviso_push"]:
        try:
            _avisar_push(reg, texto, out.name)
        except Exception as e:
            print("aviso push fallo:", e)
    return reg


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    a = sys.argv[1:]
    elegida = next((x.split("=", 1)[1] for x in a if x.startswith("--plantilla=")), None)
    if elegida and elegida not in turnos.PLANTILLAS:
        sys.exit(f"plantilla desconocida: {elegida} (validas: {', '.join(turnos.PLANTILLAS)})")
    tid = next((x.split("=", 1)[1] for x in a if x.startswith("--turno=")), None)
    fin = next((x.split("=", 1)[1] for x in a if x.startswith("--fin=")), None)
    try:
        turno(simular="--simular" in a, sin_web="--sin-web" in a, arrancar_chrome="--arrancar-chrome" in a,
              avisar="--sin-aviso" not in a, plantilla=elegida, turno_id=tid, manual="--manual" in a, fin=fin)
    finally:
        if "--simular" not in a:
            planificador.terminar()   # pase lo que pase, el turno no deja la cola bloqueada
