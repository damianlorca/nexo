# -*- coding: utf-8 -*-
"""T549: Apagar / Encender cada proveedor desde la pagina Proveedores (POST con CSRF)."""
from __future__ import annotations

from interfaz import lecturas
from nucleo import enfriamiento


def _post(cliente, csrf, **datos):
    return cliente.post("/proveedores/interruptor", data=datos, headers={"X-CSRF-Token": csrf})


def test_apagar_y_encender_desde_la_web(cliente, csrf):
    panel = cliente.get("/proveedores/salud").text
    assert 'hx-post="/proveedores/interruptor"' in panel and "Apagar" in panel
    r = _post(cliente, csrf, nombre="falso", accion="apagar", motivo="términos")
    assert r.status_code == 200 and "Proveedor desconocido" in r.text   # solo los de proveedores.CON_INTERRUPTOR
    r = _post(cliente, csrf, nombre="groq", accion="apagar", motivo="términos nuevos")
    assert "groq apagado" in r.text and enfriamiento.apagado("groq") == "apagado a mano: términos nuevos"
    r = _post(cliente, csrf, nombre="groq", accion="encender")
    assert "groq encendido" in r.text and enfriamiento.apagado("groq") is None


def test_sin_csrf_no_cambia_nada(cliente, csrf):
    assert cliente.post("/proveedores/interruptor", data={"nombre": "groq", "accion": "apagar"}).status_code == 403
    assert enfriamiento.apagado("groq") is None


def test_la_salud_lo_marca_como_apagado():
    class Prov:
        nombre = "groq"

        def estado(self):
            return {"disponible": False, "motivo": "Apagado a mano: x", "apagado": True}
    s = lecturas._salud(Prov())
    assert s["salud"] == "apagado" and s["enfriamiento"] == ""
