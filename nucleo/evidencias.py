# -*- coding: utf-8 -*-
"""Registro de evidencias por tarea y cierre con verificacion (T160, patron Hermes verify-on-stop).

Regla (Principio de Verdad): ninguna tarea pasa a HECHO Y TESTEADO sin una comprobacion
registrada (comando, test, salida o archivo comprobado). Si al cerrar no hay evidencia, se pide
UNA vez mas; si no llega, la tarea queda HECHO SIN TESTEAR y se anota por que.

- Registro: memoria/evidencias.jsonl (una linea por evidencia, solo se anade). Vive junto a
  tareas.json y sigue a `tareas.ALMACEN`, asi que los tests que redirigen las tareas a una carpeta
  temporal redirigen tambien esto. Lo que parezca un secreto se oculta ANTES de escribir.
- `evaluar(texto)`: una evidencia vale si dice que se probo y que salio; un tick ("ok", "probada",
  "funciona") no vale. Es el mismo minimo de 10 caracteres que ya exige la web.
- `cerrar(...)`: el verify-on-stop. Cierra la tarea y solo la marca testeada si hay evidencia.
- `tareas.verificar()` pasa por `registrar()`: sin evidencia o con un tick suelto ("probada") no
  marca nada (VERIFICAR_ESTRICTO). Con VERIFICAR_ESTRICTO = False el tick se aceptaria como
  evidencia DEBIL, que no cuenta para `cerrar()`.

Distinto de registros/evidencia.jsonl (nucleo.registro): aquello es la traza de cada ejecucion
del router y de manos/ (fases, proveedor, duracion); esto es la prueba de que una TAREA esta hecha.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from nucleo.candado import bloqueo
from nucleo import tareas as T

TIPOS = ("test", "comando", "salida", "archivo", "revision", "manual")
RESULTADOS = ("ok", "fallo")
MIN_CARACTERES = 10          # igual que interfaz/rutas/tareas.py (verificar)
# Estricto desde el 25/09 (Damian delego la decision en N06): un tick ("probada", "ok") tampoco vale en
# tareas.verificar(). False volveria a aceptarlo como evidencia DEBIL, que no cuenta para cerrar().
VERIFICAR_ESTRICTO = True
MAX_SALIDA = 2000            # la salida se recorta: el registro no es un volcado de logs
# Ticks que no dicen que se probo ni que salio. Se comparan sin puntos ni mayusculas.
TICKS = frozenset({"ok", "okay", "vale", "si", "sí", "hecho", "hecha", "listo", "lista", "ya", "va", "funciona",
                   "probado", "probada", "testeado", "testeada", "verificado", "verificada", "comprobado",
                   "comprobada", "test", "tests", "todo ok", "todo bien", "funciona bien", "esta bien"})


class EvidenciaInvalida(ValueError):
    """La evidencia no dice que se probo ni que salio."""


def almacen() -> Path:
    return T.ALMACEN.parent / "evidencias.jsonl"


def _candado() -> Path:
    return T.ALMACEN.parent / ".candado_evidencias.lock"


def _ocultar(s: str) -> str:
    """Tapa lo que parezca un secreto (claves, tokens). Si el ocultador no carga, no se guarda salida."""
    try:
        from interfaz import ocultar
    except Exception:
        return "«salida omitida: ocultador no disponible»" if s else s
    return ocultar.texto(s)


def evaluar(texto: str | None) -> tuple[bool, str]:
    """(vale, motivo). Vale si tiene contenido de verdad; un tick suelto no."""
    limpio = " ".join((texto or "").split())
    if not limpio:
        return False, "sin evidencia"
    if limpio.lower().strip(" .!¡") in TICKS:
        return False, f"'{limpio}' es un tick, no una evidencia: di que se probo y que salio"
    if len(limpio) < MIN_CARACTERES:
        return False, f"evidencia demasiado corta (minimo {MIN_CARACTERES} caracteres): di que se probo y que salio"
    return True, ""


def registrar(tarea_id: str, detalle: str, *, tipo: str = "manual", comando: str = "", salida: str = "",
              resultado: str = "ok", fuente: str = "", debil: bool = False) -> dict:
    """Anade una evidencia a la tarea. Lanza EvidenciaInvalida si no vale y ValueError si la tarea no existe.

    `detalle`: que se probo y que salio, en una frase. `comando`/`salida`: lo ejecutado y su salida real.
    `resultado`: "fallo" tambien se registra (un test en rojo es informacion), pero no cuenta para cerrar.
    `debil=True`: acepta un texto que no pasa evaluar() (pero nunca el vacio) y lo marca como debil.
    """
    if tipo not in TIPOS:
        raise ValueError(f"tipo de evidencia desconocido: {tipo!r}. Validos: {list(TIPOS)}")
    if resultado not in RESULTADOS:
        raise ValueError(f"resultado desconocido: {resultado!r}. Validos: {list(RESULTADOS)}")
    vale, motivo = evaluar(detalle if not (comando or salida) else f"{detalle} {comando} {salida}")
    if not vale and not (debil and " ".join((detalle or "").split())):
        raise EvidenciaInvalida(motivo)
    debil = debil and not vale
    t = T.buscar(tarea_id)
    if t is None or t["id"].lower() != tarea_id.strip().lower():
        raise ValueError(f"la tarea {tarea_id} no existe")
    salida = salida or ""
    entrada = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "tarea": t["id"], "tipo": tipo, "resultado": resultado,
               "detalle": _ocultar(" ".join(detalle.split()))[:500]}
    if comando:
        entrada["comando"] = _ocultar(comando)[:500]
    if salida:
        entrada["salida"] = _ocultar(salida[-MAX_SALIDA:])  # el final: donde pytest pone el resumen
        entrada["recortada"] = len(salida) > MAX_SALIDA
    if fuente:
        entrada["fuente"] = fuente[:80]
    if debil:
        entrada["debil"] = True
    destino = almacen()
    destino.parent.mkdir(parents=True, exist_ok=True)
    with bloqueo(_candado()):
        with destino.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
    return entrada


def de_tarea(tarea_id: str) -> list[dict]:
    """Evidencias de una tarea, en orden. Una linea rota se salta (no tumba la lectura)."""
    destino = almacen()
    if not destino.is_file():
        return []
    buscada = tarea_id.strip().lower()
    salida = []
    for linea in destino.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(linea)
        except ValueError:
            continue
        if isinstance(e, dict) and str(e.get("tarea", "")).lower() == buscada:
            salida.append(e)
    return salida


def validas(tarea_id: str, desde: int = 0) -> list[dict]:
    """Evidencias con resultado ok y no debiles (las que permiten cerrar como HECHO Y TESTEADO).

    `desde`: numero de evidencias (de cualquier tipo) de la tarea que ya habia; solo cuentan las posteriores.
    Por posicion y no por hora: dos cierres en el mismo segundo no se confunden.
    """
    return [e for e in de_tarea(tarea_id)[desde:] if e.get("resultado") == "ok" and not e.get("debil")]


def resumen(e: dict) -> str:
    partes = [f"[{e.get('tipo')}] {e.get('detalle', '')}"]
    if e.get("comando"):
        partes.append(f"$ {e['comando']}")
    if e.get("salida"):
        partes.append("-> " + e["salida"].strip().splitlines()[-1][:200])
    return " ".join(partes)


def cerrar(tarea_id: str, nota: str = "", *, evidencia: str | dict | None = None,
           pedir: Callable[[dict, str], str | dict | None] | None = None, despues: str | dict | None = None) -> dict:
    """Verify-on-stop: cierra la tarea y solo la marca HECHO Y TESTEADO si hay evidencia REGISTRADA.

    `evidencia`: texto o dict con los argumentos de registrar() (detalle, tipo, comando, salida...).
    `pedir(tarea, motivo)`: se llama UNA sola vez si falta evidencia (bot, web, otra IA...). Si no
    devuelve una evidencia valida, la tarea queda HECHO SIN TESTEAR con una nota que lo explica.
    Cuentan solo las evidencias de ESTE cierre (desde que empieza): una prueba de antes de reabrir no vale.

    Devuelve {"tarea", "estado_real", "evidencias", "pedida", "motivo"}.
    """
    t = T.buscar(tarea_id)
    if t is None or t["id"].lower() != tarea_id.strip().lower():
        raise ValueError(f"la tarea {tarea_id} no existe")
    inicio = len(de_tarea(t["id"]))
    T.completar(t["id"], nota, despues=despues or "nada: cierre sin siguiente tarea indicada",   # T1010
                cierre=T.cierre_ok(evidencia=f"Cierre con verify-on-stop, la evidencia se registra a continuacion. {nota}".strip()))
    motivo = _intentar(t["id"], evidencia) if evidencia is not None else "sin evidencia"
    pedida = False
    if not validas(t["id"], desde=inicio) and pedir is not None:
        pedida = True
        motivo = _intentar(t["id"], pedir(T.buscar(t["id"]), motivo))
    buenas = validas(t["id"], desde=inicio)
    if buenas:
        final = T.verificar(t["id"], resumen(buenas[-1]), registrada=True)
        motivo = ""
    else:
        final = T.anotar(t["id"], f"[verify-on-stop] cerrada SIN evidencia ({motivo}"
                                  f"{'; se pidio una vez mas' if pedida else ''}): queda HECHO SIN TESTEAR.")
    return {"tarea": final["id"], "estado_real": T.estado_real(final), "evidencias": len(buenas),
            "pedida": pedida, "motivo": motivo}


def _intentar(tarea_id: str, evidencia: str | dict | None) -> str:
    """Registra la evidencia si vale. Devuelve '' si se registro o el motivo del rechazo."""
    if evidencia is None:
        return "no llego evidencia"
    campos = dict(evidencia) if isinstance(evidencia, dict) else {"detalle": str(evidencia)}
    try:
        registrar(tarea_id, campos.pop("detalle", ""), **campos)
    except EvidenciaInvalida as e:
        return str(e)
    except TypeError as e:
        return f"evidencia mal formada: {e}"
    return ""
