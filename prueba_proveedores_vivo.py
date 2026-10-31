"""Prueba de proveedores.py contra los proveedores REALES (T046).

Comprueba que QwenProvider, GeminiProvider, ChatGPTProvider y
ClaudeProvider cumplen el mismo contrato minimo (Proveedor) aunque por
dentro sean completamente distintos, y que cada uno responde de
verdad o dice honestamente por que no puede.

Va en segundo plano (lanzar()) porque Gemini y ChatGPT tardan bastantes
segundos por respuesta (navegador.preguntar) y el puente MCP corta a
los 50s. Deja el resultado en registros/prueba_proveedores_vivo.txt.

Claude NO se dispara de verdad aqui: hacerlo consumiria un turno real
del plan de Claude Code solo para una prueba. Esta prueba solo
comprueba que ClaudeProvider informa correctamente de su estado (hoy,
12/09/2026, secretos.toml no tiene seccion [rutina] -> NOT_AVAILABLE).
Si algun dia el token ya esta puesto, esta prueba lo detecta y NO
dispara ningun turno (lo avisa en el registro en vez de fallar).
"""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import logging  # noqa: E402
logging.disable(logging.INFO)

import proveedores  # noqa: E402


SALIDA = RAIZ / "registros" / "prueba_proveedores_vivo.txt"
SALIDA.parent.mkdir(parents=True, exist_ok=True)

lineas: list[str] = []
fallos = 0


def anotar(texto: str = "") -> None:
    print(texto, flush=True)
    lineas.append(str(texto))
    SALIDA.write_text("\n".join(lineas), encoding="utf-8")


def comprobar(titulo: str, condicion: bool, detalle: str = "") -> None:
    global fallos

    if condicion:
        anotar(f"  VALE  {titulo}")
    else:
        fallos += 1
        anotar(f"  FALLA {titulo} {detalle}")


anotar(f"PROVEEDORES EN VIVO  {time.strftime('%Y-%m-%d %H:%M:%S')}")
anotar("=" * 60)


anotar("\n0. Los cuatro cumplen el mismo contrato minimo (duck typing)")

instancias = [
    proveedores.QwenProvider(),
    proveedores.GeminiProvider(),
    proveedores.ChatGPTProvider(),
    proveedores.ClaudeProvider(),
]

for p in instancias:
    comprobar(f"{p.nombre} cumple Proveedor", isinstance(p, proveedores.Proveedor))
    comprobar(f"{p.nombre}.capacidades() es dict", isinstance(p.capacidades(), dict))


anotar("\n1. Qwen")

try:
    q = proveedores.QwenProvider()
    estado_q = q.estado()
    anotar(f"  estado(): {estado_q}")

    comprobar("disponible", estado_q["disponible"])

    r = q.enviar("Responde solo con una palabra: hola")
    anotar(f"  enviar() -> {r}")

    comprobar("responde OK", r.ok, r.detalle)
    comprobar("hay texto", bool(r.texto.strip()))
except Exception:
    fallos += 1
    anotar("EXCEPCION en Qwen:")
    anotar(traceback.format_exc())


anotar("\n2. Gemini")

try:
    from extremidades import navegador

    if not navegador.activo():
        anotar("  Chrome no estaba activo, arrancando...")
        navegador.arrancar()

    g = proveedores.GeminiProvider()
    estado_g = g.estado()
    anotar(f"  estado(): {estado_g}")

    comprobar("disponible", estado_g["disponible"])

    r = g.enviar("Responde solo con una palabra: hola")
    anotar(f"  enviar() -> {r}")

    comprobar("responde OK", r.ok, r.detalle)
    comprobar("hay texto", bool(r.texto.strip()))
except Exception:
    fallos += 1
    anotar("EXCEPCION en Gemini:")
    anotar(traceback.format_exc())


anotar("\n3. ChatGPT")

try:
    from extremidades import navegador

    if not navegador.activo():
        anotar("  Chrome no estaba activo, arrancando...")
        navegador.arrancar()

    c = proveedores.ChatGPTProvider()
    estado_c = c.estado()
    anotar(f"  estado(): {estado_c}")

    comprobar("disponible", estado_c["disponible"])

    r = c.enviar("Responde solo con una palabra: hola")
    anotar(f"  enviar() -> {r}")

    comprobar("responde OK", r.ok, r.detalle)
    comprobar("hay texto", bool(r.texto.strip()))
except Exception:
    fallos += 1
    anotar("EXCEPCION en ChatGPT:")
    anotar(traceback.format_exc())


anotar("\n4. Claude (solo estado: NO se dispara un turno real, cuesta plan)")

try:
    cl = proveedores.ClaudeProvider()
    estado_cl = cl.estado()
    anotar(f"  estado(): {estado_cl}")

    if not estado_cl["disponible"]:
        r = cl.enviar("(prueba T046, no deberia llegar a disparar nada)")
        anotar(f"  enviar() -> {r}")
        comprobar("informa NOT_AVAILABLE sin token (T039 aun pendiente)",
                  r.estado == "NOT_AVAILABLE")
    else:
        anotar(
            "  [token YA configurado: no se dispara un turno real en esta "
            "prueba para no gastar plan sin necesidad. Avisar a Damian.]"
        )
        comprobar("disponible sin disparar nada", True)
except Exception:
    fallos += 1
    anotar("EXCEPCION en Claude:")
    anotar(traceback.format_exc())


anotar("\n" + ("TODO VALE" if fallos == 0 else f"{fallos} FALLOS"))
anotar("FIN")
