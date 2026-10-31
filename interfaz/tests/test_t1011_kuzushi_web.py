# -*- coding: utf-8 -*-
"""T1011 fase 1 (apartado 4): resumen semanal de Kuzushi en el Centro y pagina /kuzushi con cada caso (solo lee).
El registro de Kuzushi va a tmp_path (conftest raiz)."""
from __future__ import annotations

from datetime import datetime, timedelta

from nucleo import kuzushi as K


def _sembrar(monkeypatch):
    hs = [K.hallazgo("prueba", "t", "a", "T844 conserva un cierre viejo", {"tarea": "T844"}, gravedad="media"),
          K.hallazgo("prueba", "t", "b", "Aviso repetido", {"veces": 52}, gravedad="baja")]
    monkeypatch.setattr(K, "OBSERVADORES", (("prueba", lambda f: [dict(h) for h in hs]),))
    K.observar(fuentes=K.Fuentes(ahora=datetime.now() - timedelta(days=1), tareas=[]))
    K.calibrar("K0002", "no_util", "ya lo cubre el aviso del Centro")


def test_el_centro_pinta_el_resumen_semanal_con_enlace_a_cada_caso(cliente, csrf, monkeypatch):
    assert "todavía no ha pasado" in cliente.get("/centro/kuzushi").text
    _sembrar(monkeypatch)
    html = cliente.get("/centro/kuzushi").text
    assert "vio <strong>2</strong>" in html and "se descartaron <strong>1</strong>" in html
    assert 'href="/kuzushi#K0002"' in html and "ya lo cubre el aviso del Centro" in html
    assert "Semana de prueba" in html
    centro = cliente.get("/").text                    # va con la pagina: no es un panel mas del Centro v2
    assert "Kuzushi esta semana" in centro and 'href="/kuzushi#K0002"' in centro
    assert 'hx-get="/centro/kuzushi"' not in centro


def test_si_kuzushi_no_se_puede_leer_el_centro_sale_igual(cliente, csrf, monkeypatch):
    def roto():
        raise OSError("registro ilegible")
    monkeypatch.setattr(K, "resumen", roto)
    r = cliente.get("/")
    assert r.status_code == 200 and "No se ha podido leer el resumen de Kuzushi" in r.text


def test_la_pagina_de_casos_ensena_la_evidencia_y_el_ancla(cliente, csrf, monkeypatch):
    _sembrar(monkeypatch)
    html = cliente.get("/kuzushi").text
    assert 'id="K0001"' in html and "T844 conserva un cierre viejo" in html and "en la cola de Claude" in html
    assert "no útil" in html and '"veces": 52' in html


def test_kuzushi_requiere_sesion(cliente):
    assert cliente.get("/centro/kuzushi").status_code == 401
    assert cliente.get("/kuzushi").status_code in (401, 303, 307)
