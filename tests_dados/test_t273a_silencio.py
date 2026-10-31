# -*- coding: utf-8 -*-
"""T273 pieza A: respuesta [SILENT] = nada que contar; el aviso del turno se calla SOLO si todo fue silencio.

Tests dados (los escribe Claude; el implementador SOLO crea nucleo/silencio.py). Funciones PURAS. Contrato:
- `MARCAS = ("[SILENT]", "[SILENCIO]")`.
- `es_silencio(texto) -> bool`: True si el texto, sin espacios ni saltos al principio y en mayusculas, EMPIEZA por
  una de las MARCAS. None o "" -> False. La marca en medio del texto no cuenta.
- `avisar_turno(reg: dict) -> tuple[bool, str]` decide si el turno manda su aviso push. Precedencia (gana la 1a):
    1. reg["abortado"] verdadero                          -> (True, "abortado")
    2. reg["solo_lectura"] existe y su "ok" es falso        -> (True, "solo lectura violada")
    3. algun valor de reg["pasos"] (dicts) tiene clave "error" -> (True, "error")
    4. filas = reg["pasos"]["trabajo"]["filas"] (si falta algo, []); si hay filas y TODAS tienen
       "silencio" == True                                   -> (False, "silencio")
    5. si no                                                 -> (True, "")
  Sin filas no hay silencio (un turno vacio se sigue avisando como hasta ahora). Faltar claves no rompe nada.
"""
from __future__ import annotations

import pytest

from nucleo import silencio as S


@pytest.mark.parametrize("texto,esperado", [
    ("[SILENT]", True), ("  \n[silent] nada nuevo", True), ("[Silencio]", True),
    ("Hoy: [SILENT]", False), ("", False), (None, False), ("SILENT", False),
])
def test_es_silencio(texto, esperado):
    assert S.es_silencio(texto) is esperado


def _reg(filas=None, **extra):
    r = {"pasos": {"trabajo": {"filas": filas if filas is not None else []}}}
    r.update(extra)
    return r


def test_todo_silencio_calla():
    assert S.avisar_turno(_reg([{"silencio": True}, {"silencio": True}])) == (False, "silencio")


def test_una_fila_con_algo_avisa():
    assert S.avisar_turno(_reg([{"silencio": True}, {"archivo": "x.md"}])) == (True, "")


def test_sin_filas_avisa():
    assert S.avisar_turno(_reg([])) == (True, "")
    assert S.avisar_turno({}) == (True, "")


@pytest.mark.parametrize("extra,motivo", [
    ({"abortado": "cuota"}, "abortado"),
    ({"solo_lectura": {"ok": False}}, "solo lectura violada"),
])
def test_lo_grave_avisa_aunque_sea_silencio(extra, motivo):
    assert S.avisar_turno(_reg([{"silencio": True}], **extra)) == (True, motivo)


def test_error_en_un_paso_avisa():
    r = _reg([{"silencio": True}])
    r["pasos"]["cola"] = {"error": "boom"}
    assert S.avisar_turno(r) == (True, "error")


def test_precedencia_abortado_gana():
    r = _reg([{"silencio": True}], abortado="x", solo_lectura={"ok": False})
    r["pasos"]["cola"] = {"error": "boom"}
    assert S.avisar_turno(r) == (True, "abortado")


def test_solo_lectura_ok_no_cuenta():
    assert S.avisar_turno(_reg([{"silencio": True}], solo_lectura={"ok": True})) == (False, "silencio")
