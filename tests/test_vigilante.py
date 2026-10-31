# -*- coding: utf-8 -*-
"""canal/vigilante.py: el proceso que relanza el bot de Telegram si muere.

Sin ninguna prueba hasta ahora. _vivo() usa kernel32 (Windows): su prueba real es
"no ejecutable en Linux". El bucle de main() se prueba entero con dobles.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from canal import vigilante


class _Fin(Exception):
    """Para salir del while True de main()."""


def _preparar(monkeypatch, *, unico=True, pids, vivos, vueltas=1):
    """pids: lo que devuelve pid_anotado en cada llamada. vivos: {pid: bool}."""
    llamadas = {"arrancar": 0, "sleeps": []}
    pids = list(pids)

    monkeypatch.setattr(vigilante, "unico", lambda nombre: unico)
    monkeypatch.setattr(vigilante, "pid_anotado", lambda nombre: pids.pop(0) if pids else 0)
    monkeypatch.setattr(vigilante, "_vivo", lambda pid: vivos.get(pid, False))

    def arrancar():
        llamadas["arrancar"] += 1
        return 777

    monkeypatch.setattr(vigilante, "_arrancar", arrancar)

    def dormir(s):
        llamadas["sleeps"].append(s)
        if s == vigilante.INTERVALO and llamadas["sleeps"].count(vigilante.INTERVALO) >= vueltas:
            raise _Fin

    monkeypatch.setattr(vigilante.time, "sleep", dormir)
    return llamadas


def test_si_ya_hay_otro_vigilante_se_retira(monkeypatch):
    ll = _preparar(monkeypatch, unico=False, pids=[], vivos={})
    vigilante.main()
    assert ll["arrancar"] == 0 and ll["sleeps"] == []


def test_bot_vivo_no_lo_toca(monkeypatch):
    ll = _preparar(monkeypatch, pids=[100], vivos={100: True})
    with pytest.raises(_Fin):
        vigilante.main()
    assert ll["arrancar"] == 0
    assert ll["sleeps"] == [vigilante.INTERVALO]


def test_bot_muerto_lo_levanta_y_espera_el_arranque(monkeypatch):
    ll = _preparar(monkeypatch, pids=[100, 200], vivos={200: True})
    with pytest.raises(_Fin):
        vigilante.main()
    assert ll["arrancar"] == 1
    assert ll["sleeps"] == [vigilante.ESPERA_ARRANQUE, vigilante.INTERVALO]


def test_sin_pid_anotado_tambien_lo_levanta(monkeypatch):
    ll = _preparar(monkeypatch, pids=[0, 0], vivos={})
    with pytest.raises(_Fin):
        vigilante.main()
    assert ll["arrancar"] == 1


def test_si_no_consigue_levantarlo_reintenta_en_la_siguiente_vuelta(monkeypatch):
    ll = _preparar(monkeypatch, pids=[0, 0, 0, 0], vivos={}, vueltas=2)
    with pytest.raises(_Fin):
        vigilante.main()
    assert ll["arrancar"] == 2


def test_arrancar_lanza_el_bot_fuera_del_job_y_sin_ventana(monkeypatch):
    """No lanza nada de verdad: se captura la llamada a Popen."""
    for nombre, v in (("CREATE_NO_WINDOW", 0x08000000), ("CREATE_NEW_PROCESS_GROUP", 0x200),
                      ("CREATE_BREAKAWAY_FROM_JOB", 0x01000000)):
        monkeypatch.setattr(subprocess, nombre, v, raising=False)
    vistos = []

    class PopenFalso:
        pid = 4321

        def __init__(self, args, **kw):
            vistos.append((args, kw))

    monkeypatch.setattr(vigilante.subprocess, "Popen", PopenFalso)
    assert vigilante._arrancar() == 4321
    args, kw = vistos[0]
    assert args[-1] == str(vigilante.BOT)
    assert kw["creationflags"] & 0x01000000  # breakaway
    assert kw["stdin"] == subprocess.DEVNULL


def test_arrancar_sin_breakaway_si_el_job_no_lo_permite(monkeypatch):
    for nombre, v in (("CREATE_NO_WINDOW", 0x08000000), ("CREATE_NEW_PROCESS_GROUP", 0x200),
                      ("CREATE_BREAKAWAY_FROM_JOB", 0x01000000)):
        monkeypatch.setattr(subprocess, nombre, v, raising=False)
    vistos = []

    class PopenFalso:
        pid = 55

        def __init__(self, args, **kw):
            vistos.append(kw["creationflags"])
            if kw["creationflags"] & 0x01000000:
                raise OSError("acceso denegado")

    monkeypatch.setattr(vigilante.subprocess, "Popen", PopenFalso)
    assert vigilante._arrancar() == 55
    assert len(vistos) == 2 and not vistos[1] & 0x01000000


def test_vivo_rechaza_pid_no_positivo_sin_tocar_el_sistema():
    assert vigilante._vivo(0) is False
    assert vigilante._vivo(-3) is False


@pytest.mark.skipif(sys.platform != "win32", reason="no ejecutable en Linux: _vivo() usa kernel32.OpenProcess")
def test_vivo_con_un_proceso_real_windows():
    import os
    assert vigilante._vivo(os.getpid()) is True
