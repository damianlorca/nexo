# -*- coding: utf-8 -*-
"""Lecturas del core para pintar. Solo LEE: las acciones van en rutas/ y llaman al core tal cual."""
from __future__ import annotations

import json
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import proveedores
from interfaz import ocultar
from nucleo import auditor, avisos, enfriamiento, parada, registro, revision, trabajo, uso_proveedores
from nucleo import tareas as T


def estado_parada() -> dict:
    """Estado REAL de la bandera memoria/PARADA_NEXO (se relee en cada llamada, sin cache)."""
    motivo = parada.activa()
    if motivo is None:
        return {"activa": False}
    detalle = {}
    try:
        detalle = json.loads(parada.BANDERA.read_text(encoding="utf-8"))
    except Exception:
        pass  # ilegible o recien borrada: activa() ya lo ha dicho en el motivo
    return {"activa": True, "motivo": motivo, "quien": detalle.get("quien", ""), "cuando": detalle.get("cuando", "")}


# ------------------------------------------------------------------ proveedores
# Los 7 del core (proveedores.py). .estado() es la comprobacion barata (no gasta el modelo),
# pero Qwen/Gemini/ChatGPT hacen una peticion local con timeout de 3-5 s: se lanzan en
# paralelo y el resultado se cachea para no martillear en cada refresco.
# Noche 05/10 (Damian): ClaudeProvider (la API / rutina de Claude Code) ya no sale en la vista; sigue en proveedores.py.
CLASES_PROVEEDORES = ("QwenProvider", "GeminiAPIProvider", "GroqProvider", "NvidiaProvider",
                      "GeminiProvider", "ChatGPTProvider", "ClaudeWebProvider")
CACHE_PROVEEDORES = 30.0

_cache_proveedores: dict = {"cuando": 0.0, "lista": None}
_candado_proveedores = threading.Lock()


def _salud(prov) -> dict:
    nombre = getattr(prov, "nombre", type(prov).__name__)
    try:
        st = prov.estado()
        disponible, motivo = bool(st.get("disponible")), st.get("motivo") or ""
    except Exception as e:
        # Solo el tipo: el mensaje de una excepcion de configuracion podria arrastrar datos.
        return {"nombre": nombre, "salud": "error", "disponible": False,
                "motivo": f"no se pudo comprobar ({type(e).__name__})", "enfriamiento": ""}
    try:
        enfriado = enfriamiento.enfriado(nombre) or ""
    except Exception:
        enfriado = ""
    salud = "disponible" if disponible else ("enfriamiento" if enfriado else "no_disponible")
    if st.get("apagado"):   # T549: interruptor manual de la web
        salud, enfriado = "apagado", ""
    return {"nombre": nombre, "salud": salud, "disponible": disponible, "motivo": motivo, "enfriamiento": enfriado}


def salud_proveedores(max_edad: float = CACHE_PROVEEDORES) -> dict:
    """{"cuando": epoch de la comprobacion, "lista": [...]}. Cacheado `max_edad` segundos."""
    with _candado_proveedores:  # uno comprueba; los demas esperan y se llevan el mismo resultado
        if _cache_proveedores["lista"] is not None and time.time() - _cache_proveedores["cuando"] < max_edad:
            return dict(_cache_proveedores)
        instancias = [getattr(proveedores, c)() for c in CLASES_PROVEEDORES]
        with ThreadPoolExecutor(max_workers=len(instancias)) as ex:
            lista = list(ex.map(_salud, instancias))
        _cache_proveedores.update(cuando=time.time(), lista=lista)
        return dict(_cache_proveedores)


# ----------------------------------------------------------------------- tareas
# Vocabulario del Principio de Verdad (T.estado_real), en el orden en que se leen.
ORDEN_ESTADOS = ("PLANIFICADO", "EN PROCESO", "ESPERANDO", "BLOQUEADO", "APARCADA", "PROPUESTA (sin revisar)",
                 "HECHO SIN TESTEAR", "HECHO Y TESTEADO", "DESCARTADA")


def resumen_tareas() -> dict:
    """Cuantas tareas hay en cada estado real y de quien dependen las vivas. Revienta si
    tareas.json esta roto (T.cargar lo hace a proposito): la vista lo muestra como error."""
    todas = T.cargar()["tareas"]
    por_estado = Counter(T.estado_real(t) for t in todas)
    vivas = [t for t in todas if t["estado"] in T.VIVOS]
    return {
        "total": len(todas),
        "estados": [(e, por_estado[e]) for e in ORDEN_ESTADOS if por_estado[e]]
                   + [(e, c) for e, c in sorted(por_estado.items()) if e not in ORDEN_ESTADOS],
        "depende": [(d, sum(1 for t in vivas if t["depende"] == d)) for d in T.DEPENDENCIAS],
    }


def ultimas_tareas(n: int = 10) -> list[dict]:
    todas = T.cargar()["tareas"]
    recientes = sorted(todas, key=lambda t: t.get("actualizada") or "", reverse=True)[:n]
    return [{"id": t["id"], "titulo": t["titulo"], "estado_real": T.estado_real(t),
             "actualizada": t.get("actualizada") or ""} for t in recientes]


# ------------------------------------------------------------------------ trazas
COLA_TRAZAS = 64 * 1024  # bytes del final de trazas.jsonl que se leen (no el fichero entero)


def _cola(ruta, max_bytes: int) -> list[dict]:
    """Lineas JSON (dicts) de los ultimos max_bytes de `ruta`, en orden de fichero. [] si no existe."""
    try:
        with ruta.open("rb") as f:
            f.seek(0, 2)
            tam = f.tell()
            f.seek(max(0, tam - max_bytes))
            trozo = f.read()
    except OSError:
        return []
    lineas = trozo.split(b"\n")
    if tam > max_bytes:
        lineas = lineas[1:]  # la primera puede venir cortada
    salida = []
    for bruta in lineas:
        try:
            obj = json.loads(bruta.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        if isinstance(obj, dict):
            salida.append(obj)
    return salida


def ultimas_trazas(n: int = 10) -> list[dict]:
    """Las n ultimas lineas de registros/trazas.jsonl, la mas reciente primero (sin secretos)."""
    salida = []
    for obj in reversed(_cola(registro.CARPETA / "trazas.jsonl", COLA_TRAZAS)[-n:]):
        detalle = obj.get("comando") or obj.get("accion") or obj.get("texto") or obj.get("detalle") or ""
        salida.append({"t": str(obj.get("t", "")), "evento": str(obj.get("evento", "")),
                       "detalle": ocultar.texto(str(detalle))[:160]})  # ocultar ANTES de recortar
    return salida


# ----------------------------------------------------------------------- ordenes
def ultimas_ordenes(n: int = 25) -> list[dict]:
    """Ordenes dadas por CUALQUIER via (web, Telegram): son tareas con etiqueta origen:orden_*."""
    todas = [t for t in T.cargar()["tareas"]
             if any(e.startswith("origen:orden_") for e in t.get("etiquetas") or [])]
    todas.sort(key=lambda t: t.get("creada") or "", reverse=True)
    salida = []
    for t in todas[:n]:
        et = t.get("etiquetas") or []
        if "borrador:revisar_claude" in et:
            estado = "BORRADOR (revisar Claude)"
        elif "escalado:claude" in et and t["estado"] in T.VIVOS:
            estado = "PARA CLAUDE"
        else:
            estado = T.estado_real(t)
        borradores = sorted(trabajo.BORRADORES.glob(f"{t['id']}_*.md")) if trabajo.BORRADORES.is_dir() else []
        salida.append({
            "id": t["id"], "titulo": t["titulo"], "estado": estado, "creada": t.get("creada") or "",
            "categoria": next((e[4:] for e in et if e.startswith("cat:")), "?"),
            "canal": next((e[len("origen:orden_"):] for e in et if e.startswith("origen:orden_")), "?"),
            "borrador": borradores[-1].name if borradores else "",
        })
    return salida


def leer_borrador(nombre: str) -> str | None:
    """Contenido de memoria/borradores/<nombre>, o None si no existe o se sale de la carpeta."""
    carpeta = trabajo.BORRADORES.resolve()
    if not nombre or not nombre.endswith(".md"):
        return None
    ruta = (carpeta / nombre).resolve()
    if ruta.parent != carpeta or not ruta.is_file():
        return None  # ..\, rutas absolutas, subcarpetas: fuera
    return ruta.read_text(encoding="utf-8", errors="replace")


# ------------------------------------------------------------------------ tareas
def tarea(id_tarea: str) -> dict | None:
    """La tarea con ese id EXACTO (T.buscar tambien busca por titulo: aqui no sirve)."""
    aguja = (id_tarea or "").strip().lower()
    return next((t for t in T.cargar()["tareas"] if t["id"].lower() == aguja), None)


# ------------------------------------------------------------------- uso
PERIODOS_USO = (1, 7, 30)


def nombres_proveedores() -> list[str]:
    """Los .nombre de los 6 del core (atributo de clase: no hace falta instanciarlos)."""
    return [getattr(proveedores, c).nombre for c in CLASES_PROVEEDORES]


def uso_por_proveedor(dias: int) -> list[dict]:
    """Uso real de los ultimos `dias` dias (nucleo.uso_proveedores.totales). Salen los 6 del core
    aunque no tengan llamadas (0 tambien es un dato) y, al final, cualquier otro del registro."""
    totales = uso_proveedores.totales(dias)
    conocidos = nombres_proveedores()
    nombres = conocidos + sorted(n for n in totales if n not in conocidos)
    filas = []
    for nombre in nombres:
        t = totales.get(nombre) or {"n": 0, "ok": 0, "entrada": 0, "salida": 0, "seg": 0.0}
        n = t["n"]
        filas.append({
            "nombre": nombre, "llamadas": n, "ok": t["ok"], "fallos": n - t["ok"],
            "exito": round(100 * t["ok"] / n) if n else None,
            # ~4 caracteres por token: el mismo criterio que resumen() para Telegram.
            "tokens": (t["entrada"] + t["salida"]) // 4,
            "media_s": round(t["seg"] / n, 1) if n else None,
        })
    filas.sort(key=lambda f: -f["llamadas"])  # estable: los de 0 quedan en el orden del core
    return filas


# ------------------------------------------------------------------- logs
# Los .jsonl que el core escribe y la vigilancia convierte en eventos "log" (SSE).
FUENTES_LOG = ("trazas", "evidencia", "uso_proveedores")
LIMITES_LOGS = (50, 100, 200, 500)
COLA_LOGS = 512 * 1024      # por fichero: los filtros buscan en este final, no en todo el historico
CORTE_DETALLE = 300


def _hora(obj: dict) -> str:
    # trazas/evidencia: "t" = "2026-09-24 22:43:47"; uso_proveedores: "cuando" = "2026-09-24T22:43:47"
    return str(obj.get("t") or obj.get("cuando") or "").replace("T", " ")[:19]


def _resumen(obj: dict) -> str:
    resto = {k: v for k, v in obj.items() if k not in ("t", "cuando", "evento", "proveedor", "estado")}
    texto = " · ".join(f"{k}={v}" for k, v in resto.items())
    return texto if len(texto) <= CORTE_DETALLE else texto[:CORTE_DETALLE] + "…"


def lineas_log(fuente: str = "", proveedor: str = "", estado: str = "", limite: int = 100) -> dict:
    """Las `limite` lineas mas recientes de los registros, filtradas y SIN secretos (ocultar.valor
    se aplica antes de nada: ni el resumen ni el detalle ven el valor original).
    proveedor: igual al campo "proveedor"; estado: contenido en el campo "estado" (sin mayusculas)."""
    fuentes = [fuente] if fuente in FUENTES_LOG else list(FUENTES_LOG)
    proveedor, estado = proveedor.strip().lower(), estado.strip().lower()
    filas = []
    for f in fuentes:
        for obj in _cola(registro.CARPETA / f"{f}.jsonl", COLA_LOGS):
            if proveedor and str(obj.get("proveedor", "")).lower() != proveedor:
                continue
            if estado and estado not in str(obj.get("estado", "")).lower():
                continue
            limpio = ocultar.valor(obj)
            filas.append({"fuente": f, "hora": _hora(obj), "evento": str(limpio.get("evento") or ""),
                          "proveedor": str(limpio.get("proveedor") or ""), "estado": str(limpio.get("estado") or ""),
                          "resumen": _resumen(limpio),
                          "completa": json.dumps(limpio, ensure_ascii=False, indent=1)})
    filas.sort(key=lambda x: x["hora"], reverse=True)  # estable: dentro del mismo segundo, orden de fichero
    return {"filas": filas[:limite], "total": len(filas), "recortada": len(filas) > limite}


def auditoria_delegaciones() -> dict:
    """T189: ultimas delegaciones auditadas (BLOQUEADAS y en espera de decision primero) y avisos."""
    lista = auditor.recientes(12)
    orden = {"BLOQUEADA": 0, "ESPERA_DECISION": 1}
    # Las ya revisadas por Claude van al final y no cuentan (estable: dentro de cada grupo, la mas nueva antes).
    lista.sort(key=lambda a: (bool(a.get("revisado")), orden.get(a["resultado"], 2)))
    sin_revisar = auditor.pendientes_de_revisar(lista)
    # Un aviso de una auditoria ya revisada, o de la cola cuando ya no hay alerta, ya no es un aviso vivo.
    resueltas = {a["archivo"] for a in auditor.recientes(500) if a.get("revisado")}
    alerta_cola = revision.cola()["alerta"]

    def vivo(v: dict) -> bool:
        clave = str(v.get("clave") or "")
        if clave.startswith("auditoria:"):
            return clave.split(":")[1] not in resueltas
        return alerta_cola if clave.startswith("revision:cola") else True

    return {"auditorias": lista, "avisos": [v for v in avisos.recientes(20) if vivo(v)][:5],
            "bloqueadas": sum(1 for a in sin_revisar if a["resultado"] == "BLOQUEADA"),
            "en_espera": sum(1 for a in sin_revisar if a["resultado"] == "ESPERA_DECISION")}


def cola_revision() -> dict:
    """T192: borradores y propuestas que esperan el veredicto de Claude, con su antiguedad."""
    c = revision.cola()
    return {"cola": c, "umbral": revision.UMBRAL_COLA, "dias_max": revision.DIAS_MAX}


def borradores_recientes(n: int = 15) -> list[dict]:
    try:
        rutas = [p for p in trabajo.BORRADORES.glob("*.md") if p.is_file()]
    except OSError:
        return []
    rutas.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"nombre": p.name, "cuando": p.stat().st_mtime} for p in rutas[:n]]
