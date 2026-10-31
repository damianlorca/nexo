# -*- coding: utf-8 -*-
"""Linea base de la suite en principal para el implementador y su puerta (T1027, 20/10).

Por que: el 13-18/10 la puerta rechazo T844, T851, T854, T862 y el implementador dio por fallida T938 por tests
AJENOS a la tarea que tambien fallaban en principal o solo en su worktree (proceso real, datos privados que el
sparse-checkout no trae, tiempos con el PC cargado). Una tarea solo debe caer por lo que rompe ELLA.

Como: cuando la suite de la rama sale en rojo, se leen los tests que fallan (lineas FAILED/ERROR de pytest) y se
pasan SOLO esos en un worktree aparte de principal (`agente_impl/_linea_base`, mismo sparse-checkout que los del
implementador: mismo entorno). Los que tambien fallan alli ya estaban rotos antes de la tarea y no cuentan. El
resultado se guarda por commit de principal (memoria/implementador/linea_base.json): el mismo test en el mismo
commit no se vuelve a pasar.

Conservador a proposito: si no se pueden leer bien los fallos (salida cortada, timeout, recuento que no cuadra) o un
test no existe en principal (es nuevo de la tarea), el rojo cuenta.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from nucleo import implementador as I
from nucleo.escritura import escribir_atomico

NOMBRE_WT = "_linea_base"
CACHE_NOMBRE = "linea_base.json"
MAX_COMMITS = 20             # commits de principal que se recuerdan (los mas recientes)
_ROJO = re.compile(r"^(FAILED|ERROR) (.+?)(?: - .*)?$")
_CUENTA = re.compile(r"(\d+) (failed|errors?)\b")


def worktree() -> Path:
    return I.WORKTREES / NOMBRE_WT


def _cache_ruta() -> Path:
    return I.INFORMES / CACHE_NOMBRE


def rojos(salida: str) -> list[str] | None:
    """Ids de pytest que fallan (FAILED/ERROR del resumen). None si no se puede fiar: no hay ninguno o su numero no
    cuadra con el "N failed, M errors" de la ultima linea (salida cortada, interrumpida...)."""
    lineas = (salida or "").splitlines()
    ids = list(dict.fromkeys(m.group(2).strip() for l in lineas if (m := _ROJO.match(l.strip()))))
    if not ids:
        return None
    final = next((l for l in reversed(lineas) if _CUENTA.search(l)), "")
    total = sum(int(n) for n, _ in _CUENTA.findall(final))
    return ids if total == len(ids) else None


def _cargar() -> dict:
    try:
        d = json.loads(_cache_ruta().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar(d: dict) -> None:
    _cache_ruta().parent.mkdir(parents=True, exist_ok=True)
    recientes = sorted(d.items(), key=lambda kv: kv[1].get("_orden", 0))[-MAX_COMMITS:]
    escribir_atomico(_cache_ruta(), json.dumps(dict(recientes), ensure_ascii=False, indent=1))


def _preparar(commit: str) -> Path:
    """El worktree de la linea base, en `commit` (detached) y limpio. Mismo sparse-checkout que el implementador."""
    wt = worktree()
    if not (wt / ".git").exists():
        I.WORKTREES.mkdir(parents=True, exist_ok=True)
        I._git(I.REPO, "worktree", "add", "-q", "--no-checkout", "--detach", str(wt), commit)
        I._git(wt, "sparse-checkout", "set", "--no-cone", *I.patrones_sparse())
    I._git(wt, "checkout", "-q", "--detach", "-f", commit)
    I._git(wt, "reset", "-q", "--hard", commit)
    I._git(wt, "clean", "-q", "-fd")
    return wt


def _archivo(nodo: str) -> str:
    return nodo.split("::", 1)[0]


def _medir(ids: list[str], commit: str) -> dict[str, bool]:
    """{id: falla en principal}. Los que no existen alli (tests nuevos de la tarea) no fallan alli: cuentan."""
    wt = _preparar(commit)
    existen = [i for i in ids if (wt / _archivo(i)).is_file()]
    resultado = {i: False for i in ids}
    if not existen:
        return resultado
    ok, salida = I._suite(wt, existen)
    I.limpiar(wt)
    if ok:
        return resultado
    fallan = rojos(salida)
    if fallan is None:              # no se sabe que fallo alli: ninguno se da por viejo
        return resultado
    for i in existen:
        resultado[i] = i in fallan or _archivo(i) in fallan    # "ERROR tests/x.py" = el archivo entero no carga
    return resultado


def ya_en_principal(ids: list[str], commit: str | None = None) -> set[str]:
    """Los de `ids` que tambien fallan en principal (en `commit`; por defecto, la punta de principal)."""
    commit = commit or I._git(I.REPO, "rev-parse", I.RAMA_BASE).strip()
    cache = _cargar()
    del_commit = cache.get(commit) or {"_orden": max([v.get("_orden", 0) for v in cache.values()] + [0]) + 1}
    faltan = [i for i in ids if i not in del_commit]
    if faltan:
        del_commit.update(_medir(faltan, commit))
        cache[commit] = del_commit
        _guardar(cache)
    return {i for i in ids if del_commit.get(i) is True}


def filtrar(ok: bool, salida: str, commit: str | None = None) -> tuple[bool, str, list[str]]:
    """(ok de verdad, salida, fallos que ya estaban en principal). Verde si TODOS los rojos de la rama ya fallaban en
    principal; si hay uno nuevo (o no se puede saber), sigue en rojo."""
    if ok:
        return True, salida, []
    ids = rojos(salida)
    if not ids:
        return False, salida, []
    try:
        viejos = ya_en_principal(ids, commit)
    except I.FalloInfra:            # Bloque 21: la suite de principal no dio resultado: quien llama lo deja para otra tanda
        raise
    except Exception as e:  # noqa: BLE001 - sin linea base, el rojo cuenta (nunca se fusiona a ciegas)
        return False, f"{salida}\n(linea base no disponible: {type(e).__name__}: {e})", []
    return not [i for i in ids if i not in viejos], salida, sorted(viejos)
