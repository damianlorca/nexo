# -*- coding: utf-8 -*-
"""T675 fase 2 (informe documentacion/T675_INFORME_TURNOS.md, §5): menos propuestas y mejores en los turnos de
revision. Tope 3 y cada propuesta con ARCHIVO:LINEA y un TEST que la comprueba; las que no lo traigan no se crean.
(El 76 % de las 303 propuestas generadas se descartaba: el tope de 5 y la falta de evidencia lo alimentaban.)"""
from __future__ import annotations

from nucleo import plantillas_turno as PT, revision, trabajo
from nucleo import tareas as T

BUENA = ("- QUE: validar el id en tomar | DONDE: nucleo/cola.py:12 | TEST: tests/test_cola.py::test_vacia | VALOR: 4 | "
         "ESFUERZO: 1 | RIESGO: bajo: solo una guarda")
SIN_LINEA = BUENA.replace("nucleo/cola.py:12", "la cola")
SIN_TEST = BUENA.replace("TEST: tests/test_cola.py::test_vacia | ", "")


def _texto(*lineas):
    return "Informe.\n### PROPUESTAS IMPLEMENTABLES\n" + "\n".join(lineas) + "\n"


def test_sin_evidencia_el_comportamiento_de_siempre():
    r = revision.extraer_propuestas(_texto(SIN_LINEA, SIN_TEST))
    assert len(r["propuestas"]) == 2 and not r["problemas"]


def test_con_evidencia_solo_pasan_las_que_traen_archivo_linea_y_test():
    r = revision.extraer_propuestas(_texto(BUENA, SIN_LINEA, SIN_TEST), evidencia=True)
    assert [p["donde"] for p in r["propuestas"]] == ["nucleo/cola.py:12"]
    assert r["propuestas"][0]["test"] == "tests/test_cola.py::test_vacia"
    assert len(r["sin_evidencia"]) == 2
    assert any("sin archivo:linea" in s for s in r["sin_evidencia"]) and any("sin TEST" in s for s in r["sin_evidencia"])


def test_el_tope_es_3():
    r = revision.extraer_propuestas(_texto(*[BUENA.replace("validar", f"validar{i}") for i in range(5)]),
                                    evidencia=True)
    assert len(r["propuestas"]) == 3 and r["sobran"] == 2


def test_la_plantilla_de_revision_pide_tope_3_archivo_linea_y_test():
    assert "maximo 3" in trabajo.PROPUESTAS_FORMATO_CODIGO and "TEST:" in trabajo.PROPUESTAS_FORMATO_CODIGO
    lote = {"id": "T1", "titulo": "x", "etiquetas": ["plantilla:revisar_codigo"], "detalle": ""}
    assert PT.plantilla_de(lote) == "revisar_codigo"
    assert "maximo 3" in PT.instruccion(lote, 600)
    assert "maximo 5" in trabajo.PROPUESTAS_FORMATO     # el resto de turnos e investigaciones, igual que antes


def test_registrar_borrador_de_revision_no_crea_las_que_no_traen_evidencia(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "v" / "tareas.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".lock")
    o = T.anadir("Revision de codigo: lote 1", etiquetas=["plantilla:revisar_codigo"], depende="ia")
    res = revision.registrar_borrador(o["id"], "T_20261004_1000.md", texto=_texto(BUENA, SIN_LINEA, SIN_TEST))
    assert len(res["propuestas"]) == 1
    assert "sin evidencia" in " ".join(n["texto"] for n in T.buscar(o["id"])["notas"]).lower()
    o2 = T.anadir("Otra normal", depende="ia")
    res2 = revision.registrar_borrador(o2["id"], "T_20261004_1001.md", texto=_texto(BUENA, SIN_LINEA))
    assert len(res2["propuestas"]) == 2
