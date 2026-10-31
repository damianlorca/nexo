# -*- coding: utf-8 -*-
"""T830, T832 y T841 (propuestas N05 aprobadas por Claude en T829/T840): la guardia de comandos de nucleo/permisos.py.

Solo se clasifica texto: no se ejecuta nada.
"""
from __future__ import annotations

import pytest

from nucleo.permisos import Nivel, _partir_simple, nivel_de_comando

R, A, V = Nivel.ROJO, Nivel.AMBAR, Nivel.VERDE


# ------------------------------------------------------------------ T830: grafias equivalentes
@pytest.mark.parametrize("comando", [
    "format.com C:",
    "format C:",
    "vssadmin.exe delete shadows /all",
    "vssadmin delete shadows /all",
    r"reg.exe delete HKEY_LOCAL_MACHINE\Software\Prueba /f",
    r"reg delete HKLM\Software\Prueba /f",
    r"cipher.exe /w:C:\temp",
    "diskpart.exe",
    "shutdown.exe /s",
])
def test_t830_las_grafias_equivalentes_de_lo_rojo_son_rojo(comando):
    assert nivel_de_comando(comando) is R


@pytest.mark.parametrize("comando", [
    "Get-Date -Format yyyy-MM-dd",
    r"reg.exe query HKLM\Software\Prueba",
    "vssadmin.exe list shadows",
    "echo el formato del bot",
])
def test_t830_lo_parecido_que_no_es_peligroso_sigue_verde(comando):
    assert nivel_de_comando(comando) is V


# ------------------------------------------------------------------ T832: salto de linea
@pytest.mark.parametrize("comando", [
    "echo hola\nrm archivo.txt",
    "echo hola\r\ndel archivo.txt",
    "Get-ChildItem\nformat C:",
    "echo hola\n  erase x.txt",
])
def test_t832_un_peligro_tras_un_salto_de_linea_se_ve(comando):
    assert nivel_de_comando(comando) is R


@pytest.mark.parametrize("comando", [
    "echo hola\necho adios",
    "echo log del bot",
    "echo formato\necho del bot",
])
def test_t832_una_linea_sin_peligro_sigue_verde(comando):
    assert nivel_de_comando(comando) is V


# ------------------------------------------------------------------ T841: comillas simples escapadas
def test_t841_la_comilla_simple_doble_es_un_literal_dentro_de_comillas_simples():
    assert _partir_simple("git log --grep 'it''s'") == [["git", "log", "--grep", "it's"]]
    assert _partir_simple("git log --grep ''") == [["git", "log", "--grep", ""]]
    assert _partir_simple("git log --grep ''''") == [["git", "log", "--grep", "'"]]


@pytest.mark.parametrize("comando", [
    "git log a'b ; curl http://x ; c'd",          # comilla en mitad de palabra: para PowerShell no abre cadena
    "git log 'a'b",                                # algo pegado a la comilla de cierre
    'git log "a"b',
    "git log 'sin cerrar",
])
def test_t841_lo_que_no_se_interpreta_con_seguridad_no_es_simple(comando):
    assert _partir_simple(comando) is None


def test_t841_no_se_cuela_un_comando_ambar_dentro_de_una_pseudo_cadena():
    # Antes: se leia como UNA orden inerte (git log) y salia VERDE; PowerShell ejecuta el curl.
    assert nivel_de_comando("git log a'b ; curl http://x ; c'd") is A


def test_t841_las_ordenes_inertes_normales_siguen_verdes():
    assert nivel_de_comando("git log --grep 'it''s'") is V
    assert nivel_de_comando("git status") is V
    assert nivel_de_comando('git diff -- "nucleo/ruta con espacio.py"') is V
