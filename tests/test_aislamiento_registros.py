# -*- coding: utf-8 -*-
"""Incidente 27/09: la suite escribia en registros/ reales. El conftest de la raiz lo impide."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import conftest as raiz
from nucleo import registro, uso_proveedores

REALES = Path(raiz.REGISTROS_REALES)


def test_traza_y_evidencia_van_a_tmp(tmp_path):
    registro.traza("respuesta_movil", id="P2", respuesta="Si")
    linea = json.loads((tmp_path / "registros" / "trazas.jsonl").read_text(encoding="utf-8"))
    assert linea["id"] == "P2"
    for ruta in (registro.CARPETA, registro.EVIDENCIA, registro.CANDADO_EVIDENCIA, uso_proveedores.REGISTRO):
        assert REALES not in Path(ruta).parents and Path(ruta) != REALES


def test_turno_nexo_guarda_su_registro_en_tmp(tmp_path):
    import turno_nexo
    assert turno_nexo.REGISTROS == tmp_path / "registros"


def test_guardian_bloquea_y_apunta_escrituras_en_registros_reales():
    antes = len(raiz.ESCRITURAS_PROHIBIDAS)
    try:
        with pytest.raises(PermissionError):
            (REALES / "trazas.jsonl").open("a", encoding="utf-8")
        with pytest.raises(PermissionError):
            (REALES / "nuevo").mkdir(exist_ok=True)
        assert len(raiz.ESCRITURAS_PROHIBIDAS) == antes + 2
    finally:
        del raiz.ESCRITURAS_PROHIBIDAS[antes:]  # provocadas aqui a proposito: no deben tumbar la sesion


def test_guardian_deja_leer_registros_reales():
    raiz._guardian("open", (str(REALES / "trazas.jsonl"), "r", 0))


def test_guardian_cubre_auditoria_y_avisos_reales():
    """Incidente 28/09: auditoria y aviso de "T001 Investigar la libreria X" en memoria/ real."""
    antes = len(raiz.ESCRITURAS_PROHIBIDAS)
    try:
        for sub in ("auditoria", "avisos"):
            with pytest.raises(PermissionError):
                (raiz.RAIZ / "memoria" / sub / "x.json").open("w", encoding="utf-8")
        assert len(raiz.ESCRITURAS_PROHIBIDAS) == antes + 2
    finally:
        del raiz.ESCRITURAS_PROHIBIDAS[antes:]


def test_auditor_y_avisos_van_a_tmp(tmp_path):
    from nucleo import auditor, avisos
    for carpeta in (auditor.CARPETA, avisos.CARPETA):
        assert tmp_path in Path(carpeta).parents
