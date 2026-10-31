"""Cuanto se gasta de plan de Claude: un turno, un modelo, un dia.

Por que existe esto (T029)
---------------------------
Damian midio el 11/09 que el limite real es el SEMANAL, no el de
5 horas, y dejo escrito el orden de medidas de ahorro (menos
despertares, turno de noche en Sonnet no Opus, delegar en Qwen lo
mecanico, agrupar preguntas, respuestas cortas) junto con esto:
"Medir: anotar en el estado el modelo y el numero de turnos de cada
dia, para saber si baja de verdad." Sin medir no se sabe si las
medidas funcionan o si el gasto sigue igual. Este modulo es solo eso:
un contador, no un limitador ni un vigilante.

No es memoria critica (a diferencia de estado.json): si el archivo
aparece corrupto, no merece la pena apartarlo ni recuperar respaldos,
solo se empieza de cero con un aviso por el log. Perder un dia de
estadisticas no pierde memoria del proyecto, perder estado.json si.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from nucleo.candado import bloqueo
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico

ARCHIVO = RAIZ / "memoria" / "uso_diario.json"
CANDADO = RAIZ / "memoria" / ".candado_uso.lock"

# No tiene sentido acumular estadisticas para siempre en un archivo
# que nadie relee mas alla de unas semanas.
DIAS_A_CONSERVAR = 90


def _hoy() -> str:
    return time.strftime("%Y-%m-%d")


def _cargar() -> dict:
    if not ARCHIVO.is_file():
        return {"version": 1, "dias": {}}

    try:
        datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        # Estadistica, no memoria: se empieza de cero en vez de
        # complicar esto con recuperacion de respaldos.
        return {"version": 1, "dias": {}}

    if not isinstance(datos, dict) or not isinstance(datos.get("dias"), dict):
        return {"version": 1, "dias": {}}

    return datos


def _guardar(datos: dict) -> None:
    escribir_atomico(ARCHIVO, json.dumps(datos, ensure_ascii=False, indent=2))


def _podar(datos: dict) -> None:
    """Se queda solo con los ultimos DIAS_A_CONSERVAR dias."""

    dias = datos.get("dias", {})

    if len(dias) <= DIAS_A_CONSERVAR:
        return

    for clave in sorted(dias)[: len(dias) - DIAS_A_CONSERVAR]:
        del dias[clave]


def registrar_turno(modelo: str, origen: str = "") -> dict:
    """Anota un turno de hoy con ese modelo. Bajo candado, una llamada.

    origen es libre (p.ej. "nocturno", "corto", "interactivo") solo
    para poder desglosar mas adelante si hace falta; hoy no se usa
    para nada mas que quedar guardado.
    """

    modelo = (modelo or "?").strip() or "?"

    with bloqueo(CANDADO):
        datos = _cargar()

        dia = datos["dias"].setdefault(_hoy(), {"total": 0, "por_modelo": {}, "origenes": {}})

        dia["total"] += 1
        dia["por_modelo"][modelo] = dia["por_modelo"].get(modelo, 0) + 1

        if origen:
            dia["origenes"][origen] = dia["origenes"].get(origen, 0) + 1

        _podar(datos)
        _guardar(datos)

    return datos


def resumen(dias: int = 7) -> str:
    """Tabla legible de los ultimos `dias` dias, mas recientes primero."""

    datos = _cargar()
    claves = sorted(datos.get("dias", {}), reverse=True)[:dias]

    if not claves:
        return "Sin turnos registrados todavia."

    lineas = []

    for fecha in claves:
        d = datos["dias"][fecha]
        modelos = ", ".join(f"{m}={n}" for m, n in sorted(d.get("por_modelo", {}).items()))
        lineas.append(f"{fecha}: {d.get('total', 0)} turno(s)  [{modelos or 'sin desglose'}]")

    return "\n".join(lineas)


def _cli() -> None:
    if len(sys.argv) < 2:
        print("Uso: python -m nucleo.uso registrar <modelo> [origen]")
        print("     python -m nucleo.uso resumen [dias]")
        return

    accion = sys.argv[1]

    if accion == "registrar":
        if len(sys.argv) < 3:
            print("Uso: python -m nucleo.uso registrar <modelo> [origen]")
            return

        modelo = sys.argv[2]
        origen = sys.argv[3] if len(sys.argv) > 3 else ""

        registrar_turno(modelo, origen)

        print(f"registrado: {modelo}" + (f" ({origen})" if origen else ""))

        return

    if accion == "resumen":
        dias = int(sys.argv[2]) if len(sys.argv) > 2 else 7

        print(resumen(dias))

        return

    print(f"accion desconocida: {accion}")


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    _cli()
