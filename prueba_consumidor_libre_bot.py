"""Prueba de T082 Pieza 1: mensajes sueltos de Telegram ofrecidos a
consumidor_libres.py en vivo (canal/bot.py).

Mismo patron que prueba_router_libre_bot.py: cubre
_avisar_con_consumidor_libres con consumidor_libres.procesar_uno()
mockeado (rapido, deterministico, sin gastar Qwen de verdad ni tocar
memoria/tareas.json), y el disparo de los tres hilos (Qwen, Router,
consumidor_libres) desde procesar_updates(). El extremo real (Qwen
clasificando de verdad, tareas.anadir() escribiendo en el almacen
real) ya se probo en la ronda 28 contra los 4 mensajes libre_*.json
reales pendientes desde el 14/09 -- no se repite aqui.
"""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import logging  # noqa: E402
logging.disable(logging.INFO)

from nucleo import registro  # noqa: E402
registro.aislar()  # T198: sus logs (401 simulados...) no van a registros/ reales

import canal.bot as bot  # noqa: E402

# Aislado del config.toml real (N01/H01): con canal.chat_id fijo, el dueno
# seria el chat real de Damian y no el chat falso de esta prueba.
_valor_real = bot.valor
bot.valor = lambda ruta, defecto=None: 0 if ruta == "canal.chat_id" else _valor_real(ruta, defecto)

SALIDA = RAIZ / "registros" / "prueba_consumidor_libre_bot.txt"
SALIDA.parent.mkdir(parents=True, exist_ok=True)

lineas: list[str] = []
fallos = 0


def anotar(texto: str = "") -> None:
    print(texto, flush=True)
    lineas.append(str(texto))
    SALIDA.write_text("\n".join(lineas), encoding="utf-8")


def comprobar(titulo: str, condicion: bool, detalle: str = "") -> None:
    global fallos

    if condicion:
        anotar(f"  VALE  {titulo}")
    else:
        fallos += 1
        anotar(f"  FALLA {titulo} {detalle}")


anotar(f"CONSUMIDOR_LIBRES EN VIVO EN TELEGRAM (T082 Pieza 1)  {time.strftime('%Y-%m-%d %H:%M:%S')}")
anotar("=" * 60)


anotar("\n1. Flag apagado: no llama a consumidor_libres en absoluto")

try:
    bot.CONSUMIDOR_LIBRES_RESPONDE = False

    with mock.patch("consumidor_libres.procesar_uno") as procesar_falso:
        bot._avisar_con_consumidor_libres(999, {"archivo": "libre_falso.json", "hora": "10:00", "texto": "algo"})

        comprobar("procesar_uno ni se llama", procesar_falso.call_count == 0)
finally:
    bot.CONSUMIDOR_LIBRES_RESPONDE = True


anotar("\n2. Qwen no disponible: no llama a procesar_uno, no revienta")

try:
    with mock.patch("extremidades.qwen.disponible", return_value=False), \
         mock.patch("consumidor_libres.procesar_uno") as procesar_falso:
        bot._avisar_con_consumidor_libres(999, {"archivo": "x.json", "hora": "10:00", "texto": "algo"})

    comprobar("procesar_uno ni se llama sin Qwen", procesar_falso.call_count == 0)
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 2:")
    anotar(traceback.format_exc())


anotar("\n3. procesar_uno() crea la tarea (mockeado) -> se manda el aviso con id y titulo")

try:
    resultado_falso = {"archivo": "libre_falso1.json", "resultado": "TAREA_CREADA", "tarea_id": "T999", "titulo": "Revisar el recibo de la luz"}
    mensaje_libre = {"archivo": "libre_falso1.json", "hora": "2026-09-22 10:00:00", "texto": "acuerdate de revisar el recibo"}

    enviados = []

    class _RespuestaOK:
        def raise_for_status(self) -> None:
            pass

    class _ClienteFalso:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, **k):
            enviados.append(json)
            return _RespuestaOK()

    with mock.patch("extremidades.qwen.disponible", return_value=True), \
         mock.patch("consumidor_libres.procesar_uno", return_value=resultado_falso) as procesar_falso, \
         mock.patch("canal.bot.httpx.Client", return_value=_ClienteFalso()):
        bot._avisar_con_consumidor_libres(555, mensaje_libre)

    comprobar("procesar_uno() se llama con el mensaje tal cual", procesar_falso.call_args[0][0] == mensaje_libre)
    comprobar("se manda exactamente un mensaje", len(enviados) == 1, enviados)
    if enviados:
        comprobar("va al chat correcto", enviados[0].get("chat_id") == 555, enviados[0])
        comprobar("menciona el id de la tarea", "T999" in enviados[0].get("text", ""), enviados[0])
        comprobar("menciona el titulo", "Revisar el recibo de la luz" in enviados[0].get("text", ""), enviados[0])
        comprobar("va sin sonido", enviados[0].get("disable_notification") is True, enviados[0])
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 3:")
    anotar(traceback.format_exc())


anotar("\n4. procesar_uno() dice que no es tarea (mockeado) -> no se manda nada")

try:
    resultado_falso = {"archivo": "libre_falso2.json", "resultado": "NO_ES_TAREA", "categoria": "respuesta"}
    mensaje_libre = {"archivo": "libre_falso2.json", "hora": "2026-09-22 10:05:00", "texto": "no quiero que lo apuntes como tarea"}

    enviados = []

    class _ClienteFalso2:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, **k):
            enviados.append(json)

    with mock.patch("extremidades.qwen.disponible", return_value=True), \
         mock.patch("consumidor_libres.procesar_uno", return_value=resultado_falso), \
         mock.patch("canal.bot.httpx.Client", return_value=_ClienteFalso2()):
        bot._avisar_con_consumidor_libres(555, mensaje_libre)

    comprobar("no se manda ningun mensaje", len(enviados) == 0, enviados)
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 4:")
    anotar(traceback.format_exc())


anotar("\n5. procesar_uno() revienta -> no se propaga la excepcion, no se manda nada")

try:
    enviados = []

    class _ClienteFalso3:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, **k):
            enviados.append(json)

    with mock.patch("extremidades.qwen.disponible", return_value=True), \
         mock.patch("consumidor_libres.procesar_uno", side_effect=RuntimeError("fallo forzado")), \
         mock.patch("canal.bot.httpx.Client", return_value=_ClienteFalso3()):
        bot._avisar_con_consumidor_libres(555, {"archivo": "x.json", "hora": "10:00", "texto": "algo"})

    comprobar("no revienta y no manda nada", len(enviados) == 0, enviados)
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 5 (no deberia escapar ninguna):")
    anotar(traceback.format_exc())


anotar(
    "\n6. procesar_updates(): un mensaje suelto dispara el hilo de "
    "consumidor_libres ademas de Qwen/Router (y no lo dispara con el flag apagado)"
)

try:
    import json  # noqa: F401

    class _RespuestaOKu:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "result": [{
                    "update_id": 10,
                    "message": {
                        "chat": {"id": 777},
                        "text": "un mensaje suelto cualquiera",
                    },
                }],
            }

    class _ClienteFalsoU:
        def get(self, *a, **k):
            return _RespuestaOKu()

        def post(self, *a, **k):
            return _RespuestaOKu()

    hilos_lanzados = []

    class _HiloFalso:
        def __init__(self, target=None, args=(), daemon=None, **kw):
            hilos_lanzados.append(target.__name__ if target else None)

        def start(self) -> None:
            pass

    estado_falso = {"offset": 0, "chat_id": 777}

    with mock.patch("canal.bot.threading.Thread", _HiloFalso), \
         mock.patch("canal.bot.anotar_libre", return_value={"archivo": "x.json", "hora": "10:00", "texto": "y"}), \
         mock.patch("canal.bot.SALIDA", RAIZ / "_no_existe_" / "salida"):
        bot.procesar_updates(_ClienteFalsoU(), estado_falso)

    comprobar(
        "se lanza el hilo de consumidor_libres",
        "_avisar_con_consumidor_libres" in hilos_lanzados,
        hilos_lanzados,
    )

    hilos_lanzados.clear()
    estado_falso = {"offset": 1, "chat_id": 777}

    bot.CONSUMIDOR_LIBRES_RESPONDE = False

    with mock.patch("canal.bot.threading.Thread", _HiloFalso), \
         mock.patch("canal.bot.anotar_libre", return_value={"archivo": "x.json", "hora": "10:00", "texto": "y"}), \
         mock.patch("canal.bot.SALIDA", RAIZ / "_no_existe_" / "salida"):
        bot.procesar_updates(_ClienteFalsoU(), estado_falso)

    bot.CONSUMIDOR_LIBRES_RESPONDE = True

    comprobar(
        "con el flag apagado NO se lanza el hilo de consumidor_libres",
        "_avisar_con_consumidor_libres" not in hilos_lanzados,
        hilos_lanzados,
    )
    comprobar(
        "con el flag apagado los otros dos se lanzan igual",
        "_avisar_con_qwen" in hilos_lanzados and "_avisar_con_router" in hilos_lanzados,
        hilos_lanzados,
    )
except Exception:
    fallos += 1
    bot.CONSUMIDOR_LIBRES_RESPONDE = True
    anotar("EXCEPCION en caso 6:")
    anotar(traceback.format_exc())


anotar("\n" + ("TODO VALE" if fallos == 0 else f"{fallos} FALLOS"))
anotar("FIN")
