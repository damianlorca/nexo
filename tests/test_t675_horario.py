# -*- coding: utf-8 -*-
"""T675 fases 3-5 (6c): prioridad en la cola del planificador y horario real de turnos sin solapes."""
from __future__ import annotations

import json

from nucleo import planificador as P
from nucleo.config import RAIZ

CFG = {"turnos": [{"id": "a", "plantilla": "modelos"}, {"id": "b", "plantilla": "tribunal"},
                  {"id": "c", "plantilla": "implementador"}, {"id": "d", "plantilla": "cola"},
                  {"id": "e", "plantilla": "reels"}, {"id": "f", "plantilla": "desconocida"}]}


def _x(turno, pedido, manual=False):
    return {"turno": turno, "pedido": pedido, "manual": manual}


def test_la_cola_sale_por_prioridad_y_a_igualdad_por_hora():
    cola = [_x("a", "2026-10-13T01:00:00"), _x("f", "2026-10-13T00:00:00"), _x("e", "2026-10-13T00:10:00"),
            _x("d", "2026-10-13T00:20:00"), _x("c", "2026-10-13T00:30:00"), _x("b", "2026-10-13T02:00:00")]
    orden = [x["turno"] for x in sorted(cola, key=lambda x: P._orden_cola(x, CFG))]
    assert orden == ["b", "c", "d", "e", "a", "f"]          # tribunal > implementador > cola > reels > modelos > resto
    dos = [_x("c", "2026-10-13T00:40:00"), _x("c", "2026-10-13T00:30:00")]
    assert [x["pedido"][11:16] for x in sorted(dos, key=lambda x: P._orden_cola(x, CFG))] == ["00:30", "00:40"]


def test_lanzar_ya_de_damian_pasa_primero():
    cola = [_x("b", "2026-10-13T00:00:00"), _x("a", "2026-10-13T03:00:00", manual=True)]
    assert sorted(cola, key=lambda x: P._orden_cola(x, CFG))[0]["turno"] == "a"


def test_el_horario_de_la_tabla_no_tiene_solapes_y_el_tribunal_de_dia_esta_encendido():
    cfg = json.loads((RAIZ / "memoria" / "turnos_config.json").read_text(encoding="utf-8"))
    assert P.choques(cfg) == {}
    dia = next(t for t in cfg["turnos"] if t["plantilla"] == "tribunal" and t["horas"][0] >= "08:00")
    assert dia["activo"] and "apagar_bajo" not in dia and len(dia["horas"]) >= 4


def test_cada_plantilla_pide_trabajo_verificable_y_no_arranca_sin_trabajo():
    from nucleo import turnos
    for pid in ("cola", "revisar_codigo", "revisar_archivos", "investigacion", "correcciones", "vigia"):
        assert len(turnos.PLANTILLAS[pid]["texto"]) > 120, pid
    assert "sin hallazgos" in turnos.PLANTILLAS["revisar_codigo"]["texto"]
    for pid in ("tribunal", "radar", "modelos", "reels"):
        assert "No arranca" in turnos.PLANTILLAS[pid]["texto"] or "no arranca" in turnos.PLANTILLAS[pid]["texto"], pid
