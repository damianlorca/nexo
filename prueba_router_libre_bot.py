"""Prueba de T073: mensajes sueltos de Telegram ofrecidos al Router.

Cubre _texto_router (canal.bot) con router.procesar() mockeado (rapido,
determinista, sin gastar Qwen/Gemini de verdad) y termina con un caso
real end-to-end contra Qwen para demostrar que la ruta completa (Router
de produccion, sin mockear nada) tambien funciona. No manda nada a
Telegram de verdad en ningun caso: se prueba _texto_router (la funcion
pura que arma el mensaje), no _avisar_con_router (que ademas lo manda).
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

# 23/09: el Router intenta Gemini API antes que la web si hay clave. En estas pruebas
# se desactiva para no llamar a la API real; el camino API tiene su propia prueba.
import router as _router_sin_api  # noqa: E402


class _SinGeminiAPI:
    nombre = "gemini_api"

    def disponible(self):
        return False


_router_sin_api.GeminiAPIProvider = _SinGeminiAPI


SALIDA = RAIZ / "registros" / "prueba_router_libre_bot.txt"
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


anotar(f"ROUTER LIBRE EN TELEGRAM (T073)  {time.strftime('%Y-%m-%d %H:%M:%S')}")
anotar("=" * 60)


anotar("\n1. Flag apagado: no llama al Router en absoluto")

try:
    bot.ROUTER_RESPONDE_LIBRES = False

    with mock.patch("router.procesar") as procesar_falso:
        r = bot._texto_router("resume esto: hola")

        comprobar("devuelve None sin tocar el Router", r is None, repr(r))
        comprobar("router.procesar ni se llama", procesar_falso.call_count == 0)
finally:
    bot.ROUTER_RESPONDE_LIBRES = True


anotar("\n2. Router resuelve OK (mockeado) -> mensaje formado con proveedor/texto")

try:
    falso = {
        "execution_id": "exec-falso-1",
        "estado": "OK",
        "categoria": "resumen",
        "proveedor": "qwen",
        "texto": "Esto es el resumen.",
        "intentos": 1,
    }

    with mock.patch("router.procesar", return_value=falso) as procesar_falso:
        r = bot._texto_router("resume esto: un texto cualquiera")

    comprobar("procesar() se llama con el texto tal cual", procesar_falso.call_args[0][0] == "resume esto: un texto cualquiera")
    comprobar("no se le pasan claves_extraccion", "claves_extraccion" not in procesar_falso.call_args.kwargs or not procesar_falso.call_args.kwargs.get("claves_extraccion"))
    comprobar("hay mensaje", bool(r), repr(r))
    comprobar("menciona el proveedor", "qwen" in (r or ""), repr(r))
    comprobar("incluye el texto resuelto", "Esto es el resumen." in (r or ""), repr(r))
    comprobar("incluye la categoria", "resumen" in (r or ""), repr(r))
    comprobar("incluye el execution_id (trazabilidad)", "exec-falso-1" in (r or ""), repr(r))
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 2:")
    anotar(traceback.format_exc())


anotar("\n3. Router escala (mockeado) -> no se manda nada (el triaje de Qwen ya avisa)")

try:
    escalado = {
        "execution_id": "exec-falso-2",
        "estado": "ESCALADO",
        "categoria": "otro",
        "motivo": "categoria 'otro' no enrutable",
    }

    with mock.patch("router.procesar", return_value=escalado):
        r = bot._texto_router("cuentame un chiste")

    comprobar("devuelve None en escalado", r is None, repr(r))
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 3:")
    anotar(traceback.format_exc())


anotar("\n4. Router lanza una excepcion -> no revienta, no manda nada")

try:
    with mock.patch("router.procesar", side_effect=RuntimeError("fallo forzado de prueba")):
        r = bot._texto_router("resume esto: otra vez")

    comprobar("devuelve None si el Router revienta", r is None, repr(r))
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 4 (no deberia escapar ninguna):")
    anotar(traceback.format_exc())


anotar(
    "\n5. procesar_updates(): un mensaje suelto dispara el hilo del Router "
    "ademas del de Qwen (y no lo dispara si el flag esta apagado)"
)

try:
    import json
    import threading

    class _RespuestaOK:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "result": [{
                    "update_id": 1,
                    "message": {
                        "chat": {"id": 999},
                        "text": "resume esto: un mensaje suelto de prueba",
                    },
                }],
            }

    class _ClienteFalso:
        def get(self, *a, **k):
            return _RespuestaOK()

        def post(self, *a, **k):
            return _RespuestaOK()

    hilos_lanzados = []

    class _HiloFalso:
        def __init__(self, target=None, args=(), daemon=None, **kw):
            hilos_lanzados.append(target.__name__ if target else None)

        def start(self) -> None:
            pass

    estado_falso = {"offset": 0, "chat_id": 999}

    with mock.patch("canal.bot.threading.Thread", _HiloFalso), \
         mock.patch("canal.bot.anotar_libre"), \
         mock.patch("canal.bot.SALIDA", RAIZ / "_no_existe_" / "salida"):
        bot.procesar_updates(_ClienteFalso(), estado_falso)

    comprobar(
        "se lanza el hilo de Qwen",
        "_avisar_con_qwen" in hilos_lanzados,
        hilos_lanzados,
    )
    comprobar(
        "se lanza el hilo del Router",
        "_avisar_con_router" in hilos_lanzados,
        hilos_lanzados,
    )

    # Con el flag apagado, solo el hilo de Qwen.
    hilos_lanzados.clear()
    estado_falso = {"offset": 1, "chat_id": 999}

    class _RespuestaOK2(_RespuestaOK):
        def json(self) -> dict:
            return {
                "result": [{
                    "update_id": 2,
                    "message": {
                        "chat": {"id": 999},
                        "text": "otro mensaje suelto",
                    },
                }],
            }

    class _ClienteFalso2(_ClienteFalso):
        def get(self, *a, **k):
            return _RespuestaOK2()

    bot.ROUTER_RESPONDE_LIBRES = False

    with mock.patch("canal.bot.threading.Thread", _HiloFalso), \
         mock.patch("canal.bot.anotar_libre"), \
         mock.patch("canal.bot.SALIDA", RAIZ / "_no_existe_" / "salida"):
        bot.procesar_updates(_ClienteFalso2(), estado_falso)

    bot.ROUTER_RESPONDE_LIBRES = True

    comprobar(
        "con el flag apagado NO se lanza el hilo del Router",
        "_avisar_con_router" not in hilos_lanzados,
        hilos_lanzados,
    )
    comprobar(
        "con el flag apagado el de Qwen se lanza igual",
        "_avisar_con_qwen" in hilos_lanzados,
        hilos_lanzados,
    )
except Exception:
    fallos += 1
    bot.ROUTER_RESPONDE_LIBRES = True
    anotar("EXCEPCION en caso 5:")
    anotar(traceback.format_exc())


anotar(
    "\n6. REAL end-to-end (sin mockear nada): un mensaje suelto que de "
    "verdad se puede resumir, resuelto por el Router de produccion"
)

try:
    texto_largo = (
        "Nexo es el agente personal autonomo de Damian. Coordina IA local "
        "y modelos externos como Gemini, ChatGPT y Claude, junto con "
        "herramientas y control del PC, para planificar, ejecutar, "
        "verificar y completar tareas con la minima supervision humana "
        "necesaria."
    )
    peticion = f"Resume el siguiente texto en una frase corta:\n\n{texto_largo}"

    inicio = time.time()
    r = bot._texto_router(peticion)
    duracion = round(time.time() - inicio, 1)

    anotar(f"  tardo {duracion}s -> {r!r}")

    comprobar("hay mensaje real (el Router resolvio de verdad)", bool(r), repr(r))
    if r:
        comprobar("menciona algun proveedor (qwen o gemini)", "qwen" in r or "gemini" in r, r)
        comprobar("incluye la categoria resumen", "resumen" in r, r)
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 6 (real):")
    anotar(traceback.format_exc())


anotar("\n" + ("TODO VALE" if fallos == 0 else f"{fallos} FALLOS"))
anotar("FIN")
