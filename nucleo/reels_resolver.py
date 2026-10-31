# -*- coding: utf-8 -*-
"""T859 bloque 6, paso 4: resolucion de los elementos de una ficha de reel con busqueda GRATUITA.

  repo con dueno     GET api.github.com/repos/<dueno>/<repo>: existe, nombre canonico (sigue renombres),
                     estrellas, licencia, ultima actividad (pushed_at), archivado. Si da 404, se busca por nombre.
  repo sin dueno     GET api.github.com/search/repositories?q=<nombre> in:name: solo vale un candidato con el nombre
                     EXACTO (sin mayusculas ni guiones) Y cuya descripcion (T966) encaje con lo que el reel dice del
                     elemento (lineas de pantalla, frase del pie, "que es"); de varios que encajen, el de mas estrellas,
                     y la resolucion queda "por busqueda" (confianza media) con los otros candidatos anotados. Sin
                     candidato exacto o sin encaje: sin resolver (nunca se acepta un homonimo por el nombre).
  web / URL          HEAD (o GET si el servidor no admite HEAD): existe si responde < 400.
  lo demas           no aplica (un consejo, un dato o una herramienta sin URL no se busca a ciegas).

Sin sesion ni token (no hay clave de GitHub en NEXO): 60 consultas/hora y 10 busquedas/minuto. Si GitHub dice que
no queda cuota, se para (SinCuota) y lo que falte queda "pendiente: sin cuota" para la siguiente pasada; nunca se
reintenta en bucle. Lo resuelto se guarda en una cache privada (memoria/perfil_privado/reels/resoluciones.json, 7 dias).
A GitHub solo va el nombre de un elemento suelto, nunca la lista ni la coleccion.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from nucleo import reels_calidad as C
from nucleo.config import RAIZ

CACHE = RAIZ / "memoria" / "perfil_privado" / "reels" / "resoluciones.json"
API = "https://api.github.com"
DIAS_CACHE = 7
PAUSA_BUSQUEDA = 6.5          # s entre busquedas (10/minuto sin token)
CABECERAS = {"Accept": "application/vnd.github+json", "User-Agent": "NEXO-reels/1.0 (T859)",
             "X-GitHub-Api-Version": "2022-11-28"}


class SinCuota(RuntimeError):
    """GitHub no deja mas consultas hasta `reset` (epoch)."""

    def __init__(self, reset: int | None = None):
        super().__init__(f"sin cuota de GitHub hasta {reset}")
        self.reset = reset


def _plano(texto: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (texto or "").lower())


def _get(url: str, timeout: float = 20) -> tuple[int, dict | list | None, dict]:
    req = urllib.request.Request(url, headers=CABECERAS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 - solo api.github.com
            return r.status, json.load(r), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, None, dict(e.headers or {})


def _head(url: str, timeout: float = 15) -> int:
    for metodo in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=metodo, headers={"User-Agent": CABECERAS["User-Agent"]})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 - URL publica citada en el reel
                return r.status
        except urllib.error.HTTPError as e:
            if e.code in (405, 403, 501) and metodo == "HEAD":
                continue
            return e.code
        except Exception:   # noqa: BLE001 - DNS, TLS, tiempo: no responde
            return 0
    return 0


def _sin_cuota(estado: int, cab: dict) -> bool:
    cab = {k.lower(): v for k, v in (cab or {}).items()}
    return estado == 429 or (estado == 403 and str(cab.get("x-ratelimit-remaining", "1")) == "0")


def _reset(cab: dict) -> int | None:
    cab = {k.lower(): v for k, v in (cab or {}).items()}
    try:
        return int(cab.get("x-ratelimit-reset"))
    except (TypeError, ValueError):
        return None


def _datos_repo(d: dict, origen: str) -> dict:
    return {"existe": True, "origen": origen, "canonico": d.get("full_name"), "url": d.get("html_url"),
            "estrellas": d.get("stargazers_count"), "licencia": (d.get("license") or {}).get("spdx_id"),
            "ultima_actividad": d.get("pushed_at"), "archivado": bool(d.get("archived")),
            "descripcion": (d.get("description") or "")[:200], "topics": list(d.get("topics") or [])[:8]}


def repo(dueno: str, nombre: str, get=_get) -> dict | None:
    """Datos del repo o None si no existe (404). SinCuota si GitHub corta."""
    est, d, cab = get(f"{API}/repos/{urllib.parse.quote(dueno)}/{urllib.parse.quote(nombre)}")
    if _sin_cuota(est, cab):
        raise SinCuota(_reset(cab))
    if est == 200 and isinstance(d, dict):
        return _datos_repo(d, "api")
    return None


def buscar(nombre: str, get=_get, dormir=time.sleep, contexto: str | None = None) -> dict:
    """Busca por nombre exacto. {"existe": True, ...} | {"existe": None, "nota", "candidatos"}.
    T966: con `contexto` (lo que el reel dice del elemento) el candidato tiene que ENCAJAR por su descripcion; sin
    contexto utilizable no se acepta nada (Foreman, el supervisor de agentes, no es ddollar/foreman, el gestor Ruby)."""
    q = urllib.parse.quote(f"{nombre} in:name")
    dormir(PAUSA_BUSQUEDA)
    est, d, cab = get(f"{API}/search/repositories?q={q}&sort=stars&order=desc&per_page=10")
    if _sin_cuota(est, cab):
        raise SinCuota(_reset(cab))
    if est != 200 or not isinstance(d, dict):
        return {"existe": None, "nota": f"busqueda fallida ({est})", "candidatos": []}
    items = d.get("items") or []
    exactos = [i for i in items if _plano(i.get("name")) == _plano(nombre)]
    otros = [i.get("full_name") for i in items[:3]]
    if not exactos:
        return {"existe": None, "nota": "sin candidato con ese nombre exacto", "candidatos": otros}
    if contexto is not None:
        encajan = [i for i in exactos if C.encaja(i.get("description") or "", contexto, i.get("topics"))[0]]
        if not encajan:
            desc = "; ".join(f"{i.get('full_name')}: {(i.get('description') or 'sin descripcion')[:60]}"
                             for i in exactos[:3])
            return {"existe": None, "candidatos": [i.get("full_name") for i in exactos[:4]],
                    "nota": ("hay repos con ese nombre pero ninguno encaja con lo que dice el reel (" + desc + ")")
                    if plano_ctx(contexto) else "sin descripcion del reel para contrastar el repo"}
        exactos = encajan
    mejor = max(exactos, key=lambda i: i.get("stargazers_count") or 0)
    r = _datos_repo(mejor, "busqueda")
    r["candidatos"] = [i.get("full_name") for i in exactos if i is not mejor][:4]
    return r


def plano_ctx(contexto: str | None) -> str:
    return _plano(contexto)


def contexto_de(e: dict) -> str:
    """Lo que el reel dice del elemento: lineas de pantalla bajo su nombre, frase del pie y 'que es'."""
    return " ".join(str(e.get(k) or "") for k in ("descripcion_pantalla", "descripcion_pie", "que_es"))


def _url_de(e: dict) -> str | None:
    u = (e.get("url") or "").strip()
    if not u:
        return None
    if not re.match(r"(?i)https?://", u):
        u = "https://" + u.lstrip("/")
    return u


def resolver_elemento(e: dict, get=_get, head=_head, dormir=time.sleep) -> dict:
    if e.get("tipo") == "repo":
        nombre = e.get("nombre") or ""
        if e.get("dueno"):
            r = repo(e["dueno"], nombre, get)
            if r:
                return r
            if e.get("origen") == "citas":       # lectura literal: si no existe, no se busca a ciegas
                return {"existe": False, "nota": f"{e['dueno']}/{nombre} no existe en GitHub"}
            b = buscar(nombre, get, dormir, contexto_de(e))
            if b.get("existe"):
                b["nota"] = f"{e['dueno']}/{nombre} no existe; encontrado por nombre"
                return b
            return {"existe": False, "nota": f"{e['dueno']}/{nombre} no existe en GitHub",
                    "candidatos": b.get("candidatos", [])}
        return buscar(nombre, get, dormir, contexto_de(e))
    u = _url_de(e)
    if u and "github.com/" in u.lower():
        m = re.search(r"github\.com/([\w.-]+)/([\w.-]+)", u, re.I)
        if m:
            r = repo(m.group(1), m.group(2).removesuffix(".git"), get)
            return r or {"existe": False, "nota": "repo de la URL no existe"}
    if u:
        est = head(u)
        return {"existe": 0 < est < 400, "origen": "web", "url": u, "http": est}
    return {"existe": None, "nota": "no aplica (no es repo ni trae URL)"}


def _clave(e: dict) -> str:
    # T966 (v2): la resolucion de un repo depende de lo que el reel dice de el (una cache vieja aceptaba homonimos)
    ctx = hashlib.sha1(_plano(contexto_de(e)).encode()).hexdigest()[:8] if e.get("tipo") == "repo" else ""
    return f"v2|{e.get('tipo')}|{_plano(e.get('dueno'))}/{_plano(e.get('nombre'))}|{_plano(e.get('url'))}|{ctx}"


def cargar_cache(ruta: Path | None = None) -> dict:
    ruta = ruta or CACHE
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def guardar_cache(cache: dict, ruta: Path | None = None) -> None:
    ruta = ruta or CACHE
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ruta)


def resolver_ficha(ficha: dict, get=_get, head=_head, dormir=time.sleep, cache: dict | None = None,
                   ahora: datetime | None = None) -> dict:
    """Resuelve cada elemento (en su sitio, campo `resolucion`) y devuelve un resumen. Un repo encontrado por busqueda
    recibe su dueno (marcado). Sin cuota: lo que falte queda pendiente y se para."""
    ahora = ahora or datetime.now()
    cache = {} if cache is None else cache
    res = {"resueltos": 0, "no_existen": 0, "sin_resolver": 0, "pendientes": 0, "sin_cuota": None}
    for e in ficha.get("elementos", []):
        k = _clave(e)
        c = cache.get(k)
        if c and ahora - datetime.fromisoformat(c["cuando"]) < timedelta(days=DIAS_CACHE):
            r = c["r"]
        elif res["sin_cuota"] is not None:
            r = {"existe": None, "nota": "pendiente: sin cuota de GitHub"}
        else:
            try:
                r = resolver_elemento(e, get, head, dormir)
                cache[k] = {"cuando": ahora.isoformat(timespec="seconds"), "r": r}
            except SinCuota as s:
                res["sin_cuota"] = s.reset
                r = {"existe": None, "nota": "pendiente: sin cuota de GitHub"}
        e["resolucion"] = r
        if r.get("existe") and r.get("origen") == "busqueda" and not e.get("dueno") and r.get("canonico"):
            e["dueno"] = r["canonico"].split("/")[0]
            e["dueno_por_busqueda"] = True
        if r.get("existe"):
            res["resueltos"] += 1
        elif r.get("existe") is False:
            res["no_existen"] += 1
        elif "pendiente" in (r.get("nota") or ""):
            res["pendientes"] += 1
        else:
            res["sin_resolver"] += 1
    return res
