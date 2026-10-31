"""Archivos de la cola de tareas en formato v2 (T1010 paso 2): hot, historial y detalle.

    memoria/tareas.json              solo las NO cerradas (pendiente, en_curso, esperando, bloqueada,
                                     aparcada, propuesta). Es lo que se lee a cada paso.
    memoria/tareas_historial.jsonl   las cerradas (hecha, descartada): una linea por tarea con el registro
                                     completo y un `resumen` de 1 linea. Primera linea: cabecera con la
                                     version del historial.
    memoria/tareas_detalle/<id>.json lo pesado de una tarea: notas antiguas, conversaciones, descarte y
                                     fallos_turno. No se carga salvo que alguien lo pida.

Todo cuelga de la carpeta de `tareas.json` (los tests la redirigen a tmp_path), nunca de rutas fijas.

Coherencia entre archivos: quien escribe pone PRIMERO el historial (con version nueva) y DESPUES
tareas.json (que anota la `version_historial` que espera). Quien lee comprueba que casan y reintenta si
no (otro proceso estaba a medias). Los mutadores ya van bajo `nucleo.candado`, asi que dos escritores a
la vez no se dan.

Este modulo no importa `nucleo.tareas`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from nucleo.escritura import escribir_atomico

REINTENTOS_LECTURA = 8
ESPERA_LECTURA_S = 0.05


def ruta_historial(almacen: Path) -> Path:
    return Path(almacen).parent / "tareas_historial.jsonl"


def dir_detalle(almacen: Path) -> Path:
    return Path(almacen).parent / "tareas_detalle"


def ruta_privada(almacen: Path, tid: str) -> Path:
    return Path(almacen).parent / "perfil_privado" / "tareas" / f"{tid}.md"


# ------------------------------------------------------------------ historial

def leer_historial(almacen: Path) -> tuple[int, list[dict]]:
    """(version, registros). Sin archivo: (0, []). Una linea rota se salta (no se pierde el resto)."""
    ruta = ruta_historial(almacen)
    if not ruta.is_file():
        return 0, []
    version = 0
    regs: list[dict] = []
    for i, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines()):
        if not linea.strip():
            continue
        try:
            d = json.loads(linea)
        except ValueError:
            continue
        if i == 0 and isinstance(d, dict) and "_historial" in d:
            version = int(d["_historial"])
        elif isinstance(d, dict) and d.get("id"):
            regs.append(d)
    return version, regs


def texto_historial(version: int, registros: list[dict]) -> str:
    lineas = [json.dumps({"_historial": version}, ensure_ascii=False)]
    lineas += [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in registros]
    return "\n".join(lineas) + "\n"


def escribir_historial(almacen: Path, version: int, registros: list[dict]) -> None:
    ruta = ruta_historial(almacen)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(ruta, texto_historial(version, registros))


def leer_coherente(almacen: Path) -> tuple[dict, list[dict]]:
    """(contenido de tareas.json, registros del historial) comprobando que casan. Revienta si tareas.json esta roto."""
    datos: dict = {}
    regs: list[dict] = []
    for _ in range(REINTENTOS_LECTURA):
        datos = json.loads(Path(almacen).read_text(encoding="utf-8"))
        espera = datos.get("version_historial")
        version, regs = leer_historial(almacen)
        if espera is None or int(espera) == version:
            return datos, regs
        time.sleep(ESPERA_LECTURA_S)
    return datos, regs     # no casaron: se sigue con lo que hay (la union por id lo aguanta)


# ------------------------------------------------------------------ detalle

def leer_detalle(almacen: Path, tid: str) -> dict:
    ruta = dir_detalle(almacen) / f"{tid}.json"
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def escribir_detalle(almacen: Path, tid: str, datos: dict) -> None:
    carpeta = dir_detalle(almacen)
    carpeta.mkdir(parents=True, exist_ok=True)
    escribir_atomico(carpeta / f"{tid}.json", json.dumps(datos, ensure_ascii=False, indent=1) + "\n")


def fusionar_detalle(almacen: Path, tid: str, **campos) -> dict:
    """Actualiza campos del detalle de `tid`. Un valor None quita el campo. Devuelve el detalle resultante."""
    d = leer_detalle(almacen, tid)
    antes = json.dumps(d, sort_keys=True, ensure_ascii=False)
    for k, v in campos.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    if json.dumps(d, sort_keys=True, ensure_ascii=False) != antes:
        escribir_detalle(almacen, tid, d)
    return d


def anadir_notas_antiguas(almacen: Path, tid: str, notas: list[dict]) -> None:
    """Las notas que dejan de ser vigentes se guardan (cronologicas, sin duplicar) en el detalle."""
    if not notas:
        return
    d = leer_detalle(almacen, tid)
    previas = d.get("notas_antiguas") or []
    vistas = {(n.get("cuando"), n.get("texto")) for n in previas}
    nuevas = [n for n in notas if (n.get("cuando"), n.get("texto")) not in vistas]
    if nuevas:
        d["notas_antiguas"] = previas + nuevas
        escribir_detalle(almacen, tid, d)


def tamanos(almacen: Path) -> dict:
    """Bytes de cada parte (para el informe de la migracion)."""
    a = Path(almacen)
    h = ruta_historial(a)
    det = dir_detalle(a)
    archivos = list(det.glob("*.json")) if det.is_dir() else []
    return {
        "tareas.json": a.stat().st_size if a.is_file() else 0,
        "tareas_historial.jsonl": h.stat().st_size if h.is_file() else 0,
        "tareas_detalle": sum(f.stat().st_size for f in archivos),
        "tareas_detalle_archivos": len(archivos),
    }
