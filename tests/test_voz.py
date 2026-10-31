# -*- coding: utf-8 -*-
"""extremidades/voz.py: Piper sin Piper.

prueba_voz.py necesita piper.exe (en Linux: FileNotFoundError). Aqui piper y la voz son
archivos vacios en tmp_path y subprocess.run se sustituye: se prueba que se le pasa bien el
texto, las rutas y los errores. La voz real solo se puede oir en el PC.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from extremidades import voz


@pytest.fixture
def piper(tmp_path, monkeypatch):
    exe = tmp_path / "piper" / "piper.exe"
    onnx = tmp_path / "piper" / "voz.onnx"
    exe.parent.mkdir()
    rutas = {"voz.piper": str(exe), "voz.modelo": str(onnx)}
    monkeypatch.setattr(voz, "valor", lambda clave, defecto=None: rutas.get(clave, defecto))
    monkeypatch.setattr(voz, "salidas", lambda: tmp_path / "salidas")
    llamadas = []

    def run(args, **kw):
        llamadas.append((args, kw))
        return SimpleNamespace(returncode=estado["rc"], stderr=estado["err"])

    estado = {"rc": 0, "err": b"", "llamadas": llamadas, "exe": exe, "onnx": onnx}
    monkeypatch.setattr(voz.subprocess, "run", run)
    return estado


def test_no_disponible_sin_piper(piper):
    assert voz.disponible() is False
    with pytest.raises(FileNotFoundError, match="Piper no esta"):
        voz.narrar("hola")
    assert piper["llamadas"] == []


def test_sin_modelo_de_voz_avisa(piper):
    piper["exe"].write_bytes(b"")
    assert voz.disponible() is True
    with pytest.raises(FileNotFoundError, match="Falta la voz"):
        voz.narrar("hola")


def test_narrar_pasa_el_texto_por_stdin_en_utf8(piper, tmp_path):
    piper["exe"].write_bytes(b"")
    piper["onnx"].write_bytes(b"")
    destino = tmp_path / "out" / "a.wav"
    assert voz.narrar("¿Qué tal, Damián?", destino) == destino
    args, kw = piper["llamadas"][0]
    assert args == [str(piper["exe"]), "--model", str(piper["onnx"]), "--output_file", str(destino)]
    assert kw["input"] == "¿Qué tal, Damián?".encode("utf-8")
    assert kw["timeout"] == 180 and destino.parent.is_dir()


def test_sin_destino_va_a_salidas(piper, tmp_path):
    piper["exe"].write_bytes(b"")
    piper["onnx"].write_bytes(b"")
    ruta = voz.narrar("hola")
    assert ruta.parent == tmp_path / "salidas" and ruta.name.startswith("voz_") and ruta.suffix == ".wav"


def test_error_de_piper_se_cuenta(piper):
    piper["exe"].write_bytes(b"")
    piper["onnx"].write_bytes(b"")
    piper["rc"], piper["err"] = 1, "modelo corrupto ñ".encode("utf-8")
    with pytest.raises(RuntimeError, match="modelo corrupto ñ"):
        voz.narrar("hola")


def test_rutas_relativas_cuelgan_de_la_raiz(monkeypatch):
    monkeypatch.setattr(voz, "valor", lambda clave, defecto=None: defecto)
    assert voz._ruta("piper", "piper/piper.exe") == voz.RAIZ / "piper" / "piper.exe"
