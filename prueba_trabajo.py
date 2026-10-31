# -*- coding: utf-8 -*-
"""Pruebas de nucleo/trabajo.py (generar -> revisiones de otras IAs -> mejora final). Sin red."""
from unittest import mock

from nucleo import trabajo
from proveedores import Resultado

ok = mal = 0


def caso(nombre, cond):
    global ok, mal
    print("OK " if cond else "MAL", nombre)
    ok, mal = ok + bool(cond), mal + (not cond)


p = "Investiga para esta tarea de NEXO (asistente personal multi-IA de Damian, local-first, Windows). Entrega un informe"
caso("eco del prompt detectado", trabajo._es_eco(p, "Has dicho " + p + " ..."))
caso("negativa detectada", trabajo._es_eco(p, "Soy una IA basada en texto y no tengo esa capacidad."))
caso("informe normal no es eco", not trabajo._es_eco(p, "Informe: X sirve para Y. Recomendacion: adoptar."))
caso("gravedad y veredicto se leen", trabajo._gravedad("FALLOS:\n- a\nGRAVEDAD: **MEDIA**\nVEREDICTO: CAMBIOS_NECESARIOS") == "MEDIA"
     and trabajo._veredicto("GRAVEDAD: BAJA\nVEREDICTO: APROBADO") == "APROBADO")


class F:
    def __init__(self, nombre, resp=None, disp=True, url=None):
        self.nombre, self.resp, self._d, self.llamadas, self.url = nombre, resp, disp, [], url

    def disponible(self):
        return self._d

    def enviar(self, tarea, buscar=False):
        self.llamadas.append(tarea)
        return self.resp(tarea) if callable(self.resp) else (self.resp or Resultado("ERROR", detalle="falla"))

    def continuar(self, tarea):
        self.llamadas.append("CONTINUAR:" + tarea)
        return Resultado("OK", texto="VERSION FINAL mejorada " + "x" * 300)


REV = Resultado("OK", texto="FALLOS:\n- \"dato\" dudoso\nOMISIONES:\n- falta coste\nMEJORAS:\n- ninguno\nAÑADIR:\n- riesgos\n"
                            "GRAVEDAD: MEDIA\nVEREDICTO: CAMBIOS_NECESARIOS")
with mock.patch("proveedores.GeminiAPIProvider", lambda **k: F("gemini_api", REV)), \
     mock.patch("proveedores.GeminiProvider", lambda: F("gemini", REV)), \
     mock.patch("proveedores.GroqProvider", lambda **k: F("groq", REV)), \
     mock.patch("proveedores.ChatGPTProvider", lambda: F("chatgpt")), \
     mock.patch.object(trabajo, "_web", return_value=True):
    nombres = [r.nombre for r in trabajo._revisores("chatgpt")]
    caso(f"revisores de chatgpt: otras IAs primero, chatgpt al final, nunca qwen {nombres}",
         nombres[-1] == "chatgpt" and "qwen" not in nombres and "gemini" in nombres and "groq" in nombres)
    revs = trabajo._revisar({"id": "T9", "titulo": "x"}, "borrador", "chatgpt")
    caso("se recogen 2 revisiones con gravedad", len(revs) == 2 and all(r["gravedad"] == "MEDIA" for r in revs))
    autor = F("chatgpt", url="https://chatgpt.com/c/abc")
    final, modo = trabajo._mejorar(autor, "prompt", "borrador", revs)
    caso("mejora final en la MISMA conversacion con las revisiones",
         modo == "misma conversacion" and final and "Revision de gemini" in autor.llamadas[-1] and "AÑADIR" in autor.llamadas[-1])
    sin_url = F("gemini_api", lambda tarea: Resultado("OK", texto="FINAL " + "y" * 300))
    final2, modo2 = trabajo._mejorar(sin_url, "prompt", "borrador", revs)
    caso("sin conversacion: se manda borrador+revisiones", final2 and "TU BORRADOR ANTERIOR" in sin_url.llamadas[-1])

# T163: la revision de prueba trae las 4 secciones obligatorias (antes solo FALLOS, que ya no cuenta).
leve = Resultado("OK", texto="FALLOS:\n- ninguno\nOMISIONES:\n- ninguno\nMEJORAS:\n- ninguno\nAÑADIR:\n- ninguno\n"
                             "GRAVEDAD: BAJA\nVEREDICTO: CAMBIOS_NECESARIOS")
with mock.patch.object(trabajo, "_revisores", return_value=[F("gemini", leve)]):
    caso("gravedad BAJA -> APROBADO", trabajo._revisar({"id": "T9", "titulo": "x"}, "b", "chatgpt")[0]["veredicto"] == "APROBADO")
malformato = Resultado("OK", texto="me parece bien")
with mock.patch.object(trabajo, "_revisores", return_value=[F("gemini", malformato)]):
    caso("revision sin formato no cuenta", trabajo._revisar({"id": "T9", "titulo": "x"}, "b", "chatgpt") == [])

print(f"\n{ok}/{ok + mal} OK")
raise SystemExit(1 if mal else 0)
