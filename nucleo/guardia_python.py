# -*- coding: utf-8 -*-
"""Guardia de ejecucion para ejecutar_python() (T091, hueco L1).

Problema: ejecutar_python() comprueba la RUTA del script, pero no lo que el
codigo hace por dentro: un script dentro del proyecto (verde) podia escribir,
borrar o lanzar comandos en cualquier sitio sin pasar por nucleo/permisos.py.

Solucion: en vez de `python script.py`, ejecutar
`python nucleo/guardia_python.py script.py`. Este lanzador instala un
*audit hook* de Python (PEP 578: no se puede quitar una vez puesto) y luego
ejecuta el script tal cual (runpy, como __main__). El hook aplica las MISMAS
reglas que nucleo/permisos.py:

  - escribir / crear / borrar / renombrar / cambiar permisos de un archivo:
    solo en la zona verde (config permisos.zona_verde) o en la carpeta TEMP.
    Blindados -> no. secretos.toml -> nunca.
  - leer secretos.toml: solo desde nucleo/config.py (asi un script puede usar
    config.valor(), pero no abrir el archivo y volcarlo).
  - lanzar procesos (subprocess, os.system, os.startfile, exec/spawn): el texto
    del comando pasa por permisos.nivel_de_comando(); solo VERDE sigue.
  - escribir en el registro de Windows: nunca.

Cuando algo se corta, la operacion NO ocurre (el hook salta antes) y el script
recibe GuardiaBloqueo (RuntimeError) con el motivo. Con aprobado=True (Damian dijo que si a
esa cosa concreta) ejecutar_python() no usa este lanzador.

Limites honestos (no es una caja de arena):
  - Leer archivos fuera de la zona verde se permite y NO se bloquea todavia
    (REQ-070 lo pone en ambar para las herramientas, pero bloquearlo aqui
    rompe la libreria estandar de Python, que vive fuera). Queda pendiente.
  - Codigo nativo via ctypes/extensiones C puede saltarse el hook.
  - Un script puede leer un secreto via config.valor() y mostrarlo. Esto frena
    accidentes y errores de una IA, no a un atacante decidido.
"""
from __future__ import annotations

import os
import runpy
import sys
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MAX_AVISOS = 200   # T708: tope de lineas de bloqueo por proceso

_local = threading.local()


class GuardiaBloqueo(RuntimeError):
    """Operacion cortada por la guardia.

    NO hereda de PermissionError/OSError a proposito: tempfile.mkstemp() en Windows
    reintenta hasta 10.000 veces ante PermissionError (prueba real 23/09: un
    escribir_atomico() fuera de zona se quedo en bucle y lleno 5,7 MB de log).
    """


def _norma(p) -> str | None:
    if isinstance(p, int):
        return None  # descriptor ya abierto
    if isinstance(p, bytes):
        p = os.fsdecode(p)
    try:
        return os.path.normcase(os.path.abspath(os.fspath(p)))
    except Exception:
        return None


def instalar() -> None:
    if str(RAIZ) not in sys.path:
        sys.path.append(str(RAIZ))
    from nucleo import permisos  # antes del hook: lee config.toml

    zonas = [_norma(z) for z in permisos.zonas_verdes()]
    temp = os.environ.get("TEMP") or os.environ.get("TMP")
    if temp:
        zonas.append(_norma(temp))
    blindados = {_norma(RAIZ / b) for b in permisos.ARCHIVOS_BLINDADOS}
    rojos = {n.lower() for n in permisos.ARCHIVOS_EN_ROJO}
    config_py = _norma(RAIZ / "nucleo" / "config.py")
    # os.devnull: subprocess lo abre en escritura para DEVNULL (prueba real 23/09, platform.system()).
    inocuos = {_norma(os.devnull), _norma("nul")}
    Verde = permisos.Nivel.VERDE
    nivel_de_comando = permisos.nivel_de_comando
    sep = os.sep

    def dentro(p: str) -> bool:
        return any(p == z or p.startswith(z.rstrip(sep) + sep) for z in zonas if z)

    cuenta = [0]

    def cortar(motivo: str) -> None:
        msg = f"GUARDIA NEXO: bloqueado {motivo}. Si Damian lo aprueba, repetir con aprobado=True."
        cuenta[0] += 1
        try:
            if cuenta[0] <= MAX_AVISOS:
                sys.stderr.write(msg + "\n")
            elif cuenta[0] == MAX_AVISOS + 1:
                sys.stderr.write(f"GUARDIA NEXO: mas de {MAX_AVISOS} bloqueos; el resto se corta sin escribir mas.\n")
        except Exception:
            pass
        raise GuardiaBloqueo(msg)

    def escritura(p_bruta, que: str) -> None:
        p = _norma(p_bruta)
        if p is None or p in inocuos:
            return
        if os.path.basename(p) in rojos:
            cortar(f"{que} en archivo rojo ({p})")
        if p in blindados:
            cortar(f"{que} en archivo blindado ({p})")
        if not dentro(p):
            cortar(f"{que} fuera de la zona verde ({p})")

    def desde_config() -> bool:
        f = sys._getframe(2)
        while f is not None:
            if os.path.normcase(os.path.abspath(f.f_code.co_filename)) == config_py:
                return True
            f = f.f_back
        return False

    def comando(texto: str) -> None:
        if nivel_de_comando(texto) is not Verde:
            cortar(f"comando no verde: {texto[:200]}")

    ESCRIBE = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC

    def hook(evento: str, args: tuple) -> None:
        if getattr(_local, "dentro", False):
            return
        _local.dentro = True
        try:
            if evento == "open":
                ruta, modo, flags = (list(args) + [None, None, None])[:3]
                p = _norma(ruta)
                if p is None:
                    return
                es_escritura = (isinstance(modo, str) and any(c in modo for c in "wax+")) or (
                    modo is None and isinstance(flags, int) and flags & ESCRIBE)
                if es_escritura:
                    escritura(ruta, "escribir")
                elif os.path.basename(p) in rojos and not desde_config():
                    cortar(f"leer archivo rojo ({p})")
            elif evento in ("os.remove", "os.rmdir", "shutil.rmtree"):
                escritura(args[0], "borrar")
            elif evento == "os.rename":
                escritura(args[0], "mover (origen)")
                escritura(args[1], "mover (destino)")
            elif evento in ("os.mkdir", "os.chmod", "os.truncate", "os.utime", "os.chown"):
                escritura(args[0], evento)
            elif evento in ("os.symlink", "os.link"):
                escritura(args[1], evento)
            elif evento == "subprocess.Popen":
                ejecutable, argumentos = args[0], args[1]
                texto = argumentos if isinstance(argumentos, (str, bytes)) else " ".join(map(str, argumentos or []))
                if isinstance(texto, bytes):
                    texto = os.fsdecode(texto)
                comando(texto or str(ejecutable))
            elif evento == "os.system":
                comando(str(args[0]))
            elif evento in ("os.exec", "os.spawn", "os.posix_spawn"):
                comando(" ".join(map(str, args[1] or [])) if len(args) > 1 else str(args[0]))
            elif evento == "os.startfile":
                cortar(f"abrir programa/archivo con os.startfile ({args[0]})")
            elif evento.startswith("winreg.") and evento.split(".", 1)[1] in (
                    "CreateKey", "DeleteKey", "DeleteValue", "SetValue", "SaveKey", "LoadKey"):
                cortar(f"escribir en el registro de Windows ({evento})")
        finally:
            _local.dentro = False

    sys.addaudithook(hook)


def main(argv: list[str]) -> int:
    if not argv:
        print("uso: python nucleo/guardia_python.py script.py [args...]", file=sys.stderr)
        return 2
    script = os.path.abspath(argv[0])
    instalar()
    sys.argv = [script] + argv[1:]
    # sys.path[0] era nucleo/ (el del lanzador): se sustituye por la carpeta del script,
    # igual que haria `python script.py`.
    sys.path[0] = os.path.dirname(script)
    runpy.run_path(script, run_name="__main__")
    return 0


if __name__ == "__main__":
    # --help sin ejecutar nada (incidente 05/10). Lanzada como script, sys.path[0] es nucleo/: hace falta la raiz
    # para importar nucleo.ayuda (instalar() la anade igual, al final). Solo mira el PRIMER argumento: los demas
    # son del script vigilado y su --help es suyo.
    if str(RAIZ) not in sys.path: sys.path.append(str(RAIZ))
    from nucleo import ayuda; ayuda.atender(__doc__, sys.argv[1:2])
    raise SystemExit(main(sys.argv[1:]))
