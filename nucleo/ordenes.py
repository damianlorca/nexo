# -*- coding: utf-8 -*-
"""Ordenes libres de Damian (T140 pieza 1, modo "hazlo ya"). Sin Claude.

Damian escribe una orden (Telegram /orden o la web). NEXO:
  1. la da de alta como tarea (siempre: nada se pierde) con cat:/prov: del clasificador;
  2. segun la categoria:
     - resumen/redaccion/investigacion -> la trabaja YA con nucleo.trabajo (borrador +
       revisor de otro proveedor). Nunca la cierra: queda para que Claude la revise;
     - codigo/arquitectura/operacion_pc -> NO la ejecuta: la deja encolada para Claude
       (etiqueta escalado:claude) con la orden literal;
     - personal -> la deja para Damian.
Permisos (idea T145): una orden por canal NO ejecuta comandos ni toca el sistema;
solo produce tareas y borradores.
"""
from __future__ import annotations

import logging

from nucleo import clasificador as K
from nucleo import descartes
from nucleo import tareas as T

DELEGABLE = ("resumen", "redaccion", "investigacion")


def procesar(texto: str, canal: str = "telegram", trabajar: bool = True) -> dict:
    texto = (texto or "").strip()
    if len(texto) < 4:
        return {"estado": "VACIA", "respuesta": "Escribe la orden detrás de /orden."}
    provisional = {"titulo": texto[:90], "detalle": texto, "depende": "ia"}
    cat = K.clasificar(provisional)
    prov = K.PROVEEDOR_POR_CATEGORIA.get(cat, "claude")
    depende = "damian" if cat == "personal" else "ia"
    etiquetas = [f"cat:{cat}", f"prov:{prov}", f"origen:orden_{canal}"]
    if cat not in DELEGABLE and cat != "personal":
        etiquetas.append("escalado:claude")
    t = T.anadir(texto[:90], detalle=f"Orden literal de Damián ({canal}):\n{texto}", importancia=4, urgencia=4,
                 depende=depende, etiquetas=etiquetas)
    T.anotar(t["id"], f"Orden via {canal}. Clasificada automaticamente como '{cat}' (acierto medido ~80 %): revisar si no encaja.")
    r = {"tarea": t["id"], "categoria": cat, "proveedor": prov}
    previos = _descartado_antes(t["id"], texto)
    if cat in DELEGABLE and trabajar:
        from nucleo import trabajo
        original = trabajo.candidatas
        trabajo.candidatas = lambda: [x for x in original() if x["id"] == t["id"]]
        try:
            filas = trabajo.ciclo(max_tareas=1)
        finally:
            trabajo.candidatas = original
        f = filas[0] if filas else {}
        r.update(estado="BORRADOR" if f.get("archivo") else "SIN_BORRADOR", **{k: f.get(k) for k in ("archivo", "autor", "revisor", "veredicto")})
        if f.get("archivo"):
            r["respuesta"] = (f"✅ {t['id']} ({cat}): borrador de {f.get('autor')} en {f['archivo']}. "
                              f"Revisor {f.get('revisor')}: {f.get('veredicto') or 'sin veredicto'}. Claude lo revisa antes de darlo por bueno.")
        else:
            err = next((i.get("error") for i in f.get("intentos", []) if i.get("error")), "sin proveedor disponible")
            r["respuesta"] = f"⚠️ {t['id']} ({cat}) apuntada, pero no pude hacer el borrador ahora: {err}. Queda en la cola."
    elif cat == "personal":
        r.update(estado="PARA_DAMIAN", respuesta=f"📌 {t['id']} apuntada como tuya ({cat}).")
    elif cat in DELEGABLE:  # trabajar=False: apuntada; la trabaja un turno (no es para Claude)
        r.update(estado="ENCOLADA", respuesta=f"📥 {t['id']} ({cat}) apuntada: la trabajo en un turno.")
    else:
        r.update(estado="ESCALADO", respuesta=f"🧠 {t['id']} ({cat}) necesita a Claude: queda encolada con tu orden literal.")
    if previos:
        r["descartado_antes"] = [d["id"] for d in previos]
        r["respuesta"] += f" ⚠️ Ya se descartó algo parecido: {descartes.texto_aviso(previos)}"
    return r


def _descartado_antes(tarea_id: str, texto: str) -> list[dict]:
    """T688 pieza 3: avisa (nota en la tarea y en la respuesta) si la orden se parece a algo ya DESCARTADO.
    Nunca impide dar de alta la orden: si el aviso falla, la orden sigue."""
    try:
        return descartes.avisar(tarea_id, texto)
    except Exception as e:   # el aviso es accesorio: nunca se pierde una orden por el
        logging.getLogger(__name__).warning("aviso de descartes fallo: %s", type(e).__name__)
        return []
