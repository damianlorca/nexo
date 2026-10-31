# -*- coding: utf-8 -*-
"""Command Center (home): estado global, salud de proveedores, tareas por estado, ultimas acciones.

La pagina pinta el esqueleto y cada panel se carga aparte (hx-trigger="load") y se refresca con
los eventos SSE que le tocan (nexo:parada, nexo:tareas, nexo:log, nexo:reconciliar). Asi un panel
lento (proveedores) no retrasa los demas y cada uno tiene su propio estado loading/empty/error.
Los paneles son `def`: FastAPI los corre en el threadpool (leen disco o hacen sondeos locales).
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import Response

from interfaz import lecturas, presentar
from interfaz.vistas import pintar, pintar_panel
from nucleo import parada

router = APIRouter()


@router.get("/")
def centro(request: Request):
    """Centro v2 (T230, aprobado 18/10): saludo, frase de estado y ultima visita; Te toca + Hecho desde tu ultima visita
    a la izquierda, En marcha + Avisos a la derecha. Lo de antes, en /tecnico. Cada carga de la pagina cuenta como
    visita (una a menos de 30 min de la anterior no la mueve)."""
    presentar.registrar_visita()
    return pintar(request, "centro.html", saludo=presentar.saludo(), visita=presentar.visita_llana(),
                  kuzushi=_resumen_kuzushi())


def _resumen_kuzushi() -> dict | None:
    """T1011: el resumen semanal va con la pagina; si no se puede leer, el Centro sale igual (sin el)."""
    try:
        from nucleo import kuzushi
        return kuzushi.resumen()
    except Exception:   # noqa: BLE001 - el Centro no se cae por Kuzushi
        return None


@router.get("/centro/frase")
def panel_frase(request: Request):
    return pintar_panel(request, "_centro_frase.html", "/centro/frase", presentar.frase_estado)


@router.get("/centro/en_marcha")
def panel_en_marcha(request: Request):
    return pintar_panel(request, "_centro_en_marcha.html", "/centro/en_marcha", presentar.en_marcha_ahora)


@router.get("/centro/hecho")
def panel_hecho(request: Request):
    return pintar_panel(request, "_centro_hecho.html", "/centro/hecho", presentar.hecho_desde_visita)


@router.get("/centro/avisos")
def panel_avisos(request: Request):
    return pintar_panel(request, "_centro_avisos.html", "/centro/avisos", presentar.avisos_pendientes)


@router.get("/centro/radares")
def panel_radares(request: Request):
    return pintar_panel(request, "_centro_radares.html", "/centro/radares", presentar.radares_fila)


@router.get("/centro/kuzushi")
def panel_kuzushi(request: Request):
    """T1011 fase 1 (apartado 4): resumen semanal de Kuzushi: visto / arreglado / descartado y por que. Solo lee."""
    from nucleo import kuzushi
    return pintar_panel(request, "_centro_kuzushi.html", "/centro/kuzushi", lambda: {"r": kuzushi.resumen()})


ESTADOS_KUZUSHI = {"calibrar": "en la cola de Claude", "util": "útil, espera turno", "espera": "en espera",
                   "claude": "lo decide Claude", "damian": "te toca decidir", "tarea": "convertido en tarea",
                   "descartado": "descartado", "resuelto": "arreglado"}


@router.get("/kuzushi")
def kuzushi_casos(request: Request):
    """T1011 fase 1: cada caso de Kuzushi con su evidencia (los enlaces del resumen apuntan a su ancla)."""
    from nucleo import kuzushi
    try:
        datos, error = kuzushi.vista(), ""
    except Exception as e:   # noqa: BLE001 - la pagina no se cae por un registro ilegible
        datos, error = {"r": {}, "hallazgos": []}, type(e).__name__
    return pintar(request, "kuzushi.html", estados=ESTADOS_KUZUSHI, error=error, **datos)


@router.get("/tecnico")
def tecnico(request: Request):
    """T691 fase 1: el Centro de antes, completo (Mas -> Detalle tecnico)."""
    return pintar(request, "tecnico.html")


@router.get("/bandejas")
def bandejas(request: Request):
    """T691 fase 1: todo lo que espera una decision de Damian (tribunal, riesgo, revision, chat, tareas suyas)."""
    return pintar(request, "bandejas.html")


@router.get("/radares")
def radares(request: Request):
    """T693 R2: pestana provisional con las tarjetas de cada radar (solo lectura; las acciones llegan en R3)."""
    from nucleo import radar
    try:
        lista, error = radar.vista_web(), ""
    except Exception as e:   # noqa: BLE001 - la pestana no se cae por un radar
        lista, error = [], type(e).__name__
    return pintar(request, "radares.html", radares=lista, error=error)


@router.get("/centro/te_toca")
def panel_te_toca(request: Request, todas: int = 0):
    """T691 fase 1: frase de estado y tarjetas de lo que espera a Damian (en Bandejas, todas)."""
    return _te_toca(request, todas)


def _te_toca(request: Request, todas: int = 0, **extra):
    return pintar_panel(request, "_centro_te_toca.html", "/centro/te_toca",
                        lambda: presentar.te_toca_llano(None if todas else presentar.MAX_TE_TOCA),
                        todas=1 if todas else 0, **extra)


@router.get("/centro/resumen")
def panel_resumen(request: Request):
    """T230: arriba del todo, en palabras normales: si Nexo funciona y que necesita a Damian."""
    return pintar_panel(request, "_centro_resumen.html", "/centro/resumen", presentar.centro)


@router.get("/centro/turnos")
def panel_turnos(request: Request):
    """T231: el turno en marcha (paso, tiempo, tarea), la cola, el proximo programado y el ultimo resultado."""
    from nucleo import planificador
    return pintar_panel(request, "_centro_turnos.html", "/centro/turnos", planificador.resumen_centro)


@router.get("/centro/ias")
def panel_ias(request: Request):
    """T230: cada IA con su punto de estado y su color de marca (bloquear/ordenar: T195)."""
    return pintar_panel(request, "_centro_ias.html", "/centro/ias",
                        lambda: {"ias": presentar.ias(lecturas.salud_proveedores())})


@router.get("/centro/estado")
def panel_estado(request: Request):
    return pintar_panel(request, "_centro_estado.html", "/centro/estado",
                        lambda: {"parada": lecturas.estado_parada(), "cierre": parada.cierre_pedido()})


@router.get("/centro/proveedores")
def panel_proveedores(request: Request):
    return pintar_panel(request, "_centro_proveedores.html", "/centro/proveedores",
                        lambda: {"salud": lecturas.salud_proveedores()})


@router.get("/centro/tareas")
def panel_tareas(request: Request):
    return pintar_panel(request, "_centro_tareas.html", "/centro/tareas",
                        lambda: {"resumen": lecturas.resumen_tareas()})


@router.get("/centro/acciones/tareas")
def panel_tareas_tocadas(request: Request):
    return pintar_panel(request, "_centro_tareas_tocadas.html", "/centro/acciones/tareas",
                        lambda: {"tareas": lecturas.ultimas_tareas()})


@router.get("/centro/auditoria")
def panel_auditoria(request: Request):
    """T189: delegaciones auditadas (las BLOQUEADAS primero) y los ultimos avisos de NEXO."""
    return pintar_panel(request, "_centro_auditoria.html", "/centro/auditoria", lecturas.auditoria_delegaciones)


@router.get("/centro/revision")
def panel_revision(request: Request):
    """T192: cola de revision de Claude (borradores y propuestas pendientes, antiguedad, alerta)."""
    return pintar_panel(request, "_centro_revision.html", "/centro/revision", lecturas.cola_revision)


@router.get("/centro/freno")
def panel_freno(request: Request):
    """T666 (F0): propuestas y revisiones abiertas frente a sus limites, y entradas/salidas por semana."""
    from nucleo import freno
    return pintar_panel(request, "_centro_freno.html", "/centro/freno", lambda: {"m": freno.metricas()})


@router.get("/centro/descartadas")
def panel_descartadas(request: Request, causa: str = ""):
    """T688 pieza 2: lo descartado por idea con su motivo, quien y cuando; filtrable por causa. Solo lee."""
    from nucleo import descartes
    return pintar_panel(request, "_centro_descartadas.html", "/centro/descartadas", lambda: descartes.vista(causa))


def _datos_tribunal() -> dict:
    from nucleo import tribunal
    try:
        orden = tribunal.orden_claude()
    except OSError:
        orden = "(falta documentacion/prompts/CLAUDE_BANDEJA.md)"
    return {"m": tribunal.metricas(), "orden": orden}


@router.get("/centro/tribunal")
def panel_tribunal(request: Request):
    """T667 (F1): bandeja de Damian, bandeja de Claude (con la orden para copiar) y calidad del tribunal."""
    return pintar_panel(request, "_centro_tribunal.html", "/centro/tribunal", _datos_tribunal)


def _datos_claude() -> dict:
    from nucleo import tribunal
    try:
        orden = tribunal.orden_claude()
    except OSError:
        orden = "(falta documentacion/prompts/CLAUDE_BANDEJA.md)"
    from nucleo import implementador
    # T669: los diffs del piloto que esperan el veredicto de Claude tambien encienden el indicador.
    piloto = len(implementador.piloto()["pendientes_claude"])
    return {"pendientes": tribunal.bandeja_claude()["pendientes"] + piloto, "orden": orden}


@router.get("/centro/claude")
def panel_claude(request: Request):
    """Indicador fijo de la bandeja de Claude: casos pendientes y la orden para pegar en Code (un toque)."""
    return pintar_panel(request, "_centro_claude.html", "/centro/claude", _datos_claude)


@router.post("/tribunal/decidir")
def tribunal_decidir(request: Request, nombre: str = Form(""), accion: str = Form(""), resultado: str = Form(""),
                     desde: str = Form(""), todas: int = Form(0)):
    """Damian en su bandeja: aprobar, rechazar o mandar a Claude. Lo aplica el core (revision.veredicto)."""
    from nucleo import tareas as T
    from nucleo import tribunal
    aviso = error = ""
    try:
        tribunal.decidir_damian(nombre, accion, resultado or None)
        aviso = {"aprobar": "Aprobado", "rechazar": "Rechazado", "claude": "Enviado a Claude"}[accion] + f": {nombre}"
    except (tribunal.BandejaLlena, ValueError, T.RevisionPendiente, KeyError) as e:
        error = str(e) or "acción desconocida"
    if desde == "centro":     # T230 v2: el boton de la tarjeta de «Te toca» repinta Te toca, no la bandeja
        return _te_toca(request, todas, aviso=aviso, error=error)
    return pintar_panel(request, "_centro_tribunal.html", "/centro/tribunal", _datos_tribunal, aviso=aviso,
                        error=error)


def _datos_riesgo() -> dict:
    from nucleo import riesgo
    return {"m": riesgo.bandeja(incluir_r3=True)}


@router.get("/centro/riesgo")
def panel_riesgo(request: Request):
    """T668 (F2): matriz de riesgo. R1 se hara salvo tu NO (8 h), R2 espera tu OK sobre el diff, R3 es de Claude."""
    return pintar_panel(request, "_centro_riesgo.html", "/centro/riesgo", _datos_riesgo)


@router.post("/riesgo/decidir")
def riesgo_decidir(request: Request, id: str = Form(""), accion: str = Form(""), desde: str = Form(""),
                   todas: int = Form(0)):
    """Damian veta un R1 o aprueba/rechaza un R2. Solo solicitudes de la matriz (lo ambar va por su camino)."""
    from nucleo import aprobaciones as ap
    aviso = error = ""
    try:
        s = ap.ver(id)
        if s.get("nivel") not in ap.NIVELES_MATRIZ:
            raise ValueError(f"{id} no es de la matriz de riesgo")
        if accion == "aprobar" and s["nivel"] == "R2":
            ap.aprobar(id, quien="damian", motivo="web: Centro, matriz de riesgo")
            aviso = f"Aprobada: {id}"
        elif accion == "aceptar" and s["nivel"] == "R1":
            # T967: "Aceptar" junto a "Vetar": la R1 queda aprobada al momento; el implementador sigue en su tanda.
            ap.aprobar(id, quien="damian", motivo="web: Centro, R1 aceptada")
            aviso = f"Aceptada: {id}"
        elif accion == "denegar":
            ap.denegar(id, quien="damian", motivo="web: Centro, matriz de riesgo")
            aviso = ("Vetada" if s["nivel"] == "R1" else "Rechazada") + f": {id}"
        else:
            raise ValueError("acción desconocida")
    except (ap.NoEncontrada, ap.EstadoInvalido, ValueError) as e:
        error = str(e).strip("'") or "no se pudo decidir"
    if desde == "centro":
        return _te_toca(request, todas, aviso=aviso, error=error)
    return pintar_panel(request, "_centro_riesgo.html", "/centro/riesgo", _datos_riesgo, aviso=aviso, error=error)


@router.post("/riesgo/deshacer")
def riesgo_deshacer(request: Request, id: str = Form("")):
    """T890: Damian deshace un veto R1 (vetado hace menos de 7 dias y con su tarea aun abierta). Solo desde la web."""
    from nucleo import aprobaciones as ap
    aviso = error = ""
    try:
        s = ap.ver(id)
        if s.get("nivel") != "R1":
            raise ValueError(f"{id} no es un veto R1")
        s = ap.deshacer_veto(id, quien="damian", motivo="web: Centro, deshacer veto")
        aviso = f"Veto deshecho: {id}. Vuelve a esperar tu NO hasta {s['vence']} (silencio = sí)."
    except (ap.NoEncontrada, ap.EstadoInvalido, ValueError) as e:
        error = str(e).strip("'") or "no se pudo deshacer el veto"
    return pintar_panel(request, "_centro_riesgo.html", "/centro/riesgo", _datos_riesgo, aviso=aviso, error=error)


@router.get("/centro/acciones/trazas")
def panel_trazas(request: Request):
    return pintar_panel(request, "_centro_trazas.html", "/centro/acciones/trazas",
                        lambda: {"trazas": lecturas.ultimas_trazas()})


@router.post("/centro/brief")
def brief_ahora(request: Request):
    """T697: "Cuéntamelo ahora". El mismo brief que lanza el 13 % del altavoz, en un hilo (tarda: Gemini TTS)."""
    from fastapi.responses import HTMLResponse
    from extremidades import altavoz
    oyente = altavoz.oyente_activo()
    altavoz.contar_en_hilo(cc=oyente.cc if oyente is not None else None)
    return HTMLResponse('<p id="msg-brief" class="nota nota-aviso" role="status">Preparando el brief para el '
                        'altavoz «Damián»… Si no suena, sale un aviso aquí.</p>')


def _datos_ambar() -> dict:
    """T1020: la ficha es la del guardian (nucleo.guardian.explicacion). Bandejas ensena tambien lo que el tribunal del
    guardian esta mirando (con su nota); Te toca no."""
    from interfaz import ocultar
    from nucleo import aprobaciones as ap, guardian
    return {"pendientes": [s | {"accion": ocultar.texto(s.get("accion", "")),
                                "detalle": ocultar.texto(str(s.get("detalle") or "")[:1500]),
                                "explica": ocultar.valor(guardian.explicacion(s)),
                                "con_tribunal": (s.get("tribunal") or {}).get("estado") == "pendiente"}
                           for s in ap.pendientes()]}


@router.get("/centro/ambar")
def panel_ambar(request: Request):
    """T751: lo ambar que espera a Damian (antes solo con los botones de Telegram). Sin respuesta = NO."""
    return pintar_panel(request, "_centro_ambar.html", "/centro/ambar", _datos_ambar)


@router.post("/ambar/decidir")
def ambar_decidir(request: Request, id: str = Form(""), accion: str = Form(""), desde: str = Form(""),
                  todas: int = Form(0)):
    """Aprobar o denegar una solicitud AMBAR (las R1/R2 van por /riesgo/decidir). Queda en el historial encadenado
    de la cola con quien="damian:web"."""
    from nucleo import aprobaciones as ap
    aviso = error = ""
    try:
        s = ap.ver(id)
        if s.get("nivel") in ap.NIVELES_MATRIZ:
            raise ValueError(f"{id} es de la matriz de riesgo: decídela en su bandeja")
        if accion == "aprobar":
            ap.aprobar(id, quien="damian:web", motivo="web: Bandejas, aprobaciones ámbar")
            aviso = f"Aprobada: {id}"
        elif accion == "denegar":
            ap.denegar(id, quien="damian:web", motivo="web: Bandejas, aprobaciones ámbar")
            aviso = f"Denegada: {id}"
        else:
            raise ValueError("acción desconocida")
    except (ap.NoEncontrada, ap.EstadoInvalido, ValueError) as e:
        error = str(e).strip("'") or "no se pudo decidir"
    if desde == "centro":
        return _te_toca(request, todas, aviso=aviso, error=error)
    if desde == "ficha":   # T1020: desde la ficha de la solicitud, se vuelve a pintar la ficha (o se dice el error)
        if error:
            from html import escape
            return Response(f'<p class="estado-parado" role="alert">{escape(error)}</p>', media_type="text/html")
        return Response(status_code=204, headers={"HX-Redirect": f"/aprobacion/{id}"})
    return pintar_panel(request, "_centro_ambar.html", "/centro/ambar", _datos_ambar, aviso=aviso, error=error)


# ------------------------------------------------------------------ T1020: ficha de una solicitud de la cola
ESTADOS_LLANO = {"pendiente": "Espera una decisión", "aprobada": "Aprobada (aún sin usar)", "usada": "Aprobada y hecha",
                 "denegada": "Denegada: no se hizo", "caducada": "Caducó sin respuesta: no se hizo"}
QUIEN_LLANO = {"guardian": "NEXO solo (guardián)", "tribunal": "el tribunal de 3 IAs", "revisor:reglas": "NEXO solo (reglas)",
               "sistema": "NEXO", "damian:web": "tú (web)", "damian": "tú", "silencio": "tu silencio"}


def datos_aprobacion(id_: str) -> dict:
    from interfaz import ocultar
    from nucleo import aprobaciones as ap, guardian
    s = ap.ver(id_.upper())
    eventos = [{"cuando": e.get("cuando", ""), "tipo": e.get("tipo", ""),
                "quien": QUIEN_LLANO.get(e.get("quien", ""), e.get("quien", "")), "motivo": ocultar.texto(e.get("motivo") or "")}
               for e in s.get("eventos") or []]
    x = {"id": s["id"], "accion": ocultar.texto(s.get("accion", "")), "nivel": s.get("nivel", "ambar"),
         "detalle": ocultar.texto(str(s.get("detalle") or "")[:3000]), "estado": s["estado"],
         "estado_llano": ESTADOS_LLANO.get(s["estado"], s["estado"]), "vence": str(s.get("vence") or "")[:16],
         "decidida_por": QUIEN_LLANO.get(s.get("decidida_por", ""), s.get("decidida_por", "")),
         "explica": ocultar.valor(guardian.explicacion(s)),
         "con_tribunal": (s.get("tribunal") or {}).get("estado") == "pendiente"}
    return {"x": x, "eventos": eventos}


@router.get("/aprobacion/{id_}")
def ficha_aprobacion(request: Request, id_: str):
    """T1020: la ficha en llano de una solicitud (guardian), su historia y, si espera a Damian, los botones."""
    from nucleo import aprobaciones as ap
    try:
        datos = datos_aprobacion(id_)
    except ap.NoEncontrada:
        return pintar(request, "error.html", codigo=404, codigo_error=404)
    from nucleo import chat_aprobacion as CA
    return pintar(request, "aprobacion.html", chat=CA.conversacion(datos["x"]["id"]), **datos)


@router.post("/aprobacion/{id_}/chat")
def chat_aprobacion_post(request: Request, id_: str, mensaje: str = Form(""), escalar: str = Form("")):
    """T1020 pieza 3: el minichat de la ficha. Solo explica (NVIDIA, reserva Groq/Gemini API, Qwen); «Escalar» la
    deja para Claude. Sin acciones: decidir es con los botones."""
    from nucleo import aprobaciones as ap, chat_aprobacion as CA
    aviso = ""
    try:
        CA.preguntar(id_, mensaje, escalar == "1")
    except CA.ChatRechazado as e:
        aviso = str(e)
    try:
        datos = datos_aprobacion(id_)
    except (ap.NoEncontrada, CA.ChatRechazado):
        return Response('<p class="estado-parado" role="alert">No hay ninguna solicitud con ese nombre.</p>',
                        media_type="text/html")
    return pintar(request, "_aprobacion_chat.html", chat=CA.conversacion(datos["x"]["id"]), aviso_chat=aviso, **datos)


# ------------------------------------------------------------------ T859 bloque 6: huecos de reels (solo Damian)
def _datos_reels_huecos() -> dict:
    from nucleo import reels_huecos
    return {"huecos": reels_huecos.pendientes()[:reels_huecos.MAX_TANDA]}


@router.get("/centro/reels_huecos")
def panel_reels_huecos(request: Request):
    """Reels que piden 'comenta X / DM / link in bio' y cuya informacion esencial no esta en publico."""
    return pintar_panel(request, "_centro_reels_huecos.html", "/centro/reels_huecos", _datos_reels_huecos)


@router.post("/reels/hueco")
def reels_hueco(request: Request, codigo: str = Form(""), accion: str = Form(""), texto: str = Form("")):
    """'Pegado' guarda lo recibido (contenido NO confiable, solo dato) y deja el reel para reprocesar;
    'No merece la pena' lo cierra. NEXO nunca comenta ni escribe desde la cuenta de Damian."""
    from nucleo import reels_huecos
    aviso = error = ""
    try:
        if accion == "pegado":
            reels_huecos.pegar(codigo, texto)
            aviso = "Guardado: el reel se rehará con lo que has pegado en la próxima pasada del lote."
        elif accion == "no_merece":
            reels_huecos.no_merece(codigo, "Damian (web)")
            aviso = "Apartado: no se volverá a pedir."
        else:
            raise ValueError("acción desconocida")
    except (KeyError, ValueError) as e:
        error = str(e).strip("'") or "no se pudo guardar"
    return pintar_panel(request, "_centro_reels_huecos.html", "/centro/reels_huecos", _datos_reels_huecos,
                        aviso=aviso, error=error)
