# -*- coding: utf-8 -*-
"""T842 y T843: documentacion/propuestas/aplicar_n01.py (aplicar parches subidos en LF sobre archivos CRLF).

Se prueba contra un repo git de verdad en tmp_path: nada de dobles de git.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parent.parent / "documentacion" / "propuestas" / "aplicar_n01.py"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("aplicar_n01_prueba", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "RAIZ", tmp_path)

    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True, check=True).stdout
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("config", "core.autocrlf", "false")
    mod.git_real = git
    return mod, tmp_path, git


def _parche(tmp_path, git, nombre, contenido_ant, contenido_nuevo, crlf):
    f = tmp_path / nombre
    f.write_bytes(contenido_ant.replace("\n", "\r\n" if crlf else "\n").encode())
    git("add", nombre)
    git("commit", "-qm", "base")
    f.write_bytes(contenido_nuevo.encode())               # el parche se genera en LF, como lo guarda GitHub
    diff = git("diff", "--", nombre)
    git("checkout", "--", nombre)
    f.write_bytes(contenido_ant.replace("\n", "\r\n" if crlf else "\n").encode())
    p = tmp_path / "x.patch"
    p.write_text(diff, encoding="utf-8", newline="\n")
    return p


def test_parche_en_lf_sobre_archivo_crlf_se_aplica_y_vuelve_a_crlf(repo, capsys):
    mod, raiz, git = repo
    p = _parche(raiz, git, "a.txt", "uno\ndos\ntres\n", "uno\nDOS\ntres\n", crlf=True)
    mod.aplicar(str(p))
    assert (raiz / "a.txt").read_bytes() == b"uno\r\nDOS\r\ntres\r\n"
    assert "1 archivos devueltos a CRLF" in capsys.readouterr().out


def test_t843_si_no_hay_archivos_crlf_no_se_afloja_el_espacio(repo):
    """El parche no encaja por otra razon (el archivo cambio): ni se prueba --ignore-whitespace."""
    mod, raiz, git = repo
    p = _parche(raiz, git, "b.txt", "uno\ndos\ntres\n", "uno\nDOS\ntres\n", crlf=False)
    (raiz / "b.txt").write_bytes(b"uno\nOTRA COSA\ntres\n")
    with pytest.raises(SystemExit) as e:
        mod.aplicar(str(p))
    assert "no es el problema previsto" in str(e.value)
    assert (raiz / "b.txt").read_bytes() == b"uno\nOTRA COSA\ntres\n"


def test_t842_si_el_archivo_ya_no_existe_tras_aplicar_no_se_lee(repo, capsys, monkeypatch):
    """El archivo CRLF desaparece entre aplicar y devolverlo a CRLF: antes era un FileNotFoundError."""
    mod, raiz, git = repo
    p = _parche(raiz, git, "c.txt", "uno\ndos\n", "uno\nDOS\n", crlf=True)
    real = mod.git

    def git_y_borra(*a):
        r = real(*a)
        if a[:2] == ("apply", "--ignore-whitespace"):
            (raiz / "c.txt").unlink()
        return r
    monkeypatch.setattr(mod, "git", git_y_borra)
    mod.aplicar(str(p))
    assert "0 archivos devueltos a CRLF" in capsys.readouterr().out
