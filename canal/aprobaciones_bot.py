"""Aprobaciones desde el movil (T154 fase F4, sobre la cola de T077).

Por que existe esto
-------------------
La cola de aprobaciones (nucleo/aprobaciones.py) guarda lo ambar que
espera a Damian, pero hasta ahora solo se podia contestar por la CLI del
PC. Si Damian esta fuera, lo pendiente caducaba sin que se enterase.
Esto le deja verlo y decidir desde Telegram:

- aviso automatico de cada peticion nueva, con botones Aprobar / Denegar;
- /aprobaciones: lista lo pendiente, cada una con sus botones;
- /aprobar <id> [motivo] y /denegar <id> [motivo]: lo mismo escrito.

Seguridad
---------
Solo es seguro porque el bot ya atiende SOLO al chat de Damian
(canal/bot.py, _es_del_dueno, hallazgo B de N04): el filtro se aplica
antes de llegar aqui. Cada decision queda en el historial encadenado de
la cola con quien="damian:telegram". El silencio sigue contando como NO:
lo que no se conteste caduca como siempre.

Todo son funciones que devuelven texto o mensajes ya formados; el envio
lo hace canal/bot.py. Asi se prueban sin Telegram (tests/test_aprobaciones_bot.py).
"""

from __future__ import annotations

from nucleo import aprobaciones

PREFIJO = "APR"
QUIEN = "damian:telegram"

# Cuantos ids avisados se recuerdan en estado_bot.json. Los ids no se
# repiten (A0001, A0002...), asi que basta con no crecer sin limite.
MAX_AVISADAS = 200


def teclado(id_: str) -> dict:
    return {"inline_keyboard": [[
        {"text": "✅ Aprobar", "callback_data": f"{PREFIJO}|{id_}|si"},
        {"text": "❌ Denegar", "callback_data": f"{PREFIJO}|{id_}|no"},
    ]]}


def texto_solicitud(s: dict) -> str:
    return (
        f"\U0001F6A6 Aprobacion {s['id']} ({s.get('origen') or '?'})\n"
        f"{s['accion']}:\n{s['detalle'][:1500]}\n\n"
        f"Caduca {s['vence']} (sin respuesta = NO)."
    )


def mensaje_solicitud(s: dict) -> dict:
    return {"text": texto_solicitud(s)[:4000], "reply_markup": teclado(s["id"])}


def cmd_lista() -> list[dict]:
    """/aprobaciones: un mensaje por pendiente (con botones), o uno que diga que no hay."""

    try:
        ps = aprobaciones.pendientes()
    except Exception as e:  # noqa: BLE001 - almacen roto: se dice, no se tapa
        return [{"text": f"No puedo leer la cola de aprobaciones: {e}"}]

    if not ps:
        return [{"text": "No hay nada esperando tu aprobacion."}]

    return [mensaje_solicitud(s) for s in ps[:10]] + (
        [{"text": f"... y {len(ps) - 10} mas. /aprobaciones otra vez tras contestar."}]
        if len(ps) > 10 else []
    )


def decidir(id_: str, aprobar: bool, motivo: str = "") -> str:
    fn = aprobaciones.aprobar if aprobar else aprobaciones.denegar

    try:
        s = fn(id_.strip().upper(), quien=QUIEN, motivo=motivo)
    except aprobaciones.NoEncontrada:
        return f"No existe la aprobacion {id_}."
    except aprobaciones.EstadoInvalido as e:
        return f"No se puede: {e}."
    except Exception as e:  # noqa: BLE001
        return f"No he podido decidir {id_}: {e}"

    if aprobar:
        return f"✅ {s['id']} aprobada. Vale una vez, hasta {s['vence']}."

    return f"❌ {s['id']} denegada."


def cmd_decidir(argumento: str, aprobar: bool) -> str:
    """/aprobar <id> [motivo] y /denegar <id> [motivo]."""

    partes = argumento.strip().split(maxsplit=1)

    if not partes:
        return f"Uso: /{'aprobar' if aprobar else 'denegar'} <id> [motivo]. Lista: /aprobaciones"

    return decidir(partes[0], aprobar, partes[1] if len(partes) > 1 else "")


def es_boton(data: str) -> bool:
    return data.startswith(PREFIJO + "|")


def boton(data: str) -> str:
    """Callback de los botones: APR|<id>|si o APR|<id>|no."""

    partes = data.split("|")

    if len(partes) != 3 or partes[2] not in ("si", "no"):
        return "Boton no valido."

    return decidir(partes[1], partes[2] == "si", "desde el boton")


def avisos_nuevos(estado: dict) -> list[dict]:
    """Mensajes para las pendientes que aun no se han avisado. Marca las avisadas en estado.

    Lo llama el bucle del bot en cada vuelta. Si la cola no se puede leer,
    no avisa de nada (y no revienta el bot: lo esencial es el canal).
    """

    try:
        ps = aprobaciones.pendientes()
    except Exception:  # noqa: BLE001
        return []

    avisadas = estado.setdefault("aprobaciones_avisadas", [])
    nuevas = [s for s in ps if s["id"] not in avisadas]

    for s in nuevas:
        avisadas.append(s["id"])

    del avisadas[:-MAX_AVISADAS]

    return [mensaje_solicitud(s) for s in nuevas]
