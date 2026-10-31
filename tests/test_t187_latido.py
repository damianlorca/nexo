# -*- coding: utf-8 -*-
"""T187 (Damian 04/10): un turno que muere sin dejar registro ya no queda mudo. turno_nexo.py escribe un latido
cada minuto en turno_en_marcha.json; el planificador (tick, cada 20 s en la web) registra la muerte como fallo
(la vigilancia de la web manda el push) y avisa si el proceso sigue vivo pero sin latido. Sin procesos reales."""
from __future__ import annotations

import json
import os
import time

from interfaz import vigilancia
from nucleo import avisos, planificador as P, registro

PID_MUERTO = 99999999


def _registros():
    return sorted(registro.CARPETA.glob("turno_nexo_*.json"))


def test_turno_muerto_sin_registro_deja_un_fallo_que_la_web_avisa():
    ahora = time.time()
    P.progreso(pid_turno=PID_MUERTO, turno="t1", nombre="Noche", paso="trabajo", tarea="T101",
               lanzado=ahora - 900, latido=ahora - 400)
    assert P.en_marcha() is None and not P.EN_MARCHA.exists()
    (ruta,) = _registros()
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert "murio sin dejar registro" in datos["pasos"]["turno"]["error"]
    assert "trabajo" in datos["abortado"] and "T101" in datos["abortado"] and "7 min" in datos["abortado"]
    assert vigilancia.fallos_turno(datos) == ["turno"]     # => push "Turno nocturno: 1 fallo" (interfaz/push.py)


def test_turno_que_no_llego_a_arrancar_tambien_se_registra():
    P.progreso(pid=PID_MUERTO, turno="t1", nombre="Noche", lanzado=time.time() - 600)   # sin pid_turno
    assert P.en_marcha() is None
    (ruta,) = _registros()
    assert "no llego a arrancar" in json.loads(ruta.read_text(encoding="utf-8"))["abortado"]


def test_turno_que_ya_escribio_su_registro_final_no_se_duplica():
    lanzado = time.time() - 600
    P.progreso(pid_turno=PID_MUERTO, turno="t1", nombre="Noche", lanzado=lanzado)
    registro.CARPETA.mkdir(parents=True, exist_ok=True)
    (registro.CARPETA / "turno_nexo_20260101_000000.json").write_text("{}", encoding="utf-8")
    assert P.en_marcha() is None
    assert len(_registros()) == 1                         # solo el suyo


def test_turno_vivo_con_latido_reciente_no_avisa():
    ahora = time.time()
    P.progreso(pid_turno=os.getpid(), turno="t1", nombre="Noche", lanzado=ahora - 300, latido=ahora - 30)
    assert P.en_marcha() is not None
    assert P._vigilar_latido(ahora) is None and not list(avisos.CARPETA.glob("aviso_*.json"))
    assert _registros() == []


def test_turno_vivo_sin_latido_avisa_una_vez_tras_confirmar():
    ahora = time.time()
    P.progreso(pid_turno=os.getpid(), turno="t1", nombre="Noche", paso="trabajo", lanzado=ahora - 900,
               latido=ahora - 400)
    assert P._vigilar_latido(ahora) == "sospecha"                       # primera vez: solo sospecha
    assert P._vigilar_latido(ahora + 30) == "sospecha"                  # aun no han pasado LATIDO_CONFIRMA
    assert not list(avisos.CARPETA.glob("aviso_*.json"))
    assert P._vigilar_latido(ahora + P.LATIDO_CONFIRMA + 1) == "avisado"
    (aviso,) = avisos.CARPETA.glob("aviso_*.json")
    datos = json.loads(aviso.read_text(encoding="utf-8"))
    assert "sin señales" in datos["titulo"] and datos["ruta"] == "/turnos"
    assert P._vigilar_latido(ahora + 600) is None                       # una sola vez por turno


def test_si_el_latido_vuelve_la_sospecha_se_borra_y_no_avisa():
    ahora = time.time()
    P.progreso(pid_turno=os.getpid(), turno="t1", nombre="Noche", lanzado=ahora - 900, latido=ahora - 400)
    assert P._vigilar_latido(ahora) == "sospecha"                       # p. ej. el PC acababa de despertar
    P.progreso(latido=ahora + 20)                                       # el turno vuelve a latir
    assert P._vigilar_latido(ahora + 40) is None
    assert not list(avisos.CARPETA.glob("aviso_*.json"))


def test_tick_registra_la_muerte_y_libera_la_cola():
    P.progreso(pid_turno=PID_MUERTO, turno="t1", nombre="Noche", lanzado=time.time() - 600)
    hecho = P.tick()
    assert "latido" in hecho and len(_registros()) == 1 and P.en_marcha() is None


def test_iniciar_latido_escribe_el_primero_ya_y_se_para():
    P.progreso(pid_turno=os.getpid(), turno="t1")                       # lo que hace turno_nexo.py antes
    parar = P.iniciar_latido(cada=0.05)
    try:
        for _ in range(100):
            if P._leer(P.EN_MARCHA, {}).get("latido"):
                break
            time.sleep(0.02)
        primero = P._leer(P.EN_MARCHA, {})["latido"]
        time.sleep(0.2)
        assert P._leer(P.EN_MARCHA, {})["latido"] > primero            # sigue latiendo
    finally:
        parar.set()
    time.sleep(0.15)
    quieto = P._leer(P.EN_MARCHA, {})["latido"]
    time.sleep(0.2)
    assert P._leer(P.EN_MARCHA, {})["latido"] == quieto                 # parado


def test_el_latido_no_recrea_el_fichero_si_el_turno_ya_acabo():
    parar = P.iniciar_latido(cada=0.05)                                 # sin turno_en_marcha.json: nada que latir
    try:
        time.sleep(0.2)
        assert not P.EN_MARCHA.exists()
    finally:
        parar.set()


# ------------------------------------------------------------------ 04/10: finally y aviso por falta de progreso
def test_el_latido_no_cuenta_como_avance():
    P.progreso(pid_turno=os.getpid(), turno="t1", paso="trabajo")
    antes = P._leer(P.EN_MARCHA, {})["actualizado"]
    time.sleep(0.02)
    P._anotar({"latido": time.time()}, False)
    d = P._leer(P.EN_MARCHA, {})
    assert d["actualizado"] == antes and d["latido"]
    P.progreso(paso="otro")
    assert P._leer(P.EN_MARCHA, {})["actualizado"] > antes


def test_turno_vivo_sin_progreso_en_30_min_avisa_una_vez_aunque_el_latido_siga():
    ahora = time.time()
    P.progreso(pid_turno=os.getpid(), turno="t1", nombre="Noche", paso="trabajo", tarea="T101", lanzado=ahora - 4000)
    d = P._leer(P.EN_MARCHA, {})
    d["actualizado"] = ahora - 1900                                   # ultimo progreso hace 31 min
    P._escribir(P.EN_MARCHA, d)
    P._anotar({"latido": ahora - 10}, False)                          # el hilo sigue latiendo: no basta
    assert P._vigilar_progreso(ahora) == "avisado"
    (aviso,) = avisos.CARPETA.glob("aviso_*.json")
    datos = json.loads(aviso.read_text(encoding="utf-8"))
    assert "sin avanzar" in datos["titulo"] and "trabajo" in datos["cuerpo"] and "T101" in datos["cuerpo"]
    assert P._vigilar_progreso(ahora + 600) is None                   # una sola vez


def test_turno_con_progreso_reciente_o_muerto_no_avisa_por_progreso():
    ahora = time.time()
    P.progreso(pid_turno=os.getpid(), turno="t1", lanzado=ahora - 4000)
    assert P._vigilar_progreso(ahora) is None                         # acaba de progresar
    P.progreso(pid_turno=PID_MUERTO, turno="t1", lanzado=ahora - 4000)
    d = P._leer(P.EN_MARCHA, {})
    d["actualizado"] = ahora - 5000
    P._escribir(P.EN_MARCHA, d)
    assert P._vigilar_progreso(ahora) is None                         # muerto: lo trata en_marcha()
    assert not list(avisos.CARPETA.glob("aviso_*.json"))


def test_tick_incluye_la_vigilancia_de_progreso():
    assert "progreso" in P.tick()


def _turno_con_latido_espiado(monkeypatch, cuerpo):
    import turno_nexo
    parar = []

    class Evento:
        def set(self):
            parar.append(True)

    monkeypatch.setattr(turno_nexo.planificador, "iniciar_latido", lambda: Evento())
    monkeypatch.setattr(turno_nexo, "_turno", cuerpo)
    return turno_nexo, parar


def test_el_latido_se_para_en_cualquier_salida(monkeypatch):
    for salida in (lambda *a: {"ok": 1}, lambda *a: (_ for _ in ()).throw(RuntimeError("x")),
                   lambda *a: (_ for _ in ()).throw(SystemExit("y"))):
        tn, parado = _turno_con_latido_espiado(monkeypatch, salida)
        try:
            tn.turno()
        except (RuntimeError, SystemExit):
            pass
        assert parado == [True]


def test_un_turno_simulado_no_arranca_latido(monkeypatch):
    tn, parado = _turno_con_latido_espiado(monkeypatch, lambda *a: {"ok": 1})
    monkeypatch.setattr(tn.planificador, "iniciar_latido", lambda: (_ for _ in ()).throw(AssertionError("no")))
    assert tn.turno(simular=True) == {"ok": 1}
