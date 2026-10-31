# -*- coding: utf-8 -*-
"""T145 pieza B: el ejecutor de acciones directas (T848) pregunta el permiso del canal a permisos_canal (T853).

Tests dados (los escribe Claude; el implementador SOLO cambia nucleo/orden_ejecutor.py). Va DESPUES de T848 y T853.
Contrato:
- Paso 1 de `ejecutar` (canal) pasa a ser: `permisos_canal.permitido(canal, "accion_directa")` (llamado por el
  modulo, para que los dobles funcionen); si es (False, motivo) -> {"estado": "NO_PERMITIDA", "respuesta": con el
  motivo}. Ya no se mira PERMITIDAS para decidir el canal.
- PERMITIDAS["web"] sigue siendo la LISTA BLANCA de acciones (paso 2) y vale para cualquier canal con permiso.
- Si permisos_canal.permitido lanza una excepcion -> NO_PERMITIDA (fallo cerrado), nunca EJECUTADA ni ERROR.
- Todo lo demas de T848 no cambia (sus tests siguen pasando).
"""
from __future__ import annotations

import pytest

from nucleo import orden_ejecutor as E
from nucleo import permisos_canal as PC
from nucleo import turnos


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(turnos, "BANDERA", tmp_path / "TURNOS_DESACTIVADOS")


def test_la_politica_decide_el_canal(monkeypatch):
    monkeypatch.setitem(PC.POLITICA, "telegram", frozenset(PC.POLITICA["telegram"] | {"accion_directa"}))
    r = E.ejecutar({"accion": "turnos", "activar": False}, "telegram")
    assert r["estado"] == "EJECUTADA" and turnos.desactivados()


def test_sin_permiso_dice_el_motivo_de_la_politica():
    r = E.ejecutar({"accion": "turnos", "activar": False}, "turno")
    assert r["estado"] == "NO_PERMITIDA" and "turno" in r["respuesta"] and "accion_directa" in r["respuesta"]
    assert turnos.desactivados() is None


def test_canal_desconocido():
    r = E.ejecutar({"accion": "turnos", "activar": False}, "whatsapp")
    assert r["estado"] == "NO_PERMITIDA" and "canal desconocido" in r["respuesta"]


def test_lista_blanca_sigue_mandando():
    assert E.ejecutar({"accion": "borrar", "tarea": "T001"}, "web")["estado"] == "NO_SOPORTADA"


def test_fallo_de_la_politica_es_cerrado(monkeypatch):
    def roto(canal, cap):
        raise RuntimeError("politica rota")
    monkeypatch.setattr(PC, "permitido", roto)
    r = E.ejecutar({"accion": "turnos", "activar": False}, "web")
    assert r["estado"] == "NO_PERMITIDA" and turnos.desactivados() is None
