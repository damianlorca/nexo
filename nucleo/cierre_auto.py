# -*- coding: utf-8 -*-
"""Cierre automatico de lo ya hecho (Damian 11/10, independencia de NEXO, bloque 1).

Problema: tareas que siguen abiertas aunque su trabajo ya esta en `principal` (T708, T711...). Nadie las cierra y
ensucian la cola.

Que hace (un paso del planificador, una vez al dia, en un proceso aparte para no bloquear el tick):
  1. Un solo `git log principal`: cada commit cuyo ASUNTO (primera linea) cita el ID de una tarea abierta
     (pendiente, en curso o esperando). Un ID citado solo en el cuerpo no cuenta (suele ser una mencion de paso).
     No cuentan los espejos de la nube ni los commits que solo tocan memoria/.
  2. CERRABLE si: el commit mas reciente que la cita no dice parcial/xfail/pendiente/WIP, entre esos commits hay
     tests (tests/ o interfaz/tests/, que sigan existiendo), la tarea no exige otro cierre (investigacion con
     RESULTADO, revision de Claude pendiente, propuesta sin aprobar, epica) y es ATOMICA: una fusion del implementador
     ('Fusiona impl/Txxx', tests dados) o un bug ya verificado (testeado o nota [verificado]). Un commit con tests
     no prueba que una tarea por fases haya acabado (T669, T320...): esas van a Claude.
  3. Se EJECUTAN esos tests. Verdes -> se cierra con evidencia (nucleo.evidencias.cerrar: commit + salida de pytest).
     Rojos o cualquier duda -> NO se cierra: va a la lista de dudosas para Claude (memoria/cierre_auto/dudosas.json,
     CLI `dudosas`), con el motivo.

CLI (.venv\\Scripts\\python.exe -m nucleo.cierre_auto ...):
  simular                 que cerraria y que dejaria para Claude (sin ejecutar tests ni tocar nada)
  aplicar [--max N]       ejecuta los tests de las cerrables y cierra las verdes (lo que hace el planificador)
  dudosas                 la lista que espera a Claude
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from nucleo import tareas as T
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico

REPO = RAIZ
RAMA = "principal"
CARPETA = RAIZ / "memoria" / "cierre_auto"
PYTHON = RAIZ / ".venv" / "Scripts" / "python.exe"
ABIERTAS = ("pendiente", "en_curso", "esperando")
MAX_POR_PASADA = 10
CADA = timedelta(hours=24)
TIMEOUT_TESTS = 900
LANZADOR = None            # los tests lo sustituyen (conftest): nunca un proceso real desde un tick de prueba
_ID = re.compile(r"\bT\d{3,4}\b")
_DUDOSO = re.compile(r"(?i)\b(parcial|xfail|wip|pendiente|a medias|sin terminar|borrador|primer paso)\b")
_NO_CUENTA = re.compile(r"(?i)^(espejo de|tareas:|memoria:)")
_TEST = re.compile(r"^(tests|interfaz/tests)/(.+/)?test_[^/]+\.py$")
SEP_C, SEP_F = "\x1e", "\x1f"


# ================================================================ git
def _git(*args, cwd=None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd or REPO, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.stdout if r.returncode == 0 else ""


def commits_por_tarea(git=None) -> dict[str, list[dict]]:
    """{Txxx: [commit, ...]} (el mas reciente primero) con los commits de principal que la citan en el asunto."""
    git = git or _git
    salida = git("log", RAMA, f"--format={SEP_C}%H{SEP_F}%s", "--name-only", "-m", "--first-parent")
    por_tarea: dict[str, list[dict]] = {}
    for bloque in salida.split(SEP_C):
        if not bloque.strip():
            continue
        cabecera, _, resto = bloque.partition("\n")
        sha, _, asunto = cabecera.partition(SEP_F)
        if _NO_CUENTA.search(asunto):
            continue
        archivos = [a.strip() for a in resto.splitlines() if a.strip()]
        if archivos and all(a.startswith("memoria/") for a in archivos):
            continue
        c = {"sha": sha[:10], "asunto": asunto.strip(), "archivos": archivos}
        for tid in dict.fromkeys(_ID.findall(asunto)):
            por_tarea.setdefault(tid, []).append(c)
    return por_tarea


# ================================================================ decision
def _exige_otro_cierre(t: dict) -> str:
    et = t.get("etiquetas") or []
    if any(str(e).startswith("revision_claude:") for e in et):
        return "espera la revision de Claude de su borrador"
    if "cat:investigacion" in et and not any(str(e).startswith("turno:lote") for e in et):
        return "investigacion: solo se cierra con RESULTADO (nucleo.investigacion decidir)"
    if t.get("estado") == "propuesta":
        return "propuesta sin aprobar"
    if any(str(e).startswith("epica") and ":" not in str(e)[5:6] for e in et) or "cat:epica" in et:
        return "epica: se cierra cuando acaban sus hijas"
    return ""


def evaluar(t: dict, commits: list[dict], existe=None) -> dict:
    """{"tid", "decision": cerrar|dudosa, "motivo", "commit", "tests"}."""
    existe = existe or (lambda r: (REPO / r).is_file())
    r = {"tid": t["id"], "titulo": t.get("titulo", "")[:90], "decision": "dudosa", "motivo": "", "commit": None,
         "tests": []}
    ultimo = commits[0]
    r["commit"] = {"sha": ultimo["sha"], "asunto": ultimo["asunto"][:120]}
    commits = vigentes(commits)
    tests = sorted({a for c in commits for a in c["archivos"] if _TEST.match(a) and existe(a)})
    r["tests"] = tests
    otro = _exige_otro_cierre(t)
    if otro:
        r["motivo"] = otro
    elif not commits or _REVERT.match(ultimo["asunto"]):
        r["motivo"] = "su ultimo cambio se deshizo (git revert): no esta en principal"
    elif _DUDOSO.search(ultimo["asunto"]):
        r["motivo"] = f"el ultimo commit que la cita dice '{_DUDOSO.search(ultimo['asunto']).group(0)}'"
    elif not tests:
        r["motivo"] = "sus commits no traen tests: no hay como comprobarlo sin Claude"
    elif any(_FUSION.match(c["asunto"]) and t["id"] in c["asunto"].split(":")[0] for c in commits):
        r["decision"], r["motivo"] = "cerrar", f"fusionada por la puerta del implementador con {len(tests)} test(s) dados"
    elif not _es_bug(t):
        # 11/10: un commit con tests no prueba que la tarea ACABO (T669, T320, T682... van por fases y tienen commits
        # con tests). Solo las atomicas se cierran solas; el resto lo confirma Claude.
        r["motivo"] = "tiene commits con tests pero no es atomica (no es un bug ni una fusion del implementador): " \
                      "confirmar que no queda trabajo"
    elif not _verificada(t):
        r["motivo"] = "bug con commits y tests, pero sin verificacion previa (testeado o nota [verificado])"
    else:
        r["decision"], r["motivo"] = "cerrar", f"bug verificado: {len(commits)} commit(s) la citan con {len(tests)} test(s)"
    return r


_FUSION = re.compile(r"^Fusiona impl/T\d{3,4}\b")
_REVERT = re.compile(r'^Revert "(.+)"$')


def vigentes(commits: list[dict]) -> list[dict]:
    """Bloque 21 (26/10): sin los commits deshechos por un 'Revert "<asunto>"' POSTERIOR (ni los propios reverts). T844
    se cerro sola con la fusion que la puerta habia revertido. `commits`: el mas reciente primero."""
    deshechos: dict[str, int] = {}
    salida = []
    for c in commits:
        m = _REVERT.match(c["asunto"])
        if m:
            deshechos[m.group(1)] = deshechos.get(m.group(1), 0) + 1
        elif deshechos.get(c["asunto"]):
            deshechos[c["asunto"]] -= 1
        else:
            salida.append(c)
    return salida


def _es_bug(t: dict) -> bool:
    return "bug" in (t.get("etiquetas") or []) or "tipo:bug" in (t.get("etiquetas") or []) \
        or str(t.get("titulo", "")).upper().startswith("BUG")


def _verificada(t: dict) -> bool:
    return bool(t.get("testeado")) or any("[verificado]" in str(n.get("texto", "")) for n in t.get("notas") or [])


def candidatas(por_tarea: dict | None = None, tareas: list[dict] | None = None) -> list[dict]:
    por_tarea = commits_por_tarea() if por_tarea is None else por_tarea
    tareas = T.cargar()["tareas"] if tareas is None else tareas
    return [evaluar(t, por_tarea[t["id"]]) for t in tareas if t.get("estado") in ABIERTAS and t["id"] in por_tarea]


# ================================================================ ejecucion
def ejecutar_tests(tests: list[str]) -> tuple[bool, str]:
    try:
        p = subprocess.run([str(PYTHON), "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests], cwd=REPO,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_TESTS)
    except subprocess.TimeoutExpired:
        return False, f"pytest tardo mas de {TIMEOUT_TESTS} s"
    lineas = [x for x in (p.stdout + p.stderr).strip().splitlines() if x.strip()]
    return p.returncode == 0, (lineas[-1] if lineas else f"codigo {p.returncode}")[:300]


def _cerrar(c: dict, salida: str) -> None:
    from nucleo import evidencias
    detalle = (f"Cierre automatico (nucleo.cierre_auto): el trabajo esta en principal, commit {c['commit']['sha']} "
               f"'{c['commit']['asunto'][:80]}'; sus tests ({', '.join(c['tests'])}) ejecutados ahora: {salida}")
    r = evidencias.cerrar(c["tid"], evidencia={"detalle": detalle, "tipo": "test",
                                               "comando": "pytest -q " + " ".join(c["tests"]), "salida": salida})
    if r.get("estado_real") not in ("HECHO Y TESTEADO",):
        raise RuntimeError(f"cerrada sin testear: {r.get('motivo', '')}"[:200])


def repasar(aplicar: bool = False, maximo: int = MAX_POR_PASADA, ejecutar=None, por_tarea=None, tareas=None) -> dict:
    ejecutar = ejecutar or ejecutar_tests
    res = {"cuando": datetime.now().isoformat(timespec="seconds"), "aplicar": aplicar, "cerradas": [],
           "cerrables": [], "dudosas": []}
    for c in candidatas(por_tarea, tareas):
        if c["decision"] != "cerrar":
            res["dudosas"].append(c)
            continue
        if not aplicar or len(res["cerradas"]) >= maximo:
            res["cerrables"].append(c)
            continue
        ok, salida = ejecutar(c["tests"])
        if not ok:
            res["dudosas"].append(dict(c, decision="dudosa", motivo=f"sus tests NO pasan ahora: {salida}"))
            continue
        try:
            _cerrar(c, salida)
        except Exception as e:  # noqa: BLE001  (RevisionPendiente, CierrePropuesta...: decide Claude)
            res["dudosas"].append(dict(c, decision="dudosa", motivo=f"no se pudo cerrar: {e}"[:300]))
            continue
        res["cerradas"].append(dict(c, salida=salida))
    if aplicar:
        CARPETA.mkdir(parents=True, exist_ok=True)
        escribir_atomico(CARPETA / "dudosas.json", json.dumps(res["dudosas"], ensure_ascii=False, indent=1))
        escribir_atomico(CARPETA / "ultimo.json", json.dumps({k: v for k, v in res.items() if k != "dudosas"}
                                                             | {"n_dudosas": len(res["dudosas"])},
                                                             ensure_ascii=False, indent=1))
        if res["cerradas"]:
            _avisar(res)
    return res


def _avisar(res: dict) -> None:
    try:
        from nucleo import avisos
        avisos.emitir("cierre_auto", f"Cerradas solas {len(res['cerradas'])} tarea(s) ya hechas",
                      ", ".join(c["tid"] for c in res["cerradas"]) + f". Dudosas para Claude: {len(res['dudosas'])}.",
                      ruta="/", clave=f"cierre_auto:{res['cuando'][:10]}", urgencia="normal")
    except Exception:
        pass


# ================================================================ planificador
def ultimo() -> dict | None:
    try:
        return json.loads((CARPETA / "ultimo.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def repaso_si_toca(ahora: datetime | None = None, lanzar=None) -> str | None:
    """Lo llama el planificador en cada tick. Una vez al dia lanza `aplicar` en un proceso aparte (ejecuta tests: no
    puede bloquear el tick). Devuelve lo que hizo o None."""
    ahora = ahora or datetime.now()
    u = ultimo()
    try:
        if u and ahora - datetime.fromisoformat(u["cuando"]) < CADA:
            return None
    except (KeyError, TypeError, ValueError):
        pass
    marca = CARPETA / "lanzado.json"
    try:
        if ahora - datetime.fromisoformat(json.loads(marca.read_text(encoding="utf-8"))["cuando"]) < CADA:
            return None                   # ya lanzado hoy (aun corriendo o fallo): no se relanza en cada tick
    except (OSError, ValueError, KeyError, TypeError):
        pass
    CARPETA.mkdir(parents=True, exist_ok=True)
    escribir_atomico(marca, json.dumps({"cuando": ahora.isoformat(timespec="seconds")}))
    lanzar = lanzar or LANZADOR or (lambda: subprocess.Popen([str(PYTHON), "-m", "nucleo.cierre_auto", "aplicar"], cwd=REPO,
                                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).pid)
    return f"lanzado cierre_auto (pid {lanzar()})"


def _cli(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    orden = argv[0] if argv else "simular"
    if orden == "dudosas":
        try:
            print(json.dumps(json.loads((CARPETA / "dudosas.json").read_text(encoding="utf-8")), ensure_ascii=False,
                             indent=1))
        except OSError:
            print("(sin dudosas guardadas: aun no ha corrido 'aplicar')")
        return 0
    if orden in ("simular", "aplicar"):
        maximo = int(argv[argv.index("--max") + 1]) if "--max" in argv else MAX_POR_PASADA
        r = repasar(aplicar=orden == "aplicar", maximo=maximo)
        for clave in ("cerradas", "cerrables", "dudosas"):
            print(f"== {clave} ({len(r[clave])})")
            for c in r[clave]:
                print(f"  {c['tid']}  {c['commit']['sha']}  {c['motivo'][:110]}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(_cli(sys.argv[1:]))
