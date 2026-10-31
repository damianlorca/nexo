"""Registro estructurado. Una linea por evento, legible y greppable."""

from __future__ import annotations

import json
import logging
import logging.handlers
import time
from pathlib import Path

from nucleo.config import RAIZ


CARPETA = RAIZ / "registros"

_configurado = False
LOG_MAX_BYTES = 50 * 1024 ** 2


def _preparar() -> None:
    global _configurado

    if _configurado:
        return

    CARPETA.mkdir(parents=True, exist_ok=True)

    archivo = CARPETA / f"agente_{time.strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)-14s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            # T708: tope por archivo (un bucle de log no puede llenar el disco); 3 copias antiguas
            logging.handlers.RotatingFileHandler(archivo, maxBytes=LOG_MAX_BYTES, backupCount=3, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    _configurado = True


def logger(nombre: str) -> logging.Logger:
    _preparar()

    return logging.getLogger(nombre)


def traza(evento: str, **datos) -> None:
    """Evento estructurado a registros/trazas.jsonl.

    Sirve para que el cerebro pueda releer que ha pasado sin
    tener que interpretar texto libre.
    """

    CARPETA.mkdir(parents=True, exist_ok=True)

    linea = {
        "t": time.strftime("%Y-%m-%d %H:%M:%S"),
        "evento": evento,
        **datos,
    }

    destino: Path = CARPETA / "trazas.jsonl"

    with destino.open("a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")


def aislar(carpeta: str | Path | None = None) -> Path:
    """T198: para las suites prueba_* sueltas (pytest ya lo hace en conftest.py).

    Manda log, trazas y evidencia a una carpeta temporal para que un 401 simulado no deje un
    'TOKEN INVALIDO' falso en registros/agente_<fecha>.log. Llamar ANTES de importar canal.bot;
    si el log ya estaba abierto en la carpeta real, se reabre en la nueva.
    """
    global CARPETA, EVIDENCIA, CANDADO_EVIDENCIA, _configurado

    import tempfile

    base = Path(carpeta) if carpeta else Path(tempfile.mkdtemp(prefix="nexo_prueba_registros_"))
    base.mkdir(parents=True, exist_ok=True)
    CARPETA = base
    EVIDENCIA = base / "evidencia.jsonl"
    CANDADO_EVIDENCIA = base / ".candado_evidencia.lock"

    if _configurado:
        raiz = logging.getLogger()
        formato = None
        for h in [h for h in raiz.handlers if isinstance(h, logging.FileHandler)]:
            formato = formato or h.formatter
            raiz.removeHandler(h)
            h.close()
        nuevo = logging.FileHandler(base / f"agente_{time.strftime('%Y%m%d')}.log", encoding="utf-8")
        nuevo.setFormatter(formato)
        raiz.addHandler(nuevo)

    return base


# ------------------------------------------------- Pieza 1: registro de evidencia
#
# Lo de arriba (logger(), traza()) sigue exactamente igual y en produccion
# (canal/bot.py, manos/shell.py, etc. lo siguen usando tal cual). Esto es
# NUEVO y NO esta conectado a ningun sitio de produccion todavia -- es la
# pieza de codigo que decide Damian el 13/09: extender este modulo (no uno
# nuevo), sin cablear manos/shell.py ni manos/servidor_mcp.py todavia, sin
# migrar los hechos antiguos de memoria/estado.json, sin pasar a blindado.
#
# Fuente de diseno: documentacion/MASTER_REQUIREMENTS_CHECKLIST.md (seccion
# 23, re-evaluacion de Pieza 1) y las notas de T054 en memoria/tareas.json.
# Objetivo: que una cadena de ejecucion completa (quien propuso, quien
# valido, que tool corrio, quien verifico, con que resultado) se pueda
# reconstruir leyendo este archivo, sin tener que interpretar texto libre.
#
# Un evento de evidencia es UNA fila de registros/evidencia.jsonl (archivo
# separado de trazas.jsonl a proposito: trazas.jsonl sigue siendo el log
# plano ya usado en produccion, con su propio esquema libre; evidencia.jsonl
# es el esquema rico y con campos fijos que necesita el resto de la
# arquitectura -- Router, pipeline multi-IA, evidence_packet, watchdog).

import uuid
from nucleo.candado import bloqueo

EVIDENCIA = CARPETA / "evidencia.jsonl"
CANDADO_EVIDENCIA = RAIZ / "registros" / ".candado_evidencia.lock"

# Vocabulario cerrado. Un valor fuera de estos conjuntos es casi siempre un
# error de quien llama (typo, o esta inventando una fase/rol nuevo sin
# pasar por una decision consciente) -- se rechaza pronto en vez de dejar
# basura silenciosa en el registro.
FASES_VALIDAS = frozenset({
    "peticion", "decision", "propuesta", "validacion", "permiso", "tool",
    "ejecucion", "verificacion", "resultado", "error", "reintento",
    "escalado",
    # "progreso": fase nueva (13/09) para operaciones largas -- trabajo
    # local continuo (T063) o cualquier ejecucion que dura minutos/horas y
    # necesita dejar constancia de avance sin cerrar el execution_id.
    "progreso",
})

# Las 5 etiquetas de origen ya fijadas en FASE4_B/FASE4_I, en formato de
# codigo (sin espacios/mayusculas) para que sea comodo filtrar y comparar.
ORIGENES_VALIDOS = frozenset({
    "nexo_decidio", "ia_externa_propuso", "nexo_acepto", "tool_ejecuto",
    "verificador_confirmo",
})

# Roles fijados por Damian el 13/09 (T054), para Pieza 1 y para el futuro
# pipeline multi-IA / evidence_packet.
ROLES_VALIDOS = frozenset({
    "planner", "worker", "reviewer", "verifier", "synthesizer",
    "final_specialist",
})

# Escala de confianza de 5 grados fijada por Damian el 13/09: "revisado por
# varias IAs" NO es lo mismo que "verificado". En mayusculas porque asi la
# escribio el, y para que no se confunda con el campo libre `resultado`.
VERIFICACION_VALIDA = frozenset({
    "GENERATED", "REVIEWED", "CONSENSUS", "EVIDENCE_VERIFIED",
    "EXPERIMENTALLY_VALIDATED",
})


def nuevo_execution_id() -> str:
    """Identificador corto y unico para una cadena de ejecucion nueva."""

    return uuid.uuid4().hex[:12]


def registrar_evidencia(
    fase: str,
    *,
    execution_id: str | None = None,
    parent_execution_id: str | None = None,
    actor: str | None = None,
    rol: str | None = None,
    proveedor: str | None = None,
    modelo: str | None = None,
    tool: str | None = None,
    accion: str | None = None,
    estado: str | None = None,
    duracion: float | None = None,
    error: str | None = None,
    reintento: int | None = None,
    escalado: bool | None = None,
    verificacion: str | None = None,
    resultado: str | None = None,
    progreso: str | None = None,
) -> dict:
    """Anade una entrada de evidencia a registros/evidencia.jsonl.

    Devuelve el `execution_id` usado (generado solo si no se paso uno) para
    que quien llama pueda encadenar las siguientes fases de la misma
    ejecucion, o usarlo como `parent_execution_id` de una ejecucion hija
    (p.ej. varias IAs trabajando bajo la misma peticion original).

    Todos los campos salvo `fase` son opcionales: cada fase de la cadena
    de ejecucion (PROPUESTA->VALIDACION->PERMISOS->TOOL->EJECUCION->
    VERIFICACION->RESULTADO, mas PROGRESO para operaciones largas) rellena
    solo lo que le corresponde -- una fase "tool" no tiene por que traer
    `verificacion`, una fase "verificacion" no tiene por que traer `tool`.
    Los campos no usados no se escriben (igual que traza() ya hacia de
    facto), para que el archivo siga siendo compacto y greppable.

    No se conecta a manos/shell.py ni a manos/servidor_mcp.py todavia
    (decision explicita de Damian, 13/09) -- por ahora es una funcion de
    libreria, pensada primero para la prueba aislada de esta misma pieza y
    despues para quien decida usarla desde un sitio de produccion concreto.
    """

    if fase not in FASES_VALIDAS:
        raise ValueError(
            f"fase de evidencia desconocida: {fase!r}. Validas: "
            f"{sorted(FASES_VALIDAS)}"
        )

    if actor is not None and actor not in ORIGENES_VALIDOS:
        raise ValueError(
            f"actor/origen desconocido: {actor!r}. Validos: "
            f"{sorted(ORIGENES_VALIDOS)}"
        )

    if rol is not None and rol not in ROLES_VALIDOS:
        raise ValueError(
            f"rol desconocido: {rol!r}. Validos: {sorted(ROLES_VALIDOS)}"
        )

    if verificacion is not None and verificacion not in VERIFICACION_VALIDA:
        raise ValueError(
            f"nivel de verificacion desconocido: {verificacion!r}. Validos: "
            f"{sorted(VERIFICACION_VALIDA)}"
        )

    execution_id = execution_id or nuevo_execution_id()

    entrada = {
        "t": time.strftime("%Y-%m-%d %H:%M:%S"),
        "execution_id": execution_id,
        "parent_execution_id": parent_execution_id,
        "fase": fase,
        "actor": actor,
        "rol": rol,
        "proveedor": proveedor,
        "modelo": modelo,
        "tool": tool,
        "accion": accion,
        "estado": estado,
        "duracion": duracion,
        "error": error,
        "reintento": reintento,
        "escalado": escalado,
        "verificacion": verificacion,
        "resultado": resultado,
        "progreso": progreso,
    }

    # Quitar campos no usados (None) -- deliberado, ver docstring de arriba.
    entrada = {k: v for k, v in entrada.items() if v is not None}

    CARPETA.mkdir(parents=True, exist_ok=True)

    with bloqueo(CANDADO_EVIDENCIA):
        with EVIDENCIA.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entrada, ensure_ascii=False) + "\n")

    return entrada


def leer_evidencia(
    execution_id: str | None = None,
    parent_execution_id: str | None = None,
) -> list[dict]:
    """Lee registros/evidencia.jsonl, filtrando si se pide.

    Sin filtros, devuelve todas las entradas en orden. Con `execution_id`,
    devuelve solo las fases de esa cadena concreta -- esto es lo que
    permite "reconstruir una cadena completa de ejecucion" a partir del
    archivo. Con `parent_execution_id`, devuelve todas las ejecuciones
    hijas de una misma peticion (el patron que necesitara el futuro
    evidence_packet para agrupar lo que hicieron varias IAs sobre el mismo
    encargo).

    No falla si el archivo no existe todavia (cadena vacia, no error).
    """

    if not EVIDENCIA.is_file():
        return []

    resultado: list[dict] = []

    with EVIDENCIA.open(encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()

            if not linea:
                continue

            entrada = json.loads(linea)

            if execution_id is not None and entrada.get("execution_id") != execution_id:
                continue

            if (
                parent_execution_id is not None
                and entrada.get("parent_execution_id") != parent_execution_id
            ):
                continue

            resultado.append(entrada)

    return resultado
