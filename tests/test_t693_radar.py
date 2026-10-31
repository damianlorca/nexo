# -*- coding: utf-8 -*-
"""T693 R1: motor comun de radares. Sin red: las fuentes son dobles."""
from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from nucleo import radar as R
from nucleo import plantillas_turno, turnos

AHORA = datetime(2026, 10, 5, 8, 15)

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>Google STEP internship 2027</title><link>https://ej.org/step?utm_source=ig&amp;id=3</link>
<pubDate>Sun, 04 Oct 2026 10:00:00 GMT</pubDate><description>&lt;p&gt;Paid internship&lt;/p&gt;</description></item>
<item><title>CERN summer student programme</title><link>https://ej.org/cern/</link></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>ESA YGT 2027</title><link href="https://esa.int/ygt"/><updated>2026-10-03T00:00:00Z</updated>
<summary>Young graduate trainees</summary></entry></feed>"""


def respuesta(texto="", datos=None, codigo=200):
    def raise_for_status():
        if codigo >= 400:
            raise RuntimeError(f"HTTP {codigo}")
    return SimpleNamespace(text=texto, json=lambda: datos, raise_for_status=raise_for_status)


def get_falso(rutas: dict):
    def get(url, params=None, cabeceras=None):
        return rutas[url]
    return get


def _config(radar_id="prueba", **extra):
    cfg = {"id": radar_id, "nombre": "Prueba", "por_dia": 2, "modo": "real",
           "fuentes": [{"id": "feed", "tipo": "rss", "url": "https://ej.org/rss", "terminos": "RSS oficial, 05/10"},
                       {"id": "api", "tipo": "api", "url": "https://ej.org/api", "lista": "data.items",
                        "campos": {"titulo": "name", "url": "link", "fecha": "created", "texto": "desc"},
                        "terminos": "API publica documentada, 05/10"}]}
    cfg.update(extra)
    R.carpeta(radar_id).mkdir(parents=True, exist_ok=True)
    (R.carpeta(radar_id) / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return cfg


API = {"data": {"items": [{"name": "Anthropic campus ambassadors", "link": "https://ej.org/ant", "created": 1791100000,
                           "desc": "student programme"},
                          {"name": "Google STEP internship 2027", "link": "https://ej.org/step?id=3&fbclid=zz"}]}}


def _rutas(api=None, rss=RSS):
    return {"https://ej.org/rss": respuesta(rss), "https://ej.org/api": respuesta(datos=api if api is not None else API)}


def test_normalizar_url_quita_rastreo_fragmento_y_barra():
    assert R.normalizar_url("HTTPS://www.Ej.org/a/?utm_source=ig&id=3&fbclid=x#arriba") == "https://ej.org/a?id=3"
    assert R.id_articulo("https://ej.org/a/?igshid=1") == R.id_articulo("https://ej.org/a")


def test_lector_rss_y_atom():
    f = {"id": "feed", "url": "u"}
    rss = R.leer_rss(f, AHORA, get_falso({"u": respuesta(RSS)}))
    assert [a["titulo"] for a in rss] == ["Google STEP internship 2027", "CERN summer student programme"]
    assert rss[0]["fecha"] == "2026-10-04" and rss[0]["texto"] == "Paid internship"
    atom = R.leer_rss(f, AHORA, get_falso({"u": respuesta(ATOM)}))
    assert atom[0]["url"] == "https://esa.int/ygt" and atom[0]["fecha"] == "2026-10-03"


def test_lector_rss_niega_entidades():
    malo = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>'
    with pytest.raises(ValueError):
        R.leer_rss({"id": "f", "url": "u"}, AHORA, get_falso({"u": respuesta(malo)}))


def test_lector_api_y_json_con_campos_y_url_base(tmp_path):
    f = {"id": "api", "url": "u", "lista": "data.items", "campos": {"titulo": "name", "url": "link", "fecha": "created"}}
    arts = R.leer_api(f, AHORA, get_falso({"u": respuesta(datos=API)}))
    assert arts[0]["titulo"] == "Anthropic campus ambassadors" and arts[0]["fecha"].startswith("2026-")
    archivo = tmp_path / "feed.json"
    archivo.write_text(json.dumps({"items": [{"title": "Uno", "url": "/uno"}]}), encoding="utf-8")
    arts = R.leer_json({"id": "j", "url": f"archivo:{archivo}", "url_base": "https://ej.org"}, AHORA)
    assert len(arts) == 1 and arts[0]["url"] == "https://ej.org/uno" and arts[0]["titulo"] == "Uno"


def test_lector_vigia_reutiliza_sus_fuentes(monkeypatch):
    from nucleo import vigia
    monkeypatch.setitem(vigia.FUENTES, "groq", lambda ahora: [
        {"fuente": "groq", "id": "m1", "nombre": "m1", "url": "https://console.groq.com/docs/models", "fecha": ""},
        {"fuente": "groq", "id": "m2", "nombre": "m2", "url": "https://console.groq.com/docs/models", "fecha": ""}])
    arts = R.leer_vigia({"id": "groq", "funcion": "groq"}, AHORA)
    assert [a["titulo"] for a in arts] == ["m1", "m2"] and arts[0]["id"] != arts[1]["id"]


def test_fuente_sin_terminos_no_se_lee_y_una_caida_no_tumba_el_resto():
    cfg = {"fuentes": [{"id": "sin", "tipo": "rss", "url": "x"},
                       {"id": "off", "tipo": "rss", "url": "y", "terminos": "ok", "activa": False,
                        "motivo_inactiva": "terminos no lo permiten"},
                       {"id": "rota", "tipo": "rss", "url": "z", "terminos": "ok"},
                       {"id": "buena", "tipo": "rss", "url": "w", "terminos": "ok"}]}
    leido = R.leer_fuentes(cfg, AHORA, get_falso({"z": respuesta(codigo=500), "w": respuesta(RSS)}))
    assert leido["saltadas"] == {"sin": "sin terminos comprobados (como se respeta su web): no se lee",
                                 "off": "terminos no lo permiten"}
    assert "rota" in leido["errores"] and leido["por_fuente"] == {"buena": 2}


def test_deduplica_por_url_por_titulo_y_dentro_del_lote():
    almacen = [{"id": "x", "url": "https://ej.org/cern", "titulo": "CERN summer student programme 2026 edition"}]
    items = [R._articulo({"id": "f"}, "https://ej.org/cern/?utm_source=a", "CERN otra cosa"),
             R._articulo({"id": "f"}, "https://otra.org/1", "Google STEP internship programme 2027 Europe"),
             R._articulo({"id": "g"}, "https://otra.org/2", "Google STEP internship programme 2027 Europe"),
             R._articulo({"id": "g"}, "https://otra.org/3", "ESA young graduate trainee programme")]
    nuevos, repetidos = R.deduplicar(items, almacen)
    assert [a["url"] for a in nuevos] == ["https://otra.org/1", "https://otra.org/3"]
    assert sorted(repetidos.values()) == ["ya visto (misma URL)", "ya visto (titulo casi igual)"]


def test_marca_lo_descartado_antes_sin_quitarlo(monkeypatch):
    from nucleo import descartes
    monkeypatch.setattr(descartes, "buscar", lambda texto, reg: [{"id": "T435"}] if "ESA" in texto else [])
    nuevos, _ = R.deduplicar([R._articulo({"id": "g"}, "https://o.org/3", "ESA young graduate trainee programme")],
                             [], reg_descartes=[{"id": "T435", "texto": "x"}])
    assert nuevos[0]["descartado_antes"] == "T435"


def test_primera_pasada_es_linea_base_y_la_segunda_publica_lo_nuevo():
    _config()
    inf = R.pasada("prueba", AHORA, get=get_falso(_rutas()))
    assert inf["linea_base"] == 3 and inf["publicadas"] == [] and inf["repetidos"] == 1   # STEP sale en las dos
    assert {a["estado"] for a in R.articulos("prueba")} == {"base"}
    items = API["data"]["items"] + [{"name": "NVIDIA graduate program", "link": "https://ej.org/nv"}]
    inf = R.pasada("prueba", AHORA.replace(day=6), get=get_falso(_rutas({"data": {"items": items}})))
    assert [a["titulo"] for a in inf["publicadas"]] == ["NVIDIA graduate program"] and inf["linea_base"] == 0
    assert [a["titulo"] for a in R.tarjetas("prueba")] == ["NVIDIA graduate program"]


def test_por_dia_y_nota_deciden_las_publicadas():
    _config(por_dia=1, umbral=50)
    R.pasada("prueba", AHORA, get=get_falso(_rutas({"data": {"items": []}})))     # linea base de las dos fuentes
    otro = (RSS.replace("Google STEP", "Meta").replace("ej.org/step", "ej.org/meta")
            .replace("CERN summer", "Nada que ver").replace("ej.org/cern", "ej.org/x"))
    notas = {"Meta internship 2027": (80, "empresa que te interesa"), "Nada que ver student programme": (40, "")}
    inf = R.pasada("prueba", AHORA.replace(day=6), get=get_falso(_rutas({"data": {"items": []}}, otro)),
                   puntuar=lambda c, a: notas[a["titulo"]])
    assert [(a["titulo"], a["nota"]) for a in inf["publicadas"]] == [("Meta internship 2027", 80)]
    estados = {a["titulo"]: a["estado"] for a in R.articulos("prueba")}
    assert estados["Meta internship 2027"] == "nueva" and estados["Nada que ver student programme"] == "filtrada"


def test_simular_usa_almacen_sombra_y_no_toca_el_real():
    _config(modo="simular")
    inf = R.pasada("prueba", AHORA, get=get_falso(_rutas()))
    assert inf["simular"] and inf["archivo"].startswith("simulacion_20261005_0815")
    assert R.articulos("prueba") == [] and len(R.articulos("prueba", sim=True)) == 3
    assert R.hecho_hoy("prueba", AHORA) and not R.hecho_hoy("prueba", AHORA.replace(day=6))


def test_caducan_sin_borrarse():
    alm = [{"estado": "nueva", "cuando": "2026-08-01T00:00:00"}, {"estado": "guardada", "cuando": "2026-08-01T00:00:00"},
           {"estado": "nueva", "cuando": "2026-10-01T00:00:00"}]
    assert R.caducar(alm, {"caducidad_dias": 30}, AHORA) == 1
    assert [a["estado"] for a in alm] == ["caducada", "guardada", "nueva"]


def test_turno_radar_puerta_paso_y_resumen():
    _config("uno", modo="simular")
    _config("dos", activo=False)
    assert R.ids_de_texto("") == ["dos", "uno"] and R.ids_de_texto("radar=uno") == ["uno"]
    ctx = {"plantilla": "radar", "texto": "Pasada diaria"}
    assert plantillas_turno.candidatas(ctx) == 1
    paso = R.turno("", ahora=AHORA, get=get_falso(_rutas()))
    assert list(paso["radares"]) == ["uno"] and paso["radares"]["uno"]["linea_base"] == 3
    assert "uno (simulado): 4 leídos" in R.texto_resumen(paso)
    assert R.candidatas("", AHORA) == 0 and R.turno("", ahora=AHORA, get=get_falso(_rutas())) == {"radares": {}}
    assert "radar" in turnos.PLANTILLAS and "ya pasaron hoy" in plantillas_turno.por_que_nada(ctx)


def test_vigia_como_radar_con_sus_mismas_fuentes():
    from nucleo import vigia
    R.instalar_vigia()
    cfg = R.cargar_config("vigia")
    assert cfg["modo"] == "simular" and {f["funcion"] for f in cfg["fuentes"]} == set(vigia.FUENTES)
    assert all(R.fuente_lista(f) is None for f in cfg["fuentes"])
    (R.carpeta("vigia") / "config.json").write_text(json.dumps({**cfg, "por_dia": 9}), encoding="utf-8")
    R.instalar_vigia()                                            # no pisa uno editado
    assert R.cargar_config("vigia")["por_dia"] == 9


def test_id_de_radar_no_valido():
    with pytest.raises(ValueError):
        R.carpeta("../fuera")
