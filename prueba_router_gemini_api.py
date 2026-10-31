# -*- coding: utf-8 -*-
"""T136: el Router prueba Gemini API antes que Gemini web (sin red: todo simulado).
H16 (26/09): Gemini va despues de ChatGPT; aqui ChatGPT falla para llegar a Gemini."""
from unittest import mock

import router
from proveedores import Resultado

TEXTO = ("La reunion del lunes reviso el presupuesto del proyecto. Se acordo reducir gastos de viaje un 20 por ciento, "
         "contratar a dos personas para soporte y retrasar el lanzamiento dos semanas para cerrar pruebas pendientes. ") * 3


class Falso:
    def __init__(self, nombre, respuesta=None, disponible=True):
        self.nombre, self.respuesta, self._disp, self.llamadas = nombre, respuesta, disponible, 0

    def disponible(self):
        return self._disp

    def estado(self):
        return {"disponible": self._disp, "motivo": ""}

    def enviar(self, tarea):
        self.llamadas += 1
        return self.respuesta or Resultado("ERROR", detalle=f"{self.nombre} falla")

    def capacidades(self):
        return {}


BUEN_RESUMEN = Resultado("OK", texto="Se recortan viajes un 20 %, se contratan dos personas y se retrasa el lanzamiento.")
ok = mal = 0


def caso(nombre, cond):
    global ok, mal
    print("OK " if cond else "MAL", nombre)
    ok, mal = ok + bool(cond), mal + (not cond)


def correr(api, web, gpt):
    qwen = Falso("qwen")
    with mock.patch("router.QwenProvider", return_value=qwen), \
         mock.patch("router.GeminiAPIProvider", return_value=api), \
         mock.patch("router.GeminiProvider", return_value=web), \
         mock.patch("router.ChatGPTProvider", return_value=gpt), \
         mock.patch("router._clasificar", return_value="resumen"):
        return router.procesar(TEXTO)


api, web, gpt = Falso("gemini_api", BUEN_RESUMEN), Falso("gemini"), Falso("chatgpt")
r = correr(api, web, gpt)
caso("con clave: resuelve Gemini API", r["estado"] == "OK" and r.get("proveedor") == "gemini_api")
caso("con clave: ChatGPT antes (1 vez) y no toca la web", web.llamadas == 0 and gpt.llamadas == 1)

api, web, gpt = Falso("gemini_api"), Falso("gemini", BUEN_RESUMEN), Falso("chatgpt")
r = correr(api, web, gpt)
caso("API falla: pasa a Gemini web", r["estado"] == "OK" and r.get("proveedor") == "gemini" and api.llamadas == 1)

api, web, gpt = Falso("gemini_api", disponible=False), Falso("gemini", BUEN_RESUMEN), Falso("chatgpt")
r = correr(api, web, gpt)
caso("sin clave: ni se intenta la API", api.llamadas == 0 and r.get("proveedor") == "gemini")

api, web, gpt = Falso("gemini_api"), Falso("gemini"), Falso("chatgpt")
r = correr(api, web, gpt)
caso("todo falla: escala y cita los tres", r["estado"] == "ESCALADO")

print(f"\n{ok}/{ok + mal} OK")
raise SystemExit(1 if mal else 0)
