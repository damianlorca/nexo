"""Servidor MCP del agente. Esto es lo que Claude ve como "manos".

Arranque desde Claude Desktop:
    uv run --with "mcp[cli]<2" mcp run <ruta a este archivo>

(<2 porque mcp 2.x quita FastMCP; requisitos.txt ya lo fija igual.)

Notas aprendidas a base de golpes:
- sys.executable, nunca "python": en Windows la cadena "python"
  puede caer en el alias de Microsoft Store, que abre la tienda y
  deja el proceso colgado para siempre.
- Todos los timeouts por debajo de 50 s: el puente con Claude corta
  a los 60 y sin respuesta no hay diagnostico posible.
- Si cambias este archivo, hay que MATAR el proceso viejo. Cerrar la
  ventana de Claude no lo mata; queda un zombi sirviendo el codigo
  anterior. Ver docs/ARRANQUE.md.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import hashlib     # noqa: E402
import os          # noqa: E402
import subprocess  # noqa: E402
import time        # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

from manos import archivos, shell                        # noqa: E402
from nucleo import aprobaciones, revisor                 # noqa: E402
from nucleo.permisos import (  # noqa: E402
    Bloqueado,
    NecesitaAprobacion,
    Nivel,
    exigir,
    nivel_de_comando,
    nivel_de_ruta,
)
from nucleo.registro import registrar_evidencia  # noqa: E402


mcp = FastMCP("Nexo")


def _extra(motivo: str) -> dict | None:
    """T1020: el para-que de quien pide. Va en extra (fuera de la huella): el guardian lo pone en la ficha de Damian
    ("Quien lo pide y para que") y el tribunal lo lee. Sin motivo, la ficha dice "No lo ha dicho"."""
    motivo = " ".join(str(motivo or "").split())[:500]
    return {"motivo": motivo} if motivo else None


def _envuelto(fn, *args, _motivo: str = "", **kwargs) -> str:
    """Traduce las excepciones de permisos a texto que Claude entiende.

    Una excepcion cruda solo dice "ha fallado". Esto dice por que y
    que hace falta para desbloquearlo.
    """

    try:
        return str(fn(*args, **kwargs))

    except Bloqueado as e:
        return f"BLOQUEADO (rojo): {e}"

    except NecesitaAprobacion as e:
        # T077: que no se pierda. Estas herramientas (escribir, archivar,
        # cwd fuera de zona) aun no aceptan aprobacion_id: queda en cola
        # para que Damian lo vea y lo haga el o apruebe el cambio.
        s = aprobaciones.solicitar(e.accion, e.detalle, origen="mcp", extra=_extra(_motivo))

        return (
            f"NECESITA APROBACION (ambar): {e.accion}\n"
            f"DETALLE: {e.detalle}\n"
            f"SOLICITUD: {s['id']} ({s['estado']}; queda en la cola de aprobaciones)."
        )

    except (aprobaciones.NoEncontrada, aprobaciones.EstadoInvalido, aprobaciones.NoCoincide) as e:
        return f"APROBACION NO VALIDA: {e}. No se ha ejecutado nada."

    except Exception as e:
        return f"ERROR {type(e).__name__}: {e}"


# ---------------------------------------------------------------
# Puerta de aprobaciones (T077, propuesta N04)
# ---------------------------------------------------------------
#
# Antes, aprobado=True era un booleano que ponia quien llamaba, y ademas
# se saltaba exigir() ENTERO, rojo incluido (manos/shell.py). Ahora:
# - rojo: nunca pasa, haya lo que haya;
# - ambar: solo con un aprobacion_id que Damian haya aprobado FUERA de
#   este canal (CLI o Telegram) y que coincida con la accion exacta; se
#   gasta al usarlo. Lo que encaja en la lista blanca de nucleo/revisor.py
#   lo aprueba el revisor de reglas y pasa sin esperar;
# - verde: como siempre.
# Aprobar no es una herramienta MCP a proposito: el agente no se aprueba.

def _puerta(accion: str, detalle: str, nivel: Nivel, aprobacion_id: str, aprobado: bool, motivo: str = ""):
    """Devuelve (aprobado_para_manos, respuesta). Si respuesta no es None, devolverla y no ejecutar."""

    if nivel is not Nivel.AMBAR:
        return False, None  # verde pasa; rojo lo corta exigir() dentro de manos

    if aprobacion_id:
        aprobaciones.consumir(aprobacion_id, accion, detalle)  # revienta si no vale
        return True, None

    s = aprobaciones.solicitar(accion, detalle, origen="mcp", extra=_extra(motivo))

    # T1020: el guardian (gancho de aprobaciones.solicitar) aprueba solo lo que SOLO LEE, sin secretos ni lo
    # privado. Si ya viene aprobada (por el, o por Damian antes para esta accion exacta), se gasta aqui mismo.
    if s["estado"] == "aprobada":
        aprobaciones.consumir(s["id"], accion, detalle)
        return True, None

    # T154 F1: el revisor de reglas despacha lo obvio (lista blanca minima)
    # sin molestar a Damian. Queda en el historial como revisor:reglas.
    if revisor.procesar(s).decision == "permitir":
        aprobaciones.consumir(s["id"], accion, detalle)
        return True, None

    return False, (
        f"NECESITA APROBACION (ambar): {accion}\n"
        f"DETALLE: {detalle[:300]}\n"
        f"SOLICITUD: {s['id']} ({s['estado']}, vence {s['vence']})\n"
        + ("aprobado=True ya no basta. " if aprobado else "")
        + "Damian decide fuera de este canal "
        f"(python -m nucleo.aprobaciones aprobar {s['id']}). "
        f'Cuando este aprobada, repite la llamada con aprobacion_id="{s["id"]}".'
    )


# ---------------------------------------------------------------
# Diagnostico
# ---------------------------------------------------------------

@mcp.tool()
def info_entorno() -> str:
    """Raiz, Python en uso, PID del servidor y hora. Empieza siempre por aqui."""

    return (
        f"RAIZ: {RAIZ}\n"
        f"SERVIDOR: {Path(__file__).resolve()}\n"
        f"EXECUTABLE: {sys.executable}\n"
        f"PYTHON PROYECTO: {shell.python_del_proyecto()}\n"
        f"VERSION: {sys.version.split()[0]}\n"
        f"PID: {os.getpid()}\n"
        f"HORA: {time.strftime('%Y-%m-%d %H:%M:%S')}"
    )


# ---------------------------------------------------------------
# Archivos
# ---------------------------------------------------------------

@mcp.tool()
def listar(subcarpeta: str = "", patron: str = "*", aprobacion_id: str = "", motivo: str = "") -> str:
    """Lista archivos del proyecto. patron admite comodines: *.py

    Fuera de las carpetas de NEXO pide permiso: si devuelve NECESITA
    APROBACION con una SOLICITUD, cuando este aprobada repite la llamada
    con aprobacion_id=<id> (T1025: va atada a ESA carpeta). Lo que el
    guardian aprueba al entrar se lista a la primera.

    motivo: para que lo necesitas, en una frase (sale en la ficha de Damian si hace falta permiso).
    """

    def _listar() -> str:
        base = archivos._resolver(subcarpeta) if subcarpeta else archivos.RAIZ
        nivel = nivel_de_ruta(base, escritura=False)
        aprobado, respuesta = _puerta("listar", str(base), nivel, aprobacion_id, False, motivo)
        if respuesta:
            return respuesta
        return "\n".join(archivos.listar(subcarpeta, patron, aprobado=aprobado))

    return _envuelto(_listar)


@mcp.tool()
def leer(ruta: str, aprobacion_id: str = "", motivo: str = "") -> str:
    """Lee un archivo de texto.

    Fuera de las carpetas de NEXO pide permiso: si devuelve NECESITA
    APROBACION con una SOLICITUD, cuando este aprobada repite la llamada
    con aprobacion_id=<id> (T1025: va atada a ESTA ruta). Lo que el
    guardian aprueba al entrar se lee a la primera.

    motivo: para que lo necesitas, en una frase (sale en la ficha de Damian si hace falta permiso).
    """

    def _leer() -> str:
        p = archivos._resolver(ruta)
        nivel = nivel_de_ruta(p, escritura=False)
        aprobado, respuesta = _puerta("leer", str(p), nivel, aprobacion_id, False, motivo)
        if respuesta:
            return respuesta
        return archivos.leer(ruta, aprobado=aprobado)

    return _envuelto(_leer)


@mcp.tool()
def escribir(ruta: str, contenido: str, aprobacion_id: str = "", motivo: str = "") -> str:
    """Escribe un archivo. Si ya existia, guarda respaldo antes.

    Si devuelve NECESITA APROBACION con una SOLICITUD, espera a que
    Damian la apruebe y repite la llamada con aprobacion_id=<id> y el
    MISMO contenido (T861: la aprobacion va atada a la ruta y al sha256
    del contenido; otro contenido pide otra aprobacion).

    motivo: para que lo escribes, en una frase (sale en la ficha de Damian y lo lee el tribunal).
    """

    def _escribir() -> str:
        p = archivos._resolver(ruta)
        nivel = nivel_de_ruta(p, escritura=True)
        detalle = f"{p} sha256:{hashlib.sha256(contenido.encode('utf-8')).hexdigest()[:16]}"
        aprobado, respuesta = _puerta("escribir", detalle, nivel, aprobacion_id, False, motivo)
        if respuesta:
            return respuesta
        return archivos.escribir(ruta, contenido, aprobado=aprobado)

    return _envuelto(_escribir)


@mcp.tool()
def archivar(ruta: str, motivo: str = "") -> str:
    """Mueve algo a _archivo/. El agente no borra: archiva."""

    return _envuelto(archivos.archivar, ruta, motivo, _motivo=motivo)


# ---------------------------------------------------------------
# Shell
# ---------------------------------------------------------------

@mcp.tool()
def comando(
    comando: str, cwd: str = "", timeout: int = 45, aprobado: bool = False, aprobacion_id: str = "",
    motivo: str = "",
) -> str:
    """Ejecuta un comando de PowerShell que termina solo.

    Si devuelve NECESITA APROBACION con una SOLICITUD, espera a que
    Damian la apruebe y repite la llamada con aprobacion_id=<id>.
    Lo que solo lee lo aprueba el guardian al momento y se ejecuta sin esperar.

    motivo: para que lo necesitas, en una frase (sale en la ficha de Damian y lo lee el tribunal).
    """

    def _correr():
        ok, respuesta = _puerta(
            "ejecutar comando", comando, nivel_de_comando(comando), aprobacion_id, aprobado, motivo
        )

        return respuesta or shell.ejecutar(comando, cwd or None, timeout, ok)

    return _envuelto(_correr, _motivo=motivo)


@mcp.tool()
def lanzar(
    comando: str, nombre: str = "proceso", cwd: str = "", aprobado: bool = False, aprobacion_id: str = "",
    motivo: str = "",
) -> str:
    """Arranca un proceso que no termina solo y devuelve el control.

    Chrome con depuracion, ComfyUI, el bot de Telegram.

    motivo: para que lo arrancas, en una frase (sale en la ficha de Damian y lo lee el tribunal).
    """

    def _correr():
        ok, respuesta = _puerta(
            "lanzar proceso", comando, nivel_de_comando(comando), aprobacion_id, aprobado, motivo
        )

        if respuesta:
            return respuesta

        if ok:
            return shell.lanzar(comando, nombre, cwd or None, True)

        # 18/10 (A0062/A0069/A0071): el envoltorio de la guardia nombra nucleo/guardia_python.py, que es blindado, y
        # shell.lanzar lo veia AMBAR aunque lo pedido fuera VERDE: pedia una aprobacion que luego nunca se consumia.
        # El nivel ya se ha juzgado arriba sobre lo pedido; el envoltorio lo pone NEXO. aprobado=True salta el ambar
        # del envoltorio, NUNCA el rojo (shell.lanzar lo corta igual).
        envuelto = _con_guardia(comando)
        return shell.lanzar(envuelto, nombre, cwd or None, envuelto != comando)

    return _envuelto(_correr, _motivo=motivo)


# T091 (2a pieza, aprobada por Damian 23/09): `python script.py ...` lanzado con lanzar()
# tambien pasa por nucleo/guardia_python.py. No cubre `python -m` ni comandos compuestos.
_PY_SCRIPT = re.compile(
    r'^(?P<py>"?[^"\s]*pythonw?(?:\.exe)?"?)\s+(?P<script>(?!-)[^\s"]+\.py)(?P<resto>(\s.*)?)$', re.I
)


def _con_guardia(comando: str) -> str:
    m = _PY_SCRIPT.match(comando.strip())
    if not m or m.group("script").replace("/", "\\").lower().endswith("nucleo\\guardia_python.py"):
        return comando
    return f'{m.group("py")} {RAIZ / "nucleo" / "guardia_python.py"} {m.group("script")}{m.group("resto") or ""}'


@mcp.tool()
def proceso_vivo(pid: int) -> str:
    """Comprueba si un proceso lanzado sigue en marcha."""

    return _envuelto(lambda: f"PID {pid} vivo: {shell.vivo(pid)}")


@mcp.tool()
def ejecutar_python(ruta: str, timeout: int = 45, aprobado: bool = False, aprobacion_id: str = "",
                    motivo: str = "") -> str:
    """Ejecuta un script Python del proyecto con el mismo interprete.

    Si devuelve NECESITA APROBACION con una SOLICITUD, espera a que
    Damian la apruebe y repite la llamada con aprobacion_id=<id>.

    motivo: para que lo ejecutas, en una frase (sale en la ficha de Damian y lo lee el tribunal).
    """

    pedido = aprobado

    def _correr() -> str:
        nonlocal aprobado

        archivo = Path(ruta)

        if not archivo.is_absolute():
            archivo = RAIZ / archivo

        archivo = archivo.resolve()
        nivel = nivel_de_ruta(archivo, escritura=True)

        aprobado, respuesta = _puerta("ejecutar_python", str(archivo), nivel, aprobacion_id, pedido, motivo)

        if respuesta:
            return respuesta

        if not aprobado:
            exigir(nivel, "ejecutar_python", str(archivo))

        if not archivo.is_file():
            raise FileNotFoundError(str(archivo))

        limite = max(1, min(int(timeout), 50))
        inicio = time.time()

        try:
            r = subprocess.run(
                [shell.python_del_proyecto(), str(RAIZ / "nucleo" / "guardia_python.py"), str(archivo)]
                if not aprobado else [shell.python_del_proyecto(), str(archivo)],
                cwd=str(RAIZ),
                capture_output=True,
                text=True,
                timeout=limite,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                env=shell._entorno(),
            )

            registrar_evidencia(
                "tool",
                tool="servidor_mcp.ejecutar_python",
                accion=str(archivo),
                estado="OK" if r.returncode == 0 else "ERROR",
                duracion=round(time.time() - inicio, 2),
                resultado=f"codigo={r.returncode}",
            )

            return (
                f"CODIGO: {r.returncode}\n"
                f"SALIDA:\n{r.stdout}\n"
                f"ERROR:\n{r.stderr}"
            )

        except subprocess.TimeoutExpired as e:
            registrar_evidencia(
                "tool",
                tool="servidor_mcp.ejecutar_python",
                accion=str(archivo),
                estado="TIMEOUT",
                duracion=round(time.time() - inicio, 2),
                resultado=f"timeout tras {limite}s",
            )

            return (
                f"CODIGO: -1\nSALIDA:\n{e.stdout or ''}\n"
                f"ERROR:\nTIMEOUT tras {limite}s. Usa lanzar()."
            )

    return _envuelto(_correr)


if __name__ == "__main__":
    mcp.run()
