# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import unicodedata

def _normalizar_texto(texto: str) -> str:
    if not isinstance(texto, str):
        return ""
    t = texto.strip()
    if not t or len(t) > 160:
        return ""
    # Quitar ¿¡ iniciales y .!? finales
    t = re.sub(r'^[¿¡]+', '', t)
    t = re.sub(r'[.!?]+$', '', t)
    t = t.strip()
    
    # Normalizar Unicode (quitar tildes) y pasar a minúsculas
    nfkd = unicodedata.normalize('NFKD', t)
    sin_tildes = "".join([c for c in nfkd if not unicodedata.combining(c)])
    t_min = sin_tildes.lower()
    
    # Colapsar espacios
    t_min = re.sub(r'\s+', ' ', t_min).strip()
    
    # Quitar un prefijo de cortesía al principio si lo hay
    prefijos = ["nexo,", "nexo", "por favor,", "por favor", "porfa,", "porfa"]
    for p in prefijos:
        # Usar patrón para asegurar que empiece por la palabra exacta
        patron = r'^' + re.escape(p) + r'(?:\s+|$)'
        if re.match(patron, t_min):
            t_min = re.sub(patron, '', t_min).strip()
            break
            
    return t_min

def _quitar_cortesia_final(resto: str) -> str:
    r = resto.strip()
    if not r:
        return ""
    sufijos = ["por favor", "porfa", "gracias"]
    for s in sufijos:
        patron = r'(?:\b|,\s*)' + re.escape(s) + r'$'
        if re.search(patron, r):
            r = re.sub(patron, '', r).strip()
            r = r.rstrip(',').strip()
            break
    return r

def detectar(texto: str) -> dict | None:
    if not isinstance(texto, str):
        return None
    
    t_orig = texto.strip()
    if not t_orig or len(t_orig) > 160:
        return None
        
    t_norm = _normalizar_texto(texto)
    if not t_norm:
        return None
        
    # Verificar negaciones iniciales comunes
    if t_norm.startswith("no ") or t_norm.startswith("nunca "):
        return None

    # 1. estado_tarea: "como va|como esta|estado de|que tal va" + [la] [tarea] + Txxx
    m_est = re.match(r'^(como va|como esta|estado de|que tal va)\b\s*(?:la\s+)?(?:tarea\s+)?(t\d{3,4})\b(.*)$', t_norm)
    if m_est:
        tarea = m_est.group(2).upper()
        resto = _quitar_cortesia_final(m_est.group(3))
        if resto == "":
            return {"accion": "estado_tarea", "tarea": tarea}

    # 2. asignar: "cambia|pasa|asigna|manda" + [la] [tarea] + Txxx + "a" + claude|damian|nexo|ia
    m_asig = re.match(r'^(cambia|pasa|asigna|manda)\b\s*(?:la\s+)?(?:tarea\s+)?(t\d{3,4})\b\s+a\s+(claude|damian|nexo|ia)\b(.*)$', t_norm)
    if m_asig:
        tarea = m_asig.group(2).upper()
        persona = m_asig.group(3)
        if persona == "nexo":
            persona = "ia"
        resto = _quitar_cortesia_final(m_asig.group(4))
        if resto == "":
            return {"accion": "asignar", "tarea": tarea, "a": persona}

    # 3. prioridad: "sube|baja" + [la] [prioridad de] [la] [tarea] + Txxx
    m_prio = re.match(r'^(sube|baja)\b\s*(?:la\s+)?(?:prioridad\s+(?:de\s+)?)?(?:la\s+)?(?:tarea\s+)?(t\d{3,4})\b(.*)$', t_norm)
    if m_prio:
        verbo = m_prio.group(1)
        tarea = m_prio.group(2).upper()
        sentido = 1 if verbo == "sube" else -1
        resto = _quitar_cortesia_final(m_prio.group(3))
        if resto == "":
            return {"accion": "prioridad", "tarea": tarea, "sentido": sentido}

    # 4. turnos: "activa|enciende|reanuda" | "desactiva|apaga|para|pausa" + [los] + "turnos"
    m_turn = re.match(r'^(activa|enciende|reanuda|desactiva|apaga|para|pausa)\b\s*(?:los\s+)?turnos\b(.*)$', t_norm)
    if m_turn:
        verbo = m_turn.group(1)
        activar = verbo in ("activa", "enciende", "reanuda")
        resto = _quitar_cortesia_final(m_turn.group(2))
        if resto == "":
            return {"accion": "turnos", "activar": activar}

    # 5. aviso: "mandame|enviame|avisame" + ... + una de "notificacion|push|aviso" en cualquier punto del texto;
    m_aviso = re.match(r'^(mandame|enviame|avisame)\b(.*)$', t_norm)
    if m_aviso:
        cuerpo = m_aviso.group(2)
        if any(palabra in cuerpo for palabra in ["notificacion", "push", "aviso"]):
            minutos = 0
            m_min = re.search(r'\b(\d+)\s*(?:min|minuto|minutos)\b', cuerpo)
            if m_min:
                minutos = int(m_min.group(1))
            return {"accion": "aviso", "minutos": minutos, "texto": t_orig}

    return None