# -*- coding: utf-8 -*-
"""Politica de permisos por canal (T145 pieza A).

Define las capacidades disponibles y la tabla de permisos por canal.
La funcion `permitido` implementa un fallo cerrado con precedencia estricta.
"""
from __future__ import annotations

# Capacidades en el orden especificado
CAPACIDADES = (
    "leer_estado",
    "crear_tarea",
    "accion_directa",
    "borrador_ia_externa",
    "escribir_codigo",
    "ejecutar_comando",
    "enviar_privado_fuera",
)

# Politica de permisos por canal
POLITICA = {
    "claude_sesion": frozenset(CAPACIDADES[:-1]),  # Todas menos "enviar_privado_fuera"
    "web": frozenset({
        "leer_estado",
        "crear_tarea",
        "accion_directa",
        "borrador_ia_externa",
    }),
    "telegram": frozenset({
        "leer_estado",
        "crear_tarea",
    }),
    "turno": frozenset({
        "leer_estado",
        "crear_tarea",
        "borrador_ia_externa",
    }),
    "implementador": frozenset({
        "leer_estado",
        "escribir_codigo",
    }),
}


def capacidades(canal: str) -> list[str]:
    """Devuelve las capacidades permitidas para un canal, en el orden de CAPACIDADES.
    
    Si el canal no existe, devuelve una lista vacia.
    """
    if canal is None:
        return []
    canal_norm = canal.strip().lower()
    if canal_norm not in POLITICA:
        return []
    permitidas = POLITICA[canal_norm]
    return [cap for cap in CAPACIDADES if cap in permitidas]


def permitido(canal: str, capacidad: str) -> tuple[bool, str]:
    """Comprueba si una capacidad esta permitida para un canal.
    
    Precedencia de comprobaciones:
    1. capacidad desconocida -> (False, motivo con "capacidad desconocida")
    2. canal desconocido, vacio o None -> (False, motivo con "canal desconocido")
    3. capacidad no permitida al canal -> (False, motivo con el canal y la capacidad)
    4. si no -> (True, "")
    
    canal y capacidad se comparan tras strip() y en minusculas.
    """
    # Normalizar capacidad
    cap_norm = capacidad.strip().lower() if capacidad else ""
    
    # 1. capacidad desconocida
    if cap_norm not in CAPACIDADES:
        return (False, f"capacidad desconocida: {capacidad}")
    
    # Normalizar canal
    canal_norm = canal.strip().lower() if canal else ""
    
    # 2. canal desconocido, vacio o None
    if canal_norm not in POLITICA:
        return (False, f"canal desconocido: {canal}")
    
    # 3. capacidad no permitida al canal
    if cap_norm not in POLITICA[canal_norm]:
        return (False, f"capacidad {cap_norm} no permitida para canal {canal_norm}")
    
    # 4. permitido
    return (True, "")