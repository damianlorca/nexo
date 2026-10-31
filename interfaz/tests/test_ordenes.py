# -*- coding: utf-8 -*-
"""Incremento 5: ordenes (instantanea/bloque en hilo, resultado por SSE, bloqueadas con PARADA)."""
from __future__ import annotations

import threading
import time

import pytest

from nucleo import ordenes, parada, tareas, trabajo


class ProcesarFalso:
    """Sustituto de nucleo.ordenes.procesar: apunta las llamadas y puede esperar o fallar."""

    def __init__(self, resultado=None, espera=0.0, error=None):
        self.resultado = resultado or {"estado": "PARA_DAMIAN", "tarea": "T001", "categoria": "personal",
                                       "proveedor": "claude", "respuesta": "📌 T001 apuntada como tuya (personal)."}
        self.espera = espera
        self.error = error
        self.llamadas = []
        self.a_la_vez = 0
        self.max_a_la_vez = 0
        self.soltar = threading.Event()
        self.soltar.set()
        self._candado = threading.Lock()

    def __call__(self, texto, canal="telegram", trabajar=True):
        with self._candado:
            self.llamadas.append({"texto": texto, "canal": canal, "trabajar": trabajar})
            self.a_la_vez += 1
            self.max_a_la_vez = max(self.max_a_la_vez, self.a_la_vez)
        try:
            self.soltar.wait(5)
            time.sleep(self.espera)
            if self.error:
                raise self.error
            return dict(self.resultado)
        finally:
            with self._candado:
                self.a_la_vez -= 1


@pytest.fixture
def procesar(monkeypatch):
    falso = ProcesarFalso()
    monkeypatch.setattr(ordenes, "procesar", falso)
    return falso


def _orden(cliente, csrf, texto="investiga qué es X", modo="instantanea"):
    return cliente.post("/orden", data={"texto": texto, "modo": modo}, headers={"X-CSRF-Token": csrf})


def _esperar(app, id_orden, estados=("hecha", "error", "cancelada"), limite=5.0):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        o = app.state.trabajador.orden(id_orden)
        if o and o["estado"] in estados:
            return o
        time.sleep(0.02)
    raise AssertionError(f"la orden {id_orden} no llego a {estados}: {app.state.trabajador.orden(id_orden)}")


# ------------------------------------------------------------------ pagina
def test_pagina_ordenes_formulario_y_secciones(cliente, csrf):
    r = cliente.get("/ordenes")
    assert r.status_code == 200
    assert 'hx-post="/orden"' in r.text and 'value="instantanea"' in r.text and 'value="bloque"' in r.text
    assert "Aún no has dado órdenes" in r.text and 'hx-get="/ordenes/historial"' in r.text


# ------------------------------------------------------------- instantanea
def test_instantanea_responde_al_momento_y_el_resultado_llega_por_el_bus(cliente, csrf, app, procesar):
    procesar.espera = 0.8  # "tarda minutos": la peticion NO puede esperarla
    t0 = time.monotonic()
    r = _orden(cliente, csrf)
    assert time.monotonic() - t0 < 0.5
    assert r.status_code == 200 and 'id="orden-W1"' in r.text and "En cola" in r.text
    assert "Orden W1 recibida (ahora): en cola." in r.text
    o = _esperar(app, "W1")
    assert o["estado"] == "hecha"
    assert procesar.llamadas == [{"texto": "investiga qué es X", "canal": "web", "trabajar": True}]
    estados = [e.datos["estado"] for e in app.state.bus.despues(0) if e.tipo == "orden"]
    assert estados == ["en_cola", "en_curso", "hecha"]


def test_tarjeta_terminada_con_borrador_y_aviso(cliente, csrf, app, procesar):
    procesar.resultado = {"estado": "BORRADOR", "tarea": "T007", "categoria": "investigacion",
                          "proveedor": "gemini_api", "archivo": "memoria/borradores/T007_20260925_0100.md",
                          "autor": "gemini_api", "revisor": "groq", "veredicto": "APROBADO", "respuesta": "✅ ..."}
    _orden(cliente, csrf)
    _esperar(app, "W1")
    r = cliente.get("/ordenes/W1", params={"anunciar": 1}).text
    assert "Borrador hecho" in r and "T007" in r and "groq" in r and "APROBADO" in r
    assert 'href="/borrador?f=T007_20260925_0100.md"' in r
    assert 'hx-swap-oob="innerHTML:#avisos"' in r and "Orden W1 terminada" in r
    assert "#avisos" not in cliente.get("/ordenes/W1").text  # sin anunciar, no toca los avisos


# ------------------------------------------------------------------ bloque
def test_bloque_solo_triaja_con_trabajar_false(cliente, csrf, app, procesar):
    procesar.resultado = {"estado": "ENCOLADA", "tarea": "T002", "categoria": "investigacion",
                          "proveedor": "gemini", "respuesta": "📥 T002 (investigacion) apuntada: la trabajo en un turno."}
    r = _orden(cliente, csrf, modo="bloque")
    assert "para más tarde" in r.text
    _esperar(app, "W1")
    assert procesar.llamadas[0]["trabajar"] is False
    t = cliente.get("/ordenes/W1").text
    assert "la trabajará NEXO en un turno" in t and "necesita a Claude" not in t


def test_bloque_de_codigo_si_queda_para_claude(cliente, csrf, app, procesar):
    procesar.resultado = {"estado": "ESCALADO", "tarea": "T003", "categoria": "codigo", "proveedor": "claude",
                          "respuesta": "🧠 T003 (codigo) necesita a Claude"}
    _orden(cliente, csrf, modo="bloque")
    _esperar(app, "W1")
    assert "Encolada para Claude" in cliente.get("/ordenes/W1").text


# ------------------------------------------------------------------ PARADA
def test_con_parada_se_rechaza_sin_llamar_al_core_y_la_web_sigue_viva(cliente, csrf, app, procesar):
    parada.activar("revision", "damian")
    r = _orden(cliente, csrf)
    assert r.status_code == 200
    assert r.headers["hx-retarget"] == "#error-orden" and "PARADA de emergencia activa (revision)" in r.text
    assert app.state.trabajador.recientes() == [] and procesar.llamadas == []
    pagina = cliente.get("/ordenes").text
    assert "Órdenes bloqueadas" in pagina and "<fieldset disabled>" in pagina
    assert cliente.get("/").status_code == 200
    # Seguir sigue funcionando y las ordenes vuelven.
    assert cliente.post("/seguir", data={"confirmacion": "si"}, headers={"X-CSRF-Token": csrf}).status_code == 200
    assert 'data-activa="0"' in cliente.get("/ordenes/bloqueo").text
    assert 'id="orden-W1"' in _orden(cliente, csrf).text


def test_orden_en_cola_no_arranca_si_se_activa_la_parada(cliente, csrf, app, procesar):
    procesar.soltar.clear()          # la primera orden se queda "trabajando"
    _orden(cliente, csrf, texto="primera orden")
    _esperar(app, "W1", ("en_curso",))
    _orden(cliente, csrf, texto="segunda orden")
    parada.activar("a mitad", "damian")
    procesar.soltar.set()
    o2 = _esperar(app, "W2")
    assert o2["estado"] == "cancelada" and "se activó la PARADA" in o2["error"]
    assert [x["texto"] for x in procesar.llamadas] == ["primera orden"]


# ---------------------------------------------------------- serie y errores
def test_ordenes_de_una_en_una(cliente, csrf, app, procesar):
    procesar.espera = 0.1
    for i in range(3):
        _orden(cliente, csrf, texto=f"orden numero {i}")
    for i in range(1, 4):
        _esperar(app, f"W{i}")
    assert procesar.max_a_la_vez == 1 and len(procesar.llamadas) == 3


def test_fallo_del_core_queda_como_error_sin_filtrar_el_mensaje(cliente, csrf, app, procesar):
    procesar.error = RuntimeError("token=SECRETO en la traza")
    _orden(cliente, csrf)
    o = _esperar(app, "W1")
    assert o["estado"] == "error" and "RuntimeError" in o["error"] and "SECRETO" not in o["error"]
    assert "SECRETO" not in cliente.get("/ordenes/W1").text


@pytest.mark.parametrize("texto,modo", [("abc", "instantanea"), ("x" * 4001, "instantanea"), ("orden valida", "otro")])
def test_texto_o_modo_invalidos_se_rechazan(cliente, csrf, app, procesar, texto, modo):
    r = _orden(cliente, csrf, texto=texto, modo=modo)
    assert r.headers.get("hx-retarget") == "#error-orden"
    assert app.state.trabajador.recientes() == []


def test_orden_sin_csrf_da_403(cliente, csrf, app, procesar):
    assert cliente.post("/orden", data={"texto": "investiga algo"}).status_code == 403
    assert app.state.trabajador.recientes() == []


def test_tarjeta_desconocida_devuelve_vacio(cliente, csrf):
    r = cliente.get("/ordenes/W999")
    assert r.status_code == 200 and r.text == ""


# ------------------------------------------------------ historial y borrador
def test_historial_muestra_ordenes_de_todas_las_vias_con_borrador(cliente, csrf):
    t = tareas.anadir("resume el informe", etiquetas=["cat:resumen", "prov:qwen", "origen:orden_telegram",
                                                       "borrador:revisar_claude"])
    tareas.anadir("no es una orden")
    (trabajo.BORRADORES / f"{t['id']}_20260925_0100.md").write_text("# hola", encoding="utf-8")
    r = cliente.get("/ordenes/historial").text
    assert "resume el informe" in r and "telegram" in r and "BORRADOR (revisar Claude)" in r
    assert f'href="/borrador?f={t["id"]}_20260925_0100.md"' in r
    assert "no es una orden" not in r


def test_historial_vacio(cliente, csrf):
    assert "Aún no hay órdenes registradas" in cliente.get("/ordenes/historial").text


def test_borrador_se_ve_escapado(cliente, csrf):
    (trabajo.BORRADORES / "T001_x.md").write_text("<script>alert(1)</script> texto", encoding="utf-8")
    r = cliente.get("/borrador", params={"f": "T001_x.md"})
    assert r.status_code == 200 and "&lt;script&gt;" in r.text and "<script>alert" not in r.text


@pytest.mark.parametrize("nombre", ["../tareas.json", "..\\tareas.md", "C:\\Windows\\win.ini", "noexiste.md", "", "sub/x.md"])
def test_borrador_no_sale_de_la_carpeta(cliente, csrf, nombre, entorno):
    (entorno / "memoria" / "tareas.md").write_text("secreto", encoding="utf-8")
    r = cliente.get("/borrador", params={"f": nombre})
    assert r.status_code == 404 and "secreto" not in r.text


def test_bloqueo_solo_repinta_el_aviso_no_el_formulario(cliente, csrf):
    pagina = cliente.get("/ordenes").text
    assert 'hx-get="/ordenes/bloqueo"' in pagina and 'id="formulario-orden" hx-get' not in pagina
    parada.activar("x", "damian")
    r = cliente.get("/ordenes/bloqueo").text
    assert 'data-activa="1"' in r and "Órdenes bloqueadas" in r and "<textarea" not in r


def test_no_se_olvidan_ordenes_en_cola_aunque_pasen_de_50(cliente, csrf, app, procesar):
    import interfaz.trabajador as trab
    procesar.soltar.clear()                      # la primera se queda trabajando; el resto, en cola
    for i in range(trab.MAX_RECORDADAS + 5):
        _orden(cliente, csrf, texto=f"orden numero {i}")
    ids = {o["id"] for o in app.state.trabajador.recientes()}
    assert len(ids) == trab.MAX_RECORDADAS + 5   # ninguna terminada: no se puede olvidar ninguna
    procesar.soltar.set()
    _esperar(app, f"W{trab.MAX_RECORDADAS + 5}", limite=20)
    assert len(procesar.llamadas) == trab.MAX_RECORDADAS + 5
    assert len(app.state.trabajador.recientes()) == trab.MAX_RECORDADAS  # al terminar, recorta las viejas
