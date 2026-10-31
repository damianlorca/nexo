# -*- coding: utf-8 -*-
"""T1027 (20/10): el implementador no cogia nada porque 9 tareas con tests dados estaban en "necesita a Claude", casi
todas por tests AJENOS que fallaban en cualquier worktree (proceso real, datos privados, tiempos). Ahora la puerta y
el implementador solo cuentan los rojos que NO esten ya en principal: nucleo/linea_base.py pasa esos tests en un
worktree de principal con el mismo sparse-checkout y guarda el resultado por commit.

Git REAL en tmp_path (fixture `repo` de test_t669_implementador); la suite, el modelo y el revisor son dobles."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nucleo import implementador as I, linea_base as L, puerta as P
from nucleo import tareas as T
from tests.test_t669_implementador import FIRMA, aider_que_escribe, git, nueva, repo  # noqa: F401

_MEDIR = L._medir          # el de verdad (conftest lo cambia por uno que revienta en cada test)
VIEJO = "tests/test_viejo.py::test_a"
ROJO_VIEJO = f"=== short test summary info ===\nFAILED {VIEJO} - AssertionError\n1 failed, 9 passed in 1.0s"


# ------------------------------------------------------------------ leer los rojos
def test_rojos_lee_failed_y_error_y_desconfia_si_no_cuadra():
    salida = ("tests/test_x.py::test_b\n  <unknown>:2: DeprecationWarning\n=== short test summary info ===\n"
              "FAILED tests/test_x.py::test_b[a-1] - AssertionError: no\nERROR tests/test_y.py - SyntaxError\n"
              "1 failed, 2000 passed, 1 error in 300.0s")
    assert L.rojos(salida) == ["tests/test_x.py::test_b[a-1]", "tests/test_y.py"]
    assert L.rojos("FAILED tests/test_x.py::test_b - x\n3 failed, 1 passed") is None     # salida cortada
    assert L.rojos("la suite tardo mas de 1200 s") is None
    assert L.rojos("1 failed: test_x") is None                                          # sin resumen de pytest


# ------------------------------------------------------------------ filtrar
def test_filtrar_verde_si_todos_los_rojos_ya_estaban_y_rojo_si_hay_uno_nuevo(monkeypatch):
    monkeypatch.setattr(L, "ya_en_principal", lambda ids, commit=None: {VIEJO})
    assert L.filtrar(True, "todo verde") == (True, "todo verde", [])
    assert L.filtrar(False, ROJO_VIEJO) == (True, ROJO_VIEJO, [VIEJO])
    dos = f"FAILED {VIEJO} - x\nFAILED tests/test_nuevo.py::test_b - x\n2 failed"
    ok, _, previos = L.filtrar(False, dos)
    assert ok is False and previos == [VIEJO]
    assert L.filtrar(False, "la suite tardo mas de 1200 s")[0] is False             # no se sabe: cuenta


def test_sin_linea_base_el_rojo_cuenta():
    ok, salida, previos = L.filtrar(False, ROJO_VIEJO)      # conftest: _medir revienta (como sin git o sin disco)
    assert ok is False and previos == [] and "linea base no disponible" in salida


# ------------------------------------------------------------------ medir en un worktree de principal
def test_mide_en_un_worktree_de_principal_solo_los_que_existen_y_guarda_por_commit(repo, monkeypatch):
    monkeypatch.setattr(L, "_medir", _MEDIR)
    (repo / "tests" / "test_viejo.py").write_text("def test_a():\n    assert False\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, *FIRMA, "commit", "-qm", "test roto en principal")
    commit = git(repo, "rev-parse", "principal").strip()
    pasadas = []

    def suite(cwd, archivos=None):
        pasadas.append((Path(cwd), list(archivos or [])))
        return False, ROJO_VIEJO
    monkeypatch.setattr(I, "_suite", suite)
    nuevo = "tests/test_de_la_tarea.py::test_b"                 # no existe en principal: es de la tarea
    assert L.ya_en_principal([VIEJO, nuevo]) == {VIEJO}
    wt = L.worktree()
    assert pasadas == [(wt, [VIEJO])]                          # solo lo que existe alli
    assert git(wt, "rev-parse", "HEAD").strip() == commit and not (wt / "memoria" / "becas.md").exists()  # sparse
    cache = json.loads((I.INFORMES / L.CACHE_NOMBRE).read_text(encoding="utf-8"))
    assert cache[commit][VIEJO] is True and cache[commit][nuevo] is False
    assert L.ya_en_principal([VIEJO]) == {VIEJO} and len(pasadas) == 1        # mismo commit: de la cache
    git(repo, *FIRMA, "commit", "-q", "--allow-empty", "-m", "otro commit")
    assert L.ya_en_principal([VIEJO]) == {VIEJO} and len(pasadas) == 2        # commit nuevo: se vuelve a medir


def test_un_test_que_en_principal_pasa_no_es_viejo(repo, monkeypatch):
    monkeypatch.setattr(L, "_medir", _MEDIR)
    (repo / "tests" / "test_viejo.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, *FIRMA, "commit", "-qm", "test sano")
    monkeypatch.setattr(I, "_suite", lambda cwd, archivos=None: (True, "1 passed"))
    assert L.ya_en_principal([VIEJO]) == set()


# ------------------------------------------------------------------ la puerta y el implementador
def _sin_piloto(monkeypatch):
    monkeypatch.setattr(I, "en_piloto", lambda: False)


def _suite_con_rojo_viejo(monkeypatch):
    monkeypatch.setattr(I, "_suite", lambda cwd, archivos=None: (False, ROJO_VIEJO))


def test_la_puerta_fusiona_si_los_rojos_ya_estaban_en_principal(repo, monkeypatch):
    _sin_piloto(monkeypatch)
    _suite_con_rojo_viejo(monkeypatch)
    monkeypatch.setattr(L, "_medir", lambda ids, commit: {i: i == VIEJO for i in ids})
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}))
    assert r["estado"] == "listo" and r["fallos_previos"] == [VIEJO]          # el implementador tampoco cae
    g = P.pasar(t["id"], r)
    assert g["estado"] == "fusionada", g                                       # ni la puerta ni la salud tras fusionar
    assert g["fallos_previos"] == [VIEJO] and "ya estaban" in g["motivo"]
    assert any("ya fallaban en principal" in n["texto"] for n in T.buscar(t["id"])["notas"])


def test_la_puerta_rechaza_un_rojo_nuevo(repo, monkeypatch):
    _sin_piloto(monkeypatch)
    monkeypatch.setattr(L, "_medir", lambda ids, commit: {i: False for i in ids})
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}))
    _suite_con_rojo_viejo(monkeypatch)            # ahora el rojo es de la rama: en principal ese test pasa
    g = P.pasar(t["id"], r)
    assert g["estado"] == "rechazada" and VIEJO in g["motivo"]


def test_tras_fusionar_un_rojo_nuevo_en_principal_se_deshace(repo, monkeypatch):
    _sin_piloto(monkeypatch)
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}))
    vistos = []

    def suite(cwd, archivos=None):
        vistos.append(Path(cwd))
        return (True, "verde") if Path(cwd) != I.REPO else (False, ROJO_VIEJO)
    monkeypatch.setattr(I, "_suite", suite)
    monkeypatch.setattr(L, "_medir", lambda ids, commit: {i: False for i in ids})     # antes de fusionar pasaba
    assert P.pasar(t["id"], r)["estado"] == "revertida"


# ------------------------------------------------------------------ reintentos
def test_el_reintento_empieza_por_un_modelo_que_no_fallo_esta_tarea(monkeypatch):
    ids = [m.id for m in I.modelos_programar()]
    monkeypatch.setattr(I, "cargar_informe", lambda tid: {"intentos": [{"modelo": ids[0], "ok": False},
                                                                        {"modelo": ids[1], "ok": False}]})
    assert [m.id for m in I._modelos_para("T1")] == ids[2:] + ids[:2]


@pytest.mark.parametrize("codigo", [503, 500, 502, 504])
def test_un_5xx_del_proveedor_no_gasta_intento(tmp_path, monkeypatch, codigo):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(I, "_clave", lambda m: "k")
    monkeypatch.setattr(I, "INFORMES", tmp_path / "inf")
    r = I.ejecutar_directo(tmp_path, I.MODELOS[0], ["a.py"], "haz algo",
                           llamar=lambda p, m, t: {"texto": "", "error": f"HTTP {codigo} high demand", "codigo": codigo})
    assert r["ok"] is False and r["no_disponible"] is True


def test_el_prompt_exige_ayuda_en_todo_main():
    assert "ayuda.atender(__doc__)" in I._mensaje({"id": "T1", "titulo": "x"}, "codigo")


def test_los_tests_dados_de_puzzles_dicen_el_contrato_de_ayuda():
    for ruta in sorted((I.REPO / I.CARPETA_TESTS_DADOS).glob("test_puzzles_*.py")):
        doc = ruta.read_text(encoding="utf-8").split('"""')[1]
        assert "ayuda.atender(__doc__)" in doc and "test_ayuda_entradas" in doc, ruta.name
