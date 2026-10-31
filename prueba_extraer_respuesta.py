# -*- coding: utf-8 -*-
"""Prueba de navegador._extraer_respuesta (sin navegador: solo texto)."""
from extremidades import navegador as nav

fallos = []


def comprobar(nombre, obtenido, esperado):
    ok = obtenido == esperado
    print(("  OK    " if ok else "  FALLO ") + nombre + ("" if ok else f"\n        obtenido={obtenido!r}\n        esperado={esperado!r}"))
    if not ok:
        fallos.append(nombre)


PROMPT = "Resume esto en una frase."
ANTES = "Cabecera de la web\nHistorial\n"

# 1. Caso visto el 23/09: encuesta de satisfaccion de ChatGPT pegada al final.
ultimo = (ANTES + PROMPT + "\nChatGPT ha dicho\nEl registro permite reconstruir la ejecucion.\n\n"
          "¿Te está resultando útil esta conversación hasta ahora?\nSi\nNo")
comprobar("quita la encuesta de ChatGPT", nav._extraer_respuesta(ANTES, ultimo, PROMPT),
          "El registro permite reconstruir la ejecucion.")

# 2. Ya funcionaba: pie 'puede cometer errores' y lo que viene detras.
ultimo = (ANTES + PROMPT + "\nGemini ha dicho\nRespuesta de dos\nlineas.\n"
          "Gemini puede cometer errores, incluso sobre personas.\nFlash")
comprobar("quita el pie de disclaimer", nav._extraer_respuesta(ANTES, ultimo, PROMPT),
          "Respuesta de dos\nlineas.")

# 3. Sin pie ni encuesta: la respuesta queda intacta.
ultimo = ANTES + PROMPT + "\nChatGPT ha dicho\nSolo la respuesta."
comprobar("respuesta limpia intacta", nav._extraer_respuesta(ANTES, ultimo, PROMPT), "Solo la respuesta.")

# 4. Mayusculas distintas de la encuesta: tambien se quita.
ultimo = ANTES + PROMPT + "\nRespuesta.\n¿TE ESTÁ RESULTANDO ÚTIL ESTA CONVERSACIÓN?"
comprobar("encuesta en mayusculas", nav._extraer_respuesta(ANTES, ultimo, PROMPT), "Respuesta.")

print("\nTODO VALE" if not fallos else f"\n{len(fallos)} FALLOS")
raise SystemExit(1 if fallos else 0)
