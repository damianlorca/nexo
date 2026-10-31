# -*- coding: utf-8 -*-
"""Turnos desde la web (T231, rediseno 28/09): TABLA de turnos con alta, edicion, duplicar, borrar (archivar),
activo/inactivo y "Lanzar ya"; interruptor general; textos de las plantillas; resumen de los ultimos turnos.

Todo pasa por nucleo.turnos (la tabla) y nucleo.planificador (cola, proxima ejecucion, choques, en marcha).
Cada POST devuelve la tabla releida del disco (sin optimistic update). "Lanzar ya" encola: si hay otro turno
en marcha, espera; nunca corren dos a la vez. Son `def`: FastAPI las corre en el threadpool.
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request

from interfaz.lecturas import estado_parada
from interfaz.vistas import pintar, pintar_panel
from nucleo import planificador, registro, turnos

router = APIRouter()

N_TURNOS = 10
NOMBRES_DIAS = {"lunes": "L", "martes": "M", "miercoles": "X", "jueves": "J", "viernes": "V", "sabado": "S",
                "domingo": "D"}


def _dias_texto(dias: list[str]) -> str:
    if len(dias) == 7:
        return "todos los días"
    if dias == list(turnos.DIAS[:5]):
        return "de lunes a viernes"
    return " ".join(NOMBRES_DIAS[d] for d in dias)


def tabla() -> dict:
    """Lo que pinta la tabla: cada turno con proxima ejecucion, ultimo resultado, estado y choques."""
    cfg = turnos.cargar()
    choques = planificador.choques(cfg)
    marcha = planificador.en_marcha()
    en_cola = [x["turno"] for x in planificador.cola()]
    filas = []
    for t in cfg["turnos"]:
        prox, saltada = planificador.proxima_efectiva(t) if t["activo"] else (None, None)
        filas.append(dict(
            t, dias_texto=_dias_texto(t["dias"]), proxima=planificador.fecha_corta(prox) if prox else "—",
            saltada=planificador.fecha_corta(saltada) if saltada else "",
            instrucciones_texto=(f"Personalizadas: {t['instrucciones'][:90]}" if t["instrucciones"]
                                 else turnos.PLANTILLAS[t["plantilla"]]["nombre"]),
            plantilla_nombre=turnos.PLANTILLAS[t["plantilla"]]["nombre"],
            ultimo=planificador.resultado_corto(planificador.ultimo_registro(t["id"])),
            en_marcha=bool(marcha and marcha.get("turno") == t["id"]),
            en_cola=(en_cola.index(t["id"]) + 1) if t["id"] in en_cola else 0,
            choca=choques.get(t["id"], [])))
    est = planificador.estado()
    return {"filas": filas, "desactivados": turnos.desactivados(), "parada": estado_parada(),
            "marcha": marcha, "errores": (est.get("errores") or [])[-3:], "trabajo": _trabajo(est, cfg)}


def _trabajo(est: dict, cfg: dict) -> dict:
    """Modo 'Trabajar ahora' y lo ultimo que se encolo (con el motivo de lo que no)."""
    nombre = {t["id"]: t["nombre"] for t in cfg["turnos"]}
    u = est.get("ultimo_trabajo") or {}
    modo = est.get("trabajo") or {}
    return {"hasta": (modo.get("hasta") or "").replace("T", " ")[11:16], "activo": bool(modo),
            "cuando": (u.get("cuando") or "").replace("T", " ")[:16], "fin": u.get("fin", ""),
            "encolados": [nombre.get(i, i) for i in u.get("encolados") or []],
            "saltados": [{"turno": nombre.get(x["turno"], x["turno"]), "motivo": x["motivo"]}
                         for x in u.get("saltados") or []]}


def _pintar_tabla(request: Request, aviso: str = "", error: str = "", limpiar_form: bool = False):
    return pintar(request, "_turnos_tabla.html", **tabla(), aviso=aviso, error=error, limpiar_form=limpiar_form)


def _form(turno: dict | None = None, error: str = "") -> dict:
    vacio = {"id": "", "nombre": "", "plantilla": turnos.PLANTILLA_DEFECTO, "instrucciones": "", "tareas": [],
             "dias": list(turnos.DIAS), "horas": ["03:30"], "max_tareas": 2, "max_minutos": turnos.MINUTOS_DEFECTO,
             "avisar": True, "activo": True}
    return {"t": turno or vacio, "plantillas": turnos.plantillas(), "dias": turnos.DIAS,
            "max_tareas": turnos.MAX_TAREAS, "min_minutos": turnos.MIN_MINUTOS, "max_minutos": turnos.MAX_MINUTOS,
            "max_texto": turnos.MAX_TEXTO, "error": error}


@router.get("/turnos")
def pagina(request: Request):
    return pintar(request, "turnos.html", plantillas=turnos.plantillas(), max_texto=turnos.MAX_TEXTO)


@router.get("/turnos/tabla")
def panel_tabla(request: Request):
    return pintar_panel(request, "_turnos_tabla.html", "/turnos/tabla",
                        lambda: dict(tabla(), aviso="", error="", limpiar_form=False))


@router.get("/turnos/nuevo")
def form_nuevo(request: Request):
    return pintar(request, "_turno_form.html", **_form())


@router.get("/turnos/{turno_id}/editar")
def form_editar(request: Request, turno_id: str):
    t = turnos.buscar(turno_id)
    if not t:
        return _pintar_tabla(request, error="Ese turno ya no existe.")
    return pintar(request, "_turno_form.html", **_form(t))


@router.post("/turnos/guardar")
def guardar(request: Request, id: str = Form(""), nombre: str = Form(""), plantilla: str = Form(""),
            instrucciones: str = Form(""), tareas: str = Form(""), dias: list[str] = Form([]), horas: str = Form(""),
            max_tareas: str = Form("2"), max_minutos: str = Form(str(turnos.MINUTOS_DEFECTO)),
            avisar: str = Form(""), activo: str = Form("")):
    datos = {"id": id, "nombre": nombre, "plantilla": plantilla, "instrucciones": instrucciones, "tareas": tareas,
             "dias": dias, "horas": horas, "max_tareas": max_tareas, "max_minutos": max_minutos,
             "avisar": avisar == "si", "activo": activo == "si"}
    try:
        if id and not turnos.buscar(id):
            raise turnos.ConfigInvalida("ese turno ya no existe")
        t = turnos.guardar_turno(datos)
    except turnos.ConfigInvalida as e:
        r = pintar(request, "_turno_form.html", **_form(dict(datos, horas=horas.split(","),
                                                            tareas=tareas.split(",") if tareas else []), str(e)))
        r.headers["HX-Retarget"], r.headers["HX-Reswap"] = "#turno-form", "innerHTML"   # el error, en el formulario
        return r
    return _pintar_tabla(request, aviso=f"Turno «{t['nombre']}» guardado.", limpiar_form=True)


@router.get("/turnos/cerrar-form")
def cerrar_form():
    from fastapi.responses import HTMLResponse
    return HTMLResponse("")


@router.post("/turnos/{turno_id}/duplicar")
def duplicar(request: Request, turno_id: str):
    try:
        t = turnos.duplicar(turno_id)
    except turnos.ConfigInvalida as e:
        return _pintar_tabla(request, error=str(e))
    return _pintar_tabla(request, aviso=f"Duplicado como «{t['nombre']}» (nace INACTIVO: revísalo y actívalo).")


@router.post("/turnos/{turno_id}/borrar")
def borrar(request: Request, turno_id: str):
    try:
        t = turnos.archivar(turno_id)
    except turnos.ConfigInvalida as e:
        return _pintar_tabla(request, error=str(e))
    return _pintar_tabla(request, aviso=f"Turno «{t['nombre']}» quitado de la tabla (queda archivado).")


@router.post("/turnos/{turno_id}/activo")
def activo(request: Request, turno_id: str, valor: str = Form("")):
    try:
        t = turnos.poner_activo(turno_id, valor == "si")
    except turnos.ConfigInvalida as e:
        return _pintar_tabla(request, error=str(e))
    return _pintar_tabla(request, aviso=f"«{t['nombre']}» {'ACTIVO' if t['activo'] else 'INACTIVO'}.")


@router.post("/turnos/{turno_id}/lanzar")
def lanzar(request: Request, turno_id: str):
    if estado_parada()["activa"]:
        return _pintar_tabla(request, error="La PARADA está puesta: el turno no arrancaría. Quítala antes.")
    if turnos.desactivados():
        return _pintar_tabla(request, error="Los turnos están desactivados (interruptor general): actívalos antes.")
    t = turnos.buscar(turno_id)
    if t:
        from nucleo import plantillas_turno
        ctx = turnos.contexto(t, manual=True)
        try:
            vacio = plantillas_turno.candidatas(ctx) == 0
        except Exception:
            vacio = False   # la comprobacion nunca impide lanzar
        if vacio:
            return _pintar_tabla(request, error=f"«{t['nombre']}» no haría nada ahora: "
                                               f"{plantillas_turno.por_que_nada(ctx)}. No se ha lanzado.")
    try:
        planificador.encolar(turno_id, manual=True)
        hecho = planificador.tick()
    except turnos.ConfigInvalida as e:
        return _pintar_tabla(request, error=str(e))
    except Exception as e:
        return _pintar_tabla(request, error=f"No se pudo lanzar: {str(e)[:200]}")
    t = turnos.buscar(turno_id)
    if hecho.get("lanzado") == turno_id:
        return _pintar_tabla(request, aviso=f"«{t['nombre']}» arrancado. Sigue su progreso en el Centro.")
    return _pintar_tabla(request, aviso=f"«{t['nombre']}» en cola: {hecho.get('motivo') or 'arrancará en cuanto pueda'}.")


@router.post("/turnos/trabajar")
def trabajar(request: Request, horas: str = Form("0")):
    """'Trabajar ahora': una pasada (0) o modo trabajo de 1, 2 o 3 horas. No se salta el freno F0."""
    if estado_parada()["activa"]:
        return _pintar_tabla(request, error="La PARADA está puesta: no se encola nada. Quítala antes.")
    if turnos.desactivados():
        return _pintar_tabla(request, error="Los turnos están desactivados (interruptor general): actívalos antes.")
    try:
        h = int(horas or 0)
        res = planificador.encolar_todos(h or None)
        hecho = planificador.tick()
    except (ValueError, turnos.ConfigInvalida):
        return _pintar_tabla(request, error="Horas no válidas (0, 1, 2 o 3).")
    except Exception as e:
        return _pintar_tabla(request, error=f"No se pudo encolar: {str(e)[:200]}")
    n = len(res["encolados"])
    texto = (f"{n} turno{'s' if n != 1 else ''} encolado{'s' if n != 1 else ''}" if n
             else "No hay trabajo para ningún turno ahora")
    if h and n:
        texto += f"; modo trabajo hasta las {res['hasta'].replace('T', ' ')[11:16]}"
    if hecho.get("lanzado"):
        texto += ". El primero ya ha arrancado"
    return _pintar_tabla(request, aviso=texto + ".")


@router.post("/turnos/trabajar/parar")
def dejar_de_trabajar(request: Request):
    habia = planificador.dejar_de_trabajar()
    return _pintar_tabla(request, aviso="Modo trabajo quitado: lo ya encolado o en marcha sigue." if habia
                         else "No había modo trabajo.")


@router.post("/turnos/interruptor")
def interruptor(request: Request, accion: str = Form(""), motivo: str = Form("")):
    if accion == "off":
        turnos.desactivar(motivo.strip()[:200] or "desactivados desde la web")
    elif accion == "on":
        turnos.activar()
    else:
        return _pintar_tabla(request, error="Acción desconocida.")
    return _pintar_tabla(request, aviso="Turnos DESACTIVADOS: no arrancará ninguno." if turnos.desactivados()
                         else "Turnos ACTIVADOS.")


@router.post("/turnos/texto")
def editar_texto(request: Request, plantilla: str = Form(""), texto: str = Form(""), restablecer: str = Form("")):
    try:
        turnos.editar_texto(plantilla, "" if restablecer else texto)
    except turnos.ConfigInvalida as e:
        return pintar(request, "_turnos_textos.html", plantillas=turnos.plantillas(), max_texto=turnos.MAX_TEXTO,
                      error=str(e))
    return pintar(request, "_turnos_textos.html", plantillas=turnos.plantillas(), max_texto=turnos.MAX_TEXTO,
                  aviso="Texto de fábrica restablecido." if restablecer else "Texto guardado.")


# ------------------------------------------------------------------ resumen
def _fila(f: dict) -> dict:
    return {"tarea": f.get("tarea", ""), "titulo": f.get("titulo", ""), "veredicto": f.get("veredicto") or
            ("simulado" if f.get("simulado") else "sin borrador"), "auditoria": f.get("auditoria", ""),
            "revision": f.get("revision_claude", ""), "propuestas": f.get("propuestas") or [],
            "error": next((i.get("error") for i in f.get("intentos", []) if i.get("error")), "")}


def ultimos_turnos(n: int = N_TURNOS) -> list[dict]:
    import json
    salida = []
    for p in sorted(registro.CARPETA.glob("turno_nexo_*.json"), reverse=True)[:n]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if d.get("silencioso"):   # noche 05/10: el tribunal sin cambios no hace ruido en la web
            continue
        pasos = d.get("pasos") or {}
        filas = [_fila(f) for f in (pasos.get("trabajo") or {}).get("filas", [])]
        errores = {k: str(v.get("error"))[:200] for k, v in pasos.items() if isinstance(v, dict) and v.get("error")}
        salida.append({"archivo": p.name, "inicio": (d.get("inicio") or "").replace("T", " ")[:16],
                       "plantilla": d.get("nombre_turno") or d.get("nombre_plantilla") or "Turno antiguo (sin plantilla)",
                       "manual": d.get("manual"), "simular": d.get("simular"), "abortado": d.get("abortado", ""),
                       "explicacion": d.get("explicacion", ""), "filas": filas, "errores": errores, "solo_lectura": d.get("solo_lectura"),
                       "instrucciones": d.get("instrucciones", ""), "propuestas": [x for f in filas for x in f["propuestas"]],
                       "tribunal": (planificador.texto_tribunal(pasos["tribunal"])
                                    if isinstance(pasos.get("tribunal"), dict) and not pasos["tribunal"].get("error") else "")})
    return salida


@router.get("/turnos/resumen")
def panel_resumen(request: Request):
    def leer():
        from nucleo import vigia
        return {"turnos": ultimos_turnos(), "vigia": vigia.resumen_semanal()}
    return pintar_panel(request, "_turnos_resumen.html", "/turnos/resumen", leer)


# ------------------------------------------------------------------ control individual (Damian 28/09)
def _hecho(request: Request, texto: str, error: bool = False):
    """Respuesta de una accion sobre un turno en marcha/en cola: mensaje visible (fuera de los paneles, que se
    refrescan) + evento para que TODAS las vistas abiertas (Turnos, Centro, movil) se relean del disco."""
    from fastapi.responses import HTMLResponse
    from html import escape
    request.app.state.bus.publicar("turno_estado", {})
    clase = "nota nota-bloqueo" if error else "nota nota-aviso"
    r = HTMLResponse(f'<p id="msg-turnos" hx-swap-oob="true" class="{clase}" role="{"alert" if error else "status"}">'
                     f"{escape(texto)}</p>")
    r.headers["HX-Trigger"] = "nexo:turno_estado"
    return r


@router.get("/turnos/en-curso")
def panel_en_curso(request: Request):
    return pintar_panel(request, "_turnos_en_curso.html", "/turnos/en-curso", planificador.en_curso)


@router.post("/turnos/marcha/parar")
def parar(request: Request):
    try:
        m = planificador.parar()
    except turnos.ConfigInvalida as e:
        return _hecho(request, str(e).capitalize() + ".", error=True)
    return _hecho(request, f"Parando «{m.get('nombre')}»: termina lo que tiene entre manos y no empieza nada más. "
                           f"Si en {planificador.FORZAR_TRAS // 60} min sigue, se cierra a la fuerza. La PARADA general no se toca.")


@router.post("/turnos/cola/{turno_id}/quitar")
def quitar(request: Request, turno_id: str):
    try:
        planificador.quitar(turno_id)
    except turnos.ConfigInvalida as e:
        return _hecho(request, str(e).capitalize() + ".", error=True)
    t = turnos.buscar(turno_id)
    return _hecho(request, f"«{t['nombre'] if t else turno_id}» quitado de la cola.")


@router.post("/turnos/{turno_id}/posponer")
def posponer(request: Request, turno_id: str, opcion: str = Form(""), hora: str = Form("")):
    try:
        cuando = planificador.posponer(turno_id, opcion, hora)
    except turnos.ConfigInvalida as e:
        return _hecho(request, str(e).capitalize() + ".", error=True)
    t = turnos.buscar(turno_id)
    return _hecho(request, f"«{t['nombre'] if t else turno_id}» pospuesto hasta {planificador.fecha_corta(cuando)}.")


@router.post("/turnos/{turno_id}/saltar")
def saltar(request: Request, turno_id: str, deshacer: str = Form("")):
    try:
        if deshacer:
            planificador.deshacer_salto(turno_id)
            texto = "Ya no se salta: la próxima ejecución vuelve a contar."
        else:
            cuando = planificador.saltar_proxima(turno_id)
            texto = f"Se saltará solo la del {planificador.fecha_corta(cuando)}; las siguientes, normal."
    except turnos.ConfigInvalida as e:
        return _pintar_tabla(request, error=str(e))
    return _pintar_tabla(request, aviso=texto)


@router.post("/turnos/cola/{turno_id}/mover")
def mover(request: Request, turno_id: str, hacia: str = Form("")):
    try:
        planificador.mover(turno_id, hacia)
    except turnos.ConfigInvalida as e:
        return _hecho(request, str(e).capitalize() + ".", error=True)
    t = turnos.buscar(turno_id)
    texto = {"primero": "pasa el primero", "arriba": "sube un puesto", "abajo": "baja un puesto"}[hacia]
    return _hecho(request, f"«{t['nombre'] if t else turno_id}» {texto} en la cola.")


@router.post("/turnos/{turno_id}/reanudar")
def reanudar(request: Request, turno_id: str):
    try:
        planificador.reanudar(turno_id)
        planificador.tick()
    except turnos.ConfigInvalida as e:
        return _hecho(request, str(e).capitalize() + ".", error=True)
    t = turnos.buscar(turno_id)
    m = planificador.en_marcha()
    if m and m.get("turno") == turno_id:
        return _hecho(request, f"«{t['nombre']}» reanudado: ya está en marcha.")
    return _hecho(request, f"«{t['nombre'] if t else turno_id}» reanudado: es el primero de la cola y arranca en cuanto "
                           "termine el que está en marcha.")


@router.post("/turnos/parados/{turno_id}/descartar")
def descartar(request: Request, turno_id: str):
    planificador.descartar_parado(turno_id)
    return _hecho(request, "Quitado de la lista de parados.")


@router.post("/turnos/reanudar-todos")
def reanudar_todos(request: Request):
    turnos.activar()
    return _hecho(request, "Turnos reanudados: los activos vuelven a arrancar a su hora.")
