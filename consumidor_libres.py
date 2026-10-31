"""Consumidor Mensajes sueltos de Telegram -> tareas.json (Ronda 28, T082/modo bloque).

Cierra el hueco real que dejaba el "modo bloque" descrito en
documentacion/handoff_ronda25/09_DISENO_APP_ORDENES.md: un mensaje
suelto de Telegram (uno que no responde a nada y no es un comando)
hoy se guarda en canal/entrada/libre_*.json y ahi se queda -- lo
clasifica extremidades.triaje (categoria/urgencia/resumen) pero nadie
convierte esa clasificacion en una tarea real de memoria/tareas.json.
Eso lo tenia que hacer un turno de Claude a mano, leyendo los sueltos
uno a uno (evidencia real: 4 archivos libre_*.json de ronda 25/14-09
seguian sin tocar hasta esta ronda).

Que hace
--------
1. Toma los libre_*.json pendientes (reutiliza
   extremidades.triaje.mensajes_pendientes(), sin reimplementar el
   glob).
2. Clasifica cada uno con extremidades.triaje.triar() (reutilizado tal
   cual: categoria in {tarea, dato, respuesta, charla}, urgencia,
   resumen). No se duplica ninguna logica de clasificacion aqui.
3. Si categoria == "tarea": la da de alta en memoria/tareas.json via
   nucleo.tareas.anadir() (API ya existente, con su propio candado
   entre procesos -- no se toca el almacen a mano). Titulo = resumen
   de Qwen; detalle = texto original completo (nunca se pierde el
   texto exacto de Damian); etiquetas ["origen:telegram_libre",
   "clasificado_auto"] para que se vea a simple vista que NO la
   redacto Damian a mano; urgencia numerica derivada del label de
   Qwen (urgente=4, no urgente=2, si no dijo nada=3 por defecto,
   igual que el resto de campos de nucleo.tareas). SIEMPRE con una
   nota que dice de donde salio y con que confianza, nunca como un
   hecho consumado sin mas.
4. Si categoria != "tarea" (dato/respuesta/charla) o Qwen no supo
   clasificar: NO se crea ninguna tarea -- se deja constancia en el
   resultado de la llamada para que quede trazable, pero el mensaje
   no se convierte en trabajo. Caso real que prueba esto: uno de los
   4 sueltos pendientes decia literalmente "no quiero que lo apuntes
   como tarea, quiero que me contestes" -- exactamente el caso que
   este paso tiene que dejar pasar sin tocar tareas.json.
5. Cada libre_*.json procesado se renombra a *.json.procesado (mismo
   patron que ya usa canal/bot.py con canal/salida/*.json.enviado):
   no se borra (Nexo no borra, archiva/marca), y deja de aparecer en
   mensajes_pendientes() porque el glob es libre_*.json exacto.

Que NO hace, a proposito
-------------------------
No fusiona con una tarea ya existente aunque el tema se parezca --
intentar adivinar cual es la misma tarea con texto libre es mas
peligroso que crear una tarea de mas (que se puede fusionar a mano
despues); crear un duplicado nunca corrompe una tarea real. No decide
importancia/dificultad/coste -- se quedan en su valor por defecto de
nucleo.tareas (3/3/2), porque Qwen no los estima y forzar un numero
inventado seria peor que dejar el defecto neutro. No toca router.py,
canal/bot.py ni nucleo/permisos.py -- solo lee canal/entrada/ y
escribe en memoria/tareas.json a traves de la API ya existente y
probada de nucleo.tareas. No se invoca solo: es CLI/import manual,
igual que consumidor_router.py (T070) -- conectarlo a la escucha en
vivo de canal/bot.py es un paso aparte, posterior, y solo si Damian
lo confirma tras ver como se comporta con datos reales.
"""

from __future__ import annotations

import sys
from pathlib import Path

from extremidades import triaje
from nucleo import tareas
from nucleo.config import RAIZ
from nucleo.registro import logger

log = logger("consumidor_libres")

ENTRADA = RAIZ / "canal" / "entrada"

# Label de urgencia de Qwen (triaje.URGENCIAS) -> numero 1-5 de
# nucleo.tareas. Solo dos valores posibles ademas de "no lo dijo":
# no se inventa una escala mas fina de la que Qwen realmente da.
URGENCIA_DESDE_LABEL = {"urgente": 4, "no urgente": 2}
URGENCIA_DEFECTO = 3


def _urgencia_numerica(label: str) -> int:
    return URGENCIA_DESDE_LABEL.get((label or "").strip().lower(), URGENCIA_DEFECTO)


def _marcar_procesado(nombre_archivo: str) -> None:
    origen = ENTRADA / nombre_archivo

    if not origen.is_file():
        return

    destino = origen.with_suffix(origen.suffix + ".procesado")
    origen.rename(destino)


def procesar_uno(mensaje: dict) -> dict:
    """Clasifica UN mensaje suelto y, si toca, lo convierte en tarea.

    `mensaje` es una de las entradas que devuelve
    triaje.mensajes_pendientes() ({"archivo", "hora", "texto"}).
    Nunca lanza: cualquier fallo de Qwen se registra como "sin
    clasificar" y el archivo NO se marca procesado (se reintenta en
    la siguiente pasada), igual que el resto de Nexo no da nada por
    perdido sin evidencia.
    """

    archivo = mensaje["archivo"]
    texto = mensaje.get("texto", "")

    try:
        lectura = triaje.triar(texto)
    except Exception as e:  # noqa: BLE001 - un fallo de Qwen no debe tirar el lote
        log.warning("no se pudo clasificar %s: %s", archivo, e)

        return {
            "archivo": archivo,
            "resultado": "ERROR_CLASIFICACION",
            "detalle": str(e),
        }

    categoria = (lectura.get("categoria") or "").strip().lower()
    urgencia_label = lectura.get("urgencia") or ""
    resumen = (lectura.get("resumen") or "").strip()

    if categoria != "tarea":
        _marcar_procesado(archivo)

        return {
            "archivo": archivo,
            "resultado": "NO_ES_TAREA",
            "categoria": categoria or "(sin clasificar)",
            "resumen": resumen,
        }

    titulo = (resumen or texto)[:120].strip() or "(mensaje de Telegram sin texto)"

    nota = (
        f"Creada automaticamente por consumidor_libres.py a partir de un "
        f"mensaje suelto de Telegram ({mensaje.get('hora', '?')}, "
        f"{archivo}). Clasificacion de Qwen: categoria=tarea, "
        f"urgencia={urgencia_label or '(no la dijo)'}. "
        "PENDIENTE_DE_REVISION: clasificacion automatica, no confirmada "
        "por Damian ni por Claude -- revisar titulo/detalle/prioridad."
    )

    t = tareas.anadir(
        titulo,
        detalle=texto,
        depende="ia",
        urgencia=_urgencia_numerica(urgencia_label),
        etiquetas=["origen:telegram_libre", "clasificado_auto"],
        notas=[{"cuando": mensaje.get("hora", ""), "texto": nota}],
    )

    _marcar_procesado(archivo)

    log.info("tarea %s creada desde %s (categoria=tarea)", t["id"], archivo)

    return {
        "archivo": archivo,
        "resultado": "TAREA_CREADA",
        "tarea_id": t["id"],
        "titulo": t["titulo"],
    }


def procesar_pendientes() -> dict:
    """Pasa por TODOS los libre_*.json pendientes. Devuelve un resumen.

    No es un daemon ni un cron: se invoca a mano (CLI o import), igual
    que consumidor_router.py. Cada mensaje se procesa de forma
    independiente -- un fallo en uno no bloquea el resto.
    """

    pendientes = triaje.mensajes_pendientes()

    log.info("consumidor_libres: %d mensajes sueltos pendientes", len(pendientes))

    resultados = [procesar_uno(m) for m in pendientes]

    resumen = {
        "total": len(resultados),
        "tareas_creadas": [
            r["tarea_id"] for r in resultados if r["resultado"] == "TAREA_CREADA"
        ],
        "no_es_tarea": [
            r["archivo"] for r in resultados if r["resultado"] == "NO_ES_TAREA"
        ],
        "sin_clasificar": [
            r["archivo"]
            for r in resultados
            if r["resultado"] == "ERROR_CLASIFICACION"
        ],
        "detalle": resultados,
    }

    return resumen


def _cli(argv: list[str]) -> int:
    from extremidades import qwen

    if not qwen.disponible():
        print("Ningun runtime local (Qwen) responde. Nada que hacer.")

        return 1

    resumen = procesar_pendientes()

    print(f"Procesados: {resumen['total']}")
    print(f"Tareas creadas: {resumen['tareas_creadas'] or '(ninguna)'}")
    print(f"No eran tarea (dato/respuesta/charla): {resumen['no_es_tarea'] or '(ninguno)'}")
    print(f"Sin clasificar (error, reintentar despues): {resumen['sin_clasificar'] or '(ninguno)'}")

    for r in resumen["detalle"]:
        print(f"  - {r}")

    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(_cli(sys.argv[1:]))
