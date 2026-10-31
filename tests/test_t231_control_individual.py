# -*- coding: utf-8 -*-
"""T231 (28/09, tras la prueba real): control individual de turnos. Parar el que esta en marcha sin tocar la
PARADA general, quitar de la cola, posponer (15 min, 1 h, manana a la misma hora, hora elegida) y saltar
solo la proxima ejecucion. Sin procesos reales."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import pytest

from nucleo import parada, registro
from nucleo import planificador as P
from nucleo import turnos

LUNES = datetime(2026, 9, 28, 16, 59, 30)


def _turno(**campos):
    base = {"nombre": "Prueba", "plantilla": "cola", "dias": list(turnos.DIAS), "horas": ["03:30"]}
    return turnos.guardar_turno(dict(base, **campos))


def _lanzar(entrada):
    return 99999999


@pytest.fixture
def cierre(tmp_path, monkeypatch):
    monkeypatch.setattr(parada, "BANDERA", tmp_path / "PARADA_NEXO")
    monkeypatch.setattr(parada, "CIERRE", tmp_path / "CIERRE_TURNO")
    return tmp_path


# ------------------------------------------------------------------ parar
def test_parar_pide_cierre_suave_sin_tocar_la_parada(cierre):
    t = _turno(nombre="Tarde")
    P.encolar(t["id"], manual=True)
    P.tick(LUNES, lanzar=_lanzar)
    m = P.parar()
    assert m["turno"] == t["id"] and parada.cierre_pedido() and parada.motivo_cierre() == "parado por Damian"
    assert parada.activa() is None                                   # la PARADA general no se toca
    assert P.en_curso()["marcha"]["parando"]


def test_parar_sin_turno_en_marcha_lo_dice():
    with pytest.raises(turnos.ConfigInvalida, match="ningun turno en marcha"):
        P.parar()


def test_si_no_obedece_se_cierra_por_pid_exacto_tras_comprobar_su_linea(cierre, monkeypatch):
    t = _turno(nombre="Tarde")
    P.progreso(pid_turno=4242, turno=t["id"], nombre="Tarde", inicio="2026-09-28T17:00:00",
               lanzado=time.time() - 400, parar_pedido=time.time() - P.FORZAR_TRAS - 5)
    muertos = []
    monkeypatch.setattr(P, "_vivo", lambda pid: pid == 4242 and not muertos)
    monkeypatch.setattr(P, "_linea_de_comando", lambda pid: f"python.exe turno_nexo.py --turno={t['id']} --arrancar-chrome")
    monkeypatch.setattr(P, "_matar", muertos.append)
    hecho = P.tick(LUNES, lanzar=_lanzar)
    assert muertos == [4242] and "cerrado" in hecho["forzado"] and not P.EN_MARCHA.exists()
    reg = json.loads(sorted(registro.CARPETA.glob("turno_nexo_*.json"))[-1].read_text(encoding="utf-8"))
    assert reg["turno_id"] == t["id"] and "parado por Damian" in reg["abortado"]


def test_nunca_mata_un_pid_que_ya_es_de_otro_programa(cierre, monkeypatch):
    t = _turno()
    P.progreso(pid_turno=4242, turno=t["id"], lanzado=time.time() - 400, parar_pedido=time.time() - P.FORZAR_TRAS - 5)
    muertos = []
    monkeypatch.setattr(P, "_vivo", lambda pid: True)
    monkeypatch.setattr(P, "_linea_de_comando", lambda pid: "C:/Windows/notepad.exe")    # Windows reutilizo el PID
    monkeypatch.setattr(P, "_matar", muertos.append)
    assert "no se toca" in P.tick(LUNES, lanzar=_lanzar)["forzado"] and muertos == []


def test_antes_del_plazo_no_se_fuerza(monkeypatch):
    P.progreso(pid_turno=4242, turno="x", lanzado=time.time(), parar_pedido=time.time())
    monkeypatch.setattr(P, "_vivo", lambda pid: True)
    monkeypatch.setattr(P, "_matar", lambda pid: pytest.fail("no debe matar antes de tiempo"))
    assert P.tick(LUNES, lanzar=_lanzar)["forzado"] is None


def test_turno_parado_lo_dice_en_su_registro(cierre, monkeypatch, tmp_path):
    import turno_nexo
    from nucleo import trabajo
    from nucleo import tareas as T
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado")
    monkeypatch.setattr(turno_nexo, "ram_libre_gb", lambda: 32.0)
    T.anadir("Investigar X", depende="ia", etiquetas=["cat:investigacion"])
    t = _turno()

    def ciclo(**k):
        P.parar()          # Damian pulsa "Parar" mientras trabaja
        return []
    monkeypatch.setattr(trabajo, "ciclo", ciclo)
    reg = turno_nexo.turno(turno_id=t["id"])
    assert reg["parado"] == "parado por Damian" and not parada.cierre_pedido() and not P.EN_MARCHA.exists()


# ------------------------------------------------------------------ cola: quitar y posponer
def test_quitar_de_la_cola():
    a, b = _turno(nombre="A"), _turno(nombre="B")
    P.encolar(a["id"], manual=True)
    P.encolar(b["id"], manual=True)
    P.quitar(a["id"])
    assert [x["turno"] for x in P.cola()] == [b["id"]]
    with pytest.raises(turnos.ConfigInvalida):
        P.quitar(a["id"])


@pytest.mark.parametrize("opcion, hora, esperado", [
    ("15m", "", datetime(2026, 9, 28, 17, 14, 30)),
    ("1h", "", datetime(2026, 9, 28, 17, 59, 30)),
    ("manana", "", datetime(2026, 9, 29, 17, 0)),          # misma hora que estaba pedido (17:00), manana
    ("hora", "20:15", datetime(2026, 9, 28, 20, 15)),       # hoy, aun no ha pasado
    ("hora", "08:00", datetime(2026, 9, 29, 8, 0)),         # ya paso hoy: manana
])
def test_posponer_en_la_cola(opcion, hora, esperado):
    t = _turno(horas=["17:00"])
    P.encolar(t["id"], cuando=datetime(2026, 9, 28, 17, 0))
    assert P.posponer(t["id"], opcion, hora, ahora=LUNES) == esperado
    assert P.cola()[0]["no_antes"] == esperado.isoformat(timespec="seconds")


def test_pospuesto_no_arranca_antes_y_deja_pasar_a_los_demas():
    a, b = _turno(nombre="A"), _turno(nombre="B")
    P.encolar(a["id"], manual=True, cuando=LUNES)
    P.encolar(b["id"], manual=True, cuando=LUNES)
    P.posponer(a["id"], "1h", ahora=LUNES)
    assert P.tick(LUNES, lanzar=_lanzar)["lanzado"] == b["id"]            # B no espera a A
    P.terminar()
    assert P.tick(LUNES + timedelta(minutes=30), lanzar=_lanzar)["lanzado"] is None
    assert P.tick(LUNES + timedelta(minutes=61), lanzar=_lanzar)["lanzado"] == a["id"]


def test_posponer_el_que_esta_en_marcha_lo_para_y_lo_reencola(cierre):
    t = _turno()
    P.encolar(t["id"], manual=True, cuando=LUNES)
    P.tick(LUNES, lanzar=_lanzar)
    cuando = P.posponer(t["id"], "15m", ahora=LUNES)
    assert parada.cierre_pedido() and P.cola()[0]["turno"] == t["id"]
    assert P.cola()[0]["no_antes"] == cuando.isoformat(timespec="seconds")


def test_posponer_opcion_mala():
    t = _turno()
    P.encolar(t["id"], manual=True)
    with pytest.raises(turnos.ConfigInvalida):
        P.posponer(t["id"], "siglo")
    with pytest.raises(turnos.ConfigInvalida):
        P.posponer(t["id"], "hora", "25:00")


# ------------------------------------------------------------------ saltar solo la proxima
def test_saltar_solo_la_proxima():
    t = _turno(horas=["17:00"])
    l = []
    P.tick(LUNES, lanzar=lambda e: l.append(e) or 1)                          # 16:59:30
    assert P.saltar_proxima(t["id"], LUNES) == datetime(2026, 9, 28, 17, 0)
    prox, saltada = P.proxima_efectiva(t, LUNES)
    assert saltada == datetime(2026, 9, 28, 17, 0) and prox == datetime(2026, 9, 29, 17, 0)
    hecho = P.tick(LUNES + timedelta(minutes=1), lanzar=lambda e: l.append(e) or 1)
    assert hecho["saltados"] == [t["id"]] and not l and P.cola() == []
    assert "saltos" not in P.estado() or t["id"] not in P.estado()["saltos"]   # solo esa
    P.tick(LUNES + timedelta(days=1), lanzar=lambda e: l.append(e) or 1)
    P.tick(LUNES + timedelta(days=1, minutes=1), lanzar=lambda e: l.append(e) or 1)
    assert [e["turno"] for e in l] == [t["id"]]                                # la del martes, normal


def test_deshacer_salto():
    t = _turno(horas=["17:00"])
    P.saltar_proxima(t["id"], LUNES)
    P.deshacer_salto(t["id"])
    assert P.proxima_efectiva(t, LUNES) == (datetime(2026, 9, 28, 17, 0), None)


def test_en_curso_para_las_listas(monkeypatch):
    a, b = _turno(nombre="A"), _turno(nombre="B")
    P.encolar(a["id"], manual=True, cuando=LUNES)
    P.encolar(b["id"], manual=False, cuando=LUNES)
    P.posponer(b["id"], "hora", "20:15", ahora=LUNES)
    c = P.en_curso(LUNES)["cola"]
    assert [(x["nombre"], x["pos"], x["manual"]) for x in c] == [("A", 1, True), ("B", 2, False)]
    assert c[1]["pospuesto"] == "lun 28/09 20:15" and c[0]["pospuesto"] == ""


# ------------------------------------------------------------------ reanudar y reordenar (28/09, 2a ronda)
def test_mover_en_la_cola():
    a, b, c = _turno(nombre="A"), _turno(nombre="B"), _turno(nombre="C")
    for t in (a, b, c):
        P.encolar(t["id"], manual=True)
    orden = lambda: [x["turno"] for x in P.cola()]  # noqa: E731
    P.mover(c["id"], "primero")
    assert orden() == [c["id"], a["id"], b["id"]]
    P.mover(a["id"], "abajo")
    assert orden() == [c["id"], b["id"], a["id"]]
    P.mover(a["id"], "arriba")
    P.mover(c["id"], "arriba")                    # ya es el primero: se queda
    assert orden() == [c["id"], a["id"], b["id"]]
    with pytest.raises(turnos.ConfigInvalida):
        P.mover(a["id"], "al_infinito")


def test_reanudar_un_pospuesto_pasa_el_primero_y_sin_espera():
    a, b = _turno(nombre="A"), _turno(nombre="B")
    P.encolar(a["id"], manual=True, cuando=LUNES)
    P.encolar(b["id"], manual=True, cuando=LUNES)
    P.posponer(b["id"], "manana", ahora=LUNES)
    assert P.reanudar(b["id"], LUNES) == "pospuesto"
    assert [x["turno"] for x in P.cola()] == [b["id"], a["id"]] and "no_antes" not in P.cola()[0]
    assert P.tick(LUNES, lanzar=_lanzar)["lanzado"] == b["id"]


def test_parado_sale_en_la_lista_y_se_puede_reanudar(cierre):
    t = _turno(nombre="Tarde")
    P.encolar(t["id"], manual=True)
    P.tick(LUNES, lanzar=_lanzar)
    P.parar()
    P.terminar()                                          # el turno acaba tras el cierre suave
    [p] = P.en_curso()["parados"]
    assert p["turno"] == t["id"] and p["nombre"] == "Tarde"
    assert P.reanudar(t["id"]) == "parado"
    assert P.en_curso()["parados"] == [] and P.cola()[0]["turno"] == t["id"]


def test_posponer_el_que_esta_en_marcha_no_lo_deja_como_parado(cierre):
    t = _turno()
    P.encolar(t["id"], manual=True)
    P.tick(LUNES, lanzar=_lanzar)
    P.posponer(t["id"], "1h")
    P.terminar()
    assert P.en_curso()["parados"] == [] and P.cola()[0]["turno"] == t["id"]


def test_reanudar_algo_que_no_esta_pospuesto_ni_parado():
    t = _turno()
    with pytest.raises(turnos.ConfigInvalida):
        P.reanudar(t["id"])
