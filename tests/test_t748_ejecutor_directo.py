# -*- coding: utf-8 -*-
"""T748: ejecutor directo del implementador (sin Aider): mismo contrato que ejecutar_aider. Sin red."""
from __future__ import annotations

import pytest

from nucleo import implementador as I

M = I.MODELOS[0]


@pytest.fixture
def wt(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "_clave", lambda m: "k")
    d = tmp_path / "T900"
    (d / "nucleo").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "memoria").mkdir()
    (d / "nucleo" / "cola.py").write_bytes(b"def f(x):\r\n    return x\r\n")
    (d / "tests" / "test_cola.py").write_text("def test_f():\n    assert True\n", encoding="utf-8")
    (d / "memoria" / "becas.md").write_text("PRIVADO", encoding="utf-8")
    return d


def _llamar(*respuestas, vistos=None):
    cola = list(respuestas)

    def llamar(prov, modelo, prompt):
        if vistos is not None:
            vistos.append((prov, modelo, prompt))
        r = cola.pop(0)
        return r if isinstance(r, dict) else {"texto": r, "error": "", "codigo": 200, "segundos": 1}
    return llamar


BLOQUE = "ARCHIVO: nucleo/cola.py\n<<<<<<< SEARCH\n    return x\n=======\n    return x + 1\n>>>>>>> REPLACE"


def test_aplica_bloques_respeta_crlf_y_no_envia_privados(wt):
    vistos = []
    r = I.ejecutar_directo(wt, M, ["nucleo/cola.py", "memoria/becas.md"], "haz X",
                           solo_lectura=["tests/test_cola.py"], llamar=_llamar(BLOQUE, vistos=vistos))
    assert r["ok"] and (wt / "nucleo" / "cola.py").read_bytes() == b"def f(x):\r\n    return x + 1\r\n"
    prov, modelo, prompt = vistos[0]
    assert (prov, modelo) == (M.proveedor, M.aider.split("/", 1)[1])
    assert "PRIVADO" not in prompt and "memoria/becas.md" not in prompt
    assert "=== tests/test_cola.py (SOLO LECTURA) ===" in prompt and "haz X" in prompt


def test_sin_marca_de_archivo_vale_si_solo_hay_uno(wt):
    r = I.ejecutar_directo(wt, M, ["nucleo/cola.py"], "x", llamar=_llamar(BLOQUE.split("\n", 1)[1]))
    assert r["ok"]


def test_bloque_que_no_cuadra_da_una_vuelta_mas_con_el_error(wt):
    malo = "ARCHIVO: nucleo/cola.py\n<<<<<<< SEARCH\nno existe\n=======\nx\n>>>>>>> REPLACE"
    vistos = []
    r = I.ejecutar_directo(wt, M, ["nucleo/cola.py"], "x", llamar=_llamar(malo, BLOQUE, vistos=vistos))
    assert r["ok"] and "no se pudo aplicar" in vistos[1][2]
    r = I.ejecutar_directo(wt, M, ["nucleo/cola.py"], "x", llamar=_llamar(malo, malo))
    assert not r["ok"] and "no se pudo aplicar" in r["salida"]


def test_no_toca_archivos_que_no_se_le_dieron(wt):
    otro = BLOQUE.replace("nucleo/cola.py", "tests/test_cola.py")
    r = I.ejecutar_directo(wt, M, ["nucleo/cola.py"], "x", solo_lectura=["tests/test_cola.py"],
                           llamar=_llamar(otro, otro))
    assert not r["ok"] and "assert True" in (wt / "tests" / "test_cola.py").read_text(encoding="utf-8")


def test_archivo_nuevo_con_search_vacio(wt):
    nuevo = "ARCHIVO: tests/test_nuevo.py\n<<<<<<< SEARCH\n=======\ndef test_n():\n    pass\n>>>>>>> REPLACE"
    r = I.ejecutar_directo(wt, M, ["tests/test_nuevo.py"], "x", llamar=_llamar(nuevo))
    assert r["ok"] and "def test_n" in (wt / "tests" / "test_nuevo.py").read_text(encoding="utf-8")


def test_cuota_o_clave_es_no_disponible_y_no_gasta_intento(wt, monkeypatch):
    r = I.ejecutar_directo(wt, M, ["nucleo/cola.py"], "x",
                           llamar=_llamar({"texto": "", "error": "HTTP 429", "codigo": 429, "segundos": 0}))
    assert not r["ok"] and r["no_disponible"]
    monkeypatch.setattr(I, "_clave", lambda m: "")
    assert I.ejecutar_directo(wt, M, ["nucleo/cola.py"], "x", llamar=_llamar())["no_disponible"]


def test_implementar_usa_el_directo_por_defecto():
    assert I.EJECUTOR == "directo"
    import inspect
    assert "ejecutar_directo if EJECUTOR" in inspect.getsource(I.implementar)
