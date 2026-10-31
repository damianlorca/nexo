# -*- coding: utf-8 -*-
"""T076: dos preguntas seguidas al mismo proveedor con pausa corta (8 s).
Comprueba que cada respuesta es la suya y no se mezcla con la otra.
Uso: python prueba_navegador_seguidas.py chatgpt|gemini
Resultado en registros/prueba_navegador_seguidas_<sitio>.txt"""
import sys
import time
from pathlib import Path

from extremidades import navegador

sitio = sys.argv[1] if len(sys.argv) > 1 else "chatgpt"
SALIDA = Path(f"registros/prueba_navegador_seguidas_{sitio}.txt")
lineas = []


def log(s):
    lineas.append(s)
    SALIDA.write_text("\n".join(lineas), encoding="utf-8")


P1 = ("Escribe una lista numerada de 8 frutas, una por linea, sin nada mas, "
      "y en la ultima linea escribe exactamente CIERRE_UNO")
P2 = ("Escribe una lista numerada de 8 herramientas de carpinteria, una por linea, sin nada mas, "
      "y en la ultima linea escribe exactamente CIERRE_DOS")

log(f"PRUEBA PREGUNTAS SEGUIDAS ({sitio}) {time.strftime('%Y-%m-%d %H:%M:%S')}")
if not navegador.activo():
    navegador.arrancar(aprobado=True)

t0 = time.time()
r1 = navegador.preguntar(sitio, P1)
log(f"\n--- R1 ({time.time()-t0:.1f}s) ---\n{r1}")
time.sleep(8)
t0 = time.time()
r2 = navegador.preguntar(sitio, P2)
log(f"\n--- R2 ({time.time()-t0:.1f}s) ---\n{r2}")

ok1 = "CIERRE_UNO" in r1 and "CIERRE_DOS" not in r1
ok2 = "CIERRE_DOS" in r2 and "CIERRE_UNO" not in r2
log(f"\nR1 limpia: {ok1} | R2 limpia: {ok2}")
log("RESULTADO: " + ("OK" if ok1 and ok2 else "MEZCLA/INCOMPLETA"))
log("FIN")
