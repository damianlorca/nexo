# -*- coding: utf-8 -*-
"""T890 punto 1: toda ficha lleva un elemento dato/idea con la afirmacion principal; lo prometido se busca en publico
(sin red: Crossref es un doble)."""
from __future__ import annotations

from nucleo import reels_ficha as F
from nucleo import reels_huecos, reels_publico as RP

MAT = "8 days of Fed announcements account for 80% of S&P 500 gains. Comment IF and I send you the paper"
CRUDO = {"tema": "Fed announcement days and S&P 500 gains",
         "resumen": "Eight Fed announcement days a year explain about 80% of the S&P 500 gains.",
         "afirmacion_principal": {"texto": "8 dias de anuncios de la Fed = ~80 % de las subidas del S&P 500",
                                  "categorias": ["trading"]},
         "promesa": {"texto": "send you the paper", "n": None, "tipo": "fuentes"},
         "llamada": {"hay": True, "tipo": "comenta", "palabra": "IF", "promete": "send you the paper",
                     "nombrado_en_publico": False},
         "elementos": []}


def test_ficha_sin_elementos_lleva_la_afirmacion_principal():
    f = F.normalizar(CRUDO, MAT)
    assert len(f["elementos"]) == 1
    e = f["elementos"][0]
    assert e["tipo"] == "dato" and e["origen"] == "afirmacion" and "80 %" in e["nombre"]
    assert e["categorias"] == ["trading"] and f["afirmacion_principal"] == e["nombre"]


def test_sin_afirmacion_del_modelo_se_usa_el_resumen():
    crudo = {k: v for k, v in CRUDO.items() if k != "afirmacion_principal"}
    f = F.normalizar(crudo, MAT)
    assert f["elementos"][0]["nombre"].startswith("Eight Fed announcement days")


def test_la_afirmacion_no_cuenta_para_la_promesa_ni_cubre_el_hueco():
    f = F.normalizar(dict(CRUDO, promesa={"texto": "3 repos", "n": 3, "tipo": "repos"}), MAT)
    assert F.completitud(f)["encontrados"] == 0 and F.completitud(f)["faltan"] == 3
    f = F.normalizar(CRUDO, MAT)
    f["completitud"] = F.completitud(f)
    h = reels_huecos.evaluar(f)
    assert h["hay"] and not h["cubierto"] and "el reel no nombra lo que promete" in h["faltas"]


def test_no_se_duplica_ni_se_arrastra_al_rehacer():
    f1 = F.normalizar(CRUDO, MAT)
    f2 = F.normalizar(dict(CRUDO, afirmacion_principal="otra redaccion"), MAT)
    assert F.conservar_anteriores(f2, f1) == 0 and len(f2["elementos"]) == 1


def _crossref(titulo):
    return lambda url: {"message": {"items": [{"title": [titulo], "URL": "https://doi.org/10.1/x",
                                                "issued": {"date-parts": [[2019]]}}]}}


def test_busqueda_publica_acepta_un_paper_parecido_y_cubre_el_hueco():
    f = F.normalizar(CRUDO, MAT)
    r = RP.buscar_prometido(f, get=_crossref("Eight Fed Announcement Days Explain S&P Gains"))
    assert r["aceptado"]["url"] == "https://doi.org/10.1/x"
    RP.aplicar(f, r)
    assert f["elementos"][-1]["origen"] == "busqueda" and f["busqueda_publica"]["aceptado"]
    f["completitud"] = F.completitud(f)
    assert reels_huecos.evaluar(f)["cubierto"]


def test_busqueda_publica_rechaza_lo_que_no_se_parece_y_no_busca_guias_privadas():
    f = F.normalizar(CRUDO, MAT)
    assert RP.buscar_prometido(f, get=_crossref("Equity in Mathematics Education"))["aceptado"] is None
    g = F.normalizar(dict(CRUDO, llamada=dict(CRUDO["llamada"], promete="la guia en PDF"),
                          promesa={"texto": "la guia", "n": None, "tipo": None}), MAT)
    assert RP.buscar_prometido(g, get=lambda u: 1 / 0) is None
    assert RP.buscar_prometido(f, get=lambda u: None)["candidatos"] == []


def test_datos_sueltos_del_modelo_no_son_la_afirmacion_ni_cubren_un_paper():
    f = F.normalizar(dict(CRUDO, elementos=[{"tipo": "dato", "nombre": "S&P500", "categorias": ["trading"]}]), MAT)
    assert [e["origen"] for e in f["elementos"]] == ["modelo", "afirmacion"]
    f["completitud"] = F.completitud(f)
    assert not reels_huecos.evaluar(f)["cubierto"]


def test_busqueda_publica_no_acepta_titulos_que_solo_comparten_palabras_genericas():
    """Caso real DeTJ1JSgedl: 'most important days ... missing' casaba con 'Found: Most Important Missing Link'."""
    f = F.normalizar(dict(CRUDO, afirmacion_principal="Missing the market's 8 most important days a year means "
                          "missing 80% of its gains"), MAT)
    r = RP.buscar_prometido(f, get=_crossref("Found: Most Important Missing Link"))
    assert r["aceptado"] is None and r["candidatos"][0]["titulo"].startswith("Found")


def test_la_consulta_prefiere_las_palabras_clave_del_modelo():
    f = F.normalizar(dict(CRUDO, consulta_publica="FOMC announcement days equity premium  S&P 500"), MAT)
    assert f["consulta_publica"] == "FOMC announcement days equity premium S&P 500"
    assert RP.consulta(f) == f["consulta_publica"]
    assert RP.consulta(F.normalizar(CRUDO, MAT)).startswith("8 dias de anuncios")


def test_la_tarjeta_de_huecos_enseña_lo_mas_cercano_que_hallo_la_busqueda_publica():
    f = F.normalizar(CRUDO, MAT)
    f.update(codigo="C1", url="https://x/reel/C1", autor="quantpapers")
    RP.aplicar(f, RP.buscar_prometido(f, get=_crossref("Equity in Mathematics Education")))
    f["completitud"] = F.completitud(f)
    fila = reels_huecos.hueco(f)
    assert fila["candidatos"] and "Equity in Mathematics Education" in fila["candidatos"][0]
    md = reels_huecos.tarjeta_md({"tarjeta": {"id": "H1", "fuera_de_tanda": 0}, "filas": [fila]})
    assert "sin verificar" in md and "doi.org/10.1/x" in md


def test_un_paper_descrito_pero_sin_url_ni_busqueda_acertada_sigue_siendo_hueco():
    """Caso real DeTJ1JSgedl con el modelo nuevo: 17 elementos (cuenta, cifras, 'paper del NY Fed 1994-2011', tecnicas)
    pero ninguno es un localizador del paper."""
    elementos = [{"tipo": "web", "nombre": "StockMarketExplained", "categorias": ["trading"]},
                 {"tipo": "dato", "nombre": "Paper on Fed announcement effect (NY Fed, 1994-2011)",
                  "categorias": ["trading"]},
                 {"tipo": "tecnica", "nombre": "Staircase analogy", "categorias": ["trading"]}]
    f = F.normalizar(dict(CRUDO, elementos=elementos), MAT)
    f["completitud"] = F.completitud(f)
    assert not reels_huecos.evaluar(f)["cubierto"]
    f["elementos"].append({"tipo": "web", "nombre": "Paper", "url": "https://doi.org/10.1/x", "origen": "modelo",
                           "categorias": ["trading"]})                       # con una URL real, si se cubre
    assert reels_huecos.evaluar(f)["cubierto"]
