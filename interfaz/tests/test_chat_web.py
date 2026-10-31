# -*- coding: utf-8 -*-
"""T290: chat de la tarea en la web (ficha). Dobles: sin Ollama ni APIs de verdad."""
from __future__ import annotations

import pytest

from nucleo import aprobaciones as ap
from nucleo import chat_tarea as C
from nucleo import tareas as T
from proveedores import Resultado


class Prov:
    def __init__(self, nombre, texto="Falta el paso 2."):
        self.nombre, self.texto, self.prompts, self.ultimo_modelo = nombre, texto, [], ""

    def disponible(self):
        return True

    def enviar(self, prompt):
        self.prompts.append(prompt)
        return Resultado("OK", texto=self.texto)


@pytest.fixture(autouse=True)
def sin_modelos(monkeypatch):
    nvidia = Prov("nvidia")
    monkeypatch.setattr(C, "_qwen_interpretar", lambda p: None)
    monkeypatch.setattr(C, "redactar_resumen", lambda t: "Resumen.")
    monkeypatch.setattr(C, "proveedores_dudas", lambda: [nvidia])
    monkeypatch.setattr(C, "_qwen_proveedor", lambda: Prov("qwen", "local"))
    return nvidia


def _post(cliente, csrf, url, **datos):
    return cliente.post(url, data=datos, headers={"X-CSRF-Token": csrf})


def _esperar(app):
    app.state.chat._pool.submit(lambda: None).result(timeout=10)


def test_ficha_trae_el_chat(cliente, csrf):
    t = T.anadir("Web", detalle="x")
    r = cliente.get(f"/tareas/{t['id']}")
    assert r.status_code == 200
    assert 'id="chat-tarea"' in r.text and f'hx-get="/tareas/{t["id"]}/chat"' in r.text
    assert "Escalar" in r.text and "Súbele la prioridad" in r.text
    r = cliente.get(f"/tareas/{t['id']}/chat")
    assert "Todavía no hay conversación" in r.text


def test_enviar_pregunta_contesta_nvidia(cliente, csrf, app, sin_modelos):
    t = T.anadir("Web", detalle="Falta el paso 2.")
    r = _post(cliente, csrf, f"/tareas/{t['id']}/chat", mensaje="¿Qué falta?")
    assert r.status_code == 200 and "¿Qué falta?" in r.text
    assert 'id="chat-form"' in r.text and 'hx-swap-oob="outerHTML"' in r.text   # el cuadro se vacia
    _esperar(app)
    r = cliente.get(f"/tareas/{t['id']}/chat")
    assert "NVIDIA" in r.text and "Falta el paso 2." in r.text and "Pensando" not in r.text
    assert sin_modelos.prompts


def test_sin_csrf_no_entra(cliente, csrf):
    t = T.anadir("Web")
    r = cliente.post(f"/tareas/{t['id']}/chat", data={"mensaje": "hola"})
    assert r.status_code == 403
    assert C.historial(t["id"]) == []


def test_accion_sola_y_deshacer_desde_la_web(cliente, csrf, app):
    t = T.anadir("Web", importancia=3, urgencia=3)
    _post(cliente, csrf, f"/tareas/{t['id']}/chat", mensaje="Súbele la prioridad")
    _esperar(app)
    r = cliente.get(f"/tareas/{t['id']}/chat")
    assert "Hecho sin preguntar" in r.text and "Deshacer" in r.text
    assert T.buscar(t["id"])["importancia"] == 4
    n = C.historial(t["id"])[-1]["n"]
    r = _post(cliente, csrf, f"/tareas/{t['id']}/chat/{n}/deshacer")
    assert r.status_code == 200 and "(deshecho)" in r.text
    assert r.headers.get("HX-Trigger") == "nexo:tareas"
    assert T.buscar(t["id"])["importancia"] == 3


def test_propuesta_aprobar_desde_la_web_y_sale_en_el_centro(cliente, csrf, app):
    t = T.anadir("Web")
    _post(cliente, csrf, f"/tareas/{t['id']}/chat", mensaje="Cambia el título a Web nueva")
    _esperar(app)
    r = cliente.get(f"/tareas/{t['id']}/chat")
    assert "Necesita tu OK" in r.text and "Aprobar" in r.text
    assert T.buscar(t["id"])["titulo"] == "Web"
    centro = cliente.get("/centro/resumen")
    assert "Esperan tu OK en el chat" in centro.text and f"/tareas/{t['id']}#chat-tarea" in centro.text
    n = C.historial(t["id"])[-1]["n"]
    r = _post(cliente, csrf, f"/tareas/{t['id']}/chat/{n}/aprobar")
    assert "Aprobado" in r.text
    assert T.buscar(t["id"])["titulo"] == "Web nueva"
    assert "Esperan tu OK" not in cliente.get("/centro/resumen").text
    r = _post(cliente, csrf, f"/tareas/{t['id']}/chat/{n}/aprobar")      # dos veces no
    assert "ya estaba decidida" in r.text and r.headers.get("HX-Retarget") == "#error-chat"


def test_denegar_desde_la_web(cliente, csrf, app):
    t = T.anadir("Web")
    _post(cliente, csrf, f"/tareas/{t['id']}/chat", mensaje="descártala")
    _esperar(app)
    n = C.historial(t["id"])[-1]["n"]
    r = _post(cliente, csrf, f"/tareas/{t['id']}/chat/{n}/denegar")
    assert "No aprobado" in r.text
    assert T.buscar(t["id"])["estado"] == "pendiente"
    assert ap.ver(C.historial(t["id"])[1]["aprobacion"])["estado"] == "denegada"


def test_mensaje_vacio_y_parada(cliente, csrf, bandera):
    t = T.anadir("Web")
    r = _post(cliente, csrf, f"/tareas/{t['id']}/chat", mensaje="  ")
    assert r.headers.get("HX-Retarget") == "#error-chat" and "Escribe algo" in r.text
    bandera.write_text("prueba", encoding="utf-8")
    r = _post(cliente, csrf, f"/tareas/{t['id']}/chat", mensaje="Súbele la prioridad")
    assert "PARADA" in r.text
    assert C.historial(t["id"]) == []


def test_escalar_desde_la_web(cliente, csrf, app, sin_modelos):
    t = T.anadir("Web")
    _post(cliente, csrf, f"/tareas/{t['id']}/chat", mensaje="¿Rompe algo?", escalar="1")
    _esperar(app)
    r = cliente.get(f"/tareas/{t['id']}/chat")
    assert "para Claude" in r.text and "Guardada para Claude" in r.text
    assert not sin_modelos.prompts
    assert C.escalados()[0]["tarea"] == t["id"]


def test_sin_contestar_se_puede_reintentar(cliente, csrf, app):
    t = T.anadir("Web")
    m = C.enviar(t["id"], "¿Qué falta?")          # como si la web se hubiera reiniciado a medias
    r = cliente.get(f"/tareas/{t['id']}/chat")
    assert "Reintentar" in r.text
    _post(cliente, csrf, f"/tareas/{t['id']}/chat/{m['n']}/reintentar")
    _esperar(app)
    assert "Reintentar" not in cliente.get(f"/tareas/{t['id']}/chat").text


def test_el_texto_se_escapa(cliente, csrf, app):
    t = T.anadir("Web")
    _post(cliente, csrf, f"/tareas/{t['id']}/chat", mensaje="anota: <script>alert(1)</script>")
    _esperar(app)
    r = cliente.get(f"/tareas/{t['id']}/chat")
    assert "<script>alert(1)" not in r.text and "&lt;script&gt;" in r.text


def test_evento_chat_por_sse(app, cliente, csrf):
    t = T.anadir("Web")
    antes = app.state.bus.ultimo_id
    _post(cliente, csrf, f"/tareas/{t['id']}/chat", mensaje="¿Qué falta?")
    _esperar(app)
    assert antes != app.state.bus.ultimo_id
    assert any(e.tipo == "chat" and e.datos == {"tarea": t["id"]} for e in app.state.bus._criticos)
