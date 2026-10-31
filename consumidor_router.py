"""Consumidor manual Cola -> Router (T070) + Planificador minimo (T065).

Cierra, para un caso muy acotado, el hueco que quedo tras T067/T044:
router.py demostro que Nexo puede resolver tareas de resumen/extraccion
de principio a fin (clasificar -> ejecutar -> verificar -> fallback a
Gemini -> evidencia), pero no tenia NINGUN consumidor real -- ni la cola
de tareas (nucleo.tareas) ni Telegram lo invocaban nunca; solo lo movia
prueba_router_minimo.py. Este modulo es ESE consumidor, y nada mas.

Que hace
--------
1. Toma UNA tarea de memoria/tareas.json por su id exacto (nunca "la
   siguiente que encuentre", nunca la cola entera).
2. Exige que la tarea sea de Nexo (depende == "ia"), este viva
   (estado "pendiente" o "en_curso") y lleve la etiqueta EXACTA
   "router:auto" en su lista `etiquetas` (campo ya existente en el
   esquema de tareas.json, no se anade ningun campo nuevo). Sin esa
   etiqueta se niega a tocarla -- es la unica condicion que hace que
   las tareas reales de hoy (ninguna la lleva) queden fuera por
   diseno, no por casualidad.
3. Si la tarea ademas lleva una etiqueta "router:claves:clave1,clave2"
   se usan esas claves como `claves_extraccion` (solo hacen falta si
   router.procesar() clasifica el texto como "extraccion"; para
   "resumen" no se necesitan y basta con "router:auto").
4. Llama a router.procesar(texto, claves_extraccion) SIN TOCAR
   router.py -- se reutiliza tal cual (T067/T044), con su propia
   cadena de evidencia en registros/evidencia.jsonl y su propia
   clasificacion/decision de categoria (este modulo no fuerza ninguna
   categoria, router.py sigue siendo el unico que decide resumen vs
   extraccion vs otro).
5. Segun lo que devuelva router.procesar():
   - "OK": la tarea se marca hecha con nucleo.tareas.completar(),
     anotando proveedor, execution_id e intentos en la nota.
   - "ESCALADO": la tarea NO cambia de estado (sigue viva tal cual
     estaba), solo se anota con nucleo.tareas.anotar() el motivo y el
     execution_id, para que un humano o una sesion de Claude decida.

Que NO es
---------
No es un daemon ni un cron ni un watcher: se invoca a mano, una tarea
cada vez, desde la CLI de este archivo o importando consumir_tarea().
No barre la cola buscando trabajo por su cuenta. No anade categorias
nuevas al Router (router.py solo entiende resumen/extraccion/otro,
exactamente igual que antes). No toca canal/bot.py ni Telegram. No
modifica router.py, proveedores.py, nucleo/tareas.py ni
nucleo/registro.py -- los reutiliza tal cual, importados sin cambios.

Planificador minimo (T065, autorizado por Damian sobre este mismo
archivo, alcance estrictamente acotado)
------------------------------------------------------------------
`planificar()` es el unico anadido de T065: pasa de "consumir_tarea(id)
exige que alguien ya sepa que id tocar" a "planificar() elige por su
cuenta cual, entre las tareas ya elegibles, intentar ahora". No decide
prioridad por si mismo -- reutiliza tal cual `nucleo.tareas.listar()`/
`ordenadas()`/`puntuacion()` (ya existente, ya usado en produccion por
`siguiente()` y por la vista `tareas.md`, ya con escalado de urgencia
por fecha limite) para ordenar a las candidatas, y entrega la primera a
`consumir_tarea()` sin ejecutar el Router directamente ni duplicar
ninguna de sus reglas. Candidata = viva (pendiente/en_curso) +
depende=ia + etiqueta "router:auto" -- exactamente el mismo filtro que
ya exige `consumir_tarea()`, reutilizado via `_es_elegible()`. Sin
candidatas, no toca nada y lo dice. Sigue siendo invocacion manual/bajo
demanda: sin daemon, cron, temporizador ni bucle. Ejecuta como maximo
UNA tarea por llamada.
"""

from __future__ import annotations

import sys

import router as router_mod
from nucleo import tareas


ETIQUETA_AUTO = "router:auto"
PREFIJO_CLAVES = "router:claves:"


class TareaNoElegible(Exception):
    """La tarea no cumple la convencion minima para pasar por el Router."""


def _es_elegible(tarea: dict) -> bool:
    return ETIQUETA_AUTO in (tarea.get("etiquetas") or [])


def _claves_extraccion(tarea: dict) -> list[str] | None:
    for etiqueta in tarea.get("etiquetas") or []:
        if etiqueta.startswith(PREFIJO_CLAVES):
            resto = etiqueta[len(PREFIJO_CLAVES):]
            claves = [c.strip() for c in resto.split(",") if c.strip()]

            return claves or None

    return None


def consumir_tarea(tarea_id: str) -> dict:
    """Resuelve UNA tarea concreta a traves del Router, si es elegible.

    Lanza TareaNoElegible (sin tocar la tarea) si no existe, no es de
    Nexo (depende != "ia"), ya esta cerrada, o no lleva la etiqueta
    "router:auto" -- para que un uso accidental sobre una tarea real
    de las ya existentes falle alto y claro en vez de tocarla.

    router.procesar() en si mismo nunca lanza (cualquier fallo termina
    en escalado registrado como evidencia); este consumidor tampoco
    lanza por un fallo del Router, solo por falta de elegibilidad.
    """

    tarea = tareas.buscar(tarea_id)

    if tarea is None:
        raise TareaNoElegible(f"no existe ninguna tarea con id/texto '{tarea_id}'")

    if tarea["depende"] != "ia":
        raise TareaNoElegible(
            f"{tarea['id']} depende de '{tarea['depende']}', no de 'ia' -- "
            "el consumidor solo toca tareas propias de Nexo"
        )

    if tarea["estado"] not in ("pendiente", "en_curso"):
        raise TareaNoElegible(
            f"{tarea['id']} esta en estado '{tarea['estado']}', no viva -- "
            "el consumidor solo toca tareas pendientes o en curso"
        )

    if not _es_elegible(tarea):
        raise TareaNoElegible(
            f"{tarea['id']} no lleva la etiqueta '{ETIQUETA_AUTO}' -- "
            "no es elegible para este consumidor"
        )

    texto = (tarea.get("detalle") or "").strip()

    if not texto:
        raise TareaNoElegible(
            f"{tarea['id']} no tiene contenido en 'detalle' para procesar"
        )

    claves = _claves_extraccion(tarea)

    resultado = router_mod.procesar(texto, claves_extraccion=claves)

    # T724: solo se actua sobre un resultado que cumple el contrato del Router; lo demas se anota y NO se cierra
    invalido = _fuera_de_contrato(resultado)
    if invalido:
        tareas.anotar(tarea["id"], f"Router: resultado fuera de contrato ({invalido}); no se cierra la tarea")
        return {"tarea_id": tarea["id"], "estado": "INVALIDO", "motivo": invalido,
                "execution_id": resultado.get("execution_id") if isinstance(resultado, dict) else None}

    if resultado["estado"] == "OK":
        nota = (
            f"Resuelta automaticamente por el Router (execution_id="
            f"{resultado['execution_id']}, categoria={resultado['categoria']}, "
            f"proveedor={resultado['proveedor']}, "
            f"intentos={resultado.get('intentos')}): {resultado['texto']}"
        )

        tareas.completar(tarea["id"], nota=nota, despues="nada: resuelta por el Router, sin seguimiento",   # T1010
                         cierre=tareas.cierre_ok(evidencia=nota))
    else:
        nota = (
            f"Router escalado (execution_id={resultado['execution_id']}, "
            f"categoria={resultado['categoria']}): {resultado['motivo']}"
        )

        tareas.anotar(tarea["id"], nota)

    return {"tarea_id": tarea["id"], **resultado}


# T724: estados que devuelve router.procesar() y las claves que trae cada uno
CONTRATO_ROUTER = {
    "OK": ("execution_id", "categoria", "proveedor", "texto"),
    "ESCALADO": ("execution_id", "categoria", "motivo"),
}


def _fuera_de_contrato(resultado) -> str:
    """'' si el resultado del Router se puede usar; si no, por que."""
    if not isinstance(resultado, dict):
        return f"no es un dict ({type(resultado).__name__})"
    estado = resultado.get("estado")
    if estado not in CONTRATO_ROUTER:
        return f"estado desconocido {estado!r}"
    faltan = [k for k in CONTRATO_ROUTER[estado] if k not in resultado]
    if faltan:
        return f"estado {estado} sin {', '.join(faltan)}"
    if estado == "OK" and not str(resultado.get("texto") or "").strip():
        return "estado OK con texto vacio"
    return ""


def candidatas_elegibles() -> list[dict]:
    """Tareas vivas, de Nexo, elegibles para el Router -- YA ORDENADAS.

    Reutiliza `nucleo.tareas.listar(depende="ia")` (que ya devuelve el
    resultado ordenado por `ordenadas()`/`puntuacion()`, con el mismo
    escalado de urgencia por fecha limite que usa el resto de Nexo) y
    solo filtra encima: estado vivo en el sentido estricto de
    `consumir_tarea()` (pendiente/en_curso, no "esperando"/"bloqueada"/
    "aparcada") y la etiqueta "router:auto" via `_es_elegible()`.
    Filtrar una lista ya ordenada conserva el orden relativo -- no hace
    falta volver a ordenar ni tocar `puntuacion()`.
    """

    vivas = tareas.listar(depende="ia")

    return [
        t for t in vivas
        if t["estado"] in ("pendiente", "en_curso") and _es_elegible(t)
        and (t.get("detalle") or "").strip()     # T723: lo mismo que exige consumir_tarea()
    ]


def planificar() -> dict | None:
    """Elige la UNICA tarea elegible de mayor prioridad y la resuelve.

    No decide prioridad por su cuenta: `candidatas_elegibles()` ya
    llega ordenada por el motor de `nucleo.tareas` (sin duplicar esa
    logica aqui). Entrega la primera candidata a `consumir_tarea()` --
    no llama a `router.procesar()` directamente, no repite ninguna de
    sus reglas.

    Devuelve el dict de `consumir_tarea()` para la tarea elegida (una
    sola, nunca mas de una por llamada), o None si no hay ninguna
    candidata -- en ese caso no se toca ninguna tarea ni se invoca el
    Router en absoluto.
    """

    candidatas = candidatas_elegibles()

    if not candidatas:
        return None

    elegida = candidatas[0]

    return consumir_tarea(elegida["id"])


def _cli(argv: list[str]) -> int:
    if not argv:
        print(__doc__)

        return 2

    if argv[0] == "planificar":
        resultado = planificar()

        if resultado is None:
            print(
                "SIN CANDIDATOS: ninguna tarea viva (pendiente/en_curso), "
                f"depende=ia, con la etiqueta '{ETIQUETA_AUTO}' -- no se ha "
                "tocado ninguna tarea"
            )

            return 1

        print(
            f"planificada {resultado['tarea_id']}  "
            f"categoria={resultado.get('categoria')}  "
            f"estado={resultado['estado']}  execution_id={resultado['execution_id']}"
        )

        return 0

    tarea_id = argv[0]

    try:
        resultado = consumir_tarea(tarea_id)
    except TareaNoElegible as e:
        print(f"NO ELEGIBLE: {e}")

        return 1

    print(
        f"{resultado['tarea_id']}  categoria={resultado.get('categoria')}  "
        f"estado={resultado['estado']}  execution_id={resultado['execution_id']}"
    )

    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(_cli(sys.argv[1:]))
