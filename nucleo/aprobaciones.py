"""Cola de aprobaciones persistente (T077): lo ambar no se pierde.

Por que existe esto
-------------------
Hasta ahora, cuando una accion salia ambar (nucleo/permisos.py lanza
NecesitaAprobacion), el servidor MCP devolvia un texto "preguntaselo a
Damian y vuelve a llamar con aprobado=True". Dos problemas:

1. Si Damian no estaba delante (turno desatendido), la peticion se
   perdia: no quedaba en ningun sitio. Nota del 23/09 en T077: "lo que
   necesite aprobacion debe quedar en cola persistente, no perderse".
2. `aprobado=True` es un booleano que pone quien llama. Nada comprueba
   que Damian haya dicho que si de verdad, ni a QUE dijo que si.

Este modulo resuelve el almacen. NO se engancha solo a nada: el punto
de enganche con manos/servidor_mcp.py y nucleo/permisos.py (blindados)
esta como propuesta en documentacion/propuestas/N04.patch.

Ciclo de vida de una solicitud
-------------------------------
    pendiente --aprobar()--> aprobada --consumir()--> usada
        |                        |
        |--denegar()--> denegada |--(sin usar a tiempo)--> caducada
        |--(sin respuesta a tiempo)--> caducada

- Solo se decide sobre una `pendiente`. Aprobar algo ya denegado o
  caducado revienta (EstadoInvalido): una decision no se reescribe.
- El silencio cuenta como NO: lo que nadie contesta, caduca (T154).
- Una aprobacion vale UNA vez y solo para la accion exacta aprobada:
  `consumir()` compara la huella (sha256 de accion + detalle completos).
  Aprobar "git push origin nube/N04" no autoriza "git push --force".
- Pedir dos veces lo mismo mientras sigue pendiente devuelve la misma
  solicitud: sin duplicados que Damian tenga que contestar dos veces.

Historial auditable
--------------------
Cada cambio queda en dos sitios:
- dentro de la solicitud (`eventos`), para leerlo junto a ella;
- en memoria/aprobaciones_historial.jsonl, solo-anadir, una linea por
  evento, encadenada con sha256 (cada linea lleva la huella de la
  anterior). `verificar_historial()` recorre la cadena: si alguien
  edita o borra una linea del medio, la cadena se rompe y se ve donde.
  No impide editar (nada en disco lo impide); lo hace EVIDENTE.

Disco
-----
Escritura atomica (nucleo.escritura) + candado entre procesos
(nucleo.candado), igual que nucleo/tareas.py. Si el JSON esta roto,
cargar() revienta a proposito: una cola vacia escrita encima de la
buena es como se pierden las cosas (mismo criterio que hallazgo D1).

CLI:
    python -m nucleo.aprobaciones pendientes
    python -m nucleo.aprobaciones ver A0003
    python -m nucleo.aprobaciones aprobar A0003 [--quien damian] [motivo]
    python -m nucleo.aprobaciones denegar A0003 [--quien damian] [motivo]
    python -m nucleo.aprobaciones caducar
    python -m nucleo.aprobaciones verificar
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from nucleo.candado import bloqueo
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico


ALMACEN = RAIZ / "memoria" / "aprobaciones.json"
HISTORIAL = RAIZ / "memoria" / "aprobaciones_historial.jsonl"
CANDADO = RAIZ / "memoria" / ".candado_aprobaciones.lock"

ESTADOS = ("pendiente", "aprobada", "denegada", "caducada", "usada")
ABIERTOS = ("pendiente", "aprobada")  # los que aun pueden cambiar

# Cuanto espera una pregunta sin respuesta antes de contar como NO, y
# cuanto vale un si antes de usarse. Cortos a proposito: un si de ayer
# para algo que ya no se recuerda no es un si.
TTL_PENDIENTE = timedelta(hours=24)
TTL_APROBADA = timedelta(hours=2)

# T967 (Damian 17/10): el plazo del veto R1 baja de 24 h a 8 h (el silencio sigue valiendo como si). Si la R1 pasa
# antes por el tribunal (nucleo/tribunal_r1.py), el plazo de 8 h solo empieza a correr cuando llega a su bandeja:
# mientras tanto el tribunal tiene hasta ESPERA_TRIBUNAL para dictaminar (pasado ese tiempo, cae a Damian igual).
TTL_VETO = timedelta(hours=8)
ESPERA_TRIBUNAL = timedelta(hours=4)

# T668 (F2): solicitudes de la matriz de riesgo. R1 = veto (si nadie dice NO a tiempo, queda aprobada);
# R2 = OK normal (el silencio es NO). El bot de Telegram no las ve: pendientes() solo las da si se piden.
NIVELES_MATRIZ = ("R1", "R2")
TIPOS = ("normal", "veto")

# Damian 05/10 (A0015 caduco con el PC apagado): los plazos solo corren con NEXO encendido. La web deja un
# latido (latir()) cada minuto; un hueco de mas de HUECO_APAGADO sin latido es tiempo apagado y se suma a los
# plazos abiertos. Sin archivo de latido (tests, NEXO sin web) todo sigue como antes.
HUECO_APAGADO = timedelta(minutes=5)

# T890 (14/10, A0050 vetada sin querer): un veto R1 se puede deshacer, solo Damian desde la web, durante 7 dias y
# mientras su tarea siga sin cerrarse.
VENTANA_DESHACER = timedelta(days=7)

FORMATO = "%Y-%m-%d %H:%M:%S"
GENESIS = "0" * 64  # huella "anterior" de la primera linea del historial


class EstadoInvalido(ValueError):
    """Se intento decidir sobre una solicitud que ya no esta abierta."""


class NoEncontrada(KeyError):
    """No hay solicitud con ese id."""


class NoCoincide(PermissionError):
    """La aprobacion existe, pero no es para esta accion exacta."""


# ------------------------------------------------------------ utilidades

def _ahora() -> datetime:
    return datetime.now().replace(microsecond=0)


def _txt(d: datetime) -> str:
    return d.strftime(FORMATO)


def _fecha(s: str) -> datetime:
    return datetime.strptime(s, FORMATO)


def huella(accion: str, detalle: str) -> str:
    """Identidad de una accion: la accion y el detalle COMPLETOS.

    Separador \\x00 para que ("ab", "c") y ("a", "bc") no coincidan.
    """

    return hashlib.sha256(f"{accion}\x00{detalle}".encode("utf-8")).hexdigest()


def _sha_linea(linea: str) -> str:
    return hashlib.sha256(linea.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------- disco

def cargar() -> dict:
    """Lee el almacen. Si no existe, cola vacia; si esta roto, revienta."""

    if not ALMACEN.is_file():
        return {"version": 1, "siguiente_id": 1, "solicitudes": []}

    datos = json.loads(ALMACEN.read_text(encoding="utf-8"))

    datos.setdefault("version", 1)
    datos.setdefault("siguiente_id", 1)
    datos.setdefault("solicitudes", [])

    return datos


def _guardar(datos: dict) -> None:
    escribir_atomico(ALMACEN, json.dumps(datos, ensure_ascii=False, indent=2) + "\n")


def _ultima_huella_historial() -> str:
    if not HISTORIAL.is_file():
        return GENESIS

    ultima = ""

    with HISTORIAL.open(encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                ultima = linea.rstrip("\n")

    return _sha_linea(ultima) if ultima else GENESIS


def _anotar_historial(evento: dict) -> None:
    """Anade una linea encadenada al historial. Solo anadir, nunca reescribir.

    Se llama con el candado puesto, asi que nadie mete una linea entre
    leer la ultima huella y escribir la nueva.
    """

    registro = {"anterior": _ultima_huella_historial(), **evento}
    linea = json.dumps(registro, ensure_ascii=False, sort_keys=True)

    HISTORIAL.parent.mkdir(parents=True, exist_ok=True)

    with HISTORIAL.open("a", encoding="utf-8", newline="\n") as f:
        f.write(linea + "\n")
        f.flush()


def _evento(s: dict, tipo: str, cuando: datetime, quien: str, motivo: str) -> None:
    e = {"cuando": _txt(cuando), "tipo": tipo, "quien": quien, "motivo": motivo}

    s["eventos"].append(e)
    _anotar_historial({"id": s["id"], "huella": s["huella"], **e})


def _buscar(datos: dict, id_: str) -> dict:
    for s in datos["solicitudes"]:
        if s["id"] == id_:
            return s

    raise NoEncontrada(id_)


def _ruta_latido() -> Path:
    # Junto al almacen: los tests que lo mueven a tmp_path se llevan tambien el latido.
    return ALMACEN.with_name("aprobaciones_latido.json")


def _leer_latido() -> datetime | None:
    try:
        return _fecha(json.loads(_ruta_latido().read_text(encoding="utf-8"))["latido"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def hueco_apagado(ahora: datetime | None = None) -> timedelta:
    """Tiempo sin latido aun no sumado a los plazos (0 si no hay hueco o no hay latido)."""

    ahora = ahora or _ahora()
    ultimo = _leer_latido()

    if ultimo is None or ahora - ultimo <= HUECO_APAGADO:
        return timedelta(0)

    return ahora - ultimo


def latir(ahora: datetime | None = None) -> timedelta:
    """La web lo llama cada minuto. Si venia de un hueco (PC apagado), alarga los plazos abiertos lo que
    duro el hueco y lo apunta en cada solicitud. Devuelve el hueco aplicado."""

    ahora = ahora or _ahora()

    with bloqueo(CANDADO):
        hueco = hueco_apagado(ahora)

        if hueco and ALMACEN.is_file():
            datos = cargar()
            if _alargar_plazos(datos, hueco, ahora):
                _guardar(datos)

        escribir_atomico(_ruta_latido(), json.dumps({"latido": _txt(ahora)}) + "\n")

        return hueco


def _alargar_plazos(datos: dict, hueco: timedelta, ahora: datetime) -> bool:
    cambiado = False

    for s in datos["solicitudes"]:
        if s["estado"] in ABIERTOS and s.get("vence"):
            s["vence"] = _txt(_fecha(s["vence"]) + hueco)
            _evento(s, "plazo_ampliado", ahora, "sistema",
                    f"NEXO estuvo apagado {int(hueco.total_seconds() // 60)} min: el plazo no corre apagado")
            cambiado = True

    return cambiado


def _vencida(s: dict, ahora: datetime) -> bool:
    if s["estado"] not in ABIERTOS or not s.get("vence"):
        return False

    # Un hueco aun no aplicado (la web acaba de arrancar) no cuenta como tiempo pasado.
    return _fecha(s["vence"]) + hueco_apagado(ahora) <= ahora


def _caducar_en(datos: dict, ahora: datetime) -> list[str]:
    """Marca como caducadas las abiertas que han pasado su plazo."""

    ids = []

    for s in datos["solicitudes"]:
        if _vencida(s, ahora) and s["estado"] == "pendiente" and s.get("tipo") == "veto":
            # T668: R1. Nadie dijo NO en el plazo: el silencio vale si (decision de Damian, plan §4).
            s["estado"] = "aprobada"
            s["vence"] = _txt(ahora + _ttl_aprobada(s))
            s["decidida_por"] = "silencio"
            if s.get("tribunal", {}).get("estado") == "pendiente":
                s["tribunal"]["estado"] = "sin_dictamen"   # el tribunal no llego a tiempo: decidio el silencio
            _evento(s, "aprobada_por_silencio", ahora, "sistema", "nadie dijo NO en el plazo del veto")
            continue
        if _vencida(s, ahora):
            previo = s["estado"]
            s["estado"] = "caducada"
            _evento(
                s, "caducada", ahora, "sistema",
                "sin respuesta a tiempo" if previo == "pendiente"
                else "aprobada pero no usada a tiempo",
            )
            ids.append(s["id"])

    return ids


def _ttl_aprobada(s: dict) -> timedelta:
    return timedelta(seconds=s["ttl_aprobada_s"]) if s.get("ttl_aprobada_s") else TTL_APROBADA


# ------------------------------------------------------------------- API

def solicitar(
    accion: str,
    detalle: str = "",
    nivel: str = "ambar",
    origen: str = "",
    ahora: datetime | None = None,
    ttl: timedelta | None = None,
    tipo: str = "normal",
    ttl_aprobada: timedelta | None = None,
    extra: dict | None = None,
    espera_tribunal: timedelta | None = None,
) -> dict:
    """Da de alta una peticion de aprobacion. Devuelve la solicitud.

    Si ya hay una PENDIENTE con la misma huella, devuelve esa (sin
    duplicar). Una aprobada sin usar tambien se devuelve: quien pide
    otra vez lo mismo lo que necesita es consumirla.

    T668: `tipo="veto"` = el silencio en el plazo vale si (solo R1); `ttl_aprobada` = cuanto vale el si antes de
    usarse (por defecto 2 h); `extra` = datos para pintar (resumen, diff resumido) que NO entran en la huella.
    T967: `espera_tribunal` (solo veto R1) = la R1 espera primero al tribunal; su plazo `ttl` empieza a contar
    cuando el tribunal la manda a la bandeja de Damian (registrar_tribunal), con ese margen de espera como tope.
    """

    if tipo not in TIPOS:
        raise ValueError(f"tipo desconocido: {tipo}")

    if espera_tribunal and not (tipo == "veto" and nivel == "R1"):
        raise ValueError("el tribunal solo juzga vetos R1 (nunca R2 ni R3)")

    ahora = ahora or _ahora()
    h = huella(accion, detalle)

    with bloqueo(CANDADO):
        datos = cargar()
        _caducar_en(datos, ahora)

        for s in datos["solicitudes"]:
            if s["huella"] == h and s["estado"] in ABIERTOS:
                _guardar(datos)
                return s

        s = {
            "id": f"A{datos['siguiente_id']:04d}",
            "accion": accion,
            "detalle": detalle,
            "nivel": nivel,
            "origen": origen,
            "huella": h,
            "estado": "pendiente",
            "creada": _txt(ahora),
            "vence": _txt(ahora + (ttl or TTL_PENDIENTE) + (espera_tribunal or timedelta(0))),
            "eventos": [],
        }
        if espera_tribunal:
            s["tribunal"] = {"estado": "pendiente"}
        if tipo != "normal":
            s["tipo"] = tipo
        if ttl_aprobada:
            s["ttl_aprobada_s"] = int(ttl_aprobada.total_seconds())
        if extra:
            s["extra"] = extra

        datos["siguiente_id"] += 1
        datos["solicitudes"].append(s)
        _evento(s, "alta", ahora, origen or "desconocido", "")
        _guardar(datos)

    # T1020: el guardian la mira en cuanto entra (fuera del candado: puede aprobarla o mandarla al tribunal). Si falla,
    # la solicitud sigue tal cual y el barrido del planificador la recoge al minuto.
    return _gancho_guardian(s)


def _gancho_guardian(s: dict) -> dict:
    try:
        from nucleo import guardian
        return guardian.al_solicitar(s) or s
    except Exception:   # noqa: BLE001 - el guardian nunca impide dar de alta una solicitud
        return s


def _decidir(id_: str, nuevo: str, quien: str, motivo: str, ahora: datetime | None) -> dict:
    ahora = ahora or _ahora()

    with bloqueo(CANDADO):
        datos = cargar()
        _caducar_en(datos, ahora)
        s = _buscar(datos, id_)

        if s["estado"] != "pendiente":
            _guardar(datos)  # por si acaba de caducar: que quede escrito
            raise EstadoInvalido(f"{id_} esta {s['estado']}, no pendiente")

        s["estado"] = nuevo
        s["decidida_por"] = quien   # T967: quien decidio (tribunal / damian / silencio)

        if s.get("tribunal", {}).get("estado") == "pendiente":
            s["tribunal"]["estado"] = "superado"   # Damian se adelanto: el tribunal ya no tiene nada que juzgar

        if nuevo == "aprobada":
            s["vence"] = _txt(ahora + _ttl_aprobada(s))

        _evento(s, nuevo, ahora, quien, motivo)
        _guardar(datos)

        return s


def aprobar(id_: str, quien: str = "damian", motivo: str = "", ahora: datetime | None = None) -> dict:
    """Damian dice que si. Solo sobre una pendiente."""

    return _decidir(id_, "aprobada", quien, motivo, ahora)


def denegar(id_: str, quien: str = "damian", motivo: str = "", ahora: datetime | None = None) -> dict:
    """Damian dice que no. Solo sobre una pendiente."""

    return _decidir(id_, "denegada", quien, motivo, ahora)


def registrar_tribunal(id_: str, resultado: str, dictamenes: list[dict], motivo: str = "",
                       ahora: datetime | None = None) -> dict:
    """T967: el tribunal dejo su dictamen sobre un veto R1 que esperaba. `resultado`:
    'aprobar' (3/3 APROBAR -> aprobada, decidida_por='tribunal'), 'vetar' (3/3 VETAR -> denegada, decidida_por=
    'tribunal'; se deshace con 'Deshacer veto') o 'bandeja' (cualquier otro caso: sigue pendiente y empieza a
    correr el plazo de TTL_VETO para Damian, con los dictamenes a la vista). Solo sobre una R1 pendiente cuyo
    tribunal este pendiente: lo demas revienta (EstadoInvalido)."""
    if resultado not in ("aprobar", "vetar", "bandeja"):
        raise ValueError(f"resultado desconocido: {resultado}")

    ahora = ahora or _ahora()

    with bloqueo(CANDADO):
        datos = cargar()
        _caducar_en(datos, ahora)
        s = _buscar(datos, id_)

        if s["estado"] != "pendiente" or s.get("tribunal", {}).get("estado") != "pendiente":
            _guardar(datos)
            raise EstadoInvalido(f"{id_} no espera al tribunal (estado {s['estado']})")

        via = s["tribunal"].get("via", "")
        s["tribunal"] = {"estado": "bandeja" if resultado == "bandeja" else "decidido", "resultado": resultado,
                         "cuando": _txt(ahora), "motivo": motivo, "dictamenes": dictamenes}
        if via:
            s["tribunal"]["via"] = via

        if resultado == "bandeja":
            if s.get("tipo") == "veto":
                s["vence"] = _txt(ahora + TTL_VETO)   # ahora corre el plazo de Damian
            s["tribunal"]["via"] = via   # T1020: se conserva por que camino llego al tribunal
            _evento(s, "tribunal_a_bandeja", ahora, "tribunal", motivo)
        else:
            s["estado"] = "aprobada" if resultado == "aprobar" else "denegada"
            s["decidida_por"] = "tribunal"

            if resultado == "aprobar":
                s["vence"] = _txt(ahora + _ttl_aprobada(s))

            _evento(s, s["estado"], ahora, "tribunal", motivo)

        _guardar(datos)

        return s


def anotar_explicacion(id_: str, explicacion: dict) -> dict:
    """T1020: guarda la ficha en llano del guardian en extra.explicacion. No es una decision: no toca el estado, ni la
    huella (extra no entra en ella), ni el historial encadenado."""
    with bloqueo(CANDADO):
        datos = cargar()
        s = _buscar(datos, id_)
        s.setdefault("extra", {})["explicacion"] = explicacion
        _guardar(datos)
        return s


def a_tribunal(id_: str, motivo: str, quien: str = "guardian", ahora: datetime | None = None) -> dict:
    """T1020: el guardian manda una solicitud AMBAR o R2 pendiente al tribunal de 3 familias (nucleo/guardian.py).
    El dictamen llega por registrar_tribunal; su plazo no cambia (lo ambar sigue caducando a las 24 h, la R2 a los
    7 dias). Solo sobre una pendiente que no este ya con el tribunal; nunca R1 (esas van por espera_tribunal) ni R3."""
    ahora = ahora or _ahora()

    with bloqueo(CANDADO):
        datos = cargar()
        _caducar_en(datos, ahora)
        s = _buscar(datos, id_)

        if s["estado"] != "pendiente" or s.get("tribunal") or s.get("nivel") not in ("ambar", "R2"):
            _guardar(datos)
            raise EstadoInvalido(f"{id_} no puede ir al tribunal (estado {s['estado']}, nivel {s.get('nivel')})")

        s["tribunal"] = {"estado": "pendiente", "via": "guardian", "desde": _txt(ahora)}
        _evento(s, "a_tribunal", ahora, quien, motivo)
        _guardar(datos)

        return s


def consumir(id_: str, accion: str, detalle: str = "", ahora: datetime | None = None) -> dict:
    """Gasta una aprobacion para ejecutar la accion. Vale una sola vez.

    Revienta si no existe (NoEncontrada), si no esta aprobada o ya se
    uso o caduco (EstadoInvalido), o si la accion no es exactamente la
    aprobada (NoCoincide). Quien ejecute debe hacerlo SOLO si esto
    vuelve sin excepcion.
    """

    ahora = ahora or _ahora()

    with bloqueo(CANDADO):
        datos = cargar()
        _caducar_en(datos, ahora)
        s = _buscar(datos, id_)

        if s["estado"] != "aprobada":
            _guardar(datos)
            raise EstadoInvalido(f"{id_} esta {s['estado']}, no aprobada")

        if s["huella"] != huella(accion, detalle):
            _anotar_historial({
                "id": id_, "huella": s["huella"], "cuando": _txt(ahora),
                "tipo": "rechazo_consumo", "quien": "sistema",
                "motivo": "la accion no coincide con la aprobada",
            })
            _guardar(datos)
            raise NoCoincide(f"{id_} no aprueba esta accion")

        s["estado"] = "usada"
        s["vence"] = None
        _evento(s, "usada", ahora, "sistema", "")
        _guardar(datos)

        return s


def _fecha_veto(s: dict) -> datetime | None:
    """Cuando dijo NO Damian (ultimo evento 'denegada')."""
    cuando = [e["cuando"] for e in s.get("eventos", []) if e.get("tipo") == "denegada"]
    return _fecha(cuando[-1]) if cuando else None


def _tarea_cerrada(s: dict) -> str:
    """'' si la tarea del veto sigue abierta (o no hay tarea que mirar); si no, su estado final."""
    id_tarea = (s.get("extra") or {}).get("tarea")
    if not id_tarea:
        return ""
    from nucleo import tareas as T
    t = T.buscar(id_tarea)
    return t["estado"] if t and t.get("estado") in T.CERRADOS else ""


def _porque_no_se_deshace(datos: dict, s: dict, ahora: datetime) -> str:
    """'' si el veto se puede deshacer; si no, el motivo."""
    if s.get("tipo") != "veto" or s.get("nivel") != "R1":
        return f"{s['id']} no es un veto R1"
    if s["estado"] != "denegada":
        return f"{s['id']} esta {s['estado']}, no vetada"
    cuando = _fecha_veto(s)
    if cuando is None or ahora - cuando >= VENTANA_DESHACER:
        return f"{s['id']} se vetó hace más de {VENTANA_DESHACER.days} días"
    cerrada = _tarea_cerrada(s)
    if cerrada:
        return f"la tarea {s['extra']['tarea']} ya está {cerrada}: no hay nada que deshacer"
    if any(o is not s and o["huella"] == s["huella"] and o["estado"] in ABIERTOS for o in datos["solicitudes"]):
        return f"ya hay otra solicitud abierta para lo mismo que {s['id']}"
    return ""


def vetos_deshacibles(ahora: datetime | None = None) -> list[dict]:
    """Los R1 vetados que aun se pueden deshacer (para pintarlos en el Centro). Solo lee."""
    ahora = ahora or _ahora()
    datos = cargar()
    return [s for s in datos["solicitudes"] if not _porque_no_se_deshace(datos, s, ahora)]


def deshacer_veto(id_: str, quien: str = "damian", motivo: str = "", ahora: datetime | None = None) -> dict:
    """T890: Damian se arrepiente de un veto R1. La solicitud vuelve a `pendiente` con un plazo de veto NUEVO
    (TTL_VETO desde ahora; si nadie vuelve a vetar, vale si, como cualquier R1). Solo se puede si: es un veto R1 en
    estado `denegada`, se vetó hace menos de 7 dias, su tarea no esta cerrada y no hay otra solicitud abierta
    para lo mismo. Queda en el historial encadenado. Solo la llama la web (Damian)."""
    ahora = ahora or _ahora()

    with bloqueo(CANDADO):
        datos = cargar()
        _caducar_en(datos, ahora)
        s = _buscar(datos, id_)
        motivo_no = _porque_no_se_deshace(datos, s, ahora)

        if motivo_no:
            _guardar(datos)
            raise EstadoInvalido(motivo_no)

        s["estado"] = "pendiente"
        s["vence"] = _txt(ahora + TTL_VETO)
        s.pop("decidida_por", None)
        _evento(s, "veto_deshecho", ahora, quien, motivo)
        _guardar(datos)

        return s


def caducar(ahora: datetime | None = None) -> list[str]:
    """Pasa a caducada todo lo abierto fuera de plazo. Devuelve los ids."""

    ahora = ahora or _ahora()

    with bloqueo(CANDADO):
        datos = cargar()
        antes = json.dumps(datos, sort_keys=True)
        ids = _caducar_en(datos, ahora)

        if ids or json.dumps(datos, sort_keys=True) != antes:  # T668: un veto aprobado por silencio tambien
            _guardar(datos)

        return ids


def pendientes(ahora: datetime | None = None, incluir_matriz: bool = False) -> list[dict]:
    """Lo que espera a Damian. Solo lee: lo vencido no sale, aunque no
    este marcado aun (eso lo hace caducar()).

    T668: las R1/R2 de la matriz de riesgo solo salen con incluir_matriz=True
    (las pinta el Centro de la web; el bot de Telegram no recibe nada nuevo)."""

    ahora = ahora or _ahora()

    return [
        s for s in cargar()["solicitudes"]
        if s["estado"] == "pendiente" and not _vencida(s, ahora)
        and (incluir_matriz or s.get("nivel") not in NIVELES_MATRIZ)
    ]


def ver(id_: str) -> dict:
    return _buscar(cargar(), id_)


def historial() -> list[dict]:
    if not HISTORIAL.is_file():
        return []

    return [
        json.loads(l) for l in HISTORIAL.read_text(encoding="utf-8").splitlines() if l.strip()
    ]


def verificar_historial() -> tuple[bool, int | None]:
    """Comprueba la cadena. (True, None) si esta entera; si no, (False, n)
    con n = numero de linea (desde 1) donde se rompe."""

    if not HISTORIAL.is_file():
        return True, None

    anterior = GENESIS

    for n, linea in enumerate(HISTORIAL.read_text(encoding="utf-8").splitlines(), 1):
        if not linea.strip():
            continue

        try:
            registro = json.loads(linea)
        except json.JSONDecodeError:
            return False, n

        if registro.get("anterior") != anterior:
            return False, n

        anterior = _sha_linea(linea)

    return True, None


# ------------------------------------------------------------------- CLI

def _linea(s: dict) -> str:
    return f"{s['id']} [{s['estado']}] {s['accion']}: {s['detalle'][:100]} (vence {s['vence']})"


def _autor_cli(args: list[str]) -> tuple[str, list[str]]:
    """T198: quien decide de verdad. --quien X manda; si no, Claude Code se delata por CLAUDECODE;
    si no, no se sabe y se dice (antes firmaba siempre 'damian')."""

    if "--quien" in args:
        i = args.index("--quien")
        if i + 1 < len(args):
            return args[i + 1], args[:i] + args[i + 2:]

    if os.environ.get("CLAUDECODE"):
        return "claude-code", args

    return "cli (sin identificar)", args


def main(argv: list[str]) -> int:
    orden = argv[0] if argv else "pendientes"
    resto = argv[1:]

    try:
        if orden == "pendientes":
            ps = pendientes()
            print("\n".join(_linea(s) for s in ps) if ps else "Nada pendiente.")

        elif orden == "ver" and resto:
            print(json.dumps(ver(resto[0]), ensure_ascii=False, indent=2))

        elif orden in ("aprobar", "denegar") and resto:
            fn = aprobar if orden == "aprobar" else denegar
            quien, motivo = _autor_cli(resto[1:])
            print(_linea(fn(resto[0], quien=quien, motivo=" ".join(motivo))))

        elif orden == "caducar":
            ids = caducar()
            print("Caducadas: " + (", ".join(ids) if ids else "ninguna"))

        elif orden == "verificar":
            ok, n = verificar_historial()
            print("Historial integro." if ok else f"HISTORIAL ROTO en la linea {n}.")
            return 0 if ok else 2

        else:
            print(__doc__.split("CLI:")[1])
            return 1

    except (NoEncontrada, EstadoInvalido) as e:
        print(f"ERROR: {e}")
        return 1

    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    sys.exit(main(sys.argv[1:]))
