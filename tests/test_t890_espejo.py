# -*- coding: utf-8 -*-
"""T890 (10): el planificador publica el espejo de GitHub una vez al dia desde las 03:00, nunca con PARADA, y avisa
(1 al dia) si falla. Sin red ni git: el script es un doble (subprocess simulado)."""
from __future__ import annotations

import subprocess
from datetime import datetime
from types import SimpleNamespace

import pytest

from nucleo import avisos, espejo, parada
from nucleo import planificador as P


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(espejo, "CARPETA", tmp_path / "espejo")
    monkeypatch.setattr(espejo, "LANZADOR", None)
    monkeypatch.setattr(avisos, "CARPETA", tmp_path / "avisos")
    monkeypatch.setattr(parada, "activa", lambda: False)
    return tmp_path


def _dia(h, m=0, d=17):
    return datetime(2026, 10, d, h, m)


def _avisos():
    return sorted(avisos.CARPETA.glob("aviso_*.json"))


class Corredor:
    def __init__(self, resultado=(0, "Publicado abc en origin/espejo")):
        self.resultado, self.llamadas = resultado, 0

    def __call__(self):
        self.llamadas += 1
        if isinstance(self.resultado, Exception):
            raise self.resultado
        return self.resultado


def test_antes_de_las_3_no_hace_nada_y_a_partir_de_las_3_publica_una_vez_al_dia():
    c = Corredor()
    assert espejo.repaso_si_toca(_dia(2, 59), c, en_hilo=False) is None and c.llamadas == 0
    assert espejo.repaso_si_toca(_dia(3, 0), c, en_hilo=False) == "espejo: codigo 0" and c.llamadas == 1
    for h in (3, 4, 9, 23):                                    # el resto del dia: ni una vez mas
        assert espejo.repaso_si_toca(_dia(h, 30), c, en_hilo=False) is None
    assert c.llamadas == 1
    assert espejo.repaso_si_toca(_dia(3, 5, d=18), c, en_hilo=False) == "espejo: codigo 0" and c.llamadas == 2


def test_primera_vuelta_despues_de_las_3_aunque_el_pc_estuviera_apagado():
    c = Corredor()
    assert espejo.repaso_si_toca(_dia(11, 40), c, en_hilo=False) == "espejo: codigo 0" and c.llamadas == 1
    assert espejo.ultimo()["dia"] == "2026-10-17" and espejo.ultimo()["codigo"] == 0


def test_con_la_parada_puesta_no_publica_ni_marca_el_dia_y_sale_cuando_se_quita(monkeypatch):
    c = Corredor()
    monkeypatch.setattr(parada, "activa", lambda: True)
    assert espejo.repaso_si_toca(_dia(3, 0), c, en_hilo=False) is None and c.llamadas == 0
    assert espejo.ultimo() == {}                               # el dia no se gasto
    monkeypatch.setattr(parada, "activa", lambda: False)
    assert espejo.repaso_si_toca(_dia(7, 0), c, en_hilo=False) == "espejo: codigo 0" and c.llamadas == 1


def test_si_el_script_aborta_o_falla_un_aviso_y_solo_uno_al_dia():
    c = Corredor((2, "ABORTADO: el remoto tiene cambios que no son un espejo (Merge pull request)"))
    assert espejo.repaso_si_toca(_dia(3, 0), c, en_hilo=False) == "espejo: codigo 2"
    a = _avisos()
    assert len(a) == 1
    texto = a[0].read_text(encoding="utf-8")
    assert "espejo de GitHub no se ha publicado" in texto and "ABORTADO" in texto and "traerlos a local" in texto
    espejo.repaso_si_toca(_dia(4, 0), c, en_hilo=False)        # mas vueltas el mismo dia: ni otro intento ni otro aviso
    assert c.llamadas == 1 and len(_avisos()) == 1
    espejo._avisar("2026-10-17", "otra vez", "x")               # aunque algo lo pidiera: la clave del dia ya salio
    assert len(_avisos()) == 1


@pytest.mark.parametrize("fallo", [subprocess.TimeoutExpired("publicar_nube", 900), OSError("sin python"),
                                   RuntimeError("git roto")])
def test_si_el_proceso_no_termina_o_revienta_tambien_avisa_y_no_tira_el_tick(fallo):
    assert espejo.repaso_si_toca(_dia(3, 0), Corredor(fallo), en_hilo=False) == "espejo: codigo -1"
    assert len(_avisos()) == 1 and espejo.ultimo()["codigo"] == -1


def test_sin_cambios_no_avisa():
    espejo.repaso_si_toca(_dia(3, 0), Corredor((0, "Sin cambios desde el ultimo espejo.")), en_hilo=False)
    assert _avisos() == []


def test_el_script_real_se_lanza_con_subprocess_sin_tocar_nada(monkeypatch):
    """_ejecutar corre publicar_nube.py con el interprete del venv; aqui subprocess.run es un doble."""
    visto = {}

    def run(cmd, **k):
        visto.update(cmd=cmd, **k)
        return SimpleNamespace(returncode=0, stdout="Publicado 123 en origin/espejo\n", stderr="")
    monkeypatch.setattr(espejo.subprocess, "run", run)
    assert espejo.repaso_si_toca(_dia(3, 0), en_hilo=False) == "espejo: codigo 0"
    assert visto["cmd"][1].endswith("publicar_nube.py") and visto["cwd"] == espejo.REPO
    assert visto["timeout"] == espejo.TIMEOUT_S and visto["capture_output"] is True
    assert "Publicado" in espejo.ultimo()["salida"]


def test_en_hilo_el_tick_no_espera_al_script(monkeypatch):
    import threading
    libre, termino = threading.Event(), threading.Event()

    def lento():
        libre.wait(5)
        termino.set()
        return 0, "ok"
    assert espejo.repaso_si_toca(_dia(3, 0), lento) == "espejo lanzado"      # vuelve sin esperar
    assert not termino.is_set() and espejo.ultimo()["salida"] == "en curso"
    libre.set()
    assert termino.wait(5)


def test_el_tick_del_planificador_llama_al_espejo_y_nunca_se_rompe_por_el(monkeypatch):
    llamadas = []
    monkeypatch.setattr(espejo, "repaso_si_toca", lambda ahora: llamadas.append(ahora) or "espejo lanzado")
    r = P.tick(_dia(3, 10), lanzar=lambda e: 1)
    assert llamadas and r["espejo"] == "espejo lanzado"
    monkeypatch.setattr(espejo, "repaso_si_toca", lambda ahora: 1 / 0)
    assert P.tick(_dia(3, 11), lanzar=lambda e: 1)["espejo"] is None
