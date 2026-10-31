# -*- coding: utf-8 -*-
"""T550: vigilancia de los terminos de uso (nucleo/terminos.py). Sin red: la lectura es un doble."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from nucleo import terminos, vigia

AHORA = datetime(2026, 10, 5, 9, 0)
TERMINOS_REAL = vigia._terminos   # al importar: antes de que el conftest lo anule en cada test
BASE = "Términos. " + "Puedes usar el servicio para fines personales. " * 40 + "No puedes replicar el servicio."


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(vigia, "CARPETA", tmp_path / "vigia")
    monkeypatch.setattr(terminos, "TERMINOS", ({"clave": "g", "nombre": "Gemini API", "url": "https://x/g"},
                                               {"clave": "o", "nombre": "OpenAI", "url": "https://x/o", "archivo": True}))
    avisos, tareas = [], []
    return {"avisos": avisos, "tareas": tareas,
            "avisar": lambda titulo, cuerpo, ruta, clave: avisos.append((titulo, cuerpo, ruta, clave)),
            "crear": lambda titulo, detalle: tareas.append((titulo, detalle)) or {"id": "T9999"}}


def _comprobar(ent, textos, ahora=AHORA):
    def leer(t):
        v = textos[t["clave"]]
        if isinstance(v, Exception):
            raise v
        return v, "directa"
    return terminos.comprobar(ahora, leer_=leer, avisar=ent["avisar"], crear_tarea=ent["crear"])


def test_texto_sin_scripts_ni_etiquetas():
    html = "<html><script>var x=1</script><style>p{}</style><p>Hola&nbsp;&amp; adi&oacute;s</p><!-- c --></html>"
    assert terminos.texto(html) == "Hola & adiós"


def test_linea_base_igual_y_cambio_con_tarea_y_aviso(entorno):
    assert _comprobar(entorno, {"g": BASE, "o": BASE}) == {"g": "base", "o": "base"}
    assert _comprobar(entorno, {"g": BASE, "o": BASE}) == {"g": "igual", "o": "igual"}
    assert not entorno["avisos"] and not entorno["tareas"]
    nuevo = BASE.replace("No puedes replicar el servicio.", "No puedes replicar ni clonar voces del servicio.")
    assert _comprobar(entorno, {"g": nuevo, "o": BASE}) == {"g": "cambio", "o": "igual"}
    titulo, detalle = entorno["tareas"][0]
    assert titulo == "Revisar cambio de términos: Gemini API (05/10)"
    assert "- No puedes replicar el servicio." in detalle and "+ No puedes replicar ni clonar voces del servicio." in detalle
    assert entorno["avisos"][0][0] == "Cambian los términos: Gemini API" and entorno["avisos"][0][2] == "/tareas/T9999"
    assert _comprobar(entorno, {"g": nuevo, "o": BASE})["g"] == "igual"   # el cambio se avisa una vez


def test_sin_leer_nunca_es_sin_cambios_y_avisa_a_los_7_dias(entorno):
    _comprobar(entorno, {"g": BASE, "o": BASE})
    r = _comprobar(entorno, {"g": BASE, "o": LookupError("directa: HTTP 403; archive.org: HTTP 429")})
    assert r["o"].startswith("sin leer: directa: HTTP 403") and not entorno["avisos"]
    r = _comprobar(entorno, {"g": BASE, "o": LookupError("HTTP 403")}, AHORA + timedelta(days=7))
    assert entorno["avisos"] and entorno["avisos"][0][0] == "No puedo leer: OpenAI"
    assert _comprobar(entorno, {"g": BASE, "o": BASE}, AHORA + timedelta(days=8))["o"] == "igual"   # vuelve, sin falso cambio
    assert "sin_leer_desde" not in vigia._leer("terminos.json", {})["o"]


def test_leer_prueba_archive_org_solo_si_toca_y_rechaza_paginas_cortas():
    def bloqueado(url):
        raise LookupError("403")
    largo = "<p>" + "Texto de términos. " * 200 + "</p>"
    assert terminos.leer({"url": "u", "archivo": True}, directo=bloqueado, archivo=lambda u: largo)[1] == "archive.org"
    with pytest.raises(LookupError):
        terminos.leer({"url": "u"}, directo=bloqueado, archivo=lambda u: largo)
    with pytest.raises(LookupError, match="solo 5 caracteres"):
        terminos.leer({"url": "u"}, directo=lambda u: "<p>Error</p>")


def test_el_vigia_lo_llama_y_no_se_cae(monkeypatch):
    monkeypatch.setattr(terminos, "comprobar", lambda ahora: 1 / 0)
    assert vigia._terminos.__name__ == "<lambda>"          # en los tests el conftest lo anula (sin red)
    assert TERMINOS_REAL(AHORA) == {"error": "ZeroDivisionError"}
