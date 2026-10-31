# -*- coding: utf-8 -*-
"""T693 R1: motor comun de radares (diseno en documentacion/diseno/RADARES.md).

Un radar = un archivo `memoria/radares/<id>/config.json` (fuentes + filtros), no codigo nuevo. Cada pasada:
  1. LEE las fuentes con codigo (lectores `api`, `json`, `rss` y `vigia`, que reutiliza las fuentes del vigia T272);
     una fuente caida no tumba el resto y una fuente SIN `terminos` (como se respeta su web) no se lee nunca.
  2. DEDUPLICA por URL normalizada (sin parametros de rastreo), por parecido de titulo contra el almacen y dentro
     del lote, y marca lo que ya se descarto antes (registro T688).
  3. La primera lectura de una fuente es solo LINEA BASE: se guarda lo visto y no se publica nada.
  4. NOTA local (R2: `puntuar` del radar; sin el, todo vale lo mismo) y se quedan los `por_dia` mejores.
  5. PUBLICA tarjetas en el almacen `articulos.jsonl` (estado `nueva`). Nada vive solo en un texto.
En modo SIMULAR (el de R1: `"modo": "simular"` en el config o `simular=True`) hace lo mismo sobre un almacen y un
estado SOMBRA (`articulos_simulacion.jsonl`, `estado_simulacion.json`) y escribe un informe
`simulacion_AAAAMMDD_HHMM.json`: la linea base avanza igual, pero el almacen real no se toca.

No escribe tareas ni llama a ninguna IA. La PARADA y el interruptor de turnos los aplica turno_nexo.py.
CLI: .venv\\Scripts\\python.exe -m nucleo.radar lista | simular <radar> | pasada <radar> | tarjetas <radar>
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from nucleo import freno

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "memoria" / "radares"
TIMEOUT = 20
UA = {"User-Agent": "NEXO-radar/1.0 (asistente personal; lectura publica)"}
MAX_POR_FUENTE = 100
UMBRAL_TITULO = 0.8           # parecido de titulo (Jaccard de raices) para considerarlo el mismo articulo
ESTADOS = ("base", "filtrada", "nueva", "vista", "me_gusta", "guardada", "descartada", "caducada")
VISIBLES = ("nueva", "vista", "me_gusta", "guardada")
_RASTREO = re.compile(r"^(utm_\w+|fbclid|gclid|dclid|mc_cid|mc_eid|igshid|igsh|ref|ref_src|si|_hsenc|_hsmi|yclid)$", re.I)


def _get(url: str, params: dict | None = None, cabeceras: dict | None = None):
    import httpx
    return httpx.get(url, headers={**UA, **(cabeceras or {})}, params=params, timeout=TIMEOUT, follow_redirects=True)


# ------------------------------------------------------------------ URL e ids
def normalizar_url(url: str) -> str:
    """Esquema y host en minusculas, sin fragmento, sin parametros de rastreo y sin barra final."""
    p = urlsplit((url or "").strip())
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _RASTREO.match(k)])
    ruta = p.path.rstrip("/") or ""
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."), ruta, query, ""))


def id_articulo(url: str) -> str:
    return hashlib.sha1(normalizar_url(url).encode("utf-8")).hexdigest()[:12]


# ------------------------------------------------------------------ lectores
def _camino(dato, camino: str):
    """'data.items' o 'a.0.b' dentro de un JSON; '' es el propio dato."""
    for trozo in [c for c in (camino or "").split(".") if c]:
        dato = dato[int(trozo)] if isinstance(dato, list) else (dato or {}).get(trozo)
    return dato


def _limpio(texto) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", str(texto or "")).split())


def _fecha(valor) -> str:
    """AAAA-MM-DD de lo que venga (ISO, RFC 822 de RSS o epoch); '' si no se entiende."""
    if valor in (None, ""):
        return ""
    if isinstance(valor, (int, float)):
        return datetime.fromtimestamp(float(valor)).strftime("%Y-%m-%d")
    s = str(valor).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    try:
        return parsedate_to_datetime(s).strftime("%Y-%m-%d")
    except (TypeError, ValueError, IndexError):
        return ""


def _articulo(fuente: dict, url: str, titulo: str, fecha="", texto="") -> dict | None:
    if not url or not titulo:
        return None
    return {"id": id_articulo(url), "url": url.strip(), "fuente": fuente["id"], "titulo": _limpio(titulo)[:300],
            "fecha": _fecha(fecha), "texto": _limpio(texto)[:1500]}


def _extraer(items, fuente: dict) -> list[dict]:
    campos = {"titulo": "title", "url": "url", "fecha": "date", "texto": "description", **(fuente.get("campos") or {})}
    salida = []
    for it in (items or [])[:MAX_POR_FUENTE]:
        if not isinstance(it, dict):
            continue
        url = _camino(it, campos["url"])
        if fuente.get("url_base") and url and not str(url).startswith("http"):
            url = fuente["url_base"].rstrip("/") + "/" + str(url).lstrip("/")
        a = _articulo(fuente, str(url or ""), str(_camino(it, campos["titulo"]) or ""), _camino(it, campos["fecha"]),
                      _camino(it, campos["texto"]))
        if a:
            salida.append(a)
    return salida


def leer_api(fuente: dict, ahora: datetime, get=_get) -> list[dict]:
    """API JSON por HTTP (con `params` opcionales); `lista` dice donde estan los elementos."""
    r = get(fuente["url"], fuente.get("params"), fuente.get("cabeceras"))
    r.raise_for_status()
    return _extraer(_camino(r.json(), fuente.get("lista", "")), fuente)


def leer_json(fuente: dict, ahora: datetime, get=_get) -> list[dict]:
    """Documento JSON publicado (un feed JSON, un JSON Feed 1.1...) o un archivo local con `archivo:`."""
    url = fuente["url"]
    if url.startswith("archivo:"):
        datos = json.loads(Path(url[len("archivo:"):]).read_text(encoding="utf-8"))
    else:
        r = get(url, None, None)
        r.raise_for_status()
        datos = r.json()
    return _extraer(_camino(datos, fuente.get("lista", "items")), fuente)


_ATOM = "{http://www.w3.org/2005/Atom}"


def leer_rss(fuente: dict, ahora: datetime, get=_get) -> list[dict]:
    """RSS 2.0 o Atom. Se niegan los documentos con entidades declaradas (XXE / 'billion laughs')."""
    r = get(fuente["url"], None, {"Accept": "application/rss+xml, application/atom+xml, application/xml"})
    r.raise_for_status()
    texto = r.text
    if "<!ENTITY" in texto.upper():
        raise ValueError("el feed declara entidades XML: no se lee")
    raiz = ET.fromstring(texto.encode("utf-8") if isinstance(texto, str) else texto)
    salida = []
    for it in raiz.iter("item"):   # RSS 2.0
        salida.append(_articulo(fuente, it.findtext("link") or "", it.findtext("title") or "",
                                it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date") or "",
                                it.findtext("description") or ""))
    for e in raiz.iter(f"{_ATOM}entry"):   # Atom
        enlace = next((l.get("href") for l in e.findall(f"{_ATOM}link") if l.get("rel") in (None, "alternate")), "")
        salida.append(_articulo(fuente, enlace or "", e.findtext(f"{_ATOM}title") or "",
                                e.findtext(f"{_ATOM}published") or e.findtext(f"{_ATOM}updated") or "",
                                e.findtext(f"{_ATOM}summary") or e.findtext(f"{_ATOM}content") or ""))
    return [a for a in salida if a][:MAX_POR_FUENTE]


def leer_vigia(fuente: dict, ahora: datetime, get=_get) -> list[dict]:
    """Las fuentes fijas del vigia (T272) tal cual: `funcion` es su nombre en vigia.FUENTES."""
    from nucleo import vigia
    salida = []
    for it in vigia.FUENTES[fuente["funcion"]](ahora):
        a = _articulo(fuente, it.get("url") or "", it.get("nombre") or it.get("id") or "", it.get("fecha") or "",
                      it.get("descripcion") or "")
        if a:
            # varios modelos comparten la URL de la pagina (changelog, lista de Groq): el id del vigia los separa
            a["id"] = hashlib.sha1(f"{normalizar_url(a['url'])}#{it.get('id')}".encode("utf-8")).hexdigest()[:12]
            salida.append(a)
    return salida[:MAX_POR_FUENTE]


LECTORES = {"api": leer_api, "json": leer_json, "rss": leer_rss, "vigia": leer_vigia}


# ------------------------------------------------------------------ configuracion y almacen
def carpeta(radar_id: str) -> Path:
    if not re.match(r"^[a-z0-9_]+$", radar_id or ""):
        raise ValueError(f"id de radar no valido: {radar_id!r}")
    return CARPETA / radar_id


def cargar_config(radar_id: str) -> dict:
    cfg = json.loads((carpeta(radar_id) / "config.json").read_text(encoding="utf-8"))
    cfg.setdefault("id", radar_id)
    cfg.setdefault("por_dia", 5)
    cfg.setdefault("caducidad_dias", 30)
    cfg.setdefault("modo", "simular")
    cfg.setdefault("activo", True)
    cfg.setdefault("fuentes", [])
    return cfg


def radares() -> list[str]:
    if not CARPETA.exists():
        return []
    return sorted(p.parent.name for p in CARPETA.glob("*/config.json"))


def fuente_lista(f: dict) -> str | None:
    """None si la fuente se puede leer; si no, por que no."""
    if f.get("activa") is False:
        return f.get("motivo_inactiva") or "desactivada"
    if not str(f.get("terminos") or "").strip():
        return "sin terminos comprobados (como se respeta su web): no se lee"
    if f.get("tipo") not in LECTORES:
        return f"tipo de lector desconocido: {f.get('tipo')!r}"
    return None


def _sufijo(sim: bool) -> str:
    return "_simulacion" if sim else ""


def articulos(radar_id: str, sim: bool = False) -> list[dict]:
    ruta = carpeta(radar_id) / f"articulos{_sufijo(sim)}.jsonl"
    if not ruta.exists():
        return []
    salida = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            salida.append(json.loads(linea))
        except ValueError:
            continue
    return salida


def _guardar_articulos(radar_id: str, lista: list[dict], sim: bool = False) -> None:
    from nucleo.escritura import escribir_atomico
    carpeta(radar_id).mkdir(parents=True, exist_ok=True)
    escribir_atomico(carpeta(radar_id) / f"articulos{_sufijo(sim)}.jsonl",
                     "".join(json.dumps(a, ensure_ascii=False) + "\n" for a in lista))


def _leer_estado(radar_id: str, sim: bool = False) -> dict:
    try:
        return json.loads((carpeta(radar_id) / f"estado{_sufijo(sim)}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _escribir(radar_id: str, nombre: str, datos) -> Path:
    from nucleo.escritura import escribir_atomico
    carpeta(radar_id).mkdir(parents=True, exist_ok=True)
    ruta = carpeta(radar_id) / nombre
    escribir_atomico(ruta, json.dumps(datos, ensure_ascii=False, indent=1))
    return ruta


# ------------------------------------------------------------------ pasos
def leer_fuentes(cfg: dict, ahora: datetime, get=_get, lectores: dict | None = None) -> dict:
    lectores = lectores or LECTORES
    items, por_fuente, errores, saltadas = [], {}, {}, {}
    for f in cfg["fuentes"]:
        motivo = fuente_lista(f)
        if motivo:
            saltadas[f["id"]] = motivo
            continue
        try:
            leidos = lectores[f["tipo"]](f, ahora, get)
        except Exception as e:   # noqa: BLE001 - una fuente caida no tumba el resto
            errores[f["id"]] = f"{type(e).__name__}: {e}"[:200]
            continue
        por_fuente[f["id"]] = len(leidos)
        items += leidos
        if f.get("pausa"):
            time.sleep(float(f["pausa"]))
    return {"items": items, "por_fuente": por_fuente, "errores": errores, "saltadas": saltadas}


def deduplicar(items: list[dict], almacen: list[dict], reg_descartes: list[dict] | None = None,
               por_titulo: bool = True) -> tuple[list, dict]:
    """(nuevos, repetidos {id: motivo}). Mismo id/URL o titulo casi igual (almacen o el propio lote) = repetido.
    Los parecidos a algo DESCARTADO antes (T688) no se quitan: se marcan en `descartado_antes`."""
    ids = {a["id"] for a in almacen}
    urls = {normalizar_url(a["url"]) for a in almacen}
    titulos = [freno.palabras(a["titulo"]) for a in almacen]
    nuevos, repetidos = [], {}
    for it in items:
        pal = freno.palabras(it["titulo"])
        if it["id"] in ids or normalizar_url(it["url"]) in urls:
            repetidos[it["id"]] = "ya visto (misma URL)"
            continue
        if por_titulo and any(freno.parecido(pal, t) >= UMBRAL_TITULO for t in titulos):
            repetidos[it["id"]] = "ya visto (titulo casi igual)"
            continue
        if reg_descartes:
            from nucleo import descartes
            previos = descartes.buscar(it["titulo"], reg_descartes)
            if previos:
                it = {**it, "descartado_antes": previos[0]["id"]}
        nuevos.append(it)
        ids.add(it["id"])
        urls.add(normalizar_url(it["url"]))
        titulos.append(pal)
    return nuevos, repetidos


def _registro_descartes() -> list[dict]:
    try:
        from nucleo import descartes
        return descartes.registro()
    except Exception:   # noqa: BLE001 - el aviso es accesorio
        return []


def pasada(radar_id: str, ahora: datetime | None = None, simular: bool | None = None, get=_get,
           lectores: dict | None = None, puntuar=None) -> dict:
    """Una pasada del radar. `simular=None` usa el `modo` del config. `puntuar(cfg, articulo) -> (nota, motivo)`."""
    ahora = ahora or datetime.now()
    cfg = cargar_config(radar_id)
    if simular is None:
        simular = cfg["modo"] != "real"
    if cfg.get("clase") == "precios":   # T665: un precio por producto y dia, con historico (nucleo/precios.py)
        from nucleo import precios, precios_ia
        informe = precios.pasada(ahora, simular=simular, get=get)
        # 05/10: una vez a la semana, el precio preguntado a ChatGPT/Gemini web (nucleo/precios_ia.py). Solo en
        # una pasada real con la red de verdad (get=_get): los tests y las simulaciones nunca abren el navegador.
        if not simular and get is _get and precios_ia.toca(ahora):
            try:
                informe["ia"] = precios_ia.pasada(ahora)
            except Exception as e:   # noqa: BLE001 - la pasada diaria no cae por la de la IA
                informe["ia"] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
        return informe
    if puntuar is None:
        puntuar = _puntuador(cfg)
    estado = _leer_estado(radar_id, simular)
    almacen = articulos(radar_id, simular)
    leido = leer_fuentes(cfg, ahora, get, lectores)
    nuevos, repetidos = deduplicar(leido["items"], almacen, _registro_descartes(),
                                   por_titulo=cfg.get("dedup_titulo", True))
    vistas_antes = set(estado.get("fuentes_vistas") or [])
    base = [a for a in nuevos if a["fuente"] not in vistas_antes]
    candidatos = [a for a in nuevos if a["fuente"] in vistas_antes]
    for a in candidatos:
        nota, motivo = puntuar(cfg, a)
        a["nota"], a["motivo"] = nota, motivo
    umbral = cfg.get("umbral", 0)
    aptos = sorted([a for a in candidatos if a["nota"] is None or a["nota"] >= umbral],
                   key=lambda a: -(a["nota"] or 0))
    publicar = aptos[:int(cfg["por_dia"])]
    ids_pub = {a["id"] for a in publicar}
    informe = {"radar": radar_id, "cuando": ahora.isoformat(timespec="seconds"), "simular": simular,
               "por_fuente": leido["por_fuente"], "errores": leido["errores"], "saltadas": leido["saltadas"],
               "leidos": len(leido["items"]), "repetidos": len(repetidos), "linea_base": len(base),
               "fuentes_nuevas": sorted({a["fuente"] for a in base}), "candidatos": len(candidatos),
               "publicadas": [{k: a.get(k) for k in ("id", "titulo", "url", "fuente", "fecha", "nota", "motivo",
                                                      "descartado_antes")} for a in publicar]}
    if simular:
        informe["archivo"] = _escribir(radar_id, f"simulacion_{ahora:%Y%m%d_%H%M}.json", informe).name
    marca = ahora.isoformat(timespec="seconds")
    for a in base:
        almacen.append({**a, "estado": "base", "cuando": marca, "marcas": []})
    for a in candidatos:
        almacen.append({**a, "estado": "nueva" if a["id"] in ids_pub else "filtrada", "cuando": marca, "marcas": []})
    caducar(almacen, cfg, ahora)
    _guardar_articulos(radar_id, almacen, simular)
    estado.update(ultima=marca, fuentes_vistas=sorted(vistas_antes | set(leido["por_fuente"])),
                  ultimo=dict((k, informe[k]) for k in ("por_fuente", "errores", "saltadas", "leidos", "repetidos",
                                                        "linea_base", "candidatos")))
    _escribir(radar_id, f"estado{_sufijo(simular)}.json", estado)
    return informe


def caducar(almacen: list[dict], cfg: dict, ahora: datetime) -> int:
    """Las nuevas/vistas de mas de `caducidad_dias` pasan a `caducada` (se quedan en el archivo: no se borra nada)."""
    corte = (ahora - timedelta(days=int(cfg["caducidad_dias"]))).isoformat(timespec="seconds")
    n = 0
    for a in almacen:
        if a.get("estado") in ("nueva", "vista") and str(a.get("cuando") or "") < corte:
            a["estado"] = "caducada"
            n += 1
    return n


def _puntuador(cfg: dict):
    """R2: el radar elige su nota local (nucleo/radar_nota.py). Sin `nota` en el config, todos valen igual."""
    if not cfg.get("nota"):
        return lambda cfg_, art: (None, "")
    from nucleo import radar_nota
    return radar_nota.puntuador(cfg)


def tarjetas(radar_id: str, estados: tuple = VISIBLES, sim: bool = False) -> list[dict]:
    return sorted([a for a in articulos(radar_id, sim) if a.get("estado") in estados],
                  key=lambda a: (str(a.get("cuando") or ""), a.get("nota") or 0), reverse=True)


def vista_web(max_tarjetas: int = 20, max_base: int = 10) -> list[dict]:
    """Para la pestana provisional (R2): por radar, su estado, sus tarjetas y, mientras solo hay linea base, lo
    leido en la primera lectura con su nota local (no se publica: es para ver si el filtro acierta)."""
    salida = []
    for r in radares():
        try:
            cfg = cargar_config(r)
        except (OSError, ValueError) as e:
            salida.append({"id": r, "nombre": r, "error": type(e).__name__})
            continue
        sim = cfg["modo"] != "real"
        est = _leer_estado(r, sim)
        base = [a for a in articulos(r, sim) if a.get("estado") == "base"]
        if base:
            puntuar = _puntuador(cfg)
            for a in base:
                a["nota"], a["motivo"] = puntuar(cfg, a)
            base.sort(key=lambda a: -(a["nota"] or 0))
        salida.append({"id": r, "nombre": cfg.get("nombre") or r, "simular": sim, "activo": cfg["activo"],
                       "ultima": est.get("ultima"), "ultimo": est.get("ultimo") or {},
                       "fuentes": [{"id": f["id"], "url": f.get("url", ""), "motivo": fuente_lista(f)}
                                   for f in cfg["fuentes"]],
                       "tarjetas": tarjetas(r, sim=sim)[:max_tarjetas], "base": base[:max_base], "n_base": len(base)})
    return salida


# ------------------------------------------------------------------ turno
def ids_de_texto(texto: str) -> list[str]:
    """`radar=oportunidades,vigia` en las instrucciones del turno; sin eso, todos los radares activos."""
    m = re.search(r"radar\s*=\s*([a-z0-9_,\s]+)", texto or "")
    pedidos = [x.strip() for x in m.group(1).split(",") if x.strip()] if m else None
    return [r for r in radares() if (pedidos is None or r in pedidos)]


def hecho_hoy(radar_id: str, ahora: datetime | None = None) -> bool:
    ahora = ahora or datetime.now()
    hoy = ahora.strftime("%Y-%m-%d")
    return any(str(_leer_estado(radar_id, sim).get("ultima") or "").startswith(hoy) for sim in (False, True))


def candidatas(texto: str = "", ahora: datetime | None = None) -> int:
    """Radares activos que aun no han pasado hoy (la puerta del turno: sin esto no se despierta a nadie)."""
    n = 0
    for r in ids_de_texto(texto):
        try:
            if cargar_config(r)["activo"] and not hecho_hoy(r, ahora):
                n += 1
        except (OSError, ValueError):
            continue
    return n


def turno(texto: str = "", simular: bool = False, ahora: datetime | None = None, get=_get) -> dict:
    """Paso del turno `radar`: una pasada por radar activo que no haya pasado hoy. `simular=True` (turno en
    simulacion) fuerza el modo simular aunque el radar este en `real`."""
    ahora = ahora or datetime.now()
    hechos = {}
    for r in ids_de_texto(texto):
        try:
            cfg = cargar_config(r)
            if not cfg["activo"] or hecho_hoy(r, ahora):
                continue
            inf = pasada(r, ahora, simular=True if simular else None, get=get)
            hechos[r] = {k: inf[k] for k in ("simular", "leidos", "repetidos", "linea_base", "candidatos", "errores",
                                              "saltadas")} | {"publicadas": len(inf["publicadas"])}
        except Exception as e:   # noqa: BLE001 - un radar roto no tumba los demas
            hechos[r] = {"error": f"{type(e).__name__}: {e}"[:200]}
    return {"radares": hechos}


def texto_resumen(paso: dict) -> str:
    partes = []
    for r, h in (paso.get("radares") or {}).items():
        if "error" in h:
            partes.append(f"{r}: ERROR {h['error'][:80]}")
        else:
            partes.append(f"{r}{' (simulado)' if h.get('simular') else ''}: {h['leidos']} leídos, {h['repetidos']} "
                          f"repetidos, {h['publicadas']} tarjetas" + (f", caídas {', '.join(h['errores'])}" if h.get("errores") else ""))
    return "radar: " + ("; ".join(partes) if partes else "nada que hacer hoy")


# ------------------------------------------------------------------ vigia como radar (migracion R1)
def config_vigia() -> dict:
    """El vigia (T272) como radar, con sus mismas fuentes. En simulacion hasta que Damian lo pase a real."""
    terminos = {
        "github": "API REST publica de GitHub (search/repositories) sin clave, con pausas por el limite de 10/min",
        "ollama": "pagina publica de la biblioteca de Ollama (orden newest), una lectura al dia",
        "openrouter": "API publica /api/v1/models de OpenRouter",
        "nvidia": "API /v1/models de NVIDIA build con la clave de NEXO",
        "groq": "API /openai/v1/models de Groq con la clave de NEXO",
        "gemini_changelog": "pagina publica del changelog de la API de Gemini, una lectura al dia",
    }
    return {"id": "vigia", "nombre": "Novedades (vigía)", "activo": True, "modo": "simular", "por_dia": 5,
            "caducidad_dias": 30, "nota": None,
            "dedup_titulo": False,   # modelos distintos con nombres casi iguales (llama-8b / llama-70b)
            "fuentes": [{"id": n, "tipo": "vigia", "funcion": n, "terminos": t + " (heredado del vigia T272, 28/09)"}
                        for n, t in terminos.items()]}


def instalar_vigia() -> Path:
    """Crea memoria/radares/vigia/config.json si no existe (no pisa uno editado)."""
    ruta = carpeta("vigia") / "config.json"
    if not ruta.exists():
        _escribir("vigia", "config.json", config_vigia())
    return ruta


def _cli(argv: list[str]) -> int:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    orden, resto = (argv[0] if argv else "lista"), argv[1:]
    if orden == "lista":
        for r in radares():
            c = cargar_config(r)
            print(f"{r:<15} {c['modo']:<8} {'activo' if c['activo'] else 'apagado':<8} "
                  f"{len(c['fuentes'])} fuentes, {len(tarjetas(r))} tarjetas")
        return 0
    if orden == "instalar_vigia":
        print(instalar_vigia())
        return 0
    if orden in ("simular", "pasada") and resto:
        inf = pasada(resto[0], simular=orden == "simular")
        print(json.dumps({k: v for k, v in inf.items() if k != "publicadas"}, ensure_ascii=False, indent=1))
        for a in inf["publicadas"]:
            print(f"- [{a['fuente']}] {a['titulo'][:90]} ({a.get('nota')}) {a['url']}")
        return 0
    if orden == "tarjetas" and resto:
        for a in tarjetas(resto[0]):
            print(f"- {a['estado']:<8} {a.get('nota')} {a['titulo'][:90]}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    import sys
    raise SystemExit(_cli(sys.argv[1:]))
