# -*- coding: utf-8 -*-
"""T078: uso de Claude por sesion de Claude Code y por tarea (linea base para comparar antes/despues).

uso_proveedores.jsonl ya mide qwen/gemini/chatgpt/groq, pero las sesiones de Code (donde se gasta el
plan de Claude) no pasan por NEXO. Lo que si queda es el transcript de cada sesion en
~/.claude/projects/<carpeta del repo>/<sesion>.jsonl, con el `usage` REAL de cada peticion a la API
(modelo, esfuerzo, tokens de entrada, de cache y de salida). Aqui se resume eso.

- Una peticion aparece en varias lineas (una por bloque de contenido) con el mismo usage: se cuenta
  una vez por requestId.
- Tareas trabajadas en la sesion: las que salen en el asunto de sus `git commit -m "Txxx..."` y en sus
  `nucleo.tareas hecha|completar|verificar Txxx`. Por tarea se reparte el uso de la sesion a partes
  iguales entre sus tareas (es una estimacion: la sesion no dice cuanto fue a cada una).
- "ponderado" = tokens expresados en tokens de entrada del MISMO modelo con los multiplicadores de
  precio de la API (cache 5 min x1.25, cache 1 h x2, lectura de cache x0.1, salida x5). Sirve para
  comparar sesiones del mismo modelo; entre modelos no (el precio base es distinto).
- Claude Code borra los transcripts viejos (30 dias por defecto): `actualizar` guarda el resumen de
  cada sesion en registros/uso_claude.jsonl (una linea por sesion, se reescribe entera) y conserva
  las sesiones cuyo transcript ya no existe.
- Solo lee numeros, comandos de commit/tareas y el titulo de la sesion; nunca copia el texto de la
  conversacion.

Uso:  .venv\\Scripts\\python.exe -m nucleo.uso_claude actualizar|resumen [dias]|tareas [dias]|comparar AAAA-MM-DD [dias]
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REGISTRO = RAIZ / "registros" / "uso_claude.jsonl"
PROYECTOS = Path.home() / ".claude" / "projects"

PESOS = {"entrada": 1.0, "cache_5m": 1.25, "cache_1h": 2.0, "cache_lectura": 0.1, "salida": 5.0}
CAMPOS = tuple(PESOS)

_ID = re.compile(r"\bT\d{3,}\b")
_COMMIT = re.compile(r"git\s+commit\b.*?-m\s+([\"'])(.*?)(?:\n|\1)", re.S)
_TAREAS_CLI = re.compile(r"nucleo\.tareas\s+(?:hecha|completar|verificar|testeada)\s+(T\d{3,})\b", re.I)


def carpeta_proyecto(raiz: Path = RAIZ) -> str:
    """Nombre que Claude Code da a la carpeta del proyecto (C:\\a\\b -> C--a-b)."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(raiz))


def transcripts(raiz: Path = RAIZ, proyectos: Path = PROYECTOS) -> list[Path]:
    """Sesiones de este repo y de sus worktrees (carpetas que empiezan igual), con sus subagentes."""
    base = carpeta_proyecto(raiz)
    if not proyectos.is_dir():
        return []
    salida = []
    for d in proyectos.iterdir():
        if d.is_dir() and (d.name == base or d.name.startswith(base + "-")):
            salida += sorted(d.glob("*.jsonl"))
    return salida


def _vacio() -> dict:
    return {**{c: 0 for c in CAMPOS}, "peticiones": 0}


def ponderado(u: dict) -> float:
    return round(sum(PESOS[c] * u.get(c, 0) for c in CAMPOS))


def _tareas_de_comando(cmd: str) -> set[str]:
    ids = set(_TAREAS_CLI.findall(cmd))
    for m in _COMMIT.finditer(cmd):
        ids |= set(_ID.findall(m.group(2).splitlines()[0] if m.group(2) else ""))
    return ids


def _sumar(u: dict, usage: dict) -> None:
    cc = usage.get("cache_creation") or {}
    c5, c1 = cc.get("ephemeral_5m_input_tokens"), cc.get("ephemeral_1h_input_tokens")
    if c5 is None and c1 is None:  # formato viejo sin desglose: se toma como cache de 5 min
        c5, c1 = usage.get("cache_creation_input_tokens", 0), 0
    u["entrada"] += usage.get("input_tokens", 0) or 0
    u["cache_5m"] += c5 or 0
    u["cache_1h"] += c1 or 0
    u["cache_lectura"] += usage.get("cache_read_input_tokens", 0) or 0
    u["salida"] += usage.get("output_tokens", 0) or 0
    u["peticiones"] += 1


def leer_sesion(ruta: Path) -> dict | None:
    """Resumen de una sesion: fechas, titulo, uso por modelo, esfuerzo y tareas. None si no hay peticiones."""
    vistas: set[str] = set()
    modelos: dict[str, dict] = defaultdict(_vacio)
    esfuerzos: dict[str, int] = defaultdict(int)
    tareas: set[str] = set()
    titulo, inicio, fin = "", None, None
    rutas = [ruta] + sorted((ruta.parent / ruta.stem / "subagents").glob("*.jsonl"))
    for r in rutas:
        try:
            lineas = r.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for linea in lineas:
            try:
                x = json.loads(linea)
            except ValueError:
                continue
            if x.get("type") == "custom-title" and r == ruta:
                titulo = x.get("customTitle") or titulo
                continue
            if x.get("type") != "assistant":
                continue
            m = x.get("message") or {}
            for b in m.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    cmd = (b.get("input") or {}).get("command")
                    if isinstance(cmd, str):
                        tareas |= _tareas_de_comando(cmd)
            clave = x.get("requestId") or m.get("id")
            usage = m.get("usage")
            if not clave or not usage or clave in vistas or m.get("model") == "<synthetic>":
                continue
            vistas.add(clave)
            _sumar(modelos[m.get("model") or "?"], usage)
            esfuerzos[x.get("effort") or "?"] += 1
            cuando = x.get("timestamp") or ""
            inicio = min(inicio or cuando, cuando)
            fin = max(fin or cuando, cuando)
    if not vistas:
        return None
    return {"sesion": ruta.stem, "titulo": titulo, "inicio": _local(inicio), "fin": _local(fin),
            "modelos": dict(modelos), "esfuerzos": dict(esfuerzos), "tareas": sorted(tareas)}


def _local(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return iso


# ------------------------------------------------------------------ registro
def cargar(registro: Path = REGISTRO) -> dict[str, dict]:
    datos = {}
    if registro.is_file():
        for linea in registro.read_text(encoding="utf-8").splitlines():
            try:
                s = json.loads(linea)
                datos[s["sesion"]] = s
            except (ValueError, KeyError, TypeError):
                continue
    return datos


def actualizar(registro: Path = REGISTRO, rutas: list[Path] | None = None) -> int:
    """Relee los transcripts que haya y reescribe el registro. Devuelve cuantas sesiones hay."""
    datos = cargar(registro)
    for r in transcripts() if rutas is None else rutas:
        s = leer_sesion(r)
        if s:
            datos[s["sesion"]] = s
    registro.parent.mkdir(parents=True, exist_ok=True)
    tmp = registro.with_suffix(".tmp")
    orden = sorted(datos.values(), key=lambda s: s["inicio"])
    tmp.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in orden), encoding="utf-8")
    tmp.replace(registro)
    return len(datos)


# ------------------------------------------------------------------ informes
def _en_rango(s: dict, desde: date | None, hasta: date | None) -> bool:
    d = s["inicio"][:10]
    return (desde is None or d >= desde.isoformat()) and (hasta is None or d < hasta.isoformat())


def por_modelo(sesiones: list[dict]) -> dict[str, dict]:
    tot: dict[str, dict] = defaultdict(_vacio)
    for s in sesiones:
        for modelo, u in s["modelos"].items():
            for k in (*CAMPOS, "peticiones"):
                tot[modelo][k] += u.get(k, 0)
    return dict(tot)


def por_tarea(sesiones: list[dict]) -> dict[str, dict]:
    """{tarea: {sesiones, ponderado por modelo (reparto a partes iguales)}}."""
    tot: dict[str, dict] = defaultdict(lambda: {"sesiones": 0, "ponderado": defaultdict(float)})
    for s in sesiones:
        if not s["tareas"]:
            continue
        parte = 1 / len(s["tareas"])
        for t in s["tareas"]:
            tot[t]["sesiones"] += 1
            for modelo, u in s["modelos"].items():
                tot[t]["ponderado"][modelo] += ponderado(u) * parte
    return {t: {"sesiones": v["sesiones"], "ponderado": {m: round(p) for m, p in v["ponderado"].items()}}
            for t, v in tot.items()}


def comparar(corte: date, dias: int, sesiones: list[dict]) -> dict:
    """Media diaria de peticiones y ponderado por modelo en los `dias` antes y despues de `corte`."""
    antes = [s for s in sesiones if _en_rango(s, corte - timedelta(days=dias), corte)]
    despues = [s for s in sesiones if _en_rango(s, corte, corte + timedelta(days=dias))]

    def media(grupo):
        return {m: {"peticiones_dia": round(u["peticiones"] / dias, 1), "ponderado_dia": round(ponderado(u) / dias)}
                for m, u in por_modelo(grupo).items()}
    return {"corte": corte.isoformat(), "dias": dias, "antes": {"sesiones": len(antes), "modelos": media(antes)},
            "despues": {"sesiones": len(despues), "modelos": media(despues)}}


def _mil(n: float) -> str:
    """En millones con un decimal: 44894123 -> '44.9M' (la consola de Windows no pinta bien '·')."""
    return f"{n / 1e6:.1f}M"


def resumen(dias: int, sesiones: list[dict]) -> str:
    desde = date.today() - timedelta(days=dias - 1)
    grupo = [s for s in sesiones if _en_rango(s, desde, None)]
    if not grupo:
        return f"Sin sesiones de Claude Code en los ultimos {dias} dias."
    lineas = [f"Claude Code, ultimos {dias} dias: {len(grupo)} sesiones"]
    for m, u in sorted(por_modelo(grupo).items()):
        lineas.append(f"  {m}: {u['peticiones']} peticiones | ponderado {_mil(ponderado(u))} | salida "
                      f"{_mil(u['salida'])} | cache leida {_mil(u['cache_lectura'])}")
    for s in grupo:
        tot = sum(ponderado(u) for u in s["modelos"].values())
        pet = sum(u["peticiones"] for u in s["modelos"].values())
        esf = ",".join(sorted(s["esfuerzos"]))
        lineas.append(f"  {s['inicio'][5:16]} {s['sesion'][:8]} {s['titulo'][:30]:30} {pet:4} pet | "
                      f"{_mil(tot):>7} | esfuerzo {esf} | {' '.join(s['tareas']) or '-'}")
    return "\n".join(lineas)


def _cli(argv: list[str]) -> int:
    accion = argv[0] if argv else "resumen"
    num = [a for a in argv[1:] if a.isdigit()]
    if accion == "actualizar":
        print(f"{actualizar()} sesiones en {REGISTRO}")
        return 0
    sesiones = list(cargar().values())
    if accion == "resumen":
        print(resumen(int(num[0]) if num else 7, sesiones))
    elif accion == "tareas":
        desde = date.today() - timedelta(days=int(num[0]) - 1) if num else None
        filas = por_tarea([s for s in sesiones if _en_rango(s, desde, None)])
        for t, v in sorted(filas.items(), key=lambda kv: -sum(kv[1]["ponderado"].values())):
            print(f"{t}  {v['sesiones']} ses | " + " | ".join(f"{m} {_mil(p)}" for m, p in v["ponderado"].items()))
    elif accion == "comparar" and len(argv) > 1:
        corte = date.fromisoformat(argv[1])
        print(json.dumps(comparar(corte, int(argv[2]) if len(argv) > 2 else 7, sesiones), ensure_ascii=False, indent=1))
    else:
        print(__doc__.strip().splitlines()[-1])
        return 2
    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    sys.exit(_cli(sys.argv[1:]))
