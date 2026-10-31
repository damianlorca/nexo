# -*- coding: utf-8 -*-
"""T1025 (20/10): manos/archivos.leer acepta aprobado=True igual que escribir (T861): salta el AMBAR (leer fuera de las
carpetas de NEXO, como la A0066), NUNCA el ROJO (secretos.toml sigue bloqueado). manos/ es blindado: el cambio esta en
documentacion/diffs/T1025_leer_aprobado.patch y estos tests se saltan solos hasta que Damian lo aplique. No necesitan
mcp (los de servidor_mcp estan en test_enganche_aprobaciones.py)."""
from __future__ import annotations

import pytest

from manos import archivos
from nucleo import permisos
from nucleo.config import RAIZ

pytestmark = pytest.mark.skipif("aprobado" not in archivos.leer.__code__.co_varnames,
                                reason="parche documentacion/diffs/T1025_leer_aprobado.patch no aplicado (blindados)")


@pytest.fixture(autouse=True)
def zona_verde_solo_el_repo(monkeypatch):
    monkeypatch.setattr(permisos, "zonas_verdes", lambda: [RAIZ])   # tmp_path queda fuera: AMBAR


def test_fuera_de_nexo_sin_aprobar_pide_aprobacion(tmp_path):
    fuera = tmp_path / "plantilla.env.example"
    fuera.write_text("A=1", encoding="utf-8")
    with pytest.raises(permisos.NecesitaAprobacion):
        archivos.leer(fuera)


def test_fuera_de_nexo_aprobado_se_lee(tmp_path):
    fuera = tmp_path / "plantilla.env.example"
    fuera.write_text("A=1", encoding="utf-8")
    assert archivos.leer(fuera, aprobado=True) == "A=1"


def test_aprobado_nunca_salta_el_rojo(tmp_path):
    secreto = tmp_path / "secretos.toml"
    secreto.write_text("x = 'falso'", encoding="utf-8")
    assert permisos.nivel_de_ruta(secreto, escritura=False) is permisos.Nivel.ROJO
    with pytest.raises(permisos.Bloqueado):
        archivos.leer(secreto, aprobado=True)


def test_dentro_de_nexo_no_cambia_nada():
    assert "NEXO" in archivos.leer(RAIZ / "CLAUDE.md", aprobado=False)


listar_parcheado = pytest.mark.skipif("aprobado" not in archivos.listar.__code__.co_varnames,
                                      reason="parche documentacion/diffs/T1025_listar_aprobado.patch no aplicado")


@listar_parcheado
def test_listar_fuera_de_nexo_sin_aprobar_pide_y_aprobado_lista(tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    with pytest.raises(permisos.NecesitaAprobacion):
        archivos.listar(str(tmp_path))
    assert archivos.listar(str(tmp_path), aprobado=True) == ["a.txt"]
