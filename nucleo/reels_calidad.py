# -*- coding: utf-8 -*-
"""T966: control de calidad SIN IA de las fichas de reels (REVISION_CLAUDE_2026-10-17.md).

Todo son funciones puras que llaman reels_ficha (normalizar), reels_resolver (encaje de repos), reels_huecos y
reels_tareas:

  corregir_ocr         Al->AI, l/I y 0/O en nombres leidos por OCR ('TogetherAl', 'Aria-lcons', '0pen Graph')
  descripcion_pantalla las lineas de descripcion que salen en pantalla debajo del nombre de un elemento
  encaja               un repo solo vale si su descripcion encaja con lo que el reel dice de el
  repo_basura          'mi-app', '.claude-', 'plugin.json' no son repos
  clasificar_url       cada URL suelta se clasifica (repo, cuenta, red social, documentacion, acortador...)
  alfabeto_ajeno       CJK, cirilico, arabe... en un texto que debe ir en espanol
  problemas_texto      campos de la ficha con alfabeto ajeno, en ingles o con 'para que' pobre/repetido
  retipar              idea de proyecto != idea de negocio; personas y cuentas no son 'dato'
  seguridad            saltarse permisos / autonomia total -> Fuera; sin censura / descargar videos -> Damian; obsoleto
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse


def plano(texto: str | None) -> str:
    s = unicodedata.normalize("NFKD", (texto or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s)


SIN_USO = "sin uso claro"   # 'para que' honesto cuando el elemento no tiene un uso concreto para Damian o NEXO


def recortar(texto: str | None, maximo: int = 200) -> str:
    """Recorta `texto` a `maximo` caracteres SIN partir una frase a medias: en el ultimo final de frase, si no en la
    ultima palabra entera, y con '…' cuando se ha quitado algo."""
    t = re.sub(r"\s+", " ", str(texto or "")).strip()
    if len(t) <= maximo:
        return t
    corte = t[:maximo - 1]
    fin = max(corte.rfind(x) for x in (". ", "! ", "? ", "; "))
    if fin >= maximo // 2:
        return corte[:fin + 1].strip()
    palabra = corte.rfind(" ")
    return (corte[:palabra] if palabra >= maximo // 2 else corte).rstrip(" ,;:-") + "…"


# ------------------------------------------------------------------ OCR
# palabras en las que el OCR lee 'l' (ele minuscula) donde va 'I' (i mayuscula): Icons, Image, Index, Input...
_CON_I = ("icon", "image", "img", "index", "input", "insight", "instant", "intel", "inter", "invoice", "issue", "item",
          "inbox", "info", "init", "insta", "install", "ide", "idea", "ink", "iron", "ios", "ip", "it", "in", "is")
_PALABRAS_I = re.compile(r"(?i)^(" + "|".join(_CON_I) + r")")


def _l_por_i(trozo: str) -> str:
    """'lcons' -> 'Icons' si 'I'+resto empieza como una palabra con I conocida (y la 'l' no abre una palabra real)."""
    if len(trozo) >= 3 and trozo[0] == "l" and trozo[1].islower() and _PALABRAS_I.match("I" + trozo[1:]):
        # 'lcons' si; 'link', 'lint', 'list' no: la 'I' tendria que dar 'Ink', 'Ilist'... se exige consonante dificil detras
        if trozo[1] not in "aeiou" and not trozo.lower().startswith(("lin", "lis", "lit", "liv", "log")):
            return "I" + trozo[1:]
    return trozo


def corregir_ocr(nombre: str | None) -> str:
    """Arregla los fallos tipicos del OCR en NOMBRES (no en texto libre: 'Al' puede ser 'al' en castellano)."""
    if not nombre:
        return nombre or ""
    s = str(nombre).strip()
    # 0 -> O dentro de palabras ('0pen', 'Op3n' no): un cero pegado a letras minusculas o entre letras
    s = re.sub(r"(?<![0-9A-Za-z])0(?=[a-z]{2,})", "O", s)
    s = re.sub(r"(?<=[A-Za-z])0(?=[A-Za-z])", "o", s)
    # Al -> AI: sufijo CamelCase ('TogetherAl', 'MistralAl') o palabra suelta 'Al' delante de otra ('Al receptionist')
    s = re.sub(r"(?<=[a-z])Al\b", "AI", s)
    s = re.sub(r"\bAl(?=[ -][a-z])", "AI", s)
    s = re.sub(r"\bAl$", "AI", s) if re.search(r"[A-Za-z]", s.replace("Al", "", 1)) and " " in s else s
    # l -> I tras guion o al empezar palabra ('Aria-lcons')
    s = re.sub(r"(?<=[-_ /.])([l][a-z]+)", lambda m: _l_por_i(m.group(1)), s)
    s = re.sub(r"^([l][a-z]+)", lambda m: _l_por_i(m.group(1)), s)
    return s


# ------------------------------------------------------------------ descripcion en pantalla
_ENCABEZADO = re.compile(r"^#\s*\d{1,2}$")
_FOTOGRAMA = re.compile(r"^\[fotograma [\d-]+ · [\d:]+\]$")


def descripcion_pantalla(mat: str, nombre: str, maximo: int = 360) -> str:
    """Las lineas de descripcion que salen en pantalla JUSTO debajo del nombre (hasta el siguiente '#n' o fotograma).
    El OCR de pantalla pierde los espacios: se devuelve tal cual (se compara luego sin espacios). '' si no aparece."""
    clave = plano(nombre)
    if len(clave) < 3:
        return ""
    pantalla = mat.split("[PANTALLA]", 1)[-1] if "[PANTALLA]" in mat else ""
    lineas = pantalla.splitlines()
    for i, lin in enumerate(lineas):
        if _FOTOGRAMA.match(lin) or _ENCABEZADO.match(lin.strip()):
            continue
        if clave not in plano(lin) or len(lin.strip()) > len(nombre) + 12:   # el nombre solo, como titulo del bloque
            continue
        cola = []
        for sig in lineas[i + 1:i + 9]:
            if _FOTOGRAMA.match(sig) or _ENCABEZADO.match(sig.strip()):
                break
            if sig.strip():
                cola.append(sig.strip())
        texto = " ".join(cola)
        if len(plano(texto)) >= 25:
            return texto[:maximo]
    return ""


# ------------------------------------------------------------------ encaje de un repo con lo que dice el reel
_VACIAS_ENCAJE = {"with", "that", "this", "from", "your", "into", "for", "and", "the", "based", "using", "open",
                  "source", "tool", "tools", "simple", "easy", "fast", "modern", "built", "build", "app", "apps",
                  "application", "applications", "project", "library", "framework", "free", "support", "supports",
                  "manage", "make", "makes", "create", "creates", "provide", "provides", "more", "than", "like",
                  "code", "github"}


def _claves(texto: str) -> list[str]:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [w for w in dict.fromkeys(re.findall(r"[a-z0-9]+", t)) if len(w) >= 4 and w not in _VACIAS_ENCAJE]


def encaja(descripcion_repo: str, contexto: str, topics: list[str] | None = None) -> tuple[bool, list[str]]:
    """¿La descripcion (y topics) de un repo de GitHub encaja con lo que el reel dice del elemento (`contexto`: lineas de
    pantalla + frase del pie + 'que es')? Palabras significativas de la descripcion del repo que aparecen en el
    contexto (comparado SIN espacios: el OCR de pantalla los pierde). Hacen falta 2 (o 1 si la descripcion del repo
    es muy corta). Sin descripcion o sin contexto no se puede decir que encaje."""
    ctx = plano(contexto)
    palabras = _claves(" ".join([descripcion_repo or ""] + [str(t) for t in topics or []]))
    if not ctx or not palabras:
        return False, []
    comunes = [w for w in palabras if w in ctx]
    return (len(comunes) >= 2 or (len(comunes) >= 1 and len(palabras) <= 3)), comunes


# ------------------------------------------------------------------ repos basura de 'citas' y URLs sueltas
_EXT = re.compile(r"\.(json|md|py|js|ts|tsx|jsx|yml|yaml|toml|txt|png|jpg|jpeg|gif|svg|html|css|sh|ps1|bat|lock|cfg|ini|env)$", re.I)
_PLACEHOLDER = {"mi-app", "my-app", "mi-repo", "my-repo", "mi-proyecto", "my-project", "tu-repo", "your-repo",
                "tu-usuario", "your-username", "username", "user", "usuario", "owner", "org", "repo", "example",
                "ejemplo", "foo", "bar", "path", "src", "lib", "bin", "docs", "dist", "build", "node_modules",
                "app", "project", "proyecto", "name", "nombre", "xxx", "tu-app", "tu-proyecto", "your-app",
                "your-project", "claude", ".claude", "home", "users", "tmp", "etc", "usr", "var", "opt"}
_PAREJAS = {"and/or", "input/output", "client/server", "read/write", "yes/no", "on/off", "true/false", "try/catch",
            "ctrl/cmd", "alt/option", "front/back", "frontend/backend", "pros/cons", "i/o", "w/o", "n/a", "24/7",
            "ci/cd", "tcp/ip", "http/https", "ui/ux", "q/a", "r/w", "he/she", "his/her", "s/he", "either/or"}


def repo_basura(repo: str) -> str:
    """'' si 'dueno/repo' puede ser un repo; si no, por que no."""
    if "/" not in repo:
        return "no es dueno/repo"
    dueno, nombre = repo.split("/", 1)
    if repo.lower() in _PAREJAS:
        return "pareja de palabras, no un repo"
    for parte in (dueno, nombre):
        if not parte or parte[0] in "-." and parte.lower() not in _PLACEHOLDER and parte in (dueno,):
            return f"'{parte}' no puede ser un dueno"
    if dueno.endswith(("-", ".")) or nombre.endswith("-") or dueno.startswith(("-", ".")):
        return "nombre cortado por el OCR (acaba o empieza en guion/punto)"
    if dueno.lower() in _PLACEHOLDER or nombre.lower() in _PLACEHOLDER:
        return "marcador de ejemplo (mi-app, tu-usuario...)"
    if _EXT.search(nombre) or _EXT.search(dueno):
        return "es un archivo (plugin.json...), no un repo"
    if len(dueno) < 3 or len(nombre) < 3:
        return "trozo demasiado corto"
    return ""


_SOCIAL = ("instagram.com", "cdninstagram.com", "facebook.com", "fbcdn.net", "x.com", "twitter.com", "tiktok.com",
           "linkedin.com", "youtube.com", "youtu.be", "t.me", "discord.gg", "discord.com", "threads.net", "reddit.com",
           "twitch.tv", "whatsapp.com", "wa.me", "patreon.com", "ko-fi.com", "buymeacoffee.com", "substack.com")
_ACORTADOR = ("bit.ly", "t.co", "tinyurl.com", "lnkd.in", "goo.gl", "ow.ly", "buff.ly", "linktr.ee", "beacons.ai",
              "taplink.cc", "bio.link", "carrd.co", "link.tree")
_DOCS = ("docs.", "readthedocs.io", "gitbook.io", "developer.", "developers.", "/docs", "/documentation", "/guide",
         "/api", "wiki")
_PAPERS = ("arxiv.org", "doi.org", "ssrn.com", "semanticscholar.org", "researchgate.net", "nber.org", "scholar.google",
           "papers.", "openreview.net", "aclanthology.org", "biorxiv.org", "pubmed")
_NUBE_MODELOS = ("huggingface.co", "civitai.com", "ollama.com", "kaggle.com")


def clasificar_url(url: str) -> dict:
    """{'clase', 'repo'?, 'cuenta'?}: repo | cuenta_github | red_social | acortador | paper | modelo | documentacion |
    herramienta. Las que no son herramienta/paper/modelo/documentacion/repo NO se vuelven elemento de la ficha."""
    u = url if re.match(r"(?i)https?://", url) else "https://" + url.lstrip("/")
    p = urlparse(u)
    host = (p.netloc or "").lower().removeprefix("www.")
    ruta = [x for x in p.path.split("/") if x]
    if host == "github.com":
        if len(ruta) >= 2 and not repo_basura(f"{ruta[0]}/{ruta[1].removesuffix('.git')}"):
            return {"clase": "repo", "repo": f"{ruta[0]}/{ruta[1].removesuffix('.git')}"}
        return {"clase": "cuenta_github", "cuenta": ruta[0] if ruta else ""}
    if any(host == h or host.endswith("." + h) for h in _SOCIAL):
        return {"clase": "red_social", "cuenta": ruta[0] if ruta else ""}
    if any(host == h or host.endswith("." + h) for h in _ACORTADOR):
        return {"clase": "acortador"}
    if any(h in host or h in u.lower() for h in _PAPERS):
        return {"clase": "paper"}
    if any(host == h or host.endswith("." + h) for h in _NUBE_MODELOS):
        return {"clase": "modelo"}
    if any(h in host or h in p.path.lower() for h in _DOCS):
        return {"clase": "documentacion"}
    return {"clase": "herramienta"}


CLASES_ELEMENTO = {"paper", "modelo", "documentacion", "herramienta"}   # las demas van a ficha['urls_sueltas']


# ------------------------------------------------------------------ idioma
def alfabeto_ajeno(texto: str | None) -> str:
    """Primer caracter de un alfabeto que no es el latino (CJK, cirilico, arabe, hebreo, tailandes, hangul...), o ''."""
    for c in texto or "":
        if ord(c) < 0x250 or not c.isalpha():
            continue
        n = unicodedata.name(c, "")
        if n.startswith(("LATIN", "GREEK")) and not n.startswith("GREEK"):
            continue
        if n.startswith("LATIN"):
            continue
        return c
    return ""


_ES = {"el", "la", "los", "las", "de", "del", "que", "y", "en", "un", "una", "para", "con", "por", "es", "se", "su",
       "al", "lo", "como", "más", "mas", "sin", "sobre", "entre", "también", "cada", "esta", "este", "puede", "permite"}
_EN = {"the", "and", "of", "to", "is", "in", "for", "with", "that", "this", "your", "you", "are", "on", "it", "by",
       "an", "as", "or", "from", "can", "will", "has", "have", "into", "than", "its", "their", "which", "without"}


def es_ingles(texto: str | None) -> bool:
    """Texto libre (>=5 palabras) que esta mas en ingles que en espanol."""
    pal = re.findall(r"[a-záéíóúñü]+", (texto or "").lower())
    if len(pal) < 5:
        return False
    en, es = sum(p in _EN for p in pal), sum(p in _ES for p in pal)
    # un texto en espanol de 5+ palabras casi siempre lleva alguna palabra de enlace (de, la, que, en...): sin ninguna,
    # y mas aun si es de frases en ingles ('educational page explaining stock market concepts'), no vale como espanol
    return (en >= 2 and en > es) or (es == 0 and len(pal) >= 5)


# ------------------------------------------------------------------ 'para que' concreto y sin repetir
_GENERICO = re.compile(r"(?i)^(idea central del reel|[uú]til( para (todos|cualquiera|la gente|el estudiante))?\.?|"
                       r"herramienta [uú]til\.?|para (mejorar|aprender|crear contenido|ahorrar tiempo|el estudiante)\.?|"
                       r"interesante\.?|sirve para (muchas cosas|todo)\.?|n/?a|-|—|\?|"
                       r"para quien guarda el reel.*|referencia de contenido( divulgativo)?\.?)$")
_DEL_CREADOR = re.compile(r"(?i)\b(el creador|la creadora|el autor del reel|del reel|de la cuenta|del influencer|"
                          r"startup (del|de la) creador|su (propio )?(negocio|canal|cuenta))\b")


def para_que_pobre(e: dict, otros: list[dict]) -> str:
    """'' si el 'para que' vale; si no, el motivo: vacio/generico, sobre el creador del reel o igual al de otro."""
    t = re.sub(r"\s+", " ", str(e.get("para_que") or "")).strip()
    if e.get("origen") == "afirmacion" or plano(t) == plano(SIN_USO):
        return ""
    if len(plano(t)) < 12 or _GENERICO.match(t):
        return "vacio o generico"
    if _DEL_CREADOR.search(t):
        return "habla del creador del reel, no de lo que sirve a NEXO/Damian"
    pt = plano(t)
    for o in otros:
        if o is not e and o.get("origen") != "afirmacion" and plano(o.get("para_que")) == pt:
            return "repetido en otro elemento"
    return ""


def problemas_texto(ficha: dict) -> dict:
    """{'alfabeto': [campos], 'ingles': [campos], 'para_que': {nombre: motivo}} (todo vacio = la ficha esta bien)."""
    alf, ing = [], []

    def mirar(campo: str, texto: str | None) -> None:
        if alfabeto_ajeno(texto):
            alf.append(campo)
        elif es_ingles(texto):
            ing.append(campo)

    for campo in ("tema", "resumen", "afirmacion_principal"):
        mirar(campo, ficha.get(campo))
    pq = {}
    for e in ficha.get("elementos", []):
        for campo in ("nombre", "dueno"):
            if alfabeto_ajeno(e.get(campo)):
                alf.append(f"{e.get('nombre')}.{campo}")
        for campo in ("que_es", "para_que"):
            if e.get("origen") == "afirmacion" and campo == "nombre":
                continue
            mirar(f"{e.get('nombre')}.{campo}", e.get(campo))
        if e.get("tipo") not in ("repo",) or True:
            m = para_que_pobre(e, ficha.get("elementos", []))
            if m and e.get("origen") not in ("citas", "busqueda"):
                pq[e.get("nombre")] = m
    return {"alfabeto": alf, "ingles": ing, "para_que": pq}


def quitar_alfabeto_ajeno(texto: str) -> str:
    """Ultimo recurso tras el reintento: quita los caracteres ajenos (la ficha queda marcada)."""
    limpio = "".join(c for c in texto or "" if not alfabeto_ajeno(c))
    return re.sub(r"\s{2,}", " ", limpio).strip()


# ------------------------------------------------------------------ tipos
_DINERO = re.compile(r"(?i)\b(vend\w+|ingres\w+|cliente\w*|suscripci\w+|monetiz\w+|negocio|ganar dinero|facturar|"
                     r"factur\w+|revenue|income|business|sell\w*|customers?|paying|subscription|saas|agencia|agency|"
                     r"freelanc\w+|cobrar|cobra\w*|mrr|startup|emprend\w+|lucr\w+|beneficios?)\b")
_PERSONA = re.compile(r"(?i)\b(cuenta|account|creador\w*|creator|perfil|profile|persona|people|profesor\w*|"
                      r"investigador\w*|researcher|economist\w*|economista\w*|trader\w*|autor\w*|author|fundador\w*|"
                      r"founder|ceo|cto|influencer|youtuber|programador\w*|ingeniero\w*)\b")
# Bloque 10: instituciones y empresas NO son 'cuenta' (cuenta = cuenta o persona): tienen su propio tipo
_ORG = re.compile(r"(?i)\b(organismo|instituci[oó]n|universidad|university|empresa|company|compa[nñ][ií]a|banco|bank|"
                  r"reserve|reserva|agencia|agency|fondo|fund|corporaci[oó]n|corporation|ministerio|gobierno|"
                  r"government|fundaci[oó]n|foundation|instituto|institute|laborator\w+|labs?|inc|ltd|"
                  r"asociaci[oó]n|bolsa|exchange)\b")
_ORG_INICIO = re.compile(r"(?i)^\W*(?:(?:el|la|los|las|un|una|the|a|an)\s+)?(?:organismo|instituci[oó]n|universidad|university|"
                         r"empresa|company|compa[nñ][ií]a|banco|bank|agencia|agency|fondo|fund|corporaci[oó]n|corporation|"
                         r"ministerio|gobierno|government|fundaci[oó]n|foundation|instituto|institute|laboratorio|"
                         r"asociaci[oó]n|bolsa|exchange)\b")


def _parece_nombre_propio(nombre: str) -> bool:
    n = nombre.strip()
    if n.startswith("@"):
        return True
    pal = n.split()
    return 1 <= len(pal) <= 4 and all(p[:1].isupper() for p in pal) and not re.search(r"\d", n) and len(n) <= 40


def retipar(e: dict) -> str | None:
    """Tipo corregido o None. idea_negocio sin dinero -> idea_proyecto; dato o cuenta que es una institucion o empresa ->
    organizacion; dato que es una persona/cuenta -> cuenta (cuenta = solo cuentas o personas)."""
    texto = " ".join(str(e.get(k) or "") for k in ("nombre", "que_es", "para_que"))
    if e.get("tipo") == "idea_negocio" and not _DINERO.search(texto):
        return "idea_proyecto"
    if e.get("tipo") in ("dato", "cuenta") and e.get("origen") != "afirmacion":
        nombre = str(e.get("nombre") or "").strip()
        que_es = str(e.get("que_es") or "")[:90]
        if nombre.startswith("@") or _PERSONA.search(nombre):          # una cuenta o una(s) persona(s)
            return "cuenta" if e.get("tipo") == "dato" else None
        if not re.search(r"\d", nombre) and (_ORG.search(nombre) or _ORG_INICIO.search(que_es)):
            return "organizacion"                                       # 'Federal Reserve', 'Banco de Espana'
        if e.get("tipo") == "cuenta":
            return None
        if _parece_nombre_propio(nombre) and _PERSONA.search(texto):
            return "cuenta"
        # 'Hedge fund quant trader': 'creador del reel, trader...' -> una persona, no un dato (sin cifras en el nombre)
        if not re.search(r"\d", nombre) and _PERSONA.search(que_es):
            return "cuenta"
    return None


# ------------------------------------------------------------------ seguridad y obsolescencia
_PELIGRO = re.compile(r"(?i)(dangerously[-_ ]?skip[-_ ]?permissions?|skip[-_ ]?permissions?|bypass(ing)? permissions?|"
                      r"permission[s]?[-_ ]?mode[\"': ]+bypass|--dangerously|yolo mode|auto[-_ ]?approve (all|everything)|"
                      r"saltar(se)? (los )?permisos|sin (pedir )?permisos|autonom[ií]a total|full(y)? autonom\w+|"
                      r"total autonomy|sin (pedir )?confirmaci[oó]n|desactiv\w+ (los )?permisos|allow all tools|"
                      r"acceso total sin)")
_DAMIAN = re.compile(r"(?i)(sin censura|uncensored|abliterat\w+|decensor\w*|jailbreak\w*|sin filtros?|unfiltered|"
                     r"descarg\w+ (de )?(los )?v[ií]deos?|download(ing|er)? (instagram |youtube |tiktok )?videos?|"
                     r"video downloader|yt-dlp|scrap\w+ (instagram|tiktok|linkedin)|evad\w+ (la )?(detecci\w+|censura))")
_OBSOLETO = re.compile(r"(?i)\b(claude[- ]?(opus|sonnet|haiku)[- ]?[1-4](\.\d)?|claude[- ]?[1-4](\.\d)?\b|"
                       r"gpt[- ]?[1-4](\.\d)?(o|-turbo)?\b|gemini[- ]?[1-2](\.\d)?\b|llama[- ]?[1-3](\.\d)?\b|"
                       r"gemma[- ]?[1-2]\b|mistral[- ]7b|chatgpt[- ]?(3|4)\b)")


def seguridad(e: dict) -> dict | None:
    """{'nivel': 'peligro'|'damian'|'obsoleto', 'motivo'} o None.
    peligro  -> sale del plan (Fuera) con aviso de seguridad: pide saltarse permisos o dar autonomia total.
    damian   -> se marca para Damian (modelos sin censura, descargas de video): NEXO no lo investiga solo.
    obsoleto -> se descarta (modelo/version superada)."""
    texto = " ".join(str(e.get(k) or "") for k in ("nombre", "que_es", "para_que", "descripcion_pantalla"))
    if _PELIGRO.search(texto):
        return {"nivel": "peligro", "motivo": "pide saltarse permisos o dar autonomia total: nunca como investigacion"}
    if _DAMIAN.search(texto):
        return {"nivel": "damian", "motivo": "modelos sin censura o descarga de videos: lo decide Damian"}
    if e.get("tipo") in ("modelo", "herramienta", "tecnica", "repo", "web", "consejo") and _OBSOLETO.search(
            str(e.get("nombre") or "")):
        return {"nivel": "obsoleto", "motivo": "version de modelo superada"}
    return None


def frase_pie(mat: str, nombre: str, maximo: int = 320) -> str:
    """Frases del pie del reel donde se nombra el elemento (lo que el creador dice de el). '' si no aparece."""
    clave = plano(nombre)
    if len(clave) < 3 or "[PIE]" not in mat:
        return ""
    pie = mat.split("[PIE]", 1)[1].split("[AUDIO]", 1)[0]
    frases = re.split(r"(?<=[.!?])\s+|\n+", pie)
    hit = [f.strip() for f in frases if clave in plano(f) or clave in plano(corregir_ocr(f))]
    return " ".join(hit)[:maximo]
