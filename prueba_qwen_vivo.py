"""Prueba de qwen contra el modelo de verdad, de punta a punta.

Va en segundo plano (lanzar()) porque cada respuesta tarda entre 5 y
30 segundos y el puente MCP corta a los 50. Deja el resultado en
registros/prueba_qwen_vivo.txt.
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

from extremidades import qwen  # noqa: E402


SALIDA = RAIZ / "registros" / "prueba_qwen_vivo.txt"
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


anotar(f"QWEN EN VIVO  {time.strftime('%Y-%m-%d %H:%M:%S')}")
anotar("=" * 60)

try:
    anotar("\n1. El runtime responde")

    t0 = time.time()
    hay = qwen.disponible()
    anotar(f"  disponible() tarda {time.time() - t0:.1f}s")

    comprobar("disponible() dice que si", hay)
    comprobar("lista modelos", len(qwen.modelos()) > 0, str(qwen.modelos()))

    anotar("\n2. clasificar() DE VERDAD, el caso que antes salia vacio")

    casos = [
        ("El plazo de la beca se cerro hace tres meses, ya no se puede pedir.",
         ["urgente", "no urgente"], "no urgente"),
        ("La beca de colaboracion cierra el 22 de septiembre y aun no has "
         "entregado el proyecto.",
         ["urgente", "no urgente"], "urgente"),
        ("Compra ya criptomonedas con un 500% de rentabilidad garantizada, "
         "pincha en este enlace.",
         ["spam", "no spam"], "spam"),
        ("Te escribo desde la secretaria del departamento sobre tu matricula.",
         ["spam", "no spam"], "no spam"),
    ]

    for texto, cats, esperado in casos:
        t0 = time.time()

        obtenido = qwen.clasificar(texto, cats)

        tardanza = time.time() - t0

        anotar(f"  texto    : {texto[:60]}...")
        anotar(f"  categorias {cats} -> {obtenido!r}  ({tardanza:.1f}s)")

        comprobar("    no devuelve vacio", bool(obtenido))
        comprobar("    acierta", obtenido == esperado, f"esperaba {esperado!r}")
        anotar("")

    anotar("\n3. resumir() devuelve algo con sentido")

    t0 = time.time()

    resumen = qwen.resumir(
        "Las becas de colaboracion del Ministerio de Educacion son ayudas de "
        "2.000 euros para estudiantes de ultimo curso de grado o de master "
        "que colaboran con un departamento universitario en tareas de "
        "investigacion. Requieren una nota media minima y la conformidad de "
        "un departamento que avale el proyecto. El plazo de la convocatoria "
        "2026-2027 termina el 22 de septiembre de 2026.",
        palabras=40,
    )

    anotar(f"  tarda {time.time() - t0:.1f}s")
    anotar(f"  resumen: {resumen!r}")

    comprobar("no viene vacio", bool(resumen.strip()))
    comprobar("no arrastra el bloque de razonamiento", "<think>" not in resumen.lower())
    comprobar("habla del tema", "beca" in resumen.lower() or "colabora" in resumen.lower())

    anotar("\n4. El minimo de tokens se aplica solo")

    t0 = time.time()

    corto = qwen.pedir("Di exactamente la palabra: listo.", max_tokens=5)

    anotar(f"  con max_tokens=5 pedido -> {corto!r}  ({time.time() - t0:.1f}s)")

    comprobar(
        "no devuelve vacio pese a pedir 5 tokens (antes si)",
        bool(corto.strip()),
    )

except Exception:
    fallos += 1
    anotar("EXCEPCION:")
    anotar(traceback.format_exc())

anotar("\n" + ("TODO VALE" if fallos == 0 else f"{fallos} FALLOS"))
anotar("FIN")
