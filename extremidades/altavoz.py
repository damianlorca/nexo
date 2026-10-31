# -*- coding: utf-8 -*-
"""Extremidad: el altavoz "Damián" (Google Home Mini) por Cast y el brief hablado (T697, via B sin cuentas).

Disparo (probado con Damian el 05/10): su rutina de Google Home ("Hey Google, nexo") pone el volumen del altavoz
"Damián" al 13 %, que por Cast se lee como 0.130. El Oyente:
  - solo escucha al altavoz de nombre EXACTO "Damián" (nunca "marina" ni la tele); si no lo encuentra, no hace nada;
  - guarda el ultimo volumen normal (salidas/home/estado_altavoz.json);
  - al ver 0.13 lo RESTAURA al instante y, solo si lo ha podido restaurar, cuenta el brief. Si no puede, no
    reproduce nada y deja un aviso en el Centro (nucleo/avisos.py);
  - NUNCA cambia el volumen por su cuenta: lo unico que hace es devolverlo al que habia antes del 13 %;
  - si el altavoz desaparece, lo vuelve a buscar: cada BUSCAR_CADA segundos al principio y, mientras no aparezca,
    cada vez mas espaciado (hasta ESPERA_MAX); con el PC en la red de casa, como mucho cada EN_CASA_CADA s. Busca tambien en la ultima IP buena (salidas/home/estado_altavoz.json)
    y deja en el registro cuantos dispositivos Cast ve. El Centro dice "altavoz no visible (el PC esta fuera de
    casa?)" en vez de reintentar sin decir nada (05/10: desde las 15:19 el PC estaba en otra red).
Lo arranca la web (interfaz/app.py, solo en la instancia definitiva) en un hilo.

La voz: Gemini "Bloom" (extremidades/voz_gemini.py); sin cuota o con fallo, Piper (extremidades/voz.py).
"""
from __future__ import annotations

import functools
import http.server
import json
import socket
import threading
import time
import unicodedata
from pathlib import Path

from nucleo.config import salidas, valor
from nucleo.escritura import escribir_atomico
from nucleo.registro import logger

log = logger("extremidades.altavoz")

NOMBRE = "Damián"
HOSTS = ["192.168.0.104"]
DISPARO = 0.13
TOLERANCIA = 0.004
ESPERA_RESTAURAR = 5.0
BUSCAR_CADA = 60.0
ESPERA_MAX = 900.0                     # s: sin altavoz, como mucho una busqueda cada 15 min
# Damian 05/10 (prueba real, 22:16): al volver a casa tardo en verlo porque la espera iba por 15 min. Con el PC en
# la red de casa (la /24 del altavoz, 192.168.0.x) se busca como mucho cada EN_CASA_CADA s, y una espera larga
# se corta a trozos de PASO_ESPERA s en cuanto el PC vuelve a casa.
EN_CASA_CADA = 45.0
PASO_ESPERA = 30.0
NOCHE = (0, 7)                         # horas [0, 7): al 13 % de madrugada se devuelve el volumen pero no se habla
FUERA_DE_CASA = "altavoz no visible (¿el PC está fuera de casa?)"

# Ultima busqueda real (la lee el Centro): cuando, cuantos dispositivos Cast se vieron y si estaba "Damián"
ULTIMA_BUSQUEDA: dict = {}

_contando = threading.Lock()   # un brief cada vez (oyente y boton comparten el candado)


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def carpeta() -> Path:
    return salidas() / "home"


def _estado_ruta() -> Path:
    return carpeta() / "estado_altavoz.json"


def _leer_estado() -> dict:
    try:
        d = json.loads(_estado_ruta().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar_estado(**cambios) -> None:
    try:
        carpeta().mkdir(parents=True, exist_ok=True)
        escribir_atomico(_estado_ruta(), json.dumps({**_leer_estado(), **cambios}))
    except OSError as e:
        log.warning("altavoz: no pude guardar su estado (%s)", type(e).__name__)


def leer_volumen_normal() -> float | None:
    try:
        v = _leer_estado().get("volumen_normal")
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def guardar_volumen_normal(v: float) -> None:
    _guardar_estado(volumen_normal=round(float(v), 3), cuando=time.strftime("%Y-%m-%d %H:%M:%S"))


def ultima_ip() -> str | None:
    ip = _leer_estado().get("ultima_ip")
    return ip if isinstance(ip, str) and ip else None


def guardar_ultima_ip(ip: str) -> None:
    if ip and ip != ultima_ip():
        _guardar_estado(ultima_ip=ip, ip_cuando=time.strftime("%Y-%m-%d %H:%M:%S"))


def hosts_conocidos(hosts: list[str] | None = None) -> list[str]:
    """Los del config y, ademas, la ultima IP en la que se encontro de verdad (por si el router le dio otra)."""
    lista = list(hosts or valor("altavoz.hosts", HOSTS))
    ip = ultima_ip()
    if ip and ip not in lista:
        lista.append(ip)
    return lista


def ip_local(destino: str) -> str | None:
    """La IP del PC con la que saldria hacia `destino` (UDP connect: no manda nada)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((destino, 8009))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None


def fuera_de_casa(hosts: list[str] | None = None, ip_local_=None) -> bool:
    """True si la IP del PC no esta en la misma red /24 que ninguna IP conocida del altavoz."""
    ip_local_ = ip_local_ or ip_local
    for h in hosts_conocidos(hosts):
        mia = ip_local_(h)
        if mia and mia.rsplit(".", 1)[0] == h.rsplit(".", 1)[0]:
            return False
    return True


def es_disparo(v) -> bool:
    return v is not None and abs(float(v) - DISPARO) <= TOLERANCIA


def avisar(titulo: str, cuerpo: str) -> None:
    from nucleo import avisos
    avisos.emitir("altavoz", titulo, cuerpo, ruta="/", clave=f"altavoz:{titulo}")


# ------------------------------------------------------------------ Cast (lo unico que toca la red local)
def buscar(nombre: str = NOMBRE, hosts: list[str] | None = None, timeout: float = 10):
    """(chromecast, browser) del altavoz de nombre EXACTO, o (None, None). Quien lo use cierra el browser."""
    import pychromecast
    casts, browser = pychromecast.get_listed_chromecasts(friendly_names=[nombre], known_hosts=hosts_conocidos(hosts),
                                                         discovery_timeout=timeout)
    exactos = [c for c in casts if _nfc(c.cast_info.friendly_name) == _nfc(nombre)]
    vistos = len(getattr(browser, "devices", None) or {})
    ULTIMA_BUSQUEDA.update(cuando=time.strftime("%Y-%m-%d %H:%M:%S"), vistos=vistos, encontrado=len(exactos) == 1)
    if len(exactos) != 1:
        cerrar_busqueda(browser)
        log.info("altavoz: veo %d dispositivos Cast; llamados %r exactamente: %d", vistos, nombre, len(exactos))
        return None, None
    cc = exactos[0]
    cc.wait(timeout=timeout)
    guardar_ultima_ip(cc.cast_info.host)
    return cc, browser


def cerrar_busqueda(browser) -> None:
    if browser is None:
        return
    try:
        import pychromecast
        pychromecast.discovery.stop_discovery(browser)
    except Exception:   # noqa: BLE001
        pass


def reproducir(cc, wav: Path, espera_max: float = 180) -> str:
    """Sirve el WAV por HTTP en la IP local que ve el altavoz y lo reproduce al volumen que tenga. Devuelve el
    idle_reason (FINISHED si sono entero)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((cc.cast_info.host, 8009))
    ip_pc = s.getsockname()[0]
    s.close()
    srv = http.server.ThreadingHTTPServer(
        (ip_pc, 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(wav.parent)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        mc = cc.media_controller
        mc.play_media(f"http://{ip_pc}:{srv.server_address[1]}/{wav.name}", "audio/wav", title="NEXO")
        mc.block_until_active(timeout=15)
        visto, fin = False, time.time() + espera_max
        while time.time() < fin:
            time.sleep(0.5)
            st = mc.status.player_state
            visto = visto or st == "PLAYING"
            if visto and st == "IDLE":
                break
        return str(mc.status.idle_reason)
    finally:
        srv.shutdown()


# ------------------------------------------------------------------ el brief
_ERRORES_DE_CODIGO = (TypeError, AttributeError, NameError, ImportError, AssertionError)


def sintetizar(texto: str, destino: Path) -> tuple[Path, str]:
    """(wav, "gemini"|"piper"). Gemini Bloom primero; ante CUALQUIER fallo suyo (T886, no solo SinVoz), Piper."""
    from extremidades import voz, voz_gemini
    try:
        return voz_gemini.narrar(texto, destino), "gemini"
    except voz_gemini.SinVoz as e:
        log.info("altavoz: %s -> Piper", e)
    except _ERRORES_DE_CODIGO:
        # T886: un error de programacion en la ruta de Gemini tampoco deja el brief sin voz, pero NO se esconde:
        # sale con traza en el log (y se arregla); un fallo de la red/servicio, en cambio, es lo esperable.
        log.exception("altavoz: Gemini TTS fallo por un ERROR DE CODIGO -> Piper (arreglarlo)")
    except Exception as e:   # noqa: BLE001 - T886: ante CUALQUIER otro fallo de Gemini (red, formato, disco), Piper
        log.warning("altavoz: Gemini TTS fallo (%s: %s) -> Piper", type(e).__name__, str(e)[:200])
    return voz.narrar(texto, destino), "piper"


def contar(cc=None, componer=None, sintetizar_=None, reproducir_=None, buscar_=None) -> dict:
    """Compone el brief, lo pasa a voz y lo reproduce en "Damián". Sin el altavoz a mano, lo busca y lo suelta.
    Un brief cada vez: si ya hay uno sonando devuelve {"ok": False, "motivo": "ya está sonando"}."""
    from nucleo import brief, parada
    componer = componer or brief.componer
    sintetizar_ = sintetizar_ or sintetizar
    reproducir_ = reproducir_ or reproducir
    buscar_ = buscar_ or buscar
    if parada.activa():
        return {"ok": False, "motivo": "PARADA activa: no cuento nada"}
    if not _contando.acquire(blocking=False):
        return {"ok": False, "motivo": "ya está sonando"}
    browser = None
    try:
        texto = componer()
        wav, motor = sintetizar_(texto, carpeta() / "brief.wav")
        if cc is None:
            cc, browser = buscar_()
            if cc is None:
                return {"ok": False, "motivo": f"no encuentro el altavoz {NOMBRE!r}", "motor": motor}
        fin = reproducir_(cc, wav)
        log.info("altavoz: brief contado (%s, %d palabras, %s)", motor, len(texto.split()), fin)
        return {"ok": True, "motor": motor, "fin": fin, "palabras": len(texto.split())}
    except Exception as e:   # noqa: BLE001 - un brief roto no tumba la web ni el oyente
        log.warning("altavoz: el brief fallo (%s: %s)", type(e).__name__, str(e)[:200])
        return {"ok": False, "motivo": f"{type(e).__name__}"}
    finally:
        if browser is not None:
            try:
                cc.disconnect(timeout=5)
            except Exception:   # noqa: BLE001
                pass
            cerrar_busqueda(browser)
        _contando.release()


def contar_en_hilo(cc=None, avisar_fallo: bool = True, contar_=None) -> None:
    contar_ = contar_ or contar

    def correr():
        r = contar_(cc=cc)
        if not r.get("ok") and avisar_fallo and r.get("motivo") != "ya está sonando":
            avisar("El brief no ha sonado", r.get("motivo", ""))
    threading.Thread(target=correr, name="nexo-brief", daemon=True).start()


# ------------------------------------------------------------------ el oyente del volumen
class Oyente:
    """Escucha el volumen de "Damián". Todo lo de Cast se inyecta para probarlo sin altavoz."""

    def __init__(self, buscar_=buscar, contar_=None, avisar_=avisar, leer_=leer_volumen_normal,
                 guardar_=guardar_volumen_normal, esperar_restaurar: float = ESPERA_RESTAURAR,
                 buscar_cada: float = BUSCAR_CADA, espera_max: float = ESPERA_MAX, fuera_=None, hora_=None,
                 en_casa_cada: float = EN_CASA_CADA, paso_espera: float = PASO_ESPERA):
        self._buscar = buscar_
        self._contar = contar_ or (lambda cc: contar_en_hilo(cc=cc))
        self._avisar = avisar_
        self._guardar = guardar_
        self.volumen_normal = leer_()
        self._esperar = esperar_restaurar
        self._buscar_cada = buscar_cada
        self._espera_max = espera_max
        self._fuera = fuera_ or fuera_de_casa
        self._hora = hora_ or (lambda: time.localtime().tm_hour)
        self._en_casa_cada = en_casa_cada
        self._paso = paso_espera
        self.fuera: bool | None = None     # ultima comprobacion de la red del PC
        self.fallos = 0                     # busquedas seguidas sin encontrarlo
        self.no_visible: str | None = None  # texto para el Centro mientras no se ve
        self._parar = threading.Event()
        self._perdido = threading.Event()
        self._restaurado = threading.Event()
        self._objetivo: float | None = None
        self._atendiendo = threading.Lock()
        self.cc = None

    # -- callbacks de pychromecast (llegan en su hilo: aqui no se espera nada)
    def new_cast_status(self, st) -> None:
        self.ver_volumen(getattr(st, "volume_level", None))

    def new_connection_status(self, st) -> None:
        if getattr(st, "status", "") in ("LOST", "FAILED", "DISCONNECTED"):
            log.info("altavoz: conexion %s", st.status)
            self._perdido.set()

    def ver_volumen(self, v) -> None:
        if v is None:
            return
        v = float(v)
        if self._objetivo is not None:          # restaurando: solo cuenta la confirmacion
            if abs(v - self._objetivo) <= TOLERANCIA:
                self._restaurado.set()
            return
        if es_disparo(v):
            self._disparo()
            return
        if self.volumen_normal is None or abs(v - self.volumen_normal) > TOLERANCIA / 2:
            self.volumen_normal = v
            self._guardar(v)

    def _disparo(self, contar: bool = True) -> None:
        if self._atendiendo.acquire(blocking=False):
            threading.Thread(target=self._atender, args=(contar,), name="nexo-altavoz-disparo", daemon=True).start()

    def _de_noche(self) -> bool:
        return NOCHE[0] <= self._hora() < NOCHE[1]

    def _atender(self, contar: bool = True) -> None:
        """Restaura el volumen normal y, SOLO si lo confirma (y contar), cuenta el brief."""
        try:
            normal = self.volumen_normal
            if normal is None:
                self._avisar("Brief no reproducido", "El altavoz se puso al 13 % pero no sé el volumen de antes: "
                             "no lo toco ni reproduzco nada. Ponlo a mano donde quieras.")
                return
            self._restaurado.clear()
            self._objetivo = normal
            try:
                self.cc.set_volume(normal)
                ok = self._restaurado.wait(self._esperar)
                if not ok:   # sin evento: se mira el estado directamente
                    ok = abs(float(self.cc.status.volume_level) - normal) <= TOLERANCIA
            except Exception as e:   # noqa: BLE001
                log.warning("altavoz: no pude restaurar el volumen (%s)", type(e).__name__)
                ok = False
            finally:
                self._objetivo = None
            if not ok:
                self._avisar("Brief no reproducido", f"No he podido devolver el altavoz a su volumen "
                             f"({round(normal * 100)} %): no reproduzco nada.")
                return
            if not contar:
                log.info("altavoz: 13 %% visto de madrugada, volumen devuelto a %.2f; no cuento el brief", normal)
                self._avisar("Brief no contado", "El altavoz estaba al 13 % de madrugada: le he devuelto su volumen "
                             "y no he dicho nada. Si lo quieres, «Cuéntamelo ahora» en el Centro.")
                return
            log.info("altavoz: 13 %% visto, volumen devuelto a %.2f; cuento el brief", normal)
            self._contar(self.cc)
        finally:
            self._atendiendo.release()

    # -- bucle: buscar, escuchar y volver a buscar si desaparece
    def espera(self) -> float:
        """Cuanto esperar a la siguiente busqueda: BUSCAR_CADA y, con cada fallo seguido, el doble (tope ESPERA_MAX)."""
        base = min(self._buscar_cada * (2 ** max(self.fallos - 1, 0)), self._espera_max)
        if self.fallos and self.fuera is False:   # en casa: nada de esperar 15 min
            return min(base, self._en_casa_cada)
        return base

    def _comprobar_fuera(self) -> bool:
        try:
            self.fuera = bool(self._fuera())
        except Exception:   # noqa: BLE001
            self.fuera = False
        return self.fuera

    def esperar_busqueda(self) -> float:
        """Espera hasta la siguiente busqueda a trozos de PASO_ESPERA; si mientras tanto el PC vuelve a la red de
        casa, corta en cuanto lleve EN_CASA_CADA s. Devuelve lo esperado."""
        total, esperado = self.espera(), 0.0
        while esperado < total and not self._parar.is_set():
            paso = min(self._paso, total - esperado)
            self._parar.wait(paso)
            esperado += paso
            if esperado >= self._en_casa_cada and esperado < total and not self._comprobar_fuera():
                break
        return esperado

    def conectar(self) -> bool:
        cc, browser = self._buscar()
        if cc is None:
            self.fallos += 1
            fuera = self._comprobar_fuera()
            vistos = ULTIMA_BUSQUEDA.get("vistos")
            self.no_visible = FUERA_DE_CASA if fuera else (
                f"altavoz no visible: veo {vistos} dispositivos Cast y ninguno se llama «{NOMBRE}»"
                if vistos is not None else f"altavoz no visible: no encuentro «{NOMBRE}»")
            if self.fallos == 1:
                log.info("altavoz: %s; lo vuelvo a buscar cada vez mas espaciado (hasta %d s)",
                         self.no_visible, self._espera_max)
            return False
        if self.fallos:
            log.info("altavoz: visible otra vez tras %d busquedas", self.fallos)
        self.fallos, self.no_visible = 0, None
        self._perdido.clear()
        cc.register_status_listener(self)
        try:
            cc.register_connection_listener(self)
        except AttributeError:
            pass
        self.cc = cc
        self._browser = browser
        v = getattr(cc.status, "volume_level", None) if cc.status is not None else None
        if v is not None and not es_disparo(v):
            self.ver_volumen(v)
        elif es_disparo(v):
            # Damian 05/10 (22:16): se puso al 13 % antes de que NEXO lo viera (volvia a casa). Antes se ignoraba;
            # ahora se devuelve su volumen y se cuenta el brief (de madrugada, solo el volumen).
            log.info("altavoz: ya estaba al 13 %% al encontrarlo; lo atiendo como un disparo%s",
                     " (de madrugada: sin brief)" if self._de_noche() else "")
            self._disparo(contar=not self._de_noche())
        log.info("altavoz: escuchando %r (volumen normal %s)", NOMBRE, self.volumen_normal)
        return True

    def soltar(self) -> None:
        cc, self.cc = self.cc, None
        if cc is not None:
            try:
                cc.disconnect(timeout=5)
            except Exception:   # noqa: BLE001
                pass
        cerrar_busqueda(getattr(self, "_browser", None))
        self._browser = None

    def correr(self) -> None:
        while not self._parar.is_set():
            try:
                if self.cc is None and not self.conectar():
                    self.esperar_busqueda()
                    continue
                if self._perdido.wait(self._buscar_cada) and not self._parar.is_set():
                    log.info("altavoz: perdido; lo vuelvo a buscar")
                    self.soltar()
            except Exception as e:   # noqa: BLE001 - el oyente no muere nunca por un fallo de red
                log.warning("altavoz: fallo del oyente (%s)", type(e).__name__)
                self.soltar()
                self._parar.wait(self._buscar_cada)
        self.soltar()

    def parar(self) -> None:
        self._parar.set()
        self._perdido.set()

    def arrancar(self) -> threading.Thread:
        h = threading.Thread(target=self.correr, name="nexo-altavoz", daemon=True)
        h.start()
        return h


_oyente: Oyente | None = None


def oyente_activo() -> Oyente | None:
    return _oyente


def estado_oyente() -> dict | None:
    """Para el Centro: None sin oyente; si no, {"visible": bool, "texto": str, "fallos": int, "vistos": int|None}."""
    o = _oyente
    if o is None:
        return None
    if o.cc is not None:
        return {"visible": True, "texto": f"escuchando el altavoz «{NOMBRE}»", "fallos": 0,
                "vistos": ULTIMA_BUSQUEDA.get("vistos")}
    return {"visible": False, "texto": o.no_visible or "buscando el altavoz…", "fallos": o.fallos,
            "vistos": ULTIMA_BUSQUEDA.get("vistos")}


def arrancar_oyente() -> Oyente:
    global _oyente
    _oyente = Oyente()
    _oyente.arrancar()
    return _oyente


def parar_oyente() -> None:
    global _oyente
    if _oyente is not None:
        _oyente.parar()
    _oyente = None
