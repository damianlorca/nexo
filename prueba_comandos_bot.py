"""Prueba de los comandos de tareas del bot, SIN tocar memoria/tareas.json.

Se monkeypatchea nucleo.tareas.ALMACEN/VISTA a archivos temporales
antes de importar canal.bot, para que /tarea, /tareas y /hecha
trabajen sobre una cola de mentira. Nada de esto toca la cola real.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo import registro  # noqa: E402
registro.aislar()  # T198: sus logs (401 simulados...) no van a registros/ reales

from nucleo import tareas  # noqa: E402
from nucleo import uso  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="prueba_tareas_bot_"))
tareas.ALMACEN = TMP / "tareas.json"
tareas.VISTA = TMP / "tareas.md"
tareas.CANDADO = TMP / ".candado.lock"
uso.ARCHIVO = TMP / "uso_diario.json"
uso.CANDADO = TMP / ".candado_uso.lock"

import httpx  # noqa: E402

import canal.bot as bot  # noqa: E402
from canal.bot import (  # noqa: E402
    _cmd_ahora,
    _cmd_hecha,
    _cmd_tarea,
    _cmd_tareas,
    _cmd_uso,
    _texto_estado,
)

bot.ESTADO_MISION = TMP / "estado.json"


fallos = []


def comprobar(nombre: str, cond: bool, detalle: str = "") -> None:
    marca = "OK " if cond else "MAL"
    print(f"[{marca}] {nombre}" + (f"  -- {detalle}" if detalle and not cond else ""))
    if not cond:
        fallos.append(nombre)


# 1. Cola vacia al principio.
r = _cmd_tareas("")
comprobar("cola vacia dice que esta vacia", "vacía" in r.lower(), r)

# 2. Anadir sin titulo da instrucciones, no revienta.
r = _cmd_tarea("   ")
comprobar("anadir sin titulo no revienta", r.startswith("Uso:"), r)

# 3. Anadir de verdad.
r = _cmd_tarea("Probar el comando /tarea desde Telegram")
comprobar("anadir devuelve un ID", r.startswith("✅ T"), r)

id_nuevo = r.split()[1]

# 4. Aparece en la lista.
r = _cmd_tareas("")
comprobar(f"{id_nuevo} aparece en /tareas", id_nuevo in r, r)

# 5. /tareas tuyas no la ve (depende=ia, no damian).
r = _cmd_tareas("tuyas")
comprobar(f"{id_nuevo} NO aparece en /tareas tuyas", id_nuevo not in r, r)

# 6. Cerrar una que no existe.
r = _cmd_hecha("T999 no deberia existir")
comprobar("cerrar una tarea inexistente avisa, no revienta", "No encuentro" in r, r)

# 7. Cerrarla de verdad, con nota.
r = _cmd_hecha(f"{id_nuevo} probado a mano y funciona")
comprobar(f"{id_nuevo} se cierra", r.startswith("✅") and id_nuevo in r, r)

# 8. Ya no sale en /tareas (solo lista vivas).
r = _cmd_tareas("")
comprobar(f"{id_nuevo} desaparece de /tareas tras cerrarla", id_nuevo not in r, r)

# 9. Se guardo de verdad en el almacen temporal (no en memoria).
datos = tareas.cargar()
guardada = next((t for t in datos["tareas"] if t["id"] == id_nuevo), None)
comprobar(
    "quedo en el almacen temporal con estado hecha y la nota",
    guardada is not None and guardada["estado"] == "hecha"
    and any("funciona" in n["texto"] for n in guardada["notas"]),
)

# 10. /estado sin memoria/estado.json de mentira: dice que no hay mision.
r = _texto_estado()
comprobar("estado sin archivo dice que no hay mision", "misión" in r.lower(), r)

# 11. /estado con un estado.json de mentira: sale legible, no el JSON crudo.
bot.ESTADO_MISION.write_text(
    json.dumps({
        "estado": "trabajando",
        "ultima_accion": "prueba automatica",
        "ultimo_resultado": "todo en verde",
        "esperando_a": "nada",
    }, ensure_ascii=False),
    encoding="utf-8",
)

r = _texto_estado()
comprobar(
    "estado con datos no es JSON crudo (no empieza por llave)",
    not r.strip().startswith("{"),
    r,
)
comprobar("estado con datos incluye el campo 'estado'", "trabajando" in r, r)
comprobar("estado con datos incluye la ultima accion", "prueba automatica" in r, r)

# 12. /estado incluye la siguiente tarea de la cola si hay alguna.
_cmd_tarea("Tarea para comprobar que /estado la menciona")
r = _texto_estado()
comprobar(
    "estado menciona la siguiente tarea de la cola",
    "Siguiente en mi cola" in r,
    r,
)

# 13. /uso sin turnos registrados no revienta.
r = _cmd_uso("")
comprobar("uso sin turnos no revienta", "Sin turnos" in r, r)

# 14. /uso con un turno registrado lo muestra.
uso.registrar_turno("claude-opus-5", "prueba")
r = _cmd_uso("")
comprobar("uso con un turno lo muestra", "claude-opus-5" in r, r)

# 15. /uso con argumento numerico no revienta (dias a mostrar).
r = _cmd_uso("3")
comprobar("uso con dias como argumento no revienta", "claude-opus-5" in r, r)


# --------------------------------------------------- /ahora (T039)
#
# _cmd_ahora recibe un `cliente` inyectable para no tocar la red de
# verdad. Para probar la rama "sin token" y la rama "con token" hace
# falta tambien sustituir bot.valor (canal.bot importa `valor` con
# `from nucleo.config import valor`, asi que el nombre vive en el
# espacio de canal.bot, no en nucleo.config).

_valor_original = bot.valor


class _RespuestaFalsa:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _ClienteFalso:
    """Sustituye a httpx.Client: nunca toca la red de verdad."""

    def __init__(self, status_code: int = 200, excepcion: Exception | None = None) -> None:
        self.status_code = status_code
        self.excepcion = excepcion
        self.llamadas: list[tuple[str, dict, dict]] = []

    def post(self, url, headers=None, json=None):
        self.llamadas.append((url, headers, json))

        if self.excepcion:
            raise self.excepcion

        return _RespuestaFalsa(self.status_code)


def _con_valores(extra: dict) -> None:
    def _falso(clave, defecto=None):
        return extra.get(clave, defecto)

    bot.valor = _falso


# 16. Sin token configurado: explica como conseguirlo, no llama a nada.
_con_valores({})
r = _cmd_ahora("")
comprobar(
    "ahora sin token explica donde conseguirlo",
    "claude.ai/code/routines" in r,
    r,
)

# 17. Con token e id, un 200 confirma que el turno se ha pedido.
_con_valores({"rutina.token_api": "sk-ant-oat01-falso", "rutina.id": "trig_falso"})
cliente_ok = _ClienteFalso(status_code=200)
r = _cmd_ahora("mira esto", cliente=cliente_ok)
comprobar("ahora con exito confirma el turno pedido", "pedido" in r.lower(), r)
comprobar(
    "ahora manda el texto como cuerpo",
    cliente_ok.llamadas[0][2] == {"text": "mira esto"},
    cliente_ok.llamadas,
)
comprobar(
    "ahora manda el token en la cabecera Authorization",
    cliente_ok.llamadas[0][1]["Authorization"] == "Bearer sk-ant-oat01-falso",
    cliente_ok.llamadas[0][1],
)
comprobar(
    "ahora usa la url de la rutina configurada",
    cliente_ok.llamadas[0][0] == bot.URL_DISPARO_RUTINA.format(id="trig_falso"),
    cliente_ok.llamadas[0][0],
)

# 17b. Sin texto, el cuerpo va vacio (no {"text": ""}).
cliente_vacio = _ClienteFalso(status_code=200)
_cmd_ahora("   ", cliente=cliente_vacio)
comprobar(
    "ahora sin texto manda el cuerpo vacio",
    cliente_vacio.llamadas[0][2] == {},
    cliente_vacio.llamadas,
)

# 18. 429: avisa del limite diario, no como un error generico cualquiera.
cliente_429 = _ClienteFalso(status_code=429)
r = _cmd_ahora("", cliente=cliente_429)
comprobar("ahora con 429 avisa del limite diario", "límite" in r.lower(), r)

# 19. Otro codigo de error (token caducado, por ejemplo): manda a revisar el token.
cliente_401 = _ClienteFalso(status_code=401)
r = _cmd_ahora("", cliente=cliente_401)
comprobar("ahora con 401 manda a revisar el token", "token" in r.lower(), r)

# 20. Fallo de red: no revienta, explica que no ha podido avisar.
cliente_roto = _ClienteFalso(excepcion=httpx.ConnectError("sin red"))
r = _cmd_ahora("", cliente=cliente_roto)
comprobar("ahora con fallo de red no revienta", "no he podido" in r.lower(), r)

bot.valor = _valor_original


# --------------------------------------------------- 401 seguidos (T040)
#
# Un token de Telegram invalido en secretos.toml NO tira el proceso
# (procesar_updates solo duerme 60s y reintenta con el token ya
# cargado en memoria): si alguien corrige secretos.toml mientras el
# bot sigue vivo, nunca se entera. El arreglo: tras varios 401
# seguidos el bot se rinde (SystemExit) para que el vigilante lo
# relance con el token nuevo. Se prueba con un cliente.get() falso
# que siempre lanza un 401, y con time.sleep noqueado (el codigo real
# duerme 60s entre intentos, y aqui no hay 5 minutos que perder).

import time as _time  # noqa: E402

_sleep_original = _time.sleep
_time.sleep = lambda segundos: None


class _RespuestaHTTP:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _RespuestaOK:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"result": []}


class _FalloConRespuesta(httpx.HTTPError):
    def __init__(self, status_code: int) -> None:
        super().__init__("fallo simulado")
        self.response = _RespuestaHTTP(status_code)


class _ClienteGetFalso:
    """Sustituye a httpx.Client para procesar_updates: solo hace falta .get()."""

    def __init__(self, secuencia: list) -> None:
        self.secuencia = list(secuencia)
        self.llamadas = 0

    def get(self, *args, **kwargs):
        self.llamadas += 1
        paso = self.secuencia.pop(0)

        if paso == "ok":
            return _RespuestaOK()

        raise _FalloConRespuesta(paso)


# 21. RENDIRSE_TRAS_401 x 401 seguidos: el bot se rinde (SystemExit).
bot._401_seguidos = 0
cliente_401 = _ClienteGetFalso([401] * bot.RENDIRSE_TRAS_401)
estado_falso = {"offset": 0}

se_rindio = False

for _ in range(bot.RENDIRSE_TRAS_401):
    try:
        bot.procesar_updates(cliente_401, estado_falso)
    except SystemExit:
        se_rindio = True
        break

comprobar(
    f"tras {bot.RENDIRSE_TRAS_401} x 401 seguidos el bot se rinde",
    se_rindio,
)
comprobar(
    "se rindio justo al llegar al numero configurado, ni antes ni despues",
    cliente_401.llamadas == bot.RENDIRSE_TRAS_401,
    cliente_401.llamadas,
)

# 22. Un exito de por medio reinicia el contador (no arrastra 401 viejos).
bot._401_seguidos = 0
secuencia = [401, 401, "ok"] + [401] * bot.RENDIRSE_TRAS_401
cliente_mixto = _ClienteGetFalso(secuencia)

rendido_en = None
intentos = 0

while cliente_mixto.secuencia:
    intentos += 1
    try:
        bot.procesar_updates(cliente_mixto, estado_falso)
    except SystemExit:
        rendido_en = intentos
        break

comprobar(
    "un exito intermedio reinicia el contador (hacen falta 5 mas, no 2 mas)",
    rendido_en == 3 + bot.RENDIRSE_TRAS_401,
    rendido_en,
)

bot._401_seguidos = 0
_time.sleep = _sleep_original

print()
if fallos:
    print(f"FALLARON {len(fallos)}: {fallos}")
    raise SystemExit(1)

print(f"TODO BIEN. Almacen de prueba en {TMP} (no es memoria/ real).")
