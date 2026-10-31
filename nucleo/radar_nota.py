# -*- coding: utf-8 -*-
"""T693 R2: nota local (0-100) de un articulo de radar. Determinista, sin IA y sin red (RADARES.md §3.3).

Mezcla los filtros genericos del config del radar (`filtros.palabras_si` / `palabras_no`) con las empresas y
organizaciones del perfil PRIVADO de Damian (memoria/perfil_privado/perfil.md, seccion "### Empresas..."), que se
lee aqui, en el PC, y nunca sale: ni a un prompt, ni a una tarea, ni a un log. El `motivo` ("por que te lo enseño")
solo nombra lo que ya esta en el texto publico del articulo.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PERFIL = RAIZ / "memoria" / "perfil_privado" / "perfil.md"
BASE = 30
POR_PALABRA = 15
MAX_PALABRAS = 45
POR_EMPRESA = 25
CASTIGO_NO = 60
# Mayusculas que no son empresas (inicio de frase, siglas genericas)
_NO_EMPRESA = {"IA", "AI", "NO", "Ver", "Ejemplos", "Criterio", "Encajan", "Trabajos"}


def _plano(texto: str) -> str:
    s = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def empresas_del_perfil(ruta: Path | None = None) -> list[str]:
    """Nombres propios (palabra con mayuscula o sigla) de la seccion de empresas del perfil; [] si no hay perfil."""
    try:
        texto = (ruta or PERFIL).read_text(encoding="utf-8")
    except OSError:
        return []
    m = re.search(r"^###\s*Empresas[^\n]*\n(.*?)(?=^#{2,3}\s|\Z)", texto, re.M | re.S)
    if not m:
        return []
    nombres = []
    for vineta in re.split(r"\n\s*-\s", "\n" + m.group(1)):
        cola = vineta.split(":", 1)[1] if ":" in vineta else vineta
        cola = re.sub(r"\([^)]*\)", " ", cola)
        for n in re.findall(r"\b([A-Z][A-Za-z]+|[A-Z]{2,})\b", cola):
            if n not in _NO_EMPRESA and n not in nombres:
                nombres.append(n)
    return nombres


def _aparece(termino: str, texto_plano: str) -> bool:
    t = _plano(termino).strip()
    return bool(t) and re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", texto_plano) is not None


def puntuar(articulo: dict, si: list[str], no: list[str], empresas: list[str]) -> tuple[int, str]:
    texto = _plano(f"{articulo.get('titulo', '')} {articulo.get('texto', '')}")
    malas = [p for p in no if _aparece(p, texto)]
    buenas, raices = [], set()
    for p in si:            # "internship" e "internships" cuentan una vez
        if _aparece(p, texto) and _plano(p)[:8] not in raices:
            buenas.append(p)
            raices.add(_plano(p)[:8])
    suyas = [e for e in empresas if _aparece(e, texto)]
    nota = BASE + min(len(buenas) * POR_PALABRA, MAX_PALABRAS) + (POR_EMPRESA if suyas else 0)
    if malas:
        nota -= CASTIGO_NO
    nota = max(0, min(100, nota))
    partes = []
    if suyas:
        partes.append("organización que te interesa: " + ", ".join(suyas[:3]))
    if buenas:
        partes.append("encaja con lo que buscas: " + ", ".join(buenas[:3]))
    if malas:
        partes.append("pero parece " + ", ".join(malas[:2]))
    return nota, "; ".join(partes)


def puntuador(cfg: dict, perfil: Path | None = None):
    """La funcion `puntuar(cfg, articulo)` que usa radar.pasada. Lee el perfil una vez por pasada."""
    f = cfg.get("filtros") or {}
    si, no = list(f.get("palabras_si") or []), list(f.get("palabras_no") or [])
    empresas = empresas_del_perfil(perfil) if (cfg.get("nota") or {}).get("perfil") else []
    return lambda cfg_, art: puntuar(art, si, no, empresas)
