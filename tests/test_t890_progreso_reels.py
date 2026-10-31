# -*- coding: utf-8 -*-
"""T890 (4): el turno 'reels' avanza POR REEL (el lote corre en un subproceso: antes, 30 min sin progreso() = falso
'turno colgado' aunque terminase 30/30)."""
from __future__ import annotations

import os
import threading

from extremidades import reels
from nucleo import planificador as P


def test_vigilar_progreso_avisa_cada_vez_que_termina_un_reel_y_no_antes():
    marcas = iter([(0, 0), (0, 0), (1, 0), (1, 0), (2, 1)])
    avisos_ = []
    parar = threading.Event()

    def marca(_ruta):
        try:
            return next(marcas)
        except StopIteration:
            parar.set()
            return (2, 1)
    reels.vigilar_progreso_lote(parar, avisar=avisos_.append, cada=0.001, marca=marca)
    assert avisos_ == [(0, 0), (1, 0), (2, 1)]            # solo cuando cambia: un aviso por reel terminado


def test_marca_lote_cuenta_hechos_y_fallos(tmp_path):
    ruta = tmp_path / "lote.json"
    ruta.write_text('{"hechos": {"a": {}, "b": {}}, "fallos": {"c": {"n": 2}, "d": {"n": 1}}}', encoding="utf-8")
    assert reels._marca_lote(ruta) == (2, 3)
    assert reels._marca_lote(tmp_path / "no_existe.json") == (0, 0)


def test_progreso_si_turno_solo_si_este_proceso_es_el_turno(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "EN_MARCHA", tmp_path / "turno_en_marcha.json")
    assert P.progreso_si_turno(paso="reels") is False and not P.EN_MARCHA.exists()   # suelto: no finge un turno
    P.progreso(pid_turno=os.getpid() + 1, turno="t1")
    assert P.progreso_si_turno(paso="reels") is False                                # otro proceso es el turno
    P.progreso(pid_turno=os.getpid(), turno="t1", actualizado=1.0)
    assert P.progreso_si_turno(paso="reels", tarea="reels: 3 hechos") is True
    d = P._leer(P.EN_MARCHA, {})
    assert d["paso"] == "reels" and d["tarea"] == "reels: 3 hechos" and d["actualizado"] > 1.0


def test_el_turno_de_reels_vigila_el_progreso_mientras_corre_el_lote_y_lo_para_al_acabar(monkeypatch):
    monkeypatch.setattr(reels, "cola_lote", lambda **k: ["x"])
    monkeypatch.setattr(reels, "_leer_estado_lote", lambda ruta: {})
    # T1027: sin rehacer_todas=False, turno() leia la coleccion PRIVADA real (memoria/perfil_privado/reels), que el
    # worktree del implementador no tiene: el test dependia de los datos de Damian.
    monkeypatch.setattr(reels, "config_lote", lambda *a, **k: {"crear_propuestas": False, "una_noche": False,
                                                                "rehacer_todas": False})
    vigias = []
    arrancado = threading.Event()

    def vigia(parar, *a, **k):
        vigias.append(parar)
        arrancado.set()
        parar.wait(60)
    monkeypatch.setattr(reels, "vigilar_progreso_lote", vigia)
    durante = []

    def correr(*a, **k):
        # Bloque 23 (K0035): con 2 s tumbo la puerta de T851, T854 y T862 (suite en serie con el PC cargado: el hilo
        # tardaba mas en entrar). Thread.start() no espera a que la funcion arranque; la espera holgada solo cuesta
        # tiempo si el hilo de verdad no arranca.
        assert arrancado.wait(60)                             # el hilo ya esta vigilando cuando arranca el lote
        durante.append(vigias[0].is_set())
        return type("R", (), {"stdout": '{"hechos": [], "fallos": []}', "stderr": "", "returncode": 0})()
    r = reels.turno(maximo=1, correr=correr)
    assert durante == [False] and vigias[0].is_set() and r["noche"]["hechos"] == []
