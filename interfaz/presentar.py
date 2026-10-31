# -*- coding: utf-8 -*-
"""T230: lo que pintan Centro, Tareas y la ficha, ya traducido para Damian (sale del boceto aprobado el 28/09).

Solo LEE y prepara datos para las plantillas. Las acciones siguen en rutas/ llamando al core.
Lo crudo (ids de etiqueta, estados del core, puntuacion) sigue en cada `t` para el "Detalle tecnico".
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from interfaz import humano as H
from nucleo import auditor, avisos, parada, responsables, revision
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico
from nucleo import chat_tarea as C
from nucleo import tareas as T

ORDENES = [
    ("prioridad", "Lo más importante primero"),
    ("actualizada", "Movidas hace poco"),
    ("creada", "Creadas hace poco"),
    ("antiguas", "Las más antiguas primero"),
    ("limite", "Por fecha límite"),
]
MAX_FILAS = 300
MAX_TEXTO_FILTRO = 100
MAX_ETIQUETA = 60
# Orden de los parametros en la URL (la barra de direcciones guarda el filtro)
CLAVES_URL = ("estado", "depende", "etiqueta", "q", "categoria", "tema", "proveedor", "origen", "orden")
DEFECTOS_URL = {"estado": "vivas", "orden": "prioridad"}


# ---------------------------------------------------------------------- una tarea
def vuelve(t: dict) -> str:
    if t["estado"] != "aparcada":
        return ""
    hasta = t.get("aparcada_hasta")
    try:
        return "vuelve el " + date.fromisoformat(hasta).strftime("%d/%m") if hasta else "sin fecha de vuelta"
    except (TypeError, ValueError):
        return "sin fecha de vuelta"


def vista(t: dict) -> dict:
    """Todo lo que la vista humana necesita de una tarea (lo crudo va aparte, en `t`)."""
    punt = T.puntuacion(t)
    prio, clase_prio = H.prioridad(punt)
    dias = T.dias_restantes(t)
    return {"t": t, "estado": H.estado(T.estado_real(t)), "et": H.etiquetas(t.get("etiquetas")), "resumen": H.resumen(t),
            "quien": H.QUIEN.get(t["depende"], t["depende"]), "prioridad": prio, "clase_prio": clase_prio,
            "puntuacion": punt, "claude": T.sugerencia_claude(t),
            "plazo": H.plazo(dias) if t.get("limite") else "", "vencida": bool(t.get("limite") and dias is not None and dias < 0),
            "creada": H.hace(t.get("creada")), "actualizada": H.hace(t.get("actualizada")), "vuelve": vuelve(t)}


def atajos_aparcar(hoy: date | None = None) -> list[tuple[str, date]]:
    hoy = hoy or date.today()
    mes = hoy.replace(year=hoy.year + (hoy.month == 12), month=hoy.month % 12 + 1, day=1)
    # "1 mes": mismo dia del mes siguiente (o el ultimo si no existe, p. ej. 31/01 -> 28/02)
    ultimo = (mes.replace(year=mes.year + (mes.month == 12), month=mes.month % 12 + 1) - timedelta(days=1)).day
    return [("Mañana", hoy + timedelta(days=1)), ("1 semana", hoy + timedelta(days=7)),
            ("1 mes", mes.replace(day=min(hoy.day, ultimo)))]


def ficha(t: dict, todas: list[dict]) -> dict:
    por_id = {x["id"]: x for x in todas}
    v = vista(t)

    def enlace(i):
        x = por_id.get(i)
        return {"id": i, "titulo": x["titulo"] if x else "(ya no existe)", "estado": H.estado(T.estado_real(x)) if x else None}

    relacionadas = [("Nace de", enlace(e.split(":", 1)[1])) for e in t.get("etiquetas") or [] if e.startswith("tarea_origen:")]
    if t.get("bloqueada_por"):
        relacionadas.append(("Espera a", enlace(t["bloqueada_por"])))
    relacionadas += [("Ha generado", enlace(x["id"])) for x in todas
                     if f"tarea_origen:{t['id']}" in (x.get("etiquetas") or [])]

    notas = []
    for n in reversed(t.get("notas") or []):
        texto = n.get("texto") or ""
        prueba = texto.startswith("[verificado]")
        notas.append({"cuando": H.hace(n.get("cuando")), "exacto": n.get("cuando", ""), "prueba": prueba,
                      "texto": texto[12:].strip() if prueba else texto})

    er = v["estado"]["crudo"]
    if responsables.es_suya(t) and t["estado"] in T.VIVOS and t["estado"] != "aparcada":
        te_toca = "Esta tarea depende de ti. Lee el resumen y, cuando la hagas, deja una nota o márcala hecha."
    elif er == "HECHO SIN TESTEAR":
        te_toca = "Falta que alguien pruebe que funciona y lo deje escrito (abajo, «Verificar con evidencia»)."
    elif er == "PROPUESTA (sin revisar)":
        te_toca = "Nada por ahora: Claude decidirá si la idea vale. Si quieres opinar, deja una nota."
    else:
        te_toca = ""
    return {"v": v, "relacionadas": relacionadas, "notas_humanas": notas, "te_toca": te_toca,
            "atajos": atajos_aparcar(), "hoy": date.today(), "hace": H.hace}


# ---------------------------------------------------------------------- lista
def _limpio(valor: str, permitidos) -> str:
    return valor if valor in permitidos else ""


def url_tareas(f: dict, sin: str = "") -> str:
    partes = {k: f[k] for k in CLAVES_URL if k != sin and f.get(k) and f[k] != DEFECTOS_URL.get(k)}
    return "/tareas" + ("?" + urlencode(partes) if partes else "")


def lista(estado="vivas", depende="", etiqueta="", q="", categoria="", tema="", proveedor="", origen="",
          orden="prioridad") -> dict:
    """Lista filtrada y ordenada. `estado` acepta los grupos humanos y, por compatibilidad con enlaces
    viejos, tambien los estados del core (pendiente, hecha...). Revienta si tareas.json esta roto."""
    todas = [vista(t) for t in T.cargar()["tareas"]]
    grupos = dict(H.GRUPOS)
    estado = estado if estado in grupos or estado in T.ESTADOS else "vivas"
    orden = orden if orden in dict(ORDENES) else "prioridad"

    def opciones(clave):
        return sorted(Counter(v["et"][clave] for v in todas if v["et"][clave]).items())

    ops = {c: opciones(c) for c in ("categoria", "tema", "proveedor", "origen")}
    f = {"estado": estado, "depende": _limpio(depende, T.DEPENDENCIAS),
         "etiqueta": (etiqueta or "").strip()[:MAX_ETIQUETA], "q": (q or "").strip()[:MAX_TEXTO_FILTRO],
         "categoria": _limpio(categoria, dict(ops["categoria"])), "tema": _limpio(tema, dict(ops["tema"])),
         "proveedor": _limpio(proveedor, dict(ops["proveedor"])), "origen": _limpio(origen, dict(ops["origen"])),
         "orden": orden}

    def en_estado(v):
        if estado in T.ESTADOS:
            return v["t"]["estado"] == estado
        g = v["estado"]["grupo"]
        return {"todas": True, "vivas": g in H.GRUPOS_VIVOS}.get(estado, g == estado)

    filas = [v for v in todas if en_estado(v)]
    if f["depende"]:
        filas = [v for v in filas if v["t"]["depende"] == f["depende"]]
    for clave in ("categoria", "tema", "proveedor", "origen"):
        if f[clave]:
            filas = [v for v in filas if v["et"][clave] == f[clave]]
    if f["etiqueta"]:
        e = f["etiqueta"].lower()
        filas = [v for v in filas if any(e in x.lower() for x in v["t"].get("etiquetas") or [])]
    if f["q"]:
        aguja = f["q"].lower()
        filas = [v for v in filas if aguja in v["t"]["id"].lower() or aguja in v["t"]["titulo"].lower()
                 or aguja in (v["t"].get("detalle") or "").lower() or aguja in (v["t"].get("resumen_humano") or "").lower()]

    if orden == "prioridad":
        filas.sort(key=lambda v: -v["puntuacion"])
    elif orden in ("actualizada", "creada"):
        filas.sort(key=lambda v: v["t"].get(orden) or "", reverse=True)
    elif orden == "antiguas":
        filas.sort(key=lambda v: v["t"].get("creada") or "")
    else:  # limite: primero las que tienen fecha, la mas cercana antes
        filas.sort(key=lambda v: (not v["t"].get("limite"), v["t"].get("limite") or "", -v["puntuacion"]))

    nombres = {"depende": H.QUIEN, "estado": grupos}
    chips = []
    for clave in ("q", "estado", "depende", "categoria", "tema", "proveedor", "origen", "etiqueta"):
        valor = f[clave]
        if not valor or valor == DEFECTOS_URL.get(clave):
            continue
        texto = nombres.get(clave, {}).get(valor, valor)
        chips.append({"texto": f"«{texto}»" if clave == "q" else (f"etiqueta {texto}" if clave == "etiqueta" else texto),
                      "url": url_tareas(f, sin=clave)})

    cuenta = Counter(v["estado"]["grupo"] for v in todas)
    cuenta["vivas"] = sum(cuenta[g] for g in H.GRUPOS_VIVOS)
    cuenta["todas"] = len(todas)
    return {"filas": filas[:MAX_FILAS], "total": len(filas), "recortada": len(filas) > MAX_FILAS, "f": f, "ops": ops,
            "grupos": H.GRUPOS, "cuenta": cuenta, "ordenes": ORDENES, "quienes": H.QUIEN, "chips": chips,
            "url": url_tareas(f)}


# ---------------------------------------------------------------------- centro
def centro() -> dict:
    todas = T.cargar()["tareas"]
    vivas = [t for t in todas if t["estado"] in T.VIVOS and t["estado"] != "aparcada"]
    # Guardia de responsables (05/10): "Te toca" solo con lo que de verdad es suyo
    te_tocan = sorted((vista(t) for t in vivas if responsables.es_suya(t)), key=lambda v: -v["puntuacion"])
    repaso = responsables.ultimo_repaso() or {}
    mal_asignadas = repaso.get("mal_asignadas") or []
    vencidas = [v for v in (vista(t) for t in vivas) if v["vencida"] and v["t"]["depende"] != "damian"]
    recientes = [vista(t) for t in sorted(todas, key=lambda t: t.get("actualizada") or "", reverse=True)[:8]]

    auditorias = [H.aviso_auditoria(a) for a in auditor.recientes(12)]
    abiertos = [a for a in auditorias if not a["resuelto"]]
    resueltos = [a for a in auditorias if a["resuelto"]]
    cola = revision.cola()
    # Avisos que no son de auditoria ni de la cola (esos ya salen contados en palabras normales)
    otros = [x for x in avisos.recientes(20) if x.get("tipo") not in ("auditoria", "revision")][:5]
    chat_ok = C.esperan_ok()   # T290: cambios pedidos en el chat de una tarea que esperan su OK
    n_atencion = len(te_tocan) + len(chat_ok) + len(abiertos) + len(vencidas) + (1 if cola["alerta"] else 0)         + (1 if mal_asignadas else 0)
    return {"te_tocan": te_tocan[:6], "n_te_tocan": len(te_tocan), "chat_ok": chat_ok, "vencidas": vencidas[:5],
            "mal_asignadas": mal_asignadas, "repaso_cuando": repaso.get("cuando"), "altavoz": _altavoz(), "recientes": recientes,
            "abiertos": abiertos, "resueltos": resueltos[:6], "cola": cola, "otros": otros, "n_atencion": n_atencion,
            "cierre": parada.cierre_pedido(), "hace": H.hace,
            "cuenta": {g: sum(1 for t in todas if H.estado(T.estado_real(t))["grupo"] == g)
                       for g in ("por_hacer", "en_marcha", "atascadas", "sin_comprobar", "aparcadas")}}


def _altavoz() -> dict | None:
    """T697 (05/10): estado del oyente del altavoz; None si no hay oyente o no se puede leer."""
    try:
        from extremidades import altavoz
        return altavoz.estado_oyente()
    except Exception:   # noqa: BLE001 - el Centro no se cae por el altavoz
        return None


def ias(salud: dict) -> list[dict]:
    return [{**H.ia(p["nombre"], p["salud"]), "motivo": p.get("enfriamiento") or p.get("motivo") or ""}
            for p in salud["lista"]]


# ------------------------------------------------------------------ T691 fase 1: "Te toca" y contador de Bandejas
MAX_TE_TOCA = 3


def te_toca(maximo: int | None = MAX_TE_TOCA) -> dict:
    """Todo lo que espera una decision de Damian, de mas a menos urgente, en tarjetas cortas. Cada fuente que falle
    se salta (el Centro no se cae por un panel); el detalle y las acciones siguen en /bandejas y en la ficha."""
    items: list[dict] = []

    def fuente(fn):
        try:
            fn()
        except Exception:   # noqa: BLE001 - una bandeja ilegible no tumba el Centro
            pass

    def tribunal_():
        from nucleo import tribunal
        for e in tribunal.bandeja_damian():
            items.append({"chip": "Tribunal · sin acuerdo", "urgente": False, "titulo": f"{e['origen']} · {e['titulo']}",
                          "detalle": (e.get("lineas") or [""])[min(1, len(e.get("lineas") or [""]) - 1)],
                          "enlace": "/bandejas#bandeja-tribunal", "accion": "Decidir en Bandejas", "tipo": "tribunal",
                          "ref": e["nombre"], "es_inv": bool(e.get("es_inv")), "resultado": e.get("resultado") or ""})

    def riesgo_():
        from nucleo import guardian, riesgo
        m = riesgo.bandeja()
        con_tribunal = {s["id"] for s in guardian.tribunal_pendientes()}   # T1020: aun no es de Damian
        for f in m["r2"]:
            if f["id"] in con_tribunal:
                continue
            items.append({"chip": f"R2 · espera tu OK · vence {str(f['vence'])[:10]}", "urgente": True,
                          "titulo": f"{f['tarea']} · {f['titulo']}".strip(" ·"), "detalle": f.get("resumen", ""),
                          "enlace": "/bandejas#bandeja-riesgo", "accion": "Ver el diff y decidir", "tipo": "r2",
                          "ref": f["id"], "vence": f["vence"], "ficha": f"/aprobacion/{f['id']}"})
        for f in m["r1"]:
            items.append({"chip": f"R1 · se hará salvo tu NO · {str(f['vence'])[:16]}", "urgente": False,
                          "titulo": f"{f['tarea']} · {f['titulo']}".strip(" ·"), "detalle": f.get("resumen", ""),
                          "enlace": "/bandejas#bandeja-riesgo", "accion": "Revisar", "tipo": "r1",
                          "ref": f["id"], "vence": f["vence"]})

    def chat_():
        for p in C.esperan_ok():
            items.append({"chip": "Chat de una tarea · caduca en 24 h", "urgente": True, "titulo": f"{p['tarea']} · OK pedido",
                          "detalle": p.get("texto", ""), "enlace": f"/tareas/{p['tarea']}#chat-tarea",
                          "accion": "Abrir la tarea", "tipo": "chat"})

    def ambar_():
        """T751: lo ambar de la cola (las del chat de una tarea ya salen en chat_). T1020: con la ficha del guardian
        (nucleo.guardian.explicacion) y sin lo que el tribunal del guardian aun esta mirando."""
        from interfaz import ocultar
        from nucleo import aprobaciones as ap, guardian
        for s in guardian.para_damian(ap.pendientes()):
            if s.get("origen") == "chat_tarea":
                continue
            ex = guardian.explicacion(s)
            items.append({"chip": f"Aprobación ámbar · caduca {str(s.get('vence'))[:16]}", "urgente": True,
                          "titulo": f"{s['id']} · {ocultar.texto(ex['que'])}",
                          "detalle": ocultar.texto(f"Lo pide: {ex['quien']} Riesgo: {ex['riesgo']}"),
                          "enlace": "/bandejas#bandeja-ambar", "accion": "Aprobar o denegar", "tipo": "ambar",
                          "ref": s["id"], "vence": s.get("vence"), "ficha": f"/aprobacion/{s['id']}",
                          "por_que_llano": ocultar.texto(" ".join(x for x in (
                              f"{ex['tipo_llano']}.", f"Lo pide {ex['quien_corto']}.",
                              f"Para qué: {ex['para_que']}", f"Recomendación: {ex['recomendacion']}") if x)),
                          "por_que_a_ti": ocultar.texto(ex.get("por_que_a_ti") or "")})

    def tareas_():
        vivas = [t for t in T.cargar()["tareas"] if t["estado"] in T.VIVOS and t["estado"] != "aparcada"
                 and responsables.es_suya(t)]
        for t in sorted(vivas, key=lambda t: -T.puntuacion(t)):
            items.append({"chip": "Tarea tuya", "urgente": False, "titulo": f"{t['id']} · {t['titulo']}",
                          "detalle": H.resumen(t)["texto"], "enlace": f"/tareas/{t['id']}", "accion": "Abrir la tarea",
                          "tipo": "tarea", "limite": t.get("limite") or "", "dias": T.dias_restantes(t)})

    for fn in (riesgo_, ambar_, chat_, tribunal_, tareas_):
        fuente(fn)
    decisiones = sum(1 for i in items if i["chip"] != "Tarea tuya")
    return {"tarjetas": items[:maximo] if maximo else items, "total": len(items), "decisiones": decisiones,
            "parada": parada.activa(), "cierre": parada.cierre_pedido()}


def n_bandejas() -> int:
    """Contador del icono de Bandejas: decisiones pendientes (no cuenta las tareas sueltas que dependen de Damian)."""
    return te_toca()["decisiones"]


# ------------------------------------------------- Centro en tres columnas (opcion A de Damian, bloque 5, 12/10)
# Vista principal en lenguaje llano: sin IDs (T123, A0001), sin R1/R2 ni nombres internos. Lo tecnico sigue en
# Mas -> Detalle tecnico (/tecnico) y en cada ficha.
_ID = re.compile(r"\b(?:T\d{3,4}|A\d{4}|N\d{2}|R[0-3])\b")
_CORCHETES = re.compile(r"\[[^\]]*\]\s*")      # "[Propuesta de T274] ..." -> "..."
_PARA_DAMIAN = re.compile(r"^(?:\W*(?:Para\s+Dami[aá]n)\s*[:\-–—]\s*)+", re.I)   # T230 v2: "Para Damian: x" -> "x"
_CONTADOR_FINAL = re.compile(r"\s*\(\d+\)\s*$")                                          # T230 v2: "x (5)" -> "x"
LLANO_CHIP = [   # (empieza por, texto llano)
    ("R2", "Espera tu visto bueno"),
    ("R1", "Se hará si no dices nada"),
    ("Aprobación ámbar", "Pide permiso"),
    ("Chat de una tarea", "Te pregunta algo"),
    ("Tribunal", "Las IAs no se ponen de acuerdo"),
    ("Tarea tuya", "Tarea tuya"),
]
MAX_EN_MARCHA = 5
MAX_TUS_TAREAS = 5


def llano(texto: str) -> str:
    """Quita IDs, corchetes de origen y separadores sueltos: para la vista principal."""
    t = _CORCHETES.sub("", texto or "")
    t = _ID.sub("", t)
    t = _PARA_DAMIAN.sub("", t.strip())
    t = _CONTADOR_FINAL.sub("", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\s*·\s*(·\s*)+", " · ", t)
    t = re.sub(r"\s+([:,.;])", r"\1", t)                # "borrador de : algo" -> "borrador de: algo"
    t = re.sub(r"\s{2,}", " ", t).strip(" ·:-")
    return t[:1].upper() + t[1:] if t else t


def chip_llano(chip: str) -> str:
    for ini, texto in LLANO_CHIP:
        if chip.startswith(ini):
            return texto
    return llano(chip)


def saludo(ahora: datetime | None = None) -> str:
    h = (ahora or datetime.now()).hour
    return "Buenos días, Damián" if 6 <= h < 14 else ("Buenas tardes, Damián" if 14 <= h < 21 else "Buenas noches, Damián")


def _titulos() -> dict[str, str]:
    try:
        return {t["id"]: t["titulo"] for t in T.cargar()["tareas"]}
    except Exception:   # noqa: BLE001
        return {}


def cuando_llano(texto: str | None, ahora: datetime | None = None) -> str:
    """'hoy a las 20:00', 'mañana a las 12:22', 'el 20/10 a las 12:22' (T230 v2: plazos en palabras, no fechas)."""
    ahora = ahora or datetime.now()
    f = None
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            f = datetime.strptime(str(texto or "").strip(), formato)
            break
        except ValueError:
            continue
    if f is None:
        return ""
    dias = (f.date() - ahora.date()).days
    dia = {0: "hoy", 1: "mañana", -1: "ayer"}.get(dias, f"el {f:%d/%m}")
    return f"{dia} a las {f:%H:%M}"


_PLAZO = {   # tipo de tarjeta -> que pasa si Damian no dice nada
    "ambar": "caduca", "r1": "se hará", "r2": "se descarta",
}


def plazo_llano(c: dict, ahora: datetime | None = None) -> str:
    """'Si no dices nada, caduca mañana a las 12:22'. Vacio si la tarjeta no tiene plazo."""
    if c.get("tipo") == "chat":
        return "Si no dices nada, caduca en 24 horas"
    verbo, cuando = _PLAZO.get(c.get("tipo") or ""), cuando_llano(c.get("vence"), ahora)
    return f"Si no dices nada, {verbo} {cuando}" if verbo and cuando else ""


def _limite_llano(dias: int | None, limite: str) -> str:
    if dias is None or not limite:
        return ""
    if dias in (0, 1):
        return {0: "vence hoy", 1: "vence mañana"}[dias]
    return ("venció" if dias < 0 else "vence") + f" el {limite[8:10]}/{limite[5:7]}"


def te_toca_llano(maximo: int | None = MAX_TE_TOCA, ahora: datetime | None = None) -> dict:
    """T230 v2. `tarjetas`: las DECISIONES (permiso, R1/R2, chat, tribunal) con plazo en palabras y botones; `tareas`:
    Tus tareas, una fila cada una (la de fecha limite, primero). Lo crudo queda en `chip`/`titulo`."""
    d = te_toca(None)
    decisiones, tareas = [], []
    for c in d["tarjetas"]:
        c["chip_llano"] = chip_llano(c["chip"])
        c["titulo_llano"] = llano(c["titulo"]) or c["chip_llano"]
        c["accion"] = c["accion"].replace("el diff", "el cambio")
        if c.get("tipo") == "tarea":
            tareas.append({"titulo": c["titulo_llano"], "enlace": c["enlace"],
                           "plazo": _limite_llano(c.get("dias"), c.get("limite") or ""),
                           "dias": c.get("dias") if c.get("limite") else None})
            continue
        c["plazo_llano"] = plazo_llano(c, ahora)
        c["detalle_llano"] = llano(c.get("por_que_llano") or c.get("detalle") or "")
        motivo = c.get("por_que_a_ti") or ""
        if motivo and c.get("tipo") == "ambar" and "Recomendación:" not in c["detalle_llano"]:
            c["detalle_llano"] = f"{c['detalle_llano']} Por qué te llega: {motivo[:1].lower()}{motivo[1:]}".strip()
        decisiones.append(c)
    tareas.sort(key=lambda x: (x["dias"] is None, x["dias"] if x["dias"] is not None else 0))
    return {"tarjetas": decisiones[:maximo] if maximo else decisiones, "n_decisiones": len(decisiones),
            "tareas": tareas[:MAX_TUS_TAREAS] if maximo else tareas, "n_tareas": len(tareas),
            "con_fecha": sum(1 for x in tareas if x["dias"] is not None),
            "total": len(decisiones) + len(tareas), "decisiones": d["decisiones"], "parada": d["parada"],
            "cierre": d["cierre"]}


# ------------------------------------------------------------------ En marcha (T230 v2: tres lineas)
TURNOS_LLANO = {   # nombre de turno (plantillas de nucleo/turnos.py) -> que hace, en palabras normales
    "Tareas de la cola por orden": "Trabajar las tareas de la cola por orden",
    "Revisar el codigo (sin modificar nada)": "Leer el código buscando fallos (sin cambiar nada)",
    "Revisar archivos y apuntar incoherencias": "Revisar archivos y apuntar lo que no cuadra",
    "Solo investigacion pendiente": "Hacer las investigaciones pendientes",
    "Solo correcciones de errores": "Corregir errores conocidos",
    "Vigia de novedades": "Mirar si hay novedades que te interesen",
    "Radares (fuentes fijas, tarjetas)": "Mirar las fuentes de los radares",
    "Tribunal de revision (sin Claude)": "Revisar los borradores pendientes con tres IAs distintas (si hay alguno)",
    "Banco de modelos (diario)": "Medir qué IA va mejor para cada trabajo",
    "Implementador (permanente)": "Programar una tarea con tests ya escritos (si hay alguna)",
    "Reels guardados (lote nocturno)": "Ordenar los reels que guardaste",
    "Kuzushi (observa sin IA)": "Repasar lo que hizo NEXO y apuntar lo que falla (sin IA)",
}


def turno_llano(nombre: str) -> str:
    n = " ".join(str(nombre or "").split())
    return TURNOS_LLANO.get(n) or llano(n) or "Un trabajo automático"


def en_marcha_ahora() -> dict:
    """Ahora / Despues / En cola, mas cuantas tareas hay en curso (una nota aparte)."""
    titulos = _titulos()
    ahora_ = despues = None
    cola: list[str] = []
    try:
        from nucleo import planificador
        r = planificador.resumen_centro()
        m = r.get("marcha")
        if m:
            tarea = titulos.get(m.get("tarea") or "", "")
            ahora_ = {"nombre": turno_llano(m.get("nombre") or ""), "tiempo": m.get("transcurrido", ""),
                      "parando": bool(m.get("parando")), "tarea": llano(tarea)}
        cola = [turno_llano(x.get("nombre") or x.get("turno") or "") for x in r.get("cola") or []]
        if r.get("proximo") and not r.get("desactivados"):
            despues = {"nombre": turno_llano(r["proximo"]["nombre"]), "cuando": r["proximo"]["cuando"]}
    except Exception:   # noqa: BLE001 - la columna no se cae por el planificador
        pass
    try:
        n_curso = sum(1 for t in T.cargar()["tareas"] if t["estado"] == "en_curso")
    except Exception:   # noqa: BLE001
        n_curso = 0
    return {"ahora": ahora_, "despues": despues, "cola": cola, "n_en_curso": n_curso, "parada": parada.activa()}


# ------------------------------------------------------------------ Hecho desde tu ultima visita (T230 v2)
VISITA = RAIZ / "memoria" / "interfaz_visita.json"
HUECO_VISITA = timedelta(minutes=30)
MAX_GRUPOS_HECHO = 6
MAX_RESUELTOS = 5
_FMT_VISITA = "%Y-%m-%d %H:%M:%S"


def _leer_visita() -> dict:
    try:
        d = json.loads(VISITA.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def registrar_visita(ahora: datetime | None = None) -> dict:
    """Anota una carga del Centro. `actual` = la ultima carga; `anterior` = la ultima carga ANTES de esta visita.
    Una carga a menos de 30 min de la anterior es la misma visita (un refresco no mueve `anterior`)."""
    ahora = (ahora or datetime.now()).replace(microsecond=0)
    d = _leer_visita()
    try:
        actual = datetime.strptime(str(d.get("actual") or ""), _FMT_VISITA)
    except ValueError:
        actual = None
    if actual is not None and ahora - actual > HUECO_VISITA:
        d["anterior"] = actual.strftime(_FMT_VISITA)
    d["actual"] = ahora.strftime(_FMT_VISITA)
    d = {k: d[k] for k in ("anterior", "actual") if k in d}
    try:
        escribir_atomico(VISITA, json.dumps(d, indent=1) + "\n")
    except OSError:
        pass
    return d


def ultima_visita() -> datetime | None:
    try:
        return datetime.strptime(str(_leer_visita().get("anterior") or ""), _FMT_VISITA)
    except ValueError:
        return None


def visita_llana(ahora: datetime | None = None) -> str:
    """'hoy a las 00:25' / 'ayer a las 23:10' / 'el 12/10 a las 09:00'; '' si es la primera vez."""
    v = ultima_visita()
    return cuando_llano(v.strftime(_FMT_VISITA), ahora) if v else ""


_COMMIT = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,10}\b")


def _clave_grupo(t: dict) -> str:
    """Tareas del mismo commit, o de la misma epica/tema, salen juntas. Sin nada en comun, cada una su grupo."""
    m = _COMMIT.search(str((t.get("cierre") or {}).get("evidencia") or ""))
    if m:
        return "commit:" + m.group(0)[:7]
    et = t.get("etiquetas") or []
    for pref in ("epica:", "tema:"):
        e = next((x for x in et if x.startswith(pref)), "")
        if e:
            return e
    return "tarea:" + t["id"]


def _probada(t: dict) -> bool:
    return bool(t.get("testeado")) or (t.get("cierre") or {}).get("estado_real") == "HECHO Y TESTEADO"


def hecho_desde_visita(ahora: datetime | None = None, max_qwen: int = 3) -> dict:
    """Tareas cerradas como hechas desde la ultima visita (sin dato: ultimas 24 h), agrupadas por lo que cambia."""
    from interfaz import hecho_llano
    ahora = ahora or datetime.now()
    desde = ultima_visita() or (ahora - timedelta(hours=24))
    try:
        hechas = [t for t in T.cargar()["tareas"]
                  if t["estado"] == "hecha" and str(t.get("cerrada") or "") >= desde.strftime(_FMT_VISITA)]
    except Exception:   # noqa: BLE001
        hechas = []
    hechas.sort(key=lambda t: t.get("cerrada") or "", reverse=True)
    grupos: dict[str, list[dict]] = {}
    for t in hechas:
        grupos.setdefault(_clave_grupo(t), []).append(t)     # el dict conserva el orden: el grupo mas reciente primero
    salida = []
    usadas = 0
    for miembros in list(grupos.values())[:MAX_GRUPOS_HECHO]:
        cabeza = miembros[0]
        frase, segunda, de_qwen = hecho_llano.frase(cabeza, permitir_qwen=usadas < max_qwen)
        usadas += 1 if de_qwen else 0
        n = len(miembros)
        salida.append({"frase": frase + (f" · {n} cambios" if n > 1 else ""), "segunda": segunda, "n": n,
                       "probado": all(_probada(t) for t in miembros),
                       "novedad": any((t.get("cierre") or {}).get("novedad") is True for t in miembros),
                       "enlace": f"/tareas/{cabeza['id']}" if n == 1 else "/tareas?estado=hecha&orden=actualizada",
                       "hora": str(cabeza.get("cerrada") or "")[11:16]})
    try:   # T1020: grupo «Permisos que ha resuelto NEXO» (guardian, tribunal y revisor de reglas)
        from nucleo import guardian
        resueltos = guardian.resueltos_desde(desde)
    except Exception:   # noqa: BLE001 - la cola ilegible no tumba el Centro
        resueltos = []
    return {"grupos": salida, "total": len(hechas), "n_grupos": len(grupos), "visita": visita_llana(ahora),
            "ultimas_24h": ultima_visita() is None, "resueltos": resueltos[:MAX_RESUELTOS],
            "n_resueltos": len(resueltos), "n_resueltos_si": sum(1 for r in resueltos if r["aprobada"])}


# ------------------------------------------------------------------ Avisos que piden respuesta (T230 v2)
TIPOS_AVISO_RESPUESTA = {   # tipo de nucleo/avisos.py -> como se llama el grupo en el Centro
    "terminos": "Condiciones de un servicio que han cambiado",
    "disco_bajo": "Poco espacio en el disco",
    "sin_turno": "Tareas que nadie puede coger",
    "reels": "Fichas de reels por revisar",
    "decision": "Te pide una decisión",
    "pregunta": "Te hace una pregunta",
}
VENTANA_AVISOS = timedelta(days=3)   # los avisos no llevan "resuelto": uno sin atender deja de salir pasados 3 dias


def avisos_pendientes(ahora: datetime | None = None) -> dict:
    """Solo avisos que piden una respuesta de Damian, agrupados por tipo. El resto de `avisos.recientes()` es
    informativo (auditoria, modo, espejo, turnos...) y sigue en Detalle tecnico; las decisiones de la cola (permiso,
    R1/R2) ya estan en Te toca. Salen los de tipo en TIPOS_AVISO_RESPUESTA (o con `responder` verdadero) de los
    ultimos 3 dias y sin `resuelto`."""
    ahora = ahora or datetime.now()
    grupos: dict[str, list[dict]] = {}
    try:
        recientes = avisos.recientes(60)
    except Exception:   # noqa: BLE001
        recientes = []
    for a in recientes:
        if a.get("resuelto"):
            continue
        try:
            if ahora - datetime.strptime(str(a.get("cuando") or ""), "%Y-%m-%d %H:%M:%S") > VENTANA_AVISOS:
                continue
        except ValueError:
            continue
        nombre = TIPOS_AVISO_RESPUESTA.get(a.get("tipo")) or ("Espera tu respuesta" if a.get("responder") else "")
        if nombre:
            grupos.setdefault(nombre, []).append({"titulo": llano(a.get("titulo") or ""), "ruta": a.get("ruta") or "/"})
    return {"grupos": [{"nombre": n, "avisos": v[:3], "n": len(v)} for n, v in grupos.items()],
            "total": sum(len(v) for v in grupos.values())}


def radares_fila() -> dict:
    """Una tarjeta corta por radar para la fila de abajo del Centro."""
    try:
        from nucleo import radar
        lista = radar.vista_web(max_tarjetas=3, max_base=0)
    except Exception as e:   # noqa: BLE001
        return {"radares": [], "error": type(e).__name__}
    fila = []
    for r in lista:
        if r.get("error"):
            fila.append({"nombre": llano(r["nombre"]), "frase": "No se puede leer su configuración.", "novedades": []})
            continue
        tarjetas = r.get("tarjetas") or []
        if not r.get("activo"):
            frase = "Apagado."
        elif not r.get("ultima"):
            frase = "Todavía no ha buscado."
        else:
            frase = f"Última búsqueda: {str(r['ultima'])[:16].replace('T', ' ')}."
        fila.append({"nombre": llano(r["nombre"]), "frase": frase, "prueba": bool(r.get("simular")),
                     "novedades": [{"titulo": a.get("titulo", ""), "url": a.get("url", "")} for a in tarjetas[:3]]})
    return {"radares": fila, "error": ""}


def frase_estado() -> dict:
    """La frase de arriba del Centro: si NEXO funciona, que necesita de Damian y cuantas tareas suyas hay."""
    if parada.activa():
        return {"parada": True, "frase": "NEXO está parado: no empieza ningún trabajo hasta que pulses «Seguir»."}
    d = te_toca_llano(None)
    m = en_marcha_ahora()
    nd, nt = d["n_decisiones"], d["n_tareas"]
    prisa = "ninguna con prisa" if not d["con_fecha"] else f"{d['con_fecha']} con fecha límite"
    tareas = f"{nt} tarea{'s' if nt != 1 else ''} tuya{'s' if nt != 1 else ''}, {prisa}"
    decisiones = f"{nd} cosa{'s necesitan' if nd != 1 else ' necesita'} tu decisión"
    if nd and nt:
        espera = f"{decisiones} y tienes {tareas}."
    elif nd:
        espera = f"{decisiones}."
    elif nt:
        espera = f"Tienes {tareas}."
    else:
        espera = "Nada te espera."
    partes = ["NEXO funciona.", espera]
    if m["ahora"]:
        nombre = m["ahora"]["nombre"]
        partes.append(f"Ahora: {nombre[:1].lower()}{nombre[1:]}.")
    return {"parada": False, "frase": " ".join(partes), "cierre": parada.cierre_pedido()}
