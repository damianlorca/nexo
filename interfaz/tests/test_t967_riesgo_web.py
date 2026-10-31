# -*- coding: utf-8 -*-
"""T967: boton Aceptar de las R1 y dictamenes del tribunal en el panel de riesgo. Todo a tmp_path (conftest)."""
from __future__ import annotations

from nucleo import aprobaciones as ap
from nucleo import riesgo

DIFF = ("diff --git a/nucleo/tareas.py b/nucleo/tareas.py\n--- a/nucleo/tareas.py\n+++ b/nucleo/tareas.py\n"
        "@@ -1 +1,2 @@\n+VALIDAR = True\n")


def _post(cliente, csrf, url, **datos):
    return cliente.post(url, data=datos, headers={"X-CSRF-Token": csrf})


def _tarea(id_, titulo, donde):
    return {"id": id_, "titulo": titulo, "detalle": f"QUE: {titulo}\nDONDE: {donde}", "etiquetas": []}


def test_aceptar_un_r1_la_aprueba_al_momento(cliente, csrf, entorno):
    t = _tarea("T900", "Test de la cola", "tests/test_cola.py")
    a = riesgo.autorizacion(t)
    assert "Aceptar" in cliente.get("/centro/riesgo").text
    r = _post(cliente, csrf, "/riesgo/decidir", id=a["solicitud"], accion="aceptar")
    assert r.status_code == 200 and "Aceptada" in r.text
    s = ap.ver(a["solicitud"])
    assert s["estado"] == "aprobada" and s["decidida_por"] == "damian"
    assert riesgo.autorizacion(t)["puede"]


def test_aceptar_no_vale_para_un_r2(cliente, csrf, entorno):
    f = riesgo.fusion(_tarea("T901", "Validar claves", "nucleo/tareas.py"), DIFF, "R2")
    r = _post(cliente, csrf, "/riesgo/decidir", id=f["solicitud"], accion="aceptar")
    assert "acción desconocida" in r.text and ap.ver(f["solicitud"])["estado"] == "pendiente"


def test_la_bandeja_ensena_los_dictamenes_del_tribunal(cliente, csrf, entorno):
    a = riesgo.autorizacion(_tarea("T900", "Test de la cola", "tests/test_cola.py"))
    assert "El tribunal la está juzgando" in cliente.get("/centro/riesgo").text
    ap.registrar_tribunal(a["solicitud"], "bandeja",
                          [{"id": "groq:x", "voto": "VETAR", "motivo": "mal definida"},
                           {"id": "nvidia:y", "voto": "APROBAR", "motivo": "util"}], "tribunal dividido")
    html = cliente.get("/centro/riesgo").text
    assert "tribunal dividido" in html and "mal definida" in html and "El tribunal la está juzgando" not in html
