# -*- coding: utf-8 -*-
"""T890 punto 1: lo que un reel promete enviar ("te mando el paper") se intenta resolver EN PUBLICO antes de darlo
por hueco de Damian. Busqueda GRATUITA y sin clave: Crossref (works) para papers/estudios. Sin IA: el candidato se
acepta solo si comparte suficientes palabras significativas con el tema del reel; aun aceptado queda marcado
"por busqueda, sin verificar" (confianza media). Guias, prompts, plantillas o listas privadas NO se buscan: no hay
nada publico equivalente (lo cubre Damian, ver reels_huecos).
A Crossref solo va una consulta corta hecha con el tema del reel, nunca la lista ni la coleccion.

T966: si el modelo reconoce el paper (`titulo_probable`), se busca POR TITULO en varias fuentes gratuitas y sin clave
(Crossref, arXiv, Semantic Scholar; SSRN y NBER salen en Crossref) y se acepta el candidato cuyo titulo coincide con el
probable (similitud de palabras). Solo si eso no acierta se cae a la busqueda por palabras clave de antes."""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

CROSSREF = "https://api.crossref.org/works"
CABECERAS = {"User-Agent": "NEXO-reels/1.0 (T890; mailto:nexo@localhost)"}
ES_PAPER = re.compile(r"(?i)\b(paper|papers|study|studies|research|estudio|estudios|investigaci[oó]n|art[ií]culo|"
                      r"whitepaper|white paper)\b")
MIN_COMUN = 4                 # palabras significativas en comun para aceptar un candidato...
MIN_RATIO = 0.4               # ...y que sean al menos esta parte de las del titulo (frases genericas casan con cualquier cosa)
_VACIAS = {"the", "and", "for", "with", "that", "this", "from", "into", "than", "more", "your", "about", "how",
           "what", "when", "which", "are", "was", "were", "has", "have", "los", "las", "una", "uno", "con", "por",
           "para", "que", "del", "como", "sobre", "entre", "mas", "pero", "sus", "esta", "este",
           "most", "important", "year", "years", "means", "every", "each", "only", "over", "very", "best", "made",
           "make", "does", "will", "would", "could", "should", "found", "some", "many", "much", "just", "like"}


def _palabras(texto: str) -> set[str]:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]+", t) if len(w) > 3 and w not in _VACIAS}


def _get(url: str, timeout: float = 20) -> dict | None:
    """JSON de la respuesta; si no es JSON (arXiv devuelve Atom/XML) -> {"_texto": ...}."""
    req = urllib.request.Request(url, headers=CABECERAS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 - Crossref, arXiv, Semantic Scholar
            crudo = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    try:
        return json.loads(crudo)
    except ValueError:
        return {"_texto": crudo}


def es_papel(ficha: dict) -> bool:
    """Lo prometido es un paper/estudio (y el reel no lo nombra ya en publico)."""
    ll = ficha.get("llamada") or {}
    p = ficha.get("promesa") or {}
    if ll.get("nombrado_en_publico"):
        return False
    return bool(ES_PAPER.search(" ".join(str(x or "") for x in (ll.get("promete"), p.get("texto")))))


def consulta(ficha: dict) -> str:
    # Mejor: las palabras clave en ingles que dio el modelo para ese paper; si no, solo la afirmacion (mezclar idiomas desvia)
    base = str(ficha.get("consulta_publica") or ficha.get("afirmacion_principal") or ficha.get("tema") or "")
    return re.sub(r"\s+", " ", base).strip()[:200]


ARXIV = "http://export.arxiv.org/api/query"
SEMANTIC = "https://api.semanticscholar.org/graph/v1/paper/search"
MIN_SIMILITUD = 0.7           # F1 de palabras entre el titulo probable y el del candidato


def _tokens_titulo(titulo: str) -> set[str]:
    t = unicodedata.normalize("NFKD", (titulo or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]+", t) if len(w) > 2 and w not in _VACIAS}


def similitud(a: str, b: str) -> float:
    """F1 de las palabras significativas de dos titulos (0 a 1)."""
    ta, tb = _tokens_titulo(a), _tokens_titulo(b)
    if not ta or not tb:
        return 0.0
    comunes = len(ta & tb)
    if not comunes:
        return 0.0
    p, r = comunes / len(tb), comunes / len(ta)
    return 2 * p * r / (p + r)


def _por_titulo(titulo: str, get) -> list[dict]:
    """Candidatos de las fuentes gratuitas para un titulo probable: [{titulo, url, anio, fuente}]."""
    q = urllib.parse.quote(titulo)
    salida = []
    d = get(f"{CROSSREF}?rows=5&select=title,URL,issued&query.title={q}")
    for i in ((d or {}).get("message") or {}).get("items") or []:
        t = " ".join((i.get("title") or [""])[:1]).strip()
        if t and i.get("URL"):
            anio = ((i.get("issued") or {}).get("date-parts") or [[None]])[0][0]
            salida.append({"titulo": t[:200], "url": i["URL"], "anio": anio, "fuente": "crossref"})
    d = get(f"{ARXIV}?search_query=ti:%22{q}%22&max_results=3")
    for ent in re.findall(r"(?s)<entry>(.*?)</entry>", (d or {}).get("_texto") or ""):
        t = re.search(r"(?s)<title>(.*?)</title>", ent)
        u = re.search(r"<id>(.*?)</id>", ent)
        y = re.search(r"<published>(\d{4})", ent)
        if t and u:
            salida.append({"titulo": re.sub(r"\s+", " ", t.group(1)).strip()[:200], "url": u.group(1).strip(),
                           "anio": int(y.group(1)) if y else None, "fuente": "arxiv"})
    d = get(f"{SEMANTIC}?query={q}&limit=3&fields=title,year,url")
    for i in (d or {}).get("data") or []:
        if i.get("title") and i.get("url"):
            salida.append({"titulo": i["title"][:200], "url": i["url"], "anio": i.get("year"),
                           "fuente": "semanticscholar"})
    return salida


def buscar_por_titulo(ficha: dict, get=_get) -> dict | None:
    """T966: con el titulo probable del modelo. None si no hay titulo. Acepta el candidato de mayor similitud si
    llega a MIN_SIMILITUD."""
    titulo = re.sub(r"\s+", " ", str(ficha.get("titulo_probable") or "")).strip()
    if not titulo:
        return None
    cands = _por_titulo(titulo, get)
    for c in cands:
        c["similitud"] = round(similitud(titulo, c["titulo"]), 2)
    cands.sort(key=lambda c: -c["similitud"])
    mejor = next((c for c in cands if c["similitud"] >= MIN_SIMILITUD), None)
    return {"consulta": titulo, "por": "titulo", "candidatos": cands[:3], "aceptado": mejor}


def buscar_prometido(ficha: dict, get=_get) -> dict | None:
    """None si no aplica. Si aplica: {"consulta", "candidatos": [{titulo, url, anio, comunes}], "aceptado": cand|None}.
    T966: primero por titulo probable (varias fuentes); si no acierta, por palabras clave en Crossref."""
    if not es_papel(ficha):
        return None
    por_titulo = buscar_por_titulo(ficha, get)
    if por_titulo and por_titulo["aceptado"]:
        return por_titulo
    q = consulta(ficha)
    if not q:
        return por_titulo
    url = f"{CROSSREF}?rows=5&select=title,URL,issued&query.bibliographic={urllib.parse.quote(q)}"
    d = get(url)
    items = ((d or {}).get("message") or {}).get("items") or []
    ref = _palabras(q + " " + (ficha.get("resumen") or ""))
    cands = []
    for i in items:
        titulo = " ".join((i.get("title") or [""])[:1]).strip()
        if not titulo or not i.get("URL"):
            continue
        propias = _palabras(titulo)
        comunes = sorted(propias & ref)
        anio = ((i.get("issued") or {}).get("date-parts") or [[None]])[0][0]
        cands.append({"titulo": titulo[:200], "url": i["URL"], "anio": anio, "comunes": comunes,
                      "_r": len(comunes) / max(1, len(propias))})
    cands.sort(key=lambda c: (len(c["comunes"]), c["_r"]), reverse=True)
    mejor = next((c for c in cands if len(c["comunes"]) >= MIN_COMUN and c["_r"] >= MIN_RATIO), None)
    for c in cands:
        c.pop("_r")
    if por_titulo:     # lo hallado por titulo (sin acierto seguro) tambien se ensena como candidato
        cands = (por_titulo["candidatos"] + cands)[:3]
    return {"consulta": q, "candidatos": cands[:3], "aceptado": mejor}


def aplicar(ficha: dict, resultado: dict | None) -> dict:
    """Guarda la busqueda en la ficha y, si hay candidato aceptado, lo anade como elemento (origen "busqueda")."""
    if not resultado:
        return ficha
    ficha["busqueda_publica"] = resultado
    a = resultado.get("aceptado")
    if a and not any(e.get("url") == a["url"] for e in ficha.get("elementos", [])):
        ficha.setdefault("elementos", []).append({
            "tipo": "web", "nombre": a["titulo"], "dueno": None, "url": a["url"],
            "que_es": f"Paper candidato ({a.get('anio') or 's/f'}) hallado por busqueda publica "
                      f"({a.get('fuente') or 'Crossref'}{', por titulo' if a.get('similitud') else ''}), "
                      f"sin verificar que sea el del reel",
            "para_que": "es lo que el reel promete enviar", "categorias": _cats(ficha), "fuentes": ["busqueda"],
            "confianza": "media", "en_promesa": False, "origen": "busqueda", "verificado": True})
    return ficha


def _cats(ficha: dict) -> list[str]:
    for e in ficha.get("elementos", []):
        if e.get("tipo") == "dato" and e.get("categorias"):
            return list(e["categorias"])
    return ["sin_clasificar"]
