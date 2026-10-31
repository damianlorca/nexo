# -*- coding: utf-8 -*-
"""Circuito cerrado de revision (T192, Damian 27/09): borrador de NEXO -> revision de Claude -> implementacion.

Condicion de Damian para reactivar los turnos. Lo que NEXO investiga no se queda en un cajon ni se
implementa solo:

  1. PLANTILLA: todo informe de investigacion termina con '### PROPUESTAS IMPLEMENTABLES' (una linea
     por propuesta: QUE | DONDE | VALOR 1-5 | ESFUERZO 1-5 | RIESGO) o 'NINGUNA: <por que>'. La pide
     trabajo.INSTRUCCION y la comprueba el auditor (punto h, `comprobar_seccion`).
  2. AL GUARDAR EL BORRADOR (`registrar_borrador`, lo llama trabajo.ciclo): una tarea de REVISION para
     Claude (cat:revision) y una tarea en estado 'propuesta' por cada propuesta, enlazadas con la
     tarea origen (etiqueta tarea_origen:Txxx) y el borrador (de_borrador:<archivo>). Las propuestas
     llevan bloqueada_por = la revision: no se implementa nada sin veredicto de Claude.
  3. COLA (`cola`, `comprobar_cola`): borradores y propuestas pendientes con su antiguedad, en la web
     (panel del centro) y aviso push (nucleo.avisos) si hay >= UMBRAL_COLA o alguno supera DIAS_MAX.
  4. VEREDICTO (`veredicto`, solo Claude): APROBADO -> propuestas a 'pendiente' con prioridad y la
     origen se cierra con evidencia; DESCARTADO -> origen y propuestas descartadas con motivo;
     REHACER -> la origen vuelve a NEXO con las instrucciones en su detalle; SUPERADO (T224) -> el
     trabajo ya lo hizo Claude por otra via: cierra la revision, descarta las propuestas y anota en la
     origen donde vive el trabajo real SIN cambiar su estado. La origen NO se puede cerrar antes (tareas.completar lo impide mientras tenga la etiqueta revision_claude:).
     T674: si la origen es una INVESTIGACION (nucleo.investigacion), DESCARTADO y REHACER juzgan el BORRADOR, no el
     contenido: la investigacion sigue viva (vuelve a pendiente; tras 2 seguidos, 'esperando' a Claude). APROBADO
     exige RESULTADO ADOPTAR/ADAPTAR/DESCARTAR + motivo: DESCARTAR la cierra, ADOPTAR/ADAPTAR crea su integracion.

El extractor de propuestas es un parser determinista, no Qwen: el formato es fijo y lo exige el
auditor, y un parser no alucina ni gasta RAM (minimo recurso suficiente). Si el formato no se lee,
la revision lo dice y Claude lo ve.

CLI:
  .venv\\Scripts\\python.exe -m nucleo.revision cola
  .venv\\Scripts\\python.exe -m nucleo.revision registrar T167 T167_20260927_1539.md
  .venv\\Scripts\\python.exe -m nucleo.revision veredicto T167_20260927_1539.md APROBADO "motivo" [T210=4 T211=descartar]
  .venv\\Scripts\\python.exe -m nucleo.revision veredicto <borrador> REHACER "motivo" --instrucciones "que corregir"
  .venv\\Scripts\\python.exe -m nucleo.revision veredicto <borrador> APROBADO "motivo" --resultado ADOPTAR "motivo del resultado"   (investigaciones, T674)
  .venv\\Scripts\\python.exe -m nucleo.revision veredicto <borrador> SUPERADO "donde esta el trabajo real"
  .venv\\Scripts\\python.exe -m nucleo.revision superada T134 "donde esta el trabajo real"  (corrige un DESCARTADO)
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

from nucleo import tareas as T

RAIZ = Path(__file__).resolve().parent.parent
BORRADORES = RAIZ / "memoria" / "borradores"

SECCION = "PROPUESTAS IMPLEMENTABLES"
VEREDICTOS = ("APROBADO", "DESCARTADO", "REHACER", "SUPERADO")
# T667: quien puede dar el veredicto -> (como se nombra en "Revision de ...", en "APROBADA por ...").
QUIENES = {"claude": ("Claude", "Claude"), "tribunal": ("el tribunal", "el tribunal"), "damian": ("Damian", "Damian")}
UMBRAL_COLA = 5              # borradores esperando revision -> aviso
DIAS_MAX = 7                 # alguno mas viejo -> aviso
MIN_JUSTIFICACION = 15       # 'NINGUNA: <por que>' necesita un por que de verdad

ET_REVISION = "revision:borrador"          # la tarea de revision de Claude
ET_PROPUESTA = "cat:propuesta"
PRE_ORIGEN = "tarea_origen:"
PRE_BORRADOR = "de_borrador:"
PRE_PENDIENTE = "revision_claude:"         # en la tarea origen mientras espera veredicto
# Etiquetas de una pasada de NEXO que se quitan al REHACER (asi trabajo.candidatas la vuelve a coger).
ET_PASADA = ("borrador:revisar_claude", "ok_absoluto", "auditoria:bloqueada", "user_decision_required")

_CAMPO = re.compile(r"(?i)\b(QU[EÉ]|D[OÓ]NDE|TEST|VALOR|ESFUERZO|RIESGO)\s*:")
_NOMBRE_CAMPO = {"QUE": "que", "QUÉ": "que", "DONDE": "donde", "DÓNDE": "donde", "VALOR": "valor",
                 "ESFUERZO": "esfuerzo", "RIESGO": "riesgo", "TEST": "test"}
# T675 fase 2: evidencia que exigen los turnos de revision (archivo con linea y un test que lo comprueba).
TOPE_CON_EVIDENCIA = 3
# T1007: una investigacion propone como mucho 2 y solo con un DONDE real (archivo o modulo/carpeta de NEXO).
TOPE_INVESTIGACION = 2
_DONDE_REAL = re.compile(r"[\w./\-]+\.(?:py|md|js|json|toml|ps1|bat|html|css|txt|ini)\b|"
                         r"\b(?:nucleo|interfaz|canal|extremidades|roles|manos|memoria|herramientas_nube|"
                         r"tests|tests_dados|router|proveedores|planificador|tribunal|implementador|vigia|navegador)\b|documentacion/", re.I)
_ARCHIVO_LINEA = re.compile(r"[\w./\-]+\.\w{1,5}(?::\d+|\s*,?\s*(?:l[ií]neas?|L)\s*\d+)", re.I)
_CABECERA = re.compile(r"(?im)^[ \t#*_>\d.)-]*PROPUESTAS\s+IMPLEMENTABLES\b[ \t*_:]*$")
# Donde acaba la seccion: el cierre del autor, las fuentes que anade NEXO u otra cabecera Markdown.
_FIN = re.compile(r"(?im)^[ \t#*_=>-]*(AUTOAUDITOR[IÍ]A|CIERRE\s*:|COMPROBADO\s*:|CAMBIOS\s*:|RECHAZADO\s*:|"
                  r"Fuentes enlazadas)|^#{1,6}\s")
_INICIO_ITEM = re.compile(r"(?im)^[ \t]*(?:[-*•]|\d+[.)])?[ \t]*(?=QU[EÉ]\s*:)")
_NINGUNA = re.compile(r"(?im)^[ \t\-*•]*NINGUNA\b[ \t*_]*[:.\-—]?[ \t]*(.*)$")


# ------------------------------------------------------------------ la seccion
def _seccion(texto: str) -> str | None:
    """Texto de la ULTIMA seccion PROPUESTAS IMPLEMENTABLES (sin la cabecera) o None si no hay."""
    marcas = list(_CABECERA.finditer(texto or ""))
    if not marcas:
        return None
    resto = texto[marcas[-1].end():]
    # T265: con las cabeceras de la web ya como '#', una sub-cabecera ('#### Propuesta 1') no cierra la
    # seccion; solo otra de su nivel o superior (sin '#' en la cabecera, cualquiera, como antes).
    nivel = len(re.match(r"[ \t]*(#*)", marcas[-1].group()).group(1)) or 6
    fin = next((m for m in _FIN.finditer(resto)
                if m.group(1) or len(m.group().rstrip()) <= nivel), None)
    return (resto[:fin.start()] if fin else resto).strip()


def _nivel(valor: str) -> int | None:
    m = re.search(r"[1-5]", valor or "")
    return int(m.group()) if m else None


def extraer_propuestas(texto: str, evidencia: bool = False, tope: int | None = None, donde_real: bool = False) -> dict:
    """{"hay_seccion", "propuestas": [{que, donde, test, valor, esfuerzo, riesgo, faltan}], "ninguna", "problemas"}.

    `evidencia` (turnos de revision, T675 fase 2): solo pasan las propuestas con DONDE = archivo:linea y TEST; las
    demas quedan en `sin_evidencia` (con el motivo) y, pasadas las TOPE_CON_EVIDENCIA primeras, el resto en `sobran`.
    T1007: `donde_real` (investigaciones) deja en `sin_evidencia` las que no nombran un archivo o modulo de NEXO y
    `tope` corta las que pasen de ese numero (a `sobran`)."""
    sec = _seccion(texto)
    salida = {"hay_seccion": sec is not None, "propuestas": [], "ninguna": None, "problemas": [],
              "sin_evidencia": [], "sobran": 0}
    if sec is None:
        salida["problemas"].append(f"falta la seccion {SECCION}")
        return salida
    limpio = sec.replace("**", "").replace("__", "")
    inicios = [m.start() for m in _INICIO_ITEM.finditer(limpio)]
    for i, ini in enumerate(inicios):
        trozo = limpio[ini:inicios[i + 1] if i + 1 < len(inicios) else len(limpio)]
        campos: dict[str, str] = {}
        marcas = list(_CAMPO.finditer(trozo))
        for j, m in enumerate(marcas):
            fin = marcas[j + 1].start() if j + 1 < len(marcas) else len(trozo)
            nombre = _NOMBRE_CAMPO[m.group(1).upper()]
            campos.setdefault(nombre, " ".join(trozo[m.end():fin].split()).strip(" |;-—"))
        p = {"que": campos.get("que", ""), "donde": campos.get("donde", ""), "test": campos.get("test", ""), "valor": _nivel(campos.get("valor", "")),
             "esfuerzo": _nivel(campos.get("esfuerzo", "")), "riesgo": campos.get("riesgo", "")}
        p["faltan"] = [k for k in ("que", "donde", "valor", "esfuerzo", "riesgo") if not p[k]]
        if p["que"]:
            salida["propuestas"].append(p)
    if evidencia:
        buenas = []
        for p in salida["propuestas"]:
            falta = ([] if _ARCHIVO_LINEA.search(p["donde"]) else ["sin archivo:linea en DONDE"])                 + ([] if p["test"] else ["sin TEST"])
            if falta:
                salida["sin_evidencia"].append(f"{p['que'][:60]} ({', '.join(falta)})")
            else:
                buenas.append(p)
        salida["sobran"] = max(0, len(buenas) - TOPE_CON_EVIDENCIA)
        salida["propuestas"] = buenas[:TOPE_CON_EVIDENCIA]
    if donde_real:
        buenas = []
        for p in salida["propuestas"]:
            if _DONDE_REAL.search(p["donde"]):
                buenas.append(p)
            else:
                salida["sin_evidencia"].append(f"{p['que'][:60]} (DONDE sin archivo ni modulo real)")
        salida["propuestas"] = buenas
    if tope is not None and len(salida["propuestas"]) > tope:
        salida["sobran"] += len(salida["propuestas"]) - tope
        salida["propuestas"] = salida["propuestas"][:tope]
    if not salida["propuestas"]:
        m = _NINGUNA.search(limpio)
        if m:
            salida["ninguna"] = m.group(1).strip()
            if len(salida["ninguna"]) < MIN_JUSTIFICACION:
                salida["problemas"].append("'NINGUNA' sin justificar")
        else:
            salida["problemas"].append("la seccion no trae propuestas legibles ni 'NINGUNA: <por que>'")
    for n, p in enumerate(salida["propuestas"], 1):
        if p["faltan"]:
            salida["problemas"].append(f"propuesta {n} sin {', '.join(p['faltan'])}")
    return salida


def comprobar_seccion(texto: str) -> tuple[bool, str]:
    """Punto h del auditor: (ok, detalle)."""
    r = extraer_propuestas(texto)
    if r["problemas"]:
        return False, "; ".join(r["problemas"])
    if r["propuestas"]:
        return True, f"{len(r['propuestas'])} propuesta(s) implementable(s) completas"
    return True, f"ninguna propuesta, justificado: {r['ninguna'][:120]}"


def version_final(md: str) -> str:
    """Del .md de un borrador, la version que cuenta ('## Version final' o '## Ultima version ...')."""
    m = re.search(r"(?m)^## (Version final|Ultima version)[^\n]*\n", md or "")
    if not m:
        return md or ""
    resto = md[m.end():]
    fin = re.search(r"(?m)^## (?!#)", resto)
    return resto[:fin.start()] if fin else resto


# ------------------------------------------------------------------ utilidades de tareas
def _et(t: dict, prefijo: str) -> str:
    return next((e[len(prefijo):] for e in t.get("etiquetas") or [] if e.startswith(prefijo)), "")


def _avisar_descartes(creadas: list[dict]) -> None:
    """T688 pieza 3: cada propuesta nueva que se parezca a algo ya DESCARTADO lleva el motivo anterior en una nota.
    Solo avisa; si falla, las propuestas quedan registradas igual."""
    try:
        from nucleo import descartes
        reg = descartes.registro()
        for c in creadas:
            descartes.avisar(c["id"], reg=reg)
    except Exception as e:   # el aviso es accesorio
        import logging
        logging.getLogger(__name__).warning("aviso de descartes fallo: %s", type(e).__name__)


def _vivas() -> list[dict]:
    return [t for t in T.cargar()["tareas"] if t["estado"] in T.VIVOS]


def _nombre(borrador: str | Path) -> str:
    return str(borrador).replace("\\", "/").rsplit("/", 1)[-1]


def revision_de(borrador: str) -> dict | None:
    """La tarea de revision (viva) del borrador `borrador`."""
    nombre = _nombre(borrador)
    return next((t for t in _vivas() if ET_REVISION in (t.get("etiquetas") or [])
                 and _et(t, PRE_BORRADOR) == nombre), None)


def _enrutar(pid: str) -> None:
    """T837: una propuesta aprobada que ningun turno ejecuta pasa a Claude con triaje (o al implementador si ya
    tiene tests dados). Nunca rompe la aprobacion."""
    try:
        from nucleo import enrutado
        enrutado.enrutar(pid, "al aprobarla")
    except Exception as e:   # el enrutado es accesorio: la aprobacion ya esta hecha
        T.anotar(pid, f"T837: no se pudo enrutar al aprobar ({type(e).__name__}); queda depende=ia")


def propuestas_de(borrador: str, estados: tuple = ("propuesta",)) -> list[dict]:
    nombre = _nombre(borrador)
    return [t for t in T.cargar()["tareas"] if ET_PROPUESTA in (t.get("etiquetas") or [])
            and _et(t, PRE_BORRADOR) == nombre and t["estado"] in estados]


def revision_pendiente(t: dict) -> str:
    """Id de la revision de Claude que espera la tarea `t` ('' si ninguna). Lo usa tareas.completar."""
    return _et(t, PRE_PENDIENTE)


def _quitar(etiquetas: list[str], *prefijos: str) -> list[str]:
    return [e for e in etiquetas if not any(e == p or (p.endswith(":") and e.startswith(p)) for p in prefijos)]


# ------------------------------------------------------------------ 2) al guardar el borrador
def _quitar_repetidas(ext: dict, origen: dict, nombre: str) -> list[str]:
    """T1007: antes de crear cada propuesta, filtro sin IA contra las abiertas y las descartadas (embeddings locales de
    nucleo.freno). Si se parece a una existente, NO se crea: se anota en ella y aqui se devuelve el aviso. Si el filtro
    falla, se crean todas como antes."""
    if not ext["propuestas"]:
        return []
    try:
        from nucleo import freno
        dups = freno.parecidas_a_existentes([p["que"] for p in ext["propuestas"]])
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("filtro de repetidas fallo: %s", type(e).__name__)
        return []
    nuevas, avisos = [], []
    for p, d in zip(ext["propuestas"], dups):
        if d is None:
            nuevas.append(p)
            continue
        if d["id"]:
            T.anotar(d["id"], f"T1007: {origen['id']} (borrador {nombre}) propone de nuevo algo parecido "
                              f"({d['parecido']}, {d['metodo']}): {p['que'][:200]}. No se crea otra propuesta.")
        avisos.append(f"'{p['que'][:60]}' ~ {d['id'] or 'otra del mismo informe'} ({d['tipo']}, {d['parecido']})")
    ext["propuestas"] = nuevas
    ext["repetidas"] = avisos
    return avisos


def registrar_borrador(tarea_id: str, borrador: str | Path, texto: str | None = None,
                       auditoria: str = "") -> dict:
    """Crea la revision de Claude y las propuestas del borrador. Idempotente por borrador.

    `texto`: la version final (si None, se lee del .md). Devuelve {"revision", "propuestas", "extraccion",
    "sustituida", "nueva"}. Si la origen esperaba la revision de un borrador anterior, esa revision y sus
    propuestas quedan descartadas: Claude revisa siempre el ultimo.
    """
    nombre = _nombre(borrador)
    origen = next((t for t in T.cargar()["tareas"] if t["id"].lower() == tarea_id.strip().lower()), None)
    if origen is None:
        raise ValueError(f"la tarea {tarea_id} no existe")
    ya = revision_de(nombre)
    if ya is not None:
        return {"revision": ya, "propuestas": propuestas_de(nombre), "extraccion": None, "sustituida": "",
                "nueva": False}
    if texto is None:
        ruta = Path(borrador) if Path(borrador).is_file() else BORRADORES / nombre
        texto = version_final(ruta.read_text(encoding="utf-8", errors="replace"))
    from nucleo import plantillas_turno
    plantilla = plantillas_turno.plantilla_de(origen)
    es_inv = "cat:investigacion" in (origen.get("etiquetas") or []) and not plantilla   # T1007
    ext = extraer_propuestas(texto, evidencia=plantilla in ("revisar_codigo", "revisar_archivos"),
                             tope=TOPE_INVESTIGACION if es_inv else None, donde_real=es_inv)
    repetidas = _quitar_repetidas(ext, origen, nombre)

    sustituida = ""
    anterior = revision_pendiente(origen)
    if anterior:
        vieja = next((t for t in _vivas() if t["id"] == anterior), None)
        if vieja is not None:
            sustituida = anterior
            for p in propuestas_de(_et(vieja, PRE_BORRADOR)):
                T.actualizar(p["id"], estado="descartada", causa="sustituida",
                             motivo=f"el borrador {nombre} sustituye al suyo sin revisarlo")
                T.anotar(p["id"], f"Descartada sin revisar: el borrador {nombre} sustituye al suyo (T192).")
            T.actualizar(anterior, estado="descartada")
            T.anotar(anterior, f"Sustituida por la revision del borrador {nombre}, mas reciente.")

    ruta_rel = f"memoria/borradores/{nombre}"
    if ext["propuestas"]:
        resumen = f"{len(ext['propuestas'])} propuesta(s) en estado 'propuesta'"
    elif repetidas:
        resumen = "NINGUNA propuesta nueva: ya existian parecidas (" + "; ".join(repetidas)[:300] + ")"
    elif ext["sin_evidencia"]:
        resumen = "SIN propuestas con evidencia (archivo:linea y TEST): " + "; ".join(ext["sin_evidencia"])[:300]
    elif ext["ninguna"] is not None:
        resumen = f"NINGUNA propuesta; justificacion del autor: {ext['ninguna'][:200]}"
    else:
        resumen = "SIN propuestas legibles (" + "; ".join(ext["problemas"]) + ")"
    rev = T.anadir(
        f"Revisar borrador de {origen['id']}: {origen['titulo'][:80]}",
        detalle=(f"Borrador {ruta_rel} (auditoria {auditoria or '?'}) de la tarea {origen['id']}. {resumen}.\n"
                 f"Veredicto (solo Claude): .venv\\Scripts\\python.exe -m nucleo.revision veredicto {nombre} "
                 "APROBADO|DESCARTADO|REHACER|SUPERADO \"motivo\". APROBADO pasa las propuestas a pendiente; "
                 "REHACER necesita --instrucciones."),
        importancia=origen.get("importancia", 3), urgencia=3, dificultad=2, coste=1, depende="ia",
        etiquetas=["cat:revision", "prov:claude", ET_REVISION, f"{PRE_ORIGEN}{origen['id']}",
                   f"{PRE_BORRADOR}{nombre}"])

    creadas = []
    for p in ext["propuestas"]:
        detalle = (f"QUE: {p['que']}\nDONDE: {p['donde'] or '?'}\nVALOR: {p['valor'] or '?'} · ESFUERZO: "
                   f"{p['esfuerzo'] or '?'}\nRIESGO: {p['riesgo'] or '?'}\n"
                   f"Sale del borrador {ruta_rel} (tarea origen {origen['id']}). No se implementa sin el "
                   f"veredicto de Claude en {rev['id']} (T192).")
        creadas.append(T.anadir(
            f"[Propuesta de {origen['id']}] {p['que'][:100]}", detalle=detalle, estado="propuesta",
            importancia=p["valor"] or 3, urgencia=2, dificultad=p["esfuerzo"] or 3, coste=2, depende="ia",
            bloqueada_por=rev["id"],
            etiquetas=[ET_PROPUESTA, "prov:claude", f"{PRE_ORIGEN}{origen['id']}", f"{PRE_BORRADOR}{nombre}"]))
    if creadas:
        T.actualizar(rev["id"], detalle=rev["detalle"] + "\nPropuestas: " + ", ".join(c["id"] for c in creadas))
        _avisar_descartes(creadas)

    et = _quitar(list(T.buscar(origen["id"]).get("etiquetas") or []), PRE_PENDIENTE)
    T.actualizar(origen["id"], etiquetas=et + [f"{PRE_PENDIENTE}{rev['id']}"])
    T.anotar(origen["id"], f"T192: borrador {nombre} en la cola de revision de Claude ({rev['id']}); "
                           + (f"propuestas {', '.join(c['id'] for c in creadas)}." if creadas else resumen + ".")
                           + (f" Sin evidencia, no creadas: {'; '.join(ext['sin_evidencia'])[:300]}."
                              if ext["sin_evidencia"] and creadas else "")
                           + (f" Por encima del tope: {ext['sobran']}." if ext["sobran"] else "")
                           + (f" Parecidas a otras ya existentes (anotado en ellas, no creadas): {'; '.join(repetidas)[:300]}."
                              if repetidas else "")
                           + (f" Sustituye a la revision {sustituida}." if sustituida else "")
                           + " No se cierra sin veredicto.")
    return {"revision": T.buscar(rev["id"]), "propuestas": creadas, "extraccion": ext, "sustituida": sustituida,
            "nueva": True}


# ------------------------------------------------------------------ 3) la cola
def _fecha_borrador(nombre: str) -> datetime | None:
    m = re.search(r"_(\d{8})_(\d{4})\.md$", nombre)
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M") if m else None
    except ValueError:
        return None


def _dias(desde: datetime | None, ahora: datetime) -> float:
    return round((ahora - desde).total_seconds() / 86400, 1) if desde else 0.0


def _creada(t: dict) -> datetime | None:
    try:
        return datetime.strptime(t.get("creada") or "", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _riesgo(t: dict) -> str:
    m = re.search(r"(?m)^RIESGO:\s*(.*)$", t.get("detalle") or "")
    return m.group(1).strip() if m else ""


def cola(ahora: datetime | None = None) -> dict:
    """Lo que espera a Claude: revisiones de borradores y propuestas, con su antiguedad en dias."""
    ahora = ahora or datetime.now()
    vivas = _vivas()
    revisiones = []
    for t in vivas:
        if ET_REVISION not in (t.get("etiquetas") or []):
            continue
        nombre = _et(t, PRE_BORRADOR)
        # La antiguedad cuenta desde el borrador (lo que lleva esperando el trabajo), no desde la tarea.
        desde = _fecha_borrador(nombre) or _creada(t)
        revisiones.append({"id": t["id"], "origen": _et(t, PRE_ORIGEN), "borrador": nombre, "titulo": t["titulo"],
                           "dias": _dias(desde, ahora), "desde": desde.strftime("%Y-%m-%d %H:%M") if desde else "",
                           "propuestas": len(propuestas_de(nombre))})
    propuestas = []
    for t in vivas:
        if t["estado"] != "propuesta":
            continue
        nombre = _et(t, PRE_BORRADOR)
        desde = _fecha_borrador(nombre) or _creada(t)
        propuestas.append({"id": t["id"], "titulo": t["titulo"], "origen": _et(t, PRE_ORIGEN), "borrador": nombre,
                           "revision": t.get("bloqueada_por") or "", "valor": t.get("importancia"),
                           "esfuerzo": t.get("dificultad"), "riesgo": _riesgo(t), "dias": _dias(desde, ahora)})
    revisiones.sort(key=lambda r: -r["dias"])
    propuestas.sort(key=lambda p: (-p["dias"], T.clave_id(p["id"])))
    con_revision = {r["id"] for r in revisiones}
    huerfanas = [p for p in propuestas if p["revision"] not in con_revision]
    pendientes = len(revisiones) + len(huerfanas)
    vieja = max([r["dias"] for r in revisiones] + [p["dias"] for p in propuestas] + [0.0])
    motivos = []
    if pendientes >= UMBRAL_COLA:
        motivos.append(f"{pendientes} borradores esperan revision (umbral {UMBRAL_COLA})")
    if vieja > DIAS_MAX:
        motivos.append(f"el mas antiguo lleva {vieja:.0f} dias (maximo {DIAS_MAX})")
    return {"revisiones": revisiones, "propuestas": propuestas, "huerfanas": huerfanas, "pendientes": pendientes,
            "mas_antigua": vieja, "alerta": bool(motivos), "motivos": motivos}


def comprobar_cola(ahora: datetime | None = None) -> Path | None:
    """Si la cola pasa del umbral o de la antiguedad, deja un aviso (push). Como mucho uno al dia."""
    c = cola(ahora)
    if not c["alerta"]:
        return None
    from nucleo import avisos
    ahora = ahora or datetime.now()
    clave = f"revision:cola:{ahora:%Y-%m-%d}"
    if avisos.ya_emitido(clave):   # emitir() solo frena 1 h; esto, un dia entero
        return None
    return avisos.emitir("revision", f"Cola de revision de Claude: {c['pendientes']} borrador(es) esperando",
                         "; ".join(c["motivos"]) + ". Sin revision no se cierra ni se implementa nada.",
                         ruta="/#t-revision", clave=clave, urgencia="normal",
                         ahora=ahora.timestamp())


# ------------------------------------------------------------------ 4) el veredicto de Claude
def veredicto(borrador: str, decision: str, motivo: str, instrucciones: str = "",
              propuestas: dict[str, int | str] | None = None, resultado: tuple[str, str] | None = None,
              quien: str = "claude") -> dict:
    """Aplica el veredicto sobre un borrador. Lo llaman Claude (sesion o CLI), el tribunal (T667, unanimidad de
    3 familias o apelacion) y Damian desde la bandeja del tribunal; `quien` queda en las notas y el RESULTADO.

    propuestas (solo APROBADO): {id: urgencia 1-5 | "descartar"}. Sin entrada, la urgencia sale del valor
    (valor >= 4 -> 3, si no 2). Registra la evidencia (T160) en la revision y en la origen.
    """
    from nucleo import evidencias
    decision = decision.strip().upper()
    if decision not in VEREDICTOS:
        raise ValueError(f"veredicto desconocido {decision!r}: {', '.join(VEREDICTOS)}")
    if quien not in QUIENES:
        raise ValueError(f"quien desconocido {quien!r}: {', '.join(QUIENES)}")
    de, por = QUIENES[quien]
    motivo = " ".join((motivo or "").split())
    if len(motivo) < MIN_JUSTIFICACION:
        raise ValueError("el veredicto necesita un motivo de verdad (minimo 15 caracteres)")
    if decision == "REHACER" and len((instrucciones or "").strip()) < MIN_JUSTIFICACION:
        raise ValueError("REHACER necesita instrucciones concretas para NEXO")
    nombre = _nombre(borrador)
    rev = revision_de(nombre)
    if rev is None:
        raise ValueError(f"no hay revision pendiente del borrador {nombre}")
    origen_id = _et(rev, PRE_ORIGEN)
    from nucleo import investigacion
    origen0 = T.buscar(origen_id) if origen_id else None
    es_inv = origen0 is not None and origen0["id"] == origen_id and investigacion.es_investigacion(origen0)
    if es_inv and decision == "APROBADO":
        if not resultado:
            raise ValueError(f"{origen_id} es una investigacion: APROBADO necesita --resultado ADOPTAR|ADAPTAR|DESCARTAR "
                             "\"motivo\" (T674)")
        resultado = investigacion._validar(*resultado)
    elif es_inv and decision == "SUPERADO" and resultado:
        resultado = investigacion._validar(*resultado)
    propuestas = {k.upper(): v for k, v in (propuestas or {}).items()}
    mias = propuestas_de(nombre)
    desconocidas = set(propuestas) - {p["id"] for p in mias}
    if desconocidas:
        raise ValueError(f"propuestas que no son de este borrador: {', '.join(sorted(desconocidas))}")
    texto = f"Revision de {de} del borrador {nombre}: {decision}. {motivo}"

    aprobadas, descartadas = [], []
    for p in mias:
        eleccion = propuestas.get(p["id"])
        if decision == "APROBADO" and eleccion != "descartar":
            urg = int(eleccion) if isinstance(eleccion, int) or str(eleccion or "").isdigit() else (
                3 if (p.get("importancia") or 0) >= 4 else 2)
            T.actualizar(p["id"], estado="pendiente", urgencia=urg, bloqueada_por="",
                         etiquetas=list(p.get("etiquetas") or []) + ["propuesta:aprobada"])
            _enrutar(p["id"])
            T.anotar(p["id"], f"APROBADA por {por} ({rev['id']}): {motivo}")
            aprobadas.append(p["id"])
        else:
            porque = {"APROBADO": f"descartada por {por} al aprobar el borrador", "DESCARTADO": "borrador descartado",
                   "REHACER": "el borrador se rehace; saldran propuestas nuevas",
                   "SUPERADO": "borrador superado: el trabajo se hizo por otra via"}[decision]
            causa = {"APROBADO": "idea", "SUPERADO": "superado"}.get(decision, "borrador")
            T.actualizar(p["id"], estado="descartada", bloqueada_por="", causa=causa, motivo=f"{porque}: {motivo}")
            T.anotar(p["id"], f"Descartada ({porque}, {rev['id']}): {motivo}")
            descartadas.append(p["id"])
    resumen_p = (f" Propuestas aprobadas: {', '.join(aprobadas) or 'ninguna'}; descartadas: "
                 f"{', '.join(descartadas) or 'ninguna'}.")

    # La revision de Claude esta hecha: se cierra con su evidencia.
    evidencias.cerrar(rev["id"], texto + resumen_p,
                      evidencia={"detalle": texto + resumen_p, "tipo": "revision", "fuente": "revision.veredicto"})

    origen = T.buscar(origen_id) if origen_id else None
    if origen is not None and origen["id"] == origen_id and es_inv:
        # T674: el veredicto juzga el borrador; el contenido de la investigacion se decide con su RESULTADO
        et = _quitar(list(origen.get("etiquetas") or []), PRE_PENDIENTE)
        if decision in ("REHACER", "DESCARTADO"):
            # sin etiquetas "borrador:" (trabajo.candidatas las salta): asi NEXO la vuelve a coger
            et = [e for e in et if e not in ET_PASADA] + ["rehacer:revision_claude"]
            cambios = {"etiquetas": list(dict.fromkeys(et))}
            if decision == "REHACER":
                detalle = (origen.get("detalle") or "").rstrip()
                cambios["detalle"] = f"{detalle}\nCORRECCIONES PEDIDAS EN LA REVISION: {' '.join(instrucciones.split())}"
            T.actualizar(origen_id, **cambios)
            T.anotar(origen_id, f"{texto} El borrador no vale, la investigacion sigue viva ({rev['id']}).")
            evidencias.registrar(origen_id, texto, tipo="revision", fuente="revision.veredicto")
            investigacion.borrador_malo(origen_id, decision, motivo)
        elif decision == "SUPERADO":
            # T860: el trabajo ya se hizo por otra via. Nunca vuelve a la cola como "borrador malo": con RESULTADO
            # se cierra; sin el, espera a Claude para fijarlo (T674: una investigacion solo cierra con RESULTADO).
            evidencias.registrar(origen_id, texto, tipo="revision", fuente="revision.veredicto")
            T.anotar(origen_id, texto)
            if resultado:
                T.actualizar(origen_id, etiquetas=list(dict.fromkeys(et + ["revisado:superado"])))
                investigacion.decidir(origen_id, resultado[0], resultado[1], informe=f"memoria/borradores/{nombre}",
                                      evidencia={"detalle": texto, "tipo": "revision", "fuente": "revision.veredicto"},
                                      quien=quien)
            else:
                T.actualizar(origen_id, estado="esperando", depende="claude",
                             etiquetas=list(dict.fromkeys(et + ["revisado:superado", "borrador:superado"])))
                T.anotar(origen_id, "T860: SUPERADO sin RESULTADO: queda esperando a Claude para fijar "
                                    "ADOPTAR/ADAPTAR/DESCARTAR (no vuelve a la cola de los turnos).")
        else:   # APROBADO
            T.actualizar(origen_id, etiquetas=list(dict.fromkeys(et + ["revisado:aprobado"])))
            investigacion.borrador_bueno(origen_id)
            informe = f"memoria/borradores/{nombre}"
            investigacion.decidir(origen_id, resultado[0], resultado[1], informe=informe,
                                  evidencia={"detalle": texto + resumen_p, "tipo": "revision",
                                             "fuente": "revision.veredicto"}, quien=quien)
    elif origen is not None and origen["id"] == origen_id:
        et = _quitar(list(origen.get("etiquetas") or []), PRE_PENDIENTE)
        if decision == "REHACER":
            et = [e for e in et if e not in ET_PASADA] + ["rehacer:revision_claude"]
            detalle = (origen.get("detalle") or "").rstrip()
            T.actualizar(origen_id, etiquetas=list(dict.fromkeys(et)), estado="pendiente",
                         detalle=f"{detalle}\nCORRECCIONES PEDIDAS EN LA REVISION: {' '.join(instrucciones.split())}")
            T.anotar(origen_id, f"{texto} Vuelve a NEXO con instrucciones ({rev['id']}).")
        else:
            T.actualizar(origen_id, etiquetas=list(dict.fromkeys(et + [f"revisado:{decision.lower()}"])))
            if decision == "APROBADO":
                evidencias.cerrar(origen_id, texto + resumen_p,
                                  evidencia={"detalle": texto + resumen_p, "tipo": "revision",
                                             "fuente": "revision.veredicto"})
            else:
                evidencias.registrar(origen_id, texto, tipo="revision", fuente="revision.veredicto")
                T.anotar(origen_id, texto)
                if decision == "DESCARTADO":
                    T.actualizar(origen_id, estado="descartada")
    # Con el veredicto, los bloqueos del auditor de este borrador quedan revisados (dejan de avisar en la web).
    from nucleo import auditor
    resueltas = auditor.resolver_borrador(nombre, decision, motivo)
    return {"revision": rev["id"], "origen": origen_id, "veredicto": decision, "aprobadas": aprobadas,
            "descartadas": descartadas, "auditorias_resueltas": resueltas}


def aplicar_parcial(borrador: str, aprobar: list[str], descartar: list[str], motivo: str,
                    quien: str = "tribunal") -> dict:
    """T667 (Damian 04/10): expediente PARCIAL. Aplica las propuestas en las que el tribunal fue unanime y deja la
    revision ABIERTA con el resto (las divididas van a apelacion). El veredicto final del borrador lo da despues
    veredicto(), que solo ve las que siguen en estado 'propuesta'."""
    if quien not in QUIENES:
        raise ValueError(f"quien desconocido {quien!r}: {', '.join(QUIENES)}")
    _, por = QUIENES[quien]
    nombre = _nombre(borrador)
    rev = revision_de(nombre)
    if rev is None:
        raise ValueError(f"no hay revision pendiente del borrador {nombre}")
    mias = {p["id"]: p for p in propuestas_de(nombre)}
    ajenas = [x for x in list(aprobar) + list(descartar) if x not in mias]
    if ajenas:
        raise ValueError(f"propuestas que no estan pendientes en este borrador: {', '.join(ajenas)}")
    motivo = " ".join((motivo or "").split())
    for pid in aprobar:
        p = mias[pid]
        T.actualizar(pid, estado="pendiente", urgencia=3 if (p.get("importancia") or 0) >= 4 else 2, bloqueada_por="",
                     etiquetas=list(p.get("etiquetas") or []) + ["propuesta:aprobada"])
        _enrutar(pid)
        T.anotar(pid, f"APROBADA por {por} en revision parcial ({rev['id']}): {motivo}")
    for pid in descartar:
        T.actualizar(pid, estado="descartada", bloqueada_por="", causa="idea",
                     motivo=f"descartada por {por} en revision parcial: {motivo}")
        T.anotar(pid, f"Descartada por {por} en revision parcial ({rev['id']}): {motivo}")
    resto = [p for p in mias if p not in aprobar and p not in descartar]
    T.anotar(rev["id"], f"Revision parcial de {por}: aprobadas {', '.join(aprobar) or 'ninguna'}; descartadas "
                        f"{', '.join(descartar) or 'ninguna'}; siguen en revision {', '.join(resto) or 'ninguna'}.")
    return {"revision": rev["id"], "aprobadas": list(aprobar), "descartadas": list(descartar), "siguen": resto}


def reclasificar_superada(tarea_id: str, motivo: str) -> dict:
    """T224: corrige una origen DESCARTADA por veredicto cuyo trabajo se hizo por otra via.

    Queda como la habria dejado SUPERADO: vuelve a 'pendiente' (su estado al esperar la revision),
    cambia revisado:descartado por revisado:superado y anota donde vive el trabajo real.
    """
    motivo = " ".join((motivo or "").split())
    if len(motivo) < MIN_JUSTIFICACION:
        raise ValueError("reclasificar necesita un motivo de verdad (minimo 15 caracteres)")
    t = T.buscar(tarea_id)
    if t is None or t["id"].lower() != tarea_id.strip().lower():
        raise ValueError(f"no existe la tarea {tarea_id}")
    et = list(t.get("etiquetas") or [])
    if t["estado"] != "descartada" or "revisado:descartado" not in et:
        raise ValueError(f"{t['id']} no esta descartada por un veredicto: no hay nada que reclasificar")
    et = [e for e in et if e not in ("revisado:descartado", "borrador:rechazado")] + ["revisado:superado"]
    T.actualizar(t["id"], estado="pendiente", etiquetas=list(dict.fromkeys(et)))
    return T.anotar(t["id"], f"Reclasificada SUPERADA (no descartada, T224): {motivo}")


# ------------------------------------------------------------------ CLI
def _cli(argv: list[str]) -> int:
    if not argv or argv[0] == "cola":
        c = cola()
        print(f"{c['pendientes']} pendiente(s); mas antigua {c['mas_antigua']} d; alerta: "
              f"{'; '.join(c['motivos']) or 'no'}")
        for r in c["revisiones"]:
            print(f"  {r['id']}  {r['dias']:5.1f} d  origen {r['origen']}  {r['borrador']}  ({r['propuestas']} propuestas)")
        for p in c["propuestas"]:
            print(f"    {p['id']} [propuesta, valor {p['valor']}, esfuerzo {p['esfuerzo']}] {p['titulo'][:90]}")
        return 0
    if argv[0] == "registrar" and len(argv) >= 3:
        r = registrar_borrador(argv[1], argv[2])
        print(f"revision {r['revision']['id']} ({'nueva' if r['nueva'] else 'ya existia'}); propuestas: "
              f"{', '.join(p['id'] for p in r['propuestas']) or 'ninguna'}"
              + (f"; sustituye a {r['sustituida']}" if r["sustituida"] else ""))
        return 0
    if argv[0] == "veredicto" and len(argv) >= 4:
        resto, instrucciones, props, resultado = argv[4:], "", {}, None
        i = 0
        while i < len(resto):
            if resto[i] == "--instrucciones" and i + 1 < len(resto):
                instrucciones = resto[i + 1]
                i += 2
                continue
            if resto[i] == "--resultado" and i + 2 < len(resto):
                resultado = (resto[i + 1], resto[i + 2])
                i += 3
                continue
            k, _, v = resto[i].partition("=")
            props[k] = int(v) if v.isdigit() else v.lower()
            i += 1
        print(veredicto(argv[1], argv[2], argv[3], instrucciones, props, resultado))
        return 0
    if argv[0] == "superada" and len(argv) >= 3:
        t = reclasificar_superada(argv[1], argv[2])
        print(f"{t['id']} -> {t['estado']} (revisado:superado)")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    from nucleo import consola
    consola.preparar()   # consola cp1252 de Windows: '?' en lo que no cabe, tildes intactas
    raise SystemExit(_cli(sys.argv[1:]))
