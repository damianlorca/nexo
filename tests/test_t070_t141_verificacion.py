# -*- coding: utf-8 -*-
"""Verificacion con evidencia (05/10) de dos tareas cerradas sin testear:
T070 consumidor Cola->Router (consumidor_router.consumir_tarea) y T141 (/turno del bot; /ahora fuera de /start).
Con dobles: sin red, sin Router real y sin Telegram."""
from __future__ import annotations

import pytest

import consumidor_router as C
from nucleo import tareas as T


def _router(estado):
    def procesar(texto, claves_extraccion=None):
        if estado == "OK":
            return {"estado": "OK", "execution_id": "e1", "categoria": "simple", "proveedor": "qwen",
                    "intentos": 1, "texto": "resuelto: " + texto}
        return {"estado": "ESCALADO", "execution_id": "e2", "categoria": "simple", "motivo": "nadie pudo"}
    return procesar


def test_t070_consume_una_tarea_etiquetada_y_la_cierra(monkeypatch):
    t = T.anadir("Prueba consumidor", detalle="di hola", etiquetas=["router:auto"])
    monkeypatch.setattr(C.router_mod, "procesar", _router("OK"))
    r = C.consumir_tarea(t["id"])
    assert r["estado"] == "OK"
    cerrada = T.buscar(t["id"])
    assert cerrada["estado"] == "hecha" and "Resuelta automaticamente por el Router" in cerrada["notas"][-1]["texto"]


def test_t070_escalado_solo_anota(monkeypatch):
    t = T.anadir("Prueba escalado", detalle="algo dificil", etiquetas=["router:auto"])
    monkeypatch.setattr(C.router_mod, "procesar", _router("ESCALADO"))
    C.consumir_tarea(t["id"])
    assert T.buscar(t["id"])["estado"] == "pendiente"
    assert "Router escalado" in T.buscar(t["id"])["notas"][-1]["texto"]


def test_t070_sin_etiqueta_no_toca_la_tarea(monkeypatch):
    t = T.anadir("Tarea normal", detalle="no tocar")
    monkeypatch.setattr(C.router_mod, "procesar", lambda *a, **k: pytest.fail("no debe llamar al Router"))
    with pytest.raises(C.TareaNoElegible):
        C.consumir_tarea(t["id"])
    assert T.buscar(t["id"])["estado"] == "pendiente"


def test_t141_ahora_fuera_de_start_y_turno_remite_a_la_web():
    """T141 (23/09) quito /ahora de la ayuda de /start y anadio /turno; el 28/09 (T231, Damian) /turno se desactivo
    a favor de la cola de la web. Lo que queda vigente: /ahora no se anuncia y /turno no lanza nada por fuera."""
    import inspect
    from canal import bot
    lanzados = []
    respuesta = bot._cmd_turno("", lanzar=lanzados.append)
    assert lanzados == [] and "web" in respuesta
    fuente = inspect.getsource(bot.procesar_updates)
    ayuda = fuente[fuente.index("Canal abierto"):][:2500]
    assert "/ahora" not in ayuda and "/estado" in ayuda


def test_t066_red_de_seguridad_eco_y_negativa():
    """T066: si la web cambia o reutiliza una conversacion contaminada (caso real Gemini 23/09), la respuesta que es
    eco del prompt o una negativa corta se detecta y no cuenta como trabajo hecho."""
    from nucleo import trabajo
    prompt = "Analiza los riesgos de seguridad del modulo de turnos y propone tres mejoras concretas con su riesgo"
    assert trabajo._es_eco(prompt, "Has dicho " + prompt)
    assert trabajo._es_eco(prompt, "No te puedo ayudar con eso, ya que soy un modelo de lenguaje.")
    assert not trabajo._es_eco(prompt, "1. Candado por turno. 2. Tope de RAM. 3. Registro firmado. " * 5)


# ------------------------------------------------------------------ T723 / T724 (propuestas de T720)
def test_t723_sin_detalle_no_es_candidata():
    a = T.anadir("Con detalle", detalle="di hola", etiquetas=["router:auto"])
    b = T.anadir("Sin detalle", detalle="   ", etiquetas=["router:auto"])
    ids = [t["id"] for t in C.candidatas_elegibles()]
    assert a["id"] in ids and b["id"] not in ids


@pytest.mark.parametrize("resultado,trozo", [
    ({"estado": "RARO", "execution_id": "e"}, "estado desconocido"),
    ({"estado": "OK", "execution_id": "e", "categoria": "c", "proveedor": "q"}, "sin texto"),
    ({"estado": "OK", "execution_id": "e", "categoria": "c", "proveedor": "q", "texto": "  "}, "texto vacio"),
    ({"estado": "ESCALADO", "execution_id": "e"}, "sin categoria, motivo"),
    (None, "no es un dict"),
])
def test_t724_resultado_fuera_de_contrato_se_anota_y_no_cierra(monkeypatch, resultado, trozo):
    t = T.anadir("Prueba contrato", detalle="di hola", etiquetas=["router:auto"])
    monkeypatch.setattr(C.router_mod, "procesar", lambda *a, **k: resultado)
    r = C.consumir_tarea(t["id"])
    assert r["estado"] == "INVALIDO" and trozo in r["motivo"]
    x = T.buscar(t["id"])
    assert x["estado"] == "pendiente" and "fuera de contrato" in x["notas"][-1]["texto"]
