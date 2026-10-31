# -*- coding: utf-8 -*-
"""28/09: `python -m nucleo.revision cola` reventaba en la consola cp1252 de Windows con un titulo con '→'."""
from __future__ import annotations

import io
import sys

from nucleo import consola, revision
from nucleo import tareas as T


def test_la_cola_de_revision_no_revienta_en_una_consola_cp1252(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado")
    monkeypatch.setattr(revision, "BORRADORES", tmp_path / "borradores")
    (tmp_path / "borradores").mkdir()
    (tmp_path / "borradores" / "T001_20260928_1200.md").write_text(
        "## Version final\nx\n### PROPUESTAS IMPLEMENTABLES\n- QUE: Crear Thread → Continue → Outcome de la migración | DONDE: memoria "
        "y cola de tareas | VALOR: 4 | ESFUERZO: 2 | RIESGO: bajo: texto\n", encoding="utf-8")
    T.anadir("Investigar la migración", depende="ia", etiquetas=["cat:investigacion"])
    revision.registrar_borrador("T001", tmp_path / "borradores" / "T001_20260928_1200.md")
    bruto = io.BytesIO()
    consola_win = io.TextIOWrapper(bruto, encoding="cp1252", errors="strict")   # como la consola de Windows
    monkeypatch.setattr(sys, "stdout", consola_win)
    consola.preparar()
    assert revision._cli(["cola"]) == 0
    consola_win.flush()
    texto = bruto.getvalue().decode("cp1252")
    assert "Crear Thread ? Continue ? Outcome de la migración" in texto        # tildes intactas
