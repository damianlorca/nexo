# -*- coding: utf-8 -*-
"""Cierre automatico de lo ya hecho (nucleo/cierre_auto.py, Damian 11/10). Sin git real ni pytest real: dobles."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from nucleo import cierre_auto as C
from nucleo import tareas as T

SEP_C, SEP_F = C.SEP_C, C.SEP_F


@pytest.fixture(autouse=True)
def cola_aislada(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "tareas.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado_tareas.lock")


def _log(*commits):
    return "".join(f"{SEP_C}{sha}{SEP_F}{asunto}\n\n" + "\n".join(archivos) + "\n" for sha, asunto, archivos in commits)


def _git(texto):
    return lambda *a, **k: texto


def test_solo_cuenta_el_id_en_el_asunto_y_no_los_espejos_ni_solo_memoria():
    log = _log(("a1", "T900: arregla el bucle", ["nucleo/x.py", "tests/test_x.py"]),
               ("a2", "Espejo de a1 T900", ["nucleo/x.py"]),
               ("a3", "Tareas: evidencia de T900", ["memoria/tareas.json"]),
               ("a4", "Otra cosa (de paso cita T901 en el asunto)", ["memoria/tareas.json"]),
               ("a5", "Radar nuevo", ["nucleo/r.py"]))
    por = C.commits_por_tarea(git=_git(log))
    assert [c["sha"] for c in por["T900"]] == ["a1"] and "T901" not in por


def _tarea(titulo, **campos):
    return T.anadir(titulo, detalle="QUE: x", **campos)


def _evaluar(t, *commits):
    return C.evaluar(t, [{"sha": s, "asunto": a, "archivos": f} for s, a, f in commits], existe=lambda r: True)


def test_bug_verificado_con_tests_se_cierra_y_lo_demas_va_a_claude():
    bug = _tarea("BUG: el log crece sin tope", etiquetas=["bug"])
    T.verificar(bug["id"], "pytest tests/test_escritura.py: 12 passed (tope probado con un doble)")
    assert _evaluar(T.buscar(bug["id"]), ("c1", f"{bug['id']}: tope", ["tests/test_escritura.py"]))["decision"] == "cerrar"

    sin_verificar = _tarea("BUG: otro", etiquetas=["bug"])
    r = _evaluar(sin_verificar, ("c2", f"{sin_verificar['id']}: arreglo", ["tests/test_y.py"]))
    assert r["decision"] == "dudosa" and "verificacion" in r["motivo"]

    grande = _tarea("F3 Implementador por fases")
    r = _evaluar(grande, ("c3", f"{grande['id']}: fase 1", ["tests/test_z.py"]))
    assert r["decision"] == "dudosa" and "atomica" in r["motivo"]

    sin_tests = _tarea("BUG: sin tests", etiquetas=["bug"])
    assert "tests" in _evaluar(sin_tests, ("c4", f"{sin_tests['id']}: x", ["nucleo/a.py"]))["motivo"]

    parcial = _tarea("BUG: a medias", etiquetas=["bug"])
    T.verificar(parcial["id"], "pytest tests/test_w.py: 3 passed, el resto pendiente")
    r = _evaluar(T.buscar(parcial["id"]), ("c5", f"{parcial['id']} (parcial): primer arreglo", ["tests/test_w.py"]))
    assert r["decision"] == "dudosa" and "parcial" in r["motivo"]


def test_fusion_del_implementador_se_cierra():
    t = _tarea("[Propuesta de T1] Validar claves", etiquetas=["tests:dados"])
    r = _evaluar(t, ("m1", f"Fusiona impl/{t['id']}: [Propuesta de T1] Validar", ["tests/test_t9.py", "a.py"]))
    assert r["decision"] == "cerrar" and "implementador" in r["motivo"]


def test_una_fusion_deshecha_no_cierra_la_tarea():
    """Bloque 21 (26/10): T844 se cerro como HECHO Y TESTEADO con el commit que la DESHIZO como evidencia (la puerta la
    revirtio por la salud y el commit de la fusion original seguia en el historial)."""
    t = _tarea("T746 rehecha", etiquetas=["tests:dados"])
    fusion = f"Fusiona impl/{t['id']}: T746 rehecha: fallback lexico"
    r = _evaluar(t, ("r1", f'Revert "{fusion}"', ["nucleo/freno.py", "tests/test_t746.py"]),
                 ("m1", fusion, ["nucleo/freno.py", "tests/test_t746.py"]))
    assert r["decision"] == "dudosa" and "deshizo" in r["motivo"]
    # fusionada otra vez despues del revert: si cuenta
    r = _evaluar(t, ("m2", fusion, ["nucleo/freno.py", "tests/test_t746.py"]),
                 ("r1", f'Revert "{fusion}"', ["nucleo/freno.py", "tests/test_t746.py"]),
                 ("m1", fusion, ["nucleo/freno.py", "tests/test_t746.py"]))
    assert r["decision"] == "cerrar"


def test_investigacion_y_revision_pendiente_nunca_se_cierran_solas():
    inv = _tarea("Investigar X", etiquetas=["cat:investigacion", "bug"])
    assert "RESULTADO" in _evaluar(inv, ("i1", f"{inv['id']}: x", ["tests/test_x.py"]))["motivo"]
    rev = _tarea("BUG: algo", etiquetas=["bug", "revision_claude:T1_x.md"])
    assert "revision" in _evaluar(rev, ("r1", f"{rev['id']}: x", ["tests/test_x.py"]))["motivo"]


def test_repasar_ejecuta_los_tests_cierra_con_evidencia_y_lista_las_dudosas(tmp_path, monkeypatch):
    bug = _tarea("BUG: tope", etiquetas=["bug"])
    T.verificar(bug["id"], "pytest tests/test_tope.py: 4 passed tras el arreglo")
    rojo = _tarea("BUG: rojo", etiquetas=["bug"])
    T.verificar(rojo["id"], "pytest tests/test_rojo.py: 2 passed tras el arreglo")
    fase = _tarea("Epica por fases")
    por = {bug["id"]: [{"sha": "b1", "asunto": f"{bug['id']}: tope", "archivos": ["tests/test_tope.py"]}],
           rojo["id"]: [{"sha": "r1", "asunto": f"{rojo['id']}: x", "archivos": ["tests/test_rojo.py"]}],
           fase["id"]: [{"sha": "f1", "asunto": f"{fase['id']}: fase 1", "archivos": ["tests/test_f.py"]}]}
    monkeypatch.setattr(C, "REPO", tmp_path)
    for f in ("tests/test_tope.py", "tests/test_rojo.py", "tests/test_f.py"):
        (tmp_path / f).parent.mkdir(exist_ok=True)
        (tmp_path / f).write_text("", encoding="utf-8")
    ejecutados = []

    def ejecutar(tests):
        ejecutados.append(tests)
        return ("rojo" not in tests[0]), ("4 passed in 0.1s" if "rojo" not in tests[0] else "1 failed")
    r = C.repasar(aplicar=True, ejecutar=ejecutar, por_tarea=por)
    assert [c["tid"] for c in r["cerradas"]] == [bug["id"]]
    assert T.buscar(bug["id"])["estado"] == "hecha" and T.estado_real(T.buscar(bug["id"])) == "HECHO Y TESTEADO"
    assert T.buscar(rojo["id"])["estado"] == "pendiente"               # tests en rojo: no se cierra
    dudosas = {c["tid"]: c["motivo"] for c in r["dudosas"]}
    assert "NO pasan" in dudosas[rojo["id"]] and fase["id"] in dudosas
    assert ["tests/test_f.py"] not in ejecutados                       # lo dudoso ni se ejecuta
    assert (C.CARPETA / "dudosas.json").exists()


def test_simular_no_toca_nada():
    bug = _tarea("BUG: tope", etiquetas=["bug"])
    T.verificar(bug["id"], "pytest tests/test_tope.py: 4 passed tras el arreglo")
    por = {bug["id"]: [{"sha": "b1", "asunto": f"{bug['id']}: tope", "archivos": ["tests/test_tope.py"]}]}
    r = C.repasar(aplicar=False, ejecutar=lambda t: pytest.fail("simular no ejecuta tests"), por_tarea=por)
    assert r["cerradas"] == [] and T.buscar(bug["id"])["estado"] == "pendiente"


def test_el_planificador_lo_lanza_una_vez_al_dia():
    lanzados = []
    ahora = datetime(2026, 10, 11, 12, 0)
    assert "lanzado" in C.repaso_si_toca(ahora, lanzar=lambda: lanzados.append(1) or 7)
    assert C.repaso_si_toca(ahora + timedelta(hours=1), lanzar=lambda: lanzados.append(1) or 7) is None
    assert C.repaso_si_toca(ahora + timedelta(hours=25), lanzar=lambda: lanzados.append(1) or 7)
    assert len(lanzados) == 2
