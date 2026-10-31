# -*- coding: utf-8 -*-
"""T192: la cola de revision de Claude se ve en la web, avisa por push y la web no cierra la origen antes."""
from __future__ import annotations

from datetime import datetime

from interfaz import vigilancia
from interfaz.eventos import Bus
from interfaz.vigilancia import Vigilante
from nucleo import avisos, revision
from nucleo import tareas as T

DOS = ("### PROPUESTAS IMPLEMENTABLES\n"
       "- QUE: Anadir las reglas al rol de programador | DONDE: roles y prompts | VALOR: 4 | ESFUERZO: 1 | "
       "RIESGO: bajo: solo texto\n"
       "- QUE: Cargar la politica solo en tareas de codigo | DONDE: router | VALOR: 3 | ESFUERZO: 3 | "
       "RIESGO: medio: puede no activarse\n")


def _post(cliente, csrf, url, **datos):
    return cliente.post(url, data=datos, headers={"X-CSRF-Token": csrf})


def test_panel_vacio(cliente, csrf):
    r = cliente.get("/centro/revision")
    assert r.status_code == 200 and "Nada esperando la revisión de Claude." in r.text


def test_panel_muestra_borrador_y_sus_dos_propuestas_con_antiguedad(cliente, csrf):
    # 04/10: la fecha era fija (27/09) y el test caducaba a los 7 dias; ahora es la de ayer.
    from datetime import datetime, timedelta
    nombre = f"T001_{datetime.now() - timedelta(days=1):%Y%m%d_%H%M}.md"
    o = T.anadir("Investigar X", etiquetas=["cat:investigacion"])
    r = revision.registrar_borrador(o["id"], nombre, texto=DOS, auditoria="APROBADA")
    html = cliente.get("/centro/revision").text
    assert "1 borrador y 2 propuestas esperando" in html
    assert f'href="/tareas/{r["revision"]["id"]}"' in html and f'href="/tareas/{o["id"]}"' in html
    assert f"/borrador?f={nombre}" in html
    for p in r["propuestas"]:
        assert f'href="/tareas/{p["id"]}"' in html
    assert "valor 4 · esfuerzo 1" in html and "riesgo medio: puede no activarse" in html
    assert " d</strong>" in html and "Revisión atrasada" not in html


def test_panel_marca_la_alerta_si_alguno_pasa_de_siete_dias(cliente, csrf):
    o = T.anadir("Investigar Y")
    revision.registrar_borrador(o["id"], "T001_20260901_1000.md", texto=DOS)
    html = cliente.get("/centro/revision").text
    assert "Revisión atrasada" in html and "dias (maximo 7)" in html


def test_la_web_no_cierra_la_origen_sin_veredicto(cliente, csrf):
    o = T.anadir("Investigar Z")
    revision.registrar_borrador(o["id"], "T001_20260927_1000.md", texto=DOS)
    r = _post(cliente, csrf, f"/tareas/{o['id']}/completar", nota="cierro yo")
    assert "No se cierra" in r.text and "espera la revision de Claude" in r.text
    assert T.buscar(o["id"])["estado"] == "pendiente"


def test_la_lista_filtra_por_estado_propuesta(cliente, csrf):
    o = T.anadir("Investigar W")
    revision.registrar_borrador(o["id"], "T001_20260927_1000.md", texto=DOS)
    html = cliente.get("/tareas", params={"estado": "propuesta"}).text
    assert "[Propuesta de" in html and "PROPUESTA (sin revisar)" in html


def test_vigilancia_comprueba_la_cola_y_el_aviso_sale_como_evento(monkeypatch):
    v = Vigilante(Bus())
    assert v.revisar() == []   # foto inicial (y primera comprobacion de la cola: vacia, sin aviso)
    for i in range(revision.UMBRAL_COLA):
        revision.registrar_borrador(T.anadir(f"inv {i}")["id"], f"T00{i}_{datetime.now():%Y%m%d}_100{i}.md", texto=DOS)
    assert [e for e in v.revisar() if e[0] == "aviso"] == []          # aun no toca comprobar (CADA_COLA)
    monkeypatch.setattr(vigilancia, "CADA_COLA", 0.0)
    v.revisar()                                                        # comprueba: deja el aviso en disco
    eventos = [e for e in v.revisar() if e[0] == "aviso"]              # y la siguiente pasada lo emite
    assert len(eventos) == 1 and eventos[0][1]["tipo"] == "revision"
    assert "5 borrador" in eventos[0][1]["titulo"] and eventos[0][1]["ruta"] == "/#t-revision"
    v.revisar()
    assert len(avisos.recientes()) == 1                                # uno al dia, no uno por pasada


def test_panel_freno_f0_muestra_cola_limites_y_semanas(cliente, csrf, monkeypatch):
    """T666: el Centro ensena propuestas y revisiones frente a sus limites y las entradas/salidas por semana."""
    from nucleo import freno
    monkeypatch.setattr(freno, "LIMITE_PROPUESTAS", 1)
    o = T.anadir("Investigar X", etiquetas=["cat:investigacion"])
    revision.registrar_borrador(o["id"], "T001_20260927_1539.md", texto=DOS, auditoria="APROBADA")
    html = cliente.get("/centro/freno").text
    assert "Freno puesto:" in html and "2 propuestas abiertas (limite 1)" in html
    assert "Propuestas abiertas <strong>2</strong> / 1" in html and "revisiones pendientes <strong>1</strong> / 15" in html
    assert "Propuestas entran" in html and html.count("<tr><th scope=\"row\">") == 6
    assert 'hx-get="/centro/freno"' in cliente.get("/tecnico").text
