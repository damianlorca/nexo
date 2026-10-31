# -*- coding: utf-8 -*-
"""Tapado de datos privados antes de que un texto salga del PC (auditor.tapar). Fallo del 05/10: se aplicaban
primero los patrones de auditor.PRIVADO, que tapan solo 'C:\\Users\\', y el regex de la ruta entera ya no casaba:
salia '[privado]damia\\x.txt' (el nombre de usuario). Lo usan tareas.lista_para_ia_externa (T232),
plantillas_turno._tapar y el brief (T697)."""
from __future__ import annotations

import pytest

from nucleo import auditor, brief, plantillas_turno
from nucleo import tareas as T

RUTAS = ["C:\\Users\\damia\\Desktop\\AI\\agente\\secretos.toml", "c:/users/damia/notas.txt",
         "D:\\USERS\\damia\\cv.pdf"]


@pytest.mark.parametrize("ruta", RUTAS)
def test_tapar_quita_la_ruta_entera(ruta):
    t = auditor.tapar(f"Revisar {ruta} hoy")
    assert t == "Revisar [privado] hoy" and "damia" not in t


def test_tapar_sigue_tapando_lo_demas():
    t = auditor.tapar("correo a ana@ejemplo.com con sk-" + "a" * 30 + " y secretos.toml", "[x]")
    assert "ana@" not in t and "sk-" not in t and "secretos" not in t and t.count("[x]") == 3
    assert auditor.tapar("") == "" and auditor.tapar(None) == ""


def test_lista_para_ia_externa_no_filtra_el_usuario(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado")
    T.anadir("Revisar C:\\Users\\damia\\x.txt", detalle="ver c:/users/damia/y.md")
    lineas = T.lista_para_ia_externa()
    assert len(lineas) == 1 and "damia" not in lineas[0] and lineas[0].count("[privado]") == 2


def test_plantillas_y_brief_usan_el_mismo_tapado():
    assert plantillas_turno._tapar("en C:\\Users\\damia\\a.py") == "en [omitido]"
    assert brief._tapar("en C:\\Users\\damia\\a.py") == "en [privado]"
