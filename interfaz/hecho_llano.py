# -*- coding: utf-8 -*-
"""T230 (Centro v2): la frase en llano de cada cosa "Hecha desde tu ultima visita".

De donde sale, por orden:
  1. `cierre.para_damian` de la tarea (lo rellena quien cierra: Claude/Code);
  2. la que Qwen local genero antes y se guardo en `tareas_detalle/<id>.json` (clave `frase_damian`);
  3. Qwen local ahora (qwen2.5:7b, num_ctx 4096, num_predict 80; nunca mas de 8B), a partir de titulo + objetivo +
     evidencia; se guarda en el detalle sin pisar nada de lo que hubiera;
  4. sin Qwen: el titulo en llano cortado por palabra (nunca a media palabra).
La segunda frase opcional es el `objetivo` de la tarea, tambien cortado por palabra.
"""
from __future__ import annotations

import time

from nucleo import tareas as T
from nucleo import tareas_almacen as AL

MODELO = "qwen2.5:7b"
URL_OLLAMA = "http://localhost:11434"
NUM_CTX = 4096
NUM_PREDICT = 80
TIMEOUT = 25.0
MAX_FRASE = 110
MAX_SEGUNDA = 130
REINTENTO_S = 600       # tras un fallo de Qwen no se vuelve a intentar durante 10 min (el panel se refresca cada 2)
_fallo_hasta = 0.0


def cortar(texto: str, maximo: int) -> str:
    """Corta por palabra (con «…»), nunca a media palabra."""
    t = " ".join(str(texto or "").split())
    if len(t) <= maximo:
        return t
    corte = t[:maximo - 1].rsplit(" ", 1)[0].rstrip(" ,;:.-—·(")
    return (corte or t[:maximo - 1]) + "…"


def _prompt(titulo: str, objetivo: str, evidencia: str) -> str:
    return ("Escribe UNA frase corta en español llano (máximo 20 palabras) que diga qué cambia para el usuario con "
            "este trabajo ya terminado. Sin números de tarea, sin nombres de archivo, sin tecnicismos.\n"
            f"Título: {titulo[:200]}\nObjetivo: {objetivo[:300]}\nCómo se comprobó: {evidencia[:300]}\nFrase:")


def _qwen(prompt: str) -> str:
    """Una llamada a Ollama local. '' si no esta, si hay OTRO modelo cargado (un modelo cada vez) o si falla."""
    try:
        import httpx
        cargados = [m.get("name", "") for m in httpx.get(f"{URL_OLLAMA}/api/ps", timeout=2).json().get("models", [])]
        if any(n and n != MODELO for n in cargados):
            return ""
        r = httpx.post(f"{URL_OLLAMA}/api/chat", timeout=TIMEOUT, json={
            "model": MODELO, "stream": False, "think": False, "keep_alive": 0,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"num_ctx": NUM_CTX, "num_predict": NUM_PREDICT, "temperature": 0.2}})
        if r.status_code != 200:
            return ""
        return ((r.json().get("message") or {}).get("content") or "").strip()
    except Exception:   # noqa: BLE001 - sin Qwen se usa el titulo
        return ""


def _limpiar(texto: str) -> str:
    t = " ".join(str(texto or "").replace("\n", " ").split()).strip(" \"'«»")
    return cortar(t, MAX_FRASE) if len(t) >= 12 else ""


def frase(t: dict, permitir_qwen: bool = True) -> tuple[str, str, bool]:
    """(frase, segunda_frase, generada_ahora_con_qwen) de una tarea cerrada."""
    global _fallo_hasta
    from interfaz.presentar import llano
    cierre = t.get("cierre") or {}
    segunda = cortar(t.get("objetivo") or "", MAX_SEGUNDA)
    propia = _limpiar(cierre.get("para_damian") or "")
    if propia:
        return propia, segunda, False
    guardada = _limpiar(AL.leer_detalle(T.ALMACEN, t["id"]).get("frase_damian") or "")
    if guardada:
        return guardada, segunda, False
    if permitir_qwen and time.time() >= _fallo_hasta:
        generada = _limpiar(_qwen(_prompt(llano(t.get("titulo") or ""), t.get("objetivo") or "",
                                          cierre.get("evidencia") or "")))
        if generada:
            try:
                AL.fusionar_detalle(T.ALMACEN, t["id"], frase_damian=generada)
            except OSError:
                pass
            return generada, segunda, True
        _fallo_hasta = time.time() + REINTENTO_S
    return cortar(llano(t.get("titulo") or ""), MAX_FRASE), segunda, False
