"""Bot de Telegram. El canal movil del agente.

Se arranca una vez y se queda corriendo:
    python canal/bot.py

Que hace:
- Vigila canal/salida/ y manda al movil lo que el agente deje ahi.
- Escucha Telegram y deja lo que contestas en canal/entrada/.
- Las preguntas salen con botones: tocas uno y ya esta.
- /tarea, /tareas y /hecha dan de alta y cierran tareas SIN pasar por
  Claude: van directo a nucleo.tareas. Coste cero, siempre disponible.
- /verificar <id> <evidencia> (T160) la marca HECHO Y TESTEADO solo con
  evidencia de verdad (que se probo y que salio); /hecha la pide al cerrar.
- /estado da un resumen legible (que hace Nexo, que espera, cual es
  la siguiente tarea), no el JSON en crudo.
- /uso da cuantos turnos y de que modelo ha habido cada dia (T029),
  para ver si las medidas de ahorro estan bajando el gasto de verdad.
- /ahora [texto] (T039) dispara un turno de Claude YA, sin esperar al
  cron de las 23:00, usando el disparador de rutina por API (se paga
  con el plan de Claude Code, no con la API de pago). Necesita que
  Damian genere un token una vez en claude.ai/code/routines y lo
  pegue en secretos.toml — ver el propio mensaje de /ahora si falta.
- /imagen <texto> (T041) genera una imagen con ComfyUI en el propio
  equipo y la manda por el chat. Tarda unos 30 s, asi que contesta al
  momento y trabaja en un hilo. No gasta plan de Claude: es la GPU de
  casa. Lo que sabemos de esa GPU (y lo que NO hay que volver a
  intentar) esta en la cabecera de extremidades/imagen.py.
- Un mensaje suelto (que no contesta a nada) recibe ademas, en unos
  segundos y en un mensaje aparte, una lectura rapida de Qwen
  (extremidades.triaje): que categoria y urgencia le pone y un
  resumen de una frase. Qwen NO decide ni da de alta nada por su
  cuenta (ver el docstring de triaje.py): solo dice lo que ha leido,
  para que sepas que el mensaje ha llegado y mas o menos de que va,
  aunque Nexo (Claude) no lo mire hasta su siguiente turno.
- T073 (14/09): ademas de esa lectura informativa, el mismo mensaje
  suelto se ofrece de verdad a router.py (T067/T044): si Qwen lo
  clasifica como "resumen" y lo resuelve (o, tras agotar Qwen, lo
  resuelve Gemini como fallback), la respuesta llega por aqui mismo,
  con la misma verificacion mecanica y el mismo registro de
  evidencia que ya usa consumidor_router.py para la cola. Una
  "extraccion" real no puede resolverse desde un mensaje suelto (no
  hay claves que pedirle a Telegram), asi que siempre escala -- y un
  escalado no manda nada por este canal (la lectura de Qwen de
  arriba ya avisa de que el mensaje ha llegado).
- T082 Pieza 1 (22/09): el mismo mensaje suelto se ofrece tambien a
  consumidor_libres.py, reutilizando extremidades.triaje.triar()
  (sin duplicar la clasificacion) y nucleo.tareas.anadir(): si Qwen
  lo lee como "tarea" de verdad, se da de alta en tareas.json con
  etiquetas origen:telegram_libre + clasificado_auto y una nota
  PENDIENTE_DE_REVISION, y avisa por aqui mismo que ha creado la
  tarea (sin sonido). Si no es una tarea, no toca nada: el triaje
  de Qwen de arriba ya cubre esa lectura. Apagalo en config.toml
  (canal.consumidor_libres_responde = false) si prefieres que
  ningun mensaje suelto se convierta en tarea sin que tu lo pidas.
- N04 (25/09): aprobaciones desde el movil (T154 F4). Cada peticion
  ambar nueva de la cola (nucleo/aprobaciones.py) llega con botones
  Aprobar / Denegar; /aprobaciones las lista y /aprobar o /denegar
  deciden por texto. La logica esta en canal/aprobaciones_bot.py.

Solo depende de httpx. Nada de librerias grandes: cuanto menos
tenga, menos se rompe cuando no hay nadie mirando. Qwen y las tareas
se importan por dentro de sus funciones, para que si algo de eso
falla (Ollama parado, un import roto) el bot siga vivo igualmente:
lo esencial es el canal, no el adorno.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import httpx  # noqa: E402

from canal.interruptor import bot_activo  # noqa: E402  (T751)
from nucleo import tareas               # noqa: E402
from nucleo import uso                  # noqa: E402
from nucleo.config import valor          # noqa: E402
from nucleo.escritura import escribir_atomico  # noqa: E402
from nucleo.instancia import unico       # noqa: E402
from nucleo.registro import logger, traza  # noqa: E402
from nucleo import frescura               # noqa: E402  (T131: fija la hora de arranque del bot)


log = logger("canal.bot")

# httpx registra cada URL a nivel INFO, y la URL de la API de
# Telegram lleva el token dentro. Sin esto, el token acaba en claro
# en los registros. Se calla httpx y punto.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def _sin_token(texto: str) -> str:
    """Por si algun mensaje de error arrastra algun token (Telegram o rutina)."""

    if TOKEN:
        texto = texto.replace(TOKEN, "<token_telegram>")

    token_rutina = valor("rutina.token_api", "")

    if token_rutina:
        texto = texto.replace(token_rutina, "<token_rutina>")

    return texto

SALIDA = RAIZ / "canal" / "salida"
ENTRADA = RAIZ / "canal" / "entrada"
ESTADO = RAIZ / "canal" / "estado_bot.json"
ESTADO_MISION = RAIZ / "memoria" / "estado.json"

TOKEN = valor("canal.token_telegram", "")

# Si Qwen debe leer y comentar los mensajes sueltos mientras Nexo no
# esta mirando. Apagalo en config.toml (canal.qwen_responde_libres =
# false) si resulta cargante.
QWEN_RESPONDE_LIBRES = bool(valor("canal.qwen_responde_libres", True))

# T073 (14/09): ademas del triaje informativo de Qwen, un mensaje
# suelto que Qwen clasifica como "resumen" se intenta de verdad con
# el Router (T067/T044) -- mismas reglas, mismos verificadores y el
# mismo fallback a Gemini que ya usa consumidor_router.py para la
# cola, reutilizados tal cual (router.procesar()), sin duplicar nada
# de eso aqui. Una "extraccion" no puede resolverse desde un mensaje
# suelto (no hay claves que pedirle a Telegram) y siempre escala; un
# escalado no manda nada (el triaje de Qwen de arriba ya avisa de
# que el mensaje ha llegado). Apagalo en config.toml
# (canal.router_responde_libres = false) si prefieres que TODO
# mensaje suelto quede solo para que Nexo (Claude) lo revise a mano.
ROUTER_RESPONDE_LIBRES = bool(valor("canal.router_responde_libres", True))

# T082 Pieza 1 (22/09): ademas del triaje informativo y del Router, un
# mensaje suelto que Qwen clasifica como "tarea" de verdad se da de
# alta en tareas.json via consumidor_libres.py (reutilizado tal cual,
# sin duplicar logica de clasificacion ni de escritura). Nunca se
# fusiona con una tarea existente ni se le pone importancia/dificultad:
# queda con etiqueta clasificado_auto y nota PENDIENTE_DE_REVISION para
# que Damian (o Nexo en su proxima pasada) la revise. Apagalo en
# config.toml (canal.consumidor_libres_responde = false) si prefieres
# que ningun mensaje suelto se convierta en tarea sin que lo pidas tu.
CONSUMIDOR_LIBRES_RESPONDE = bool(valor("canal.consumidor_libres_responde", True))

# N01 (H11): los tres hilos de un mensaje suelto (triaje, Router, consumidor_libres)
# usan Qwen. Con este candado van de uno en uno: un modelo trabajando cada vez, no
# tres peticiones a la vez contra Ollama. Y ninguno arranca con la PARADA activa.
_UN_MODELO = threading.Lock()


def _parado() -> bool:
    try:
        from nucleo import parada
        return parada.activa() is not None
    except Exception:
        return False

# T039: disparar un turno de Claude bajo demanda por API, sin esperar
# al cron. Documentacion oficial: POST a este endpoint con un token
# PROPIO DE LA RUTINA (no la API key normal), generado a mano una vez
# en claude.ai/code/routines. Se factura contra el plan de Claude
# Code (igual que un turno interactivo o programado), NO como API de
# pago aparte — asi que respeta la restriccion de coste cero del
# proyecto. Sin token configurado, /ahora explica como conseguirlo y
# no hace ninguna llamada.
URL_DISPARO_RUTINA = "https://api.anthropic.com/v1/claude_code/routines/{id}/fire"
BETA_RUTINA = "experimental-cc-routine-2026-04-01"


class SinToken(RuntimeError):
    pass


def api(metodo: str) -> str:
    return f"https://api.telegram.org/bot{TOKEN}/{metodo}"


def cargar_estado() -> dict:
    if ESTADO.is_file():
        try:
            return json.loads(ESTADO.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    return {"offset": 0, "chat_id": valor("canal.chat_id", 0)}


def guardar_estado(estado: dict) -> None:
    # Atomico (N02): un estado a medias hacia que cargar_estado volviera a
    # offset 0 y Telegram reentregara updates ya procesadas.
    escribir_atomico(ESTADO, json.dumps(estado, ensure_ascii=False, indent=2))


def teclado(opciones: list[str], id_pregunta: str) -> dict:
    """Botones en filas de dos, o de uno si el texto es largo."""

    filas, fila = [], []

    for i, opcion in enumerate(opciones[:8]):
        fila.append({
            "text": opcion[:60],
            "callback_data": f"{id_pregunta}|{i}",
        })

        if len(fila) == 2 or len(opcion) > 20:
            filas.append(fila)
            fila = []

    if fila:
        filas.append(fila)

    return {"inline_keyboard": filas}


def enviar(cliente: httpx.Client, estado: dict, mensaje: dict) -> bool:
    chat = estado.get("chat_id")

    if not chat:
        log.warning("todavia no se quien eres: escribe /start al bot")
        return False

    tipo = mensaje.get("tipo", "aviso")
    texto = mensaje.get("texto", "")

    try:
        if tipo == "pregunta":
            r = cliente.post(api("sendMessage"), json={
                "chat_id": chat,
                "text": f"❓ {texto}",
                "reply_markup": teclado(mensaje.get("opciones", []), mensaje["id"]),
            })

        elif tipo in ("foto", "archivo"):
            ruta = Path(mensaje.get("ruta", ""))

            if not ruta.is_file():
                log.error("no existe el archivo: %s", ruta)
                return False

            metodo = "sendPhoto" if tipo == "foto" else "sendDocument"
            campo = "photo" if tipo == "foto" else "document"

            with ruta.open("rb") as f:
                r = cliente.post(
                    api(metodo),
                    data={
                        "chat_id": chat,
                        "caption": texto[:1000],
                        "disable_notification": bool(
                            mensaje.get("silencioso")
                        ),
                    },
                    files={campo: (ruta.name, f)},
                )

        else:
            prefijo = "🔴 " if mensaje.get("urgente") else ""

            r = cliente.post(api("sendMessage"), json={
                "chat_id": chat,
                "text": f"{prefijo}{texto}"[:4000],
                # Sin sonido ni vibracion. El mensaje llega y espera
                # en el chat. Es lo que usa el turno de noche para
                # dejar el resumen sin despertar a nadie.
                "disable_notification": bool(mensaje.get("silencioso")),
            })

        r.raise_for_status()

        return True

    except httpx.HTTPError as e:
        log.error("fallo al enviar: %s", _sin_token(str(e)))
        return False


def anotar_respuesta(id_pregunta: str, respuesta: str, origen: str) -> None:
    ENTRADA.mkdir(parents=True, exist_ok=True)

    (ENTRADA / f"{id_pregunta}.json").write_text(
        json.dumps({
            "id": id_pregunta,
            "respuesta": respuesta,
            "origen": origen,
            "hora": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    traza("respuesta_movil", id=id_pregunta, respuesta=respuesta[:200])


def anotar_libre(texto: str) -> dict:
    """Guarda el mensaje suelto y devuelve su forma de 'mensaje'
    (archivo/hora/texto), la misma que espera
    consumidor_libres.procesar_uno() -- para no tener que releer el
    archivo que se acaba de escribir.
    """

    ENTRADA.mkdir(parents=True, exist_ok=True)

    # Fecha + hora + sufijo aleatorio (B3 de N02): con solo HHMMSS, dos
    # mensajes en el mismo segundo, o a la misma hora de otro dia sin
    # leer, se pisaban y el primero se perdia. El orden alfabetico sigue
    # siendo el cronologico (triaje y buzon los leen con sorted()).
    marca = f"libre_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    nombre_archivo = f"{marca}.json"
    hora = time.strftime("%Y-%m-%d %H:%M:%S")

    # Atomico: el turno y el triaje leen esta carpeta mientras el bot escribe.
    escribir_atomico(
        ENTRADA / nombre_archivo,
        json.dumps({
            "texto": texto,
            "hora": hora,
        }, ensure_ascii=False, indent=2),
    )

    traza("mensaje_movil", texto=texto[:200])

    return {"archivo": nombre_archivo, "hora": hora, "texto": texto}


# --------------------------------------------------- comandos de tareas
#
# Van directos a nucleo.tareas, sin pasar por Claude ni por Qwen: dar
# de alta o cerrar una tarea es una operacion mecanica y determinista,
# no algo que necesite criterio. Coste cero y funciona aunque Nexo no
# este despierto ni Ollama responda. Es T002: "que el bot sepa dar de
# alta y cerrar tareas desde el movil".
#
# Cada uno es una funcion PURA (recibe texto, devuelve texto) para
# poder probarlos sin necesidad de un chat de Telegram de verdad. Ver
# prueba_comandos_bot.py.

def _cmd_tarea(argumento: str) -> str:
    titulo = argumento.strip()

    if not titulo:
        return (
            "Uso: /tarea <titulo>\n"
            "Ejemplo: /tarea revisar el recibo de la UPV"
        )

    t = tareas.anadir(titulo, depende="ia")

    return (
        f"✅ {t['id']} añadida (p={tareas.puntuacion(t)}, "
        f"modelo sugerido: {tareas.modelo_sugerido(t)}).\n"
        "La verá Nexo en su próxima pasada por la cola."
    )


def _cmd_tareas(argumento: str) -> str:
    quien = argumento.strip().lower()
    depende = "damian" if quien in ("tuyas", "mi", "mias_no") else "ia"

    pendientes = tareas.listar(depende=depende)

    if not pendientes:
        return (
            "Nada pendiente ahí ahora mismo."
            if depende == "damian"
            else "Cola vacía por mi lado. Pídeme algo con /tarea."
        )

    cabecera = "Pendientes tuyas:" if depende == "damian" else "Las mías, por orden:"

    lineas = [
        f"{t['id']} (p={tareas.puntuacion(t)}) — {t['titulo']}"
        for t in pendientes[:8]
    ]

    return cabecera + "\n" + "\n".join(lineas)


def _cmd_hecha(argumento: str) -> str:
    partes = argumento.strip().split(maxsplit=1)

    if not partes:
        return "Uso: /hecha <id> [nota]"

    id_tarea, nota = partes[0], (partes[1] if len(partes) > 1 else "")

    t = tareas.completar(id_tarea, nota, despues="nada: cerrada con /hecha desde Telegram",   # T1010
                         cierre=tareas.cierre_ok(evidencia=f"Cerrada a mano por Damian con /hecha. {nota}".strip()))

    if not t:
        return f"No encuentro la tarea {id_tarea}."

    # T160 (verify-on-stop): cerrar no es comprobar. Se pide la evidencia UNA vez;
    # si no llega, la tarea se queda en HECHO SIN TESTEAR, que es lo que es.
    return (
        f"✅ {t['id']} cerrada (HECHO SIN TESTEAR).\n"
        f"Para dejarla HECHO Y TESTEADO: /verificar {t['id']} <qué probaste y qué salió>"
    )


def _cmd_verificar(argumento: str) -> str:
    """T160: marca una tarea hecha como testeada SOLO con evidencia de verdad."""
    from nucleo import evidencias

    partes = argumento.strip().split(maxsplit=1)

    if len(partes) < 2:
        return "Uso: /verificar <id> <qué probaste y qué salió>"

    id_tarea, evidencia = partes

    actual = tareas.buscar(id_tarea)

    if actual is None or actual["id"].lower() != id_tarea.lower():
        return f"No encuentro la tarea {id_tarea}."

    if actual["estado"] != "hecha":
        # Igual que la web: una evidencia de ANTES de hacer el trabajo no vale.
        return f"{actual['id']} no está hecha: ciérrala primero con /hecha {actual['id']}."

    vale, motivo = evidencias.evaluar(evidencia)

    if not vale:
        return f"❌ No la marco: {motivo}."

    t = tareas.verificar(actual["id"], evidencia)

    if not t or not t.get("testeado"):
        return f"❌ No la marco: di qué probaste y qué salió."

    return f"🧪 {t['id']} HECHO Y TESTEADO. Evidencia guardada."



def _cmd_parar(argumento: str) -> str:
    """Parada de emergencia: ningun turno automatico sigue hasta /seguir."""
    from nucleo import parada
    d = parada.activar(argumento, quien="telegram")
    extra = f" Modelos descargados: {', '.join(d['ollama_descargados'])}." if d["ollama_descargados"] else ""
    return f"⛔ NEXO PARADO ({d['motivo']}). Ningun turno automatico sigue hasta /seguir.{extra}"


def _cmd_seguir(argumento: str) -> str:
    from nucleo import parada
    return "▶️ Parada quitada: NEXO puede volver a trabajar." if parada.desactivar() else "No habia ninguna parada activa."


def _cmd_turno(argumento: str, lanzar=None) -> str:
    """DESACTIVADO el 28/09 (Damian, T231): lanzaba turno_nexo.py directamente, saltandose la cola del
    planificador de turnos (nucleo/planificador.py). Los turnos se lanzan desde la web (/turnos, "Lanzar ya")."""
    return ("/turno está desactivado: los turnos se lanzan desde la web de NEXO (pestaña Turnos, «Lanzar ya»), "
            "que respeta la cola.")


def _cmd_orden(argumento: str, lanzar=None) -> str:
    """T140: orden libre 'hazlo ya'. Se procesa en segundo plano (puede tardar minutos
    si hay que investigar); el resultado llega como aviso al terminar."""
    from nucleo import parada
    if parada.activa():
        return f"⛔ Parada activa ({parada.activa()}). /seguir antes de mandar órdenes."
    if len(argumento.strip()) < 4:
        return "Escribe la orden detrás de /orden, p. ej.: /orden investiga qué es Open WebUI y si nos sirve"
    import subprocess
    import sys
    raiz = Path(__file__).resolve().parent.parent
    cmd = [sys.executable, "-m", "nucleo.orden_cli", argumento.strip()]
    (lanzar or (lambda c: subprocess.Popen(c, cwd=str(raiz), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))))(cmd)
    return "📝 Orden recibida. La apunto y, si es delegable, la trabajo ya con revisor. Te aviso al acabar."

def _cmd_uso(argumento: str) -> str:
    """Cuantos turnos y de que modelo, por dia (T029: gastar menos plan)."""

    partes = argumento.strip().split()
    dias = int(partes[0]) if partes and partes[0].isdigit() else 7

    from nucleo import uso_proveedores
    return f"Turnos por día (últimos {dias}):\n{uso.resumen(dias)}\n\n{uso_proveedores.resumen(dias)}"


def _cmd_ahora(argumento: str, cliente: httpx.Client | None = None) -> str:
    """T039: dispara un turno de Claude YA, sin esperar al cron de las 23:00.

    Usa el disparador de rutina por API de Anthropic (documentacion
    oficial: un token propio de la rutina, no una API key normal, que
    se paga contra el plan de Claude Code — mismo gasto que un turno
    interactivo, no una API de pago aparte). `cliente` es inyectable
    para poder probarlo sin red de verdad (ver prueba_comandos_bot.py).
    """

    token = valor("rutina.token_api", "")
    id_rutina = valor("rutina.id", "")

    if not token or not id_rutina:
        return (
            "Todavía no puedo pedir un turno inmediato: falta configurar el "
            "disparador de la rutina.\n"
            "1) Entra en claude.ai/code/routines con tu cuenta.\n"
            "2) Abre 'Nexo — turno de noche' y añade un disparador de API.\n"
            "3) Copia el token (empieza por sk-ant-oat01-) a secretos.toml, "
            "sección [rutina], clave token_api (y revisa que 'id' sea el de "
            "esa rutina).\n"
            "Con eso configurado, /ahora ya podrá pedirle un turno a Claude "
            "sin esperar a las 23:00."
        )

    cuerpo = {"text": argumento.strip()} if argumento.strip() else {}

    propio = cliente is None

    if propio:
        cliente = httpx.Client(timeout=20)

    try:
        r = cliente.post(
            URL_DISPARO_RUTINA.format(id=id_rutina),
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-version": "2023-06-01",
                "anthropic-beta": BETA_RUTINA,
                "Content-Type": "application/json",
            },
            json=cuerpo,
        )
    except httpx.HTTPError as e:
        return f"No he podido avisar a Claude ahora mismo: {_sin_token(str(e))}"
    finally:
        if propio:
            cliente.close()

    if r.status_code == 429:
        return (
            "Claude ha llegado al límite diario de turnos bajo demanda. "
            "Prueba más tarde, o espera al turno de las 23:00."
        )

    if r.status_code >= 400:
        return (
            f"La rutina no se ha podido disparar (código {r.status_code}). "
            "Revisa el token en secretos.toml, puede que haya caducado."
        )

    return (
        "📨 Turno pedido. Claude se pone a mirarlo ya, no hace falta "
        "esperar al de las 23:00."
    )


def _cmd_imagen(argumento: str, generar=None, buzon_=None) -> str:
    """T041: genera una imagen en el equipo y la manda por el chat.

    Tarda unos 30 s (ver la cabecera de extremidades/imagen.py, que explica
    por que), asi que aqui se contesta al momento y el trabajo se hace en un
    hilo aparte: un bot que tarda medio minuto en responder parece colgado y,
    peor, deja de leer lo que llegue mientras tanto.

    No pasa por Claude ni gasta plan: es la GPU de casa.

    `generar` y `buzon_` se inyectan en las pruebas para no depender de que
    haya un ComfyUI vivo (ver prueba_imagen_bot.py).
    """

    encargo = argumento.strip()

    if not encargo:
        return (
            "Dime qué quieres ver. Por ejemplo:\n"
            "/imagen un faro en un acantilado al amanecer\n\n"
            "Tarda unos 30 segundos y la foto te llega aquí mismo. "
            "La hace la GPU de casa, así que no gasta plan de Claude."
        )

    def trabajar() -> None:
        # Los imports van aqui dentro a proposito: si ComfyUI o el modulo
        # de imagen estuvieran rotos, el bot tiene que seguir vivo igual.
        try:
            if generar is None:
                from extremidades.imagen import generar as hacer
            else:
                hacer = generar

            if buzon_ is None:
                from canal import buzon as correo
            else:
                correo = buzon_

        except ImportError as error:
            log.error("no puedo cargar lo de las imagenes: %s", error)
            return

        try:
            destino = hacer(encargo)

        except Exception as error:  # noqa: BLE001 - cualquier fallo se avisa
            log.error("la imagen de %r no salio: %s", encargo[:60], error)

            correo.avisar(
                f"No he podido hacer la imagen de «{encargo[:100]}».\n\n"
                f"{error}",
            )

            return

        correo.enviar_foto(destino, f"🖼️ {encargo[:200]}")

        log.info("imagen enviada: %s", getattr(destino, "name", destino))

    threading.Thread(target=trabajar, daemon=True, name="imagen").start()

    return (
        f"Voy con «{encargo[:100]}». Te llega en menos de un minuto.\n"
        "Si algo falla te lo digo por aquí."
    )


def _texto_estado() -> str:
    """Resumen legible de memoria/estado.json + la cola. No el JSON en crudo."""

    if not ESTADO_MISION.is_file():
        return "Sin misión en curso."

    try:
        datos = json.loads(ESTADO_MISION.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return f"No he podido leer memoria/estado.json: {e}"

    lineas = [f"Estado: {datos.get('estado', '?')}"]

    if datos.get("ultima_accion"):
        lineas.append(f"\nÚltimo turno: {datos['ultima_accion'][:300]}")

    if datos.get("ultimo_resultado"):
        lineas.append(f"\nResultado: {datos['ultimo_resultado'][:400]}")

    if datos.get("esperando_a"):
        lineas.append(f"\nEsperando: {datos['esperando_a'][:300]}")

    try:
        sig = tareas.siguiente()
    except Exception:
        sig = None

    lineas.append(
        f"\nSiguiente en mi cola: {sig['id']} — {sig['titulo']}"
        if sig
        else "\nCola vacía por mi lado ahora mismo."
    )

    # T131: avisar si este proceso corre con codigo viejo (paso el 14/09 y el
    # 22/09: el bot seguia vivo con codigo anterior a cambios en router.py).
    try:
        viejos = frescura.desfasados()
    except Exception:
        viejos = []

    if viejos:
        lineas.append(
            "\n\nAviso: corro con código viejo. Desde que arranqué han cambiado "
            + ", ".join(viejos[:8]) + (" …" if len(viejos) > 8 else "")
            + ". Reiníciame para cargar los cambios."
        )

    return "".join(lineas)[:4000]


# --------------------------------------------------- lectura de Qwen
#
# Para "que si no esta Nexo responda Qwen": un mensaje suelto (uno que
# no contesta a una pregunta abierta) dispara, en un hilo aparte para
# no bloquear el sondeo de Telegram, una lectura rapida con el obrero.
# Qwen SOLO informa: categoria, urgencia y un resumen de una frase.
# Nunca da de alta una tarea ni decide nada (ver triaje.py). El
# mensaje de Qwen llega sin sonido: es un extra, no una alarma.

def _texto_triaje(texto: str) -> str | None:
    """La lectura de Qwen ya formada para mandar. None si no toca."""

    if not QWEN_RESPONDE_LIBRES:
        return None

    try:
        from extremidades import qwen, triaje
    except Exception as e:
        log.warning("no se puede usar Qwen para triaje: %s", e)
        return None

    try:
        if not qwen.disponible():
            return None

        lectura = triaje.triar(texto)
    except Exception as e:
        log.warning("triaje del mensaje suelto fallo: %s", _sin_token(str(e)))
        return None

    resumen = (lectura.get("resumen") or "").strip() or "(sin resumen claro)"
    categoria = lectura.get("categoria") or "?"
    urgencia = lectura.get("urgencia") or "?"

    return (
        f"🤖 Qwen: {resumen}\n"
        f"({categoria}, {urgencia}) — Nexo lo verá en su próxima pasada."
    )


def _avisar_con_qwen(chat_id: int, texto: str) -> None:
    """Corre en un hilo aparte: Qwen tarda segundos, Telegram no debe esperar."""

    with _UN_MODELO:
        mensaje = None if _parado() else _texto_triaje(texto)

    if not mensaje:
        return

    try:
        with httpx.Client(timeout=15) as cliente2:
            r = cliente2.post(api("sendMessage"), json={
                "chat_id": chat_id,
                "text": mensaje,
                "disable_notification": True,
            })

            r.raise_for_status()

    except httpx.HTTPError as e:
        log.warning("no pude mandar la lectura de Qwen: %s", _sin_token(str(e)))


# --------------------------------------------------- Router (T073)
#
# Mismo patron que el triaje de arriba (funcion pura que arma el
# texto + funcion que lo manda en un hilo aparte), pero en vez de
# comentar el mensaje, intenta RESOLVERLO de verdad reutilizando
# router.procesar() (T067/T044) tal cual esta en produccion: mismas
# reglas fijas, misma verificacion mecanica, mismo fallback a Gemini,
# misma evidencia en registros/evidencia.jsonl. Este modulo no
# clasifica ni verifica nada por su cuenta.

def _texto_router(texto: str) -> str | None:
    """El resultado del Router para un mensaje suelto, ya formado
    para mandar. None si no ha resuelto nada (escalado, error, o si
    esta apagado por config).

    Sin claves_extraccion -- no hay forma de sacarlas de un mensaje
    suelto de Telegram --, asi que una "extraccion" real siempre
    escala aqui; solo "resumen" puede resolverse de principio a fin
    por esta via. Un escalado no devuelve nada a proposito: la
    lectura de Qwen (_texto_triaje) ya avisa de que el mensaje ha
    llegado, y este canal solo habla cuando el Router de verdad ha
    resuelto algo.
    """

    if not ROUTER_RESPONDE_LIBRES:
        return None

    try:
        import router as router_mod
    except Exception as e:
        log.warning("no se puede usar el Router para el mensaje suelto: %s", e)
        return None

    try:
        # N01 (H11): un mensaje suelto se resuelve SOLO con Qwen local. Antes podia
        # acabar en ChatGPT o Gemini web por cualquier mensaje, sin pedirlo nadie.
        resultado = router_mod.procesar(texto, solo_local=True)
    except Exception as e:
        log.warning(
            "el Router fallo con el mensaje suelto: %s", _sin_token(str(e)),
        )
        return None

    if resultado.get("estado") != "OK":
        return None

    return (
        f"\U0001F9ED Router ({resultado.get('proveedor')}): "
        f"{resultado.get('texto')}\n"
        f"[{resultado.get('categoria')} · {resultado.get('execution_id')}]"
    )[:4000]


def _avisar_con_router(chat_id: int, texto: str) -> None:
    """Corre en un hilo aparte: el Router puede tardar (Qwen y, si
    hace falta, Gemini de verdad), y Telegram no debe esperar.
    """

    with _UN_MODELO:
        mensaje = None if _parado() else _texto_router(texto)

    if not mensaje:
        return

    try:
        with httpx.Client(timeout=20) as cliente2:
            r = cliente2.post(api("sendMessage"), json={
                "chat_id": chat_id,
                "text": mensaje,
            })

            r.raise_for_status()

    except httpx.HTTPError as e:
        log.warning(
            "no pude mandar el resultado del Router: %s", _sin_token(str(e)),
        )


# --------------------------------------------------- consumidor_libres (T082 Pieza 1)
#
# Mismo patron que el Router de arriba: una funcion que reutiliza el
# modulo de produccion tal cual, corriendo en un hilo aparte porque
# clasificar con Qwen tarda segundos. consumidor_libres.procesar_uno()
# ya se probo contra datos reales en la ronda 28 (ver
# prueba_consumidor_libres.py y el commit d5e3bfc): si Qwen clasifica
# el mensaje como "tarea", queda dada de alta en tareas.json con
# PENDIENTE_DE_REVISION; si no, no se avisa nada aqui (el triaje de
# Qwen de arriba ya cubre esa lectura).

def _avisar_con_consumidor_libres(chat_id: int, mensaje_libre: dict) -> None:
    """Corre en un hilo aparte: clasificar con Qwen tarda segundos."""

    if not CONSUMIDOR_LIBRES_RESPONDE:
        return

    try:
        from extremidades import qwen
        import consumidor_libres
    except Exception as e:
        log.warning("no se puede usar consumidor_libres: %s", e)
        return

    try:
        with _UN_MODELO:
            if _parado() or not qwen.disponible():
                return

            resultado = consumidor_libres.procesar_uno(mensaje_libre)
    except Exception as e:
        log.warning(
            "consumidor_libres fallo con el mensaje suelto: %s",
            _sin_token(str(e)),
        )
        return

    if resultado.get("resultado") != "TAREA_CREADA":
        return

    mensaje = (
        f"\U0001F4CB {resultado['tarea_id']} creada a partir de este mensaje "
        f"(clasificacion automatica, pendiente de tu revision): "
        f"{resultado['titulo']}"
    )

    try:
        with httpx.Client(timeout=15) as cliente2:
            r = cliente2.post(api("sendMessage"), json={
                "chat_id": chat_id,
                "text": mensaje,
                "disable_notification": True,
            })

            r.raise_for_status()

    except httpx.HTTPError as e:
        log.warning(
            "no pude avisar de la tarea creada: %s", _sin_token(str(e)),
        )


# Cuantos 409 seguidos aguantamos antes de entender que hay otro bot
# mas nuevo al mando. A 5 segundos por intento, 12 son un minuto:
# suficiente para no confundirlo con un hipo de la red.
CEDER_TRAS = 12

_conflictos = 0

# Cuantos 401 seguidos aguantamos antes de rendirnos y apagarnos.
# T040 (12/09, hallazgo en vivo): un token invalido en secretos.toml
# NO tira el proceso, solo lo duerme 60s y reintenta con el MISMO
# token ya cargado en memoria — asi que si alguien corrige el token
# mientras el bot sigue corriendo, nunca se entera: un proceso que
# no se cae nunca vuelve a leer secretos.toml. A 60s por intento, 5
# intentos son 5 minutos: apagarse entonces deja que el vigilante nos
# relance (canal/vigilante.py), y el proceso nuevo relee el token de
# secretos.toml desde cero. Sin vigilante corriendo esto no arregla
# nada solo, pero al menos dentro de 5 minutos deja de fingir que
# escucha con un token que Telegram ya ha rechazado.
RENDIRSE_TRAS_401 = 5

_401_seguidos = 0


def _dueno(estado: dict) -> int:
    """El chat de Damian. 0 = ninguno.

    N01 (H01): manda canal.chat_id de config.toml si esta puesto; asi un
    estado_bot.json viejo o tocado no cambia el dueno. Si no, el aprendido con /start.
    """

    return int(valor("canal.chat_id", 0) or 0) or estado.get("chat_id") or 0


def _es_del_dueno(estado: dict, chat_id) -> bool:
    """N04 (hallazgo B, 25/09/2026): el bot atiende SOLO a Damian.

    Antes cualquiera que diera con el bot podia mandarle /start y quedarse
    con el canal (chat_id sobrescrito), usar /orden, /turno, /seguir... y
    contestar las preguntas con los botones. Ahora lo que no venga del chat
    del dueno se ignora en silencio (solo queda en el log). La unica
    excepcion es /start cuando aun no hay dueno: asi se aprende la primera vez.
    """

    dueno = _dueno(estado)

    return bool(dueno) and chat_id == dueno


def _avisar_aprobaciones(cliente: httpx.Client, estado: dict) -> None:
    """T154 F4: avisa por aqui de cada aprobacion nueva, con sus botones.

    Si el envio falla, la peticion ya cuenta como avisada: sigue en
    /aprobaciones y, si nadie contesta, caduca (= NO), que es lo seguro.
    """

    chat = estado.get("chat_id")

    if not chat:
        return

    try:
        from canal import aprobaciones_bot
        mensajes = aprobaciones_bot.avisos_nuevos(estado)
    except Exception as e:
        log.warning("no se pueden leer las aprobaciones: %s", e)
        return

    for m in mensajes:
        try:
            cliente.post(api("sendMessage"), json={"chat_id": chat, **m}).raise_for_status()
        except httpx.HTTPError as e:
            log.warning("no pude avisar de una aprobacion: %s", _sin_token(str(e)))


def procesar_updates(cliente: httpx.Client, estado: dict) -> None:
    global _conflictos, _401_seguidos

    try:
        r = cliente.get(api("getUpdates"), params={
            "offset": estado["offset"],
            "timeout": 25,
        }, timeout=35)

        r.raise_for_status()

        datos = r.json()

        _conflictos = 0
        _401_seguidos = 0

    except (httpx.HTTPError, json.JSONDecodeError) as e:
        codigo = getattr(getattr(e, "response", None), "status_code", 0)

        if codigo == 409:
            _conflictos += 1

            log.warning(
                "409 Conflict: hay otro proceso leyendo los mensajes de "
                "este bot (%d seguidos de %d)", _conflictos, CEDER_TRAS,
            )

            if _conflictos >= CEDER_TRAS:
                log.error(
                    "cedo el paso: %d conflictos seguidos significan que "
                    "hay otro bot mas nuevo al mando. Me apago para "
                    "dejar el canal con uno solo.", _conflictos,
                )

                raise SystemExit(4)

            time.sleep(5)

            return

        # Token revocado o mal pegado. Sin esto el bot gira en
        # silencio para siempre y parece que funciona.
        respuesta = getattr(e, "response", None)

        if respuesta is not None and respuesta.status_code == 401:
            _401_seguidos += 1

            log.critical(
                "TOKEN INVALIDO (401, %d/%d). El bot esta vivo pero sordo: "
                "Telegram rechaza el token de secretos.toml. Pega el "
                "token bueno de BotFather en secretos.toml.",
                _401_seguidos, RENDIRSE_TRAS_401,
            )

            if _401_seguidos >= RENDIRSE_TRAS_401:
                log.error(
                    "me rindo tras %d intentos con este token: me apago "
                    "para que el vigilante me relance y relea "
                    "secretos.toml, por si alguien lo ha corregido "
                    "mientras tanto.", _401_seguidos,
                )

                raise SystemExit(5)

            time.sleep(60)

            return

        log.warning("getUpdates fallo: %s", _sin_token(str(e)))
        time.sleep(5)
        return

    for update in datos.get("result", []):
        estado["offset"] = update["update_id"] + 1

        if "callback_query" in update:
            cq = update["callback_query"]
            chat_boton = cq.get("message", {}).get("chat", {}).get("id")

            if not _es_del_dueno(estado, chat_boton):
                log.warning("boton ignorado: chat %s no es el del dueno", chat_boton)
                continue

            if cq["data"].startswith("APR|"):
                from canal import aprobaciones_bot

                cliente.post(api("answerCallbackQuery"), json={
                    "callback_query_id": cq["id"], "text": "Anotado",
                })

                cliente.post(api("sendMessage"), json={
                    "chat_id": chat_boton, "text": aprobaciones_bot.boton(cq["data"]),
                })

                continue

            id_pregunta, _, indice = cq["data"].partition("|")

            texto_boton = ""

            for fila in cq["message"].get("reply_markup", {}).get("inline_keyboard", []):
                for boton in fila:
                    if boton.get("callback_data") == cq["data"]:
                        texto_boton = boton["text"]

            anotar_respuesta(id_pregunta, texto_boton or indice, "boton")

            cliente.post(api("answerCallbackQuery"), json={
                "callback_query_id": cq["id"],
                "text": f"Anotado: {texto_boton}",
            })

            cliente.post(api("sendMessage"), json={
                "chat_id": cq["message"]["chat"]["id"],
                "text": f"✅ {texto_boton}",
            })

            continue

        mensaje = update.get("message") or {}
        texto = (mensaje.get("text") or "").strip()

        if not texto:
            continue

        chat_id = mensaje["chat"]["id"]

        if not _es_del_dueno(estado, chat_id):
            if texto.startswith("/start") and not _dueno(estado):
                pass  # primera vez: se aprende el dueno aqui abajo
            else:
                log.warning("mensaje ignorado: chat %s no es el del dueno", chat_id)
                continue

        if texto.startswith("/start"):
            estado["chat_id"] = chat_id

            guardar_estado(estado)

            cliente.post(api("sendMessage"), json={
                "chat_id": chat_id,
                "text": (
                    "Canal abierto. A partir de ahora te aviso por aqui.\n\n"
                    "Escribeme cuando quieras y lo leere en cuanto vuelva "
                    "a mirar. Las preguntas te llegaran con botones.\n\n"
                    "Comandos que no esperan a Nexo:\n"
                    "/tarea <titulo> — la da de alta en la cola\n"
                    "/tareas — lo que me toca hacer a mi\n"
                    "/tareas tuyas — lo que te toca a ti\n"
                    "/hecha <id> [nota] — la cierra\n"
                    "/verificar <id> <evidencia> — la marca testeada (qué probaste y qué salió)\n"
                    "/estado — resumen de que esta haciendo Nexo ahora\n"
                    "/parar [motivo] — PARADA DE EMERGENCIA de los turnos automaticos\n"
                    "/seguir — quita la parada\n"
                    "/uso [dias] — turnos y modelo por dia, para ver el gasto\n"
                    "/orden <texto> — orden libre: la apunto y, si puedo, la hago ya\n"
                    "/imagen <texto> — te hago una imagen aquí mismo con la "
                    "GPU de casa (unos 30 s, no gasta plan)\n"
                    "/aprobaciones — lo que espera tu si o tu no (con botones)\n"
                    "/aprobar <id> y /denegar <id> [motivo] — decidir por texto\n\n"
                    "Y si escribes algo suelto, en unos segundos te llega "
                    "aparte una lectura rapida de Qwen, aunque Nexo no "
                    "este mirando en ese momento."
                ),
            })

            log.info("chat_id aprendido: %s", chat_id)

            continue

        if texto.startswith("/parar"):
            cliente.post(api("sendMessage"), json={
                "chat_id": chat_id, "text": _cmd_parar(texto[len("/parar"):]),
            })

            continue

        if texto.startswith("/seguir"):
            cliente.post(api("sendMessage"), json={
                "chat_id": chat_id, "text": _cmd_seguir(texto[len("/seguir"):]),
            })

            continue

        if texto.startswith("/turno"):
            cliente.post(api("sendMessage"), json={
                "chat_id": chat_id, "text": _cmd_turno(texto[len("/turno"):]),
            })

            continue

        if texto.startswith("/orden"):
            cliente.post(api("sendMessage"), json={
                "chat_id": chat_id, "text": _cmd_orden(texto[len("/orden"):]),
            })

            continue

        if texto.startswith("/estado"):
            cliente.post(api("sendMessage"), json={
                "chat_id": chat_id, "text": _texto_estado(),
            })

            continue

        if texto.startswith("/uso"):
            cliente.post(api("sendMessage"), json={
                "chat_id": chat_id, "text": _cmd_uso(texto[len("/uso"):]),
            })

            continue

        if texto.startswith("/ahora"):
            cliente.post(api("sendMessage"), json={
                "chat_id": chat_id, "text": _cmd_ahora(texto[len("/ahora"):]),
            })

            continue

        if texto.startswith("/imagen"):
            cliente.post(api("sendMessage"), json={
                "chat_id": chat_id, "text": _cmd_imagen(texto[len("/imagen"):]),
            })

            continue

        if texto.startswith("/aprobaciones"):
            from canal import aprobaciones_bot

            for m in aprobaciones_bot.cmd_lista():
                cliente.post(api("sendMessage"), json={"chat_id": chat_id, **m})

            continue

        if texto.startswith("/aprobar") or texto.startswith("/denegar"):
            from canal import aprobaciones_bot

            cliente.post(api("sendMessage"), json={
                "chat_id": chat_id,
                "text": aprobaciones_bot.cmd_decidir(
                    texto[len("/aprobar"):], texto.startswith("/aprobar"),
                ),
            })

            continue

        if texto.startswith("/tarea "):
            cliente.post(api("sendMessage"), json={
                "chat_id": chat_id, "text": _cmd_tarea(texto[len("/tarea "):]),
            })

            continue

        if texto == "/tareas" or texto.startswith("/tareas "):
            cliente.post(api("sendMessage"), json={
                "chat_id": chat_id,
                "text": _cmd_tareas(texto[len("/tareas"):]),
            })

            continue

        if texto.startswith("/hecha "):
            cliente.post(api("sendMessage"), json={
                "chat_id": chat_id, "text": _cmd_hecha(texto[len("/hecha "):]),
            })

            continue

        if texto == "/verificar" or texto.startswith("/verificar "):
            cliente.post(api("sendMessage"), json={
                "chat_id": chat_id, "text": _cmd_verificar(texto[len("/verificar"):]),
            })

            continue

        # Cualquier otra cosa: responde a la ultima pregunta abierta,
        # o queda como mensaje suelto.
        pendientes = sorted(SALIDA.glob("*.json.enviado"))

        contestada = False

        for archivo in reversed(pendientes):
            try:
                datos_msg = json.loads(archivo.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            if datos_msg.get("tipo") != "pregunta":
                continue

            if (ENTRADA / f"{datos_msg['id']}.json").exists():
                continue

            anotar_respuesta(datos_msg["id"], texto, "texto")
            contestada = True
            break

        if not contestada:
            mensaje_libre = anotar_libre(texto)

            if QWEN_RESPONDE_LIBRES:
                threading.Thread(
                    target=_avisar_con_qwen,
                    args=(chat_id, texto),
                    daemon=True,
                ).start()

            if ROUTER_RESPONDE_LIBRES:
                threading.Thread(
                    target=_avisar_con_router,
                    args=(chat_id, texto),
                    daemon=True,
                ).start()

            if CONSUMIDOR_LIBRES_RESPONDE:
                threading.Thread(
                    target=_avisar_con_consumidor_libres,
                    args=(chat_id, mensaje_libre),
                    daemon=True,
                ).start()

        cliente.post(api("sendMessage"), json={
            "chat_id": chat_id, "text": "📥 Recibido.",
        })


def main() -> None:
    if not TOKEN:
        raise SinToken(
            "Falta el token. Copia secretos.ejemplo.toml como "
            "secretos.toml y pega el que te da BotFather."
        )

    if not bot_activo():
        log.info("canal.bot_activo = false en config.toml: el bot no arranca (T751)")
        return

    SALIDA.mkdir(parents=True, exist_ok=True)
    ENTRADA.mkdir(parents=True, exist_ok=True)

    if not unico("nexo_bot"):
        log.error(
            "ya hay otro bot de Nexo vivo. Este no arranca: dos a la "
            "vez dan 409 Conflict y se quedan los dos mudos."
        )
        raise SystemExit(3)

    estado = cargar_estado()

    log.info(
        "bot en marcha, pid=%s, chat_id=%s, qwen_responde_libres=%s, "
        "router_responde_libres=%s, consumidor_libres_responde=%s",
        os.getpid(),
        estado.get("chat_id") or "sin asignar",
        QWEN_RESPONDE_LIBRES,
        ROUTER_RESPONDE_LIBRES,
        CONSUMIDOR_LIBRES_RESPONDE,
    )

    with httpx.Client(timeout=30) as cliente:
        while True:
            if not bot_activo():   # T751: apagado en caliente; sale limpio en la siguiente vuelta
                log.info("canal.bot_activo = false: el bot se apaga")
                guardar_estado(estado)
                return

            for archivo in sorted(SALIDA.glob("*.json")):
                try:
                    mensaje = json.loads(archivo.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    archivo.rename(archivo.with_suffix(".json.roto"))
                    continue

                if enviar(cliente, estado, mensaje):
                    archivo.rename(archivo.with_suffix(".json.enviado"))

            procesar_updates(cliente, estado)

            _avisar_aprobaciones(cliente, estado)

            guardar_estado(estado)


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    try:
        main()
    except KeyboardInterrupt:
        log.info("bot detenido a mano")
