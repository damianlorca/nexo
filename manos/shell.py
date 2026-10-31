"""Manos: shell. Comandos que terminan y procesos que no.

Todo pasa por nucleo.permisos antes de ejecutarse.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from nucleo.config import RAIZ
from nucleo.permisos import Nivel, exigir, nivel_de_comando, nivel_de_ruta
from nucleo.registro import logger, registrar_evidencia, traza


log = logger("manos.shell")

LOGS = RAIZ / "registros"

# El limite del puente con Claude son 60 s. Nada por encima de 50.
TIMEOUT_MAX = 50


@dataclass
class Resultado:
    codigo: int
    salida: str
    error: str
    duracion: float
    comando: str

    @property
    def ok(self) -> bool:
        return self.codigo == 0

    def __str__(self) -> str:
        return (
            f"CODIGO: {self.codigo}  ({self.duracion:.1f}s)\n"
            f"SALIDA:\n{self.salida}\n"
            f"ERROR:\n{self.error}"
        )


_FIJAR_ENCODING = (
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    "$OutputEncoding = [System.Text.Encoding]::UTF8; "
    "$PSDefaultParameterValues['*:Encoding'] = 'UTF8'; "
)


def _powershell(comando: str) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy", "Bypass",
        "-Command", _FIJAR_ENCODING + comando,
    ]


# Claude Desktop arranca el servidor MCP con un entorno mutilado:
# PATHEXT llega valiendo ".CPL", asi que Windows no considera
# ejecutable ningun .exe y PowerShell trata python.exe como si fuera
# un documento. Sintoma: los comandos "funcionan" pero no devuelven
# nada. Se repara aqui, una vez, para todos los comandos.

PATHEXT_SANO = ".COM;.EXE;.BAT;.CMD;.VBS;.JS;.WS;.MSC"


def _carpetas_path() -> list[str]:
    windows = os.environ.get("SystemRoot", r"C:\Windows")
    local = os.environ.get(
        "LOCALAPPDATA",
        str(Path.home() / "AppData" / "Local"),
    )

    carpetas = [
        rf"{windows}\system32",
        windows,
        rf"{windows}\System32\Wbem",
        rf"{windows}\System32\WindowsPowerShell\v1.0",
        str(RAIZ / ".venv" / "Scripts"),
        rf"{local}\Programs\Python\Python311",
        rf"{local}\Programs\Python\Python311\Scripts",
        rf"{local}\Programs\Ollama",
        rf"{local}\Programs\Microsoft VS Code\bin",
        r"C:\Program Files\Git\cmd",
    ]

    heredado = os.environ.get("PATH", "")

    if heredado:
        carpetas += [c for c in heredado.split(";") if c]

    vistas, limpias = set(), []

    for c in carpetas:
        if c and c.lower() not in vistas:
            vistas.add(c.lower())
            limpias.append(c)

    return limpias


def _entorno() -> dict:
    entorno = os.environ.copy()

    entorno["PATHEXT"] = PATHEXT_SANO
    entorno["PATH"] = ";".join(_carpetas_path())
    entorno.setdefault("PYTHONIOENCODING", "utf-8")
    # L5: sin esto, un Python lanzado con lanzar() bufferiza su
    # salida en trozos de 8 KB y el log parece muerto varios minutos.
    entorno.setdefault("PYTHONUNBUFFERED", "1")

    return entorno


def python_del_proyecto() -> str:
    """El interprete del venv si existe; si no, el que haya."""

    venv = RAIZ / ".venv" / "Scripts" / "python.exe"

    return str(venv) if venv.is_file() else sys.executable


def _cwd(cwd: str | Path | None) -> Path:
    destino = Path(cwd).resolve() if cwd else RAIZ

    exigir(nivel_de_ruta(destino, escritura=False), "cwd", str(destino))

    return destino


def ejecutar(
    comando: str,
    cwd: str | Path | None = None,
    timeout: int = 45,
    aprobado: bool = False,
) -> Resultado:
    """Ejecuta un comando que termina solo.

    aprobado=True solo debe pasarlo quien ya tiene el si de Damian.
    """

    nivel = nivel_de_comando(comando)

    # N04: aprobado=True salta el ambar, NUNCA el rojo.
    if not aprobado or nivel is Nivel.ROJO:
        exigir(nivel, "ejecutar comando", comando[:120])

    directorio = _cwd(cwd)
    timeout = max(1, min(int(timeout), TIMEOUT_MAX))
    inicio = time.time()

    try:
        proceso = subprocess.run(
            _powershell(comando),
            cwd=str(directorio),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            env=_entorno(),
        )

        resultado = Resultado(
            codigo=proceso.returncode,
            salida=proceso.stdout,
            error=proceso.stderr,
            duracion=time.time() - inicio,
            comando=comando,
        )

    except subprocess.TimeoutExpired as e:
        resultado = Resultado(
            codigo=-1,
            salida=e.stdout or "",
            error=(
                f"TIMEOUT tras {timeout}s. Si no termina solo, "
                "usa lanzar()."
            ),
            duracion=time.time() - inicio,
            comando=comando,
        )

    traza(
        "comando",
        comando=comando[:200],
        codigo=resultado.codigo,
        duracion=round(resultado.duracion, 2),
    )

    registrar_evidencia(
        "tool",
        tool="shell.ejecutar",
        accion=comando[:200],
        estado="OK" if resultado.ok else "ERROR",
        duracion=round(resultado.duracion, 2),
        resultado=f"codigo={resultado.codigo}",
    )

    return resultado


# Banderas de creacion de procesos. El orden de este comentario
# importa mas que el codigo, porque cada una se puso despues de que
# algo se rompiera:
#
# DETACHED_PROCESS (descartada, 10/09): mata el proceso nada mas
#   nacer. Se queda sin consola, no hereda bien los descriptores y
#   el log sale de 0 bytes.
# CREATE_NO_WINDOW: lo que queriamos de la anterior. Sin ventana,
#   pero el proceso vive y escribe.
# CREATE_NEW_PROCESS_GROUP: que un Ctrl+C nuestro no se lo lleve por
#   delante.
# CREATE_BREAKAWAY_FROM_JOB (11/09): la importante. Claude Desktop
#   mete al servidor MCP en un Job de Windows, y al cerrarse el Job
#   se lleva a TODA su descendencia. Sin esta bandera, cada reinicio
#   del servidor mataba al bot y a Damian lo dejaba incomunicado sin
#   que nadie se enterara. Paso el 11/09 a las 03:15 con tres
#   mensajes sin entregar.

_BASE = 0

if os.name == "nt":
    _BASE = (
        subprocess.CREATE_NO_WINDOW
        | subprocess.CREATE_NEW_PROCESS_GROUP
    )

    _CON_FUGA = _BASE | 0x01000000   # CREATE_BREAKAWAY_FROM_JOB
else:
    _CON_FUGA = 0


def lanzar(
    comando: str,
    nombre: str = "proceso",
    cwd: str | Path | None = None,
    aprobado: bool = False,
    independiente: bool = True,
) -> dict:
    """Arranca algo que no termina solo y devuelve el control.

    Chrome con puerto de depuracion, ComfyUI, el bot de Telegram.
    La salida va a registros/<nombre>_<fecha>.log

    independiente=True (por defecto) hace que el proceso sobreviva a
    que Claude Desktop reinicie el servidor MCP. Es lo que quieres
    casi siempre. Ponlo a False solo para algo que deba morir con
    nosotros.

    L4: nada de | Out-String aqui. Out-String espera a que el
    proceso termine para formatear, y estos no terminan: el log
    se quedaria vacio para siempre.
    """

    nivel = nivel_de_comando(comando)

    # N04: aprobado=True salta el ambar, NUNCA el rojo.
    if not aprobado or nivel is Nivel.ROJO:
        exigir(nivel, "lanzar proceso", comando[:120])

    directorio = _cwd(cwd)

    LOGS.mkdir(parents=True, exist_ok=True)

    destino = LOGS / f"{nombre}_{time.strftime('%Y%m%d_%H%M%S')}.log"

    salida = open(destino, "w", encoding="utf-8", errors="replace")

    def _abrir(banderas: int) -> subprocess.Popen:
        return subprocess.Popen(
            _powershell(comando),
            cwd=str(directorio),
            stdout=salida,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=banderas,
            env=_entorno(),
        )

    fugado = False

    if independiente and os.name == "nt":
        try:
            proceso = _abrir(_CON_FUGA)
            fugado = True

        except OSError as e:
            # Hay Jobs que prohiben la fuga (JOB_OBJECT_LIMIT_
            # BREAKAWAY_OK sin activar). Entonces se arranca atado:
            # mejor un proceso fragil que ninguno.
            log.warning(
                "no he podido independizar %s (%s). Arranca atado al "
                "servidor: morira cuando Claude Desktop se reinicie.",
                nombre, e,
            )

            proceso = _abrir(_BASE)
    else:
        proceso = _abrir(_BASE)

    log.info(
        "lanzado %s pid=%s%s",
        nombre, proceso.pid,
        "" if fugado else " (atado al servidor)",
    )

    traza(
        "lanzar",
        nombre=nombre,
        pid=proceso.pid,
        independiente=fugado,
        comando=comando[:200],
    )

    registrar_evidencia(
        "tool",
        tool="shell.lanzar",
        accion=comando[:200],
        estado="LANZADO" if fugado else "LANZADO_ATADO",
        resultado=f"pid={proceso.pid} nombre={nombre}",
    )

    return {
        "pid": proceso.pid,
        "log": str(destino),
        "independiente": fugado,
        "comando": comando,
    }


def vivo(pid: int) -> bool:
    r = ejecutar(
        f"Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue "
        "| Select-Object -ExpandProperty ProcessName",
        timeout=20,
    )

    return bool(r.salida.strip())
