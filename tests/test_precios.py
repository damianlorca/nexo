# -*- coding: utf-8 -*-
"""Radar de precios (T665): lectura JSON-LD, robots.txt, bloqueos sin insistir, historico, minimo y aviso. Sin red."""
from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from nucleo import avisos, precios
from nucleo import radar as R

HOY = datetime(2026, 10, 5, 18, 0)
MANANA = datetime(2026, 10, 6, 6, 45)

FICHA = """<html><script type="application/ld+json">{"@context":"https://schema.org","@type":"BreadcrumbList"}</script>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Ryzen",
"offers":{"@type":"Offer","price":"%s","priceCurrency":"EUR","availability":"https://schema.org/InStock",
"seller":{"@type":"Organization","name":"PcComponentes"}}}</script></html>"""
ROBOTS = "User-agent: Python-urllib\nDisallow: /\n\nUser-agent: *\nDisallow: /carrito.php\n"


def resp(texto="", codigo=200, cabeceras=None):
    def raise_for_status():
        if codigo >= 400:
            raise RuntimeError(f"HTTP {codigo}")
    return SimpleNamespace(text=texto, status_code=codigo, headers=cabeceras or {}, raise_for_status=raise_for_status)


def get_falso(rutas: dict, pedidas: list | None = None):
    def get(url, params=None, cabeceras=None):
        if pedidas is not None:
            pedidas.append(url)
        return rutas[url]
    return get


def _config(fuentes):
    R.carpeta("precios").mkdir(parents=True, exist_ok=True)
    (R.carpeta("precios") / "config.json").write_text(json.dumps(
        {"id": "precios", "clase": "precios", "modo": "real", "fuentes": fuentes}), encoding="utf-8")


def _fuente(i="cpu", url="https://tienda.es/cpu", **extra):
    return {"id": i, "nombre": "CPU " + i, "tienda": "tienda.es", "url": url, "tipo": "jsonld",
            "terminos": "robots.txt permite las fichas; aviso legal sin prohibicion (prueba)", **extra}


# ------------------------------------------------------------------ lectura
@pytest.mark.parametrize("texto,esperado", [("229.02", 229.02), ("1.234,56 €", 1234.56), ("1,234.56", 1234.56),
                                            ("149,9", 149.9), (64.96, 64.96), ("", None), ("gratis", None)])
def test_precio_entiende_formatos(texto, esperado):
    assert precios._precio(texto) == esperado


def test_precio_de_html_saca_el_product():
    d = precios.precio_de_html(FICHA % "229.02")
    assert d == {"precio": 229.02, "disponible": True, "vendedor": "PcComponentes"}


def test_precio_de_html_lista_de_ofertas_y_graph():
    html = ('<script type="application/ld+json">{"@graph":[{"@type":"Product","offers":[{"price":0},'
            '{"price":"99.5","availability":"OutOfStock"}]}]}</script>')
    assert precios.precio_de_html(html) == {"precio": 99.5, "disponible": False, "vendedor": ""}
    assert precios.precio_de_html("<html>sin datos</html>") is None


def test_robots_que_prohibe_no_se_lee():
    get = get_falso({"https://tienda.es/robots.txt": resp("User-agent: *\nDisallow: /\n")})
    with pytest.raises(precios.Bloqueado, match="robots"):
        precios.leer_jsonld(_fuente(), get, {})


def test_desafio_antibots_no_se_esquiva():
    rutas = {"https://tienda.es/robots.txt": resp(ROBOTS),
             "https://tienda.es/cpu": resp("<html>Just a moment</html>", 403, {"cf-mitigated": "challenge"})}
    with pytest.raises(precios.Bloqueado, match="anti-bots"):
        precios.leer_jsonld(_fuente(), get_falso(rutas), {})


# ------------------------------------------------------------------ historico, minimo y aviso
def test_linea_base_y_aviso_solo_al_bajar_del_minimo():
    _config([_fuente("cpu", activa=False, motivo_inactiva="a mano")])
    r0 = precios.registrar("cpu", 229.02, HOY)
    assert r0["baja"] is False and r0["minimo_previo"] is None          # el primero es linea base
    r1 = precios.registrar("cpu", 235.00, MANANA)
    assert r1["baja"] is False and r1["minimo_previo"] == 229.02
    r2 = precios.registrar("cpu", 219.99, datetime(2026, 10, 7, 6, 45))
    assert r2["baja"] is True and r2["minimo_previo"] == 229.02 and r2["aviso"]
    aviso = avisos.recientes(5)[0]
    assert aviso["tipo"] == "precio" and "219.99" in aviso["cuerpo"] and "229.02" in aviso["cuerpo"]
    r3 = precios.registrar("cpu", 219.99, datetime(2026, 10, 8, 6, 45))  # igual al minimo: no es bajada
    assert r3["baja"] is False
    assert [d["precio"] for d in precios.historico("cpu")] == [229.02, 235.0, 219.99, 219.99]
    assert precios.minimo("cpu")["cuando"].startswith("2026-10-07")


def test_apuntar_a_mano_valida_el_precio():
    _config([_fuente("cpu", tipo="manual")])
    assert precios.apuntar("cpu", "689,00 €", "damian", HOY)["origen"] == "manual:damian"
    with pytest.raises(ValueError):
        precios.apuntar("cpu", "agotado", "damian", HOY)
    with pytest.raises(KeyError):
        precios.apuntar("no_existe", "10", "damian", HOY)


# ------------------------------------------------------------------ pasada por el motor de radares
def test_pasada_lee_apunta_y_avisa_por_el_motor():
    _config([_fuente("cpu"), _fuente("placa", url="https://tienda.es/placa"),
             _fuente("caja", activa=False, motivo_inactiva="la tienda no deja"), _fuente("ram", terminos="")])
    precios.registrar("cpu", 229.02, HOY)
    rutas = {"https://tienda.es/robots.txt": resp(ROBOTS), "https://tienda.es/cpu": resp(FICHA % "199.90"),
             "https://tienda.es/placa": resp(FICHA % "79.94")}
    inf = R.pasada("precios", MANANA, get=get_falso(rutas))          # entra por radar.pasada
    assert inf["por_fuente"] == {"cpu": 199.9, "placa": 79.94}
    assert inf["bajas"] == [{"id": "cpu", "precio": 199.9, "minimo_previo": 229.02}]
    assert set(inf["saltadas"]) == {"caja", "ram"} and "terminos" in inf["saltadas"]["ram"]
    assert precios.historico("placa")[0]["vendedor"] == "PcComponentes"
    assert R.hecho_hoy("precios", MANANA)


def test_pasada_tienda_bloqueada_no_se_insiste(monkeypatch):
    monkeypatch.setattr(precios.time, "sleep", lambda s: None)
    _config([_fuente("cpu"), _fuente("placa", url="https://tienda.es/placa")])
    pedidas = []
    rutas = {"https://tienda.es/robots.txt": resp(ROBOTS), "https://tienda.es/cpu": resp("", 403)}
    inf = precios.pasada(MANANA, get=get_falso(rutas, pedidas))
    assert inf["errores"]["cpu"].startswith("BLOQUEADO")
    assert "no se insiste" in inf["saltadas"]["placa"]
    assert "https://tienda.es/placa" not in pedidas                    # ni se pide
    assert precios.historico() == []


def test_pasada_simulada_no_escribe_ni_avisa():
    _config([_fuente("cpu")])
    precios.registrar("cpu", 229.02, HOY)
    rutas = {"https://tienda.es/robots.txt": resp(ROBOTS), "https://tienda.es/cpu": resp(FICHA % "100")}
    inf = precios.pasada(MANANA, simular=True, get=get_falso(rutas))
    assert inf["por_fuente"] == {"cpu": 100.0} and inf["bajas"] == []
    assert len(precios.historico("cpu")) == 1 and avisos.recientes(5) == []


def test_turno_radar_incluye_precios():
    _config([_fuente("cpu", activa=False, motivo_inactiva="a mano")])
    paso = R.turno("radar=precios", ahora=MANANA, get=get_falso({}))
    assert paso["radares"]["precios"]["leidos"] == 0
    assert "precios" in R.texto_resumen(paso)


# ------------------------------------------------------------------ configuracion real
def test_instalar_deja_todo_inactivo_con_motivo_y_linea_base():
    inf = precios.instalar()
    assert inf["config_creado"] and len(inf["linea_base"]) == len(precios.CANDIDATOS)
    cfg = R.cargar_config("precios")
    assert cfg["clase"] == "precios"
    for f in cfg["fuentes"]:                                             # ninguna tienda se lee con codigo hoy
        assert f["activa"] is False and f["terminos"] and f["motivo_inactiva"]
    assert precios.minimo("um870_32_512_amazon")["precio"] == 689.00
    assert precios.instalar()["linea_base"] == []                       # no duplica ni pisa
    inf = precios.pasada(MANANA, get=get_falso({}))
    assert inf["leidos"] == 0 and len(inf["saltadas"]) == len(precios.CANDIDATOS)
