# -*- coding: utf-8 -*-
"""Vigia de la interfaz web: la arranca y la relanza si /salud deja de responder.

Lo lanza la Tarea Programada "NEXO interfaz" al iniciar sesion, al desbloquear y cada 10 min (T1028;
scripts/registrar_autoarranque.ps1)
con pythonw, como proceso aparte de la web: si la web se cuelga o muere, el vigia sigue.

- Respeta la parada de la web: con memoria/INTERFAZ_DETENIDA (parar_interfaz.bat) no la relanza.
- La PARADA de NEXO (memoria/PARADA_NEXO) NO la para: la web es donde se pulsa "Seguir" y con
  PARADA ya bloquea las ordenes (decision de Damian, 25/09).
- Si en el puerto responde OTRO programa, no lanza nada: lo anota y espera (lanzar solo daria
  "puerto ocupado" en bucle).
- Solo mata el PID que lanzo el mismo y solo si su linea de comando es EXACTAMENTE la de la web
  (Windows reutiliza PIDs: tras reiniciar, ese numero puede ser el bot o el turno de NEXO).
- Si la web no vuelve tras relanzarla, espera cada vez mas (hasta 10 min) para no martillear.
- T868: si cambia codigo de interfaz/ (rutas, plantillas, estaticos) despues de lanzar la web y lleva 30 s quieto,
  la reinicia sola (la web sana seguia sirviendo codigo viejo: 404 en rutas nuevas). Mismas reglas: solo la web
  que lanzo el vigia, por su PID exacto; como mucho una vez cada 2 min y NUNCA con un turno de NEXO en marcha
  (los turnos cuelgan de la web y `taskkill /T` los mataria: se espera a que acabe).
- La salida de uvicorn va a registros/interfaz.log, rotado al (re)lanzar (5 MB x 3 copias).
- Hito movil: cada ~5 min mira si `tailscale serve` sigue publicando la web y AVISA en el log si
  falta o si hay un funnel (publico). No lo pone ni lo quita: eso es activar_movil.bat/quitar_movil.bat.

Uso:  .venv\\Scripts\\python.exe -m interfaz.vigia [--parar | --seguir | --estado]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# Solo config (ligero): si el vigia importara la web entera, un error en ella lo tumbaria tambien.
from interfaz.config import APP_ID, PUERTO  # noqa: E402

DETENIDA = RAIZ / "memoria" / "INTERFAZ_DETENIDA"
FICHERO_PID = RAIZ / "memoria" / "interfaz.pid"
LOG_WEB = RAIZ / "registros" / "interfaz.log"
PYTHONW = RAIZ / ".venv" / "Scripts" / "pythonw.exe"
PYTHON = RAIZ / ".venv" / "Scripts" / "python.exe"

INTERVALO = 30            # segundos entre comprobaciones con la web sana
FALLOS_PARA_RELANZAR = 2  # seguidos: un fallo suelto (web ocupada un momento) no la reinicia
ESPERA_ARRANQUE = 20      # segundos que se da a la web para responder tras lanzarla
ESPERA_MAX = 600          # techo del backoff si no consigue levantarla
ROTAR_BYTES = 5 * 1024 * 1024
COPIAS_LOG = 3

# Resultados de sondear()
SANA, CAIDA, AJENA = "sana", "caida", "ajena"

PASADAS_SERVE = 10        # cada cuantas pasadas sanas se mira tailscale serve (~5 min)

# T868: codigo de la web que, si cambia despues de lanzarla, pide reiniciarla.
CODIGO_WEB = RAIZ / "interfaz"
EXT_CODIGO = {".py", ".html", ".js", ".css", ".svg", ".json", ".webmanifest"}
SALTAR_DIRS = {"tests", "__pycache__", "scripts"}
QUIETO_CODIGO = 30        # s sin tocarse el ultimo archivo cambiado (una edicion o un merge a medias no reinicia)
REINICIO_MIN = 120        # s entre dos reinicios por codigo (si la web nueva no arranca, no se entra en bucle)
TURNO_EN_MARCHA = RAIZ / "memoria" / "turno_en_marcha.json"


def mirar_serve(puerto: int = PUERTO) -> tuple[str, str] | None:
    """(nivel, mensaje) sobre tailscale serve, o None si no hay Tailscale con HTTPS."""
    from interfaz import tailnet
    datos = tailnet.estado()
    if not datos:
        return None
    s = tailnet.serve(datos["host"], puerto)
    if s is None:
        return None
    if s["funnel"]:
        return ("error", "tailscale FUNNEL activo: algo esta publicado en internet. Quitalo "
                         "(tailscale funnel reset) salvo que lo hayas puesto tu a proposito")
    if not s["activo"]:
        return ("warning", "tailscale serve no publica la web: el movil no entra (activar_movil.bat)")
    return ("info", f"tailscale serve publica la web en https://{datos['host']}")


def cambio_de_codigo(desde: float, ahora: float | None = None, raiz: Path = CODIGO_WEB,
                     quieto: float = QUIETO_CODIGO) -> str | None:
    """Ruta (relativa a la raiz) del archivo de codigo de la web modificado DESPUES de `desde`, o None. Solo cuenta
    si el mas reciente lleva `quieto` s sin tocarse: mientras alguien edita o git escribe, se espera."""
    ahora = time.time() if ahora is None else ahora
    nuevo: tuple[float, Path] | None = None
    for dirpath, dirs, ficheros in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in SALTAR_DIRS]
        for f in ficheros:
            p = Path(dirpath) / f
            if p.suffix.lower() not in EXT_CODIGO:
                continue
            try:
                m = p.stat().st_mtime
            except OSError:
                continue
            if m > desde and (nuevo is None or m > nuevo[0]):
                nuevo = (m, p)
    if nuevo is None or ahora - nuevo[0] < quieto:
        return None
    return nuevo[1].relative_to(raiz).as_posix()


def turno_en_marcha(fichero: Path = TURNO_EN_MARCHA) -> bool:
    """Hay un turno de NEXO vivo (los lanza la web: son hijos suyos y un reinicio con /T los mataria). Ante la duda
    (no se puede leer o comprobar), se cuenta como en marcha: mejor esperar que matar un turno."""
    try:
        d = json.loads(fichero.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False
    except (OSError, ValueError):
        return True
    if not isinstance(d, dict) or not d.get("pid_turno"):
        return False
    try:
        from nucleo.planificador import _vivo
        return bool(_vivo(int(d["pid_turno"])))
    except Exception:   # noqa: BLE001
        return True


def lanzada_desde(inicio_vigia: float) -> float:
    """Cuando se lanzo la web que corre ahora: el momento en que el vigia anoto su PID (si no hay, desde que el vigia
    arranco: lo anterior no se puede saber)."""
    try:
        return FICHERO_PID.stat().st_mtime
    except OSError:
        return inicio_vigia


def sondear(puerto: int, timeout: float = 3.0) -> str:
    """SANA si /salud responde y es esta web; AJENA si responde otro programa; CAIDA si nada."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/salud", timeout=timeout) as r:
            datos = json.loads(r.read(4096) or b"{}")
    except (urllib.error.HTTPError, ValueError):
        return AJENA  # algo contesta HTTP, pero no es nuestro /salud
    except OSError:
        return CAIDA  # rechazada, timeout, colgada...
    return SANA if isinstance(datos, dict) and datos.get("app") == APP_ID else AJENA


def rotar(ruta: Path, max_bytes: int = ROTAR_BYTES, copias: int = COPIAS_LOG) -> None:
    """interfaz.log -> .1 -> .2 ... si pasa de max_bytes. Solo al (re)lanzar: uvicorn lo tiene abierto.
    Nunca revienta: si el log esta bloqueado (antivirus, un editor...), se sigue escribiendo en el mismo
    y ya rotara en el siguiente lanzamiento. Relanzar la web importa mas que rotar."""
    try:
        if ruta.stat().st_size < max_bytes:
            return
        for i in range(copias - 1, 0, -1):
            viejo = ruta.with_name(f"{ruta.name}.{i}")
            if viejo.exists():
                os.replace(viejo, ruta.with_name(f"{ruta.name}.{i + 1}"))
        os.replace(ruta, ruta.with_name(f"{ruta.name}.1"))
    except OSError:
        return


def orden_web(puerto: int) -> list[str]:
    interprete = PYTHONW if PYTHONW.is_file() else PYTHON
    return [str(interprete), "-m", "uvicorn", "interfaz.app:app", "--host", "127.0.0.1", "--port", str(puerto)]


def linea_web(puerto: int) -> str:
    """La linea de comando que Windows guarda para el proceso que lanza Popen(orden_web(puerto))."""
    return subprocess.list2cmdline(orden_web(puerto))


def linea_de_comando(pid: int) -> str | None:
    """Linea de comando real del proceso `pid` (Win32_Process), o None si no existe o no se puede leer."""
    consulta = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", consulta],
                           capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    linea = r.stdout.decode("utf-8", errors="replace").strip()
    return linea or None


def anotada() -> dict | None:
    """{pid, puerto, linea} de la web que lanzo el vigia, o None (sin fichero, ilegible o formato viejo)."""
    try:
        d = json.loads(FICHERO_PID.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("pid"), int) or not isinstance(d.get("puerto"), int):
        return None  # p. ej. el formato viejo (solo el numero): no se sabe que era, no se toca
    return d


def pid_anotado() -> int:
    d = anotada()
    return d["pid"] if d else 0


def _terminar(pid: int) -> None:
    # T196: /T porque el pythonw del venv es un lanzador y el uvicorn real es su HIJO; sin /T el hijo
    # quedaba vivo con el puerto ocupado. /T solo alcanza al arbol que cuelga de ESTE pid ya verificado.
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15)


def matar_anotada() -> bool:
    """Termina la web que lanzo el vigia. SOLO por su PID exacto y SOLO si la linea de comando de
    ese PID es exactamente la de la web (lo anotado al lanzar = lo que corresponde a su puerto)."""
    d = anotada()
    if d is None or d.get("linea") != linea_web(d["puerto"]):
        return False
    if linea_de_comando(d["pid"]) != d["linea"]:
        return False  # ya no existe, o el PID lo tiene ahora otro proceso: no es nuestro
    try:
        _terminar(d["pid"])
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def lanzar(puerto: int) -> int:
    """Lanza uvicorn fuera del arbol del vigia (sobrevive si el vigia muere). Devuelve el PID."""
    LOG_WEB.parent.mkdir(parents=True, exist_ok=True)
    rotar(LOG_WEB)
    orden = orden_web(puerto)
    entorno = dict(os.environ, NEXO_INTERFAZ_PUERTO=str(puerto))
    base = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    with LOG_WEB.open("ab") as log:
        log.write(f"\n==== {datetime.now().isoformat(timespec='seconds')} vigia lanza la web en {puerto}\n".encode())
        log.flush()
        try:
            p = subprocess.Popen(orden, cwd=RAIZ, env=entorno, stdin=subprocess.DEVNULL, stdout=log,
                                 stderr=subprocess.STDOUT, creationflags=base | subprocess.CREATE_BREAKAWAY_FROM_JOB)
        except OSError:
            # CREATE_BREAKAWAY_FROM_JOB falla si el Job no lo permite; sin el funciona igual.
            p = subprocess.Popen(orden, cwd=RAIZ, env=entorno, stdin=subprocess.DEVNULL, stdout=log,
                                 stderr=subprocess.STDOUT, creationflags=base)
    FICHERO_PID.write_text(json.dumps({"pid": p.pid, "puerto": puerto, "linea": subprocess.list2cmdline(orden)}),
                           encoding="utf-8")
    return p.pid


class Vigia:
    """Una pasada = paso(). Las dependencias se inyectan para probarlo sin procesos reales."""

    def __init__(self, puerto: int = PUERTO, sondear=sondear, lanzar=lanzar, matar=matar_anotada,
                 detenida=DETENIDA.exists, dormir=time.sleep, log=None, serve=mirar_serve,
                 cambio=None, desde=None, reloj=time.time, ocupado=None):
        self.puerto = puerto
        self._ocupado = ocupado      # () -> bool: algo que no se debe matar con la web (un turno en marcha)
        self._pospuesto = ""
        self._cambio, self._reloj = cambio, reloj      # cambio=None: sin reinicio por codigo (main() lo activa)
        inicio = reloj()
        self._desde = desde or (lambda: lanzada_desde(inicio))   # cuando se lanzo la web que corre
        self._ultimo_reinicio = 0.0
        self._sin_poder = ""     # codigo nuevo que no se pudo aplicar (no se repite el aviso)
        self._sondear, self._lanzar, self._matar = sondear, lanzar, matar
        self._detenida, self._dormir = detenida, dormir
        self._log = log or (lambda nivel, msg: None)
        # Al arrancar (inicio de sesion) basta un fallo para lanzarla: no tiene sentido esperar 30 s.
        self.fallos = FALLOS_PARA_RELANZAR - 1
        self.espera = INTERVALO
        self._ultimo = ""
        self._serve = serve
        self._pasadas_serve = PASADAS_SERVE - 1   # la primera pasada sana ya lo mira
        self._serve_ultimo = None

    def paso(self) -> str:
        if self._detenida():
            self.fallos = 0
            return self._anotar("detenida", "info", "web detenida a proposito (INTERFAZ_DETENIDA): no se relanza")
        estado = self._sondear(self.puerto)
        if estado == SANA:
            self.fallos, self.espera = 0, INTERVALO
            self._vigilar_serve()
            reiniciada = self._reiniciar_si_codigo_nuevo()
            if reiniciada:
                return reiniciada
            return self._anotar("sana", "info", f"web sana en {self.puerto}")
        if estado == AJENA:
            self.fallos = 0
            return self._anotar("ajena", "warning",
                                f"el puerto {self.puerto} lo ocupa otro programa (¿la v1?): no se lanza")
        self.fallos += 1
        if self.fallos < FALLOS_PARA_RELANZAR:
            return self._anotar("fallo", "warning", f"/salud no responde ({self.fallos}/{FALLOS_PARA_RELANZAR})")
        # Caida o colgada: fuera la anterior (si la lanzo el vigia) y otra nueva.
        self._matar()
        pid = self._lanzar(self.puerto)
        for _ in range(ESPERA_ARRANQUE):
            self._dormir(1)
            if self._sondear(self.puerto) == SANA:
                self.fallos, self.espera = 0, INTERVALO
                return self._anotar("relanzada", "warning", f"web relanzada (pid {pid})", siempre=True)
        self.espera = min(self.espera * 2, ESPERA_MAX)
        return self._anotar("sin_respuesta", "error",
                            f"la web (pid {pid}) no responde tras {ESPERA_ARRANQUE} s; reintento en "
                            f"{self.espera} s (ver registros/interfaz.log)", siempre=True)

    def _reiniciar_si_codigo_nuevo(self) -> str | None:
        """T868: la web sana lleva codigo viejo si cambio interfaz/ despues de lanzarla. Devuelve el estado o None."""
        if self._cambio is None:
            return None
        ahora = self._reloj()
        ruta = self._cambio(max(self._desde(), self._ultimo_reinicio), ahora)
        if not ruta or ahora - self._ultimo_reinicio < REINICIO_MIN:
            return None
        if self._ocupado is not None and self._ocupado():
            if self._pospuesto != ruta:
                self._pospuesto = ruta
                self._log("info", f"interfaz/{ruta} cambio: reinicio pospuesto hasta que acabe el turno en marcha")
            return None
        self._pospuesto = ""
        if not self._matar():     # no la lanzo el vigia (o el PID ya no es el suyo): no se toca ni se lanza otra
            if self._sin_poder != ruta:
                self._sin_poder = ruta
                self._log("warning", f"interfaz/{ruta} cambio y la web corre con codigo viejo, pero no la lanzo el "
                                     "vigia (no se reinicia sola): reiniciala a mano")
            return None
        self._ultimo_reinicio = self._reloj()
        self._sin_poder = ""
        pid = self._lanzar(self.puerto)
        for _ in range(ESPERA_ARRANQUE):
            self._dormir(1)
            if self._sondear(self.puerto) == SANA:
                return self._anotar("reiniciada_por_codigo", "warning",
                                    f"web reiniciada por cambios en interfaz/{ruta} (pid {pid})", siempre=True)
        self.espera = min(self.espera * 2, ESPERA_MAX)
        return self._anotar("sin_respuesta", "error",
                            f"la web (pid {pid}) no responde tras reiniciarla por interfaz/{ruta}; reintento en "
                            f"{self.espera} s (ver registros/interfaz.log)", siempre=True)

    def _vigilar_serve(self) -> None:
        self._pasadas_serve += 1
        if self._pasadas_serve < PASADAS_SERVE:
            return
        self._pasadas_serve = 0
        try:
            aviso = self._serve(self.puerto)
        except Exception as e:  # Tailscale raro nunca tumba al vigia
            aviso = ("warning", f"no se pudo mirar tailscale serve: {type(e).__name__}")
        if aviso is not None and aviso != self._serve_ultimo:
            self._log(*aviso)
        self._serve_ultimo = aviso

    def _anotar(self, estado: str, nivel: str, msg: str, siempre: bool = False) -> str:
        if siempre or estado != self._ultimo:  # el log recoge cambios, no una linea cada 30 s
            self._log(nivel, msg)
        self._ultimo = estado
        return estado

    def correr(self) -> None:
        while True:
            try:
                self.paso()
            except Exception as e:  # una pasada mala nunca tira al vigia
                self._log("error", f"pasada fallida: {type(e).__name__}")
            self._dormir(self.espera)


# ------------------------------------------------------------------ CLI
def parar() -> str:
    DETENIDA.parent.mkdir(parents=True, exist_ok=True)
    DETENIDA.write_text(json.dumps({"quien": "damian", "cuando": datetime.now().isoformat(timespec="seconds")}),
                        encoding="utf-8")
    if matar_anotada():
        return "Web detenida y marcada: el vigia no la relanza hasta seguir_interfaz.bat."
    return ("Marcada como detenida (el vigia no la relanza). No habia viva ninguna web lanzada por el vigia; "
            "si la arrancaste a mano, cierrala tu.")


def seguir(puerto: int = PUERTO) -> str:
    try:
        DETENIDA.unlink()
    except FileNotFoundError:
        pass
    estado = sondear(puerto)
    if estado == SANA:
        return "La web ya estaba en marcha."
    if estado == AJENA:
        return f"Quitada la marca, pero el puerto {puerto} lo ocupa otro programa: no se lanza."
    pid = lanzar(puerto)
    return f"Web lanzada (pid {pid}); el vigia la mantiene viva."


def estado(puerto: int = PUERTO) -> str:
    return (f"web en {puerto}: {sondear(puerto)} | detenida a proposito: {'si' if DETENIDA.exists() else 'no'} "
            f"| pid anotado: {pid_anotado() or '-'}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Vigia de la interfaz web de NEXO")
    grupo = ap.add_mutually_exclusive_group()
    grupo.add_argument("--parar", action="store_true", help="parar la web y que el vigia no la relance")
    grupo.add_argument("--seguir", action="store_true", help="quitar la marca de parada y lanzarla")
    grupo.add_argument("--estado", action="store_true")
    a = ap.parse_args(argv)
    if a.parar or a.seguir or a.estado:
        print(parar() if a.parar else seguir() if a.seguir else estado())
        return 0

    from nucleo.instancia import unico
    from nucleo.registro import logger
    log = logger("interfaz.vigia")
    if not unico("nexo_interfaz_vigia"):
        log.info("ya hay otro vigia de la interfaz, me retiro")
        return 0
    log.info("vigia de la interfaz en marcha (puerto %s, cada %s s)", PUERTO, INTERVALO)
    Vigia(log=lambda nivel, msg: getattr(log, nivel)(msg), cambio=cambio_de_codigo,
          ocupado=turno_en_marcha).correr()
    return 0


if __name__ == "__main__":
    sys.exit(main())
