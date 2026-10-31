# -*- coding: utf-8 -*-
"""T668 (F2): panel de la matriz de riesgo en el Centro. R1: lo que se hara salvo veto, con boton NO. R2: resumen,
diff resumido y Aprobar / Rechazar (maximo 10 esperando). R3: tareas que solo hacen Claude + Damian.
Todo a tmp_path (conftest de interfaz)."""
from __future__ import annotations

from datetime import datetime

from nucleo import aprobaciones as ap
from nucleo import riesgo
from nucleo import tareas as T

DIFF = ("diff --git a/nucleo/tareas.py b/nucleo/tareas.py\n--- a/nucleo/tareas.py\n+++ b/nucleo/tareas.py\n"
        "@@ -1 +1,2 @@\n+VALIDAR = True\n")


def _post(cliente, csrf, url, **datos):
    return cliente.post(url, data=datos, headers={"X-CSRF-Token": csrf})


def _tarea(id_, titulo, donde):
    return {"id": id_, "titulo": titulo, "detalle": f"QUE: {titulo}\nDONDE: {donde}", "etiquetas": []}


def test_centro_carga_el_panel_de_riesgo(cliente, csrf):
    assert 'hx-get="/centro/riesgo"' in cliente.get("/tecnico").text


def test_panel_vacio(cliente, csrf):
    r = cliente.get("/centro/riesgo")
    assert r.status_code == 200
    assert "Nada pendiente de veto" in r.text and "0 / 10" in r.text


def test_r1_con_boton_no_y_r2_con_resumen_y_diff(cliente, csrf, entorno):
    ahora = datetime.now().replace(microsecond=0)
    riesgo.autorizacion(_tarea("T900", "Test de la cola", "tests/test_cola.py"), ahora=ahora)
    riesgo.fusion(_tarea("T901", "Validar claves", "nucleo/tareas.py"), DIFF, "R2", resumen="Valida las claves.",
                  ahora=ahora)
    html = cliente.get("/centro/riesgo").text
    assert "T900" in html and "Test de la cola" in html and "salvo que digas NO" in html
    assert "T901" in html and "Valida las claves." in html and "VALIDAR = True" in html
    assert "1 / 10" in html


def test_no_veta_un_r1(cliente, csrf, entorno):
    a = riesgo.autorizacion(_tarea("T900", "Test de la cola", "tests/test_cola.py"))
    r = _post(cliente, csrf, "/riesgo/decidir", id=a["solicitud"], accion="denegar")
    assert r.status_code == 200 and "Vetada" in r.text
    s = ap.ver(a["solicitud"])
    assert s["estado"] == "denegada" and s["eventos"][-1]["quien"] == "damian"


def test_aprobar_un_r2_desde_la_web(cliente, csrf, entorno):
    t = _tarea("T901", "Validar claves", "nucleo/tareas.py")
    f = riesgo.fusion(t, DIFF, "R2")
    r = _post(cliente, csrf, "/riesgo/decidir", id=f["solicitud"], accion="aprobar")
    assert r.status_code == 200 and "Aprobada" in r.text
    assert riesgo.fusion(t, DIFF, "R2")["puede"]


def test_solo_decide_solicitudes_de_la_matriz(cliente, csrf, entorno):
    s = ap.solicitar("ejecutar comando", "winget --version", origen="mcp")
    r = _post(cliente, csrf, "/riesgo/decidir", id=s["id"], accion="aprobar")
    assert "no es de la matriz" in r.text
    assert ap.ver(s["id"])["estado"] == "pendiente"


def test_lista_las_tareas_r3(cliente, csrf, entorno):
    T.anadir("Endurecer permisos", etiquetas=["riesgo:R3"])
    assert "Endurecer permisos" in cliente.get("/centro/riesgo").text


def test_indicador_de_claude_cuenta_los_diffs_del_piloto(cliente, csrf, entorno, monkeypatch):
    from nucleo import implementador
    monkeypatch.setattr(implementador, "PILOTO", entorno / "memoria" / "implementador" / "piloto.json")
    assert 'data-claude-pendientes="0"' in cliente.get("/centro/claude").text
    implementador.registrar_puerta("T377", pasa=True)
    assert 'data-claude-pendientes="1"' in cliente.get("/centro/claude").text


# ------------------------------------------------------------ T890: Deshacer veto

def test_deshacer_veto_desde_el_centro(cliente, csrf, entorno):
    t = T.anadir("Tarea vetada sin querer", detalle="x")
    a = riesgo.autorizacion(_tarea(t["id"], "Test de la cola", "tests/test_cola.py"))
    assert "Deshacer veto" not in cliente.get("/centro/riesgo").text           # aun no esta vetada
    _post(cliente, csrf, "/riesgo/decidir", id=a["solicitud"], accion="denegar")
    html = cliente.get("/centro/riesgo").text
    assert "Deshacer veto" in html and t["id"] in html and "R1 que vetaste" in html
    r = _post(cliente, csrf, "/riesgo/deshacer", id=a["solicitud"])
    assert r.status_code == 200 and "Veto deshecho" in r.text
    s = ap.ver(a["solicitud"])
    assert s["estado"] == "pendiente" and s["eventos"][-1]["tipo"] == "veto_deshecho"
    assert "Deshacer veto" not in cliente.get("/centro/riesgo").text


def test_deshacer_veto_rechaza_lo_que_no_se_puede(cliente, csrf, entorno):
    f = riesgo.fusion(_tarea("T901", "Validar claves", "nucleo/tareas.py"), DIFF, "R2")
    r = _post(cliente, csrf, "/riesgo/deshacer", id=f["solicitud"])        # R2: no es un veto R1
    assert "no es un veto R1" in r.text and ap.ver(f["solicitud"])["estado"] == "pendiente"
    r = _post(cliente, csrf, "/riesgo/deshacer", id="A9999")               # no existe: error en el panel, sin romper
    assert r.status_code == 200 and "A9999" in r.text and "Veto deshecho" not in r.text


def test_deshacer_veto_exige_csrf(cliente, csrf, entorno):
    a = riesgo.autorizacion(_tarea("T900", "Test de la cola", "tests/test_cola.py"))
    ap.denegar(a["solicitud"])
    r = cliente.post("/riesgo/deshacer", data={"id": a["solicitud"]})      # sin cabecera CSRF
    assert r.status_code in (400, 403) and ap.ver(a["solicitud"])["estado"] == "denegada"
