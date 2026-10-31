# -*- coding: utf-8 -*-
"""T688 (epica T686), pieza 1: registro de descartes consultable y aviso al re-proponer.

Caso real 04/10: Damian volvio a pedir Blkit (T178), kokonutui (T179), Manus (T180), Fast-jev (T289) y Colibri (T108),
los 5 ya DESCARTADOS con motivo, y nada se lo aviso. Aqui:

  registro(tareas)   lo DESCARTADO por una razon de IDEA, con su motivo, quien, cuando y el informe:
                       - causa "resultado": investigacion cerrada con RESULTADO DESCARTAR (T674);
                       - causa "idea": propuesta descartada por Claude al aprobar el borrador (la idea no valia);
                       - causa "superado": el trabajo se hizo por otra via.
                     NO entra lo descartado por BORRADOR malo (la idea no se juzgo) ni lo descartado sin motivo,
                     ni lo fundido (la idea sigue viva en otra tarea).
  buscar(texto, reg) descartes parecidos a un texto, SIN IA: mismo nombre (lo que queda al quitar los verbos de
                     encargo: "Investigar Blkit" -> "blkit") o misma idea (Jaccard de raices, como freno.parecido).

El detector de parecidas por embeddings (freno.pares_semanticos) usa este registro y adjunta el motivo anterior:
el tribunal o Damian deciden 'el descarte sigue valiendo' o 'revalorar' sin reinvestigar desde cero.
Solo informa: no cambia ninguna tarea. La vista web 'Descartadas' y la guardia de cierre de propuestas son piezas
siguientes (documentacion/T688_REGISTRO_DESCARTES.md).
"""
from __future__ import annotations

import re

from nucleo import auditoria_cierres as AC
from nucleo import freno
from nucleo import tareas as T

UMBRAL_IDEA = freno.UMBRAL_PARECIDO
# palabras de encargo que no identifican la cosa: "Investigar Blkit" y "Auditar Blkit" son la misma peticion
ENCARGO = set("investigar investiga investigacion evaluar evalua estudiar estudia auditar audita adoptar adopta "
              "integrar integra explorar explora instalar instala probar prueba analizar analiza revisar revisa "
              "anadir anade crear crea implementar implementa propuesta herramienta repo repositorio github "
              "complementos skills skill sistema modelo para sobre como".split())


def _nucleo(texto: str) -> set[str]:
    """Palabras completas (sin tildes) que quedan al quitar verbos de encargo y palabras vacias."""
    import unicodedata
    s = unicodedata.normalize("NFKD", (texto or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\[propuesta de t\d+\]", " ", s)
    return {w for w in re.findall(r"[a-z0-9]+", s) if len(w) > 2 and w not in ENCARGO and w not in freno._STOP}


def _distintivo(n: set[str]) -> bool:
    """Un nombre propio: 2+ palabras sueltas o una de 5+ letras (un solo 'web' o 'bot' no identifica nada)."""
    return bool(n) and (len(n) >= 2 or max(map(len, n)) >= 5)


def _texto(t: dict) -> str:
    return freno.que(t) if AC._es_propuesta(t) else (t.get("titulo") or "")


def _quien_motivo(t: dict) -> tuple[str, str, str, str] | None:
    """(causa, motivo, quien, cuando) o None si el descarte no es de idea."""
    r = t.get("resultado") or {}
    if r.get("decision") == "DESCARTAR":
        return "resultado", r.get("motivo", ""), r.get("quien", ""), r.get("cuando") or t.get("cerrada") or ""
    if t.get("estado") != "descartada":
        return None
    causa = AC._causa(t)
    if causa not in ("idea", "superado"):
        return None
    nota = AC._ultima_nota_descarte(t)
    return causa, AC._motivo(nota), "claude", t.get("cerrada") or ""


def registro(tareas: list[dict] | None = None) -> list[dict]:
    tareas = T.cargar()["tareas"] if tareas is None else tareas
    out = []
    for t in tareas:
        et = t.get("etiquetas") or []
        if "turno:lote" in et or "cat:revision" in et:
            continue
        if t.get("estado") not in T.CERRADOS:
            continue
        r = _quien_motivo(t)
        if r is None:
            continue
        causa, motivo, quien, cuando = r
        informe = AC._et(t, "informe:") or AC._et(t, "de_borrador:")
        out.append({"id": t["id"], "texto": _texto(t), "causa": causa, "motivo": motivo, "quien": quien,
                    "cuando": cuando, "informe": informe, "origen": AC._et(t, "tarea_origen:")})
    return out


def buscar(texto: str, reg: list[dict], excluir: str = "") -> list[dict]:
    """Descartes de `reg` parecidos a `texto` (mismo nombre o misma idea), los mas parecidos primero."""
    nuevo = _nucleo(texto)
    pal = freno.palabras(texto)
    res = []
    for d in reg:
        if d["id"] == excluir:
            continue
        nd = _nucleo(d["texto"])
        if _distintivo(nd) and (nd <= nuevo or (_distintivo(nuevo) and nuevo <= nd)):
            res.append((1.0, "mismo nombre", d))
            continue
        j = freno.parecido(pal, freno.palabras(d["texto"]))
        if j >= UMBRAL_IDEA:
            res.append((j, "misma idea", d))
    res.sort(key=lambda x: -x[0])
    return [dict(d, parecido=round(p, 2), por=por) for p, por, d in res]


# ------------------------------------------------------------------ pieza 2: vista web 'Descartadas' (solo lee)
CAUSAS = ("resultado", "idea", "superado")
MAX_VISTA = 200


def vista(causa: str = "", tareas: list[dict] | None = None) -> dict:
    """Lo que pinta el panel 'Descartadas' del Centro: lo mas reciente primero, filtrable por causa."""
    from collections import Counter
    reg = registro(tareas)
    cuenta = Counter(d["causa"] for d in reg)
    causa = causa if causa in CAUSAS else ""
    filas = sorted((d for d in reg if not causa or d["causa"] == causa), key=lambda d: d["cuando"] or "", reverse=True)
    return {"filas": filas[:MAX_VISTA], "total": len(reg), "mostradas": min(len(filas), MAX_VISTA),
            "cuenta": {c: cuenta.get(c, 0) for c in CAUSAS}, "causa": causa}


# ------------------------------------------------------------------ pieza 3: aviso al re-proponer (no bloquea)
ET_AVISO = "aviso:descartado_antes"
MAX_AVISO = 3


def texto_aviso(parecidos: list[dict]) -> str:
    return "; ".join(f"{d['id']} ({d['por']}, {d['causa']}, {d['quien'] or '?'} {str(d['cuando'])[:10]}): "
                     f"{d['motivo'][:160]}" for d in parecidos[:MAX_AVISO])


def avisar(tarea_id: str, texto: str | None = None, reg: list[dict] | None = None) -> list[dict]:
    """Si la tarea se parece a algo DESCARTADO por idea, le deja una nota con el motivo anterior y la etiqueta
    ET_AVISO. Devuelve los parecidos (vacio si nada). Nunca bloquea ni cambia el estado."""
    t = T.buscar(tarea_id)
    if t is None or t["id"] != tarea_id:
        return []
    reg = registro() if reg is None else reg
    parecidos = buscar(texto if texto is not None else _texto(t), reg, excluir=tarea_id)[:MAX_AVISO]
    if parecidos:
        T.anotar(tarea_id, "Aviso T688: se parece a lo DESCARTADO antes (decidir si el descarte sigue valiendo o "
                           "se revalora, sin reinvestigar desde cero): " + texto_aviso(parecidos))
        et = list(t.get("etiquetas") or [])
        if ET_AVISO not in et:
            T.actualizar(tarea_id, etiquetas=et + [ET_AVISO])
    return parecidos


def avisos_candidatos(candidatos: list[dict], reg: list[dict] | None = None) -> dict[str, list[dict]]:
    """Candidatos del vigia (nombre, descripcion) que ya se descartaron: {nombre: parecidos}."""
    reg = registro() if reg is None else reg
    out = {}
    for c in candidatos:
        nombre = c.get("nombre") or c.get("id") or ""
        p = buscar(f"{nombre} {c.get('descripcion', '')}", reg)[:MAX_AVISO] if nombre else []
        if p:
            out[nombre] = p
    return out
