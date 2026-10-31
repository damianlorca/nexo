# -*- coding: utf-8 -*-
"""extremidades/papers.py: busqueda academica (OpenAlex, Semantic Scholar, arXiv).

Sin prueba propia hasta ahora (prueba_base/prueba_humo solo lo importan). La red se
sustituye por respuestas httpx fabricadas; time.sleep no espera (fixture reloj_falso).
"""
from __future__ import annotations

import httpx
import pytest

from extremidades import papers

ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <published>2024-01-02T00:00:00Z</published>
    <title>  Perovskite   stability
      study </title>
    <summary>Un resumen.</summary>
    <author><name>Ana</name></author>
    <author><name>Luis</name></author>
  </entry>
</feed>"""


def _resp(status=200, json=None, text=None, headers=None, url="https://x.test/"):
    req = httpx.Request("GET", url)
    if json is not None:
        return httpx.Response(status, json=json, headers=headers, request=req)
    return httpx.Response(status, text=text or "", headers=headers, request=req)


@pytest.fixture
def red(monkeypatch, reloj_falso):
    """Cola de respuestas para httpx.get dentro de papers. Apunta cada llamada."""
    estado = {"cola": [], "llamadas": [], "reloj": reloj_falso(papers)}

    def get(url, **kw):
        estado["llamadas"].append((url, kw))
        r = estado["cola"].pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(papers.httpx, "get", get)
    monkeypatch.setattr(papers, "valor", lambda ruta, defecto=None: defecto)
    return estado


def test_invertido_a_texto_reordena_por_posicion():
    assert papers._invertido_a_texto({"mundo": [1], "hola": [0], "otra": [2, 3]}) == "hola mundo otra otra"
    assert papers._invertido_a_texto(None) == ""


def test_openalex_parsea_un_resultado(red):
    red["cola"].append(_resp(json={"results": [{
        "title": "Titulo  con\n espacios", "publication_year": 2023,
        "authorships": [{"author": {"display_name": "Ana"}}, {"author": None}],
        "primary_location": {"source": {"display_name": "Nature"}},
        "doi": "https://doi.org/10.1/abc", "cited_by_count": 7,
        "abstract_inverted_index": {"b": [1], "a": [0]}, "open_access": {"is_oa": True},
    }]}))
    [a] = papers.openalex("x", desde_anio=2020)
    assert a.titulo == "Titulo con espacios" and a.anio == 2023
    assert a.autores == ["Ana", ""] and a.revista == "Nature"
    assert a.doi == "10.1/abc" and a.citas == 7 and a.resumen == "a b" and a.acceso_abierto
    assert red["llamadas"][0][1]["params"]["filter"] == "from_publication_date:2020-01-01"


def test_openalex_con_error_devuelve_lista_vacia(red):
    red["cola"] += [httpx.ConnectError("sin red")] * 3
    assert papers.openalex("x") == []


def test_semantic_scholar_parsea(red):
    red["cola"].append(_resp(json={"data": [{
        "title": "T", "year": 2020, "authors": [{"name": "Eva"}], "venue": "V",
        "externalIds": {"DOI": "10.2/x"}, "citationCount": None, "abstract": None,
        "openAccessPdf": {"url": "u"}, "url": "https://s2/1"}]}))
    [a] = papers.semantic_scholar("x")
    assert (a.doi, a.citas, a.resumen, a.acceso_abierto) == ("10.2/x", 0, "", True)


def test_arxiv_parsea_atom(red):
    red["cola"].append(_resp(text=ARXIV_XML))
    [a] = papers.arxiv("perovskite")
    assert a.titulo == "Perovskite stability study" and a.anio == 2024
    assert a.autores == ["Ana", "Luis"] and a.fuente == "arXiv" and a.acceso_abierto
    assert red["llamadas"][0][1]["params"]["search_query"] == "all:perovskite"


def test_arxiv_xml_roto_devuelve_vacio(red):
    red["cola"].append(_resp(text="<no cierra"))
    assert papers.arxiv("x") == []


def test_get_reintenta_tras_429_corto_y_luego_responde(red):
    red["cola"] += [_resp(429, text="", headers={"Retry-After": "3"}), _resp(json={"ok": 1})]
    assert papers._get("https://x.test/", {}).json() == {"ok": 1}
    assert len(red["llamadas"]) == 2 and red["reloj"].esperas == [3.0]


def test_get_agota_intentos_y_lanza(red):
    red["cola"] += [httpx.ConnectError("x")] * 3
    with pytest.raises(httpx.HTTPError):
        papers._get("https://x.test/", {})
    assert len(red["llamadas"]) == 3


# B7 de N02 (arreglado)
def test_get_no_reintenta_un_bloqueo_por_ip(red):
    red["cola"] += [_resp(429, headers={"Retry-After": "3600"})] * 3
    with pytest.raises(httpx.HTTPError):
        papers._get("https://x.test/", {})
    assert len(red["llamadas"]) == 1


# B8 de N02 (arreglado)
def test_retry_after_con_fecha_no_rompe_arxiv(red):
    red["cola"] += [_resp(503, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})] * 3
    assert papers.arxiv("x") == []


def test_buscar_funde_por_doi_y_ordena_por_citas(monkeypatch):
    A = papers.Articulo
    monkeypatch.setattr(papers, "openalex", lambda *a: [A("Uno", 2020, doi="10.1/A", citas=5)])
    monkeypatch.setattr(papers, "semantic_scholar", lambda *a: [A("Uno bis", 2020, doi="10.1/a", citas=9),
                                                                A("Dos", 2021, citas=50)])
    monkeypatch.setattr(papers, "arxiv", lambda *a: [A("", None)])  # sin clave: fuera
    r = papers.buscar("x", limite=5)
    assert [a.titulo for a in r] == ["Dos", "Uno"]


# B9 de N02 (arreglado)
def test_buscar_funde_el_mismo_trabajo_con_y_sin_doi(monkeypatch):
    A = papers.Articulo
    monkeypatch.setattr(papers, "openalex", lambda *a: [A("Perovskite stability study", 2024, doi="10.1/p")])
    monkeypatch.setattr(papers, "semantic_scholar", lambda *a: [])
    monkeypatch.setattr(papers, "arxiv", lambda *a: [A("Perovskite stability study", 2024)])
    assert len(papers.buscar("x")) == 1


def test_informe_y_cita(monkeypatch):
    A = papers.Articulo
    art = A("Titulo", 2022, autores=[f"A{i}" for i in range(7)], revista="R", doi="10.9/z", citas=3)
    monkeypatch.setattr(papers, "buscar", lambda *a, **k: [art])
    texto = papers.informe("q")
    assert "1 resultados" in texto and "A0, A1, A2 et al." in texto and "[3 citas]" in texto
    assert papers.cita(art) == "A0, A1, A2, A3, A4, A5, et al. (2022) Titulo. R. https://doi.org/10.9/z"
    monkeypatch.setattr(papers, "buscar", lambda *a, **k: [])
    assert papers.informe("q") == "Sin resultados para: q"


def test_retry_after_fecha_cercana_se_espera_y_reintenta(red):
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime
    pronto = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=10), usegmt=True)
    red["cola"] += [_resp(503, headers={"Retry-After": pronto}), _resp(json={"ok": 1})]
    assert papers._get("https://x.test/", {}).json() == {"ok": 1}
    assert len(red["llamadas"]) == 2 and 0 < red["reloj"].esperas[0] <= 10


def test_retry_after_basura_usa_la_espera_por_defecto():
    assert papers._retry_after("mañana", 2.0) == 2.0
    assert papers._retry_after(None, 2.0) == 2.0
    assert papers._retry_after("-5", 2.0) == 0.0


def test_buscar_funde_titulos_con_distinta_puntuacion(monkeypatch):
    A = papers.Articulo
    monkeypatch.setattr(papers, "openalex", lambda *a: [A("Perovskite Stability: a Study", 2024, citas=3)])
    monkeypatch.setattr(papers, "semantic_scholar", lambda *a: [A("perovskite stability  a study", 2024)])
    monkeypatch.setattr(papers, "arxiv", lambda *a: [A("Otro trabajo", 2023)])
    assert [a.titulo for a in papers.buscar("x")] == ["Perovskite Stability: a Study", "Otro trabajo"]
