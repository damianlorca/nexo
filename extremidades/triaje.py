"""Triaje de mensajes: el primer trabajo de verdad del obrero.

Para que sirve
--------------
Damian escribe por Telegram a cualquier hora. Cuando yo despierto me
encuentro N mensajes sin leer y me los tengo que tragar enteros para
saber cuales piden algo y cuales solo cuentan una cosa. Eso es caro:
lo hace el modelo grande, y es trabajo mecanico.

Qwen corre gratis en el PC. Esto le pasa a el la primera lectura: que
diga de que va cada mensaje y si corre prisa. Yo llego con la faena
masticada.

Lo que NO hace, a proposito
---------------------------
**No da de alta tareas por su cuenta.** Propone. Un modelo de 4B
leyendo un mensaje ambiguo y creando tareas sin que nadie mire es
justo la clase de automatismo que llena la cola de basura. La
propuesta se escribe y la confirma alguien.

Por que va por lanzar() y no por ejecutar_python()
--------------------------------------------------
Una peticion a qwen3 tarda entre 9 y 180 segundos, y el puente corta
a los 50 sin avisar (hallazgo B4). Cualquier cosa que llame aqui
dentro tiene que arrancarse con lanzar() y leerse por el log.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from extremidades import qwen
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico
from nucleo.registro import logger


log = logger("extremidades.triaje")

ENTRADA = RAIZ / "canal" / "entrada"
INFORME = RAIZ / "memoria" / "triaje.json"

# Categorias elegidas para que NO se parezcan entre si. Una de ellas
# metida dentro de otra es como se invertia la clasificacion antes
# (hallazgo F2); con palabras distintas el problema ni se plantea.
CATEGORIAS = ["tarea", "dato", "respuesta", "charla"]

URGENCIAS = ["urgente", "no urgente"]


def triar(texto: str) -> dict:
    """Una lectura de un mensaje. Dos preguntas cortas y un resumen."""

    inicio = time.time()

    categoria = qwen.clasificar(texto, CATEGORIAS, por_defecto="")

    urgencia = qwen.clasificar(texto, URGENCIAS, por_defecto="")

    resumen = qwen.pedir(
        "Resume en UNA sola frase de menos de 20 palabras que pide o "
        "que cuenta este mensaje. En espanol. Solo la frase.",
        texto,
        max_tokens=800,
    )

    return {
        "categoria": categoria,
        "urgencia": urgencia,
        "resumen": resumen.strip().replace("\n", " ")[:200],
        "segundos": round(time.time() - inicio, 1),
    }


def mensajes_pendientes() -> list[dict]:
    """Los libre_*.json que hay ahora mismo, sin marcarlos como leidos.

    NO usa buzon.mensajes_nuevos() a proposito: ese los renombra a
    .leido, y si el triaje se cae a mitad los mensajes quedarian
    marcados sin haberse mirado.
    """

    if not ENTRADA.is_dir():
        return []

    fuera = []

    for archivo in sorted(ENTRADA.glob("libre_*.json")):
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("no se puede leer %s: %s", archivo.name, e)

            continue

        fuera.append({
            "archivo": archivo.name,
            "hora": datos.get("hora", ""),
            "texto": datos.get("texto", ""),
        })

    return fuera


def triar_pendientes(guardar: bool = True) -> dict:
    """Pasa el obrero por todo lo que haya. Devuelve el informe."""

    pendientes = mensajes_pendientes()

    log.info("triaje de %d mensajes", len(pendientes))

    resultados = []

    for i, m in enumerate(pendientes, 1):
        log.info("  %d/%d  %s", i, len(pendientes), m["archivo"])

        try:
            lectura = triar(m["texto"])
        except Exception as e:
            lectura = {"error": str(e)}

            log.warning("  fallo en %s: %s", m["archivo"], e)

        resultados.append({**m, **lectura})

    informe = {
        "cuando": time.strftime("%Y-%m-%d %H:%M:%S"),
        "modelo": "qwen (obrero)",
        "mensajes": resultados,
    }

    if guardar:
        escribir_atomico(
            INFORME, json.dumps(informe, ensure_ascii=False, indent=2) + "\n"
        )

    return informe


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    print("=" * 64)
    print("TRIAJE CON QWEN")
    print("=" * 64)

    if not qwen.disponible():
        print("\nNingun runtime local responde. Nada que hacer.")

        raise SystemExit(1)

    print(f"\nmodelos: {', '.join(qwen.modelos()) or '(ninguno)'}\n")

    inicio = time.time()

    informe = triar_pendientes()

    for m in informe["mensajes"]:
        print("-" * 64)
        print(f"{m['archivo']}   {m['hora']}")

        if "error" in m:
            print(f"  ERROR: {m['error']}")

            continue

        print(f"  categoria : {m['categoria'] or '(no la dijo)'}")
        print(f"  urgencia  : {m['urgencia'] or '(no la dijo)'}")
        print(f"  resumen   : {m['resumen']}")
        print(f"  tardo     : {m['segundos']} s")

    print("-" * 64)
    print(f"\n{len(informe['mensajes'])} mensajes en {time.time() - inicio:.1f} s")
    print(f"informe en {INFORME}")
    print("\nFIN_TRIAJE")
