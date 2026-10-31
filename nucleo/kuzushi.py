# -*- coding: utf-8 -*-
"""Kuzushi fase 1 (T1011, diseno documentacion/diseno/KUZUSHI_KAIZEN.md v3, apartado 6): observar SIN IA.

Cada noche (turno "kuzushi") mira lo que NEXO ya registra y deja HALLAZGOS, cada uno con su evidencia concreta (rutas,
IDs, numeros) y una huella para no repetirlo. No llama a ninguna IA ni manda nada fuera del PC; lo que guarda pasa
por auditor.tapar (lo ensena la web y viaja en el espejo).

Fuentes (tabla 1.1): tareas, implementador y puerta, turnos, prompts (T1021), proveedores y cuota, guardian, tests,
git, salud y, nuevo del 26/10, las DECISIONES AUTOMATICAS de NEXO: (a) cierres cuya evidencia (commit) se deshizo,
ya no existe o cuyos tests citados ya no pasan (T844, 25/10 21:41: cierre_auto la cerro con su propio Revert);
(b) aprobaciones del guardian que luego se denegaron o deshicieron; (c) rechazos de la puerta que eran
infraestructura (T844/T849, "la suite tardo mas de 1200 s").

Filtro y presupuesto (1.2): una huella ya vista no se vuelve a proponer (y lo descartado no vuelve nunca); la primera
semana todo va a la cola de calibracion de Claude (util / no util); despues, lo obvio con arreglo conocido pasa a
tarea (origen kuzushi, prioridad media salvo seguridad o perdida de datos), como mucho MAX_TAREAS_NOCHE por noche y
nunca con el freno F0 puesto; el resto, a memoria/kuzushi/espera.jsonl. Lo que toca a Kuzushi, el guardian, la
puerta, el tribunal, el riesgo, los permisos o el freno (ZONAS_R3) nunca es automatico: es un hallazgo para Claude.

CLI (.venv\\Scripts\\python.exe -m nucleo.kuzushi ...):
  observar [--simular]                     una pasada (lo que hace el turno); --simular no guarda nada
  hallazgos [estado]                       lista (calibrar, espera, claude, tarea, util, descartado, resuelto)
  calibrar Kxxxx util|no_util "motivo"     veredicto de Claude durante la calibracion
  resolver Kxxxx "motivo"                  Claude lo da por arreglado (reaparece solo si su evidencia cambia)
  resumen                                  el resumen semanal (el del Centro)
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from nucleo import tareas as T
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico

CARPETA = RAIZ / "memoria" / "kuzushi"
RAMA = "principal"
MAX_TAREAS_NOCHE = 3
DIAS_CALIBRACION = 7
PRIORIDAD_MEDIA, PRIORIDAD_GRAVE = 3, 4          # 1.4 (R2): no desplaza a las tareas de Damian
CATEGORIAS_GRAVES = ("seguridad", "perdida_datos")
ZONAS_R3 = ("kuzushi", "kaizen", "guardian", "puerta", "tribunal", "riesgo", "permisos", "freno")
ABIERTOS = ("calibrar", "util", "espera", "claude", "damian")
DIAS_VENTANA = 14
DIAS_CIERRES = 45
FORMATO = "%Y-%m-%d %H:%M:%S"
DESDE_CIERRE_V2 = "2026-10-18"       # T1010: desde entonces completar() exige cierre {estado_real, evidencia}
MAX_EJECUCIONES = 8                  # (a) juegos de tests citados que se ejecutan por noche (cierres de 7 dias)
MARGEN_TOPE = 15 * 60 + 120          # planificador.MARGEN_TOPE (le pide acabar) + 2 min para cerrar
_SHA = re.compile(r"\bcommit ([0-9a-f]{7,40})\b")
_REVERT = re.compile(r'^Revert "(.+)"$')
_TEST = re.compile(r"\b((?:interfaz/)?tests/(?:[\w.-]+/)*test_[\w.-]+\.py)")


# ================================================================ utilidades
def _ruta(nombre: str) -> Path:
    return CARPETA / nombre


def _leer_json(p: Path, defecto):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def _jsonl(p: Path) -> list[dict]:
    salida = []
    try:
        for linea in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                d = json.loads(linea)
            except ValueError:
                continue
            if isinstance(d, dict):
                salida.append(d)
    except OSError:
        pass
    return salida


def _fecha(texto) -> datetime | None:
    if not texto:
        return None
    s = str(texto).strip().replace("T", " ")[:19]
    for fmt in (FORMATO, "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:len(datetime.now().strftime(fmt))], fmt)
        except ValueError:
            continue
    return None


def _tapar(x):
    """Lo que Kuzushi guarda lo ensena la web y viaja en el espejo: todo texto pasa por auditor.tapar."""
    from nucleo import auditor
    if isinstance(x, str):
        return auditor.tapar(x)
    if isinstance(x, list):
        return [_tapar(v) for v in x]
    if isinstance(x, dict):
        return {k: _tapar(v) for k, v in x.items()}
    return x


def huella(fuente: str, tipo: str, clave: str) -> str:
    return hashlib.sha1(f"{fuente}|{tipo}|{clave}".encode("utf-8")).hexdigest()[:16]


def hallazgo(fuente: str, tipo: str, clave: str, titulo: str, evidencia: dict, gravedad: str = "media",
             categoria: str = "fiabilidad", zona: str = "", arreglo: str = "", propone: str = "", donde: str = "",
             para: str = "") -> dict:
    """Un hallazgo recien observado. `clave` es lo que lo hace unico (no lleva numeros que cambian de una noche a
    otra: la evidencia se refresca, la huella no). `arreglo` = el arreglo conocido (entonces es 'obvio')."""
    return {"huella": huella(fuente, tipo, clave), "fuente": fuente, "tipo": tipo, "clave": clave,
            "titulo": titulo[:140], "gravedad": gravedad, "categoria": categoria, "zona": zona,
            "evidencia": evidencia, "arreglo": arreglo, "propone": propone, "donde": donde, "para": para}


# ================================================================ fuentes (lo que ya registra NEXO)
class Fuentes:
    """Carga perezosa de cada fuente; los tests pasan las suyas por nombre (`Fuentes(tareas=[...], commits=[...])`)."""

    def __init__(self, ahora: datetime | None = None, **dadas):
        self.ahora = ahora or datetime.now()
        self._c = dict(dadas)
        self.errores: dict[str, str] = {}

    def _x(self, nombre: str, cargar, defecto):
        if nombre not in self._c:
            try:
                self._c[nombre] = cargar()
            except Exception as e:  # noqa: BLE001  (una fuente rota no tumba las demas)
                self.errores[nombre] = f"{type(e).__name__}: {e}"[:200]
                self._c[nombre] = defecto
        return self._c[nombre]

    # --- tareas
    @property
    def tareas(self) -> list[dict]:
        return self._x("tareas", lambda: T.cargar()["tareas"], [])

    @property
    def historial(self) -> list[dict]:
        def cargar():
            from nucleo import tareas_almacen
            return tareas_almacen.leer_historial(T.ALMACEN)[1]
        return self._x("historial", cargar, [])

    def notas(self, t: dict) -> list[dict]:
        """Las notas de la tarea con las antiguas de su detalle (tareas_detalle/<id>.json)."""
        cache = self._c.setdefault("_notas", {})
        if t["id"] not in cache:
            try:
                from nucleo import tareas_almacen
                antiguas = tareas_almacen.leer_detalle(T.ALMACEN, t["id"]).get("notas_antiguas") or []
            except Exception:  # noqa: BLE001
                antiguas = []
            cache[t["id"]] = [n for n in antiguas + list(t.get("notas") or []) if isinstance(n, dict)]
        return cache[t["id"]]

    @property
    def evidencias(self) -> list[dict]:
        return self._x("evidencias", lambda: _jsonl(RAIZ / "memoria" / "evidencias.jsonl"), [])

    # --- guardian y aprobaciones
    @property
    def aprobaciones(self) -> list[dict]:
        return self._x("aprobaciones", lambda: _leer_json(RAIZ / "memoria" / "aprobaciones.json", {}).get(
            "solicitudes") or [], [])

    @property
    def guardian(self) -> list[dict]:
        return self._x("guardian", lambda: _jsonl(RAIZ / "memoria" / "guardian_decisiones.jsonl"), [])

    # --- implementador y tests
    @property
    def implementador(self) -> dict[str, dict]:
        def cargar():
            salida = {}
            for p in sorted((RAIZ / "memoria" / "implementador").glob("T*.json")):
                d = _leer_json(p, None)
                if isinstance(d, dict):
                    salida[p.stem] = d
            return salida
        return self._x("implementador", cargar, {})

    @property
    def linea_base(self) -> dict:
        return self._x("linea_base", lambda: _leer_json(RAIZ / "memoria" / "implementador" / "linea_base.json", {}), {})

    # --- turnos, proveedores, avisos
    @property
    def turnos(self) -> list[dict]:
        def cargar():
            desde = (self.ahora - timedelta(days=DIAS_VENTANA)).strftime("%Y%m%d")
            salida = []
            for p in sorted((RAIZ / "registros").glob("turno_nexo_*.json")):
                if p.stem[11:19] >= desde:
                    d = _leer_json(p, None)
                    if isinstance(d, dict):
                        salida.append(dict(d, _archivo=f"registros/{p.name}"))
            return salida
        return self._x("turnos", cargar, [])

    @property
    def uso(self) -> list[dict]:
        def cargar():
            desde = (self.ahora - timedelta(days=DIAS_VENTANA)).isoformat()
            return [d for d in _jsonl(RAIZ / "registros" / "uso_proveedores.jsonl") if str(d.get("cuando")) >= desde]
        return self._x("uso", cargar, [])

    @property
    def avisos(self) -> list[dict]:
        def cargar():
            desde = (self.ahora - timedelta(days=7)).strftime("%Y%m%d")
            salida = []
            for p in (RAIZ / "memoria" / "avisos").glob("aviso_*.json"):
                if p.stem[6:14] >= desde:
                    d = _leer_json(p, None)
                    if isinstance(d, dict):
                        salida.append(d)
            return salida
        return self._x("avisos", cargar, [])

    @property
    def borradores(self) -> list[dict]:
        """Cabeceras de los borradores de los ultimos DIAS_VENTANA dias (llamadas y prompts por tarea, T1021)."""
        def cargar():
            desde = (self.ahora - timedelta(days=DIAS_VENTANA)).strftime("%Y%m%d")
            salida = []
            for p in (RAIZ / "memoria" / "borradores").glob("*.md"):
                m = re.search(r"_(\d{8})_\d{4}$", p.stem)
                if not m or m.group(1) < desde:
                    continue
                try:
                    cabeza = p.read_text(encoding="utf-8", errors="replace")[:1500]
                except OSError:
                    continue
                salida.append({"archivo": f"memoria/borradores/{p.name}", "texto": cabeza})
            return salida
        return self._x("borradores", cargar, [])

    # --- git
    @property
    def commits(self) -> list[dict]:
        """principal (primer padre), el mas reciente primero: {sha, fecha, asunto, archivos}."""
        return self._x("commits", lambda: leer_git(), [])

    def commit(self, sha: str) -> dict | None:
        idx = self._c.setdefault("_por_sha", {})
        if not idx:
            for i, c in enumerate(self.commits):
                idx[c["sha"][:7]] = idx.get(c["sha"][:7]) or []
                idx[c["sha"][:7]].append((i, c))
        for i, c in idx.get(sha[:7], []):
            if c["sha"].startswith(sha) or sha.startswith(c["sha"]):
                return dict(c, _pos=i)
        return None

    def existe_commit(self, sha: str) -> bool:
        """Fuera de principal: puede vivir en otra rama. Los tests lo pasan como `existe=lambda sha: ...`."""
        if "existe" in self._c:
            return self._c["existe"](sha)
        return bool(_git("cat-file", "-t", sha).strip())

    def ejecutar_tests(self, tests: list[str]) -> tuple[bool, str] | None:
        """(ok, ultima linea) de pytest sobre los tests citados; None si no se ejecutan (tope de la noche o dentro de
        la suite: un test nunca lanza un pytest real). Una vez por juego de tests y pasada."""
        cache = self._c.setdefault("_tests", {})
        clave = " ".join(sorted(tests))
        if clave in cache:
            return cache[clave]
        if "ejecutar" in self._c:
            fn = self._c["ejecutar"]
        elif "PYTEST_CURRENT_TEST" in __import__("os").environ:
            return None
        else:
            from nucleo import cierre_auto
            fn = cierre_auto.ejecutar_tests
        if sum(1 for v in cache.values() if v is not None) >= MAX_EJECUCIONES:
            return None
        cache[clave] = fn(sorted(tests))
        return cache[clave]

    def existe_archivo(self, rel: str) -> bool:
        if "existe_archivo" in self._c:
            return self._c["existe_archivo"](rel)
        return (RAIZ / rel).is_file()

    # --- salud
    @property
    def disco(self) -> dict:
        def cargar():
            u = shutil.disk_usage(RAIZ)
            return {"libre_gb": round(u.free / 2**30, 1), "total_gb": round(u.total / 2**30, 1)}
        return self._x("disco", cargar, {})

    @property
    def tamanos(self) -> dict:
        def cargar():
            reg = sum(p.stat().st_size for p in (RAIZ / "registros").glob("*") if p.is_file())
            avisos = sum(1 for _ in (RAIZ / "memoria" / "avisos").glob("aviso_*.json"))
            return {"registros_mb": round(reg / 2**20), "avisos_archivos": avisos}
        return self._x("tamanos", cargar, {})


def _git(*args) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=120,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout if r.returncode == 0 else ""


def leer_git(desde_dias: int = 120) -> list[dict]:
    sep_c, sep_f = "\x1e", "\x1f"
    salida = _git("log", RAMA, f"--since={desde_dias}.days", "--first-parent", "-m", "--name-only",
                  f"--format={sep_c}%H{sep_f}%ad{sep_f}%s", "--date=format:%Y-%m-%d %H:%M:%S")
    commits = []
    for bloque in salida.split(sep_c):
        if not bloque.strip():
            continue
        cabecera, _, resto = bloque.partition("\n")
        partes = cabecera.split(sep_f)
        if len(partes) < 3:
            continue
        commits.append({"sha": partes[0], "fecha": partes[1], "asunto": partes[2].strip(),
                        "archivos": [a.strip() for a in resto.splitlines() if a.strip()]})
    return commits


def _deshecho_por(f: Fuentes, c: dict) -> dict | None:
    """El 'Revert "<asunto>"' POSTERIOR a `c` en principal (si lo hay). Un revert del revert lo devuelve a la vida."""
    pos = c.get("_pos")
    if pos is None:
        return None
    vivos, ultimo = 0, None
    for otro in reversed(f.commits[:pos]):            # de mas antiguo a mas nuevo, solo los posteriores
        m = _REVERT.match(otro["asunto"])
        if m and m.group(1) == c["asunto"]:
            vivos += 1
            ultimo = otro
        elif m and m.group(1) == f'Revert "{c["asunto"]}"':
            vivos -= 1
    return ultimo if vivos > 0 else None


# ================================================================ observadores
def _vivas(f: Fuentes) -> list[dict]:
    return [t for t in f.tareas if t.get("estado") in T.VIVOS]


def _cerradas_recientes(f: Fuentes, dias: int) -> list[dict]:
    limite = f.ahora - timedelta(days=dias)
    salida = []
    for t in f.historial + [t for t in f.tareas if t.get("estado") in T.CERRADOS]:
        if not isinstance(t, dict) or not t.get("id"):
            continue
        c = _fecha(t.get("cerrada") or t.get("actualizada"))
        if c and c >= limite:
            salida.append(t)
    return salida


_RECHAZO = re.compile(r"(?i)puerta de fusion[^:]*: NO pasa|DESHECHA \(marcha atras|no lo consiguio|RECHAZAR:"
                      r"|veredicto[^.]{0,40}\b(DESCARTADO|REHACER)\b")
_INFRA = re.compile(r"(?i)la suite tardo mas de|timeout|FalloInfra|sin_suite|espera_suite|HTTP 5\d\d|saturad")
_INFRA_DESPUES = re.compile(r"(?i)infraestructura|no por (este|su) (cambio|codigo)|test ajeno|tiempos con el PC"
                            r"|fuga entre tests|no es de su codigo")


_DEVUELTA = "Vuelve a la cola del implementador"          # nota de piloto_serie.devolver


def obs_tareas(f: Fuentes) -> list[dict]:
    """Rebotan (>=2 rechazos), atascadas >7 dias, cerradas sin evidencia, duplicadas."""
    salida = []
    for t in _vivas(f):
        # Bloque 23: la nota de piloto_serie.devolver cita el motivo anterior ("...RECHAZAR: ...") y no es un rechazo
        rechazos = [n for n in f.notas(t) if _RECHAZO.search(str(n.get("texto", "")))
                    and not str(n.get("texto", "")).startswith(_DEVUELTA)]
        if len(rechazos) >= 2 and t.get("estado") != "propuesta":
            salida.append(hallazgo(
                "tareas", "rebota", t["id"], f"{t['id']} rebota: {len(rechazos)} rechazos y sigue abierta",
                {"tarea": t["id"], "rechazos": len(rechazos),
                 "fechas": [str(n.get("cuando", ""))[:16] for n in rechazos][-6:],
                 "ultimo": str(rechazos[-1].get("texto", ""))[:200]},
                gravedad="media", donde=f"memoria/tareas.json ({t['id']})"))
        if t.get("estado") in ("en_curso", "esperando"):
            act = _fecha(t.get("actualizada"))
            if act and (f.ahora - act).days > 7:
                salida.append(hallazgo(
                    "tareas", "atascada", t["id"],
                    f"{t['id']} lleva {(f.ahora - act).days} dias en '{t['estado']}' sin moverse",
                    {"tarea": t["id"], "estado": t["estado"], "actualizada": str(t.get("actualizada"))[:16]},
                    gravedad="baja", donde=f"memoria/tareas.json ({t['id']})"))
    for t in _cerradas_recientes(f, DIAS_VENTANA):
        if t.get("estado") != "hecha" or str(t.get("cerrada") or "") < DESDE_CIERRE_V2:
            continue                                  # antes del 18/10 el cierre no existia
        c = t.get("cierre") or {}
        if not str(c.get("evidencia") or "").strip() or c.get("estado_real") not in ("HECHO Y TESTEADO",
                                                                                      "HECHO SIN TESTEAR"):
            salida.append(hallazgo(
                "tareas", "cerrada_sin_evidencia", t["id"], f"{t['id']} se cerro como hecha sin evidencia",
                {"tarea": t["id"], "cerrada": str(t.get("cerrada"))[:16], "estado_real": c.get("estado_real")},
                gravedad="media", donde="memoria/tareas_historial.jsonl"))
    from nucleo import freno
    vivas = [(t, freno.palabras(t.get("titulo", ""))) for t in _vivas(f)]
    vivas = [(t, p) for t, p in vivas if len(p) >= 3]
    for i, (a, pa) in enumerate(vivas):
        for b, pb in vivas[i + 1:]:
            if freno.parecido(pa, pb) >= 0.8:
                salida.append(hallazgo(
                    "tareas", "duplicada", f"{a['id']}|{b['id']}", f"{a['id']} y {b['id']} parecen la misma tarea",
                    {"tareas": [a["id"], b["id"]], "parecido": round(freno.parecido(pa, pb), 2),
                     "titulos": [a.get("titulo", "")[:80], b.get("titulo", "")[:80]]},
                    gravedad="baja", donde="memoria/tareas.json"))
    return salida


def _cierres_con_commit(f: Fuentes) -> dict[tuple[str, str], dict]:
    """{(tarea, sha): {cuando, tests, quien, fuente}} de los cierres que citan un commit como evidencia."""
    limite = f.ahora - timedelta(days=DIAS_CIERRES)
    cierres: dict[tuple[str, str], dict] = {}

    def apuntar(tid, texto, cuando, fuente, comando=""):
        for sha in dict.fromkeys(_SHA.findall(texto or "")):
            c = cierres.setdefault((tid, sha), {"cuando": cuando, "tests": [], "fuente": fuente,
                                               "quien": "cierre_auto" if "Cierre automatico" in texto else "a mano"})
            c["tests"] = sorted(set(c["tests"]) | set(_TEST.findall(f"{texto} {comando}")))

    for e in f.evidencias:
        cuando = _fecha(e.get("t"))
        if e.get("tarea") and cuando and cuando >= limite:
            apuntar(e["tarea"], str(e.get("detalle", "")), str(e.get("t"))[:16], "memoria/evidencias.jsonl",
                    str(e.get("comando", "")))
    for t in f.tareas + _cerradas_recientes(f, DIAS_CIERRES):
        c = t.get("cierre") or {}
        if isinstance(c, dict) and c.get("evidencia"):
            apuntar(t["id"], str(c["evidencia"]), str(t.get("cerrada") or t.get("actualizada") or "")[:16],
                    "memoria/tareas.json" if t in f.tareas else "memoria/tareas_historial.jsonl")
    return cierres


def _estado_tarea(f: Fuentes, tid: str) -> dict | None:
    for t in f.tareas:
        if t.get("id") == tid:
            return t
    for t in reversed(f.historial):
        if t.get("id") == tid:
            return t
    return None


def obs_decisiones(f: Fuentes) -> list[dict]:
    """Decisiones automaticas de NEXO que luego resultaron equivocadas (a, b, c del 26/10)."""
    salida = []
    # (a) cierres cuya evidencia se deshizo, ya no existe o cuyos tests ya no pasan
    for (tid, sha), cierre in sorted(_cierres_con_commit(f).items()):
        t = _estado_tarea(f, tid)
        if not t:
            continue
        c = f.commit(sha)
        problemas = []
        if c is None:
            if not f.existe_commit(sha):
                problemas.append(f"el commit {sha} ya no existe")
        else:
            m = _REVERT.match(c["asunto"])
            if m:
                problemas.append(f"el commit {sha[:10]} es el Revert de '{m.group(1)[:70]}': la fusion se deshizo")
            deshecho = _deshecho_por(f, c)
            if deshecho:
                problemas.append(f"el commit {sha[:10]} se deshizo despues en {deshecho['sha'][:10]} "
                                 f"({deshecho['fecha'][:16]})")
        faltan = [x for x in cierre["tests"] if not f.existe_archivo(x)]
        if faltan:
            problemas.append("sus tests citados ya no existen: " + ", ".join(faltan[:4]))
        vivos = [x for x in cierre["tests"] if x not in faltan]
        reciente = (_fecha(cierre["cuando"]) or datetime.min) >= f.ahora - timedelta(days=7)
        if vivos and reciente and t.get("estado") in T.CERRADOS:
            r = f.ejecutar_tests(vivos)
            if r is not None and not r[0]:
                problemas.append(f"sus tests citados NO pasan ahora ({' '.join(vivos)[:120]}): {r[1][:160]}")
        if not problemas:
            continue
        cerrada = t.get("estado") in T.CERRADOS
        real = (t.get("cierre") or {}).get("estado_real", "")
        if not cerrada and not str(real).startswith("HECHO"):
            continue                                  # reabierta y sin cierre viejo: ya esta arreglado
        ev = {"tarea": tid, "estado_ahora": t.get("estado"), "commit": sha[:10], "cerrada_por": cierre["quien"],
              "cuando": cierre["cuando"], "fuente": cierre["fuente"], "problemas": problemas,
              "tests_citados": cierre["tests"][:5]}
        if c is not None:
            ev["asunto"] = c["asunto"][:120]
        if cerrada:
            salida.append(hallazgo(
                "decisiones", "cierre_sin_evidencia_viva", f"{tid}:{sha[:10]}",
                f"{tid} esta cerrada como {real or 'hecha'} pero su evidencia ya no vale", ev, gravedad="grave",
                arreglo=f"reabrir {tid} y quitarle el cierre: su evidencia (commit {sha[:10]}) no esta en principal",
                propone=f"reabrir {tid}", donde=f"memoria/tareas_historial.jsonl ({tid})"))
        else:
            salida.append(hallazgo(
                "decisiones", "cierre_rancio", f"{tid}:{sha[:10]}",
                f"{tid} se reabrio pero conserva el cierre '{real}' de una evidencia que no vale", ev,
                gravedad="media", arreglo=f"quitar a {tid} el cierre viejo (cita el commit {sha[:10]})",
                propone=f"limpiar el cierre de {tid}", donde=f"memoria/tareas.json ({tid})"))
    # (a2) cerradas cuyos commits (los que la citan en el asunto) se deshicieron, aunque el cierre no cite el sha.
    # No se usa cierre_auto.vigentes: toma un 'Revert "Revert ..."' (la fusion que vuelve) por otro revert.
    por_tarea: dict[str, list[dict]] = defaultdict(list)
    for c in f.commits:
        for tid in dict.fromkeys(re.findall(r"\bT\d{3,4}\b", c["asunto"])):
            por_tarea[tid].append(c)
    vistos = {h["evidencia"]["tarea"] for h in salida}
    for t in _cerradas_recientes(f, DIAS_CIERRES):
        tid = t["id"]
        commits = por_tarea.get(tid) or []
        if t.get("estado") != "hecha" or tid in vistos or not commits:
            continue
        reales = [f.commit(c["sha"]) for c in commits if not _REVERT.match(c["asunto"])]
        if reales and all(c is not None and _deshecho_por(f, c) for c in reales):
            salida.append(hallazgo(
                "decisiones", "cerrada_con_fusion_deshecha", tid,
                f"{tid} esta cerrada pero el ultimo commit que la cita es un revert",
                {"tarea": tid, "cerrada": str(t.get("cerrada"))[:16], "ultimo_commit": commits[0]["sha"][:10],
                 "asunto": commits[0]["asunto"][:120]}, gravedad="grave",
                arreglo=f"reabrir {tid}: su cambio no esta en principal", propone=f"reabrir {tid}",
                donde="memoria/tareas_historial.jsonl"))
    # (b) aprobaciones automaticas (guardian/tribunal) que luego se denegaron o deshicieron
    por_huella: dict[str, list[dict]] = defaultdict(list)
    for s in f.aprobaciones:
        por_huella[s.get("huella", "")].append(s)
    for s in f.aprobaciones:
        ev = s.get("eventos") or []
        auto = next((e for e in ev if e.get("tipo") in ("aprobada", "aprobada_por_silencio")
                     and e.get("quien") in ("guardian", "tribunal")), None)
        if not auto:
            continue
        despues = [e for e in ev if e.get("cuando", "") >= auto.get("cuando", "")
                   and e.get("tipo") in ("denegada", "revocada", "deshecha", "vetada", "veto_deshecho")]
        otras = [o["id"] for o in por_huella.get(s.get("huella", ""), []) if o is not s
                 and o.get("estado") == "denegada" and o.get("creada", "") >= s.get("creada", "")]
        if despues or otras:
            salida.append(hallazgo(
                "decisiones", "aprobacion_automatica_deshecha", s["id"],
                f"{s['id']}: la aprobo el {auto.get('quien')} y despues se denego o deshizo",
                {"solicitud": s["id"], "accion": s.get("accion"), "aprobada": auto.get("cuando"),
                 "despues": [f"{e.get('cuando')} {e.get('tipo')} ({e.get('quien')})" for e in despues][:3],
                 "misma_accion_denegada": otras[:3]},
                gravedad="grave", categoria="seguridad", zona="guardian", donde="memoria/aprobaciones.json"))
    # (c) rechazos de la puerta (o marchas atras) que eran infraestructura
    for t in _vivas(f) + _cerradas_recientes(f, DIAS_CIERRES):
        notas = f.notas(t)
        casos = []
        es_rechazo = [bool(re.search(r"(?i)puerta de fusion[^:]*: NO pasa|DESHECHA \(marcha atras",
                                     str(n.get("texto", "")))) for n in notas]
        for i, n in enumerate(notas):
            texto = str(n.get("texto", ""))
            if not es_rechazo[i]:
                continue
            ya = _INFRA.search(texto)
            luego = None                              # la explicacion es de ESTE rechazo: antes del siguiente
            for j in range(i + 1, len(notas)):
                if es_rechazo[j]:
                    break
                if _INFRA_DESPUES.search(str(notas[j].get("texto", ""))):
                    luego = notas[j]
                    break
            if ya or luego:
                casos.append({"rechazo": str(n.get("cuando", ""))[:16], "motivo": texto[:160],
                              "por_que_infra": (ya.group(0) if ya else str(luego.get("texto", ""))[:160])})
        if casos:
            salida.append(hallazgo(
                "decisiones", "rechazo_puerta_infra", t["id"],
                f"{t['id']}: la puerta la rechazo {len(casos)} vez/veces por infraestructura, no por su codigo",
                {"tarea": t["id"], "casos": casos[-4:]}, gravedad="media", zona="puerta",
                donde="nucleo/puerta.py, nucleo/implementador.py"))
    return salida


_CAUSAS = (("tests ajenos en rojo", re.compile(r"(?i)ya fallaban|ajeno|suite en rojo en la rama: FAILED")),
           ("suite sin resultado (tiempo)", re.compile(r"(?i)tardo mas de|timeout|sin_suite")),
           ("modelo vacio o sintaxis rota", re.compile(r"(?i)vaci[oa]|sintaxis|SyntaxError|sin bloques|no devolvio")),
           ("contrato o solo lectura", re.compile(r"(?i)SOLO LECTURA|contrato|especificaci")),
           ("proveedor caido", re.compile(r"(?i)HTTP 5\d\d|saturad|429|cuota")))


def obs_implementador(f: Fuentes) -> list[dict]:
    """Fallos repetidos del implementador/puerta agrupados por causa, y tareas que fallan una y otra vez."""
    salida = []
    limite = f.ahora - timedelta(days=30)
    por_causa: dict[str, list[str]] = defaultdict(list)
    for t in _vivas(f) + _cerradas_recientes(f, 30):
        for n in f.notas(t):
            texto = str(n.get("texto", ""))
            cuando = _fecha(n.get("cuando"))
            if not cuando or cuando < limite or not re.search(r"(?i)^(puerta de fusion|implementador)", texto):
                continue
            if not _RECHAZO.search(texto) and "no pasa" not in texto.lower():
                continue
            for causa, patron in _CAUSAS:
                if patron.search(texto):
                    por_causa[causa].append(f"{t['id']} {str(n.get('cuando'))[:10]}")
                    break
    for causa, casos in por_causa.items():
        if len(casos) >= 3:
            salida.append(hallazgo(
                "implementador", "causa_repetida", causa, f"Implementador/puerta: '{causa}' {len(casos)} veces en 30 dias",
                {"causa": causa, "veces": len(casos), "casos": casos[-8:]}, gravedad="media",
                zona="puerta" if causa.startswith(("tests", "suite")) else "",
                donde="nucleo/implementador.py, nucleo/puerta.py"))
    for tid, r in f.implementador.items():
        fallidos = [i for i in r.get("intentos") or [] if not i.get("ok")]
        if r.get("estado") == "fallido" or len(fallidos) >= 3:
            salida.append(hallazgo(
                "implementador", "tarea_que_falla", tid,
                f"{tid}: el implementador fallo {len(fallidos)} intento(s) (estado {r.get('estado')})",
                {"tarea": tid, "estado": r.get("estado"), "motivo": str(r.get("motivo", ""))[:200],
                 "modelos": [i.get("modelo") for i in fallidos][-4:], "informe": f"memoria/implementador/{tid}.json"},
                gravedad="baja", donde=f"memoria/implementador/{tid}.json"))
    return salida


def obs_tests(f: Fuentes) -> list[dict]:
    """Tests en rojo en la linea base varios commits seguidos (dependen del entorno: en el worktree no existen los
    datos privados ni el entorno del PC) y tests intermitentes (rojo, verde, rojo)."""
    salida = []
    lb = sorted(((k, v) for k, v in (f.linea_base or {}).items() if isinstance(v, dict)),
                key=lambda kv: kv[1].get("_orden", 0))
    if lb:
        historia: dict[str, list[bool | None]] = defaultdict(list)
        ids = {k for _, v in lb for k in v if not k.startswith("_")}
        for _, v in lb:
            for i in ids:
                historia[i].append(v.get(i))
        seguidos = {i for i, h in historia.items() if len(h) >= 2 and h[-1] is True and h[-2] is True}
        por_archivo: dict[str, list[str]] = defaultdict(list)
        for i in sorted(seguidos):
            por_archivo[i.split("::")[0]].append(i.split("::", 1)[-1])
        for archivo, nombres in sorted(por_archivo.items()):
            ids_archivo = [f"{archivo}::{n}" if n != archivo else archivo for n in nombres]
            en_rojo = [sha for sha, v in lb if any(v.get(i) is True for i in ids_archivo)]
            salida.append(hallazgo(
                "tests", "rojo_en_linea_base", archivo,
                f"{archivo}: {len(nombres)} test(s) en rojo en la linea base de principal varios commits seguidos",
                {"archivo": archivo, "tests": nombres[:6], "desde_commit": en_rojo[0][:10],
                 "ultimo_commit": lb[-1][0][:10], "commits_en_rojo": len(en_rojo)},
                gravedad="media", categoria="fiabilidad",
                arreglo="que no dependan del entorno: en el worktree de la linea base (sparse-checkout) no hay datos "
                        "privados, procesos reales ni el cwd de principal (regla de T1027)", donde=archivo))
        for i, h in historia.items():
            vals = [x for x in h if x is not None]
            if any(a is True and b is False and c is True for a, b, c in zip(vals, vals[1:], vals[2:])):
                salida.append(hallazgo(
                    "tests", "intermitente", i, f"{i.split('::')[-1]}: rojo, verde y rojo otra vez en la linea base",
                    {"test": i, "historia": ["rojo" if x else "verde" if x is False else "-" for x in h][-8:]},
                    gravedad="media", arreglo="buscar la dependencia de tiempo, orden o entorno del test",
                    donde=i.split("::")[0]))
    ajenos: dict[str, set[str]] = defaultdict(set)
    for t in _vivas(f) + _cerradas_recientes(f, 30):
        for n in f.notas(t):
            for test in re.findall(r"FAILED ((?:interfaz/)?tests/[\w/.-]+\.py::\w+)", str(n.get("texto", ""))):
                ajenos[test].add(t["id"])
    for test, tids in ajenos.items():
        if len(tids) >= 2:
            salida.append(hallazgo(
                "tests", "tumba_a_la_puerta", test, f"{test.split('::')[-1]} tumbo la puerta en {len(tids)} tareas distintas",
                {"test": test, "tareas": sorted(tids)}, gravedad="media", zona="puerta",
                donde=test.split("::")[0]))
    return salida


def obs_turnos(f: Fuentes) -> list[dict]:
    """Turnos que pasan el tope, que fallan igual una y otra vez o que arrancan y no producen nada."""
    salida = []
    por_turno: dict[str, list[dict]] = defaultdict(list)
    for r in f.turnos:
        por_turno[r.get("turno_id") or r.get("plantilla") or "?"].append(r)
    for tid, regs in por_turno.items():
        nombre = regs[-1].get("nombre_turno") or tid
        corridos = [r for r in regs if not r.get("abortado")]
        tope = [r for r in corridos if (r.get("duracion_s") or 0) > (r.get("max_minutos") or 999) * 60 + MARGEN_TOPE]
        if tope:
            salida.append(hallazgo(
                "turnos", "pasa_el_tope", tid, f"Turno '{nombre}' paso su tope de minutos {len(tope)} vez/veces",
                {"turno": tid, "veces": len(tope), "registros": [r["_archivo"] for r in tope if "_archivo" in r][-3:],
                 "duraciones_min": [round(r["duracion_s"] / 60) for r in tope][-3:],
                 "tope_min": tope[-1].get("max_minutos")}, gravedad="media", donde="nucleo/planificador.py"))
        errores = Counter()
        for r in corridos:
            for paso, v in (r.get("pasos") or {}).items():
                if isinstance(v, dict) and v.get("error"):
                    errores[f"{paso}: {str(v['error'])[:70]}"] += 1
        for error, n in errores.items():
            if n >= 2:
                salida.append(hallazgo(
                    "turnos", "error_repetido", f"{tid}:{error[:40]}", f"Turno '{nombre}': el mismo error {n} veces",
                    {"turno": tid, "error": error, "veces": n, "dias": DIAS_VENTANA}, gravedad="media",
                    donde="turno_nexo.py"))
        vacios = [r for r in corridos if r.get("silencioso") or ("trabajo" in (r.get("pasos") or {})
                  and not any(x.get("archivo") for x in (r["pasos"]["trabajo"] or {}).get("filas") or []))]
        if len(corridos) >= 5 and len(vacios) >= 0.8 * len(corridos):
            salida.append(hallazgo(
                "turnos", "no_produce", tid, f"Turno '{nombre}': {len(vacios)} de {len(corridos)} pasadas sin producir nada",
                {"turno": tid, "corridos": len(corridos), "vacios": len(vacios), "dias": DIAS_VENTANA},
                gravedad="baja", donde="memoria/turnos_config.json"))
    sin_cerrar = [a for a in f.avisos if a.get("tipo") == "turno_sin_cerrar" or "sin cerrar" in str(a.get("titulo", ""))]
    if sin_cerrar:
        salida.append(hallazgo(
            "turnos", "turno_sin_cerrar", "planificador", f"{len(sin_cerrar)} aviso(s) de turno que no se pudo cerrar en 7 dias",
            {"avisos": [str(a.get("cuando")) for a in sin_cerrar][-5:]}, gravedad="media",
            donde="nucleo/planificador.py"))
    return salida


def obs_proveedores(f: Fuentes) -> list[dict]:
    """Proveedores con muchos fallos (>=30 % de >=10 envios en la ventana) y lo que cuesta cada respuesta util."""
    salida = []
    por: dict[str, list[dict]] = defaultdict(list)
    for u in f.uso:
        por[str(u.get("proveedor"))].append(u)
    for prov, filas in por.items():
        malos = [u for u in filas if str(u.get("estado")).upper() != "OK"]
        if len(filas) >= 10 and len(malos) / len(filas) >= 0.3:
            ok = len(filas) - len(malos)
            salida.append(hallazgo(
                "proveedores", "falla_mucho", prov,
                f"{prov}: {round(100 * len(malos) / len(filas))} % de envios fallidos en {DIAS_VENTANA} dias",
                {"proveedor": prov, "envios": len(filas), "fallidos": len(malos),
                 "estados": dict(Counter(str(u.get("estado")) for u in malos).most_common(4)),
                 "caracteres_por_ok": round(sum(u.get("entrada") or 0 for u in filas) / ok) if ok else None},
                gravedad="baja", categoria="coste", donde="nucleo/fallos.py, nucleo/enfriamiento.py"))
    return salida


def obs_guardian(f: Fuentes) -> list[dict]:
    """Lo que llega a Damian por el mismo motivo una y otra vez (>=3 en la ventana): ¿podia decidirse solo?"""
    limite = f.ahora - timedelta(days=DIAS_VENTANA)
    grupos: dict[tuple, list[dict]] = defaultdict(list)
    for d in f.guardian:
        cuando = _fecha(d.get("cuando"))
        if d.get("decision") == "damian" and cuando and cuando >= limite:
            grupos[(d.get("accion"), d.get("regla"), d.get("motivo"))].append(d)
    salida = []
    for (accion, regla, motivo), ds in grupos.items():
        if len(ds) >= 3:
            salida.append(hallazgo(
                "guardian", "a_damian_repetido", f"{accion}|{regla}|{motivo}",
                f"Guardian: {len(ds)} solicitudes '{accion}' a Damian por '{motivo}'",
                {"accion": accion, "regla": regla, "motivo": motivo, "solicitudes": [d.get("id") for d in ds][-6:]},
                gravedad="baja", categoria="carga_damian", zona="guardian", donde="nucleo/guardian.py"))
    return salida


def obs_git(f: Fuentes) -> list[dict]:
    """Reversiones en principal y archivos que necesitan arreglos una y otra vez (>=3 en 30 dias)."""
    salida = []
    limite = (f.ahora - timedelta(days=30)).strftime(FORMATO)
    recientes = [c for c in f.commits if c["fecha"] >= limite]
    for c in recientes:
        m = _REVERT.match(c["asunto"])
        if m:
            salida.append(hallazgo(
                "git", "revert", c["sha"][:10], f"Se deshizo '{m.group(1)[:80]}'",
                {"commit": c["sha"][:10], "fecha": c["fecha"][:16], "deshace": m.group(1)[:120],
                 "tareas": re.findall(r"\bT\d{3,4}\b", m.group(1))}, gravedad="baja", donde="git log principal"))
    arreglos: dict[str, list[str]] = defaultdict(list)
    for c in recientes:
        if re.search(r"(?i)\b(arregl|corrig|fix|bug)", c["asunto"]):
            for a in c["archivos"]:
                if a.endswith(".py") and not a.startswith(("tests/", "interfaz/tests/", "memoria/")):
                    arreglos[a].append(c["sha"][:10])
    for archivo, shas in arreglos.items():
        if len(shas) >= 3:
            salida.append(hallazgo(
                "git", "se_rompe_otra_vez", archivo, f"{archivo}: {len(shas)} arreglos en 30 dias",
                {"archivo": archivo, "commits": shas[:6]}, gravedad="media", donde=archivo,
                zona=next((z for z in ZONAS_R3 if z in archivo), "")))
    return salida


def obs_salud(f: Fuentes, previo: dict | None = None) -> list[dict]:
    """Tendencias (lo urgente lo avisa nucleo/avisos al momento): disco, registros que crecen sin rotar, avisos
    que se repiten."""
    salida = []
    d = f.disco
    if d.get("total_gb") and d["libre_gb"] / d["total_gb"] < 0.12:
        salida.append(hallazgo("salud", "disco_justo", "disco", f"Disco: quedan {d['libre_gb']} GB libres",
                               dict(d), gravedad="media", donde="nucleo/vigia_disco.py"))
    antes = (previo or {}).get("disco_hace_7") or {}
    if antes.get("libre_gb") and d.get("libre_gb") and antes["libre_gb"] - d["libre_gb"] > 20:
        salida.append(hallazgo("salud", "disco_baja_rapido", "disco_7d",
                               f"Disco: {round(antes['libre_gb'] - d['libre_gb'])} GB menos en 7 dias",
                               {"antes": antes, "ahora": d}, gravedad="media", donde="registros/, memoria/"))
    tam = f.tamanos
    if (tam.get("registros_mb") or 0) > 1024:
        salida.append(hallazgo("salud", "registros_grandes", "registros", f"registros/ ocupa {tam['registros_mb']} MB",
                               dict(tam), gravedad="baja", arreglo="rotar o archivar en _archivo/ los registros viejos",
                               donde="registros/"))
    if (tam.get("avisos_archivos") or 0) > 3000:
        salida.append(hallazgo("salud", "avisos_sin_rotar", "avisos", f"memoria/avisos tiene {tam['avisos_archivos']} archivos",
                               dict(tam), gravedad="baja", arreglo="archivar los avisos ya leidos de mas de 30 dias",
                               donde="nucleo/avisos.py"))
    por_tipo = Counter(str(a.get("tipo")) for a in f.avisos)
    for tipo, n in por_tipo.items():
        if n >= 15:
            salida.append(hallazgo("salud", "aviso_repetido", tipo, f"Aviso '{tipo}': {n} en 7 dias",
                                   {"tipo": tipo, "veces": n}, gravedad="baja", donde="memoria/avisos/"))
    return salida


# ---------------------------------------------------------------- T1021: prompts que salen hacia las IAs
ARCHIVOS_PROMPTS = ("nucleo/*.py", "extremidades/*.py", "roles/*.md", "proveedores.py", "router.py")
_PIDE = re.compile(r"(?i)\b(responde|escribe|devuelve|eres|tu tarea|explica|resume|revisa|eval[uú]a|elige|"
                   r"redacta|analiza|contesta|lee este|di si)\b")
_RESTRICCION = re.compile(r"(?i)(m[aá]ximo|como mucho|menos de|no m[aá]s de|hasta)\s+\d+\s*(palabras|frases|lineas|"
                          r"l[ií]neas|caracteres|puntos|propuestas|p[aá]rrafos)|\b\d+\s*-\s*\d+\s+palabras\b|"
                          r"\bUNA (sola )?frase\b|\b\d+ o \d+ frases\b")
_MIN_PROMPT = 200


def _textos_py(ruta: Path) -> list[tuple[int, str, str]]:
    """(linea, nombre, texto) de las cadenas largas de un .py (sin docstrings); las f-strings, por sus trozos fijos."""
    try:
        arbol = ast.parse(ruta.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError, ValueError):
        return []
    docs = set()
    for n in ast.walk(arbol):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body \
                and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant):
            docs.add(id(n.body[0].value))
    nombres = {}
    for n in ast.walk(arbol):
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            nombres[id(n.value)] = n.targets[0].id
    salida, dentro = [], set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.JoinedStr):
            texto = "".join(v.value for v in n.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
            dentro.update(id(v) for v in n.values)
            if len(texto) >= _MIN_PROMPT:
                salida.append((n.lineno, nombres.get(id(n), ""), texto))
    for n in ast.walk(arbol):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs and id(n) not in dentro \
                and len(n.value) >= _MIN_PROMPT:
            salida.append((n.lineno, nombres.get(id(n), ""), n.value))
    return salida


def inventario_prompts(raiz: Path | None = None) -> list[dict]:
    raiz = raiz or RAIZ
    salida = []
    for patron in ARCHIVOS_PROMPTS:
        for ruta in sorted(raiz.glob(patron)):
            rel = ruta.relative_to(raiz).as_posix()
            if rel == "nucleo/kuzushi.py":
                continue
            textos = ([(1, ruta.stem, ruta.read_text(encoding="utf-8", errors="replace"))] if ruta.suffix == ".md"
                      else _textos_py(ruta))
            for linea, nombre, texto in textos:
                if ruta.suffix == ".py" and not _PIDE.search(texto):
                    continue
                salida.append({"archivo": rel, "linea": linea, "nombre": nombre, "caracteres": len(texto),
                               "restricciones": sorted({m.group(0) for m in _RESTRICCION.finditer(texto)})[:5],
                               "_texto": texto})
    return salida


def _frases(texto: str) -> set[str]:
    return {" ".join(s.lower().split()) for s in re.split(r"(?<=[.:;!?])\s+|\n+", texto) if len(s.strip()) >= 60}


def medir_prompts(f: Fuentes, raiz: Path | None = None) -> dict:
    """T1021, primer encargo: SOLO medir y listar (no cambia ningun prompt). Plantillas por archivo con su tamano y
    sus restricciones numericas, frases repetidas entre plantillas (contexto repetido), tamano real de lo enviado
    por proveedor (registros/uso_proveedores.jsonl) y llamadas por tarea (cabeceras de los borradores)."""
    inv = inventario_prompts(raiz)
    donde_frase: dict[str, set[str]] = defaultdict(set)
    for p in inv:
        for fr in _frases(p["_texto"]):
            donde_frase[fr].add(f"{p['archivo']}:{p['linea']}")
    repetidas = sorted(((fr, sorted(sitios)) for fr, sitios in donde_frase.items()
                        if len({s.split(':')[0] for s in sitios}) >= 2), key=lambda x: -len(x[1]))
    por_prov: dict[str, list[int]] = defaultdict(list)
    for u in f.uso:
        if isinstance(u.get("entrada"), int):
            por_prov[str(u.get("proveedor"))].append(u["entrada"])

    def pct(xs, q):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0
    enviado = {p: {"envios": len(xs), "mediana": pct(xs, 0.5), "p90": pct(xs, 0.9), "maximo": max(xs)}
               for p, xs in sorted(por_prov.items())}
    llamadas = []
    for b in f.borradores:
        m = re.search(r"(\d+) llamadas web", b["texto"])
        m2 = re.search(r"c_prompt: (\d+) prompts", b["texto"])
        if m or m2:
            llamadas.append({"borrador": b["archivo"], "llamadas_web": int(m.group(1)) if m else None,
                             "prompts": int(m2.group(1)) if m2 else None})
    llamadas.sort(key=lambda x: -(x["prompts"] or x["llamadas_web"] or 0))
    return {"cuando": f.ahora.strftime(FORMATO), "plantillas": [{k: v for k, v in p.items() if k != "_texto"}
                                                                  for p in sorted(inv, key=lambda p: -p["caracteres"])],
            "repetidas": [{"frase": fr[:160], "sitios": s} for fr, s in repetidas[:20]],
            "enviado_por_proveedor": enviado, "llamadas_por_tarea": llamadas[:15],
            "nota": "Solo medicion (T1021 dentro de Kuzushi fase 1): no se ha cambiado ningun prompt."}


def obs_prompts(f: Fuentes, raiz: Path | None = None, guardar: bool = False) -> list[dict]:
    m = medir_prompts(f, raiz)
    if guardar:
        CARPETA.mkdir(parents=True, exist_ok=True)
        escribir_atomico(_ruta("T1021_prompts.json"), json.dumps(_tapar(m), ensure_ascii=False, indent=1))
    salida = []
    for p in m["plantillas"]:
        zona = next((z for z in ZONAS_R3 if z in p["archivo"]), "")
        if p["restricciones"]:
            salida.append(hallazgo(
                "prompts", "restriccion_numerica", f"{p['archivo']}:{p['nombre'] or p['linea']}",
                f"Prompt de {p['archivo']}:{p['linea']} con restriccion fija: {', '.join(p['restricciones'])[:60]}",
                {"archivo": p["archivo"], "linea": p["linea"], "nombre": p["nombre"], "caracteres": p["caracteres"],
                 "restricciones": p["restricciones"], "tarea": "T1021"}, gravedad="baja", categoria="coste",
                zona=zona, donde=f"{p['archivo']}:{p['linea']}"))
        if p["caracteres"] >= 2500:
            salida.append(hallazgo(
                "prompts", "plantilla_larga", f"{p['archivo']}:{p['nombre'] or p['linea']}",
                f"Plantilla de prompt de {p['caracteres']} caracteres en {p['archivo']}:{p['linea']}",
                {"archivo": p["archivo"], "linea": p["linea"], "nombre": p["nombre"], "caracteres": p["caracteres"],
                 "tarea": "T1021"}, gravedad="baja", categoria="coste", zona=zona, donde=f"{p['archivo']}:{p['linea']}"))
    for r in m["repetidas"][:10]:
        salida.append(hallazgo(
            "prompts", "contexto_repetido", r["frase"][:80], f"La misma frase de prompt en {len(r['sitios'])} sitios",
            {"frase": r["frase"], "sitios": r["sitios"][:6], "tarea": "T1021"}, gravedad="baja", categoria="coste",
            donde=", ".join(r["sitios"][:3])))
    for prov, e in m["enviado_por_proveedor"].items():
        if e["envios"] >= 10 and e["p90"] >= 20000:
            salida.append(hallazgo(
                "prompts", "envio_grande", prov, f"{prov}: el 10 % de los prompts pasa de {e['p90']} caracteres",
                dict(e, proveedor=prov, tarea="T1021"), gravedad="baja", categoria="coste",
                donde="registros/uso_proveedores.jsonl"))
    return salida


OBSERVADORES = (("tareas", obs_tareas), ("decisiones", obs_decisiones), ("implementador", obs_implementador),
                ("tests", obs_tests), ("turnos", obs_turnos), ("proveedores", obs_proveedores),
                ("guardian", obs_guardian), ("git", obs_git), ("salud", obs_salud), ("prompts", obs_prompts))


# ================================================================ registro, filtro y presupuesto
def cargar() -> dict:
    d = _leer_json(_ruta("hallazgos.json"), {})
    return {"siguiente": int(d.get("siguiente") or 1), "hallazgos": [h for h in d.get("hallazgos") or []
                                                                      if isinstance(h, dict)]}


def estado() -> dict:
    return _leer_json(_ruta("estado.json"), {})


def _guardar(reg: dict, est: dict) -> None:
    CARPETA.mkdir(parents=True, exist_ok=True)
    escribir_atomico(_ruta("hallazgos.json"), json.dumps(reg, ensure_ascii=False, indent=1))
    escribir_atomico(_ruta("estado.json"), json.dumps(est, ensure_ascii=False, indent=1))
    espera = [h for h in reg["hallazgos"] if h["estado"] == "espera"]
    escribir_atomico(_ruta("espera.jsonl"), "".join(json.dumps(h, ensure_ascii=False) + "\n" for h in espera))


def calibrando(est: dict, ahora: datetime) -> bool:
    hasta = _fecha(est.get("calibracion_hasta"))
    return hasta is None or ahora < hasta


def _pasar(h: dict, estado_nuevo: str, motivo: str, ahora: datetime) -> None:
    if h.get("estado") != estado_nuevo:
        h["estado"] = estado_nuevo
        h.setdefault("historial", []).append({"cuando": ahora.strftime(FORMATO), "estado": estado_nuevo,
                                              "motivo": motivo[:200]})
        h["historial"] = h["historial"][-12:]


def _crear_tarea(h: dict) -> str:
    prioridad = PRIORIDAD_GRAVE if h.get("categoria") in CATEGORIAS_GRAVES else PRIORIDAD_MEDIA
    ev = json.dumps(h.get("evidencia") or {}, ensure_ascii=False)[:900]
    t = T.anadir(
        f"Kuzushi {h['id']}: {h['titulo']}"[:80],
        detalle=(f"QUE: {h['arreglo']}\nDONDE: {h.get('donde') or '-'}\nPOR QUE (hallazgo {h['id']} de Kuzushi, "
                 f"fuente {h['fuente']}/{h['tipo']}, gravedad {h['gravedad']}): {h['titulo']}\nEVIDENCIA: {ev}"),
        objetivo=h["arreglo"][:300], quien="claude", tipo="codigo", prioridad=prioridad, esfuerzo=2,
        donde=h.get("donde") or "",
        hecho_cuando=[f"exito: el hallazgo {h['id']} deja de observarse (nucleo.kuzushi observar)",
                      "guarda: la suite completa sigue en verde y no aparece otro hallazgo en la misma zona"],
        origen={"prov": "kuzushi", "hallazgo": h["id"], "huella": h["huella"]},
        etiquetas=["origen:kuzushi", f"kuzushi:{h['id']}"])
    return t["id"]


def _encaminar(h: dict, ctx: dict, ahora: datetime) -> None:
    """Calibracion -> Claude; R3 -> Claude; obvio con arreglo y presupuesto -> tarea; el resto -> espera."""
    cal = (h.get("calibracion") or {}).get("veredicto")
    if cal == "no_util":
        _pasar(h, "descartado", "Claude: no util", ahora)
    elif ctx["calibrando"] and not cal:
        _pasar(h, "calibrar", "primera semana: Claude dice si es util antes de crear tareas", ahora)
    elif h.get("zona") in ZONAS_R3:
        _pasar(h, "claude", f"toca {h['zona']} (R3): lo decide Claude, nada automatico", ahora)
    elif h.get("para") == "damian":
        _pasar(h, "damian", "le toca decidir a Damian", ahora)
    elif not h.get("arreglo"):
        _pasar(h, "espera", "sin arreglo conocido: espera al debate (fase 2)", ahora)
    elif ctx["freno"]:
        _pasar(h, "espera", f"freno F0 puesto: {ctx['freno']}", ahora)
    elif ctx["presupuesto"] <= 0:
        _pasar(h, "espera", f"presupuesto de la noche agotado ({MAX_TAREAS_NOCHE} tareas)", ahora)
    elif ctx["simular"]:
        _pasar(h, "tarea", "(simulado) se crearia la tarea", ahora)
        ctx["presupuesto"] -= 1
    else:
        h["tarea"] = ctx["crear"](h)
        ctx["presupuesto"] -= 1
        ctx["creadas"].append(h["tarea"])
        _pasar(h, "tarea", f"arreglo conocido: tarea {h['tarea']}", ahora)


def _tareas_por_id(f: Fuentes) -> dict[str, dict]:
    salida = {t["id"]: t for t in f.historial if isinstance(t, dict) and t.get("id")}
    salida.update({t["id"]: t for t in f.tareas})
    return salida


def observar(simular: bool = False, fuentes: Fuentes | None = None, crear=None, limite: float | None = None,
             raiz_prompts: Path | None = None) -> dict:
    """Una pasada: observa, filtra por huella, encamina y guarda (salvo `simular`). Devuelve el resumen de la pasada."""
    import time
    f = fuentes or Fuentes()
    ahora = f.ahora
    reg, est = cargar(), estado()
    if not est.get("calibracion_hasta"):
        est["calibracion_hasta"] = (ahora + timedelta(days=DIAS_CALIBRACION)).strftime(FORMATO)
    hoy = ahora.strftime("%Y-%m-%d")
    hechas_hoy = int((est.get("tareas_por_dia") or {}).get(hoy, 0))
    try:
        from nucleo import freno
        cola = freno.estado_cola(f.tareas)
        freno_txt = "; ".join(cola["motivos"]) if cola["superado"] else ""
    except Exception as e:  # noqa: BLE001  (sin poder leer el freno, se actua como si estuviera puesto)
        freno_txt = f"no se pudo leer el freno ({type(e).__name__})"
    ctx = {"calibrando": calibrando(est, ahora), "freno": freno_txt, "simular": simular, "creadas": [],
           "presupuesto": max(0, MAX_TAREAS_NOCHE - hechas_hoy), "crear": crear or _crear_tarea}
    vistos, ok_fuentes, errores = [], set(), {}
    for nombre, obs in OBSERVADORES:
        if limite and time.time() > limite:
            errores[nombre] = "saltado: tope de tiempo del turno"
            continue
        try:
            if nombre == "salud":
                nuevos = obs(f, est.get("salud"))
            elif nombre == "prompts":
                nuevos = obs(f, raiz_prompts, guardar=not simular)
            else:
                nuevos = obs(f)
            vistos += nuevos
            ok_fuentes.add(nombre)
        except Exception as e:  # noqa: BLE001  (un observador roto no tapa a los demas)
            errores[nombre] = f"{type(e).__name__}: {e}"[:200]
    errores.update({f"fuente:{k}": v for k, v in f.errores.items()})
    por_huella = {h["huella"]: h for h in reg["hallazgos"]}
    nuevos_ids, reaparecidos = [], []
    vistos_ahora = set()
    for v in vistos:
        if v["huella"] in vistos_ahora:
            continue
        vistos_ahora.add(v["huella"])
        v = _tapar(v)
        h = por_huella.get(v["huella"])
        if h is None:
            h = dict(v, id=f"K{reg['siguiente']:04d}", visto=ahora.strftime(FORMATO), veces=0, estado="nuevo",
                     historial=[])
            reg["siguiente"] += 1
            reg["hallazgos"].append(h)
            por_huella[h["huella"]] = h
            nuevos_ids.append(h["id"])
            _encaminar(h, ctx, ahora)
        else:
            h.update({k: v[k] for k in ("titulo", "evidencia", "gravedad", "arreglo", "propone", "donde")})
            if h["estado"] == "resuelto" and h.get("resuelto_con") == _huella_ev(h):
                pass                                  # Bloque 23: lo resolvio Claude y la evidencia es la misma
            elif h["estado"] == "resuelto":
                reaparecidos.append(h["id"])
                _pasar(h, "nuevo", "reaparece: vuelve a observarse", ahora)
                _encaminar(h, ctx, ahora)
            elif h["estado"] == "util":
                _encaminar(h, ctx, ahora)
        h["ultimo"] = ahora.strftime(FORMATO)
        h["veces"] = int(h.get("veces") or 0) + 1
    tareas = _tareas_por_id(f)
    for h in reg["hallazgos"]:
        if h["huella"] in vistos_ahora:
            continue
        if h["estado"] in ABIERTOS and h["fuente"] in ok_fuentes:
            _pasar(h, "resuelto", "ya no se observa", ahora)
        elif h["estado"] == "tarea" and h.get("tarea") and (tareas.get(h["tarea"]) or {}).get("estado") in T.CERRADOS:
            _pasar(h, "resuelto", f"su tarea {h['tarea']} esta cerrada y ya no se observa", ahora)
    est["ultima"] = ahora.strftime(FORMATO)
    est.setdefault("tareas_por_dia", {})[hoy] = hechas_hoy + len(ctx["creadas"])
    est["tareas_por_dia"] = dict(sorted(est["tareas_por_dia"].items())[-30:])
    salud = est.setdefault("salud", {})
    muestras = dict(salud.get("muestras") or {})
    if f.disco:
        muestras[hoy] = f.disco
    muestras = dict(sorted(muestras.items())[-30:])
    hace7 = (ahora - timedelta(days=7)).strftime("%Y-%m-%d")
    salud.update({"muestras": muestras, "disco_hace_7": next((v for k, v in reversed(muestras.items()) if k <= hace7),
                                                              {})})
    res = {"cuando": est["ultima"], "simular": simular, "observados": len(vistos_ahora), "nuevos": nuevos_ids,
           "reaparecidos": reaparecidos, "tareas_creadas": ctx["creadas"], "calibrando": ctx["calibrando"],
           "freno": freno_txt, "errores": errores,
           "por_estado": dict(Counter(h["estado"] for h in reg["hallazgos"]))}
    est["ultima_pasada"] = {k: v for k, v in res.items() if k != "simular"}
    if not simular:
        _guardar(reg, est)
    res["registro"] = reg
    return res


def _huella_ev(h: dict) -> str:
    return hashlib.sha256(json.dumps(h.get("evidencia") or {}, sort_keys=True, ensure_ascii=False,
                                     default=str).encode("utf-8")).hexdigest()[:16]


def resolver(hid: str, motivo: str, ahora: datetime | None = None) -> dict:
    """Bloque 23 (29/10): Claude da un hallazgo por resuelto (arreglo hecho). Los observadores miran ventanas de 30 dias
    y seguirian viendo la evidencia VIEJA: con la huella de esa evidencia guardada, solo reaparece si cambia (un caso
    nuevo: otro turno que pasa el tope, otra tarea tumbada por el mismo test...)."""
    if not (motivo or "").strip():
        raise ValueError("hace falta el motivo")
    ahora = ahora or datetime.now()
    reg, est = cargar(), estado()
    h = next((x for x in reg["hallazgos"] if x["id"] == hid), None)
    if h is None:
        raise KeyError(f"no existe el hallazgo {hid}")
    h["resuelto_con"] = _huella_ev(h)
    _pasar(h, "resuelto", f"Claude: resuelto ({motivo.strip()[:180]})", ahora)
    _guardar(reg, est)
    return h


def calibrar(hid: str, veredicto: str, motivo: str, ahora: datetime | None = None) -> dict:
    """Claude marca un hallazgo: util (sigue su camino en la proxima pasada) o no_util (descartado para siempre)."""
    if veredicto not in ("util", "no_util"):
        raise ValueError("veredicto: util o no_util")
    if not (motivo or "").strip():
        raise ValueError("hace falta el motivo")
    ahora = ahora or datetime.now()
    reg, est = cargar(), estado()
    h = next((x for x in reg["hallazgos"] if x["id"] == hid), None)
    if h is None:
        raise KeyError(f"no existe el hallazgo {hid}")
    h["calibracion"] = {"veredicto": veredicto, "motivo": motivo.strip()[:300], "cuando": ahora.strftime(FORMATO),
                        "quien": "claude"}
    if veredicto == "no_util":
        _pasar(h, "descartado", f"Claude: no util ({motivo.strip()[:150]})", ahora)
    else:
        _pasar(h, "util", f"Claude: util ({motivo.strip()[:150]})", ahora)
    cal = est.setdefault("calibracion", {"util": 0, "no_util": 0})
    cal[veredicto] = int(cal.get(veredicto) or 0) + 1
    _guardar(reg, est)
    return h


# ================================================================ resumen semanal (apartado 4) y turno
def resumen(ahora: datetime | None = None, dias: int = 7) -> dict:
    """Lo que ve Damian en el Centro: visto / arreglado / descartado y por que, con enlace a cada caso."""
    ahora = ahora or datetime.now()
    desde = (ahora - timedelta(days=dias)).strftime(FORMATO)
    reg, est = cargar(), estado()

    def caso(h, motivo=""):
        return {"id": h["id"], "titulo": h["titulo"], "gravedad": h["gravedad"], "estado": h["estado"],
                "motivo": motivo, "tarea": h.get("tarea", ""), "url": f"/kuzushi#{h['id']}"}

    def cambio(h, estados):
        return next((e for e in reversed(h.get("historial") or []) if e["estado"] in estados and e["cuando"] >= desde),
                    None)
    vistos = [h for h in reg["hallazgos"] if h.get("visto", "") >= desde]
    arreglados = [(h, cambio(h, ("resuelto",))) for h in reg["hallazgos"]]
    descartados = [(h, cambio(h, ("descartado",))) for h in reg["hallazgos"]]
    return {"desde": desde[:10], "hasta": ahora.strftime("%Y-%m-%d"), "ultima": est.get("ultima", ""),
            "calibrando": calibrando(est, ahora), "calibracion_hasta": str(est.get("calibracion_hasta", ""))[:10],
            "visto": [caso(h) for h in vistos],
            "arreglado": [caso(h, e["motivo"]) for h, e in arreglados if e],
            "descartado": [caso(h, (h.get("calibracion") or {}).get("motivo") or e["motivo"]) for h, e in descartados if e],
            "tareas": [caso(h) for h in reg["hallazgos"] if h["estado"] == "tarea"],
            "para_claude": sum(1 for h in reg["hallazgos"] if h["estado"] in ("calibrar", "claude")),
            "para_damian": [caso(h) for h in reg["hallazgos"] if h["estado"] == "damian"],
            "en_espera": sum(1 for h in reg["hallazgos"] if h["estado"] == "espera"),
            "graves": [caso(h) for h in reg["hallazgos"] if h["gravedad"] == "grave" and h["estado"] in ABIERTOS]}


def vista() -> dict:
    """La pagina /kuzushi: el resumen y cada caso con su evidencia."""
    reg = cargar()
    orden = {"grave": 0, "media": 1, "baja": 2}
    return {"r": resumen(), "hallazgos": sorted(reg["hallazgos"], key=lambda h: (h["estado"] not in ABIERTOS,
                                                                                 orden.get(h["gravedad"], 3), h["id"]))}


def candidatas(ahora: datetime | None = None) -> int:
    """Puerta del turno (T156): 1 si hoy aun no se ha observado, 0 si ya."""
    ahora = ahora or datetime.now()
    return 0 if str(estado().get("ultima", ""))[:10] == ahora.strftime("%Y-%m-%d") else 1


def turno(simular: bool = False, limite: float | None = None) -> dict:
    r = observar(simular=simular, limite=limite)
    r.pop("registro", None)
    return r


def texto_resumen(r: dict) -> str:
    if r.get("error"):
        return f"kuzushi: ERROR {r['error'][:120]}"
    return (f"kuzushi: {r.get('observados', 0)} hallazgos vistos, {len(r.get('nuevos') or [])} nuevos, "
            f"{len(r.get('tareas_creadas') or [])} tarea(s) creada(s)"
            + (" (calibracion: todo a la cola de Claude)" if r.get("calibrando") else "")
            + (f"; {len(r['errores'])} fuente(s) con error" if r.get("errores") else ""))


# ================================================================ CLI
def _linea(h: dict) -> str:
    return f"{h['id']} [{h['estado']}] {h['gravedad']:5} {h['fuente']}/{h['tipo']}: {h['titulo']}"


def _cli(argv: list[str]) -> int:
    from nucleo import consola
    consola.preparar()
    orden = argv[0] if argv else ""
    if orden == "observar":
        r = observar(simular="--simular" in argv)
        reg = r.pop("registro")
        print(json.dumps({k: v for k, v in r.items()}, ensure_ascii=False, indent=1))
        for hid in r["nuevos"][:30]:
            h = next(x for x in reg["hallazgos"] if x["id"] == hid)
            print(_linea(h))
        return 0
    if orden == "hallazgos":
        filtro = argv[1] if len(argv) > 1 else ""
        for h in cargar()["hallazgos"]:
            if not filtro or h["estado"] == filtro:
                print(_linea(h))
                if filtro:
                    print("    " + json.dumps(h["evidencia"], ensure_ascii=False)[:400])
        return 0
    if orden == "calibrar" and len(argv) >= 4:
        h = calibrar(argv[1], argv[2], " ".join(argv[3:]))
        print(_linea(h))
        return 0
    if orden == "resolver" and len(argv) >= 3:
        h = resolver(argv[1], " ".join(argv[2:]))
        print(f"{h['id']}: {h['estado']}")
        return 0
    if orden == "resumen":
        print(json.dumps(resumen(), ensure_ascii=False, indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(_cli(sys.argv[1:]))
