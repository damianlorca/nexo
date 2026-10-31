# -*- coding: utf-8 -*-
"""Prueba del fallback a ChatGPT en router.py (T082, 23/09; orden H16 del 26/09:
Qwen -> ChatGPT -> Gemini).

Totalmente simulada: clasificacion, Qwen, Gemini y ChatGPT se sustituyen
por falsos, y registrar_evidencia se captura en memoria (no escribe en
registros/evidencia.jsonl). Cero modelos, cero navegador, cero RAM.
"""
from unittest import mock

import proveedores
import router

# 23/09: el Router intenta Gemini API antes que la web si hay clave. En estas pruebas
# se desactiva para no llamar a la API real; el camino API tiene su propia prueba.
import router as _router_sin_api  # noqa: E402


class _SinGeminiAPI:
    nombre = "gemini_api"

    def disponible(self):
        return False


_router_sin_api.GeminiAPIProvider = _SinGeminiAPI


TEXTO = (
    "El registro de evidencia permite reconstruir una cadena completa de ejecucion "
    "leyendo un unico archivo, sin interpretar texto libre ni adivinar que paso en "
    "cada paso intermedio del proceso de principio a fin."
)
TAREA = "Resume en una frase muy corta:\n\n" + TEXTO
BUENO = proveedores.Resultado("OK", texto="Evidencia en un archivo reconstruye la ejecucion.")
MALO_VERIF = proveedores.Resultado("OK", texto=TAREA)  # identico: no pasa la verificacion
ERROR = proveedores.Resultado("ERROR", detalle="fallo forzado de prueba")

fallos = []


class Falso:
    def __init__(self, nombre, resultados):
        self.nombre = nombre
        self.cola = list(resultados)
        self.llamadas = 0

    def enviar(self, tarea):
        r = self.cola[min(self.llamadas, len(self.cola) - 1)]
        self.llamadas += 1
        return r


def correr(qwen, gemini, chatgpt):
    fases = []

    def captura(fase, **kw):
        fases.append((fase, kw.get("proveedor"), kw.get("accion")))

    with mock.patch("extremidades.qwen.clasificar", return_value="resumen"), \
         mock.patch("router.registrar_evidencia", side_effect=captura), \
         mock.patch("router.QwenProvider", return_value=qwen), \
         mock.patch("router.GeminiProvider", return_value=gemini), \
         mock.patch("router.ChatGPTProvider", return_value=chatgpt):
        r = router.procesar(TAREA)
    return r, fases


def comprobar(nombre, cond, detalle=""):
    print(("  OK   " if cond else "  FALLO ") + nombre + ("" if cond else f"  -> {detalle}"))
    if not cond:
        fallos.append(nombre)


print("A. Qwen falla 2 veces y ChatGPT resuelve: Gemini no se llama")
q, g, c = Falso("qwen", [MALO_VERIF]), Falso("gemini", [BUENO]), Falso("chatgpt", [BUENO])
r, f = correr(q, g, c)
comprobar("estado OK", r.get("estado") == "OK", r)
comprobar("proveedor final chatgpt", r.get("proveedor") == "chatgpt", r)
comprobar("intentos = 3 (2 Qwen + ChatGPT)", r.get("intentos") == 3, r)
comprobar("llamadas 2/0/1 (Qwen/Gemini/ChatGPT)", (q.llamadas, g.llamadas, c.llamadas) == (2, 0, 1), (q.llamadas, g.llamadas, c.llamadas))
comprobar("evidencia del salto a ChatGPT", ("reintento", "chatgpt", "fallback_a_chatgpt_tras_agotar_qwen") in f, f)
comprobar("resultado registrado con proveedor chatgpt", any(x[0] == "resultado" and x[1] == "chatgpt" for x in f), f)

print("B. Qwen resuelve a la primera: ni Gemini ni ChatGPT se llaman")
q, g, c = Falso("qwen", [BUENO]), Falso("gemini", [BUENO]), Falso("chatgpt", [BUENO])
r, f = correr(q, g, c)
comprobar("OK con qwen", r.get("estado") == "OK" and r.get("proveedor") == "qwen", r)
comprobar("Gemini y ChatGPT sin llamar", (g.llamadas, c.llamadas) == (0, 0), (g.llamadas, c.llamadas))

print("C. ChatGPT falla y Gemini resuelve")
q, g, c = Falso("qwen", [ERROR]), Falso("gemini", [BUENO]), Falso("chatgpt", [ERROR])
r, f = correr(q, g, c)
comprobar("OK con gemini", r.get("estado") == "OK" and r.get("proveedor") == "gemini", r)
comprobar("ChatGPT llamado 1 vez antes", c.llamadas == 1, c.llamadas)
comprobar("evidencia del salto a Gemini", ("reintento", "gemini", "fallback_a_gemini_tras_fallar_chatgpt") in f, f)

print("D. Todo falla: escalado, ChatGPT y Gemini se intentan UNA sola vez")
q, g, c = Falso("qwen", [ERROR]), Falso("gemini", [MALO_VERIF]), Falso("chatgpt", [ERROR])
r, f = correr(q, g, c)
comprobar("ESCALADO", r.get("estado") == "ESCALADO", r)
comprobar("ChatGPT y Gemini llamados 1 vez", (c.llamadas, g.llamadas) == (1, 1), (c.llamadas, g.llamadas))
comprobar("el motivo menciona a los tres", all(n in r.get("motivo", "").lower() for n in ("qwen", "gemini", "chatgpt")), r)
comprobar("ultima fase = escalado", f and f[-1][0] == "escalado", f)

print("E. Categoria 'otro': escala sin llamar a ningun proveedor")
q, g, c = Falso("qwen", [BUENO]), Falso("gemini", [BUENO]), Falso("chatgpt", [BUENO])
with mock.patch("extremidades.qwen.clasificar", return_value="otro"), \
     mock.patch("router.registrar_evidencia"), \
     mock.patch("router.QwenProvider", return_value=q), \
     mock.patch("router.GeminiProvider", return_value=g), \
     mock.patch("router.ChatGPTProvider", return_value=c):
    r = router.procesar("haz algo complejo")
comprobar("ESCALADO sin llamadas", r.get("estado") == "ESCALADO" and (q.llamadas, g.llamadas, c.llamadas) == (0, 0, 0), r)

print()
print("TODO VALE" if not fallos else f"{len(fallos)} FALLOS: {fallos}")
raise SystemExit(1 if fallos else 0)
