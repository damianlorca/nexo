"""Extremidad: imagenes con ComfyUI local.

Tu equipo lleva una Radeon 890M integrada: en Windows y AMD el camino
es DirectML, mas lento que el habitual.

LO QUE FUNCIONA (medido el 12/09/2026, no supuesto):

    ComfyUI v0.3.10 + torch 2.4.1 (DirectML) + checkpoint sd-turbo
    + --directml --lowvram + 512 px + 4 pasos  ->  imagen en 12 s.

Y lo que hay que saber para no volver a perder una noche con esto:

  * La 890M solo admite unos 3 GB por DirectML (pruebas/prueba_directml.py),
    no los 16 GB de memoria compartida que uno esperaria. SDXL Turbo (UNet
    de ~5 GB en fp16) NO cabe; sd-turbo (SD 2.1, ~2,6 GB) si.
  * Cuando se pasa de memoria, ComfyUI no dice "me he quedado sin memoria":
    dice "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe1". Es
    torch leyendo en UTF-8 el mensaje de error del driver, que Windows en
    espanol devuelve en cp1252. Si ves ese Unicode raro, es falta de
    memoria de GPU, no un fallo de texto.
  * ComfyUI sobre DirectML no puede preguntar cuanta memoria hay y se
    inventa 1024 MB. Se probo engañarle con la cifra real (extremidades/
    arrancar_comfyui.py): NO ayuda, porque entonces intenta cargar mas y
    revienta antes. Ese lanzador se deja escrito por si sirve algun dia,
    pero el arranque bueno es el de siempre, con --lowvram.
  * --highvram y --novram no dan ni una sola imagen. --lowvram si.
  * PERO --lowvram solo va fino con ComfyUI recien arrancado. A partir del
    segundo encargo, ComfyUI arrastra su calculo de memoria libre basado en
    el 1 GB inventado, se cree que le quedan 64 MB, carga el modelo a
    cachos ridiculos y o revienta o se queda clavado en el paso 0 de 4.
    Tambien se probo pedirle soltar la GPU con POST /free antes de cada
    encargo: empeora (se queda en esos 64 MB desde el primero).

De ahi el apaño de este modulo: cuando un encargo se rompe, en vez de
rendirse, reinicia ComfyUI y lo intenta otra vez. Un ComfyUI recien
arrancado siempre da su imagen. Cuesta ~30 s de arranque, y por eso
generar() no reinicia por gusto: solo cuando de verdad ha fallado.

Para bocetos va bien; para algo que vayas a publicar, mejor pedirla a Gemini.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from pathlib import Path

import httpx

from manos.shell import ejecutar
from nucleo import permisos
from nucleo.config import RAIZ, salidas, valor
from nucleo.escritura import escribir_atomico
from nucleo.registro import logger


log = logger("extremidades.imagen")


COMFY = Path(r"C:\Users\damia\Desktop\AI\ComfyUI")

ARRANQUE = [
    str(COMFY / "venv" / "Scripts" / "python.exe"),
    "main.py",
    "--directml",
    "--lowvram",
    # Sin esto, el VAE de SD 2.1 en fp16 se va a NaN cada dos por tres
    # y devuelve un cuadro negro en vez de una imagen (medido el 12/09).
    "--fp32-vae",
]

# Un PNG de 512x512 con algo dibujado pesa cientos de KB. Si sale por
# debajo de esto, es el cuadro negro del VAE roto, no una imagen.
MINIMO_CREIBLE = 20 * 1024

# Cuantos encargos lleva el ComfyUI que hay ahora mismo en marcha. A
# partir del primero ya no es de fiar (ver el docstring del modulo), asi
# que el siguiente encargo lo reinicia antes de pedirle nada.
#
# Empieza en 1 a proposito: si al arrancar ya habia un ComfyUI en marcha,
# no sabemos de donde viene ni cuantas imagenes lleva hechas. Lo unico
# que sabemos limpio es el que arranquemos nosotros.
_encargos_hechos = 1


def _url() -> str:
    return valor("imagen.comfyui", "http://127.0.0.1:8188").rstrip("/")


def disponible() -> bool:
    try:
        r = httpx.get(f"{_url()}/system_stats", timeout=5)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def liberar() -> bool:
    """Pide a ComfyUI que suelte los modelos y limpie la memoria de GPU.

    OJO: en esta maquina llamar a esto ANTES de generar empeora las cosas
    (ver el docstring del modulo). Se deja porque viene bien para dejar la
    GPU libre cuando se termina de trabajar, no para preparar un encargo.
    """

    try:
        r = httpx.post(
            f"{_url()}/free",
            json={"unload_models": True, "free_memory": True},
            timeout=30,
        )

        return r.status_code < 400

    except httpx.HTTPError as error:
        log.warning("no se pudo liberar la GPU: %s", error)
        return False


# PID y linea de comando del ComfyUI que lanzo ESTE modulo (reiniciar_comfyui).
ANOTADO = RAIZ / "registros" / "comfyui_pid.json"


def _linea_arranque() -> str:
    """La linea de comando que Windows guarda para Popen(ARRANQUE)."""

    return subprocess.list2cmdline(ARRANQUE)


def _anotar(pid: int) -> None:
    """Apunta la identidad del ComfyUI recien lanzado: PID, linea de comando y hora de creacion del proceso (T929).
    La hora de creacion distingue a nuestro proceso de otro que reutilice el PID con la misma linea."""

    ANOTADO.parent.mkdir(parents=True, exist_ok=True)

    datos = {"pid": int(pid), "linea": _linea_arranque()}

    creado = _identidad(pid)[1]

    if creado:
        datos["creado"] = creado

    escribir_atomico(ANOTADO, json.dumps(datos))


def _anotado() -> dict | None:
    try:
        d = json.loads(ANOTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    if not isinstance(d, dict) or not isinstance(d.get("pid"), int) or not isinstance(d.get("linea"), str):
        return None

    return d


def _identidad(pid: int) -> tuple[str | None, str | None]:
    """(linea de comando, hora de creacion en UTC ISO) del proceso `pid`; None en lo que no se pueda leer."""

    r = ejecutar(
        f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}'; $p.CommandLine; "
        "if ($p) { $p.CreationDate.ToUniversalTime().ToString('o') }",
        timeout=20,
    )

    salida = (r.salida or "").strip() if r.ok else ""

    # La hora de creacion es la ULTIMA linea (la linea de comando de otro proceso podria llevar saltos de linea).
    cuerpo, _, ultima = salida.rpartition(chr(10))

    if cuerpo and re.fullmatch(r"\d{4}-\d\d-\d\dT\S+", ultima.strip()):
        return cuerpo.strip() or None, ultima.strip()

    return salida or None, None


def _linea_de_comando(pid: int) -> str | None:
    """Linea de comando real del proceso `pid`, o None si no existe o no se puede leer."""

    return _identidad(pid)[0]


def _terminar_arbol(pid: int) -> bool:
    """`taskkill /T` del PID dado y su arbol. Solo para un PID cuya identidad ya esta comprobada
    (o que acaba de lanzar este mismo proceso)."""

    r = ejecutar(f"taskkill /PID {int(pid)} /T /F", timeout=45)

    if not r.ok:
        log.warning("terminar ComfyUI (pid %s): codigo %s: %s", pid, r.codigo, r.error.strip())

    return bool(r.ok)


def _matar_comfyui() -> bool:
    """Mata SOLO el ComfyUI que lanzo este modulo. True si lo ha matado.

    Regla de Damian (25/09, CLAUDE.md): nunca por patron ni por nombre;
    solo por el PID exacto que lanzamos, comprobando ANTES que su linea
    de comando es exactamente la que lanzamos (Windows reutiliza PIDs).
    Hasta N02 esto buscaba en Win32_Process todo lo que tuviera
    '*ComfyUI*' en la linea de comando y lo mataba: prohibido.

    El PID de Popen es el del python.exe del venv, que en Windows es un
    lanzador: el proceso que abre el puerto 8188 es su hijo (por eso el
    12/09 matar solo ese PID dejaba el puerto ocupado). Se usa
    `taskkill /T`, que termina ese PID y SU arbol, nada mas.

    Un ComfyUI que no lanzamos nosotros (arrancado a mano, o de antes de
    anotar) no se toca nunca.
    """

    d = _anotado()

    if d is None or d["linea"] != _linea_arranque():
        return False

    linea, creado = _identidad(d["pid"])

    if linea != d["linea"] or (d.get("creado") and creado != d["creado"]):
        # Ya no existe, o ese PID es ahora de otro proceso (otra linea u otra hora de creacion): no es nuestro.
        return False

    if not _terminar_arbol(d["pid"]):
        return False

    # El PID queda libre para Windows: el registro ya no es de nadie y no debe poder apuntar a otro proceso.
    try:
        ANOTADO.unlink()
    except OSError:
        pass

    return True


def reiniciar_comfyui(espera_max: int = 90) -> bool:
    """Deja un ComfyUI recien arrancado y esperando encargos."""

    log.info("reiniciando ComfyUI para recuperar la GPU")

    _matar_comfyui()

    time.sleep(4)

    if disponible():
        # Sigue respondiendo un ComfyUI que no es nuestro (o no se ha
        # podido parar). No se toca y no se lanza otro encima del puerto.
        log.warning("hay un ComfyUI en marcha que no lance yo: no lo toco")

        return False

    # T048: arrancar ComfyUI pasa por el mismo sistema de permisos que parar (verde/ambar/rojo).
    try:
        permisos.exigir(permisos.nivel_de_comando(_linea_arranque()), "lanzar ComfyUI", _linea_arranque()[:120])
        permisos.exigir(permisos.nivel_de_ruta(COMFY, escritura=False), "lanzar ComfyUI desde", str(COMFY))
    except (permisos.Bloqueado, permisos.NecesitaAprobacion) as error:
        log.warning("no arranco ComfyUI: %s", error)

        return False

    proceso = subprocess.Popen(
        ARRANQUE,
        cwd=str(COMFY),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )

    try:
        _anotar(proceso.pid)

    except Exception as error:  # noqa: BLE001 - lo que sea: sin anotar, nadie podria pararlo luego
        # T928: un ComfyUI que no queda anotado no se podria parar nunca (y ocuparia el puerto). El PID es el
        # que acabamos de lanzar nosotros (tenemos el Popen), asi que se termina su arbol sin mas comprobaciones.
        log.error("no pude anotar el ComfyUI recien lanzado (%s): lo termino", error)

        if not _terminar_arbol(proceso.pid):
            proceso.kill()

        return False

    limite = time.time() + espera_max

    while time.time() < limite:
        time.sleep(3)

        if disponible():
            log.info("ComfyUI de vuelta")

            global _encargos_hechos

            _encargos_hechos = 0

            return True

    log.error("ComfyUI no ha vuelto en %ss", espera_max)

    return False


def _flujo(prompt: str, negativo: str, semilla: int) -> dict:
    """Flujo minimo de texto a imagen.

    Ajusta "ckpt_name" al checkpoint que tengas instalado en ComfyUI.
    """

    ancho = valor("imagen.ancho", 512)
    alto = valor("imagen.alto", 512)
    pasos = valor("imagen.pasos", 4)
    cfg = valor("imagen.cfg", 1.0)
    modelo = valor("imagen.checkpoint", "sd_turbo.safetensors")

    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": semilla, "steps": pasos, "cfg": cfg,
                "sampler_name": "euler_ancestral", "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0], "positive": ["6", 0],
                "negative": ["7", 0], "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": modelo},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": ancho, "height": alto, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negativo, "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "agente", "images": ["8", 0]},
        },
    }


def _un_intento(prompt: str, negativo: str, semilla: int, espera_max: int) -> Path:
    """Encarga una imagen y espera a que salga. Levanta si no sale."""

    cliente_id = uuid.uuid4().hex

    r = httpx.post(
        f"{_url()}/prompt",
        json={"prompt": _flujo(prompt, negativo, semilla), "client_id": cliente_id},
        timeout=30,
    )

    r.raise_for_status()

    id_trabajo = r.json()["prompt_id"]

    log.info("imagen encargada: %s", id_trabajo)

    limite = time.time() + espera_max

    while time.time() < limite:
        time.sleep(2)

        try:
            respuesta = httpx.get(f"{_url()}/history/{id_trabajo}", timeout=15)

        except httpx.HTTPError:
            continue        # transitorio: red, timeout...

        if respuesta.status_code >= 400:
            # T931: un 4xx/5xx no es "todavia no": antes caia en el except de abajo y acababa como timeout.
            raise RuntimeError(f"ComfyUI respondio HTTP {respuesta.status_code} al consultar el encargo")

        try:
            historial = respuesta.json()

        except json.JSONDecodeError:
            continue        # respuesta a medias: se vuelve a preguntar

        if id_trabajo not in historial:
            continue

        entrada = historial[id_trabajo]

        for datos in entrada.get("outputs", {}).values():
            for img in datos.get("images", []):
                bruto = httpx.get(f"{_url()}/view", params={
                    "filename": img["filename"],
                    "subfolder": img.get("subfolder", ""),
                    "type": img.get("type", "output"),
                }, timeout=60)

                bruto.raise_for_status()

                destino = salidas() / f"imagen_{time.strftime('%Y%m%d_%H%M%S')}.png"

                if len(bruto.content) < MINIMO_CREIBLE:
                    raise RuntimeError(
                        f"ComfyUI ha devuelto una imagen vacia "
                        f"({len(bruto.content)} bytes): el VAE se ha ido a NaN"
                    )

                destino.write_bytes(bruto.content)

                log.info("imagen guardada: %s", destino.name)

                return destino

        # ComfyUI ha terminado con este encargo pero no ha dado ninguna
        # imagen: se ha roto por el camino. Sin esto, la espera seguia hasta
        # agotar espera_max y luego culpaba a la lentitud de la GPU, cuando
        # el fallo real (casi siempre, falta de memoria) estaba en su log.
        estado = entrada.get("status", {})

        if estado.get("completed") is not None or estado.get("status_str"):
            raise RuntimeError(
                "ComfyUI termino el encargo sin devolver imagen "
                f"(estado: {estado.get('status_str', 'desconocido')})"
            )

    raise TimeoutError(f"ComfyUI no ha terminado en {espera_max}s")


def generar(
    prompt: str,
    negativo: str = "blurry, low quality, watermark, text",
    semilla: int | None = None,
    espera_max: int = 120,
) -> Path:
    """Genera una imagen y devuelve la ruta del archivo.

    Si el encargo se rompe (casi siempre, la GPU sin memoria tras un
    encargo anterior), reinicia ComfyUI y lo intenta una segunda vez.
    """

    if not disponible() and not reiniciar_comfyui():
        raise RuntimeError(
            "ComfyUI no responde y no he conseguido levantarlo. A mano:\n    "
            + " ".join(ARRANQUE)
            + f"\n(desde {COMFY}). O pide la imagen a Gemini si corre prisa."
        )

    semilla = semilla if semilla is not None else int(time.time()) % 2**31

    global _encargos_hechos

    # ComfyUI solo es de fiar recien arrancado. Reiniciar cuesta 13 s;
    # esperar a que se atasque, 150 s. Mejor pagar los 13.
    if _encargos_hechos:
        log.info("ComfyUI ya usado (o de origen desconocido): lo reinicio antes")

        if not reiniciar_comfyui():
            if not disponible():
                raise RuntimeError(
                    "No he podido reiniciar ComfyUI y ahora no responde. A mano:\n    "
                    + " ".join(ARRANQUE) + f"\n(desde {COMFY})."
                )

            # Uno que no lanzamos nosotros: se usa tal cual, sin matarlo.
            log.warning("no he podido reiniciar ComfyUI: uso el que hay en marcha")

    try:
        imagen = _un_intento(prompt, negativo, semilla, espera_max)

        _encargos_hechos += 1

        return imagen

    except (RuntimeError, TimeoutError, httpx.HTTPError) as primero:
        log.warning("primer intento fallido (%s); reinicio ComfyUI", primero)

        if not reiniciar_comfyui():
            raise RuntimeError(
                f"La imagen fallo ({primero}) y ComfyUI no vuelve a levantarse."
            ) from primero

        try:
            imagen = _un_intento(prompt, negativo, semilla, espera_max)

            _encargos_hechos += 1

            return imagen

        except (RuntimeError, TimeoutError, httpx.HTTPError) as segundo:
            raise RuntimeError(
                f"La imagen ha fallado dos veces, la segunda con ComfyUI recien "
                f"arrancado: {segundo}. Mira el ultimo registros/comfyui_*.log. "
                "Si aparece un UnicodeDecodeError con el byte 0xe1, es falta de "
                "memoria de GPU: baja la resolucion o usa un checkpoint menor."
            ) from segundo
