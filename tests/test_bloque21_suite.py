# -*- coding: utf-8 -*-
"""Bloque 21 (25/10): la suite ya no cabia en los tiempos del implementador.

- Una sola suite de NEXO a la vez (nucleo/cerrojo_suite.py): el implementador, la puerta y la linea base esperan a
  la que este en marcha y, si no se libera, lo dejan para la siguiente tanda SIN gastar intento.
- Una suite sin resultado (cerrojo ocupado o pasada de tiempo) es implementador.FalloInfra: nunca un rojo. En la
  salud tras fusionar se repite una vez y solo se deshace la fusion con un rojo de verdad.
- Pasada de tiempo, se cierra con TODO su arbol por PID exacto (el python del .venv es un lanzador: matar solo a el
  dejaba el pytest real suelto, pisando a la siguiente suite).
- El timeout sale de la ultima duracion medida x2 (minimo TIMEOUT_SUITE).
- La tanda solo pasa la puerta (2 suites) tras implementar si cabe en la ventana del turno; si no, la siguiente.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time

import pytest

from nucleo import cerrojo_suite as C
from nucleo import implementador as I, linea_base as L, piloto_serie as S, puerta as P
from tests.test_t669_implementador import repo  # noqa: F401  (fixture)
from tests.test_t669_permanente import _permanente, aider


@pytest.fixture
def cerrojo(tmp_path, monkeypatch):
    """El cerrojo en tmp_path y sin heredar el de la sesion de pytest (conftest lo pone en el entorno)."""
    monkeypatch.setattr(C, "RUTA", tmp_path / "suite.lock")
    monkeypatch.delenv(C.ENV, raising=False)
    return tmp_path / "suite.lock"


def _ocupar(listo: threading.Event, soltar: threading.Event):
    with C.tomar(5, motivo="otra suite"):
        listo.set()
        soltar.wait(10)


@pytest.fixture
def ocupado(cerrojo):
    """Otro (un hilo: el candado del SO va por descriptor) tiene el cerrojo mientras dura el test."""
    listo, soltar = threading.Event(), threading.Event()
    h = threading.Thread(target=_ocupar, args=(listo, soltar), daemon=True)
    h.start()
    assert listo.wait(5)
    yield
    soltar.set()
    h.join(5)


# ------------------------------------------------------------------ cerrojo
def test_el_cerrojo_es_de_uno_y_dice_quien_lo_tiene(ocupado):
    assert "otra suite" in C.quien()
    with pytest.raises(C.Ocupada):
        with C.tomar(0.3):
            pass


def test_el_hijo_de_quien_tiene_el_cerrojo_no_lo_vuelve_a_pedir(ocupado, monkeypatch):
    monkeypatch.setenv(C.ENV, "123")
    with C.tomar(0.3):          # no espera: lo hereda
        pass


def test_libre_se_toma_y_se_suelta(cerrojo):
    assert C.quien() is None
    with C.tomar(1, motivo="yo"):
        assert "yo" in C.quien()
    assert C.quien() is None


def test_la_sesion_de_pytest_tiene_el_cerrojo_y_lo_pasa_a_sus_hijos():
    assert C.heredado()        # conftest raiz: lo que lance un test no se espera a si mismo


# ------------------------------------------------------------------ _suite
def test_suite_con_otra_en_marcha_es_fallo_de_infraestructura_y_no_lanza_nada(ocupado, monkeypatch, tmp_path):
    monkeypatch.setattr(I, "ESPERA_SUITE", 0.3)
    monkeypatch.setattr(I.subprocess, "Popen", lambda *a, **k: pytest.fail("lanzo pytest con el cerrojo ocupado"))
    with pytest.raises(I.FalloInfra, match="otra suite de NEXO"):
        I._suite(tmp_path)


def test_suite_completa_anota_su_duracion_y_el_timeout_sale_de_ella(cerrojo, monkeypatch, tmp_path):
    monkeypatch.setattr(I, "_correr_pytest", lambda args, cwd, limite: (1, "1 failed"))
    assert I.timeout_suite() == I.TIMEOUT_SUITE                    # sin medida: el minimo
    assert I._suite(tmp_path, ["tests/test_x.py"]) == (False, "1 failed")
    assert I.duracion_suite() is None                              # una parcial no cuenta
    I._suite(tmp_path)
    assert I.duracion_suite() is not None                          # la completa (aunque salga roja) si
    (I.INFORMES / I.DURACION_SUITE).write_text(json.dumps({"segundos": 900}), encoding="utf-8")
    assert I.timeout_suite() == 1800
    (I.INFORMES / I.DURACION_SUITE).write_text(json.dumps({"segundos": 300}), encoding="utf-8")
    assert I.timeout_suite() == I.TIMEOUT_SUITE


def test_suite_lanza_al_hijo_con_el_cerrojo_heredado(cerrojo, monkeypatch, tmp_path):
    visto = {}

    def correr(args, cwd, limite):
        visto["args"], visto["quien"] = args, C.quien()
        return 0, "ok"
    monkeypatch.setattr(I, "_correr_pytest", correr)
    assert I._suite(tmp_path, ["tests/test_x.py"]) == (True, "ok")
    assert "implementador" in visto["quien"] and visto["args"][1:4] == ["-m", "pytest", "tests/test_x.py"]


def test_la_suite_completa_va_en_paralelo_y_la_parcial_no(cerrojo, monkeypatch, tmp_path):
    vistas = []
    monkeypatch.setattr(I, "_correr_pytest", lambda args, cwd, limite: (vistas.append(args), (0, "ok"))[1])
    monkeypatch.setattr(I, "_hay_xdist", lambda: True)
    I._suite(tmp_path)
    I._suite(tmp_path, ["tests/test_x.py"])
    assert vistas[0][-2:] == ["-n", str(I.SUITE_WORKERS)] and "-n" not in vistas[1]
    monkeypatch.setattr(I, "_hay_xdist", lambda: False)        # sin xdist instalado: en serie, como antes
    I._suite(tmp_path)
    assert "-n" not in vistas[2]


def _dormir(segundos):
    return [sys.executable, "-c", f"import time; time.sleep({segundos})"]


def test_pasada_de_tiempo_cierra_el_arbol_entero_por_pid_exacto(monkeypatch, tmp_path):
    from nucleo import planificador as PL
    args = _dormir(30)
    cerrados = []
    monkeypatch.setattr(PL, "_linea_de_comando", lambda pid: subprocess.list2cmdline(args))
    # el interprete real (mismos argumentos, sin la ruta del repo) y lo que cuelga de el son de la suite
    monkeypatch.setattr(PL, "_hijos", lambda pid: [
        {"pid": 9001, "padre": pid, "nombre": "python.exe", "linea": "C:/Python311/python.exe " + subprocess.list2cmdline(args[1:]),
         "reconocido": False},
        {"pid": 9002, "padre": 9001, "nombre": "cmd.exe", "linea": "cmd /c algo", "reconocido": False}])

    def matar(pid):
        cerrados.append(pid)
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True) if sys.platform == "win32" else \
            __import__("os").kill(pid, 9)
    monkeypatch.setattr(PL, "_matar", matar)
    inicio = time.monotonic()
    with pytest.raises(I.FalloInfra, match="tardo mas de 1 s .cerrada con su arbol"):
        I._correr_pytest(args, tmp_path, 1)
    assert len(cerrados) == 1 and time.monotonic() - inicio < 20


def test_con_un_hijo_que_no_reconoce_no_mata_nada(monkeypatch, tmp_path):
    from nucleo import planificador as PL
    args = _dormir(3)
    monkeypatch.setattr(PL, "_linea_de_comando", lambda pid: subprocess.list2cmdline(args))
    monkeypatch.setattr(PL, "_hijos", lambda pid: [
        {"pid": 9003, "padre": 4, "nombre": "notepad.exe", "linea": "notepad", "reconocido": False}])
    monkeypatch.setattr(PL, "_matar", lambda pid: pytest.fail("mato con un hijo que no reconoce"))
    with pytest.raises(I.FalloInfra, match="NO se pudo cerrar .hijo no reconocido: 9003"):
        I._correr_pytest(args, tmp_path, 0.5)


def test_si_el_pid_ya_no_es_la_suite_no_se_toca(monkeypatch, tmp_path):
    from nucleo import planificador as PL
    monkeypatch.setattr(PL, "_linea_de_comando", lambda pid: "otro programa")
    monkeypatch.setattr(PL, "_hijos", lambda pid: [])
    monkeypatch.setattr(PL, "_matar", lambda pid: pytest.fail("mato un PID que ya no es la suite"))
    with pytest.raises(I.FalloInfra, match="ya no es la suite"):
        I._correr_pytest(_dormir(3), tmp_path, 0.5)


def test_la_salida_entera_vuelve_y_el_codigo_manda(tmp_path):
    codigo, salida = I._correr_pytest([sys.executable, "-c", "import sys; print('hola ñ'); sys.exit(3)"], tmp_path, 60)
    assert codigo == 3 and "hola ñ" in salida


# ------------------------------------------------------------------ linea base, implementador y puerta
def test_la_linea_base_no_se_traga_el_fallo_de_infraestructura(monkeypatch):
    def medir(ids, commit):
        raise I.FalloInfra("otra suite de NEXO en marcha")
    monkeypatch.setattr(L, "_medir", medir)
    monkeypatch.setattr(L, "_cargar", lambda: {})
    with pytest.raises(I.FalloInfra):
        L.filtrar(False, "FAILED tests/test_a.py::test_a - x\n1 failed in 1s", commit="abc")


def _suite_sin_resultado(cwd, archivos=None):
    if not archivos:
        raise I.FalloInfra("la suite tardo mas de 1200 s")
    codigo = (cwd / "nucleo" / "cola.py").read_text(encoding="utf-8")
    return all(f"def f_{a.split('test_')[1][0]}" in codigo for a in archivos), "tests dados"


def test_sin_resultado_al_implementar_no_gasta_intento_ni_marca_la_tarea(repo, monkeypatch):
    (a,) = _permanente(repo, monkeypatch, "a")
    monkeypatch.setattr(I, "_suite", _suite_sin_resultado)
    r = S.tanda(ejecutar=aider())
    assert (r["accion"], r["tarea"], r["estado"]) == ("implementar", a, "sin_suite")
    assert a not in (I._cargar_piloto().get("cola") or {}) or not I._cargar_piloto()["cola"][a].get("final")
    assert "necesita:claude" not in (I.T.buscar(a).get("etiquetas") or [])
    assert [t["id"] for t in S.cola()] == [a]                      # vuelve en la siguiente tanda


def test_tras_implementar_la_puerta_solo_si_caben_sus_dos_suites(repo, monkeypatch):
    (a,) = _permanente(repo, monkeypatch, "a")
    monkeypatch.setattr(I, "duracion_suite", lambda: 480.0)
    monkeypatch.setattr(P, "pasar", lambda *a, **k: pytest.fail("la puerta no cabia"))
    r = S.tanda(ejecutar=aider(), limite=time.time() + 600)       # quedan 10 min; la puerta pide 2 x 8 + 3
    assert r["tarea"] == a and r["estado"] == "listo" and "siguiente tanda" in r["motivo"]
    assert S._en_puerta(I._cargar_piloto()) == [a]                # la recoge la siguiente tanda
    assert S.cabe_la_puerta(None) and S.cabe_la_puerta(1000 + 2 * 480 + S.MARGEN_PUERTA, ahora=1000)
    assert not S.cabe_la_puerta(999 + 2 * 480 + S.MARGEN_PUERTA, ahora=1000)


def test_la_puerta_sin_resultado_en_la_rama_espera_a_otra_tanda(repo, monkeypatch):
    (a,) = _permanente(repo, monkeypatch, "a")
    monkeypatch.setattr(I, "duracion_suite", lambda: 480.0)
    S.tanda(ejecutar=aider(), limite=time.time() + 60)            # implementada; la puerta, despues
    monkeypatch.setattr(I, "_suite", _suite_sin_resultado)
    r = S.tanda(ejecutar=aider())
    assert (r["accion"], r["tarea"], r["puerta"]) == ("puerta", a, "espera_suite")
    assert not I._cargar_piloto()["cola"][a].get("final") and S._en_puerta(I._cargar_piloto()) == [a]


def _salud_con(monkeypatch, *resultados):
    vistas = list(resultados)

    def suite(cwd, archivos=None):
        x = vistas.pop(0)
        if isinstance(x, Exception):
            raise x
        return x
    monkeypatch.setattr(I, "_suite", suite)
    monkeypatch.setattr(P, "_salud_web", lambda: (True, "/salud 200"))
    return vistas


def test_salud_sin_resultado_se_repite_una_vez_y_vale_si_sale_verde(monkeypatch):
    quedan = _salud_con(monkeypatch, I.FalloInfra("tardo"), (True, "verde"))
    assert P._salud() == (True, "/salud 200") and quedan == []


def test_salud_sin_resultado_dos_veces_no_deshace_y_avisa(monkeypatch):
    avisos = []
    monkeypatch.setattr(P, "_aviso", lambda *a: avisos.append(a))
    _salud_con(monkeypatch, I.FalloInfra("tardo"), I.FalloInfra("tardo"))
    ok, detalle = P._salud()
    assert ok and "SIN resultado 2 veces" in detalle and avisos


def test_salud_roja_de_verdad_tras_repetir_si_deshace(monkeypatch):
    _salud_con(monkeypatch, I.FalloInfra("tardo"), (False, "FAILED tests/test_a.py::test_a\n1 failed"))
    ok, detalle = P._salud()
    assert not ok and "en rojo" in detalle
