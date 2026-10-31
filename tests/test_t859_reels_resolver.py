# -*- coding: utf-8 -*-
"""T859 bloque 6: resolucion de elementos con la API publica de GitHub (dobles: sin red)."""
from __future__ import annotations

from datetime import datetime

import pytest

from nucleo import reels_resolver as R

REA = {"full_name": "morluto/rea", "html_url": "https://github.com/morluto/rea", "stargazers_count": 74700,
       "license": {"spdx_id": "MIT"}, "pushed_at": "2026-10-10T08:00:00Z", "archived": False, "name": "rea"}


def _get(tabla):
    vistas = []

    def get(url):
        vistas.append(url)
        for trozo, resp in tabla.items():
            if trozo in url:
                return resp
        return 404, None, {}
    get.vistas = vistas
    return get


def test_repo_con_dueno_existe():
    get = _get({"/repos/morluto/rea": (200, REA, {})})
    r = R.resolver_elemento({"tipo": "repo", "nombre": "rea", "dueno": "morluto"}, get=get)
    assert r["existe"] and r["canonico"] == "morluto/rea" and r["estrellas"] == 74700 and r["licencia"] == "MIT"
    assert r["ultima_actividad"].startswith("2026-10-10")


def test_repo_sin_dueno_por_busqueda_solo_nombre_exacto_y_el_de_mas_estrellas():
    d = "Persistent memory plugin for Claude Code sessions"          # T966: la descripcion debe encajar con el reel
    items = [{"name": "claude_mem", "full_name": "a/claude_mem", "stargazers_count": 10, "description": d},
             {"name": "claude-mem", "full_name": "thedotmack/claude-mem", "stargazers_count": 9000, "description": d},
             {"name": "claude-mem-plus", "full_name": "z/claude-mem-plus", "stargazers_count": 99999, "description": d}]
    get = _get({"/search/repositories": (200, {"items": items}, {})})
    e = {"tipo": "repo", "nombre": "Claude Mem", "que_es": "Memoria persistente para sesiones de Claude Code (plugin)",
         "descripcion_pie": "claude-mem keeps persistent memory across Claude Code sessions"}
    r = R.resolver_elemento(e, get=get, dormir=lambda s: None)
    assert r["canonico"] == "thedotmack/claude-mem" and r["origen"] == "busqueda" and r["candidatos"] == ["a/claude_mem"]
    assert "in%3Aname" in get.vistas[0]


def test_sin_candidato_exacto_queda_sin_resolver_con_candidatos():
    get = _get({"/search/repositories": (200, {"items": [{"name": "otra", "full_name": "x/otra"}]}, {})})
    r = R.resolver_elemento({"tipo": "repo", "nombre": "rtk"}, get=get, dormir=lambda s: None)
    assert r["existe"] is None and r["candidatos"] == ["x/otra"]


def test_dueno_mal_leido_404_y_no_hay_otro_es_que_no_existe():
    get = _get({"/search/repositories": (200, {"items": []}, {})})
    r = R.resolver_elemento({"tipo": "repo", "nombre": "Win", "dueno": "Mac"}, get=get, dormir=lambda s: None)
    assert r["existe"] is False


def test_web_con_head_y_url_sin_esquema():
    vistas = []
    r = R.resolver_elemento({"tipo": "web", "nombre": "MongoDB", "url": "mongodb.com/students"},
                            head=lambda u: vistas.append(u) or 200)
    assert r["existe"] and vistas == ["https://mongodb.com/students"]
    assert R.resolver_elemento({"tipo": "web", "nombre": "x", "url": "https://caida.example"}, head=lambda u: 0)["existe"] is False
    assert R.resolver_elemento({"tipo": "consejo", "nombre": "duerme"})["nota"].startswith("no aplica")


def test_sin_cuota_para_y_deja_pendiente_sin_reintentar():
    llamadas = []

    def get(url):
        llamadas.append(url)
        return 403, None, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1760000000"}
    ficha = {"elementos": [{"tipo": "repo", "nombre": "a", "dueno": "o"}, {"tipo": "repo", "nombre": "b", "dueno": "o"}]}
    res = R.resolver_ficha(ficha, get=get, dormir=lambda s: None)
    assert res["sin_cuota"] == 1760000000 and res["pendientes"] == 2 and len(llamadas) == 1
    assert ficha["elementos"][1]["resolucion"]["nota"].startswith("pendiente")


def test_cache_evita_repetir_y_la_busqueda_pone_el_dueno():
    rea = dict(REA, description="Reverse engineering assistant for binaries")
    get = _get({"/search/repositories": (200, {"items": [rea]}, {})})
    cache = {}
    ctx = {"que_es": "Asistente de ingenieria inversa de binarios (reverse engineering)"}
    ficha = {"elementos": [{"tipo": "repo", "nombre": "rea", **ctx}]}
    res = R.resolver_ficha(ficha, get=get, dormir=lambda s: None, cache=cache, ahora=datetime(2026, 10, 12))
    assert res["resueltos"] == 1 and ficha["elementos"][0]["dueno"] == "morluto" and ficha["elementos"][0]["dueno_por_busqueda"]
    otra = {"elementos": [{"tipo": "repo", "nombre": "rea", **ctx}]}
    R.resolver_ficha(otra, get=lambda u: pytest.fail("no hacia falta"), cache=cache, ahora=datetime(2026, 10, 13))
    assert otra["elementos"][0]["resolucion"]["canonico"] == "morluto/rea"


def test_cache_en_disco(tmp_path):
    ruta = tmp_path / "res.json"
    R.guardar_cache({"k": {"cuando": "2026-10-12T00:00:00", "r": {"existe": True}}}, ruta)
    assert R.cargar_cache(ruta)["k"]["r"]["existe"] and R.cargar_cache(tmp_path / "no.json") == {}


def test_lo_citado_literal_que_no_existe_no_se_busca():
    get = _get({})
    r = R.resolver_elemento({"tipo": "repo", "nombre": "Creed", "dueno": "Hepbum", "origen": "citas"}, get=get,
                            dormir=lambda s: pytest.fail("no se busca"))
    assert r["existe"] is False and len(get.vistas) == 1


# ------------------------------------------------------------------ T966: el repo tiene que encajar con el reel
FOREMAN_RUBY = {"name": "foreman", "full_name": "ddollar/foreman", "stargazers_count": 5800,
                "description": "Manage Procfile-based applications", "html_url": "https://github.com/ddollar/foreman"}
FOREMAN_IA = {"name": "foreman", "full_name": "acme/foreman", "stargazers_count": 505, "topics": ["ai-agents"],
              "description": "Supervise coding agents: progress, requirements, tests and human escalation",
              "html_url": "https://github.com/acme/foreman"}
FOREMAN_REEL = {"tipo": "repo", "nombre": "Foreman",
                "descripcion_pantalla": "Foremansupervisescodingagentswith Jev,assessing progress,requirements, tests,"
                                        "verification,andhuman escalationtoguidesoftwarework.",
                "que_es": "Supervisa agentes de programacion y comprueba progreso y tests antes de entregar"}


def test_un_homonimo_con_otra_descripcion_no_se_acepta():
    get = _get({"/search/repositories": (200, {"items": [FOREMAN_RUBY]}, {})})
    r = R.resolver_elemento(dict(FOREMAN_REEL), get=get, dormir=lambda s: None)
    assert r["existe"] is None and "ninguno encaja" in r["nota"] and r["candidatos"] == ["ddollar/foreman"]


def test_entre_homonimos_gana_el_que_encaja_aunque_tenga_menos_estrellas():
    get = _get({"/search/repositories": (200, {"items": [FOREMAN_RUBY, FOREMAN_IA]}, {})})
    r = R.resolver_elemento(dict(FOREMAN_REEL), get=get, dormir=lambda s: None)
    assert r["existe"] and r["canonico"] == "acme/foreman" and r["origen"] == "busqueda"


def test_sin_descripcion_del_reel_no_se_acepta_ningun_repo_por_nombre():
    get = _get({"/search/repositories": (200, {"items": [FOREMAN_IA]}, {})})
    r = R.resolver_elemento({"tipo": "repo", "nombre": "Foreman"}, get=get, dormir=lambda s: None)
    assert r["existe"] is None and "sin descripcion" in r["nota"]


def test_la_cache_distingue_lo_que_dice_el_reel():
    a = R._clave(dict(FOREMAN_REEL))
    b = R._clave({"tipo": "repo", "nombre": "Foreman", "que_es": "gestor de procesos Procfile"})
    assert a != b and a.startswith("v2|")
