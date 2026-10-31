# -*- coding: utf-8 -*-
"""T160: registro de evidencias por tarea y cierre verify-on-stop. Todo en tmp_path (conftest)."""
from __future__ import annotations

import json

import pytest

from nucleo import evidencias as E
from nucleo import tareas as T

SALIDA_PYTEST = "....\n" * 800 + "==== 13 passed in 0.05s ===="


def _hecha(titulo="x"):
    t = T.anadir(titulo)
    T.completar(t["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    return t["id"]


# ------------------------------------------------------------------ evaluar
@pytest.mark.parametrize("texto", ["", "   ", None, "ok", "OK.", "probada", "Funciona", "todo ok", "si", "corto"])
def test_ticks_y_vacios_no_son_evidencia(texto):
    assert E.evaluar(texto)[0] is False


def test_evidencia_con_que_se_probo_y_que_salio_vale():
    assert E.evaluar("pytest interfaz/tests -q -> 281 passed") == (True, "")


# --------------------------------------------------------------- registrar
def test_registro_va_junto_a_tareas_json_y_no_a_memoria_real():
    assert E.almacen().parent == T.ALMACEN.parent and "memoria" in str(E.almacen())
    assert E.almacen() != T.RAIZ / "memoria" / "evidencias.jsonl"


def test_registrar_guarda_una_linea_por_evidencia_y_se_lee_por_tarea():
    a, b = T.anadir("a")["id"], T.anadir("b")["id"]
    E.registrar(a, "tests del modulo en verde", tipo="test", comando="pytest -q", salida="3 passed")
    E.registrar(b, "archivo generado y abierto a mano", tipo="archivo")
    E.registrar(a, "segunda pasada, un test en rojo", tipo="test", resultado="fallo")
    lineas = E.almacen().read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 3 and all(json.loads(l)["tarea"] in (a, b) for l in lineas)
    assert [e["resultado"] for e in E.de_tarea(a)] == ["ok", "fallo"]
    assert len(E.validas(a)) == 1  # un fallo se registra, pero no cuenta para cerrar


def test_registrar_rechaza_tick_tipo_raro_y_tarea_inexistente():
    t = T.anadir("x")["id"]
    with pytest.raises(E.EvidenciaInvalida):
        E.registrar(t, "ok")
    with pytest.raises(ValueError):
        E.registrar(t, "tests en verde de verdad", tipo="intuicion")
    with pytest.raises(ValueError):
        E.registrar("T999", "tests en verde de verdad")
    assert E.de_tarea(t) == []


def test_la_salida_se_recorta_por_el_final_y_se_ocultan_secretos():
    t = T.anadir("x")["id"]
    clave = "sk-" + "A1b2C3d4" * 4
    e = E.registrar(t, f"curl con clave={clave} respondio 200", tipo="comando",
                    comando=f"curl -H 'Authorization: Bearer {clave}' http://x", salida=SALIDA_PYTEST)
    crudo = E.almacen().read_text(encoding="utf-8")
    assert clave not in crudo and "«oculto»" in crudo
    assert e["recortada"] is True and len(e["salida"]) <= E.MAX_SALIDA and e["salida"].endswith("0.05s ====")


def test_una_linea_rota_no_tumba_la_lectura():
    t = T.anadir("x")["id"]
    E.registrar(t, "tests del modulo en verde")
    with E.almacen().open("a", encoding="utf-8") as f:
        f.write("{esto no es json\n")
    assert len(E.de_tarea(t)) == 1


# ------------------------------------------------------ tareas.verificar()
def test_verificar_sin_evidencia_ya_no_marca_testeado():
    t = _hecha()
    r = T.verificar(t)
    assert r["testeado"] is False and T.estado_real(T.buscar(t)) == "HECHO SIN TESTEAR"
    assert E.de_tarea(t) == []


def test_verificar_con_evidencia_la_registra_y_marca():
    t = _hecha()
    r = T.verificar(t, "pytest interfaz/ 102 passed")
    assert r["testeado"] is True and E.validas(t)[0]["detalle"] == "pytest interfaz/ 102 passed"
    assert r["notas"][-1]["texto"] == "[verificado] pytest interfaz/ 102 passed"


def test_por_defecto_verificar_rechaza_el_tick():
    t = _hecha()
    assert E.VERIFICAR_ESTRICTO is True
    assert T.verificar(t, "probada")["testeado"] is False and E.de_tarea(t) == []


def test_modo_no_estricto_acepta_el_tick_pero_queda_debil(monkeypatch):
    monkeypatch.setattr(E, "VERIFICAR_ESTRICTO", False)
    t = _hecha()
    assert T.verificar(t, "probada")["testeado"] is True
    assert E.de_tarea(t)[0]["debil"] is True and E.validas(t) == []


def test_web_rechaza_un_tick_largo_y_no_marca(cliente, csrf):
    t = _hecha()
    r = cliente.post(f"/tareas/{t}/verificar", data={"evidencia": "funciona bien"}, headers={"X-CSRF-Token": csrf})
    assert r.headers["hx-retarget"] == "#error-verificar" and "tick" in r.text
    assert T.buscar(t)["testeado"] is False


def test_verificar_tarea_inexistente():
    assert T.verificar("T999", "pytest 3 passed de verdad") is None


def test_cli_verificar_sin_evidencia_avisa_y_da_codigo_2(capsys):
    t = _hecha()
    assert T._cli(["verificar", t]) == 2
    assert "NO verificada" in capsys.readouterr().out


# ------------------------------------------------------ verify-on-stop
def test_cerrar_con_evidencia_queda_hecho_y_testeado():
    t = T.anadir("x")["id"]
    r = E.cerrar(t, "terminada", evidencia={"detalle": "suite en verde", "tipo": "test",
                                           "comando": "pytest -q", "salida": SALIDA_PYTEST})
    assert r == {"tarea": t, "estado_real": "HECHO Y TESTEADO", "evidencias": 1, "pedida": False, "motivo": ""}
    assert "13 passed" in T.buscar(t)["notas"][-1]["texto"]


def test_cerrar_sin_evidencia_la_pide_una_vez_y_si_llega_cierra_testeada():
    t = T.anadir("x")["id"]
    pedidas = []

    def pedir(tarea, motivo):
        pedidas.append((tarea["id"], motivo))
        return "pytest interfaz/tests -q -> 281 passed"

    r = E.cerrar(t, pedir=pedir)
    assert pedidas == [(t, "sin evidencia")]
    assert r["estado_real"] == "HECHO Y TESTEADO" and r["pedida"] is True


def test_cerrar_si_la_evidencia_pedida_no_llega_queda_hecho_sin_testear():
    t = T.anadir("x")["id"]
    llamadas = []
    r = E.cerrar(t, evidencia="ok", pedir=lambda tarea, motivo: llamadas.append(motivo) or "funciona")
    assert len(llamadas) == 1 and "tick" in llamadas[0]  # se pide UNA vez, con el motivo del rechazo
    assert r["estado_real"] == "HECHO SIN TESTEAR" and r["evidencias"] == 0 and "tick" in r["motivo"]
    nota = T.buscar(t)["notas"][-1]["texto"]
    assert nota.startswith("[verify-on-stop]") and "se pidio una vez mas" in nota


def test_cerrar_sin_pedir_ni_evidencia_no_se_marca():
    t = T.anadir("x")["id"]
    r = E.cerrar(t)
    assert r["estado_real"] == "HECHO SIN TESTEAR" and r["pedida"] is False


def test_una_evidencia_de_antes_de_reabrir_no_vale_para_el_nuevo_cierre():
    t = T.anadir("x")["id"]
    E.cerrar(t, evidencia="pytest -q -> 5 passed (primera vez)")
    T.actualizar(t, estado="pendiente", testeado=False)  # se reabre (en el mismo segundo, incluso)
    r = E.cerrar(t)
    assert r["estado_real"] == "HECHO SIN TESTEAR" and len(E.validas(t)) == 1


def test_una_evidencia_en_rojo_no_cierra_como_testeada():
    t = T.anadir("x")["id"]
    r = E.cerrar(t, evidencia={"detalle": "pytest -q -> 2 failed", "tipo": "test", "resultado": "fallo"})
    assert r["estado_real"] == "HECHO SIN TESTEAR"


def test_cerrar_tarea_inexistente():
    with pytest.raises(ValueError):
        E.cerrar("T999")
