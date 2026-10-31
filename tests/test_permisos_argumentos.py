# -*- coding: utf-8 -*-
"""T024 / L6 (encargo nube N05): el filtro mira el texto de los argumentos.

nucleo/permisos.py::nivel_de_comando() busca sus patrones en la linea
ENTERA, argumentos y comillas incluidos, asi que ordenes inofensivas salen
ambar o rojo por una palabra que solo es texto (git commit -m "instale
winget").

- FALSOS_POSITIVOS: arreglados por la propuesta N05 (lista blanca de
  ordenes con argumentos inertes).
- NO_REGRESION: pasan hoy y tienen que seguir pasando con cualquier arreglo.
  Es lo que "afinar" no puede dejar escapar.
- SECRETOS: K1 por la shell: mencionar secretos.toml es ROJO.
"""
from __future__ import annotations

import pytest

from nucleo.permisos import Nivel, nivel_de_comando

V, A, R = Nivel.VERDE, Nivel.AMBAR, Nivel.ROJO

FALSOS_POSITIVOS = [
    'git commit -m "instale winget"',
    'git commit -m "quitar rm -rf del script"',
    "Get-Command winget",
    'Write-Output "pip install requests"',
    'Select-String -Pattern "Remove-Item" -Path *.ps1',
    'rg "rm -rf" .',
    "Get-Help Remove-Item",
    'git log --grep "git push"',
    'echo "schtasks"',
    'Select-String -Pattern "schtasks" -Path *.py | Select-String -Pattern "git push"',
]


@pytest.mark.parametrize("comando", FALSOS_POSITIVOS)
def test_falso_positivo_sale_verde(comando):
    assert nivel_de_comando(comando) is V


# (comando, nivel exacto). Salian asi antes de N05 y deben seguir igual.
NO_REGRESION = [
    # Ordenes normales de trabajo: verde.
    ("git status", V),
    ("git diff nucleo/tareas.py", V),
    ("Get-Date -Format yyyy-MM-dd", V),
    ("Get-Content registros\\bot.log -Tail 20", V),
    ('.venv\\Scripts\\python.exe -m nucleo.tareas siguiente', V),
    ("Get-Process -Id 1234 -ErrorAction SilentlyContinue", V),
    ('Write-Output "el log del bot"', V),

    # Lo que ya se paraba se sigue parando.
    ("format c:", R),
    ("diskpart", R),
    ("shutdown /s /t 0", R),
    ("Remove-Item archivo.txt", R),
    ("del archivo.txt", R),
    ("rm -rf carpeta", R),
    ("rd /s /q carpeta", R),
    ("pip install requests", A),
    ("npm install paquete", A),
    ("winget install algo", A),
    ("git push origin principal", A),
    ("Invoke-WebRequest https://ejemplo.invalid/a.zip -OutFile a.zip", A),
    ("curl https://ejemplo.invalid", A),
    ("schtasks /create /tn x /tr y", A),
    ("setx VAR valor", A),

    # Una orden inerte encadenada con una que no lo es: manda la linea
    # entera, como hoy.
    ("Get-ChildItem *.tmp | Remove-Item", R),
    ('echo "hola"; winget install algo', A),
    ('Write-Output "x" | Remove-Item', R),

    # Texto que otra orden reinterpreta como codigo: se sigue mirando
    # la linea entera (aunque la orden de fuera parezca inofensiva).
    ('Invoke-Expression "Remove-Item x"', R),
    ('"Remove-Item x" | iex', R),
    ('echo "Remove-Item x" | iex', R),
    ('powershell -Command "Remove-Item x"', R),

    # Bloques, subexpresiones y escapes: la linea no es simple y se mira
    # entera aunque empiece por una orden inerte.
    ('echo "$(Remove-Item x)"', R),
    ("echo (Remove-Item x)", R),
    ('Select-String -Pattern x -Path *.py | ForEach-Object { Remove-Item $_.Path }', R),
    ('echo "winget" > salida.txt; winget install algo', A),

    # git: solo relaja subordenes de solo lectura/registro, nunca push.
    ('git push -m "log"', A),
    ('git commit -m "x"; git push', A),

    # rg --pre ejecuta un programa: no es inerte.
    ('rg --pre "Remove-Item" x .', R),

    # Comillas sin cerrar: ante la duda, linea entera.
    ('echo "pip install requests', A),
]


@pytest.mark.parametrize("comando,esperado", NO_REGRESION)
def test_no_regresion(comando, esperado):
    assert nivel_de_comando(comando) is esperado


SECRETOS = [
    "Get-Content secretos.toml",
    "type secretos.toml",
    'git commit -m "no subir secretos.toml"',
]


@pytest.mark.parametrize("comando", SECRETOS)
def test_secretos_por_shell_es_rojo(comando):
    assert nivel_de_comando(comando) is R


def test_ejemplo_no_es_secreto():
    """secretos.ejemplo.toml es plantilla publica: no debe salir rojo."""
    assert nivel_de_comando("Get-Content secretos.ejemplo.toml") is V


# 27/09 (revision de Damian del diff de N05): secretos con comodines es rojo.
SECRETOS_COMODIN = [
    "Get-Content secretos*",
    "Select-String -Path secretos.* -Pattern clave",
    "type secretos.t?ml",
    "Get-Content secretos.[t]oml",
    "echo secretos*",
]


@pytest.mark.parametrize("comando", SECRETOS_COMODIN)
def test_secretos_con_comodin_es_rojo(comando):
    assert nivel_de_comando(comando) is R


@pytest.mark.parametrize("comando", ["echo secretos_de_familia", "Get-Content secretos.ejemplo.toml"])
def test_secretos_sin_comodin_ni_toml_no_es_rojo(comando):
    assert nivel_de_comando(comando) is not R


# git --output=<archivo> escribe donde le digan: nunca verde (antes de N05 ya lo era).
GIT_OUTPUT = [
    "git diff --output=nucleo/permisos.py",
    "git log --output x.txt",
    "git show HEAD --output=manos/shell.py",
    'git diff --output="a b.txt"',
    "git status; git diff --output=x",
]


@pytest.mark.parametrize("comando", GIT_OUTPUT)
def test_git_output_no_es_verde(comando):
    assert nivel_de_comando(comando) is not V


def test_git_diff_normal_sigue_verde():
    assert nivel_de_comando("git diff --stat") is V
