# -*- coding: utf-8 -*-
"""Prueba EN VIVO de ChatGPTProvider (T082), exigida por Damian antes de
conectarlo como fallback del Router ("prueba antes pero ok", 23/09).
Arranca el Chrome de pruebas (perfil propio, no el de diario) si hace falta,
manda UNA tarea de resumen real y le aplica la misma verificacion mecanica
que usaria router.py. Resultado en registros/prueba_chatgpt_vivo.txt."""
import time
from pathlib import Path

import proveedores
import router
from extremidades import navegador

SALIDA = Path("registros/prueba_chatgpt_vivo.txt")
lineas = []


def log(s):
    lineas.append(s)
    SALIDA.write_text("\n".join(lineas), encoding="utf-8")


log(f"PRUEBA CHATGPT EN VIVO {time.strftime('%Y-%m-%d %H:%M:%S')}")
if not navegador.activo():
    log("Chrome de pruebas no estaba abierto: arrancando...")
    navegador.arrancar(aprobado=True)
log(f"navegador activo: {navegador.activo()}")

p = proveedores.ChatGPTProvider()
log(f"estado(): {p.estado()}")

texto = (
    "El registro de evidencia de Nexo permite reconstruir una cadena completa de "
    "ejecucion leyendo un unico archivo, sin tener que interpretar texto libre ni "
    "adivinar que paso en cada paso intermedio del proceso. Cada entrada lleva un "
    "identificador de ejecucion, la fase, el proveedor y el resultado."
)
tarea = f"Resume el siguiente texto en una sola frase corta, en espanol:\n\n{texto}"

t0 = time.time()
r = p.enviar(tarea)
seg = time.time() - t0
log(f"enviar(): estado={r.estado} en {seg:.1f}s")
log(f"detalle: {r.detalle}")
log(f"texto: {r.texto}")

if r.ok:
    ok, motivo = router._verificar_resumen(tarea, r.texto)
    log(f"verificacion mecanica del Router: {'PASA' if ok else 'NO PASA'} ({motivo})")
    log("RESULTADO: " + ("OK" if ok else "FALLO_VERIFICACION"))
else:
    log(f"RESULTADO: FALLO_PROVEEDOR ({r.estado})")
log("FIN")
