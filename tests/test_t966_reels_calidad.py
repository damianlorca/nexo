# -*- coding: utf-8 -*-
"""T966 (17/10): calidad de las fichas de reels (REVISION_CLAUDE_2026-10-17.md). Todo con dobles, sin red."""
from __future__ import annotations

import json

import pytest

from nucleo import reels_calidad as C
from nucleo import reels_ficha as F
from nucleo import reels_publico as RP
from nucleo import reels_tareas as RT

MAT = """[PIE]
Comment "REPO" and I'll send you all 5 links

Foreman supervises your coding agents like a project manager, checking progress and tests before anything ships.
Aria-Icons hands you instant access to over 380,000 searchable SVG icons.

[AUDIO]
(sin audio)

[PANTALLA]
[fotograma 3 · 00:02]
#1
Foreman
Foremansupervisescodingagentswith
Jev,assessing progress,requirements,
tests,verification,andhuman
escalationtoguidesoftwarework.
[fotograma 6 · 00:05]
#4
Aria-lcons
Aria Iconsprovides
searchableaccessto
380,000+SVGicons,with
toolsto customize
"""


# ------------------------------------------------------------------ b) OCR
@pytest.mark.parametrize("ocr,bien", [
    ("TogetherAl", "TogetherAI"), ("MistralAl", "MistralAI"), ("Al receptionist", "AI receptionist"),
    ("Aria-lcons", "Aria-Icons"), ("0pen Graph", "Open Graph"), ("Open-glean", "Open-glean"),
    ("Alibaba", "Alibaba"), ("Link-tree", "Link-tree"), ("Foreman", "Foreman"), ("Claude-mem", "Claude-mem"),
])
def test_corregir_ocr(ocr, bien):
    assert C.corregir_ocr(ocr) == bien


def test_la_ficha_arregla_el_ocr_y_conserva_el_nombre_leido():
    crudo = {"elementos": [{"tipo": "repo", "nombre": "Aria-lcons", "que_es": "380.000 iconos SVG",
                            "para_que": "Iconos para la interfaz de NEXO"}]}
    f = F.normalizar(crudo, MAT)
    e = f["elementos"][0]
    assert e["nombre"] == "Aria-Icons" and e["nombre_ocr"] == "Aria-lcons" and e["verificado"] is True


# ------------------------------------------------------------------ c) descripciones en pantalla
def test_descripcion_de_pantalla_bajo_el_nombre():
    d = C.descripcion_pantalla(MAT, "Foreman")
    assert "supervises" in d and "escalation" in d and "Aria" not in d
    assert "380,000" in C.descripcion_pantalla(MAT, "Aria-Icons")           # el titulo del bloque sale como 'Aria-lcons'
    assert C.descripcion_pantalla(MAT, "NoExiste") == ""


def test_la_ficha_guarda_descripcion_de_pantalla_y_frase_del_pie():
    f = F.normalizar({"elementos": [{"tipo": "repo", "nombre": "Foreman", "que_es": "Supervisa agentes"}]}, MAT)
    e = f["elementos"][0]
    assert "supervises" in e["descripcion_pantalla"] and "project manager" in e["descripcion_pie"]


# ------------------------------------------------------------------ a) el repo debe encajar
def test_encaja_solo_si_la_descripcion_del_repo_coincide_con_el_reel():
    ctx = "Foremansupervisescodingagentswith assessing progress requirements tests verification"
    assert C.encaja("Supervise coding agents: progress, tests and human escalation", ctx)[0] is True
    assert C.encaja("Manage Procfile-based applications", ctx)[0] is False
    assert C.encaja("", ctx)[0] is False and C.encaja("Supervise agents", "")[0] is False


# ------------------------------------------------------------------ d) basura de citas y URLs
@pytest.mark.parametrize("repo", ["caude--/mi-app", "mi-mod/.claude-", "plugin/plugin.json", "and/or", "tu-usuario/tu-repo",
                                  "src/lib", "x/yy"])
def test_repo_basura(repo):
    assert C.repo_basura(repo)


def test_repos_reales_no_son_basura():
    for r in ("thedotmack/claude-mem", "morluto/rea", "hydra-db/open-glean", "ddollar/foreman"):
        assert C.repo_basura(r) == ""


@pytest.mark.parametrize("url,clase", [
    ("https://github.com/thedotmack/claude-mem", "repo"), ("https://github.com/thedotmack", "cuenta_github"),
    ("https://www.instagram.com/reel/Dd85NOcjWaK/", "red_social"), ("https://x.com/algo", "red_social"),
    ("https://bit.ly/abc", "acortador"), ("https://arxiv.org/abs/2401.00001", "paper"),
    ("https://huggingface.co/org/modelo", "modelo"), ("https://docs.claude.com/es/docs", "documentacion"),
    ("https://aria-icons.dev", "herramienta"),
])
def test_clasificar_url(url, clase):
    assert C.clasificar_url(url)["clase"] == clase


def test_la_ficha_no_crea_repos_basura_ni_elementos_de_redes():
    citas = {"repos": [], "repos_posibles": ["caude--/mi-app", "mi-mod/.claude-", "plugin/plugin.json"],
             "urls": ["https://www.instagram.com/reel/AAA/", "https://bit.ly/x", "https://aria-icons.dev/docs",
                      "https://github.com/hydra-db"]}
    f = F.normalizar({"elementos": []}, MAT, citas)
    assert [e["nombre"] for e in f["elementos"] if e.get("origen") == "citas"] == ["https://aria-icons.dev/docs"]
    assert len(f["citas_descartadas"]) == 3
    assert set(f["urls_sueltas"]) == {"red_social", "acortador", "cuenta_github"}


# ------------------------------------------------------------------ e) idioma
def test_alfabeto_ajeno():
    assert C.alfabeto_ajeno("aumentar la 效率 de los agentes") == "效"
    assert C.alfabeto_ajeno("Привет") and C.alfabeto_ajeno("مرحبا")
    assert C.alfabeto_ajeno("Análisis rápido: ñandú, über, çà") == ""


def test_es_ingles():
    assert C.es_ingles("Foreman supervises your coding agents like a project manager and the tests") is True
    assert C.es_ingles("Supervisa agentes de programación y comprueba los tests antes de entregar") is False
    assert C.es_ingles("Open-glean") is False


def test_problemas_de_texto_y_cierre_marcan_lo_que_no_se_arregla():
    ficha = {"tema": "Mods de Claude Code 效率", "resumen": "Cuatro mods útiles para el flujo de trabajo.",
             "afirmacion_principal": "", "elementos": [
                 {"nombre": "A", "tipo": "herramienta", "origen": "modelo", "que_es": "Aumenta la productividad 效率",
                  "para_que": "Revisar los cambios antes de que Claude los guarde en el repositorio"},
                 {"nombre": "B", "tipo": "herramienta", "origen": "modelo",
                  "que_es": "It records the screen and the voice of the user for the whole session",
                  "para_que": "Revisar los cambios antes de que Claude los guarde en el repositorio"}]}
    p = C.problemas_texto(ficha)
    assert "tema" in p["alfabeto"] and "A.que_es" in p["alfabeto"] and "B.que_es" in p["ingles"]
    assert p["para_que"] == {"A": "repetido en otro elemento", "B": "repetido en otro elemento"}
    alertas = F.cerrar_calidad(ficha)
    assert ficha["tema"] == "Mods de Claude Code" and "效" not in ficha["elementos"][0]["que_es"]
    assert any("ingles" in a for a in alertas) and any("alfabeto" in a for a in alertas)
    assert ficha["elementos"][0]["para_que"] == C.SIN_USO and ficha["elementos"][0]["para_que_pobre"]


def test_el_arreglo_del_modelo_solo_se_acepta_si_esta_bien():
    ficha = {"tema": "t", "resumen": "r", "afirmacion_principal": "", "elementos": [
        {"nombre": "Foreman", "tipo": "repo", "origen": "modelo", "que_es": "Supervises your coding agents and tests",
         "para_que": "idea central"}]}
    n = F.aplicar_correccion(ficha, {"elementos": [{"nombre": "Foreman",
                                                    "que_es": "Supervisa agentes de programación y sus tests",
                                                    "para_que": "Vigilar a los agentes de NEXO antes de fusionar su trabajo"}]})
    assert n == 2 and ficha["elementos"][0]["que_es"].startswith("Supervisa")
    mal = F.aplicar_correccion(ficha, {"tema": "效率 otra vez", "elementos": [{"nombre": "Foreman", "que_es": "It supervises all the agents and the tests of the user"}]})
    assert mal == 0 and ficha["tema"] == "t"


# ------------------------------------------------------------------ f) 'para que' concreto
@pytest.mark.parametrize("texto,pobre", [
    ("", True), ("útil", True), ("Útil para el estudiante.", True), ("idea central del reel", False),
    ("Sirve para que el creador del reel venda su curso", True),
    ("Vigilar a los agentes de NEXO y comprobar sus tests antes de fusionar", False)])
def test_para_que_pobre(texto, pobre):
    e = {"nombre": "x", "para_que": texto, "origen": "modelo" if texto != "idea central del reel" else "afirmacion"}
    assert bool(C.para_que_pobre(e, [e])) is pobre


# ------------------------------------------------------------------ g) tipos
def test_idea_de_proyecto_no_es_idea_de_negocio():
    crudo = {"elementos": [
        {"tipo": "idea de negocio", "nombre": "Crea el tuyo", "que_es": "Pedir un mod propio para Claude Code",
         "para_que": "Hacerse un mod a medida"},
        {"tipo": "idea_negocio", "nombre": "Agencia de reels", "que_es": "Vender reels a clientes por suscripción",
         "para_que": "Ingresos recurrentes"}]}
    f = F.normalizar(crudo, "[PIE]\n\n[AUDIO]\n\n[PANTALLA]\n")
    tipos = {e["nombre"]: e["tipo"] for e in f["elementos"]}
    assert tipos["Crea el tuyo"] == "idea_proyecto" and tipos["Agencia de reels"] == "idea_negocio"
    assert F.tipo_normal("idea de proyecto") == "idea_proyecto"


def test_personas_y_cuentas_no_son_dato():
    crudo = {"elementos": [
        {"tipo": "dato", "nombre": "@sahni.ai", "que_es": "Cuenta del creador del reel", "para_que": "Seguirlo"},
        {"tipo": "dato", "nombre": "Jerome Powell", "que_es": "Presidente de la Reserva Federal (persona)",
         "para_que": "Contexto"},
        {"tipo": "dato", "nombre": "80 % de las subidas", "que_es": "Las subidas ocurren en 8 días del año",
         "para_que": "Estrategia de trading"}]}
    f = F.normalizar(crudo, "[PIE]\n\n[AUDIO]\n\n[PANTALLA]\n")
    tipos = {e["nombre"]: e["tipo"] for e in f["elementos"]}
    assert tipos["@sahni.ai"] == "cuenta" and tipos["Jerome Powell"] == "cuenta" and tipos["80 % de las subidas"] == "dato"


def test_el_dato_de_idea_central_no_repite_el_resumen():
    f = F.normalizar({"resumen": "Cuatro mods útiles para Claude Code", "afirmacion_principal":
                      {"texto": "Cuatro mods útiles para Claude Code"}, "elementos": []},
                     "[PIE]\n\n[AUDIO]\n\n[PANTALLA]\n")
    d = [e for e in f["elementos"] if e["origen"] == "afirmacion"][0]
    assert d["que_es"] == ""


# ------------------------------------------------------------------ h) lo prometido: paper por titulo
def _get_papers(url):
    if "api.crossref.org" in url and "query.title" in url:
        return {"message": {"items": [
            {"title": ["Pre-FOMC Announcement Drift and Sentiment"], "URL": "https://doi.org/10.1/otro",
             "issued": {"date-parts": [[2020]]}},
            {"title": ["The Pre-FOMC Announcement Drift"], "URL": "https://doi.org/10.1111/jofi.12000",
             "issued": {"date-parts": [[2011]]}}]}}
    if "arxiv.org" in url:
        return {"_texto": "<feed><entry><id>http://arxiv.org/abs/1</id><title>Nada que ver</title>"
                          "<published>2019-01-01T00:00:00Z</published></entry></feed>"}
    if "semanticscholar" in url:
        return {"data": [{"title": "Pre-FOMC Announcement Drift", "year": 2011, "url": "https://www.semanticscholar.org/paper/x"}]}
    return None


def test_el_paper_se_busca_por_titulo_en_varias_fuentes():
    ficha = {"llamada": {"hay": True, "promete": "el paper de la Fed"}, "promesa": {"texto": "el paper"},
             "titulo_probable": "The Pre-FOMC Announcement Drift", "afirmacion_principal": "8 días de la Fed"}
    r = RP.buscar_prometido(ficha, get=_get_papers)
    assert r["por"] == "titulo" and r["aceptado"]["url"] in ("https://doi.org/10.1111/jofi.12000",
                                                            "https://www.semanticscholar.org/paper/x")
    assert r["aceptado"]["similitud"] >= RP.MIN_SIMILITUD and len(r["candidatos"]) == 3
    RP.aplicar(ficha, r)
    assert ficha["elementos"][0]["origen"] == "busqueda" and "por titulo" in ficha["elementos"][0]["que_es"]


def test_un_titulo_parecido_pero_distinto_no_se_acepta():
    ficha = {"llamada": {"hay": True, "promete": "el estudio"}, "promesa": {"texto": "el estudio"},
             "titulo_probable": "Momentum Crashes in Emerging Markets", "afirmacion_principal": ""}
    r = RP.buscar_prometido(ficha, get=_get_papers)
    assert r["aceptado"] is None


def test_la_ficha_guarda_el_titulo_probable():
    f = F.normalizar({"titulo_probable": " Pre-FOMC  Announcement Drift ", "elementos": []}, "[PIE]\n\n[AUDIO]\n\n[PANTALLA]\n")
    assert f["titulo_probable"] == "Pre-FOMC Announcement Drift"


# ------------------------------------------------------------------ k) seguridad
@pytest.mark.parametrize("texto,nivel", [
    ("Prompt que añade skipPermissions y autonomía total en ~/.claude", "peligro"),
    ("claude --dangerously-skip-permissions", "peligro"),
    ("Modelo sin censura para Ollama", "damian"), ("Descargar vídeos de Instagram con yt-dlp", "damian"),
    ("Qwen abliterated", "damian"), ("Un repo normal de iconos SVG", None)])
def test_seguridad(texto, nivel):
    s = C.seguridad({"tipo": "tecnica", "nombre": "x", "que_es": texto})
    assert (s or {}).get("nivel") == nivel


def test_lo_obsoleto_se_descarta():
    assert C.seguridad({"tipo": "modelo", "nombre": "Claude Opus 4.5"})["nivel"] == "obsoleto"
    assert C.seguridad({"tipo": "modelo", "nombre": "GPT-4"})["nivel"] == "obsoleto"
    assert C.seguridad({"tipo": "modelo", "nombre": "Claude Opus 5.5"}) is None


# ------------------------------------------------------------------ j) plan: tope de 10, tema, seguridad, base
def _ficha(cod, tema, nombres, cats=("nexo",), **extra):
    elems = [{"tipo": "repo", "nombre": n, "dueno": "o", "que_es": f"{n} hace cosas", "para_que": f"usar {n}",
              "categorias": list(cats), "origen": "modelo", "verificado": True, "resolucion": {"existe": True},
              "fuentes": ["pie"], "confianza": "alta", "en_promesa": False} for n in nombres]
    return dict({"codigo": cod, "tema": tema, "resumen": "", "elementos": elems, "llamada": {"hay": False},
                 "completitud": {"estado": "completa", "faltan": 0}}, **extra)


def _plan(fichas):
    return RT.plan(fichas, catalogo=[], tareas=[], reg=[])


def test_el_plan_no_pasa_de_10_por_tanda_y_el_resto_va_a_la_base():
    fichas = [_ficha(f"C{i:02d}", f"tema {i % 4}", [f"repo{i}"], cats=("nexo",) if i < 6 else ("diseno",))
              for i in range(14)]
    p = _plan(fichas)
    assert len(p["tareas"]) == 10 and p["a_base_por_tope"] == 4
    base = [x for filas in p["conocimiento"].values() for x in filas if x.get("por_tope")]
    assert len(base) == 4
    assert all("_filas" not in t for t in p["tareas"])
    # entran las mas importantes (nexo = 4) antes que las de diseno (3)
    assert sum(t["importancia"] == 4 for t in p["tareas"]) == 6
    temas = [t["tema"] for t in p["tareas"]]
    assert temas == sorted(temas)                                            # agrupadas por tema
    assert "más a la base" in RT.plan_md(p)


def test_lo_peligroso_sale_fuera_con_aviso_y_lo_obsoleto_se_descarta():
    f = _ficha("S1", "prompts", ["skip"])
    f["elementos"][0].update(tipo="tecnica", seguridad={"nivel": "peligro", "motivo": "pide saltarse permisos"},
                             nombre="Prompt skipPermissions")
    g = _ficha("S2", "modelos", ["Opus"])
    g["elementos"][0].update(tipo="modelo", seguridad={"nivel": "obsoleto", "motivo": "version superada"},
                             nombre="Claude Opus 4.5")
    p = _plan([f, g])
    assert p["tareas"] == [] and len(p["excluidos"]) == 2
    assert p["avisos_seguridad"] == ["Prompt skipPermissions: pide saltarse permisos"]
    assert "SEGURIDAD" in p["excluidos"][0]["motivo"] and "Obsoleto" in p["excluidos"][1]["motivo"]
    assert "AVISO DE SEGURIDAD" in RT.plan_md(p)


def test_sin_censura_y_descargas_van_a_una_tarea_para_damian():
    f = _ficha("D1", "modelos sin censura", ["abliterated"])
    f["elementos"][0].update(seguridad={"nivel": "damian", "motivo": "modelos sin censura o descarga de videos"})
    p = _plan([f])
    assert [t["tipo"] for t in p["tareas"]] == ["personal"]
    assert "SEGURIDAD" in p["tareas"][0]["detalle"] and p["tareas"][0]["depende"] == "damian"


def test_un_hueco_real_entra_al_plan_como_tarea_de_damian():
    f = _ficha("H1", "prompts", ["x"], llamada={"hay": True, "tipo": "comenta", "palabra": "PROMPT",
                                                  "promete": "el prompt completo"}, url="https://i/H1", autor="a")
    p = _plan([f])
    huecos = [t for t in p["tareas"] if t["tipo"] == "hueco_damian"]
    assert len(huecos) == 1 and "«PROMPT»" in huecos[0]["detalle"] and "H1" not in huecos[0]["detalle"]


def test_los_tipos_nuevos_van_donde_deben():
    e = {"tipo": "idea_proyecto", "categorias": ["nexo"]}
    assert RT.destino(e) == "investigacion"
    assert RT.destino({"tipo": "cuenta", "categorias": ["nexo"]}) == "conocimiento:nexo"


def test_al_rehacer_no_se_arrastra_el_nombre_mal_leido_de_la_ficha_anterior():
    """Dd85NOcjWaK: 'Aria-Icons' (nuevo) y 'Aria-lcons' (ficha anterior) salian como dos repos y la promesa daba 6/5."""
    ficha = {"elementos": [{"tipo": "repo", "nombre": "Aria-Icons", "dueno": None, "verificado": True}]}
    previa = {"elementos": [{"tipo": "repo", "nombre": "Aria-lcons", "dueno": None, "verificado": True},
                            {"tipo": "repo", "nombre": "Repolyze", "dueno": None, "verificado": True}]}
    assert F.conservar_anteriores(ficha, previa) == 1
    assert [e["nombre"] for e in ficha["elementos"]] == ["Aria-Icons", "Repolyze"]


def test_al_rehacer_las_ideas_y_los_datos_de_la_ficha_anterior_no_se_arrastran():
    ficha = {"elementos": [{"tipo": "idea_proyecto", "nombre": "Mod personalizado", "verificado": True}]}
    previa = {"elementos": [{"tipo": "idea_negocio", "nombre": "El que tu quieras", "verificado": True},
                            {"tipo": "dato", "nombre": "4 mods", "verificado": True},
                            {"tipo": "herramienta", "nombre": "Guardian de archivos", "verificado": True}]}
    assert F.conservar_anteriores(ficha, previa) == 1
    assert [e["nombre"] for e in ficha["elementos"]] == ["Mod personalizado", "Guardian de archivos"]


def test_texto_en_ingles_sin_palabras_de_enlace_tambien_se_detecta():
    assert C.es_ingles("educational page/video explaining stock market concepts") is True
    assert C.es_ingles("Página educativa que explica conceptos del mercado de valores") is False


def test_el_creador_del_reel_no_es_un_dato_y_el_para_que_de_relleno_es_pobre():
    assert C.retipar({"tipo": "dato", "nombre": "Hedge fund quant trader", "origen": "modelo",
                      "que_es": "creador del reel, trader cuantitativo de un fondo"}) == "cuenta"
    assert C.retipar({"tipo": "dato", "nombre": "4,141 slices", "origen": "modelo",
                      "que_es": "ventanas de 24 horas analizadas"}) is None
    e = {"nombre": "x", "origen": "modelo", "para_que": "Para quien guarda el reel como referencia de contenido divulgativo"}
    assert C.para_que_pobre(e, [e]) == "vacio o generico"
