# -*- coding: utf-8 -*-
"""T195: la ruta de Ajustes que sube, baja y restablece el orden de proveedores."""
from __future__ import annotations

from nucleo import orden_proveedores as O


def test_ruta_de_ajustes_sube_baja_y_restablece(cliente, csrf):
    def post(**d):
        return cliente.post("/ajustes/orden-proveedores", data=d, headers={"X-CSRF-Token": csrf})
    assert "chatgpt" in cliente.get("/ajustes").text
    r = post(nombre="groq", accion="subir")
    assert r.status_code == 200 and "groq sube un puesto" in r.text
    assert O.leer().index("groq") == O.ORDEN_BASE.index("groq") - 1
    assert "Orden elegido por ti" in r.text
    assert "Proveedor desconocido" in post(nombre="x", accion="subir").text
    assert "Acción desconocida" in post(nombre="groq", accion="saltar").text
    assert O.leer() and "restablecido" in post(accion="restablecer").text and O.leer() == []
