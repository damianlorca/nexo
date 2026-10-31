# -*- coding: utf-8 -*-
"""H16 (26/09, decidido por Damian): el Router va Qwen -> ChatGPT -> Gemini -> escalado.
Y N01 (H11): con solo_local=True no sale del PC. Todo con dobles: sin modelos ni navegador."""
from __future__ import annotations

from unittest import mock

import pytest

import router
from proveedores import Resultado

TEXTO = ("La reunion del lunes reviso el presupuesto del proyecto. Se acordo reducir gastos de viaje "
         "un 20 por ciento, contratar a dos personas para soporte y retrasar el lanzamiento. ") * 3
BUENO = Resultado("OK", texto="Se recortan viajes, se contrata soporte y se retrasa el lanzamiento.")


class Falso:
    def __init__(self, nombre, respuesta=None, disponible=True, orden=None):
        self.nombre, self.respuesta, self._disp, self.llamadas, self.orden = nombre, respuesta, disponible, 0, orden

    def disponible(self):
        return self._disp

    def estado(self):
        return {"disponible": self._disp, "motivo": ""}

    def enviar(self, tarea):
        self.llamadas += 1
        if self.orden is not None:
            self.orden.append(self.nombre)
        return self.respuesta or Resultado("ERROR", detalle=f"{self.nombre} falla")

    def capacidades(self):
        return {}


def correr(qwen, gpt, api, web, **kw):
    with mock.patch("router.QwenProvider", return_value=qwen), \
         mock.patch("router.ChatGPTProvider", return_value=gpt), \
         mock.patch("router.GeminiAPIProvider", return_value=api), \
         mock.patch("router.GeminiProvider", return_value=web), \
         mock.patch("router.registrar_evidencia"), \
         mock.patch("router._clasificar", return_value="resumen"):
        return router.procesar(TEXTO, **kw)


def test_orden_qwen_chatgpt_gemini_api_gemini_web():
    orden = []
    q, g, a, w = (Falso(n, orden=orden) for n in ("qwen", "chatgpt", "gemini_api", "gemini"))
    r = correr(q, g, a, w)
    assert r["estado"] == "ESCALADO"
    assert orden == ["qwen", "qwen", "chatgpt", "gemini_api", "gemini"]


def test_chatgpt_resuelve_y_gemini_no_se_llama():
    q, g, a, w = Falso("qwen"), Falso("chatgpt", BUENO), Falso("gemini_api"), Falso("gemini")
    r = correr(q, g, a, w)
    assert r["estado"] == "OK" and r["proveedor"] == "chatgpt"
    assert (a.llamadas, w.llamadas) == (0, 0)


def test_qwen_resuelve_y_nadie_mas_se_llama():
    q, g, a, w = Falso("qwen", BUENO), Falso("chatgpt"), Falso("gemini_api"), Falso("gemini")
    r = correr(q, g, a, w)
    assert r["proveedor"] == "qwen" and (g.llamadas, a.llamadas, w.llamadas) == (0, 0, 0)


@pytest.mark.parametrize("buenos", [("chatgpt",), ("gemini_api",), ("gemini",)])
def test_solo_local_nunca_sale_del_pc(buenos):
    fuera = {n: Falso(n, BUENO if n in buenos else None) for n in ("chatgpt", "gemini_api", "gemini")}
    r = correr(Falso("qwen"), fuera["chatgpt"], fuera["gemini_api"], fuera["gemini"], solo_local=True)
    assert r["estado"] == "ESCALADO" and "solo_local" in r["motivo"]
    assert all(p.llamadas == 0 for p in fuera.values())
