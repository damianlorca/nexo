# -*- coding: utf-8 -*-
"""T231 (rediseno 28/09): tabla de turnos y planificador de NEXO (cola, uno a la vez, choques, progreso).

Incluye el fallo de la prueba real del 28/09: dos "Lanzar ya" seguidos (revisar codigo y vigia) no ejecutaron
nada: Windows dejaba la tarea "Queued" por la bateria y el segundo pisaba al primero. Sin procesos reales.
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timedelta

import pytest

from nucleo import planificador as P
from nucleo import turnos

LUNES = datetime(2026, 9, 28, 16, 59, 30)      # lunes


def _turno(**campos):
    base = {"nombre": "Prueba", "plantilla": "cola", "dias": list(turnos.DIAS), "horas": ["03:30"]}
    return turnos.guardar_turno(dict(base, **campos))


class Lanzador:
    def __init__(self):
        self.lanzados = []

    def __call__(self, entrada):
        self.lanzados.append((entrada["turno"], entrada.get("manual", False)))
        return 99999999      # pid que no existe: en_marcha() se sostiene por ARRANQUE


# ------------------------------------------------------------------ tabla
def test_migra_la_config_vieja_a_dos_turnos():
    turnos.CONFIG.parent.mkdir(parents=True, exist_ok=True)
    turnos.CONFIG.write_text(json.dumps({"plantilla": "cola", "tareas": [], "max_tareas": 2,
                                         "horario": {"dias": list(turnos.DIAS), "horas": ["17:00"]}}), encoding="utf-8")
    cfg = turnos.cargar()
    assert cfg["migrado"] and [(t["nombre"], t["horas"], t["activo"]) for t in cfg["turnos"]] == [
        ("Noche 03:30", ["03:30"], True), ("Turno 17:00", ["17:00"], True)]
    turnos.guardar(cfg)
    assert not turnos.cargar()["migrado"] and len(turnos.cargar()["turnos"]) == 2


def test_alta_edicion_duplicar_borrar_y_activo():
    t = _turno(nombre="  Revisión   nocturna ", plantilla="revisar_codigo", horas="23:00, 05:00", max_minutos=90,
               instrucciones="Solo seguridad.", tareas="t101", avisar=False)
    assert (t["nombre"], t["horas"], t["max_minutos"], t["tareas"], t["avisar"]) == \
        ("Revisión nocturna", ["05:00", "23:00"], 90, ["T101"], False)
    ctx = turnos.contexto(t)
    assert ctx["texto"] == "Solo seguridad." and ctx["personalizadas"] and ctx["solo_lectura"]
    copia = turnos.duplicar(t["id"])
    assert copia["id"] != t["id"] and copia["nombre"].endswith("(copia)") and not copia["activo"]
    turnos.guardar_turno(dict(t, nombre="Otro nombre"))
    assert turnos.buscar(t["id"])["nombre"] == "Otro nombre" and len(turnos.cargar()["turnos"]) == 2
    turnos.poner_activo(t["id"], False)
    assert not turnos.buscar(t["id"])["activo"]
    turnos.archivar(t["id"])
    cfg = turnos.cargar()
    assert [x["id"] for x in cfg["turnos"]] == [copia["id"]] and cfg["archivados"][0]["id"] == t["id"]


@pytest.mark.parametrize("malo", [{"nombre": ""}, {"plantilla": "borrar_todo"}, {"dias": []}, {"horas": "25:00"},
                                  {"horas": "3:30"}, {"max_minutos": 5}, {"max_minutos": 999}, {"max_tareas": 9},
                                  {"tareas": "T1; rm -rf"}, {"instrucciones": "x" * 2000}])
def test_validacion(malo):
    with pytest.raises(turnos.ConfigInvalida):
        _turno(**malo)


# ------------------------------------------------------------------ calendario y choques
def test_proxima_respeta_dias_y_horas():
    t = _turno(dias=["miercoles"], horas=["17:00", "08:00"])
    assert P.proxima(t, LUNES) == datetime(2026, 9, 30, 8, 0)
    t = _turno(horas=["17:00"])
    assert P.proxima(t, LUNES) == datetime(2026, 9, 28, 17, 0)


def test_choques_avisan_y_solo_entre_activos():
    a = _turno(nombre="A", horas=["03:30"], max_minutos=55)
    b = _turno(nombre="B", horas=["04:00"], max_minutos=30)            # empieza antes de que acabe A
    c = _turno(nombre="C", horas=["05:00"])                             # no pisa a nadie
    d = _turno(nombre="D", dias=["domingo"], horas=["23:30"], max_minutos=120)
    e = _turno(nombre="E", dias=["lunes"], horas=["01:00"])             # D (domingo 23:30+2h) pisa el lunes 01:00
    f = _turno(nombre="F", horas=["03:30"], activo=False)               # inactivo: no cuenta
    ch = P.choques()
    assert ch[a["id"]] == ["B"] and ch[b["id"]] == ["A"] and c["id"] not in ch and f["id"] not in ch
    assert ch[d["id"]] == ["E"]


# ------------------------------------------------------------------ planificador
def test_tick_encola_a_su_hora_y_lanza(monkeypatch):
    t = _turno(horas=["17:00"])
    l = Lanzador()
    nada = P.tick(LUNES, lanzar=l)                                                       # 16:59:30: nada
    assert (nada["encolados"], nada["lanzado"], nada["motivo"]) == ([], None, "")
    hecho = P.tick(LUNES + timedelta(seconds=40), lanzar=l)                             # 17:00:10
    assert hecho["encolados"] == [t["id"]] and hecho["lanzado"] == t["id"] and l.lanzados == [(t["id"], False)]
    assert P.en_marcha()["turno"] == t["id"] and P.cola() == []
    P.terminar()
    assert P.tick(LUNES + timedelta(seconds=60), lanzar=l)["lanzado"] is None   # la misma hora no se repite


def test_dos_lanzar_ya_seguidos_se_ejecutan_los_dos_uno_tras_otro():
    """El fallo real del 28/09: ninguno se ejecutaba y el segundo pisaba al primero."""
    rev = _turno(nombre="Revisar codigo", plantilla="revisar_codigo", horas=["03:30"])
    vig = _turno(nombre="Vigia", plantilla="vigia", horas=["04:30"])
    l = Lanzador()
    P.encolar(rev["id"], manual=True)
    assert P.tick(LUNES, lanzar=l)["lanzado"] == rev["id"]
    P.encolar(vig["id"], manual=True)
    hecho = P.tick(LUNES + timedelta(seconds=20), lanzar=l)
    assert hecho["lanzado"] is None and "espera" in hecho["motivo"] and [x["turno"] for x in P.cola()] == [vig["id"]]
    P.terminar()                                                     # acaba el primero
    assert P.tick(LUNES + timedelta(seconds=40), lanzar=l)["lanzado"] == vig["id"]
    assert l.lanzados == [(rev["id"], True), (vig["id"], True)]


def test_encolar_dos_veces_el_mismo_no_lo_duplica():
    t = _turno()
    P.encolar(t["id"], manual=True)
    P.encolar(t["id"], manual=True)
    assert len(P.cola()) == 1


def test_lanzar_no_depende_de_windows_ni_de_la_bateria(monkeypatch):
    """El proceso se arranca directamente (sin Programador de tareas): nada de DisallowStartIfOnBatteries."""
    llamadas = []

    class Proc:
        pid = 4321
    monkeypatch.setattr(P, "_popen", lambda args, **k: llamadas.append((args, k)) or Proc())
    assert P.lanzar_proceso({"turno": "noche", "manual": True}) == 4321
    args, k = llamadas[0]
    assert args[1].endswith("turno_nexo.py") and "--turno=noche" in args and "--manual" in args
    assert not any("schtasks" in a or "ScheduledTask" in a for a in args)
    assert k["cwd"] == str(P.RAIZ) and k["stdin"] == subprocess.DEVNULL


def test_parada_y_desactivados_retienen_la_cola(monkeypatch):
    from nucleo import parada
    t = _turno()
    l = Lanzador()
    monkeypatch.setattr(parada, "activa", lambda: "me voy")
    P.encolar(t["id"], manual=True)
    assert "PARADA" in P.tick(LUNES, lanzar=l)["motivo"] and not l.lanzados and len(P.cola()) == 1
    monkeypatch.setattr(parada, "activa", lambda: None)
    turnos.desactivar("de viaje")
    t2 = _turno(nombre="Programado", horas=["17:00"])
    P.tick(LUNES + timedelta(minutes=1), lanzar=l)      # el manual SI sale aunque esten desactivados...
    assert l.lanzados == [(t["id"], True)]
    P.terminar()
    hecho = P.tick(LUNES + timedelta(minutes=2), lanzar=l)
    assert hecho["motivo"] == "turnos desactivados" and all(x["turno"] != t2["id"] for x in P.cola())  # ...lo programado no


def test_recupera_horas_perdidas_dentro_de_la_gracia():
    t = _turno(horas=["17:00"])
    l = Lanzador()
    P.tick(LUNES, lanzar=l)                                         # 16:59:30, ultimo tick
    P.tick(LUNES + timedelta(minutes=40), lanzar=l)                 # la web estuvo caida: 17:39 lo recupera
    assert l.lanzados == [(t["id"], False)]


def test_no_recupera_lo_de_hace_mas_de_la_gracia_ni_en_el_primer_tick():
    _turno(horas=["15:00"])
    l = Lanzador()
    P.tick(LUNES, lanzar=l)                          # primer tick de la vida: no dispara lo pasado
    P.tick(LUNES + timedelta(hours=3), lanzar=l)     # 19:59: 15:00 quedo fuera de la gracia
    assert l.lanzados == []


def test_turno_muerto_no_bloquea_la_cola():
    P.progreso(pid_turno=99999999, turno="x", lanzado=time.time() - 600)
    assert P.en_marcha() is None and not P.EN_MARCHA.exists()


def test_fallo_al_lanzar_queda_anotado_y_libera():
    t = _turno()
    P.encolar(t["id"], manual=True)

    def roto(entrada):
        raise OSError("no hay python")
    hecho = P.tick(LUNES, lanzar=roto)
    assert "no se pudo lanzar" in hecho["motivo"] and P.en_marcha() is None
    assert P.estado()["errores"][-1]["turno"] == t["id"]


# ------------------------------------------------------------------ turno_nexo informa del progreso
def test_turno_nexo_deja_progreso_y_lo_limpia(monkeypatch, tmp_path):
    import turno_nexo
    from nucleo import trabajo
    from nucleo import tareas as T
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado")
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: None)
    monkeypatch.setattr(turno_nexo, "ram_libre_gb", lambda: 32.0)
    T.anadir("Investigar X", depende="ia", etiquetas=["cat:investigacion"])
    t = _turno(nombre="Tarde", horas=["17:00"])
    vistos = []

    def ciclo(**k):
        k["al_empezar"](k["lista"][0])
        vistos.append(dict(P.en_marcha()))
        return []
    monkeypatch.setattr(trabajo, "ciclo", ciclo)
    turno_nexo.turno(turno_id=t["id"])
    assert vistos[0]["paso"] == "trabajo" and vistos[0]["tarea"].startswith("T001 Investigar X")
    assert vistos[0]["nombre"] == "Tarde" and vistos[0]["pid_turno"]
    assert not P.EN_MARCHA.exists()          # al acabar, la cola queda libre


def test_resumen_centro(monkeypatch):
    t = _turno(nombre="Tarde", horas=["17:00"])
    P.progreso(pid_turno=__import__("os").getpid(), turno=t["id"], nombre="Tarde", paso="trabajo",
               tarea="T001 Investigar X", lanzado=time.time() - 125)
    r = P.resumen_centro(LUNES)
    assert r["marcha"]["transcurrido"].startswith("2 min") and r["marcha"]["tarea"] == "T001 Investigar X"
    assert r["proximo"] == {"nombre": "Tarde", "cuando": "lun 28/09 17:00"} and r["ultimo"] is None
