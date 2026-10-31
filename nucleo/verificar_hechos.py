# -*- coding: utf-8 -*-
"""T288 (Damian 28/09): cuando un revisor solo puede marcar una sospecha como NO VERIFICABLE (sin
prueba), NEXO la comprueba el mismo antes de dejar que suba a ALTA y gaste una revision de Claude.

Evidencia 27-28/09 (T174, T199, T200): Gemini/NVIDIA marcaron como posible alucinacion datos REALES
(agentskills.io, OpenClaw, Hermes Agent) solo porque no podian comprobarlos ellos mismos; Claude los
comprobo y eran ciertos. Casi todos esos ESCALAR acababan aprobados: gasto de Claude evitable.

Determinista, sin modelo (igual que nucleo/auditor.py): descarga la URL citada o consulta la API
publica de GitHub (repo/release/licencia, sin clave). Si no hay URL ni repo que comprobar, o falla la
red, el resultado queda sin decidir (confirmado=None) y NUNCA se convierte en un FALSO por descarte:
ante la duda, sigue siendo NO VERIFICABLE.
"""
from __future__ import annotations

import re

import httpx

from nucleo.registro import logger

log = logger("nucleo.verificar_hechos")

TIMEOUT = 8.0
CABECERAS = {"User-Agent": "NEXO-verificador-T288 (+https://github.com/, uso interno)"}
_URL = re.compile(r"https?://[^\s\"'>\]\)]+")
_REPO = re.compile(r"github\.com/([\w.-]+/[\w.-]+?)(?:[/#?].*)?$")


def _limpiar_url(url: str) -> str:
    return url.rstrip(").,;:'\"")


def comprobar_url(url: str, timeout: float = TIMEOUT) -> dict:
    """{'confirmado': True/False/None, 'detalle': str}. None = no se pudo comprobar (red, timeout...)."""
    url = _limpiar_url(url)
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers=CABECERAS)
    except httpx.HTTPError as e:
        log.info("no se pudo comprobar %s: %s", url, e)
        return {"confirmado": None, "detalle": f"{url}: no se pudo comprobar ({type(e).__name__})"}
    if r.status_code == 404:
        return {"confirmado": False, "detalle": f"{url}: responde 404, la URL no existe"}
    if r.status_code < 400:
        return {"confirmado": True, "detalle": f"{url}: responde {r.status_code}"}
    return {"confirmado": None, "detalle": f"{url}: responde {r.status_code}, no concluyente"}


def comprobar_repo_github(owner_repo: str, timeout: float = TIMEOUT) -> dict:
    """Existencia, licencia y ultimo release de un repo de GitHub via su API publica (sin clave)."""
    owner_repo = owner_repo.strip("/")
    try:
        r = httpx.get(f"https://api.github.com/repos/{owner_repo}", timeout=timeout,
                      headers={**CABECERAS, "Accept": "application/vnd.github+json"})
    except httpx.HTTPError as e:
        log.info("no se pudo comprobar el repo %s: %s", owner_repo, e)
        return {"confirmado": None, "detalle": f"{owner_repo}: no se pudo comprobar ({type(e).__name__})"}
    if r.status_code == 404:
        return {"confirmado": False, "detalle": f"{owner_repo}: no existe en GitHub (404)"}
    if r.status_code != 200:
        return {"confirmado": None, "detalle": f"{owner_repo}: GitHub responde {r.status_code}, no concluyente"}
    datos = r.json()
    licencia = (datos.get("license") or {}).get("spdx_id") or "sin licencia detectada"
    detalle = f"{owner_repo}: existe en GitHub, licencia {licencia}"
    try:
        rel = httpx.get(f"https://api.github.com/repos/{owner_repo}/releases/latest", timeout=timeout,
                        headers={**CABECERAS, "Accept": "application/vnd.github+json"})
        if rel.status_code == 200:
            detalle += f", ultimo release {rel.json().get('tag_name', '?')}"
    except httpx.HTTPError:
        pass
    return {"confirmado": True, "detalle": detalle}


def verificar_item(texto: str) -> dict:
    """Un punto NO VERIFICABLE de un revisor: prueba primero un repo de GitHub citado, si no una URL."""
    m = _REPO.search(texto or "")
    if m:
        return comprobar_repo_github(m.group(1))
    m = _URL.search(texto or "")
    if m:
        return comprobar_url(m.group(0))
    return {"confirmado": None, "detalle": "sin URL ni repositorio de GitHub que comprobar"}


def verificar_items(textos: list[str]) -> list[dict]:
    return [verificar_item(t) for t in textos]
