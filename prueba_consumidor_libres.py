"""Prueba de consumidor_libres.py (Ronda 28, T082/modo bloque).

Cubre procesar_uno()/procesar_pendientes() con
extremidades.triaje.triar() y nucleo.tareas.anadir() mockeados
(rapido, deterministico, sin gastar Qwen de verdad ni tocar
memoria/tareas.json). El extremo real (Qwen clasificando texto de
verdad, tareas.anadir() escribiendo en el almacen real) ya se
verifico esta misma ronda contra los 4 libre_*.json que llevaban
pendientes desde el 14/09 -- ese pase real encontro y sirvio para
corregir un bug real de nucleo.tareas.render_md() (notas guardadas
como string en vez de {cuando,texto}), documentado en
memoria/tareas.json (notas de T076-T082) y en el commit de esta
ronda. No se repite aqui una llamada real a Qwen para no gastar
tiempo/tokens en algo ya demostrado con evidencia real.
"""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import logging  # noqa: E402
logging.disable(logging.INFO)

import consumidor_libres as cl  # noqa: E402

SALIDA = RAIZ / "registros" / "prueba_consumidor_libres.txt"
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


anotar(f"CONSUMIDOR_LIBRES (Ronda 28)  {time.strftime('%Y-%m-%d %H:%M:%S')}")
anotar("=" * 60)


anotar("\n1. _urgencia_numerica(): mapea el label de Qwen a 1-5")

comprobar("urgente -> 4", cl._urgencia_numerica("urgente") == 4)
comprobar("no urgente -> 2", cl._urgencia_numerica("no urgente") == 2)
comprobar("vacio/desconocido -> defecto 3", cl._urgencia_numerica("") == 3)
comprobar("case-insensitive", cl._urgencia_numerica("URGENTE") == 4)


anotar("\n2. procesar_uno(): categoria='tarea' -> crea la tarea y marca procesado")

try:
    lectura_falsa = {
        "categoria": "tarea",
        "urgencia": "urgente",
        "resumen": "Revisar el recibo de la luz",
        "segundos": 1.2,
    }
    tarea_falsa = {"id": "T999", "titulo": "Revisar el recibo de la luz"}
    mensaje = {"archivo": "libre_falso1.json", "hora": "2026-09-22 10:00:00",
               "texto": "acuerdate de revisar el recibo de la luz de este mes"}

    with mock.patch("consumidor_libres.triaje.triar", return_value=lectura_falsa) as triar_falso, \
         mock.patch("consumidor_libres.tareas.anadir", return_value=tarea_falsa) as anadir_falso, \
         mock.patch("consumidor_libres._marcar_procesado") as marcar_falso:
        r = cl.procesar_uno(mensaje)

    comprobar("triar() se llama con el texto del mensaje", triar_falso.call_args[0][0] == mensaje["texto"])
    comprobar("resultado TAREA_CREADA", r["resultado"] == "TAREA_CREADA", r)
    comprobar("tarea_id correcto", r.get("tarea_id") == "T999", r)
    comprobar("anadir() se llama con detalle=texto original", anadir_falso.call_args.kwargs.get("detalle") == mensaje["texto"])
    comprobar("etiquetas incluyen origen y clasificado_auto", set(anadir_falso.call_args.kwargs.get("etiquetas", [])) == {"origen:telegram_libre", "clasificado_auto"})
    comprobar("urgencia numerica derivada (urgente->4)", anadir_falso.call_args.kwargs.get("urgencia") == 4)
    comprobar("depende='ia' (nunca crea tareas de Damian sin que el las pida)", anadir_falso.call_args.kwargs.get("depende") == "ia")
    comprobar("la nota queda marcada PENDIENTE_DE_REVISION", "PENDIENTE_DE_REVISION" in anadir_falso.call_args.kwargs.get("notas", [{}])[0].get("texto", ""))
    comprobar("se marca el archivo como procesado", marcar_falso.call_count == 1)
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 2:")
    anotar(traceback.format_exc())


anotar("\n3. procesar_uno(): categoria != 'tarea' -> NO crea tarea, si marca procesado")
anotar("   (caso real de esta ronda: 'no quiero que lo apuntes como tarea, quiero que me contestes')")

try:
    lectura_falsa = {
        "categoria": "respuesta",
        "urgencia": "no urgente",
        "resumen": "Quiere que le conteste, no que se apunte como tarea",
        "segundos": 0.9,
    }
    mensaje = {"archivo": "libre_falso2.json", "hora": "2026-09-22 10:05:00",
               "texto": "no quiero que lo apuntes como tarea, quiero que me contestes"}

    with mock.patch("consumidor_libres.triaje.triar", return_value=lectura_falsa), \
         mock.patch("consumidor_libres.tareas.anadir") as anadir_falso, \
         mock.patch("consumidor_libres._marcar_procesado") as marcar_falso:
        r = cl.procesar_uno(mensaje)

    comprobar("resultado NO_ES_TAREA", r["resultado"] == "NO_ES_TAREA", r)
    comprobar("tareas.anadir() NUNCA se llama", anadir_falso.call_count == 0)
    comprobar("se marca el archivo como procesado igualmente", marcar_falso.call_count == 1)
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 3:")
    anotar(traceback.format_exc())


anotar("\n4. procesar_uno(): Qwen falla -> ERROR_CLASIFICACION, NO se marca procesado (se reintenta)")

try:
    mensaje = {"archivo": "libre_falso3.json", "hora": "2026-09-22 10:10:00", "texto": "algo"}

    with mock.patch("consumidor_libres.triaje.triar", side_effect=RuntimeError("Ollama caido")), \
         mock.patch("consumidor_libres.tareas.anadir") as anadir_falso, \
         mock.patch("consumidor_libres._marcar_procesado") as marcar_falso:
        r = cl.procesar_uno(mensaje)

    comprobar("resultado ERROR_CLASIFICACION", r["resultado"] == "ERROR_CLASIFICACION", r)
    comprobar("no crea tarea", anadir_falso.call_count == 0)
    comprobar("NO se marca procesado (para reintentar en la siguiente pasada)", marcar_falso.call_count == 0)
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 4:")
    anotar(traceback.format_exc())


anotar("\n5. procesar_pendientes(): agrega varios mensajes, cada uno independiente")

try:
    pendientes_falsos = [
        {"archivo": "a.json", "hora": "10:00", "texto": "tarea real"},
        {"archivo": "b.json", "hora": "10:01", "texto": "charla"},
        {"archivo": "c.json", "hora": "10:02", "texto": "rompe"},
    ]

    def _triar_falso(texto):
        if texto == "tarea real":
            return {"categoria": "tarea", "urgencia": "", "resumen": "r"}
        if texto == "charla":
            return {"categoria": "charla", "urgencia": "", "resumen": "c"}
        raise RuntimeError("fallo forzado")

    with mock.patch("consumidor_libres.triaje.mensajes_pendientes", return_value=pendientes_falsos), \
         mock.patch("consumidor_libres.triaje.triar", side_effect=_triar_falso), \
         mock.patch("consumidor_libres.tareas.anadir", return_value={"id": "T999", "titulo": "r"}), \
         mock.patch("consumidor_libres._marcar_procesado"):
        resumen = cl.procesar_pendientes()

    comprobar("total 3", resumen["total"] == 3, resumen)
    comprobar("1 tarea creada", resumen["tareas_creadas"] == ["T999"], resumen)
    comprobar("1 no-tarea", resumen["no_es_tarea"] == ["b.json"], resumen)
    comprobar("1 sin clasificar", resumen["sin_clasificar"] == ["c.json"], resumen)
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 5:")
    anotar(traceback.format_exc())


anotar("\n" + ("TODO VALE" if fallos == 0 else f"{fallos} FALLOS"))
anotar("FIN")

if fallos:
    raise SystemExit(1)
