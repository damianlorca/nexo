# -*- coding: utf-8 -*-
"""Planificador de turnos de NEXO (T231, 28/09): lee la tabla de turnos y los lanza de UNO en UNO.

Por que no una Tarea Programada de Windows por turno (decision de Claude, 28/09, tras el fallo de la prueba
real): la tarea "NEXO turno" tenia DisallowStartIfOnBatteries (valor por defecto) y con el portatil a bateria
Windows dejaba el "Lanzar ya" en cola sin arrancar y sin dar error; con IgnoreNew un segundo turno se descarta
en vez de esperar; y cada cambio de horario era un schtasks. Aqui no hay nada de eso:

  - tick() lo llama la web cada CADA segundos (interfaz/vigilancia.py). Encola cada turno activo cuya hora
    haya llegado (y no se haya disparado ya); si el PC o la web estaban apagados, recupera las horas de la
    ultima GRACIA. Luego, si no hay un turno en marcha, saca el primero de la cola y lo lanza.
  - "Lanzar ya" (encolar(..., manual=True)) va a la misma cola: dos seguidos se ejecutan uno tras otro.
  - Un turno en marcha deja memoria/turno_en_marcha.json (pid, paso, tarea, inicio); el planificador lo
    escribe al lanzar y turno_nexo.py lo actualiza y lo quita al acabar. Si el pid ya no vive, se limpia.
  - choques(): turnos cuyas ventanas (hora .. hora + tope de minutos) se pisan; el segundo esperara en cola.
Limite: si la web no esta en marcha no se lanza nada (la arranca al iniciar sesion la Tarea "NEXO interfaz" y
el vigia la relanza); las horas perdidas de mas de GRACIA no se recuperan.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from nucleo import freno, turnos
from nucleo.candado import bloqueo
from nucleo.escritura import escribir_atomico

RAIZ = Path(__file__).resolve().parent.parent
ESTADO = RAIZ / "memoria" / "planificador.json"
EN_MARCHA = RAIZ / "memoria" / "turno_en_marcha.json"
CANDADO = RAIZ / "memoria" / ".candado_planificador.lock"
SALIDAS = RAIZ / "registros"
CADA = 20                     # s entre ticks (lo usa la web)
GRACIA = timedelta(minutes=60)
ARRANQUE = 180                # s que se da a un turno recien lanzado para escribir su pid real
CADUCA_COLA = timedelta(hours=6)
DIAS = turnos.DIAS


# ------------------------------------------------------------------ utilidades
def _vivo(pid: int) -> bool:
    """El proceso existe (solo consulta; mismo metodo que canal/vigilante.py)."""
    if not pid or pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    h = k.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    try:
        codigo = wintypes.DWORD()
        return codigo.value == 259 if k.GetExitCodeProcess(h, ctypes.byref(codigo)) else True
    finally:
        k.CloseHandle(h)


def _leer(ruta: Path, defecto):
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
        return d if isinstance(d, type(defecto)) else defecto
    except (OSError, ValueError):
        return defecto


def _escribir(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(ruta, json.dumps(datos, ensure_ascii=False, indent=1))


DIAS_CORTOS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def fecha_corta(d: datetime) -> str:
    return f"{DIAS_CORTOS[d.weekday()]} {d:%d/%m %H:%M}"


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


# ------------------------------------------------------------------ calendario
def ocurrencias(turno: dict, desde: datetime, hasta: datetime) -> list[datetime]:
    """Horas programadas del turno en (desde, hasta]."""
    salida, dia = [], desde.date()
    while dia <= hasta.date():
        if DIAS[dia.weekday()] in turno["dias"]:
            for h in turno["horas"]:
                cuando = datetime.combine(dia, datetime.strptime(h, "%H:%M").time())
                if desde < cuando <= hasta:
                    salida.append(cuando)
        dia += timedelta(days=1)
    return sorted(salida)


def proxima(turno: dict, ahora: datetime | None = None) -> datetime | None:
    ahora = ahora or datetime.now()
    siguientes = ocurrencias(turno, ahora, ahora + timedelta(days=8))
    return siguientes[0] if siguientes else None


def choques(cfg: dict | None = None) -> dict[str, list[str]]:
    """{turno_id: [nombres con los que se pisa]} entre turnos ACTIVOS (ventana hora .. hora + tope minutos)."""
    activos = [t for t in (cfg or turnos.cargar())["turnos"] if t["activo"]]
    semana = 7 * 1440

    def ventanas(t):
        for d in t["dias"]:
            for h in t["horas"]:
                ini = DIAS.index(d) * 1440 + int(h[:2]) * 60 + int(h[3:])
                yield ini, ini + t["max_minutos"]

    def pisan(a, b):
        for a0, a1 in ventanas(a):
            for b0, b1 in ventanas(b):
                for desplazar in (-semana, 0, semana):   # el domingo por la noche pisa el lunes
                    if a0 < b1 + desplazar and b0 + desplazar < a1:
                        return True
        return False

    salida: dict[str, list[str]] = {}
    for i, a in enumerate(activos):
        for b in activos[i + 1:]:
            if pisan(a, b):
                salida.setdefault(a["id"], []).append(b["nombre"])
                salida.setdefault(b["id"], []).append(a["nombre"])
    return salida


# ------------------------------------------------------------------ cola
def estado() -> dict:
    return _leer(ESTADO, {})


def cola() -> list[dict]:
    return estado().get("cola") or []


def encolar(turno_id: str, manual: bool = False, cuando: datetime | None = None) -> dict:
    """Pone un turno en la cola (una sola vez: si ya esta esperando, no se repite)."""
    if not turnos.buscar(turno_id):
        raise turnos.ConfigInvalida("ese turno ya no existe")
    with bloqueo(CANDADO):
        est = estado()
        c = est.setdefault("cola", [])
        ya = next((x for x in c if x["turno"] == turno_id), None)
        if ya:
            return ya
        entrada = {"turno": turno_id, "manual": manual, "pedido": _iso(cuando or datetime.now())}
        c.append(entrada)
        _escribir(ESTADO, est)
        return entrada


# ------------------------------------------------------------------ "Trabajar ahora" (Bloque 8, 17/10)
# Damian: "cuando se que voy a estar un rato en el ordenador, le doy y se pone a currar en segundo plano".
# Encola UNA vez cada turno activo que tenga trabajo ahora, en este orden. A diferencia de "Lanzar ya" NO se salta
# el freno F0 (las generadoras frenadas salen en `saltados`). Con `horas` entra en modo trabajo hasta esa hora:
# cuando la cola se vacia, el tick vuelve a encolar mientras algun turno tenga trabajo (tope TANDAS_MAX por turno).
ORDEN_TRABAJO = ("tribunal", "implementador", "cola", "investigacion", "correcciones",
                 "revisar_codigo", "revisar_archivos", "vigia", "kuzushi", "radar", "reels")
TANDAS_MAX = 3
HORAS_TRABAJO = (1, 2, 3)
PROVEEDORES_TRABAJO = ("groq", "nvidia", "openrouter", "gemini_api", "chatgpt", "gemini")


def _por_que_no_trabajar(turno: dict, vistas: set) -> str:
    """'' si el turno puede encolarse ahora; si no, el motivo (sin efectos)."""
    from nucleo import plantillas_turno
    pl = turno["plantilla"]
    if pl in vistas:
        return "otro turno de la misma plantilla ya entra en esta pasada"
    ok, motivo = freno.puede_generar(pl)
    if not ok:
        return motivo
    ctx = turnos.contexto(turno, manual=False)   # T1007: se cuenta como lo vera el turno programado (con el freno)
    try:
        n = plantillas_turno.candidatas(ctx)
    except Exception as e:
        return f"no se pudo comprobar si hay trabajo ({type(e).__name__})"
    if n <= 0:
        try:
            return "sin trabajo: " + plantillas_turno.por_que_nada(ctx)
        except Exception:
            return "sin trabajo ahora"
    return ""


def _encolar_trabajo(est: dict, c: list, ahora: datetime, cfg: dict) -> dict:
    """Parte comun (con el candado ya puesto): anade a `c` los turnos con trabajo y cuenta tandas si hay modo."""
    from nucleo import parada
    res = {"encolados": [], "saltados": []}
    if parada.activa():
        res["saltados"].append({"turno": "*", "motivo": "PARADA puesta"})
        return res
    if turnos.desactivados():
        res["saltados"].append({"turno": "*", "motivo": "interruptor general de turnos apagado"})
        return res
    modo = est.get("trabajo")
    tandas = modo.setdefault("tandas", {}) if modo else {}
    activos = [t for t in cfg["turnos"] if t["activo"] and t["plantilla"] in ORDEN_TRABAJO]
    activos.sort(key=lambda t: ORDEN_TRABAJO.index(t["plantilla"]))
    vistas: set = set()
    marcha = en_marcha()
    for t in activos:
        if any(x["turno"] == t["id"] for x in c):
            res["saltados"].append({"turno": t["id"], "motivo": "ya esta en la cola"})
        elif marcha and marcha.get("turno") == t["id"]:
            res["saltados"].append({"turno": t["id"], "motivo": "esta en marcha"})
        elif modo and tandas.get(t["id"], 0) >= TANDAS_MAX:
            res["saltados"].append({"turno": t["id"], "motivo": f"tope de {TANDAS_MAX} tandas en este modo"})
        else:
            motivo = _por_que_no_trabajar(t, vistas)
            if motivo:
                res["saltados"].append({"turno": t["id"], "motivo": motivo})
                continue
            vistas.add(t["plantilla"])
            c.append({"turno": t["id"], "manual": False, "pedido": _iso(ahora),
                      "prio": ORDEN_TRABAJO.index(t["plantilla"]), "trabajo": True})
            if modo:
                tandas[t["id"]] = tandas.get(t["id"], 0) + 1
            res["encolados"].append(t["id"])
    return res


def encolar_todos(horas: int | None = None, ahora: datetime | None = None) -> dict:
    """'Trabajar ahora': encola cada turno activo con trabajo (orden fijo, respeta el freno F0). Con horas=1|2|3 deja
    ademas el modo trabajo puesto hasta esa hora. Devuelve {"encolados": [...], "saltados": [{turno, motivo}], "hasta"}."""
    if horas is not None and horas not in HORAS_TRABAJO:
        raise turnos.ConfigInvalida("las horas de trabajo son 1, 2 o 3")
    ahora = ahora or datetime.now()
    with bloqueo(CANDADO):
        est = estado()
        c = [x for x in est.get("cola") or [] if _vigente(x, ahora)]
        if horas:
            est["trabajo"] = {"desde": _iso(ahora), "hasta": _iso(ahora + timedelta(hours=horas)), "tandas": {},
                              "horas": horas}
        else:
            est.pop("trabajo", None)
        res = _encolar_trabajo(est, c, ahora, turnos.cargar())
        est["cola"] = c
        est["ultimo_trabajo"] = {"cuando": _iso(ahora), "encolados": res["encolados"], "saltados": res["saltados"],
                                 "horas": horas or 0}
        _escribir(ESTADO, est)
        res["hasta"] = (est.get("trabajo") or {}).get("hasta", "")
    return res


def dejar_de_trabajar() -> bool:
    """Quita el modo trabajo. No toca la cola ni mata nada."""
    with bloqueo(CANDADO):
        est = estado()
        habia = bool(est.pop("trabajo", None))
        if habia:
            est["ultimo_trabajo"] = dict(est.get("ultimo_trabajo") or {}, fin="a mano")
            _escribir(ESTADO, est)
    return habia


def modo_trabajo() -> dict | None:
    return estado().get("trabajo") or None


def _fin_modo(est: dict, motivo: str) -> str:
    est.pop("trabajo", None)
    est["ultimo_trabajo"] = dict(est.get("ultimo_trabajo") or {}, fin=motivo)
    return motivo


def _tanda_de_trabajo(est: dict, c: list, ahora: datetime, cfg: dict) -> str:
    """Desde tick() con el candado puesto. Con el modo puesto, la cola vacia y nada en marcha, encola otra tanda
    mientras haya trabajo. Devuelve lo que hizo o por que acabo el modo ('' si no hay modo)."""
    modo = est.get("trabajo")
    if not modo:
        return ""
    from nucleo import cuota, parada
    if ahora >= datetime.fromisoformat(modo["hasta"]):
        return _fin_modo(est, "llego la hora")
    if parada.activa():
        return _fin_modo(est, "PARADA puesta")
    if turnos.desactivados():
        return _fin_modo(est, "interruptor general apagado")
    if c or en_marcha():
        return "esperando a que acabe lo encolado"
    try:
        sigue, motivo = cuota.seguir(PROVEEDORES_TRABAJO, ahora.timestamp())
    except Exception:
        sigue, motivo = True, ""
    if not sigue:
        return _fin_modo(est, motivo)
    res = _encolar_trabajo(est, c, ahora, cfg)
    est["ultimo_trabajo"] = {"cuando": _iso(ahora), "encolados": res["encolados"], "saltados": res["saltados"],
                             "horas": modo.get("horas", 0)}
    if not res["encolados"]:
        return _fin_modo(est, "sin trabajo")
    return "tanda: " + ", ".join(res["encolados"])


# ------------------------------------------------------------------ en marcha
def en_marcha() -> dict | None:
    """El turno que corre ahora (con su progreso) o None. Limpia el fichero si el proceso ya no vive.
    T187: si el proceso murio SIN cerrar (no llego a limpiar el fichero), deja un registro con el fallo para
    que la vigilancia de la web mande el push (antes el fallo mas grave quedaba mudo)."""
    d = _leer(EN_MARCHA, {})
    if not d:
        return None
    edad = time.time() - float(d.get("lanzado") or 0)
    # T1024: un turno VIVO nunca se suelta, aunque pase su tope (el 19/10 se borraba el fichero a tope + 15 min y el
    # proceso seguia suelto, sin registro y con la cola libre para lanzar otro): lo cierra _cerrar_por_tope().
    if (edad < ARRANQUE and not d.get("pid_turno")) or _vivo(_pid(d)):
        return d
    _registrar_muerte(d)
    try:
        EN_MARCHA.unlink()   # el proceso murio sin limpiar: no bloquea la cola
    except OSError:
        pass
    return None


def _pid(d: dict) -> int:
    """El pid del turno (el que escribe turno_nexo.py) o, si aun no lo ha escrito, el del lanzador."""
    return int(d.get("pid_turno") or d.get("pid") or 0)


# T187 (Damian 04/10): turno_nexo.py escribe un latido cada LATIDO s en turno_en_marcha.json.
LATIDO = 60                   # s entre latidos (los escribe el turno)
LATIDO_MAX = 180              # s sin latido con el pid vivo = sospecha (PC dormido, proceso colgado)
LATIDO_CONFIRMA = 60          # s mas sin latido antes de avisar: al despertar el PC el primer tick no avisa en falso


def _hace(segundos: float) -> str:
    return f"{round(segundos / 60)} min" if segundos >= 90 else f"{round(segundos)} s"


def _registrar_muerte(d: dict) -> Path | None:
    """El proceso del turno ya no vive y no limpio su fichero: registro de fallo (lo ve la web y manda push).
    Si el turno ya escribio su registro final (murio justo despues), no se duplica."""
    from nucleo import registro
    lanzado = float(d.get("lanzado") or 0)
    registro.CARPETA.mkdir(parents=True, exist_ok=True)
    try:
        if any(p.stat().st_mtime >= lanzado for p in registro.CARPETA.glob("turno_nexo_*.json")):
            return None
    except OSError:
        pass
    ultimo = float(d.get("latido") or d.get("actualizado") or lanzado)
    paso = d.get("paso") or "?"
    if d.get("pid_turno"):
        motivo = (f"el turno murio sin dejar registro: ultimo latido hace {_hace(time.time() - ultimo)}, "
                  f"en el paso '{paso}'" + (f", tarea {d['tarea']}" if d.get("tarea") else ""))
    else:
        motivo = "el turno no llego a arrancar (el proceso lanzado murio antes de empezar)"
    reg = {"inicio": datetime.fromtimestamp(lanzado).isoformat(timespec="seconds") if lanzado else "",
           "turno_id": d.get("turno"), "nombre_turno": d.get("nombre"), "manual": d.get("manual"),
           "abortado": motivo, "explicacion": motivo, "pasos": {"turno": {"error": motivo}}, "aviso_push": False}
    ruta = registro.CARPETA / f"turno_nexo_{datetime.now():%Y%m%d_%H%M%S}.json"
    escribir_atomico(ruta, json.dumps(reg, ensure_ascii=False, indent=1))
    return ruta


def _vigilar_latido(ahora_s: float | None = None) -> str | None:
    """Turno con el proceso vivo pero sin latido: sospecha, y a los LATIDO_CONFIRMA s mas, un aviso (una vez)."""
    d = _leer(EN_MARCHA, {})
    if not d or not d.get("pid_turno") or not d.get("latido") or d.get("latido_avisado"):
        return None
    ahora_s = ahora_s or time.time()
    latido = float(d["latido"])
    if ahora_s - latido < LATIDO_MAX:
        if d.get("latido_sospecha"):
            _anotar({"latido_sospecha": 0}, False)
        return None
    sospecha = float(d.get("latido_sospecha") or 0)
    if sospecha < latido:      # primera vez que lo vemos parado (o volvio a latir y se paro otra vez)
        _anotar({"latido_sospecha": ahora_s}, False)
        return "sospecha"
    if ahora_s - sospecha < LATIDO_CONFIRMA:
        return "sospecha"
    from nucleo import avisos
    avisos.emitir("turno_sin_latido", f"Turno {d.get('nombre') or d.get('turno')} sin señales",
                  f"El turno sigue en marcha pero no da señales desde hace {_hace(ahora_s - latido)} "
                  f"(paso '{d.get('paso') or '?'}'). Mira /turnos.", ruta="/turnos",
                  clave=f"latido:{d.get('lanzado')}")
    _anotar({"latido_avisado": True}, False)
    return "avisado"


def progreso(**campos) -> None:
    """Lo llama turno_nexo.py: paso, tarea... (y pid_turno al empezar). Sin fichero, lo crea (lanzado a mano).
    Cada llamada pone `actualizado`: es la prueba de que el turno AVANZA (T187: sin ella 30 min, aviso)."""
    _anotar(campos, tocar=True)


def progreso_si_turno(**campos) -> bool:
    """T890: como progreso(), pero SOLO si este proceso es el turno en marcha (pid_turno). Para quien puede correr
    dentro de un turno o suelto (CLI, tests): suelto no crea turno_en_marcha.json ni finge un turno vivo."""
    d = _leer(EN_MARCHA, {})
    if not d or d.get("pid_turno") != os.getpid():
        return False
    progreso(**campos)
    return True


def _anotar(campos: dict, tocar: bool) -> None:
    """Escribe campos en turno_en_marcha.json. tocar=False (latido, sospechas, avisos) NO cuenta como avance: un
    hilo que late no demuestra que el turno no este colgado."""
    d = _leer(EN_MARCHA, {})
    d.update(campos)
    if tocar:
        d["actualizado"] = time.time()
    d.setdefault("lanzado", time.time())
    _escribir(EN_MARCHA, d)


PROGRESO_MAX = 1800           # s: turno vivo sin llamar a progreso() (cambio de paso o de tarea) = colgado


def _vigilar_progreso(ahora_s: float | None = None) -> str | None:
    """T187 (Damian 04/10): el latido es de un hilo y late aunque el turno este colgado en una llamada. Lo que
    prueba que avanza es progreso(): si el turno esta vivo y no la llama en PROGRESO_MAX s, un aviso (una vez)."""
    d = _leer(EN_MARCHA, {})
    if not d or not d.get("pid_turno") or d.get("progreso_avisado") or not _vivo(int(d["pid_turno"])):
        return None
    ahora_s = ahora_s or time.time()
    ultimo = float(d.get("actualizado") or d.get("lanzado") or ahora_s)
    if ahora_s - ultimo < PROGRESO_MAX:
        return None
    from nucleo import avisos
    avisos.emitir("turno_colgado", f"Turno {d.get('nombre') or d.get('turno')} sin avanzar",
                  f"El turno sigue vivo pero lleva {_hace(ahora_s - ultimo)} en el paso '{d.get('paso') or '?'}'"
                  + (f" ({d['tarea']})" if d.get("tarea") else "") + " sin cambiar de paso ni de tarea. "
                  "Mira /turnos y usa Parar si no avanza.", ruta="/turnos", clave=f"progreso:{d.get('lanzado')}")
    _anotar({"progreso_avisado": True}, False)
    return "avisado"


def iniciar_latido(cada: float | None = None):
    """T187: lo llama turno_nexo.py al empezar. Un hilo escribe `latido` en turno_en_marcha.json cada LATIDO s
    (el primero, ya). Devuelve el Event que lo para (`.set()`). Un fallo al escribir no tumba el turno."""
    import threading
    parar = threading.Event()
    cada = LATIDO if cada is None else cada

    def latir():
        while not parar.is_set():
            try:
                if EN_MARCHA.exists():   # nunca recrea el fichero que terminar() acaba de borrar
                    _anotar({"latido": time.time()}, False)
            except Exception:
                pass
            parar.wait(cada)

    threading.Thread(target=latir, name="latido-turno", daemon=True).start()
    return parar


def terminar() -> None:
    try:
        EN_MARCHA.unlink()
    except OSError:
        pass


# ------------------------------------------------------------------ lanzar
def _interprete() -> str:
    for nombre in ("pythonw.exe", "python.exe"):
        p = RAIZ / ".venv" / "Scripts" / nombre
        if p.is_file():
            return str(p)
    return sys.executable


_popen = subprocess.Popen   # los tests lo sustituyen (conftest: nunca un turno real en la suite)


def lanzar_proceso(entrada: dict) -> int:
    """Arranca turno_nexo.py suelto (sobrevive a un reinicio de la web). Devuelve el pid del lanzador."""
    SALIDAS.mkdir(parents=True, exist_ok=True)
    salida = open(SALIDAS / f"turno_salida_{datetime.now():%Y%m%d_%H%M%S}.log", "ab")
    args = [_interprete(), str(RAIZ / "turno_nexo.py"), f"--turno={entrada['turno']}", "--arrancar-chrome"]
    if entrada.get("manual"):
        args.append("--manual")
    if entrada.get("fin"):          # T1069: vuelve tras ceder; su tope es lo que le quedaba de la ventana
        args.append(f"--fin={entrada['fin']}")
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x8) | \
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = _popen(args, cwd=str(RAIZ), stdout=salida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         creationflags=flags, close_fds=True)
    salida.close()
    return p.pid


# 6c (12/10): la cola es de uno en uno; cuando hay varios listos, manda la prioridad (menor = antes) y, a igualdad, el que
# se pidio antes. Tribunal > implementador > cola > correcciones > reels > revisiones > vigia/kuzushi > radar > modelos.
PRIORIDAD = {"tribunal": 0, "implementador": 1, "cola": 2, "investigacion": 2, "correcciones": 3, "reels": 4,
             "revisar_codigo": 5, "revisar_archivos": 5, "vigia": 6, "kuzushi": 6, "radar": 7, "modelos": 8}
PRIORIDAD_DEFECTO = 9


def _orden_cola(x: dict, cfg: dict) -> tuple:
    """Clave de salida de la cola: lo manual ("Lanzar ya" de Damian) primero, luego prioridad y hora pedida."""
    t = turnos.buscar(x["turno"], cfg)
    prio = x["prio"] if "prio" in x else PRIORIDAD.get((t or {}).get("plantilla"), PRIORIDAD_DEFECTO)
    return (0 if x.get("manual") else 1, prio, x["pedido"])


def _vigente(x: dict, ahora: datetime) -> bool:
    """Una entrada de la cola caduca CADUCA_COLA despues de su hora (la pedida o la de pospuesto). La de un turno que
    cedio (T1069) caduca tambien cuando ya no le quedan MIN_RESTO minutos de su ventana."""
    if x.get("fin") and datetime.fromisoformat(x["fin"]) - ahora < timedelta(minutes=MIN_RESTO):
        return False
    ref = max(datetime.fromisoformat(x["pedido"]), datetime.fromisoformat(x.get("no_antes") or x["pedido"]))
    return ahora - ref < CADUCA_COLA


def _lista(x: dict, ahora: datetime) -> bool:
    return not x.get("no_antes") or datetime.fromisoformat(x["no_antes"]) <= ahora


# T1069 (Bloque 20, 25/10): la noche del 25/10 el lote de reels encadeno lotes de 02:00 a pasadas las 10:00 y el
# implementador y el tribunal esperaron en cola casi toda la noche (1 fusion). Un turno largo que sabe cortarse limpio
# (el lote de reels, por tramos con --hasta que acaban a cada hora en punto) pregunta al acabar cada tramo si en la cola
# espera alguien que va antes que el (lo manual de Damian o menor PRIORIDAD/ORDEN_TRABAJO, sin lo que el freno F0 no
# dejaria salir); si lo hay, cede: acaba y vuelve a la cola detras de ellos con lo que le quedaba de su ventana (`fin`).
MIN_RESTO = 10              # min: con menos ventana por delante, el turno que cede no vuelve a la cola


def _por_delante(x: dict, prio: int, cfg: dict, ahora: datetime, frenos: dict) -> bool:
    """La entrada `x` de la cola saldria antes que un turno de prioridad `prio` y nada la retiene ahora mismo."""
    from nucleo import parada
    if not _lista(x, ahora) or parada.activa():
        return False
    if x.get("manual"):
        return True
    t = turnos.buscar(x["turno"], cfg)
    if t is None or turnos.desactivados():
        return False
    if t.get("plantilla") in freno.GENERADORAS:
        if t["plantilla"] not in frenos:
            frenos[t["plantilla"]] = freno.puede_generar(t["plantilla"])[0]
        if not frenos[t["plantilla"]]:
            return False
    return _orden_cola(x, cfg)[1] < prio


def ceder(turno_id: str, fin: datetime, manual: bool = False, ahora: datetime | None = None) -> list[str]:
    """Lo llama un turno largo entre tramos. Si en la cola espera alguien que va antes que el, lo vuelve a encolar (con
    `fin`, la hora en que acababa su ventana) y devuelve a quien cede: el turno debe acabar ya. [] = sigue.
    Lo lanzado a mano ("Lanzar ya") no cede: Damian lo quiere ahora."""
    ahora = ahora or datetime.now()
    if manual:
        return []
    with bloqueo(CANDADO):
        est = estado()
        cfg = turnos.cargar()
        t = turnos.buscar(turno_id, cfg)
        prio = PRIORIDAD.get((t or {}).get("plantilla"), PRIORIDAD_DEFECTO)
        c = [x for x in est.get("cola") or [] if _vigente(x, ahora)]
        frenos: dict = {}
        delante = [x["turno"] for x in c if x["turno"] != turno_id and _por_delante(x, prio, cfg, ahora, frenos)]
        if not delante:
            return []
        if fin - ahora >= timedelta(minutes=MIN_RESTO) and not any(x["turno"] == turno_id for x in c):
            c.append({"turno": turno_id, "manual": False, "pedido": _iso(ahora), "cedido": True, "fin": _iso(fin)})
        est["cola"] = c
        est.setdefault("cedidos", []).append({"cuando": _iso(ahora), "turno": turno_id, "a": delante,
                                              "fin": _iso(fin)})
        est["cedidos"] = est["cedidos"][-30:]
        _escribir(ESTADO, est)
    return delante


def minutos_hasta(fin: str | None, max_minutos: int, ahora: datetime | None = None) -> int:
    """Tope de un turno que vuelve tras ceder: lo que le quedaba de su ventana, nunca mas que su max_minutos."""
    if not fin:
        return max_minutos
    resto = (datetime.fromisoformat(fin) - (ahora or datetime.now())).total_seconds() / 60
    return max(1, min(max_minutos, int(resto)))


def tick(ahora: datetime | None = None, lanzar=None) -> dict:
    """Una pasada: encola lo que toca y, si no hay nada en marcha, lanza el primero listo. Devuelve lo hecho."""
    from nucleo import parada
    ahora = ahora or datetime.now()
    lanzar = lanzar or lanzar_proceso
    hecho = {"encolados": [], "lanzado": None, "motivo": "", "saltados": [], "forzado": None, "frenados": []}
    with bloqueo(CANDADO):
        est = estado()
        ultimo = datetime.fromisoformat(est["ultimo_tick"]) if est.get("ultimo_tick") else ahora
        desde = max(ultimo, ahora - GRACIA)
        c = [x for x in est.get("cola") or [] if _vigente(x, ahora)]
        saltos = est.setdefault("saltos", {})
        cfg = turnos.cargar()
        for t in cfg["turnos"]:
            if not t["activo"]:
                continue
            for cuando in ocurrencias(t, desde, ahora):
                if saltos.get(t["id"]) == _iso(cuando):       # "saltar solo la proxima": esta no, la siguiente si
                    saltos.pop(t["id"])
                    hecho["saltados"].append(t["id"])
                elif not any(x["turno"] == t["id"] and not x.get("cedido") for x in c):
                    # T1069: una hora nueva sustituye al resto de una ventana cedida (trae su ventana entera)
                    c[:] = [x for x in c if x["turno"] != t["id"]]
                    c.append({"turno": t["id"], "manual": False, "pedido": _iso(cuando)})
                    hecho["encolados"].append(t["id"])
        # un salto de una hora que ya paso (turno inactivo entonces, PC apagado...) no se queda colgado
        for tid, cuando in list(saltos.items()):
            if datetime.fromisoformat(cuando) < ahora - GRACIA:
                saltos.pop(tid)
        est["ultimo_tick"] = _iso(ahora)
        est["cola"] = c
        hecho["tope"] = _cerrar_por_tope()     # T1024: vivo pasado su tope + margen -> cierre suave y luego forzado
        hecho["forzado"] = _forzar_si_toca()
        en_marcha()              # T187: si el turno murio sin cerrar, deja su registro (push) y libera la cola
        hecho["latido"] = _vigilar_latido()
        hecho["progreso"] = _vigilar_progreso()
        try:                     # T708: log enorme o disco casi lleno -> aviso; mirar nunca rompe el tick
            from nucleo import vigia_disco
            hecho["disco"] = vigia_disco.revisar()
        except Exception:
            hecho["disco"] = None
        try:                     # 05/10: repaso de responsables (cada hora; solo lectura de tareas, aviso en el Centro)
            from nucleo import responsables
            hecho["responsables"] = responsables.repaso_si_toca(ahora)
        except Exception:
            hecho["responsables"] = None
        try:                     # 11/10: cierre automatico de lo ya hecho (una vez al dia, en un proceso aparte)
            from nucleo import cierre_auto
            hecho["cierre_auto"] = cierre_auto.repaso_si_toca(ahora)
        except Exception:
            hecho["cierre_auto"] = None
        try:                     # T890 (OK de Damian 16/10): espejo de GitHub, una vez al dia desde las 03:00, sin PARADA
            from nucleo import espejo
            hecho["espejo"] = espejo.repaso_si_toca(ahora)
        except Exception:
            hecho["espejo"] = None
        try:                     # T1020: guardian de aprobaciones (barrido cada minuto; tribunal y Qwen en un proceso aparte)
            from nucleo import guardian
            hecho["guardian"] = guardian.barrido_si_toca()
        except Exception:
            hecho["guardian"] = None
        try:                     # T837: aviso diario si hay tareas vivas > 7 dias sin turno que las pueda coger
            from nucleo import enrutado
            hecho["sin_turno"] = enrutado.avisar_sin_turno(ahora)
        except Exception:
            hecho["sin_turno"] = None
        hecho["trabajo"] = _tanda_de_trabajo(est, c, ahora, cfg)
        listas = sorted((x for x in c if _lista(x, ahora)), key=lambda x: _orden_cola(x, cfg))
        # F0 (T666): con la cola de propuestas o de revisiones por encima del limite, los turnos que fabrican
        # propuestas no arrancan; salen de la cola y queda apuntado. "Lanzar ya" de Damian (manual) si pasa.
        frenar = None
        for x in list(listas):
            t = turnos.buscar(x["turno"], cfg)
            if x.get("manual") or t is None or t.get("plantilla") not in freno.GENERADORAS:
                continue
            if frenar is None:
                frenar = freno.puede_generar(t["plantilla"])
            if not frenar[0]:
                listas.remove(x)
                c.remove(x)
                hecho["frenados"].append(x["turno"])
                est.setdefault("frenados", []).append({"cuando": _iso(ahora), "turno": x["turno"],
                                                       "motivo": frenar[1]})
                est["frenados"] = est["frenados"][-20:]
        if hecho["frenados"]:
            hecho["motivo"] = frenar[1]
        if not listas:
            pass
        elif en_marcha():
            hecho["motivo"] = "hay un turno en marcha: el siguiente espera"
        elif parada.activa():
            hecho["motivo"] = "PARADA puesta: la cola espera"
        elif turnos.desactivados() and not listas[0].get("manual"):
            hecho["motivo"] = "turnos desactivados"
            est["cola"] = [x for x in c if x.get("manual")]   # lo programado no se acumula mientras esten apagados
        else:
            entrada = listas[0]
            c.remove(entrada)
            t = turnos.buscar(entrada["turno"], cfg)
            if t is None:
                hecho["motivo"] = f"el turno {entrada['turno']} ya no existe"
            else:
                _escribir(EN_MARCHA, {"turno": t["id"], "nombre": t["nombre"], "manual": entrada.get("manual", False),
                                      "pedido": entrada["pedido"], "lanzado": time.time(), "paso": "arrancando",
                                      "max_minutos": minutos_hasta(entrada.get("fin"), t["max_minutos"], ahora)})
                try:
                    pid = lanzar(entrada)
                except Exception as e:
                    terminar()
                    hecho["motivo"] = f"no se pudo lanzar: {type(e).__name__}: {e}"[:200]
                    est.setdefault("errores", []).append({"cuando": _iso(ahora), "turno": t["id"],
                                                          "error": hecho["motivo"]})
                    est["errores"] = est["errores"][-20:]
                else:
                    progreso(pid=pid)
                    hecho["lanzado"] = t["id"]
                    est.setdefault("disparos", {})[t["id"]] = _iso(ahora)
        _escribir(ESTADO, est)
    return hecho


# ------------------------------------------------------------------ control individual (Damian 28/09)
FORZAR_TRAS = 180            # s: si tras "parar" el turno sigue vivo, se cierra por su PID exacto


def _linea_de_comando(pid: int) -> str:
    """Linea de comando real del proceso (para no matar nunca un PID reutilizado por otro programa)."""
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"],
                       capture_output=True, text=True, timeout=30,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return (r.stdout or "").strip()


def _matar(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"], capture_output=True, timeout=30,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _procesos() -> list[dict]:
    """Todos los procesos (pid, padre, nombre, linea, creado) en UNA consulta. Solo lee."""
    orden = ("Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine,"
             "@{n='Creado';e={if($_.CreationDate){$_.CreationDate.ToString('o')}else{''}}} | ConvertTo-Json -Compress")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", orden], capture_output=True,
                       text=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    datos = json.loads(r.stdout or "[]")
    datos = datos if isinstance(datos, list) else [datos]
    return [{"pid": int(p.get("ProcessId") or 0), "padre": int(p.get("ParentProcessId") or 0),
             "nombre": p.get("Name") or "", "linea": p.get("CommandLine") or "", "creado": p.get("Creado") or ""}
            for p in datos]


# T1024: hijos que un turno lanza a proposito. Uno que no encaje aqui no se mata: se para y se avisa a Damian.
HIJOS_CONOCIDOS = ("conhost.exe", "git.exe")


def _hijo_reconocido(p: dict) -> bool:
    """Programa de NEXO (su linea o su ruta en el repo: el python del .venv, pytest, scripts), git, la consola que
    Windows cuelga de cada programa de consola, o el Chrome de NEXO (el unico que se abre con puerto de depuracion)."""
    linea = (p.get("linea") or "").replace("/", "\\").lower()
    nombre = (p.get("nombre") or "").lower()
    return (str(RAIZ).lower() in linea or nombre in HIJOS_CONOCIDOS
            or (nombre == "chrome.exe" and "--remote-debugging-port=" in linea))


def _hijos(pid: int, procesos: list[dict] | None = None) -> list[dict]:
    """Descendientes vivos de `pid` (hijos, nietos...) con su linea de comando y si se reconocen. Un proceso solo
    cuenta como hijo si nacio despues que su padre (Windows reutiliza PIDs: un huerfano viejo no es de este turno).
    Lo que cuelga de un hijo reconocido es suyo (las piezas de Chrome, el git que lanza git...)."""
    procesos = _procesos() if procesos is None else procesos
    por_pid = {p["pid"]: p for p in procesos}
    salida, pendientes = [], [(pid, False)]
    while pendientes:
        padre, de_reconocido = pendientes.pop()
        nacio = (por_pid.get(padre) or {}).get("creado") or ""
        for p in procesos:
            if p["padre"] != padre or p["pid"] in (padre, pid) or (nacio and p.get("creado") and p["creado"] < nacio):
                continue
            reconocido = de_reconocido or _hijo_reconocido(p)
            salida.append(dict(p, reconocido=reconocido))
            pendientes.append((p["pid"], reconocido))
    return salida


FORZAR_REINTENTO = 600       # s entre intentos de cierre forzado que no han podido (aviso solo la primera vez)


def _no_se_pudo_cerrar(d: dict, pid: int, motivo: str) -> str:
    """El turno sigue vivo y no se puede cerrar solo: aviso en el Centro (una vez por turno) y el registro sigue en
    turno_en_marcha.json (la cola espera: nunca dos turnos a la vez ni uno vivo sin registro)."""
    from nucleo import avisos
    avisos.emitir("turno_sin_cerrar", f"Turno {d.get('nombre') or d.get('turno')} sin cerrar",
                  f"El turno (pid {pid}) tenia que cerrarse ({d.get('parar_motivo') or 'Parar'}) y no se ha podido: "
                  f"{motivo}. La cola espera. Mira /turnos.", ruta="/turnos", clave=f"sin_cerrar:{d.get('lanzado')}")
    _anotar({"forzar_fallido": time.time(), "forzar_error": motivo}, False)
    return f"no se pudo cerrar el pid {pid}: {motivo}"


def _cerrar_por_tope(ahora_s: float | None = None) -> str | None:
    """T1024: turno vivo pasado su max_minutos + MARGEN_TOPE: se le pide que acabe (cierre suave, como "Parar") y,
    si no obedece en FORZAR_TRAS s, _forzar_si_toca lo cierra por su PID exacto."""
    d = _leer(EN_MARCHA, {})
    if not d or d.get("parar_pedido") or not _pid(d):
        return None
    ahora_s = ahora_s or time.time()
    minutos = float(d.get("max_minutos") or turnos.MAX_MINUTOS)
    if ahora_s - float(d.get("lanzado") or ahora_s) < minutos * 60 + MARGEN_TOPE or not _vivo(_pid(d)):
        return None
    motivo = f"paso su tope de {round(minutos)} min (+{MARGEN_TOPE // 60} de margen)"
    from nucleo import parada
    parada.pedir_cierre(motivo)
    progreso(parar_pedido=ahora_s, parar_motivo=motivo, paso="parando")
    return motivo


MARGEN_TOPE = 15 * 60        # s despues de su max_minutos que se le dan a un turno antes de pedirle que acabe


def _forzar_si_toca() -> str | None:
    """Si se pidio parar y el turno sigue vivo pasado FORZAR_TRAS, se cierra por PID EXACTO tras comprobar que
    su linea de comando es la de ese turno (regla de Damian 25/09: nunca por nombre ni patron). T1024: antes de
    usar /T lista a todos sus hijos; si hay uno que no reconoce, no mata nada y avisa. Deja registro."""
    d = _leer(EN_MARCHA, {})
    pedido = float(d.get("parar_pedido") or 0)
    pid = _pid(d)
    if not pedido or time.time() - pedido < FORZAR_TRAS or not _vivo(pid):
        return None
    if time.time() - float(d.get("forzar_fallido") or 0) < FORZAR_REINTENTO:
        return None
    try:
        linea = _linea_de_comando(pid)
    except Exception as e:  # noqa: BLE001
        return _no_se_pudo_cerrar(d, pid, f"no se pudo leer su linea de comando ({type(e).__name__})")
    if "turno_nexo.py" not in linea or f"--turno={d.get('turno')}" not in linea:
        _registrar_muerte(d)   # el turno original ya no existe: que quede su registro
        terminar()   # el PID ya es de otro programa: no se toca
        return f"pid {pid} ya no es el turno: no se toca"
    try:
        hijos = _hijos(pid)
    except Exception as e:  # noqa: BLE001
        return _no_se_pudo_cerrar(d, pid, f"no se pudieron listar sus hijos ({type(e).__name__})")
    raros = [h for h in hijos if not h["reconocido"]]
    if raros:
        return _no_se_pudo_cerrar(d, pid, "tiene hijos que no reconozco: " + "; ".join(
            f"pid {h['pid']} {h['nombre']} ({(h['linea'] or '?')[:120]})" for h in raros[:3]))
    _matar(pid)
    if _vivo(pid):
        return _no_se_pudo_cerrar(d, pid, "taskkill no lo ha cerrado")
    candado = RAIZ / "memoria" / ".candado_turno_nexo.lock"   # el de turno_nexo: si no, el siguiente no arranca
    try:
        if candado.read_text(encoding="utf-8").split()[0] == str(pid):
            candado.unlink()
    except (OSError, IndexError):
        pass
    from nucleo import parada, registro
    parada.limpiar_cierre()
    registro.CARPETA.mkdir(parents=True, exist_ok=True)
    reg = {"inicio": d.get("inicio") or "", "turno_id": d.get("turno"), "nombre_turno": d.get("nombre"),
           "manual": d.get("manual"), "abortado": f"{d.get('parar_motivo') or 'parado por Damian'} (cerrado a la fuerza tras {FORZAR_TRAS} s)",
           "hijos_cerrados": [{k: h[k] for k in ("pid", "nombre", "linea")} for h in hijos],
           "pasos": {}, "aviso_push": False}
    escribir_atomico(registro.CARPETA / f"turno_nexo_{datetime.now():%Y%m%d_%H%M%S}.json",
                     json.dumps(reg, ensure_ascii=False, indent=1))
    terminar()
    return f"{d.get('nombre')} cerrado (pid {pid})"


def parar(motivo: str = "parado por Damian", anotar: bool = True) -> dict:
    """Pide al turno en marcha que acabe YA: termina la llamada en curso y no empieza nada (cierre suave, sin
    PARADA general). Si no obedece en FORZAR_TRAS s, el siguiente tick lo cierra por su PID exacto."""
    from nucleo import parada
    m = en_marcha()
    if not m:
        raise turnos.ConfigInvalida("no hay ningun turno en marcha")
    parada.pedir_cierre(motivo)
    progreso(parar_pedido=time.time(), parar_motivo=motivo, paso="parando")
    if anotar:
        _anotar_parado(m)   # para poder "Reanudar ahora"
    return m


def quitar(turno_id: str) -> dict:
    with bloqueo(CANDADO):
        est = estado()
        c = est.get("cola") or []
        x = next((e for e in c if e["turno"] == turno_id), None)
        if x is None:
            raise turnos.ConfigInvalida("ese turno no esta en la cola")
        c.remove(x)
        _escribir(ESTADO, est)
        return x


def hasta(opcion: str, hora: str = "", base: datetime | None = None, ahora: datetime | None = None) -> datetime:
    """15m | 1h | manana (a la misma hora que estaba pedido, al dia siguiente) | hora (HH:MM: hoy si no ha
    pasado, si no manana)."""
    ahora = ahora or datetime.now()
    if opcion == "15m":
        return ahora + timedelta(minutes=15)
    if opcion == "1h":
        return ahora + timedelta(hours=1)
    if opcion == "manana":
        return datetime.combine(ahora.date() + timedelta(days=1), (base or ahora).time().replace(microsecond=0))
    if opcion == "hora":
        h = turnos.validar_horas([hora])[0]
        destino = datetime.combine(ahora.date(), datetime.strptime(h, "%H:%M").time())
        return destino if destino > ahora else destino + timedelta(days=1)
    raise turnos.ConfigInvalida("opcion de posponer desconocida")


def posponer(turno_id: str, opcion: str, hora: str = "", ahora: datetime | None = None) -> datetime:
    """Pospone un turno de la cola (o el que esta en marcha: lo para y lo vuelve a poner en la cola)."""
    ahora = ahora or datetime.now()
    m = en_marcha()
    if m and m.get("turno") == turno_id:
        pedido = m.get("pedido") or _iso(ahora)
        cuando = hasta(opcion, hora, datetime.fromisoformat(pedido), ahora)
        parar("pospuesto por Damian", anotar=False)   # vuelve a la cola: no es un parado
        with bloqueo(CANDADO):
            est = estado()
            est.setdefault("cola", []).append({"turno": turno_id, "manual": True, "pedido": pedido,
                                               "no_antes": _iso(cuando)})
            _escribir(ESTADO, est)
        return cuando
    with bloqueo(CANDADO):
        est = estado()
        x = next((e for e in est.get("cola") or [] if e["turno"] == turno_id), None)
        if x is None:
            raise turnos.ConfigInvalida("ese turno no esta ni en marcha ni en la cola")
        cuando = hasta(opcion, hora, datetime.fromisoformat(x["pedido"]), ahora)
        x["no_antes"] = _iso(cuando)
        _escribir(ESTADO, est)
    return cuando


def mover(turno_id: str, hacia: str) -> list[dict]:
    """Reordena la cola: 'arriba', 'abajo' o 'primero' (pasar el primero). Devuelve la cola nueva."""
    with bloqueo(CANDADO):
        est = estado()
        c = est.get("cola") or []
        i = next((n for n, e in enumerate(c) if e["turno"] == turno_id), None)
        if i is None:
            raise turnos.ConfigInvalida("ese turno no esta en la cola")
        destino = {"arriba": max(0, i - 1), "abajo": min(len(c) - 1, i + 1), "primero": 0}.get(hacia)
        if destino is None:
            raise turnos.ConfigInvalida("movimiento desconocido")
        c.insert(destino, c.pop(i))
        est["cola"] = c
        _escribir(ESTADO, est)
        return c


def reanudar(turno_id: str, ahora: datetime | None = None) -> str:
    """"Reanudar ahora": un pospuesto deja de esperar y pasa el primero; un parado vuelve a la cola el primero."""
    ahora = ahora or datetime.now()
    with bloqueo(CANDADO):
        est = estado()
        c = est.setdefault("cola", [])
        x = next((e for e in c if e["turno"] == turno_id), None)
        parados = est.setdefault("parados", [])
        era_parado = any(p["turno"] == turno_id for p in parados)
        est["parados"] = [p for p in parados if p["turno"] != turno_id]
        if x is not None:
            x.pop("no_antes", None)
            c.remove(x)
        elif era_parado:
            if not turnos.buscar(turno_id):
                raise turnos.ConfigInvalida("ese turno ya no existe")
            x = {"turno": turno_id, "manual": True, "pedido": _iso(ahora)}
        else:
            raise turnos.ConfigInvalida("ese turno no esta pospuesto ni parado")
        c.insert(0, x)
        _escribir(ESTADO, est)
    return "parado" if era_parado else "pospuesto"


def descartar_parado(turno_id: str) -> None:
    with bloqueo(CANDADO):
        est = estado()
        est["parados"] = [p for p in est.get("parados") or [] if p["turno"] != turno_id]
        _escribir(ESTADO, est)


def _anotar_parado(m: dict) -> None:
    with bloqueo(CANDADO):
        est = estado()
        p = [x for x in est.get("parados") or [] if x["turno"] != m.get("turno")]
        p.append({"turno": m.get("turno"), "nombre": m.get("nombre"), "cuando": _iso(datetime.now())})
        est["parados"] = p[-10:]
        _escribir(ESTADO, est)


def saltar_proxima(turno_id: str, ahora: datetime | None = None) -> datetime:
    t = turnos.buscar(turno_id)
    if not t:
        raise turnos.ConfigInvalida("ese turno ya no existe")
    prox = proxima(t, ahora)
    if prox is None:
        raise turnos.ConfigInvalida("ese turno no tiene proxima ejecucion")
    with bloqueo(CANDADO):
        est = estado()
        est.setdefault("saltos", {})[turno_id] = _iso(prox)
        _escribir(ESTADO, est)
    return prox


def deshacer_salto(turno_id: str) -> None:
    with bloqueo(CANDADO):
        est = estado()
        (est.get("saltos") or {}).pop(turno_id, None)
        _escribir(ESTADO, est)


def proxima_efectiva(turno: dict, ahora: datetime | None = None) -> tuple[datetime | None, datetime | None]:
    """(la que se ejecutara, la que se salta o None)."""
    ahora = ahora or datetime.now()
    salto = (estado().get("saltos") or {}).get(turno["id"])
    siguientes = ocurrencias(turno, ahora, ahora + timedelta(days=15))
    if salto and siguientes and _iso(siguientes[0]) == salto:
        return (siguientes[1] if len(siguientes) > 1 else None), siguientes[0]
    return (siguientes[0] if siguientes else None), None


def en_curso(ahora: datetime | None = None) -> dict:
    """Para las listas EN MARCHA y EN COLA (Turnos y Centro)."""
    ahora = ahora or datetime.now()
    nombres = {t["id"]: t["nombre"] for t in turnos.cargar()["turnos"]}
    m = en_marcha()
    if m:
        seg = int(time.time() - float(m.get("lanzado") or time.time()))
        m = dict(m, transcurrido=f"{seg // 60} min {seg % 60:02d} s", parando=bool(m.get("parar_pedido")))
    c = []
    for i, x in enumerate(cola(), 1):
        no_antes = datetime.fromisoformat(x["no_antes"]) if x.get("no_antes") else None
        c.append({"turno": x["turno"], "nombre": nombres.get(x["turno"], x["turno"]), "manual": x.get("manual"),
                  "pedido": fecha_corta(datetime.fromisoformat(x["pedido"])),
                  "pospuesto": fecha_corta(no_antes) if no_antes and no_antes > ahora else "", "pos": i})
    limite = ahora - timedelta(hours=12)
    parados = [dict(p, cuando_txt=fecha_corta(datetime.fromisoformat(p["cuando"])))
               for p in estado().get("parados") or [] if datetime.fromisoformat(p["cuando"]) > limite
               and not (m and m.get("turno") == p["turno"]) and all(x["turno"] != p["turno"] for x in c)]
    return {"marcha": m, "cola": c, "parados": parados, "desactivados": turnos.desactivados()}


# ------------------------------------------------------------------ lecturas para la web
def ultimo_registro(turno_id: str | None = None, carpeta: Path | None = None, ruidoso: bool = False) -> dict | None:
    """El ultimo registros/turno_nexo_*.json (de ese turno, si se pide). ruidoso=True salta los silenciosos (un
    turno del tribunal que no cambio nada): el Centro no los ensena."""
    from nucleo import registro
    for p in sorted((carpeta or registro.CARPETA).glob("turno_nexo_*.json"), reverse=True)[:80]:
        d = _leer(p, {})
        if ruidoso and d.get("silencioso"):
            continue
        if turno_id is None or d.get("turno_id") == turno_id:
            return dict(d, archivo=p.name)
    return None


def texto_tribunal(paso: dict) -> str:
    """Lo que hizo un turno del tribunal (noche 05/10: antes salia siempre '0 tarea(s), 0 propuesta(s)')."""
    if paso.get("simulado"):
        return f"simulado: {paso.get('candidatas', 0)} expediente(s) con trabajo"
    hechos = paso.get("hechos") or []
    fases = [h.get("fase") for h in hechos]
    rec = (paso.get("sincronizado") or {}).get("reconsiderar") or {}
    partes = [f"{n} {t}" for n, t in ((fases.count("resuelto"), "resuelto(s)"),
                                      (fases.count("damian"), "a tu bandeja"),
                                      (len(paso.get("a_claude") or []), "a la de Claude"),
                                      (fases.count("apelacion"), "en apelacion"),
                                      (fases.count("espera"), "esperando revisores")) if n]
    if rec.get("encolados"):
        partes.append(f"{len(rec['encolados'])} lote(s) de reconsideracion encolados")
    if rec.get("sueltas"):
        partes.append(f"{len(rec['sueltas'])} propuesta(s) reabiertas tras el freno")
    if not partes or (fases and all(f == "espera" for f in fases) and len(partes) == 1):
        return "tribunal sin cambios" + (f" ({fases.count('espera')} esperando revisores)" if fases else "")
    return "tribunal: " + ", ".join(partes)


def resultado_corto(reg: dict | None) -> str:
    if not reg:
        return "todavia no se ha ejecutado"
    ini = reg.get("inicio") or ""
    cuando = f"{ini[8:10]}/{ini[5:7]} {ini[11:16]}" if len(ini) >= 16 else ini
    if reg.get("abortado"):
        return f"{cuando}: no hizo nada: {(reg.get('explicacion') or reg['abortado'])[:160]}"
    filas = (reg.get("pasos", {}).get("trabajo") or {}).get("filas", [])
    props = sum(len(f.get("propuestas") or []) for f in filas)
    errores = [k for k, v in (reg.get("pasos") or {}).items() if isinstance(v, dict) and v.get("error")]
    sl = reg.get("solo_lectura") or {}
    trib = (reg.get("pasos") or {}).get("tribunal")
    if isinstance(trib, dict) and not trib.get("error"):
        return f"{cuando}: " + texto_tribunal(trib)
    return (f"{cuando}: {len(filas)} tarea(s), {props} propuesta(s)"
            + (f", error en {', '.join(errores)}" if errores else "")
            + (" · SOLO LECTURA VIOLADA" if sl and not sl.get("ok") else "")
            + (f" · parado a mano ({reg['parado']})" if reg.get("parado") else "")
            + (f" · {reg['explicacion']}" if reg.get("explicacion") else ""))


def resumen_centro(ahora: datetime | None = None) -> dict:
    """Para el bloque "Turnos" del Centro: en marcha (paso, tiempo, tarea), cola, proximo y ultimo resultado."""
    ahora = ahora or datetime.now()
    cfg = turnos.cargar()
    marcha = en_marcha()
    if marcha:
        seg = int(time.time() - float(marcha.get("lanzado") or time.time()))
        marcha = dict(marcha, transcurrido=f"{seg // 60} min {seg % 60:02d} s")
    nombres = {t["id"]: t["nombre"] for t in cfg["turnos"]}
    proximos = [(proxima(t, ahora), t["nombre"]) for t in cfg["turnos"] if t["activo"]]
    proximos = sorted((p, n) for p, n in proximos if p)
    ult = ultimo_registro(ruidoso=True)
    return {**en_curso(ahora),
            "proximo": {"nombre": proximos[0][1], "cuando": fecha_corta(proximos[0][0])} if proximos else None,
            "ultimo": {"nombre": (ult or {}).get("nombre_turno") or (ult or {}).get("nombre_plantilla") or "turno",
                       "texto": resultado_corto(ult)} if ult else None,
            "desactivados": turnos.desactivados()}
