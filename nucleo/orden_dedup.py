# -*- coding: utf-8 -*-
"""Deduplicado de órdenes contra tareas abiertas y cerradas recientes."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta

from nucleo import tareas
from nucleo import freno


def _normalizar(texto: str) -> str:
    """Normaliza el texto: minúsculas, sin tildes, solo [a-z0-9] separados por espacio."""
    if not texto:
        return ""
    # Convertir a minúsculas
    texto = texto.lower()
    # Quitar tildes
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    # Reemplazar cualquier carácter que no sea alfanumérico por espacio
    texto = re.sub(r'[^a-z0-9]', ' ', texto)
    # Colapsar espacios múltiples en uno
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto


def _extraer_texto(tarea: dict) -> str:
    """Extrae el texto relevante de la tarea (literal o título)."""
    detalle = tarea.get("detalle", "")
    # Buscar la línea "Orden literal de Damián (<canal>):"
    # Usamos re.DOTALL para que '.' coincida con saltos de línea y capture el literal completo
    match = re.search(r'Orden literal de Damián \([^)]*\):\s*(.*)', detalle, re.DOTALL)
    if match:
        return match.group(1).strip()
    return tarea.get("titulo", "")


def _es_candidata(tarea: dict, ahora: datetime, dias: int) -> bool:
    """Determina si la tarea es candidata para deduplicación."""
    estado = tarea.get("estado", "")
    etiquetas = tarea.get("etiquetas", [])
    
    # Excluir revisiones
    if "cat:revision" in etiquetas:
        return False

    if estado in tareas.VIVOS:
        return True
    
    if estado in tareas.CERRADOS:
        cerrada_str = tarea.get("cerrada")
        if not cerrada_str:
            return False
        try:
            cerrada_dt = datetime.strptime(cerrada_str, "%Y-%m-%d %H:%M:%S")
            limite = ahora - timedelta(days=dias)
            return cerrada_dt >= limite
        except ValueError:
            return False
            
    return False


def _num_id(id_str: str) -> int:
    """Extrae el número de un ID de tarea (ej. T1000 -> 1000)."""
    match = re.search(r'\d+', id_str)
    if match:
        return int(match.group())
    return 0


def buscar(texto: str, tareas_list: list[dict], ahora: datetime | None = None, dias: int = 7) -> dict | None:
    """Busca duplicados de la orden dada contra la lista de tareas."""
    if ahora is None:
        ahora = datetime.now()
        
    texto_norm = _normalizar(texto)
    if not texto_norm:
        return None

    # Filtrar candidatas
    candidatas = [t for t in tareas_list if _es_candidata(t, ahora, dias)]
    if not candidatas:
        return None

    # Preparar datos para comparación
    # Cada entrada: (id, estado, texto_norm, creado_dt, num_id)
    datos = []
    for t in candidatas:
        t_texto = _extraer_texto(t)
        t_norm = _normalizar(t_texto)
        if not t_norm:
            continue
            
        try:
            creada_dt = datetime.strptime(t.get("creada", "1970-01-01 00:00:00"), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            creada_dt = datetime(1970, 1, 1)
            
        datos.append({
            "id": t["id"],
            "estado": t["estado"],
            "norm": t_norm,
            "creada": creada_dt,
            "num_id": _num_id(t["id"])
        })

    if not datos:
        return None

    # 1) Buscar idéntica
    identica = None
    for d in datos:
        if d["norm"] == texto_norm:
            if identica is None:
                identica = d
            else:
                # Empate: más reciente creada, luego id mayor
                if d["creada"] > identica["creada"]:
                    identica = d
                elif d["creada"] == identica["creada"] and d["num_id"] > identica["num_id"]:
                    identica = d

    if identica:
        return {
            "id": identica["id"],
            "tipo": "identica",
            "similitud": 1.0,
            "estado": identica["estado"]
        }

    # 2) Buscar parecida
    # Texto corto: menos de 3 raíces (palabras) -> solo cuenta idéntica (ya no la encontramos)
    if len(texto_norm.split()) < 3:
        return None

    mejor = None
    mejor_sim = 0.0
    
    palabras_busqueda = freno.palabras(texto_norm)
    
    for d in datos:
        palabras_tarea = freno.palabras(d["norm"])
        sim = freno.parecido(palabras_busqueda, palabras_tarea)
        
        if sim >= freno.UMBRAL_PARECIDO:
            if sim > mejor_sim:
                mejor_sim = sim
                mejor = d
            elif sim == mejor_sim and mejor is not None:
                # Empate en similitud: más reciente creada, luego id mayor
                if d["creada"] > mejor["creada"]:
                    mejor = d
                elif d["creada"] == mejor["creada"] and d["num_id"] > mejor["num_id"]:
                    mejor = d

    if mejor:
        return {
            "id": mejor["id"],
            "tipo": "parecida",
            "similitud": round(mejor_sim, 3),
            "estado": mejor["estado"]
        }

    return None