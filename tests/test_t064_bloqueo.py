# -*- coding: utf-8 -*-
"""T064: `bloqueada_por` (id de otra tarea todavia viva) ahora SI afecta al orden: ni `siguiente()` ni las candidatas
del turno de NEXO eligen una tarea cuyo bloqueo sigue abierto (hueco real hallado el 23/09: 2 de 57 vivas lo usaban)."""
from __future__ import annotations

import pytest

from nucleo import tareas as T, trabajo


@pytest.fixture
def cola(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "v" / "tareas.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".lock")


def test_bloqueada_por_una_tarea_viva_no_es_la_siguiente(cola):
    base = T.anadir("Base", importancia=2, urgencia=2, depende="ia")
    dep = T.anadir("Depende de la base", importancia=5, urgencia=5, depende="ia", bloqueada_por=base["id"])
    assert T.esta_bloqueada(T.buscar(dep["id"]))
    assert T.siguiente()["id"] == base["id"]


def test_al_cerrarse_la_bloqueante_la_tarea_vuelve_a_salir(cola):
    base = T.anadir("Base", importancia=2, urgencia=2, depende="ia")
    dep = T.anadir("Depende de la base", importancia=5, urgencia=5, depende="ia", bloqueada_por=base["id"])
    T.actualizar(base["id"], estado="hecha")
    assert not T.esta_bloqueada(T.buscar(dep["id"]))
    assert T.siguiente()["id"] == dep["id"]


def test_texto_libre_o_id_inexistente_no_bloquea(cola):
    a = T.anadir("A", depende="ia", bloqueada_por="esperando a que Damian conteste")
    b = T.anadir("B", depende="ia", bloqueada_por="T9999")
    assert not T.esta_bloqueada(T.buscar(a["id"])) and not T.esta_bloqueada(T.buscar(b["id"]))


def test_no_se_bloquea_a_si_misma(cola):
    a = T.anadir("A", depende="ia")
    T.actualizar(a["id"], bloqueada_por=a["id"])
    assert not T.esta_bloqueada(T.buscar(a["id"]))


def test_el_turno_no_coge_una_tarea_bloqueada(cola):
    base = T.anadir("Base", depende="ia", etiquetas=["cat:investigacion"])
    dep = T.anadir("Dep", depende="ia", etiquetas=["cat:investigacion"], bloqueada_por=base["id"])
    ids = [t["id"] for t in trabajo.candidatas()]
    assert base["id"] in ids and dep["id"] not in ids
