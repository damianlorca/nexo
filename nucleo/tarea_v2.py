"""Formato de tarea v2 (T1010 paso 2, Damian 17/10 20:53): solo estructura.

Una tarea v2 dice lo esencial y nada mas:

    id + titulo (<=80) · instrucciones_damian (literal, solo si las pidio el; lo privado va a
    memoria/perfil_privado/tareas/<id>.md y la tarea guarda la referencia) · objetivo (<=300) ·
    hecho_cuando (1-3 comprobaciones) · donde · quien (ia|implementador|claude|damian, con
    motivo_quien si es damian) · tipo (codigo|investigacion|decision|redaccion|personal) ·
    prioridad y esfuerzo (1-5) · coste_eur · fecha_limite (la urgencia se calcula de ella) ·
    depende_de · origen · estado · cierre · despues · notas (solo vigentes, maximo 5).

Como convive con lo viejo
-------------------------
En MEMORIA cada tarea tiene los campos viejos Y los v2, siempre coherentes: unos ~40 modulos leen
`t["depende"]`, `t["importancia"]`, `t["etiquetas"]`... y siguen funcionando sin tocarlos. Los campos
viejos mandan en memoria; los v2 son vistas que `alinear()` recalcula (prioridad, esfuerzo,
fecha_limite, depende_de, tipo, origen y quien). En DISCO, el formato nuevo guarda solo la forma v2
(`a_disco`), compacta, y `de_disco` la vuelve a abrir. Lo que la forma v2 perderia (importancia y
urgencia por separado, el coste 1-5 viejo, texto libre de `bloqueada_por`) se guarda solo si difiere
de lo que dice el campo v2, asi no se pierde nada al guardar; la migracion (herramientas_nube/
migrar_tareas_v2.py) es la unica que lo colapsa a proposito.

Etiquetas de rastreo -> origen: `prov`, `tarea_origen`, `de_borrador`, `borrador`, `revisado`,
`auditoria`... dicen de donde viene la tarea. Pasan a `origen` en disco y se reconstruyen al cargar,
porque el circuito de revision, el freno y el tribunal las siguen leyendo. `cat:X` pasa a `tipo`
(con `origen["cat"]` cuando X no es el propio tipo).

Este modulo no importa `nucleo.tareas` (lo importa a el).
"""

from __future__ import annotations

import re
from datetime import datetime

QUIEN = ("ia", "implementador", "claude", "damian")
TIPOS = ("codigo", "investigacion", "decision", "redaccion", "personal")
CIERRES = ("HECHO Y TESTEADO", "HECHO SIN TESTEAR")

LIM_TITULO = 80
LIM_OBJETIVO = 300
MAX_HECHO = 3
MAX_NOTAS = 5
MIN_NADA = 10                # "nada: <motivo>" con un motivo de verdad
MIN_EVIDENCIA = 10

PRIVADO_REF = "memoria/perfil_privado/tareas/{id}.md"
MARCA_PRIVADO = "memoria/perfil_privado/tareas/"

# Familias de etiquetas de rastreo que viven en `origen` (tag "familia:valor" <-> origen[clave]).
# La clave es la familia, salvo "origen:" (colisiona con el nombre del campo) que se guarda como "via".
RASTREO = {
    "prov": "prov",
    "tarea_origen": "tarea_origen",
    "de_borrador": "de_borrador",
    "borrador": "borrador",
    "revisado": "revisado",
    "auditoria": "auditoria",
    "auditoria_id": "auditoria_id",
    "origen": "via",
    "revision": "revision",
    "propuesta": "propuesta",
    "archivada": "archivada",
    "filtro": "filtro",
    "fundida_de": "fundida_de",
    "fundida_en": "fundida_en",
}
_FAMILIA_DE_CLAVE = {v: k for k, v in RASTREO.items()}

# cat:X -> tipo v2. Lo que no es un tipo se guarda tal cual en origen["cat"].
TIPO_DE_CAT = {
    "codigo": "codigo", "arquitectura": "codigo", "integracion": "codigo", "prueba": "codigo",
    "mantenimiento": "codigo", "operacion_pc": "codigo", "seguridad": "codigo", "diseno": "codigo",
    "investigacion": "investigacion", "revision": "investigacion",
    "decision": "decision", "propuesta": "decision", "monetizacion": "decision",
    "redaccion": "redaccion",
    "personal": "personal",
}

# Campos que solo existen en v2 (no tienen version vieja): se guardan tal cual si traen algo.
SOLO_V2 = ("instrucciones_damian", "objetivo", "hecho_cuando", "donde", "motivo_quien", "coste_eur",
           "cierre", "despues")
# Vistas: se recalculan de los campos viejos.
VISTAS = ("quien", "tipo", "prioridad", "esfuerzo", "fecha_limite", "depende_de", "origen")
CAMPOS_V2 = SOLO_V2 + VISTAS

# Cosas pesadas que van a memoria/tareas_detalle/<id>.json, no a la tarea.
DETALLE_CAMPOS = ("conversaciones", "descarte", "fallos_turno", "notas_antiguas")

_RE_ID = re.compile(r"\bT\d{3,}\b")


def vacios() -> dict:
    """Los campos v2 de una tarea nueva, con su valor vacio."""
    return {
        "instrucciones_damian": "", "objetivo": "", "hecho_cuando": [], "donde": "",
        "quien": "ia", "motivo_quien": "", "tipo": "", "prioridad": 3, "esfuerzo": 3,
        "coste_eur": None, "fecha_limite": None, "depende_de": [], "origen": {},
        "cierre": {}, "despues": "",
    }


def _recortar15(n, por_defecto=3) -> int:
    try:
        v = int(n)
    except (TypeError, ValueError):
        return por_defecto
    return max(1, min(5, v))


def prioridad_de(importancia, urgencia) -> int:
    """Una sola prioridad 1-5 a partir de las dos medidas viejas (la urgencia pesa mas, como en la puntuacion)."""
    i, u = _recortar15(importancia), _recortar15(urgencia)
    return max(1, min(5, int(round((2 * i + 3 * u) / 5 + 1e-9))))


def depende_de_quien(quien: str, motivo: str = "") -> str:
    """quien (v2) -> depende (viejo). 'externo' es damian con motivo que empieza por 'externo'."""
    if quien == "implementador":
        return "ia"
    if quien == "damian" and str(motivo or "").strip().lower().startswith("externo"):
        return "externo"
    return quien if quien in ("ia", "claude", "damian") else "ia"


def ids_en(texto) -> list[str]:
    """Los T### que nombra un texto (bloqueada_por), sin repetir y en orden."""
    return list(dict.fromkeys(_RE_ID.findall(str(texto or ""))))


# ------------------------------------------------------------------ etiquetas <-> origen

def _separar_etiquetas(etiquetas) -> tuple[list[str], dict, str]:
    """(etiquetas que se quedan, rastreo {clave: valor|[valores]}, cat) a partir de la lista de etiquetas."""
    quedan: list[str] = []
    rastreo: dict = {}
    cat = ""
    for e in etiquetas or []:
        if not isinstance(e, str) or ":" not in e:
            quedan.append(e)
            continue
        fam, valor = e.split(":", 1)
        if fam == "cat" and not cat:
            cat = valor
        elif fam in RASTREO:
            clave = RASTREO[fam]
            if clave in rastreo:
                previo = rastreo[clave]
                rastreo[clave] = (previo if isinstance(previo, list) else [previo]) + [valor]
            else:
                rastreo[clave] = valor
        else:
            quedan.append(e)
    return quedan, rastreo, cat


def _etiquetas_de_rastreo(origen: dict) -> list[str]:
    tags = []
    for clave, valor in (origen or {}).items():
        fam = _FAMILIA_DE_CLAVE.get(clave)
        if not fam:
            continue
        for v in (valor if isinstance(valor, list) else [valor]):
            tags.append(f"{fam}:{v}")
    return tags


def tipo_de(cat: str) -> str:
    return TIPO_DE_CAT.get(cat, "")


# ------------------------------------------------------------------ entrada (v2 -> viejo)

def entrada(campos: dict) -> dict:
    """Traduce los nombres v2 de una llamada (anadir/actualizar) a los viejos. Los v2 ganan si vienen los dos.

    No toca `tipo` ni `origen` (necesitan las etiquetas de la tarea): lo hace `aplicar_tipo_origen`.
    """
    c = dict(campos)
    if "quien" in c:
        q = c.pop("quien")
        c["depende"] = depende_de_quien(q, c.get("motivo_quien", ""))
        c["_quien"] = q
    if "prioridad" in c:
        p = _recortar15(c.pop("prioridad"))
        c["importancia"] = p
        c["urgencia"] = p
    if "esfuerzo" in c:
        c["dificultad"] = _recortar15(c.pop("esfuerzo"))
    if "fecha_limite" in c:
        c["limite"] = c.pop("fecha_limite")
    if "depende_de" in c:
        dd = c.pop("depende_de")
        if "bloqueada_por" not in c:
            c["bloqueada_por"] = ", ".join(dd) if isinstance(dd, (list, tuple)) else str(dd or "")
    return c


def aplicar_tipo_origen(t: dict, tipo=None, origen=None) -> None:
    """Pone `tipo` (como etiqueta cat:) y `origen` (las familias de rastreo como etiquetas) en la tarea."""
    et = list(t.get("etiquetas") or [])
    if tipo is not None:
        et = [e for e in et if not (isinstance(e, str) and e.startswith("cat:"))]
        if tipo:
            et.append(f"cat:{tipo}")
    if origen is not None:
        libre = {}
        nuevo = []
        if isinstance(origen, str):
            libre["texto"] = origen
        else:
            for k, v in (origen or {}).items():
                if k == "cat":
                    et = [e for e in et if not (isinstance(e, str) and e.startswith("cat:"))]
                    et.append(f"cat:{v}")
                elif k in _FAMILIA_DE_CLAVE:
                    nuevo.append((k, v))
                else:
                    libre[k] = v
        # el origen dado sustituye al de rastreo que tuviera (las familias nombradas)
        nombradas = {_FAMILIA_DE_CLAVE[k] for k, _ in nuevo}
        et = [e for e in et if not (isinstance(e, str) and ":" in e and e.split(":", 1)[0] in nombradas)]
        et += _etiquetas_de_rastreo(dict(nuevo))
        t["_origen_libre"] = {**(t.get("_origen_libre") or {}), **libre}
    t["etiquetas"] = et


# ------------------------------------------------------------------ alinear (viejo -> vistas v2)

def alinear(t: dict) -> dict:
    """Recalcula las vistas v2 desde los campos viejos. Idempotente. Devuelve la misma tarea."""
    for k, v in vacios().items():
        if k not in t:
            t[k] = v

    libre = t.pop("_origen_libre", None)
    quien_dado = t.pop("_quien", None)

    t["prioridad"] = prioridad_de(t.get("importancia", 3), t.get("urgencia", 3))
    t["esfuerzo"] = _recortar15(t.get("dificultad", 3))
    t["fecha_limite"] = t.get("limite") or None
    t["depende_de"] = ids_en(t.get("bloqueada_por"))

    # quien: si el viejo `depende` ya no cuadra con el quien guardado, cambio el viejo y manda el viejo.
    q = quien_dado or t.get("quien") or "ia"
    if q not in QUIEN:
        q = t.get("depende") if t.get("depende") in QUIEN else "ia"
    dep = t.get("depende", "ia")
    if depende_de_quien(q, t.get("motivo_quien", "")) != dep:
        q = dep if dep in QUIEN else ("damian" if dep == "externo" else "ia")
        if dep == "externo" and not str(t.get("motivo_quien") or "").strip().lower().startswith("externo"):
            t["motivo_quien"] = "externo: espera a un tercero"
        elif dep != "externo" and str(t.get("motivo_quien") or "").strip().lower().startswith("externo"):
            t["motivo_quien"] = ""
    t["quien"] = q

    # tipo y origen desde las etiquetas (que mandan en memoria)
    _, rastreo, cat = _separar_etiquetas(t.get("etiquetas"))
    t["tipo"] = tipo_de(cat) if cat else ""
    origen = dict(rastreo)
    if cat and cat != t["tipo"]:
        origen["cat"] = cat
    if isinstance(t.get("origen"), dict):
        # lo libre que ya traia (cuando, texto...) se conserva
        origen.update({k: v for k, v in t["origen"].items() if k not in _FAMILIA_DE_CLAVE and k != "cat"})
    if libre:
        origen.update(libre)
    t["origen"] = origen
    return t


# ------------------------------------------------------------------ disco

def _resumen_cierre(t: dict) -> str:
    ev = (t.get("cierre") or {}).get("evidencia") or ""
    return " ".join(str(ev).split())[:140]


def resumen(t: dict) -> str:
    """Una linea para el historial: id, estado, titulo y como acabo."""
    base = f"{t.get('id', '?')} [{t.get('estado', '?')}] {' '.join(str(t.get('titulo') or '').split())[:90]}"
    fin = _resumen_cierre(t)
    if not fin:
        notas = t.get("notas") or []
        fin = " ".join(str((notas[-1] or {}).get("texto") or "").split())[:140] if notas else ""
    return f"{base} — {fin}" if fin else base


def a_disco(t: dict) -> dict:
    """La tarea en su forma compacta v2. Sin DETALLE_CAMPOS (los guarda el almacen aparte).

    La migracion colapsa importancia/urgencia/coste en memoria ANTES de llamar aqui (fija importancia=urgencia=
    prioridad y coste=2): entonces no hay nada que conservar aparte y el registro sale sin ellos."""
    alinear(t)
    r: dict = {"id": t["id"], "titulo": t["titulo"]}
    for k in ("instrucciones_damian", "objetivo", "hecho_cuando", "donde"):
        if t.get(k):
            r[k] = t[k]
    r["quien"] = t["quien"]
    if t.get("motivo_quien"):
        r["motivo_quien"] = t["motivo_quien"]
    if t.get("tipo"):
        r["tipo"] = t["tipo"]
    r["prioridad"] = t["prioridad"]
    r["esfuerzo"] = t["esfuerzo"]
    if t.get("coste_eur") is not None:
        r["coste_eur"] = t["coste_eur"]
    if t.get("fecha_limite"):
        r["fecha_limite"] = t["fecha_limite"]
    if t.get("depende_de"):
        r["depende_de"] = t["depende_de"]
    if t.get("origen"):
        r["origen"] = t["origen"]
    r["estado"] = t["estado"]
    if t.get("cierre"):
        r["cierre"] = t["cierre"]
    if t.get("despues"):
        r["despues"] = t["despues"]

    # lo que la forma v2 perderia, solo si difiere
    p = t["prioridad"]
    if _recortar15(t.get("importancia")) != p:
        r["importancia"] = _recortar15(t.get("importancia"))
    if _recortar15(t.get("urgencia")) != p:
        r["urgencia"] = _recortar15(t.get("urgencia"))
    if _recortar15(t.get("coste"), 2) != 2:
        r["coste"] = _recortar15(t.get("coste"), 2)
    bp = str(t.get("bloqueada_por") or "")
    if bp and bp != ", ".join(t["depende_de"]):
        r["bloqueada_por"] = bp

    if t.get("detalle"):
        r["detalle"] = t["detalle"]
    if t.get("pregunta_id"):
        r["pregunta_id"] = t["pregunta_id"]
    if t.get("testeado"):
        r["testeado"] = True
    quedan, _, _ = _separar_etiquetas(t.get("etiquetas"))
    if quedan:
        r["etiquetas"] = quedan
    if t.get("notas"):
        r["notas"] = t["notas"][-MAX_NOTAS:]
    r["creada"] = t.get("creada")
    r["actualizada"] = t.get("actualizada")
    r["cerrada"] = t.get("cerrada")

    conocidos = set(r) | set(DETALLE_CAMPOS) | set(CAMPOS_V2) | {
        "importancia", "urgencia", "dificultad", "coste", "depende", "limite", "bloqueada_por",
        "notas", "etiquetas", "detalle", "pregunta_id", "testeado", "resumen",
    }
    for k, v in t.items():
        if k not in conocidos and not k.startswith("_"):
            r[k] = v
    return r


def de_disco(r: dict) -> dict:
    """Abre un registro del disco (v2 compacto, viejo o mezcla) a la tarea completa en memoria."""
    t = dict(r)
    t.pop("resumen", None)

    # lo viejo que falte, de lo v2
    quien = t.get("quien")
    if "depende" not in t:
        t["depende"] = depende_de_quien(quien or "ia", t.get("motivo_quien", ""))
    if "prioridad" in t:
        p = _recortar15(t["prioridad"])
        t.setdefault("importancia", p)
        t.setdefault("urgencia", p)
    if "esfuerzo" in t:
        t.setdefault("dificultad", _recortar15(t["esfuerzo"]))
    if "limite" not in t:
        t["limite"] = t.get("fecha_limite") or None
    if "bloqueada_por" not in t:
        t["bloqueada_por"] = ", ".join(t.get("depende_de") or [])

    # etiquetas: las que se quedan + rastreo + cat
    et = list(t.get("etiquetas") or [])
    origen = t.get("origen") if isinstance(t.get("origen"), dict) else {}
    cat = origen.get("cat") or t.get("tipo") or ""
    en_et = {e for e in et if isinstance(e, str)}
    if cat and f"cat:{cat}" not in en_et:
        et.append(f"cat:{cat}")
    for tag in _etiquetas_de_rastreo(origen):
        if tag not in en_et:
            et.append(tag)
    t["etiquetas"] = et
    t["origen"] = dict(origen)

    for k, v in {"detalle": "", "importancia": 3, "urgencia": 3, "dificultad": 3, "coste": 2,
                 "estado": "pendiente", "limite": None, "pregunta_id": "", "testeado": False,
                 "notas": [], "cerrada": None, "bloqueada_por": ""}.items():
        t.setdefault(k, v)
    return alinear(t)


# ------------------------------------------------------------------ validador

def validar(t: dict) -> list[str]:
    """Avisos de formato de una tarea (lista vacia = bien). NUNCA bloquea: solo informa."""
    p: list[str] = []
    if len(str(t.get("titulo") or "")) > LIM_TITULO:
        p.append(f"titulo de {len(t['titulo'])} caracteres (maximo {LIM_TITULO})")
    obj = str(t.get("objetivo") or "")
    if not obj.strip():
        p.append("falta el objetivo")
    elif len(obj) > LIM_OBJETIVO:
        p.append(f"objetivo de {len(obj)} caracteres (maximo {LIM_OBJETIVO})")
    hc = t.get("hecho_cuando")
    if not isinstance(hc, list) or not (1 <= len(hc) <= MAX_HECHO) or not all(str(x).strip() for x in hc):
        p.append(f"hecho_cuando debe tener de 1 a {MAX_HECHO} comprobaciones")
    if not str(t.get("donde") or "").strip():
        p.append("falta donde")
    if t.get("quien") not in QUIEN:
        p.append(f"quien debe ser {'|'.join(QUIEN)}")
    elif t.get("quien") == "damian" and not str(t.get("motivo_quien") or "").strip():
        p.append("quien=damian pide motivo_quien")
    if t.get("tipo") not in TIPOS:
        p.append(f"tipo debe ser {'|'.join(TIPOS)}")
    for c in ("prioridad", "esfuerzo"):
        v = t.get(c)
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5:
            p.append(f"{c} debe ser 1-5")
    ce = t.get("coste_eur")
    if ce is not None and (isinstance(ce, bool) or not isinstance(ce, (int, float)) or ce < 0):
        p.append("coste_eur debe ser un numero >= 0 (0 si no cuesta)")
    fl = t.get("fecha_limite")
    if fl:
        try:
            datetime.strptime(str(fl), "%Y-%m-%d")
        except ValueError:
            p.append("fecha_limite debe ser AAAA-MM-DD")
    if len(t.get("notas") or []) > MAX_NOTAS:
        p.append(f"mas de {MAX_NOTAS} notas vigentes")
    if t.get("estado") in ("hecha", "descartada"):
        p += problemas_cierre(t)
    return p


def problemas_cierre(t: dict) -> list[str]:
    p = []
    c = t.get("cierre") or {}
    if t.get("estado") == "hecha":
        if c.get("estado_real") not in CIERRES:
            p.append(f"cierre.estado_real debe ser {' o '.join(CIERRES)}")
        if len(str(c.get("evidencia") or "").strip()) < MIN_EVIDENCIA:
            p.append("cierre sin evidencia")
    if not despues_valido(t.get("despues")):
        p.append("despues: la siguiente tarea (T###) o 'nada: motivo'")
    return p


def despues_valido(d) -> bool:
    d = str(d or "").strip()
    if _RE_ID.fullmatch(d):
        return True
    if d.lower().startswith("nada:"):
        return len(d[5:].strip()) >= MIN_NADA - 5
    return False


def declara_v2(t: dict) -> bool:
    """La tarea trae contenido v2 propio: solo a esas se les piden avisos de formato (las viejas no)."""
    return any(t.get(k) for k in ("objetivo", "hecho_cuando", "donde", "instrucciones_damian"))
