# -*- coding: utf-8 -*-
"""T026 (11/09): dos turnos a la vez se pisaban la memoria. Verificacion del 05/10: el candado propio de
turno_nexo.py (archivo exclusivo; huerfano solo pasado el tope del turno + 5 min) deja correr uno solo."""
from __future__ import annotations

import os
import time

import turno_nexo


def test_un_segundo_turno_no_coge_el_candado_y_al_soltarlo_si(tmp_path, monkeypatch):
    monkeypatch.setattr(turno_nexo, "CANDADO", tmp_path / ".candado_turno_nexo.lock")
    assert turno_nexo._tomar_candado() is True
    assert turno_nexo._tomar_candado() is False                  # el segundo turno no entra
    turno_nexo._soltar_candado()
    assert turno_nexo._tomar_candado() is True


def test_un_candado_reciente_se_respeta_y_uno_huerfano_se_roba(tmp_path, monkeypatch):
    c = tmp_path / ".candado_turno_nexo.lock"
    monkeypatch.setattr(turno_nexo, "CANDADO", c)
    c.write_text("123 0", encoding="utf-8")
    viejo = time.time() - (turno_nexo.TOPE_SEGUNDOS + 60)       # dentro del margen de 5 min: sigue siendo de otro
    os.utime(c, (viejo, viejo))
    assert turno_nexo._tomar_candado() is False
    huerfano = time.time() - (turno_nexo.TOPE_SEGUNDOS + 400)
    os.utime(c, (huerfano, huerfano))
    assert turno_nexo._tomar_candado() is True and str(os.getpid()) in c.read_text(encoding="utf-8")
