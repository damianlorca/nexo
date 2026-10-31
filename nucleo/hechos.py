# -*- coding: utf-8 -*-
"""Comprobacion de hechos contra el repo para los revisores de diffs (T685, F3 de T664).

Por que existe: el 04/10 el revisor de la puerta rechazo el diff de T347 diciendo que `evaluar_candidatas` "no existe
en el diff". La funcion existia en el archivo; el revisor solo veia las lineas del diff. Dos defensas, sin IA:
  1. `contexto_simbolos`: el prompt lleva las funciones y clases que definen los archivos tocados.
  2. `verificar_rechazo`: si el rechazo se reduce a acusaciones de "X no existe" y X existe en el repo, se anula la
     acusacion; si no queda ninguna razon, el veredicto pasa a APROBAR (anulado). Cualquier otra razon mantiene el
     rechazo. Una acusacion verdadera (el simbolo de verdad no existe) tambien se mantiene.

Solo busca en el repo que le pasen (el worktree de la rama) y nunca devuelve evidencia de rutas privadas.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from nucleo import implementador as I

_ACUSA = re.compile(
    r"no\s+(?:exist[ae]n?|est[aá]\s+(?:definid|implementad|declarad)|se\s+(?:define|encuentra)|aparece|hay)"
    r"|inexistente|not\s+defined|undefined|does(?:n't|\s+not)\s+exist|no\s+such",
    re.I)
_CAND = re.compile(r"`([^`\n]{1,120})`|(?<![\w/.])([A-Za-z_]\w*(?:\.\w+)*\(\))|(?<![\w/.])([A-Za-z]\w*_\w+)\b"
                   r"|((?:[\w.-]+/)+[\w.-]+\.\w+)")
_DEF = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)", re.M)
_MAX_CONTEXTO = 3000


def _git(repo, *args) -> str:
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.stdout if r.returncode in (0, 1) else ""


def simbolo_existe(repo, simbolo: str) -> str | None:
    """'ruta:linea' donde aparece el simbolo (o la ruta, si es un archivo); None si no esta o solo esta en lo privado."""
    s = simbolo.strip().strip("`'\"")
    s = re.sub(r"\(.*\)$", "", s)
    if not s:
        return None
    if "/" in s:
        ruta = s.lstrip("./")
        return ruta if (Path(repo) / ruta).is_file() and not I.no_enviable(ruta) else None
    # T939 (24/10): "importacion de `nucleo` que probablemente no exista": un paquete o modulo del repo existe aunque su
    # nombre no salga en ningun texto (git grep mira contenidos, no rutas).
    modulo = s.replace(".", "/")
    if re.fullmatch(r"\w+(/\w+)*", modulo) and not I.no_enviable(modulo):
        for cand in (f"{modulo}/__init__.py", f"{modulo}.py"):
            if (Path(repo) / cand).is_file():
                return cand
        if (Path(repo) / modulo).is_dir() and any((Path(repo) / modulo).glob("*.py")):
            return f"{modulo}/"
    s = s.split(".")[-1] if re.fullmatch(r"\w+(\.\w+)+", s) else s
    if not re.fullmatch(r"\w+", s):
        return None
    for linea in _git(repo, "grep", "-n", "-w", "-I", "-e", s).splitlines():
        ruta, _, resto = linea.partition(":")
        num = resto.partition(":")[0]
        if ruta and num.isdigit() and not I.no_enviable(ruta):
            return f"{ruta}:{num}"
    return None


def contexto_simbolos(repo, diff: str) -> str:
    """Funciones y clases de nivel de archivo de los .py tocados por el diff, leidas del repo (no del diff)."""
    lineas, total = [], 0
    for ruta in dict.fromkeys(re.findall(r"(?m)^diff --git a/\S+ b/(\S+)", diff or "")):
        if not ruta.endswith(".py") or I.no_enviable(ruta):
            continue
        try:
            texto = (Path(repo) / ruta).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        nombres = list(dict.fromkeys(_DEF.findall(texto)))[:80]
        if nombres:
            linea = f"{ruta}: " + ", ".join(nombres)
            if total + len(linea) > _MAX_CONTEXTO:
                break
            lineas.append(linea)
            total += len(linea)
    return "\n".join(lineas)


def _candidatos(frase: str) -> list[str]:
    out = []
    for m in _CAND.finditer(frase):
        c = next(g for g in m.groups() if g)
        if c not in out:
            out.append(c)
    return out


def verificar_rechazo(rev: dict, repo) -> dict:
    """Devuelve el veredicto con las acusaciones falsas de inexistencia anuladas (clave `anuladas`)."""
    if rev.get("veredicto") != "RECHAZAR":
        return rev
    motivo = rev.get("motivo") or ""
    anuladas, queda = [], False
    for frase in [f for f in re.split(r"(?<=[.;!?])\s+|\n", motivo) if f.strip()]:
        cands = _candidatos(frase) if _ACUSA.search(frase) else []
        encontrados = [(c, simbolo_existe(repo, c)) for c in cands]
        if cands and all(d for _, d in encontrados):
            anuladas += [{"simbolo": re.sub(r"\(.*\)$", "", c.strip("`")), "donde": d} for c, d in encontrados]
        else:
            queda = True
    if not anuladas:
        return rev
    nota = "acusacion anulada, el simbolo existe en el repo: " + ", ".join(
        f"{a['simbolo']} ({a['donde']})" for a in anuladas)
    r = dict(rev, anuladas=anuladas)
    if queda:
        r["motivo"] = f"{motivo} [{nota}]"[:600]
    else:
        r.update(veredicto="APROBAR", motivo=f"{nota}. Rechazo original: {motivo}"[:600])
    return r
