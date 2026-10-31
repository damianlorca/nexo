# -*- coding: utf-8 -*-
"""Ejecutor de acciones directas de lista blanca por canal con confirmacion."""

from __future__ import annotations

from nucleo import avisos, turnos, tareas as T

PERMITIDAS = {
    "web": {"estado_tarea", "asignar", "prioridad", "turnos", "aviso"}
}


def ejecutar(accion: dict, canal: str) -> dict:
    if canal not in PERMITIDAS:
        return {"estado": "NO_PERMITIDA", "respuesta": "Canal no permitido"}

    tipo_accion = accion.get("accion")
    if tipo_accion not in PERMITIDAS[canal]:
        return {"estado": "NO_SOPORTADA", "respuesta": "Accion no soportada"}

    try:
        if tipo_accion in {"estado_tarea", "asignar", "prioridad"}:
            tid = accion.get("tarea")
            tarea = T.buscar(tid)
            if not tarea or tarea.get("id") != tid:
                return {"estado": "ERROR", "respuesta": f"La tarea {tid} no existe"}
            if tarea.get("estado") in T.CERRADOS:
                return {"estado": "ERROR", "respuesta": "La tarea esta cerrada"}

            if tipo_accion == "estado_tarea":
                titulo = tarea.get("titulo", "")[:80]
                resp = f"Tarea {tid}: {tarea.get('estado')} - {titulo}"
                return {"estado": "EJECUTADA", "respuesta": resp}

            elif tipo_accion == "asignar":
                nuevo_asignado = accion.get("a", "")
                T.actualizar(tid, depende=nuevo_asignado)
                T.anotar(tid, f"asignada a {nuevo_asignado}")
                return {"estado": "EJECUTADA", "respuesta": f"Asignada {tid} a {nuevo_asignado}"}

            elif tipo_accion == "prioridad":
                sentido = accion.get("sentido", 1)
                imp_actual = tarea.get("importancia", 3)
                if sentido > 0:
                    nueva_imp = min(5, imp_actual + 1)
                else:
                    nueva_imp = max(1, imp_actual - 1)

                if nueva_imp == imp_actual:
                    return {"estado": "EJECUTADA", "respuesta": "ya estaba en ese limite"}

                T.actualizar(tid, importancia=nueva_imp)
                T.anotar(tid, f"importancia {imp_actual} -> {nueva_imp}")
                return {"estado": "EJECUTADA", "respuesta": f"Prioridad cambiada de {imp_actual} a {nueva_imp}"}

        elif tipo_accion == "turnos":
            activar = accion.get("activar", True)
            if activar:
                resp = turnos.activar()
            else:
                resp = turnos.desactivar("orden web de Damian")
            return {"estado": "EJECUTADA", "respuesta": str(resp)}

        elif tipo_accion == "aviso":
            minutos = accion.get("minutos", 0)
            if minutos > 0:
                return {"estado": "NO_SOPORTADA", "respuesta": "Avisos programados no soportados"}
            texto = accion.get("texto", "")[:400]
            avisos.emitir(tipo="orden", titulo="Aviso pedido por Damian", cuerpo=texto)
            return {"estado": "EJECUTADA", "respuesta": "Aviso emitido"}

        return {"estado": "NO_SOPORTADA", "respuesta": "Accion no reconocida"}

    except Exception as e:
        ex_nombre = type(e).__name__
        return {"estado": "ERROR", "respuesta": f"{ex_nombre}: {e}"}