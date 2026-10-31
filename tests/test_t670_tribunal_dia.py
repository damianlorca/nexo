# -*- coding: utf-8 -*-
"""T670 (decision del coordinador, 05/10): las propuestas que pasan de 30 no se archivan; un turno de dia del
tribunal (cada hora de 09:00 a 21:00) las digiere y se apaga solo cuando la cola baja de 30. La cuota de cada
proveedor la respeta tribunal.ciclo (enfriamiento y cupo web diario), igual que el turno de noche."""
from __future__ import annotations

from nucleo import freno, turnos

HORAS_DIA = [f"{h:02d}:00" for h in range(9, 22)]


def _dia(**k):
    base = {"nombre": "Tribunal de dia (cola > 30)", "plantilla": "tribunal", "dias": list(turnos.DIAS),
            "horas": HORAS_DIA, "max_tareas": 3, "max_minutos": 25, "avisar": True, "activo": True, "apagar_bajo": 30}
    return dict(base, **k)


def _ctx(t, manual=False):
    return turnos.contexto(turnos.buscar(t["id"]), manual=manual)


def test_turno_de_dia_valida_13_horas_y_guarda_el_umbral():
    t = turnos.guardar_turno(_dia())
    assert t["horas"] == HORAS_DIA and t["apagar_bajo"] == 30
    assert turnos.contexto(t)["apagar_bajo"] == 30


def test_editar_desde_la_web_sin_el_campo_no_pierde_el_umbral():
    t = turnos.guardar_turno(_dia())
    datos = {k: v for k, v in t.items() if k != "apagar_bajo"}
    turnos.guardar_turno(dict(datos, max_tareas=2))
    assert turnos.buscar(t["id"])["apagar_bajo"] == 30


def test_turnos_sin_umbral_no_cambian():
    t = turnos.guardar_turno(_dia(apagar_bajo=0))
    assert "apagar_bajo" not in t


def test_con_30_o_mas_trabaja_y_por_debajo_se_apaga_solo(monkeypatch):
    from turno_nexo import apagar_por_cola
    t = turnos.guardar_turno(_dia())
    monkeypatch.setattr(freno, "estado_cola", lambda tareas=None: {"propuestas": 30})
    assert apagar_por_cola(_ctx(t)) == ""
    assert turnos.buscar(t["id"])["activo"] is True
    monkeypatch.setattr(freno, "estado_cola", lambda tareas=None: {"propuestas": 29})
    assert apagar_por_cola(_ctx(t), simular=True)            # simulado: lo dice pero no toca la tabla
    assert turnos.buscar(t["id"])["activo"] is True
    assert apagar_por_cola(_ctx(t, manual=True)) == ""       # "Lanzar ya" a mano no lo apaga
    motivo = apagar_por_cola(_ctx(t))
    assert "29" in motivo and "se apaga solo" in motivo
    assert turnos.buscar(t["id"])["activo"] is False
    assert turnos.buscar(t["id"])["apagar_bajo"] == 30       # apagado, pero listo para volver a encenderse


def test_el_tribunal_de_noche_no_se_apaga_por_la_cola(monkeypatch):
    from turno_nexo import apagar_por_cola
    t = turnos.guardar_turno(_dia(apagar_bajo=0, horas=["22:00"]))
    monkeypatch.setattr(freno, "estado_cola", lambda tareas=None: {"propuestas": 0})
    assert apagar_por_cola(_ctx(t)) == ""
    assert turnos.buscar(t["id"])["activo"] is True
