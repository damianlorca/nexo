# -*- coding: utf-8 -*-
"""nucleo/candado.py: el candado de archivo que protege tareas.json, catalogo.json y la evidencia.

Antes solo se probaba de rebote (prueba_candado_tareas.py). Aqui, directo.
"""
from __future__ import annotations

import os
import threading
import time

import pytest

from nucleo import candado


def test_crea_el_candado_con_el_pid_y_lo_suelta_al_salir(tmp_path):
    ruta = tmp_path / "sub" / "x.lock"
    with candado.bloqueo(ruta):
        assert ruta.is_file()
        assert ruta.read_text().split(":")[0] == str(os.getpid())
    assert not ruta.exists()


def test_lo_suelta_aunque_el_bloque_lance(tmp_path):
    ruta = tmp_path / "x.lock"
    with pytest.raises(ValueError):
        with candado.bloqueo(ruta):
            raise ValueError("fallo dentro")
    assert not ruta.exists()


def test_exclusion_mutua_entre_hilos(tmp_path):
    """Leer-modificar-escribir con una pausa en medio: sin candado se pierden sumas."""
    ruta = tmp_path / "x.lock"
    contador = tmp_path / "n.txt"
    contador.write_text("0")

    def sumar():
        for _ in range(10):
            with candado.bloqueo(ruta, espera_maxima=20):
                n = int(contador.read_text())
                time.sleep(0.001)
                contador.write_text(str(n + 1))

    hilos = [threading.Thread(target=sumar) for _ in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert int(contador.read_text()) == 40
    assert not ruta.exists()


def test_roba_un_candado_huerfano(tmp_path):
    ruta = tmp_path / "x.lock"
    ruta.write_text("99999")
    viejo = time.time() - candado.UMBRAL_HUERFANO - 5
    os.utime(ruta, (viejo, viejo))
    t0 = time.monotonic()
    with candado.bloqueo(ruta, espera_maxima=2):
        assert ruta.read_text().split(":")[0] == str(os.getpid())
    assert time.monotonic() - t0 < 1.5


def test_sin_candado_tras_la_espera_maxima_sigue_y_no_borra_el_ajeno(tmp_path):
    """Contencion sostenida: entra SIN candado (documentado) y no toca el candado de otro."""
    ruta = tmp_path / "x.lock"
    ruta.write_text("12345")  # de otro, reciente
    t0 = time.monotonic()
    with candado.bloqueo(ruta, espera_maxima=0.3):
        pass
    assert 0.25 <= time.monotonic() - t0 < 2
    assert ruta.read_text() == "12345"


# B4 de N02 (arreglado): antes bloqueo() borraba el candado aunque ya fuera de otro.
def test_no_borra_un_candado_que_ya_no_es_suyo(tmp_path):
    ruta = tmp_path / "x.lock"
    with candado.bloqueo(ruta):
        # Simula: este bloque tardo mas que UMBRAL_HUERFANO y otro proceso robo el candado.
        ruta.unlink()
        ruta.write_text("424242")
    assert ruta.exists() and ruta.read_text() == "424242"
