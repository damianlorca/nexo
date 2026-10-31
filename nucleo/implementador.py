# -*- coding: utf-8 -*-
"""Implementador independiente de Claude (T669, F3 de la epica T664; plan §5).

Una tarea aprobada se hace con Aider (en .venv-implementador, version fijada con hash) y modelos GRATUITOS, en un
worktree propio (`../agente_impl/Txxx`, rama `impl/Txxx`). Despues la puerta (nucleo/puerta.py) decide si entra.

Reglas (decisiones de Damian del 04/10):
- EXCEPCION a "ningun turno escribe codigo": escribe codigo SOLO en su worktree y fusiona en `principal` SOLO por la
  puerta. Nunca R3 (riesgo.autorizacion). La PARADA y el interruptor de turnos lo paran antes de empezar.
- Privacidad: los archivos de PRIVADAS no llegan ni al disco del worktree (sparse-checkout) ni a Aider
  (.aiderignore + filtro de archivos); el mensaje al modelo sale del texto de la tarea, nunca de esos archivos.
- Codigo: primero los tests (solo tests/, el codigo en solo lectura) y tienen que FALLAR antes del cambio; despues
  el codigo. Documentacion: un solo paso. Suite completa en verde. Como mucho 2 intentos (el 2.o con otro modelo y
  sabiendo por que fallo el 1.o); despues la tarea queda `necesita:claude`.
- Aider con --no-auto-commits: los commits los hace el implementador con su marca (Implementador / Modelo / Nivel).
- Piloto (plan §5.4, dos fases): mientras dure nada se fusiona solo; Claude revisa cada diff y su veredicto mide el
  exito y la coincidencia con la puerta. Fase 2 (codigo, R2) solo con >= 80 % de exito y de coincidencia en la 1.

CLI:
    python -m nucleo.implementador implementar Txxx      (hace la tarea y pasa la puerta)
    python -m nucleo.implementador puerta Txxx           (vuelve a pasar la puerta: tras un OK o con el arbol limpio)
    python -m nucleo.implementador diff Txxx             (el diff de su rama contra principal)
    python -m nucleo.implementador piloto                (estado del piloto y diffs que esperan a Claude)
    python -m nucleo.implementador claude Txxx FUSIONAR|RECHAZAR "motivo"   (veredicto de Claude en el piloto)
    python -m nucleo.implementador iniciar_piloto T1,T2,... T3,T4,...       (fase 1 y fase 2)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from nucleo import cerrojo_suite
from nucleo import riesgo
from nucleo import tareas as T
from nucleo.candado import bloqueo
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico

REPO = RAIZ
WORKTREES = RAIZ.parent / "agente_impl"
INFORMES = RAIZ / "memoria" / "implementador"
PILOTO = INFORMES / "piloto.json"
AIDER = RAIZ / ".venv-implementador" / "Scripts" / "aider.exe"
PYTHON = RAIZ / ".venv" / "Scripts" / "python.exe"
SIN_NAVEGADOR = RAIZ / "nucleo" / "sin_navegador"     # sitecustomize que anula webbrowser en el proceso de Aider
RAMA_BASE = "principal"
MAX_INTENTOS = 2
CARPETA_TESTS_DADOS = "tests_dados"
# 04/10, fase 2: con "whole" (reescribir el archivo entero) los modelos gratuitos cortaban por limite de tokens en
# archivos de ~280 lineas y no llegaban a cambiar nada (T348, T421, T422). Con "diff" solo envian los trozos que cambian.
FORMATO_CODIGO = "diff"
TESTS_DADOS = "tests:dados"     # etiqueta: los tests de la tarea ya estan escritos en principal (fase 2 del piloto)
TIMEOUT_AIDER = 600
TIMEOUT_SUITE = 1200          # s, minimo; el de cada vez = la ultima suite completa medida x2 (timeout_suite, Bloque 21)
ESPERA_SUITE = 600            # s que se espera a que otra suite de NEXO suelte el cerrojo; luego, a otra tanda
DURACION_SUITE = "suite_duracion.json"
SUITE_WORKERS = 8             # pytest-xdist en la suite completa (requirements-tests.txt): 13 min en serie, <2 en paralelo
UMBRAL_PILOTO = 0.80
# Damian 04/10 (piloto: exito 10 %): la documentacion con datos de NEXO se queda con Claude. El implementador solo
# hace codigo con tests hasta que la revision de la puerta compruebe hechos contra el repo.
DOCUMENTACION = False
FIRMA = ["-c", "user.name=NEXO implementador", "-c", "user.email=nexo-implementador@localhost"]

# Lo privado de Damian (04/10). Igual que .aiderignore (lo comprueba un test).
PRIVADAS = ("memoria/becas.md", "memoria/historial_telegram.json", "canal/entrada/", "canal/estado_bot.json",
            "secretos.toml", ".env", "registros/", "chrome-perfil/")


class Modelo(NamedTuple):
    id: str
    proveedor: str
    aider: str        # nombre para Aider/litellm
    familia: str


# Prueba corta real del 04/10 (repo de juguete: errata en README + funcion con su test): los 4 hicieron 3/3 con la
# suite en verde (gpt-oss-120b 7 s, qwen3.8-27b 6 s, gemini-3.6-flash 9 s, nemotron-3-super 11 s; retirado el 21/10).
# T320/T748 (05/10, banco nucleo/banco_modelos.py, rol programar = los tests dados de T347/T348/T421/T422 con bloques
# SEARCH/REPLACE): gemini-3.5-flash-lite 4/4 en verde en todas las pasadas, gpt-oss-120b 0,86 de calidad media y
# gemini-3.6-flash 0 (no aplica bien los bloques). Orden: el banco primero y alternando familias para que el 2.o
# intento sea de otra.
MODELOS = (
    Modelo("gemini_api:gemini-3.5-flash-lite", "gemini_api", "gemini/gemini-3.5-flash-lite", "google"),
    Modelo("groq:gpt-oss-120b", "groq", "groq/openai/gpt-oss-120b", "openai"),
    Modelo("groq:qwen3.8-27b", "groq", "groq/qwen/qwen3.8-27b", "alibaba"),
    None,      # NVIDIA: lo pone _nvidia() (T1039)
)


def _nvidia(modelo: str | None = None) -> Modelo:
    """T1039 (25/10): NVIDIA = el primer modelo de config nvidia.modelos (ultra el primero), sin nombre fijo: el
    nemotron-3-super escrito a mano daba 404. `modelo` = el que toque (modelos_programar pasa el primer VIVO)."""
    import proveedores as P
    m = modelo or P.modelos_nvidia_config()[0]
    return Modelo(P.id_corto_nvidia(m), "nvidia", f"openai/{m}", "nvidia")


MODELOS = tuple(m or _nvidia() for m in MODELOS)


def clave_banco(m: Modelo) -> str:
    """'proveedor:modelo' como lo guarda el banco T320: 'groq/qwen/qwen3.8-27b' -> 'groq:qwen/qwen3.8-27b'."""
    return f"{m.proveedor}:{m.aider.split('/', 1)[1]}"


def modelos_programar() -> list[Modelo]:
    """MODELOS con el mejor y la reserva del rol 'programar' del banco delante (T320, Damian 11/10: lo elige NEXO)."""
    from nucleo import banco_modelos
    import proveedores as P
    vivo = P.modelo_nvidia_principal()       # T1039: si el primero de la config ya no esta vivo, el siguiente
    lista = [_nvidia(vivo) if m.proveedor == "nvidia" else m for m in MODELOS]
    return banco_modelos.ordenar("programar", lista, clave_banco)


# ================================================================ privacidad
def _norm(ruta: str) -> str:
    r = str(ruta).strip().strip('"').replace("\\", "/")
    while r.startswith("./"):
        r = r[2:]
    return r


def privada(ruta: str) -> bool:
    r = _norm(ruta)
    base = r.rsplit("/", 1)[-1]
    for p in PRIVADAS:
        if p.endswith("/"):
            if r.startswith(p) or r == p[:-1]:
                return True
        elif p in ("secretos.toml",):
            if base == p:
                return True
        elif p == ".env":
            if base == ".env" or base.startswith(".env."):
                return True
        elif r == p:
            return True
    return False


def no_enviable(ruta: str) -> bool:
    """Lo que NUNCA sale hacia un modelo (Damian 04/10), aunque la tarea lo pida: lo privado, todo memoria/, el vault
    (contexto/) y cualquier ruta fuera del repo (absoluta o con ..)."""
    r = _norm(ruta)
    if not r or privada(r):
        return True
    partes = r.split("/")
    return (partes[0] == "memoria" or "contexto" in partes or ".." in partes or r.startswith("/")
            or (len(r) > 1 and r[1] == ":"))


def aiderignore() -> str:
    return (RAIZ / ".aiderignore").read_text(encoding="utf-8")


def patrones_sparse() -> list[str]:
    """Todo el repo menos lo privado (sparse-checkout sin conos)."""
    pats = ["/*"]
    for p in PRIVADAS:
        pats.append(f"!{p}" if p in ("secretos.toml", ".env") else f"!/{p}")
    pats += ["!.env.*"]
    return pats


# ================================================================ cuando no trabaja
def detenido() -> str | None:
    from nucleo import parada, turnos
    m = parada.activa()
    if m:
        return f"PARADA activa: {m}"
    m = turnos.desactivados()
    return f"turnos desactivados: {m}" if m else None


# ================================================================ git
def _git(cwd, *args, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])}: {r.stderr.strip()[:500]}")
    return r.stdout


def worktree_de(tid: str) -> Path:
    return WORKTREES / tid


def crear_worktree(tid: str) -> Path:
    """Worktree propio, rama impl/Txxx desde principal, sin lo privado en disco. Si ya existe, se reutiliza."""
    wt = worktree_de(tid)
    rama = f"impl/{tid}"
    if (wt / ".git").exists():
        return wt
    WORKTREES.mkdir(parents=True, exist_ok=True)
    existe = bool(_git(REPO, "branch", "--list", rama).strip())
    if existe:
        _git(REPO, "worktree", "add", "-q", "--no-checkout", str(wt), rama)
    else:
        _git(REPO, "worktree", "add", "-q", "--no-checkout", str(wt), "-b", rama, RAMA_BASE)
    _git(wt, "sparse-checkout", "set", "--no-cone", *patrones_sparse())
    _git(wt, "reset", "-q", "--hard")
    return wt


def _cambiados(wt: Path) -> list[str]:
    salida = _git(wt, "status", "--porcelain", "--untracked-files=all")
    rutas = []
    for linea in salida.splitlines():
        ruta = linea[3:].split(" -> ")[-1].strip().strip('"')
        if ruta and not ruta.split("/")[-1].startswith(".aider."):
            rutas.append(_norm(ruta))
    return rutas


def _anadir(wt: Path) -> None:
    _git(wt, "add", "-A", "--", ".", ":(exclude).aider.*")


def _commit(wt: Path, mensaje: str) -> str:
    _anadir(wt)
    _git(wt, *FIRMA, "commit", "-q", "--no-verify", "-m", mensaje)
    return _git(wt, "rev-parse", "HEAD").strip()


def limpiar(wt) -> None:
    """Deja el worktree en su ultimo commit: lo que escriba la suite al pasar no es cambio del implementador
    (piloto 04/10: un test dejaba memoria/modelos_estado.json y se colaba en el diff)."""
    _git(wt, "reset", "-q", "--hard")
    _git(wt, "clean", "-q", "-fd", "-e", ".aider.*")


def conservar_finales(wt, base: str) -> None:
    """Cada archivo tocado conserva sus finales de linea (los nuevos, LF). Piloto T377 (04/10): Aider escribio el
    README con CRLF y el diff parecia una reescritura entera."""
    wt = Path(wt)
    for ruta in _cambiados(wt):
        f = wt / ruta
        if not f.is_file():
            continue
        nuevo = f.read_bytes()
        if b"\0" in nuevo[:8000]:
            continue                      # binario: no se toca
        r = subprocess.run(["git", "show", f"{base}:{ruta}"], cwd=str(wt), capture_output=True)
        crlf = r.returncode == 0 and b"\r\n" in r.stdout
        lf = nuevo.replace(b"\r\n", b"\n")
        f.write_bytes(lf.replace(b"\n", b"\r\n") if crlf else lf)


def preparar_tests_dados(wt, objs, base: str) -> str:
    """Fase 2 del piloto: los tests de la tarea los escribe Claude y viven en `tests_dados/` (fuera de la suite, para que
    principal siga en verde mientras la tarea esta sin hacer). Se copian a tests/ en la rama de la tarea, en un commit
    propio, y ese commit es la base del trabajo: el modelo solo escribe codigo. Devuelve el commit (o `base` si no
    habia ninguno)."""
    wt = Path(wt)
    _git(wt, "reset", "-q", "--hard", base)
    _git(wt, "clean", "-q", "-fd", "-e", ".aider.*")
    copiados = []
    for o in objs:
        origen = REPO / CARPETA_TESTS_DADOS / Path(o).name
        if o.startswith("tests/") and origen.is_file():
            destino = wt / o
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(origen.read_bytes())
            copiados.append(o)
    if not copiados:
        return base
    return _commit(wt, f"Tests dados de la tarea (escritos por Claude; fallan hasta que se haga el cambio)\n\n"
                       f"Implementador: {wt.name}")


def diff_rama(tid: str) -> str:
    base = _git(REPO, "merge-base", RAMA_BASE, f"impl/{tid}").strip()
    return _git(REPO, "diff", f"{base}..impl/{tid}")


# ================================================================ suite y Aider
class FalloInfra(RuntimeError):
    """Bloque 21: la suite no llego a dar resultado (otra suite de NEXO no solto el cerrojo, o se paso de tiempo). Es
    fallo de infraestructura, no del codigo: no es un rojo, no gasta intento y no deshace una fusion."""


def duracion_suite() -> float | None:
    """Segundos de la ultima suite COMPLETA que acabo (verde o roja), o None si no hay medida."""
    try:
        return float(json.loads((INFORMES / DURACION_SUITE).read_text(encoding="utf-8"))["segundos"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def timeout_suite() -> int:
    """Bloque 21: la ultima duracion medida x2, nunca menos de TIMEOUT_SUITE (el 25/10 la suite ya pasaba de 1200 s)."""
    d = duracion_suite()
    return max(TIMEOUT_SUITE, int(2 * d)) if d else TIMEOUT_SUITE


def _anotar_duracion(segundos: float, cwd) -> None:
    INFORMES.mkdir(parents=True, exist_ok=True)
    escribir_atomico(INFORMES / DURACION_SUITE, json.dumps(
        {"segundos": round(segundos, 1), "cuando": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         "donde": Path(cwd).name}, ensure_ascii=False))


def _cerrar_suite(proc, args: list[str]) -> str:
    """Cierra una suite pasada de tiempo con TODO su arbol, por PID exacto: el python del .venv es un lanzador que
    arranca el interprete real con los mismos argumentos, y matar solo al lanzador (lo que hacia subprocess.run con
    timeout) dejaba el pytest de verdad suelto, pisando a la suite siguiente (25/10). Como el planificador (T1024):
    linea de comando comprobada y todos los hijos listados antes del /T; con uno que no se reconoce, no se mata.
    Devuelve '' si lo cerro (o ya habia acabado) o el motivo por el que no."""
    from nucleo import planificador as PL
    if proc.poll() is not None:
        return ""
    cola = subprocess.list2cmdline(args[1:])   # "-m pytest tests interfaz/tests -q -p no:cacheprovider"
    try:
        linea = PL._linea_de_comando(proc.pid)
        hijos = PL._hijos(proc.pid)
    except Exception as e:  # noqa: BLE001 - sin poder leer los procesos no se mata nada
        return f"no se pudieron leer sus procesos ({type(e).__name__})"
    if cola not in linea:
        return "" if proc.poll() is not None else f"el PID {proc.pid} ya no es la suite: no se toca"
    nuestros = {proc.pid}
    for h in hijos:                            # _hijos da cada padre antes que sus hijos
        if h["reconocido"] or cola in h["linea"] or h["padre"] in nuestros:
            nuestros.add(h["pid"])
    raros = [h for h in hijos if h["pid"] not in nuestros]
    if raros:
        return "hijo no reconocido: " + "; ".join(f"{h['pid']} {h['nombre']} {h['linea'][:120]}" for h in raros)
    PL._matar(proc.pid)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        return "taskkill no lo cerro"
    return ""


def _correr_pytest(args: list[str], cwd, limite: int) -> tuple[int, str]:
    """(codigo, salida). La salida va a un archivo temporal y no a una tuberia: si no se puede cerrar un arbol pasado
    de tiempo, nadie se queda esperando a que suelte la tuberia."""
    import tempfile
    with tempfile.TemporaryFile() as salida:
        proc = subprocess.Popen(args, cwd=str(cwd), stdout=salida, stderr=subprocess.STDOUT,
                                env=dict(os.environ, PYTHONUTF8="1", **cerrojo_suite.env_hijo()))
        try:
            codigo = proc.wait(timeout=limite)
        except subprocess.TimeoutExpired:
            motivo = _cerrar_suite(proc, args)
            raise FalloInfra(f"la suite tardo mas de {limite} s" + (f" y NO se pudo cerrar ({motivo})" if motivo
                                                                     else " (cerrada con su arbol)")) from None
        salida.seek(0)
        return codigo, salida.read().decode("utf-8", errors="replace")


def _hay_xdist() -> bool:
    import importlib.util
    return importlib.util.find_spec("xdist") is not None


def _suite(cwd, archivos=None) -> tuple[bool, str]:
    """pytest con el .venv de NEXO dentro del worktree. Sin archivos: la suite completa.
    Bloque 21: con el cerrojo de suites de NEXO (una a la vez) y timeout_suite(). Si otra suite no suelta el cerrojo en
    ESPERA_SUITE s o esta se pasa de tiempo, FalloInfra (no es un rojo)."""
    objetivo = list(archivos) if archivos else ["tests", "interfaz/tests"]
    args = [str(PYTHON), "-m", "pytest", *objetivo, "-q", "-p", "no:cacheprovider"]
    if not archivos and SUITE_WORKERS and _hay_xdist():
        args += ["-n", str(SUITE_WORKERS)]
    try:
        with cerrojo_suite.tomar(ESPERA_SUITE, motivo=f"implementador: suite en {Path(cwd).name}"):
            inicio = time.monotonic()
            codigo, salida = _correr_pytest(args, cwd, timeout_suite())
            if not archivos:
                _anotar_duracion(time.monotonic() - inicio, cwd)
    except cerrojo_suite.Ocupada as e:
        raise FalloInfra(f"otra suite de NEXO en marcha ({e})") from None
    # T1027: la salida ENTERA (antes, los ultimos 3000 car.): nucleo.linea_base lee todos los FAILED/ERROR del resumen.
    # Quien la guarda en un informe o en un motivo la recorta alli.
    return codigo == 0, salida.strip()


def aiderignore_tarea(archivos, solo_lectura=()) -> str:
    """Lista BLANCA para una ejecucion: todo ignorado salvo los archivos de la tarea; lo privado, al final, siempre
    ignorado. Piloto 04/10 (T461): con --yes-always Aider anadia al chat cualquier archivo que el modelo nombrara
    (memoria/tareas.json, memoria/historial.md...) y lo mandaba al proveedor."""
    lineas = ["# T669: lista blanca de esta ejecucion (la genera nucleo/implementador.py)", "*"]
    for r in list(archivos) + list(solo_lectura):
        r = _norm(r)
        if not no_enviable(r) and f"!/{r}" not in lineas:
            lineas.append(f"!/{r}")
    lineas += [l.strip() for l in aiderignore().splitlines() if l.strip() and not l.startswith("#")]
    # Y lo R3 tampoco entra nunca (en el piloto Aider llego a meter nucleo/permisos.py en el chat).
    lineas += ["nucleo/permisos.py", "nucleo/instancia.py", "nucleo/config.py", "manos/", ".claude/", "CLAUDE.md",
               "AGENTS.md", "memoria/", "contexto/"]
    return "\n".join(lineas) + "\n"


def comando_aider(modelo: Modelo, archivos, mensaje: str, historial: Path, solo_lectura=(),
                  mapa: int = 0, ignorar: str = ".aiderignore", formato: str = "") -> list[str]:
    """mapa = tokens del mapa del repo. 0 en documentacion: Groq gratuito corta gpt-oss-120b en 8000 tokens/min y
    con el mapa la peticion pasaba de 12 000 (piloto, 04/10)."""
    cmd = [str(AIDER), "--model", modelo.aider, "--no-auto-commits", "--analytics-disable", "--yes-always",
           "--no-suggest-shell-commands", "--no-check-update", "--no-show-release-notes", "--no-gitignore",
           "--no-show-model-warnings",
           "--no-pretty", "--no-stream", "--no-detect-urls", "--no-fancy-input", "--no-restore-chat-history",
           "--map-tokens", str(mapa), "--aiderignore", str(ignorar), "--env-file", "NUL",
           "--chat-history-file", str(historial), "--input-history-file", "NUL", "--llm-history-file", "NUL"]
    if formato:
        cmd += ["--edit-format", formato]
    for r in solo_lectura:
        if not no_enviable(r):
            cmd += ["--read", _norm(r)]
    cmd += ["--message", mensaje]
    cmd += [_norm(a) for a in archivos if not no_enviable(a)]
    return cmd


def _clave(modelo: Modelo) -> str:
    import proveedores as P
    clase = {"groq": P.GroqProvider, "nvidia": P.NvidiaProvider, "gemini_api": P.GeminiAPIProvider}[modelo.proveedor]
    try:
        return clase()._clave() or ""
    except Exception:
        return ""


def entorno_aider(modelo: Modelo) -> dict:
    """Solo la clave de ESE proveedor (sale de secretos.toml por nucleo.config; nunca se escribe en ningun sitio)."""
    env = {k: v for k, v in os.environ.items() if not re.search(r"(?i)(api_key|token|secret)", k)}
    env.update(AIDER_ANALYTICS="false", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    # Nunca un navegador (piloto 04/10: 30 pestanas en el Chrome personal de Damian). El bloqueo de verdad es el
    # sitecustomize de SIN_NAVEGADOR; BROWSER nombra a ese navegador nulo.
    INFORMES.mkdir(parents=True, exist_ok=True)
    env.update(PYTHONPATH=os.pathsep.join([str(SIN_NAVEGADOR)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])),
               BROWSER="nexo-sin-navegador", NEXO_URLS_BLOQUEADAS=str(INFORMES / "urls_bloqueadas.log"))
    clave = _clave(modelo)
    if modelo.proveedor == "groq":
        env["GROQ_API_KEY"] = clave
    elif modelo.proveedor == "gemini_api":
        env["GEMINI_API_KEY"] = clave
    elif modelo.proveedor == "nvidia":
        env.update(OPENAI_API_KEY=clave, OPENAI_API_BASE="https://integrate.api.nvidia.com/v1")
    return env


def ejecutar_aider(worktree, modelo: Modelo, archivos, mensaje: str, solo_lectura=()) -> dict:
    mapa = 1024 if any(str(a).endswith(".py") for a in list(archivos) + list(solo_lectura)) else 0
    from nucleo.enfriamiento import enfriado
    if not _clave(modelo) or enfriado(modelo.proveedor):
        return {"ok": False, "no_disponible": True, "salida": f"{modelo.id} no disponible", "modelo": modelo.id}
    historial = INFORMES / Path(worktree).name / f"aider_{datetime.now():%Y%m%d_%H%M%S}.md"
    historial.parent.mkdir(parents=True, exist_ok=True)
    ignorar = historial.with_suffix(".aiderignore")
    ignorar.write_text(aiderignore_tarea(archivos, solo_lectura), encoding="utf-8")
    try:
        r = subprocess.run(comando_aider(modelo, archivos, mensaje, historial, solo_lectura, mapa, ignorar.resolve(),
                                        FORMATO_CODIGO if mapa else ""),
                           cwd=str(worktree),
                           env=entorno_aider(modelo), stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=TIMEOUT_AIDER)
    except subprocess.TimeoutExpired:
        return {"ok": False, "salida": f"Aider tardo mas de {TIMEOUT_AIDER} s", "modelo": modelo.id}
    salida = (r.stdout + r.stderr)[-3000:]
    caido = re.search(r"(?i)(rate.?limit|429|quota|AuthenticationError|NotFoundError|404|BadObject|Unable to list files in git repo|git repo corrupted)", salida)
    return {"ok": r.returncode == 0 and not caido, "no_disponible": bool(caido), "salida": salida,
            "modelo": modelo.id}


# ================================================================ que archivos toca
_PIEZAS = re.compile(r"PIEZAS:\s*(.+)")


def objetivos(tarea: dict) -> list[str]:
    """Rutas que nombra la tarea + las PIEZAS de su tarea origen (las revisiones de archivos). Sin privados."""
    rutas = list(riesgo.previsto(tarea).get("rutas") or [])
    for e in tarea.get("etiquetas") or []:
        if str(e).startswith("tarea_origen:"):
            o = T.buscar(str(e).split(":", 1)[1])
            m = _PIEZAS.search((o or {}).get("detalle") or "")
            if m:
                rutas += [p.split(":")[0].strip() for p in m.group(1).split(";") if p.strip()]
    vistas = []
    for r in rutas:
        r = _norm(r)
        if r and not r.endswith("/") and not no_enviable(r) and r not in vistas and riesgo.nivel_ruta(r)[0] != "R3" \
                and ((REPO / r).exists() or r.startswith("tests/")
                     or (r.endswith(".py") and (REPO / r).parent.is_dir())):   # 12/10: modulo NUEVO de una pieza
            vistas.append(r)
    return vistas


def _mensaje(tarea: dict, paso: str, error_previo: str = "") -> str:
    texto = f"Tarea {tarea['id']} de NEXO: {tarea.get('titulo', '')}\n\n{(tarea.get('detalle') or '')[:2000]}\n\n"
    # T676 (reglas de Karpathy, T167) y T713 (escalera de solucion minima de Ponytail, T176/T256, roles/codigo.md).
    reglas = ("Reglas: (1) piensa antes de editar: que pide exactamente la tarea y que supones; si algo es ambiguo, "
              "la interpretacion mas estrecha que cumpla los tests. (2) Solucion minima: si ya existe en el archivo o "
              "en la biblioteca estandar, usalo; si no, el minimo codigo nuevo, sin recortar validaciones ni "
              "seguridad. (3) Cambio quirurgico: haz SOLO lo que pide la tarea; no reformatees ni toques lo demas ni "
              "archivos que no esten en el chat. (4) El exito es verificable: los tests en verde sin romper nada. "
              "No anadas dependencias ni accesos a red. Escribe en espanol, como el resto del archivo. "
              # T1027 (T938): tests/test_ayuda_entradas.py lo exige a todo .py del repo con bloque __main__
              "(5) Si un .py tiene `if __name__ == \"__main__\":`, la PRIMERA linea de ese bloque es "
              "`from nucleo import ayuda; ayuda.atender(__doc__)` (o el script usa argparse): --help/-h nunca "
              "ejecuta nada.")
    pasos = {
        "documentacion": "Edita la documentacion para cumplir la tarea.",
        "tests": ("PASO 1 de 2: escribe SOLO los tests (en tests/) que demuestren lo que pide la tarea. Deben FALLAR "
                  "con el codigo actual. No toques el codigo (esta en solo lectura)."),
        "codigo": "PASO 2 de 2: cambia el codigo para que pasen los tests nuevos (en solo lectura) sin romper nada.",
    }
    previo = f"\n\nEl intento anterior fallo por esto; corrigelo:\n{error_previo[-1500:]}" if error_previo else ""
    return texto + pasos[paso] + "\n" + reglas + previo


# ================================================================ informes
def _informe_ruta(tid: str) -> Path:
    return INFORMES / f"{tid}.json"


def guardar_informe(inf: dict) -> dict:
    INFORMES.mkdir(parents=True, exist_ok=True)
    escribir_atomico(_informe_ruta(inf["tarea"]), json.dumps(inf, ensure_ascii=False, indent=1))
    return inf


def cargar_informe(tid: str) -> dict | None:
    try:
        return json.loads(_informe_ruta(tid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _fin(tid: str, estado: str, motivo: str, **extra) -> dict:
    inf = {"tarea": tid, "estado": estado, "motivo": motivo,
           "cuando": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **extra}
    if estado in ("listo", "fallido"):
        guardar_informe(inf)
    return inf


# ================================================================ el trabajo
def _intento(t: dict, wt: Path, base: str, modelo: Modelo, objs: list[str], es_codigo: bool, error_previo: str,
             ejecutar) -> dict:
    tid = t["id"]
    nuevos: list[str] = []
    fallaban = None
    dados = False
    if es_codigo:
        tests_obj = [o for o in objs if o.startswith("tests/")] or [f"tests/test_{tid.lower()}.py"]
        codigo_obj = [o for o in objs if not o.startswith("tests/")]
        if TESTS_DADOS in (t.get("etiquetas") or []):
            # Los tests ya estan en principal (los escribio Claude, fase 2 del piloto): son el enunciado, no se
            # reescriben. Se comprueba que fallan hoy y el modelo solo escribe codigo, con ellos en solo lectura.
            nuevos = [o for o in tests_obj if (wt / o).is_file()]
            if not nuevos or not codigo_obj:
                return {"ok": False, "motivo": f"{TESTS_DADOS}: faltan los tests o el codigo que tocar en la tarea"}
            ok_antes, salida = _suite(wt, nuevos)
            limpiar(wt)
            if ok_antes:
                return {"ok": False, "motivo": "los tests dados ya pasan: la tarea ya esta hecha o no prueba nada"}
            dados = True
        else:
            r = ejecutar(wt, modelo, tests_obj, _mensaje(t, "tests", error_previo), solo_lectura=codigo_obj)
            conservar_finales(wt, base)
            if not r.get("ok"):
                return {"ok": False, "motivo": f"Aider fallo en el paso de tests: {r.get('salida', '')[-800:]}", **r}
            cambiados = _cambiados(wt)
            fuera = [c for c in cambiados if not c.startswith("tests/")]
            if fuera:
                return {"ok": False, "motivo": f"el paso de tests toco {', '.join(fuera)}: solo tests en el paso 1"}
            nuevos = [c for c in cambiados if c.endswith(".py")]
            if not nuevos:
                return {"ok": False, "motivo": "el paso de tests no escribio ningun test"}
            _commit(wt, f"Tests de {tid} (paso 1: tests primero, fallan antes del cambio)\n\nImplementador: {tid}\n"
                        f"Modelo: {modelo.id}")
            ok_antes, salida = _suite(wt, nuevos)
            limpiar(wt)
            if ok_antes:
                return {"ok": False, "motivo": "los tests nuevos no fallan antes del cambio: no prueban nada"}
        fallaban = True
        r = ejecutar(wt, modelo, codigo_obj, _mensaje(t, "codigo", error_previo), solo_lectura=nuevos)
    else:
        r = ejecutar(wt, modelo, objs, _mensaje(t, "documentacion", error_previo))
    if not r.get("ok"):
        return {"ok": False, "motivo": f"Aider fallo: {r.get('salida', '')[-800:]}", **r}
    conservar_finales(wt, base)
    cambiados = _cambiados(wt)
    if not cambiados and not es_codigo:
        return {"ok": False, "motivo": "Aider no cambio nada"}
    privados = [c for c in cambiados if privada(c)]
    if privados:
        return {"ok": False, "motivo": f"toco archivos privados: {', '.join(privados)}"}
    retocados = [c for c in cambiados if dados and c in nuevos]
    if retocados:
        return {"ok": False, "motivo": f"cambio los tests dados ({', '.join(retocados)}): son el enunciado, solo codigo"}
    _anadir(wt)
    diff = _git(wt, "diff", "--cached", base)
    nivel = riesgo.calcular(diff=diff, etiquetas=t.get("etiquetas") or ())
    if nivel["nivel"] == "R3":
        return {"ok": False, "motivo": f"el cambio es R3 ({'; '.join(nivel['motivos'])}): nunca el implementador"}
    fuera = [c for c in cambiados if c not in objs and c not in nuevos]
    if fuera:
        return {"ok": False, "motivo": f"toco archivos fuera de alcance (no se le dieron): {', '.join(fuera)}"}
    if cambiados:
        _commit(wt, f"{tid}: {t.get('titulo', '')[:60]}\n\nImplementador: {tid}\nModelo: {modelo.id}\n"
                    f"Nivel: {nivel['nivel']}")
    ok, salida = _suite(wt)
    limpiar(wt)
    previos: list[str] = []
    if not ok:      # T1027: los rojos que ya fallaban en principal (mismo entorno) no son de esta tarea
        from nucleo import linea_base
        ok, salida, previos = linea_base.filtrar(ok, salida)
    if not ok:
        return {"ok": False, "motivo": f"la suite falla:\n{salida[-1500:]}"}
    return {"ok": True, "nivel_diff": nivel["nivel"], "tests_nuevos": nuevos, "tests_fallaban_antes": fallaban,
            "fallos_previos": previos}


# ================================================================ ejecutor directo (T748)
# T748 (05/10): con Aider, Groq gratuito rechazaba la peticion por tamano ("Request too large", limite de tokens por
# minuto: Aider anade su prompt de sistema y el mapa del repo) y gemini-3.5-flash-lite no cuadraba sus bloques; con
# un mensaje directo (archivo + tests + bloques SEARCH/REPLACE) esos mismos modelos dejaron en verde los 4 tests dados
# del banco T320. Mismos filtros de privacidad que Aider (no_enviable): solo salen los archivos de la tarea.
EJECUTOR = "directo"          # "directo" | "aider"
RONDAS_DIRECTO = 2            # como las "reflexiones" de Aider: si un bloque no cuadra, una vuelta mas con el error

PROMPT_DIRECTO = """{mensaje}

Responde UNICAMENTE con bloques de edicion. Antes de cada bloque, una linea 'ARCHIVO: ruta' con la ruta exacta:

ARCHIVO: ruta/del/archivo.py
<<<<<<< SEARCH
lineas EXACTAS copiadas del archivo actual (con su sangria)
=======
lineas nuevas
>>>>>>> REPLACE

Cada SEARCH tiene que aparecer tal cual y una sola vez en su archivo. Para un archivo nuevo, SEARCH vacio.
Solo puedes editar: {editables}.

{archivos}
"""

_ARCHIVO = re.compile(r"(?m)^\W*ARCHIVO:\s*`?([^\s`]+)`?\s*$")


def _bloques_por_archivo(respuesta: str, editables: list[str]) -> dict[str, str]:
    partes = _ARCHIVO.split(respuesta.replace("\r\n", "\n"))
    if len(partes) == 1:
        return {editables[0]: respuesta} if len(editables) == 1 else {}
    salida: dict[str, str] = {}
    for ruta, trozo in zip(partes[1::2], partes[2::2]):
        salida[_norm(ruta)] = salida.get(_norm(ruta), "") + "\n" + trozo
    return salida


def ejecutar_directo(worktree, modelo: Modelo, archivos, mensaje: str, solo_lectura=(), llamar=None) -> dict:
    """Misma firma y salida que ejecutar_aider. `llamar(proveedor, modelo, prompt)` = banco_modelos.llamar."""
    from nucleo import banco_modelos as B
    from nucleo.enfriamiento import enfriado
    llamar = llamar or B.llamar
    wt = Path(worktree)
    if not _clave(modelo) or enfriado(modelo.proveedor):
        return {"ok": False, "no_disponible": True, "salida": f"{modelo.id} no disponible", "modelo": modelo.id}
    editables = [_norm(a) for a in archivos if not no_enviable(a)]
    lectura = [_norm(r) for r in solo_lectura if not no_enviable(r) and (wt / r).is_file()]
    if not editables:
        return {"ok": False, "salida": "ningun archivo editable que se pueda enviar", "modelo": modelo.id}
    textos = "\n\n".join(f"=== {r}{' (SOLO LECTURA)' if r in lectura else ''} ===\n"
                         f"{(wt / r).read_text(encoding='utf-8', errors='replace')}"
                         for r in editables + lectura if (wt / r).is_file())
    prompt = PROMPT_DIRECTO.format(mensaje=mensaje, editables=", ".join(editables), archivos=textos)
    id_api = modelo.aider.split("/", 1)[1]          # "groq/openai/gpt-oss-120b" -> "openai/gpt-oss-120b"
    historial = INFORMES / wt.name / f"directo_{datetime.now():%Y%m%d_%H%M%S}.md"
    historial.parent.mkdir(parents=True, exist_ok=True)
    registro, error = [], ""
    for ronda in range(RONDAS_DIRECTO):
        pedido = prompt if not error else f"{prompt}\n\nTu respuesta anterior no se pudo aplicar: {error}\nRepitela entera y bien."
        r = llamar(modelo.proveedor, id_api, pedido)
        registro.append(f"## Ronda {ronda + 1} ({modelo.id})\n\n{r.get('texto') or r.get('error')}\n")
        if r.get("error"):
            historial.write_text("\n".join(registro), encoding="utf-8")
            # T1027 (T855): un 5xx (503 "high demand") es el proveedor, no el modelo: no gasta intento
            caido = r.get("codigo") in (429, 401, 403, 404, 410, 500, 502, 503, 504) or str(r["error"]).startswith("no ")
            return {"ok": False, "no_disponible": caido, "salida": f"{modelo.id}: {r['error']}", "modelo": modelo.id}
        por_archivo = _bloques_por_archivo(r["texto"], editables)
        fuera = [a for a in por_archivo if a not in editables]
        if fuera:
            error = f"intento editar archivos que no se le dieron: {', '.join(fuera)}"
            continue
        nuevos, error = {}, "" if por_archivo else "sin bloques SEARCH/REPLACE"
        for ruta, trozo in por_archivo.items():
            crudo = (wt / ruta).read_bytes() if (wt / ruta).is_file() else b""
            crlf = b"\r\n" in crudo           # se respeta el final de linea del archivo
            original = crudo.decode("utf-8").replace("\r\n", "\n")
            nuevo, motivo = B.aplicar_bloques(original, trozo)
            if nuevo is None:
                error = f"{ruta}: {motivo}"
                break
            nuevos[ruta] = nuevo.replace("\n", "\r\n") if crlf else nuevo
        if not error:
            for ruta, nuevo in nuevos.items():
                (wt / ruta).parent.mkdir(parents=True, exist_ok=True)
                (wt / ruta).write_bytes(nuevo.encode("utf-8"))
            historial.write_text("\n".join(registro), encoding="utf-8")
            return {"ok": True, "salida": f"aplicados bloques en {', '.join(nuevos)}", "modelo": modelo.id}
    historial.write_text("\n".join(registro), encoding="utf-8")
    return {"ok": False, "salida": f"no se pudo aplicar tras {RONDAS_DIRECTO} rondas: {error}", "modelo": modelo.id}


def _modelos_para(tid: str) -> list[Modelo]:
    """El orden del banco, pero los modelos que ya fallaron ESTA tarea van al final (T1027: al devolverla a la cola,
    el reintento empieza por otro: T849 sintaxis rota de nemotron, T847 sin bloques de gpt-oss...)."""
    fallaron = {i.get("modelo") for i in (cargar_informe(tid) or {}).get("intentos") or [] if not i.get("ok")}
    lista = modelos_programar()
    return [m for m in lista if m.id not in fallaron] + [m for m in lista if m.id in fallaron]


def implementar(tid: str, ejecutar=None) -> dict:
    """Hace la tarea en su worktree. No fusiona: eso es de la puerta (nucleo.puerta.pasar)."""
    ejecutar = ejecutar or (ejecutar_directo if EJECUTOR == "directo" else ejecutar_aider)
    motivo = detenido()
    if motivo:
        return _fin(tid, "detenido", motivo)
    t = T.buscar(tid)
    if t is None or t["id"] != tid:
        return _fin(tid, "error", "tarea no encontrada")
    p = _cargar_piloto()
    if p.get("aparcado"):
        return _fin(tid, "no_autorizado", "el implementador esta APARCADO (la fase 2 no llego al 80 %; plan §3.3 bis)")
    if p["activo"] and (p["fase1"] or p["fase2"]):
        lista = p["fase1"] if p["fase"] == 1 else p["fase2"]
        if tid not in lista:
            return _fin(tid, "no_autorizado", f"en el piloto solo entran las tareas de la fase {p['fase']}")
    aut = riesgo.autorizacion(t)
    if not aut["puede"]:
        return _fin(tid, "no_autorizado", aut["motivo"], nivel=aut["nivel"], solicitud=aut["solicitud"])
    objs = objetivos(t)
    if not objs:
        return _fin(tid, "fallido", "la tarea no nombra ningun archivo del repo que se pueda tocar", nivel=aut["nivel"])
    es_codigo = any(o.endswith(".py") and not o.startswith("tests/") for o in objs)
    if not es_codigo and not DOCUMENTACION:
        return _fin(tid, "no_autorizado", "documentacion: se queda con Claude (Damian 04/10; la puerta aun no comprueba "
                                          "hechos contra el repo)", nivel=aut["nivel"])
    wt = crear_worktree(tid)
    base = _git(REPO, "rev-parse", RAMA_BASE).strip()
    if TESTS_DADOS in (t.get("etiquetas") or []) and es_codigo:
        base_tests = preparar_tests_dados(wt, objs, base)
        if base_tests == base:
            return _fin(tid, "fallido", f"{TESTS_DADOS}: no hay tests en {CARPETA_TESTS_DADOS}/ para {', '.join(objs)}",
                        worktree=str(wt), nivel_aprobado=aut["nivel"])
        base = base_tests
    error, intentos, modelos = "", [], _modelos_para(tid)
    while len(intentos) < MAX_INTENTOS and modelos:
        modelo = modelos.pop(0)
        _git(wt, "reset", "-q", "--hard", base)
        _git(wt, "clean", "-q", "-fd", "-e", ".aider.*")
        try:
            r = _intento(t, wt, base, modelo, objs, es_codigo, error, ejecutar)
        except FalloInfra as e:
            # Bloque 21: la suite no dio resultado (cerrojo ocupado o se paso de tiempo): ni rojo ni intento gastado;
            # la tarea vuelve en la siguiente tanda (piloto_serie no la marca como terminada)
            return _fin(tid, "sin_suite", f"{e}; se reintenta en otra tanda", nivel=aut["nivel"], worktree=str(wt))
        if r.get("no_disponible"):
            continue               # sin cuota o sin clave: no gasta intento, prueba el siguiente modelo
        intentos.append({"modelo": modelo.id, "familia": modelo.familia, "ok": r["ok"], "motivo": r.get("motivo", "")})
        if r["ok"]:
            return _fin(tid, "listo", "implementada en su rama; falta la puerta", worktree=str(wt), rama=f"impl/{tid}",
                        base=base, nivel_aprobado=aut["nivel"], nivel_diff=r["nivel_diff"], modelo=modelo.id,
                        familia=modelo.familia, intentos=intentos, es_codigo=es_codigo, objetivos=objs,
                        tests_nuevos=r["tests_nuevos"], tests_fallaban_antes=r["tests_fallaban_antes"],
                        fallos_previos=r.get("fallos_previos") or [])
        error = r["motivo"]
    motivo = error or "ningun modelo disponible"
    if not intentos:
        # Ningun modelo llego a trabajar (cuota agotada, claves, fallo de git...): no es un intento de la tarea, no se
        # marca como fallida; el turno lo reintenta en la siguiente tanda (piloto_serie._vacio).
        return _fin(tid, "sin_modelo", motivo, nivel=aut["nivel"])
    t = T.buscar(tid)
    T.actualizar(tid, etiquetas=list(dict.fromkeys(list(t.get("etiquetas") or []) + ["necesita:claude"])))
    T.anotar(tid, f"Implementador (T669): no lo consiguio en {len(intentos)} de {MAX_INTENTOS} intentos; necesita "
                  f"Claude. Ultimo motivo: {motivo[:400]}")
    if _cargar_piloto()["activo"]:
        registrar_puerta(tid, pasa=False, fallo=True)
    return _fin(tid, "fallido", motivo, worktree=str(wt), intentos=intentos, nivel_aprobado=aut["nivel"])


# ================================================================ piloto
def _piloto_defecto() -> dict:
    return {"activo": True, "fase": 1, "fase1": [], "fase2": [], "casos": {}, "cerrada_fase1": False, "nota": ""}


def _cargar_piloto() -> dict:
    try:
        return {**_piloto_defecto(), **json.loads(PILOTO.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return _piloto_defecto()


def _guardar_piloto(p: dict) -> None:
    PILOTO.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(PILOTO, json.dumps(p, ensure_ascii=False, indent=1))


def _editar_piloto(fn) -> dict:
    PILOTO.parent.mkdir(parents=True, exist_ok=True)
    with bloqueo(PILOTO.parent / ".candado_piloto.lock"):
        p = _cargar_piloto()
        fn(p)
        _evaluar(p)
        _guardar_piloto(p)
        return p


def en_piloto() -> bool:
    return bool(_cargar_piloto()["activo"])


def iniciar_piloto(fase1, fase2) -> dict:
    def f(p):
        p.update(activo=True, fase=1, fase1=list(fase1), fase2=list(fase2), cerrada_fase1=False, nota="")
    return _editar_piloto(f)


def abrir_fase2(motivo: str) -> dict:
    """Abre la fase 2 por decision de Damian aunque la 1 no llegara al umbral (04/10: solo codigo con tests)."""
    def f(p):
        p.update(fase=2, cerrada_fase1=True, nota=f"fase 2 abierta a mano: {motivo}")
    return _editar_piloto(f)


def registrar_puerta(tid: str, pasa: bool, fallo: bool = False) -> dict:
    def f(p):
        c = p["casos"].setdefault(tid, {"fase": p["fase"], "claude": None})
        c.update(puerta=bool(pasa), fallo=bool(fallo))
    return _editar_piloto(f)


def veredicto_claude(tid: str, decision: str, motivo: str, resumen: str = "") -> dict:
    """`resumen`: 3 lineas en llano (que cambia y para que) que verá Damian junto al diff en la bandeja R2."""
    decision = decision.upper()
    if decision not in ("FUSIONAR", "RECHAZAR"):
        raise ValueError("decision: FUSIONAR o RECHAZAR")

    def f(p):
        c = p["casos"].setdefault(tid, {"fase": p["fase"], "puerta": None, "fallo": False})
        c.update(claude=decision, motivo_claude=motivo)
        if resumen:
            c["resumen"] = f"{resumen}\nOpinion de Claude: {decision}. {motivo}"
    p = _editar_piloto(f)
    if T.buscar(tid) and T.buscar(tid)["id"] == tid:
        T.anotar(tid, f"Piloto F3, revision de Claude del diff: {decision}. {motivo}")
    return p


def _metricas(casos: list[dict]) -> tuple[float | None, float | None]:
    finales = [c for c in casos if c.get("fallo") or c.get("claude")]
    exito = (sum(1 for c in finales if c.get("claude") == "FUSIONAR") / len(finales)) if finales else None
    ambos = [c for c in casos if c.get("claude") and c.get("puerta") is not None]
    coinc = (sum(1 for c in ambos if c["puerta"] == (c["claude"] == "FUSIONAR")) / len(ambos)) if ambos else None
    return exito, coinc


def _evaluar(p: dict) -> None:
    if p["fase"] != 1 or not p["fase1"] or p["cerrada_fase1"]:
        return
    casos = [p["casos"].get(t) for t in p["fase1"]]
    if not all(c and (c.get("fallo") or c.get("claude")) for c in casos):
        return
    exito, coinc = _metricas(casos)
    if (exito or 0) >= UMBRAL_PILOTO and (coinc or 0) >= UMBRAL_PILOTO:
        p.update(fase=2, nota=f"fase 1 superada (exito {exito:.0%}, coincidencia {coinc:.0%}): empieza la fase 2")
    else:
        p.update(cerrada_fase1=True,
                 nota=f"fase 1 por debajo del {UMBRAL_PILOTO:.0%} (exito {exito or 0:.0%}, coincidencia {coinc or 0:.0%}):"
                      " regla de respaldo (§3.3 bis), ajustar modelo o herramienta (opencode si falla Aider)")


def piloto() -> dict:
    p = _cargar_piloto()
    lista = p["fase1"] if p["fase"] == 1 else p["fase2"]
    casos = [p["casos"][t] for t in lista if t in p["casos"]] if lista else list(p["casos"].values())
    if not casos and p["fase"] == 2:      # fase 2 recien abierta: se ven los datos con los que se abrio
        casos = [p["casos"][t] for t in p["fase1"] if t in p["casos"]]
    exito, coinc = _metricas(casos)
    historial = [{"tarea": t, "motivo": c.get("motivo_claude", ""), "puerta": c.get("puerta")}
                 for t, c in p["casos"].items() if c.get("claude") == "RECHAZAR"]     # solo informacion, sin botones
    return {**p, "exito": exito, "coincidencia": coinc, "historial_rechazados": historial,
            "pendientes_claude": [t for t, c in p["casos"].items() if c.get("puerta") is not None
                                  and not c.get("fallo") and not c.get("claude")]}


# ================================================================ CLI
def _cli(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "implementar" and args:
        inf = implementar(args[0])
        print(json.dumps({k: v for k, v in inf.items() if k != "intentos"}, ensure_ascii=False, indent=1))
        for i in inf.get("intentos", []):
            print(f"  intento {i['modelo']}: {'OK' if i['ok'] else i['motivo'][:200]}")
        if inf["estado"] == "listo":
            from nucleo import puerta
            print(json.dumps(puerta.pasar(args[0], inf), ensure_ascii=False, indent=1))
        return 0 if inf["estado"] == "listo" else 1
    if cmd == "puerta" and args:
        from nucleo import puerta
        print(json.dumps(puerta.pasar(args[0]), ensure_ascii=False, indent=1))
        return 0
    if cmd == "diff" and args:
        print(diff_rama(args[0]))
        return 0
    if cmd == "abrir_fase2":
        print(json.dumps(abrir_fase2(" ".join(args) or "decision de Damian"), ensure_ascii=False, indent=1))
        return 0
    if cmd == "piloto":
        print(json.dumps(piloto(), ensure_ascii=False, indent=1))
        return 0
    if cmd == "claude" and len(args) >= 2:
        resto = args[2:]
        resumen = ""
        if "--resumen" in resto:
            i = resto.index("--resumen")
            resumen, resto = " ".join(resto[i + 1:]), resto[:i]
        veredicto_claude(args[0], args[1], " ".join(resto), resumen)
        print(json.dumps(piloto(), ensure_ascii=False, indent=1))
        return 0
    if cmd == "iniciar_piloto" and args:
        print(json.dumps(iniciar_piloto([x for x in args[0].split(",") if x],
                                        [x for x in (args[1] if len(args) > 1 else "").split(",") if x]),
                         ensure_ascii=False, indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(_cli(sys.argv[1:]))
