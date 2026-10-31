# -*- coding: utf-8 -*-
"""N01 (H03, H06, H07) sobre N05: el filtro de comandos y archivar() respetan
lo prohibido en CLAUDE.md. Antes eran xfail estrictos en
documentacion/nube/N01_evidencias/test_evidencias_n01.py. Sin procesos reales:
solo se clasifica texto y se llama al freno de archivar(), que no mueve nada."""
from __future__ import annotations

from pathlib import Path

import pytest

from nucleo.permisos import Bloqueado, Nivel, nivel_de_comando, nivel_de_ruta
from nucleo.config import RAIZ

ROJO = [
    "rm archivo.txt",
    r"cmd /c del memoria\tareas.json",
    'cmd.exe /k "del x"',
    "ri memoria",
    "git clean -fdx",
    "git reset --hard",
    "taskkill /IM python.exe /F",
    "Stop-Process -Name python",
    "pkill -f comfy",
    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*ComfyUI*' } | Stop-Process",
    "Get-Content secretos.toml",
]


@pytest.mark.parametrize("comando", ROJO)
def test_rojo(comando):
    assert nivel_de_comando(comando) is Nivel.ROJO


AMBAR = [
    r"Set-Content nucleo\permisos.py x",
    "Copy-Item x manos/shell.py",
    "Set-Content nucleo/guardia_python.py x",
    r"Out-File .claude\settings.json",
    "git -c user.name=x push",
]


@pytest.mark.parametrize("comando", AMBAR)
def test_ambar(comando):
    assert nivel_de_comando(comando) is Nivel.AMBAR


# Sobre N05: las ordenes inertes que solo LEEN un blindado siguen verdes.
@pytest.mark.parametrize("comando", [
    "git diff nucleo/permisos.py",
    r"Select-String -Pattern ROJOS -Path nucleo\permisos.py",
    "Stop-Process -Id 1234",
    # H08 (N02): asi reinicia extremidades/imagen.py el ComfyUI que lanzo, por PID exacto.
    "taskkill /PID 4321 /T /F",
    "(Get-CimInstance Win32_Process -Filter 'ProcessId=4321').CommandLine",
])
def test_leer_un_blindado_o_matar_por_pid_sigue_verde(comando):
    assert nivel_de_comando(comando) is Nivel.VERDE


@pytest.mark.parametrize("ruta", ["nucleo/guardia_python.py", ".claude/settings.json", "manos/__init__.py"])
def test_h06_blindados_nuevos_no_son_verdes(ruta):
    assert nivel_de_ruta(RAIZ / ruta) is not Nivel.VERDE


@pytest.mark.parametrize("carpeta", ["nucleo", "manos"])
def test_h07_archivar_carpeta_con_blindados_esta_bloqueado(carpeta):
    from manos.archivos import _comprobar_archivable
    with pytest.raises(Bloqueado):
        _comprobar_archivable(RAIZ / carpeta, RAIZ / "_archivo" / "20260927")
