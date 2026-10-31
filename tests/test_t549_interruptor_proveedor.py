# -*- coding: utf-8 -*-
"""T549: interruptor manual por proveedor. Apagado = ni se llama (enviar), ni sale como disponible, ni lo usa el
tribunal ("tribunal:x") ni el implementador (enfriado). No caduca. Sin red: enviar de verdad nunca se ejecuta."""
from __future__ import annotations

import proveedores as P
from nucleo import enfriamiento


def test_apagar_y_encender_no_caduca(monkeypatch):
    assert enfriamiento.apagado("groq") is None
    enfriamiento.apagar("groq", "terminos   nuevos\nraros")
    assert enfriamiento.apagado("groq") == "apagado a mano: terminos nuevos raros"
    assert enfriamiento.enfriado("groq").startswith("apagado a mano")
    assert enfriamiento.enfriado("tribunal:groq").startswith("apagado a mano")
    monkeypatch.setattr(enfriamiento.time, "time", lambda: 10 ** 12)   # dentro de muchos años sigue apagado
    assert enfriamiento.apagado("groq")
    enfriamiento.encender("groq")
    assert enfriamiento.apagado("groq") is None and enfriamiento.enfriado("tribunal:groq") is None
    enfriamiento.encender("groq")   # encender lo encendido no rompe


def test_todas_las_clases_respetan_el_interruptor(monkeypatch):
    for clase in P.CON_INTERRUPTOR:
        p = clase.__new__(clase)   # sin __init__: nada de red, Chrome ni claves; si llamara al enviar real, petaria
        enfriamiento.apagar(clase.nombre, "prueba")
        r = p.enviar("hola")
        assert r.estado == "NOT_AVAILABLE" and "apagado a mano" in r.detalle, clase.nombre
        assert p.disponible() is False, clase.nombre
        st = p.estado()
        assert st["disponible"] is False and st.get("apagado") is True and "prueba" in st["motivo"], clase.nombre
        enfriamiento.encender(clase.nombre)


def test_encendido_pasa_al_enviar_de_verdad(monkeypatch):
    llamadas = []

    class Falso:
        nombre = "falso"

        def enviar(self, tarea):
            llamadas.append(tarea)
            return P.Resultado("OK", texto="hecho")

        def disponible(self):
            return True

        def estado(self):
            return {"disponible": True, "motivo": ""}
    P._con_interruptor(Falso)
    f = Falso()
    assert f.enviar("x").ok and f.disponible() and llamadas == ["x"]
    enfriamiento.apagar("falso")
    assert not f.enviar("y").ok and llamadas == ["x"] and not f.disponible()


def test_la_cascada_de_revisores_salta_los_apagados(monkeypatch):
    from nucleo import trabajo
    monkeypatch.setattr(trabajo, "_web", lambda: True)
    for clase in P.CON_INTERRUPTOR:
        enfriamiento.apagar(clase.nombre)
    assert trabajo._revisores("qwen") == []   # apagados: disponible() corta antes de sondear nada
