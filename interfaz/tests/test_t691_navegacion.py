# -*- coding: utf-8 -*-
"""T691 fase 1 (maqueta aprobada por Damian el 05/10): cinco destinos (Centro, Tareas, Ordenes, Bandejas, Radares)
en barra inferior (movil) / lateral (>= 900 px), el resto en "Mas"; Centro con "Te toca"; lo viejo en /tecnico.
Ninguna ruta se rompe, la PARADA esta en todas las pantallas y la PWA sigue igual."""
from __future__ import annotations

import re

import pytest

from interfaz import presentar, vistas
from nucleo import tareas as T

DESTINOS = ["/", "/tareas", "/ordenes", "/bandejas", "/radares"]
MAS = ["/turnos", "/proveedores", "/grafo", "/logs", "/ajustes", "/tecnico"]


@pytest.fixture(autouse=True)
def contador_fresco():
    vistas._contador.update(cuando=0.0, n=None)
    yield
    vistas._contador.update(cuando=0.0, n=None)


def _nav(html: str) -> str:
    return re.search(r'<nav class="nav-principal" aria-label="Principal">(.*?)</nav>', html, re.S).group(1)


@pytest.mark.parametrize("ruta", DESTINOS + MAS)
def test_cada_pantalla_responde_con_parada_barra_y_mas(cliente, csrf, ruta):
    r = cliente.get(ruta)
    assert r.status_code == 200
    assert 'id="parada"' in r.text                          # PARADA visible en todas
    nav = _nav(r.text)
    assert [h for h in re.findall(r'href="([^"]+)"', nav)] == DESTINOS
    assert 'class="menu-mas"' in r.text
    for m in MAS:
        assert f'href="{m}"' in r.text


@pytest.mark.parametrize("ruta", DESTINOS)
def test_el_destino_actual_va_marcado(cliente, csrf, ruta):
    nav = _nav(cliente.get(ruta).text)
    assert f'href="{ruta}" aria-current="page"' in nav
    assert nav.count("aria-current") == 1


def test_la_ficha_de_una_tarea_marca_tareas(cliente, csrf):
    t = T.anadir("Algo")
    nav = _nav(cliente.get(f"/tareas/{t['id']}").text)
    assert 'href="/tareas" aria-current="true"' in nav


def test_detalle_tecnico_conserva_los_14_paneles(cliente, csrf):
    r = cliente.get("/tecnico")
    assert r.text.count('class="esqueleto"') == 14
    assert 'href="/tecnico" aria-current="page"' in r.text


def test_centro_nuevo_frase_te_toca_y_turnos(cliente, csrf):
    """Centro v2 (T230, 18/10): frase + Te toca, Hecho, En marcha y Avisos; los turnos van dentro de "En marcha"."""
    r = cliente.get("/").text
    for panel in ("frase", "te_toca", "en_marcha", "hecho", "avisos", "turnos"):
        assert f'hx-get="/centro/{panel}"' in r, panel
    assert r.count('class="esqueleto"') == 5 and 'hx-get="/centro/radares"' not in r     # ya no son 14
    assert 'href="/tecnico"' in r


def test_te_toca_como_mucho_5_tareas_y_bandejas_todas(cliente, csrf):
    for i in range(7):
        T.anadir(f"Firmar papel {i}", depende="damian")
    r = cliente.get("/centro/te_toca").text
    assert "Te toca</h2>" in cliente.get("/").text and "Tus tareas" in r
    assert r.count("tt-fila-titulo") == 5 and 'href="/tareas?depende=damian"' in r and "Ver las 7" in r
    assert cliente.get("/centro/te_toca?todas=1").text.count("tt-fila-titulo") == 7


def test_te_toca_vacio_y_parado(cliente, csrf):
    from nucleo import parada
    assert "Nada te espera" in cliente.get("/centro/te_toca").text
    parada.activar("prueba de parada", "damian")
    assert "NEXO está parado" in cliente.get("/centro/te_toca").text


def test_contador_de_bandejas_cuenta_decisiones_no_tareas(cliente, csrf, monkeypatch):
    T.anadir("Tarea suelta de Damian", depende="damian", etiquetas=["suyo:gustos"])   # suya de verdad (guardia 05/10)
    assert "nav-contador" not in _nav(cliente.get("/").text)
    monkeypatch.setattr(presentar.C, "esperan_ok", lambda: [
        {"tarea": "T001", "n": 1, "cuando": "2026-10-05 10:00:00", "texto": "Cambiar el titulo"},
        {"tarea": "T002", "n": 1, "cuando": "2026-10-05 10:01:00", "texto": "Cerrar"}])
    vistas._contador.update(cuando=0.0, n=None)
    nav = _nav(cliente.get("/radares").text)
    assert re.search(r'class="nav-contador">.*?2.*?pendientes', nav, re.S)
    tt = cliente.get("/centro/te_toca").text
    assert tt.index("Te pregunta algo") < tt.index("Tarea tuya suelta") if "Tarea tuya suelta" in tt else True
    assert tt.index("Te pregunta algo") < tt.index("Tus tareas")     # las decisiones que caducan, antes que las tareas


def test_una_fuente_rota_no_tumba_el_centro(cliente, csrf, monkeypatch):
    def rota():
        raise OSError("disco")
    monkeypatch.setattr(presentar.C, "esperan_ok", rota)
    T.anadir("Firmar", depende="damian")
    r = cliente.get("/centro/te_toca")
    assert r.status_code == 200 and "Firmar" in r.text


def test_bandejas_tiene_tribunal_riesgo_y_revision_con_sus_ids(cliente, csrf):
    r = cliente.get("/bandejas").text
    for panel, ident in (("/centro/tribunal", "panel-tribunal"), ("/centro/riesgo", "panel-riesgo")):
        assert f'id="{ident}" hx-get="{panel}"' in r     # los formularios apuntan a estos ids
    assert 'hx-get="/centro/revision"' in r and 'id="bandeja-tribunal"' in r


def test_pwa_intacta(cliente):
    m = cliente.get("/manifest.webmanifest").json()
    assert m["start_url"] == "/" and m["scope"] == "/"
    assert cliente.get("/sw.js").status_code == 200


def test_radares_pestana_provisional_con_tarjetas_y_fuente_apagada(cliente, csrf):
    """T693 R2: la pestana pinta cada radar, sus tarjetas y por que una fuente no se lee."""
    import json as _json
    from nucleo import radar
    radar.carpeta("prueba").mkdir(parents=True)
    (radar.carpeta("prueba") / "config.json").write_text(_json.dumps({
        "nombre": "Oportunidades", "modo": "real", "fuentes": [
            {"id": "buena", "tipo": "rss", "url": "u", "terminos": "RSS oficial"},
            {"id": "linktree", "tipo": "rss", "url": "v", "activa": False, "motivo_inactiva": "robots.txt lo prohibe"}]}),
        encoding="utf-8")
    radar._guardar_articulos("prueba", [
        {"id": "a", "url": "https://ej.org/cern", "titulo": "CERN Fellowship", "fuente": "buena", "estado": "nueva",
         "nota": 85, "motivo": "organización que te interesa: CERN", "cuando": "2026-10-06T08:00:00"},
        {"id": "b", "url": "https://ej.org/x", "titulo": "Filtrada", "fuente": "buena", "estado": "filtrada",
         "cuando": "2026-10-06T08:00:00"}])
    r = cliente.get("/radares").text
    assert "CERN Fellowship" in r and "nota 85" in r and "Por qué te lo enseño" in r
    assert "Filtrada" not in r and "robots.txt lo prohibe" in r
