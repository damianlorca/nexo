# -*- coding: utf-8 -*-
"""Bloque 5 (12/10), opcion A de Damian: barra lateral con "Mas -> Detalle tecnico" abajo, PARADA siempre visible,
Centro con saludo + estado en una frase + tres columnas (Te toca a ti / En marcha ahora / Hecho hoy) + fila de
Radares, modo OSCURO por defecto y lenguaje llano (sin IDs ni jerga en la vista principal)."""
from __future__ import annotations

import re
from datetime import date, datetime

import pytest

from interfaz import presentar
from nucleo import tareas as T


@pytest.fixture
def sin_turnos(monkeypatch):
    from nucleo import planificador
    monkeypatch.setattr(planificador, "resumen_centro", lambda: {"marcha": None, "cola": [], "proximo": None,
                                                                 "desactivados": 0})


def test_llano_quita_ids_corchetes_y_jerga():
    assert presentar.llano("T559 · [Propuesta de T274] separar estados") == "Separar estados"
    assert presentar.llano("A0037 · instalar algo (T859)") == "Instalar algo"
    assert presentar.llano("Revisar borrador de T123: algo") == "Revisar borrador de: algo"
    assert presentar.chip_llano("R2 · espera tu OK · vence 2026-10-19") == "Espera tu visto bueno"
    assert presentar.chip_llano("Aprobación ámbar · caduca 2026-10-13") == "Pide permiso"
    assert presentar.chip_llano("Chat de una tarea · caduca en 24 h") == "Te pregunta algo"


def test_saludo_segun_la_hora():
    assert presentar.saludo(datetime(2026, 10, 12, 9)) == "Buenos días, Damián"
    assert presentar.saludo(datetime(2026, 10, 12, 17)) == "Buenas tardes, Damián"
    assert presentar.saludo(datetime(2026, 10, 12, 23)) == "Buenas noches, Damián"


def test_modo_oscuro_por_defecto(cliente, csrf):
    r = cliente.get("/").text
    assert '<html lang="es" data-tema="oscuro">' in r
    js = cliente.get("/estatico/nexo.js").text
    assert 'TEMAS = ["oscuro", "claro"]' in js and ': "oscuro";' in js          # lo guardado viejo -> oscuro


def test_centro_saludo_cuatro_paneles_en_dos_columnas(cliente, csrf):
    """Centro v2 (T230, 18/10): Te toca + Hecho a la izquierda, En marcha + Avisos a la derecha (en movil, ese orden)."""
    r = cliente.get("/").text
    assert re.search(r"<h1>Buen(os|as) (días|tardes|noches), Damián</h1>", r)
    cols = re.findall(r'<section class="centro-col" aria-labelledby="[^"]+">\s*<h2 id="[^"]+">([^<]+)</h2>', r)
    assert cols == ["Te toca", "Hecho desde tu última visita", "En marcha", "Avisos"]
    assert r.count('class="centro-lado"') == 2 and 'id="fila-radares"' not in r     # los radares salen del Centro
    assert 'href="/radares"' in r and 'id="parada"' in r


def test_barra_lateral_mas_abajo_con_detalle_tecnico_el_primero(cliente, csrf):
    r = cliente.get("/").text
    lateral = re.search(r'<aside class="barra-lateral">(.*?)</aside>', r, re.S).group(1)
    assert lateral.index('class="nav-principal"') < lateral.index('class="nav-mas-lateral"')
    mas = re.search(r'<nav class="nav-mas-lateral".*?</nav>', lateral, re.S).group(0)
    enlaces = re.findall(r'href="([^"]+)"', mas)
    assert enlaces[0] == "/tecnico" and "<summary>Más</summary>" in mas
    assert set(enlaces) == {"/tecnico", "/turnos", "/proveedores", "/grafo", "/logs", "/ajustes"}


def test_te_toca_en_llano_sin_ids(cliente, csrf):
    t = T.anadir("Firmar el papel del banco", depende="damian")
    r = cliente.get("/centro/te_toca").text
    assert "Firmar el papel del banco" in r and t["id"] not in r.replace(f'/tareas/{t["id"]}', "")
    assert "Tus tareas" in r and f'href="/tareas/{t["id"]}"' in r and ">Abrir</a>" in r     # fila de una linea


def test_frase_de_estado(cliente, csrf, sin_turnos):
    assert "NEXO funciona. Nada te espera." in cliente.get("/centro/frase").text
    T.anadir("Firmar", depende="damian")
    assert "NEXO funciona. Tienes 1 tarea tuya, ninguna con prisa." in cliente.get("/centro/frase").text
    from nucleo import parada
    parada.activar("prueba", "damian")
    assert "NEXO está parado" in cliente.get("/centro/frase").text


def test_en_marcha_en_tres_lineas_con_los_turnos_en_llano(cliente, csrf, monkeypatch):
    t = T.anadir("Ordenar los reels guardados")
    T.actualizar(t["id"], estado="en_curso")
    from nucleo import planificador
    monkeypatch.setattr(planificador, "resumen_centro", lambda: {
        "marcha": {"nombre": "Implementador (permanente)", "transcurrido": "3 min 05 s", "tarea": t["id"]},
        "cola": [{"turno": "x", "nombre": "Tribunal de revision (sin Claude)"}],
        "proximo": {"nombre": "Banco de modelos (diario)", "cuando": "mañana 07:15"}, "desactivados": 0})
    r = cliente.get("/centro/en_marcha").text
    assert re.findall(r"<dt>([^<]+)</dt>", r) == ["Ahora", "Después · mañana 07:15", "En cola"]
    assert "Programar una tarea con tests ya escritos" in r and "3 min 05 s" in r and "«Ordenar los reels guardados»" in r
    assert "Medir qué IA va mejor" in r and "Revisar los borradores pendientes con tres IAs distintas" in r
    assert "Implementador (permanente)" not in r and t["id"] not in r.replace(f"estado=en_curso", "")


def test_en_marcha_vacio(cliente, csrf, sin_turnos):
    r = cliente.get("/centro/en_marcha").text
    assert "Nada. NEXO está esperando al siguiente turno." in r and "Vacía." in r


def test_radares_fila(cliente, csrf):
    import json as _json
    from nucleo import radar
    assert "Todavía no hay ningún radar" in cliente.get("/centro/radares").text
    radar.carpeta("prueba").mkdir(parents=True)
    (radar.carpeta("prueba") / "config.json").write_text(_json.dumps({
        "nombre": "Oportunidades", "modo": "real", "fuentes": [{"id": "buena", "tipo": "rss", "url": "u"}]}),
        encoding="utf-8")
    radar._guardar_articulos("prueba", [
        {"id": "a", "url": "https://ej.org/cern", "titulo": "CERN Fellowship", "fuente": "buena", "estado": "nueva",
         "nota": 85, "cuando": "2026-10-06T08:00:00"}])
    r = cliente.get("/centro/radares").text
    assert "Oportunidades" in r and "CERN Fellowship" in r


def test_un_panel_que_falla_no_tumba_el_centro(cliente, csrf, monkeypatch):
    monkeypatch.setattr(presentar, "hecho_desde_visita", lambda: 1 / 0)
    r = cliente.get("/centro/hecho")
    assert r.status_code == 200 and "ZeroDivisionError" in r.text


def test_el_movil_conserva_la_barra_inferior_y_el_viewport(cliente, csrf):
    r = cliente.get("/").text
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in r
    css = cliente.get("/estatico/nexo.css").text
    assert ".nav-principal {\n  position: fixed; left: 0; right: 0; bottom: 0;" in css    # barra del pulgar
    assert ".cabecera { position: sticky; top: 0;" in css                                   # PARADA siempre a la vista
