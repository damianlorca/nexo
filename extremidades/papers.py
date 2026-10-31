"""Extremidad: investigacion academica.

Va directo a las fuentes en lugar de preguntarle a una IA por ellas:

- OpenAlex          ~250 M de trabajos, todas las disciplinas
- Semantic Scholar  resumenes, citas y referencias
- arXiv             preprints de fisica, matematicas, informatica
- Crossref          metadatos de DOI y citas formales

Las cuatro son APIs publicas y gratuitas, sin clave y sin nada que
incumplir. OpenAlex pide un correo de cortesia para darte prioridad
en la cola; no es autenticacion.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from nucleo.config import valor
from nucleo.registro import logger


log = logger("extremidades.papers")

TIEMPO = 25


class Bloqueado(httpx.HTTPError):
    """Retry-After enorme: bloqueo por IP, no cola. No se reintenta."""


def _retry_after(valor_cabecera: str | None, defecto: float) -> float:
    """Segundos de Retry-After. Acepta segundos o fecha HTTP (RFC 9110).

    B8 de N02: antes solo float(); una fecha lanzaba ValueError, que
    arxiv() no capturaba, y la busqueda entera reventaba.
    """

    if not valor_cabecera:
        return defecto

    try:
        return max(0.0, float(valor_cabecera))
    except ValueError:
        pass

    try:
        cuando = parsedate_to_datetime(valor_cabecera)
    except (TypeError, ValueError):
        return defecto

    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=timezone.utc)

    return max(0.0, (cuando - datetime.now(timezone.utc)).total_seconds())


def _get(url: str, parametros: dict, cabeceras: dict | None = None,
         intentos: int = 3) -> httpx.Response:
    """GET con reintento. Estas APIs son gratuitas y a veces devuelven
    429 cuando hay cola: esperar un poco casi siempre lo resuelve."""

    espera = 2.0
    ultimo: Exception | None = None

    for intento in range(intentos):
        try:
            r = httpx.get(
                url,
                params=parametros,
                headers=cabeceras or _cabeceras(),
                timeout=TIEMPO,
                follow_redirects=True,
            )

            if r.status_code in (429, 503):
                pausa = _retry_after(r.headers.get("Retry-After"), espera)

                # Un Retry-After enorme no es cola: es un bloqueo por IP.
                # Reintentar solo gasta tiempo. Se cae a otra fuente.
                # (B7 de N02: se lanza Bloqueado, que el except de abajo deja
                # pasar; antes lo capturaba y reintentaba igualmente.)
                if pausa > 60:
                    raise Bloqueado(
                        f"bloqueo temporal en {url} "
                        f"(Retry-After {pausa:.0f}s). Se usan otras fuentes."
                    )

                log.info("cola en %s, espero %.0fs", url, pausa)
                time.sleep(min(pausa, 20))
                espera *= 2

                continue

            r.raise_for_status()

            return r

        except Bloqueado:
            raise

        except httpx.HTTPError as e:
            ultimo = e
            time.sleep(espera)
            espera *= 2

    raise ultimo or httpx.HTTPError(f"sin respuesta de {url}")


def _cabeceras() -> dict:
    correo = valor("papers.correo_cortesia", "")

    agente = "AgenteLocal/1.0"

    if correo:
        agente += f" (mailto:{correo})"

    return {"User-Agent": agente, "Accept": "application/json"}


@dataclass
class Articulo:
    titulo: str
    anio: int | None = None
    autores: list[str] = field(default_factory=list)
    revista: str = ""
    doi: str = ""
    citas: int = 0
    resumen: str = ""
    url: str = ""
    acceso_abierto: bool = False
    fuente: str = ""

    def linea(self) -> str:
        autores = ", ".join(self.autores[:3])

        if len(self.autores) > 3:
            autores += " et al."

        partes = [f"{self.titulo}"]

        if autores:
            partes.append(autores)

        if self.anio:
            partes.append(str(self.anio))

        if self.revista:
            partes.append(self.revista)

        cabecera = " · ".join(partes)

        extra = f"  [{self.citas} citas]" if self.citas else ""
        abierto = "  [acceso abierto]" if self.acceso_abierto else ""

        return f"{cabecera}{extra}{abierto}\n  {self.url or self.doi}"


def _limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "")).strip()


def _invertido_a_texto(indice: dict | None) -> str:
    """OpenAlex guarda los resumenes como indice invertido."""

    if not indice:
        return ""

    posiciones: dict[int, str] = {}

    for palabra, sitios in indice.items():
        for sitio in sitios:
            posiciones[sitio] = palabra

    return " ".join(posiciones[i] for i in sorted(posiciones))


def openalex(consulta: str, limite: int = 8, desde_anio: int | None = None) -> list[Articulo]:
    parametros = {
        "search": consulta,
        "per-page": min(limite, 25),
        "sort": "relevance_score:desc",
    }

    if desde_anio:
        parametros["filter"] = f"from_publication_date:{desde_anio}-01-01"

    try:
        r = _get("https://api.openalex.org/works", parametros)

        crudos = r.json().get("results", [])

    except (httpx.HTTPError, ValueError) as e:
        log.warning("openalex fallo: %s", e)
        return []

    articulos = []

    for w in crudos:
        sede = (w.get("primary_location") or {}).get("source") or {}

        articulos.append(Articulo(
            titulo=_limpiar(w.get("title") or w.get("display_name") or ""),
            anio=w.get("publication_year"),
            autores=[
                _limpiar((a.get("author") or {}).get("display_name", ""))
                for a in (w.get("authorships") or [])[:6]
            ],
            revista=_limpiar(sede.get("display_name", "")),
            doi=(w.get("doi") or "").replace("https://doi.org/", ""),
            citas=w.get("cited_by_count", 0) or 0,
            resumen=_limpiar(
                _invertido_a_texto(w.get("abstract_inverted_index"))
            )[:1200],
            url=w.get("doi") or w.get("id", ""),
            acceso_abierto=bool((w.get("open_access") or {}).get("is_oa")),
            fuente="OpenAlex",
        ))

    return articulos


def semantic_scholar(consulta: str, limite: int = 8) -> list[Articulo]:
    campos = (
        "title,year,authors,venue,externalIds,citationCount,"
        "abstract,openAccessPdf,url"
    )

    try:
        r = _get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            {"query": consulta, "limit": min(limite, 20), "fields": campos},
        )

        crudos = r.json().get("data", []) or []

    except (httpx.HTTPError, ValueError) as e:
        log.warning("semantic scholar fallo: %s", e)
        return []

    return [
        Articulo(
            titulo=_limpiar(p.get("title", "")),
            anio=p.get("year"),
            autores=[_limpiar(a.get("name", "")) for a in (p.get("authors") or [])[:6]],
            revista=_limpiar(p.get("venue", "")),
            doi=(p.get("externalIds") or {}).get("DOI", "") or "",
            citas=p.get("citationCount", 0) or 0,
            resumen=_limpiar(p.get("abstract") or "")[:1200],
            url=p.get("url", ""),
            acceso_abierto=bool(p.get("openAccessPdf")),
            fuente="Semantic Scholar",
        )
        for p in crudos
    ]


def arxiv(consulta: str, limite: int = 8) -> list[Articulo]:
    try:
        r = _get(
            "https://export.arxiv.org/api/query",
            {
                "search_query": f"all:{consulta}",
                "max_results": min(limite, 20),
                "sortBy": "relevance",
            },
            cabeceras={"User-Agent": _cabeceras()["User-Agent"]},
        )

        raiz = ElementTree.fromstring(r.text)

    except (httpx.HTTPError, ElementTree.ParseError) as e:
        log.warning("arxiv fallo: %s", e)
        return []

    ns = {"a": "http://www.w3.org/2005/Atom"}

    articulos = []

    for entrada in raiz.findall("a:entry", ns):
        publicado = (entrada.findtext("a:published", "", ns) or "")[:4]

        articulos.append(Articulo(
            titulo=_limpiar(entrada.findtext("a:title", "", ns)),
            anio=int(publicado) if publicado.isdigit() else None,
            autores=[
                _limpiar(a.findtext("a:name", "", ns))
                for a in entrada.findall("a:author", ns)[:6]
            ],
            revista="arXiv",
            resumen=_limpiar(entrada.findtext("a:summary", "", ns))[:1200],
            url=entrada.findtext("a:id", "", ns),
            acceso_abierto=True,
            fuente="arXiv",
        ))

    return articulos


def _titulo_clave(titulo: str) -> str:
    """Titulo comparable: minusculas, sin puntuacion ni espacios de mas."""

    return re.sub(r"[^a-z0-9]+", " ", (titulo or "").lower()).strip()[:70]


def buscar(
    consulta: str,
    limite: int = 8,
    fuentes: tuple[str, ...] = ("openalex", "semantic_scholar", "arxiv"),
    desde_anio: int | None = None,
) -> list[Articulo]:
    """Busca en varias fuentes y funde los duplicados por DOI y titulo."""

    reunidos: list[Articulo] = []

    if "openalex" in fuentes:
        reunidos += openalex(consulta, limite, desde_anio)

    if "semantic_scholar" in fuentes:
        reunidos += semantic_scholar(consulta, limite)

    if "arxiv" in fuentes:
        reunidos += arxiv(consulta, limite)

    # B9 de N02: se mira el DOI Y el titulo normalizado. Antes la clave
    # era el DOI si lo habia y si no el titulo, asi que el mismo trabajo
    # con DOI (OpenAlex) y sin DOI (arXiv) salia dos veces.
    vistos: set[str] = set()
    unicos: list[Articulo] = []

    for art in reunidos:
        claves = {c for c in (
            f"doi:{(art.doi or '').lower()}" if art.doi else "",
            f"titulo:{_titulo_clave(art.titulo)}" if _titulo_clave(art.titulo) else "",
        ) if c}

        if not claves or claves & vistos:
            continue

        vistos |= claves
        unicos.append(art)

    unicos.sort(key=lambda a: (a.citas, a.anio or 0), reverse=True)

    return unicos[:limite]


def informe(consulta: str, limite: int = 8, desde_anio: int | None = None) -> str:
    """Busqueda formateada para leer de un vistazo."""

    resultados = buscar(consulta, limite, desde_anio=desde_anio)

    if not resultados:
        return f"Sin resultados para: {consulta}"

    lineas = [f"{len(resultados)} resultados para «{consulta}»", ""]

    for i, art in enumerate(resultados, 1):
        lineas.append(f"{i}. {art.linea()}")

        if art.resumen:
            lineas.append(f"     {art.resumen[:260]}...")

        lineas.append("")

    return "\n".join(lineas)


def cita(articulo: Articulo) -> str:
    """Cita en un formato limpio, listo para el TFG."""

    autores = ", ".join(articulo.autores[:6])

    if len(articulo.autores) > 6:
        autores += ", et al."

    partes = [p for p in (
        autores,
        f"({articulo.anio})" if articulo.anio else "",
        articulo.titulo + ".",
        articulo.revista + "." if articulo.revista else "",
        f"https://doi.org/{articulo.doi}" if articulo.doi else articulo.url,
    ) if p]

    return " ".join(partes)


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    import sys

    consulta = " ".join(sys.argv[1:]) or "perovskite solar cell stability"

    print(informe(consulta, limite=5))
