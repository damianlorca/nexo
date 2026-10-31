# -*- coding: utf-8 -*-
"""F0 de la epica T664 (T666, aprobado por Damian el 03/10): freno y filtro de la cola de propuestas.

Plan: documentacion/PLAN_REVISION_APROBACION_IMPLEMENTACION.md, seccion 3.1. Sin IA (coste 0).

  1. LIMITE DE TRABAJO EN CURSO: como mucho LIMITE_PROPUESTAS propuestas abiertas y LIMITE_REVISIONES
     revisiones de Claude pendientes. Si se supera, los turnos GENERADORAS (los que fabrican propuestas)
     no arrancan: el planificador los quita de la cola y lo apunta (`puede_generar`). Un "Lanzar ya" de
     Damian (manual) si arranca: es su decision.
  2. FILTRO (`evaluar`): reglas deterministas sobre cada propuesta abierta, por orden; la primera que
     salta da el motivo. formato incompleto, caducada (DIAS_CADUCIDAD sin moverse), valor bajo
     (valor <= 2 y esfuerzo >= 4), sin fuentes (el borrador no cita ni una URL ni un archivo), contra una
     decision vigente de Damian (Telegram: nada nuevo, 27/09), duplicada de una tarea abierta o cerrada
     en los ultimos 30 dias, y fusion de propuestas parecidas entre si (se queda la de mas puntuacion).
     Aparte, solo informativo salvo que se pida: EXCEDENTE, lo que sobra por encima del limite de 30
     ordenando por puntuacion.
  3. ARCHIVAR, NO BORRAR: la propuesta pasa a 'descartada' con etiquetas archivada:filtro y filtro:<regla>,
     nota con el motivo y una foto de la tarea entera en REGISTRO; `recuperar` la devuelve tal cual.
  4. SIMULACION PRIMERO: `simular` escribe un informe en INFORMES sin tocar nada; `aplicar` hace lo mismo
     y ademas archiva.
  5. METRICAS (`metricas`): entradas y salidas de propuestas y revisiones por semana y tamano de la cola,
     para el panel del Centro.

CLI:
  .venv\\Scripts\\python.exe -m nucleo.freno estado
  .venv\\Scripts\\python.exe -m nucleo.freno simular [--excedente]
  .venv\\Scripts\\python.exe -m nucleo.freno aplicar [--excedente]
  .venv\\Scripts\\python.exe -m nucleo.freno aplicar --fundir T1,T2 --titulo "..." --motivo "..."
  .venv\\Scripts\\python.exe -m nucleo.freno parecidas [--umbral 0.70] [--modelo bge-m3]   (solo informe)
  .venv\\Scripts\\python.exe -m nucleo.freno recuperar T378
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from nucleo import tareas as T
from nucleo.candado import bloqueo

RAIZ = Path(__file__).resolve().parent.parent
REGISTRO = RAIZ / "memoria" / "freno_archivo.jsonl"
INFORMES = RAIZ / "memoria" / "freno"
BORRADORES = RAIZ / "memoria" / "borradores"

LIMITE_PROPUESTAS = 30
LIMITE_REVISIONES = 15
DIAS_CADUCIDAD = 14
DIAS_DUPLICADO = 30           # cerradas hace menos de esto cuentan para duplicado
UMBRAL_PARECIDO = 0.5         # similitud lexica (0-1) a partir de la cual dos textos son "la misma cosa"
GENERADORAS = ("vigia", "revisar_codigo", "revisar_archivos", "investigacion")

ET_ARCHIVADA = "archivada:filtro"
PRE_REGLA = "filtro:"
ET_PROPUESTA = "cat:propuesta"
ET_REVISION = "revision:borrador"
REGLAS = ("formato", "caducada", "valor_bajo", "sin_fuentes", "decision_vigente", "duplicada", "fundida", "excedente",
         "sin_concreto")
NOMBRE_REGLA = {
    "formato": "formato incompleto", "caducada": f"caducada ({DIAS_CADUCIDAD} dias sin avanzar)",
    "valor_bajo": "valor bajo (valor <= 2 y esfuerzo >= 4)", "sin_fuentes": "sin fuentes en el borrador",
    "decision_vigente": "contradice una decision vigente de Damian", "duplicada": "duplicada de otra tarea",
    "fundida": "fundida con una propuesta parecida", "excedente": f"excedente sobre el limite de {LIMITE_PROPUESTAS}",
    # T1007: solo manual (la aplica quien revisa, no evaluar()): proceso generico que no cambia nada concreto de NEXO
    "sin_concreto": "proceso generico o ajeno a NEXO: no cambia nada concreto",
}
# Decisiones de Damian que dejan sin valor una propuesta (CLAUDE.md). (regla, patron, motivo)
# Se mira el texto de la propuesta y el titulo de su tarea origen (p. ej. "Revision de codigo ...: canal/bot.py").
DECISIONES = (
    (re.compile(r"(?i)\btelegram\b|callback_?query|canal/(?:bot|aprobaciones_bot|buzon)\.py|\bbot\.py\b"),
     "toca el bot de Telegram, y Damian decidio el 27/09 no desarrollar nada nuevo por Telegram"),
)

_CAMPOS = ("QUE", "DONDE", "VALOR", "ESFUERZO", "RIESGO")
_URL = re.compile(r"https?://")
_RUTA = re.compile(r"\b[\w./-]+\.(?:py|md|js|json|toml|ps1|bat|html|css|txt|ini)\b")
_STOP = set("de la el los las un una unos unas y o a en con por para del al que se su sus como sin mas lo le es no si "
            "e u cada antes despues entre sobre desde hasta ya muy tambien solo nexo".split())


# ------------------------------------------------------------------ utilidades
def _et(t: dict, prefijo: str) -> str:
    return next((e[len(prefijo):] for e in t.get("etiquetas") or [] if e.startswith(prefijo)), "")


def _fecha(texto: str | None) -> datetime | None:
    try:
        return datetime.strptime(texto or "", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _campo(t: dict, nombre: str) -> str:
    m = re.search(rf"(?m)^{nombre}:\s*(.*?)(?:\s*·\s*ESFUERZO:.*)?$", t.get("detalle") or "")
    return m.group(1).strip() if m else ""


def que(t: dict) -> str:
    return _campo(t, "QUE") or re.sub(r"^\[Propuesta de T\d+\]\s*", "", t.get("titulo") or "")


def palabras(texto: str) -> set[str]:
    """Raices de 6 letras sin tildes ni palabras vacias: lo justo para comparar sin IA."""
    s = unicodedata.normalize("NFKD", (texto or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return {w[:6] for w in re.findall(r"[a-z0-9_]+", s) if len(w) > 2 and w not in _STOP}


def parecido(a: set[str], b: set[str]) -> float:
    """Jaccard; con textos de menos de 3 raices no se compara (demasiado poco para decir que es lo mismo)."""
    if len(a) < 3 or len(b) < 3:
        return 0.0
    return len(a & b) / len(a | b)


def es_propuesta_abierta(t: dict) -> bool:
    return t.get("estado") == "propuesta"


def es_revision_pendiente(t: dict) -> bool:
    return ET_REVISION in (t.get("etiquetas") or []) and t.get("estado") in T.VIVOS


# ------------------------------------------------------------------ 1) limite de trabajo en curso
def estado_cola(tareas: list[dict] | None = None) -> dict:
    tareas = T.cargar()["tareas"] if tareas is None else tareas
    n_p = sum(1 for t in tareas if es_propuesta_abierta(t))
    n_r = sum(1 for t in tareas if es_revision_pendiente(t))
    motivos = []
    if n_p > LIMITE_PROPUESTAS:
        motivos.append(f"{n_p} propuestas abiertas (limite {LIMITE_PROPUESTAS})")
    if n_r > LIMITE_REVISIONES:
        motivos.append(f"{n_r} revisiones pendientes (limite {LIMITE_REVISIONES})")
    return {"propuestas": n_p, "revisiones": n_r, "limite_propuestas": LIMITE_PROPUESTAS,
            "limite_revisiones": LIMITE_REVISIONES, "superado": bool(motivos), "motivos": motivos}


def puede_generar(plantilla: str, tareas: list[dict] | None = None) -> tuple[bool, str]:
    """(si, '') o (no, motivo). Solo frena las plantillas que fabrican propuestas."""
    if plantilla not in GENERADORAS:
        return True, ""
    e = estado_cola(tareas)
    if not e["superado"]:
        return True, ""
    return False, "freno F0: " + "; ".join(e["motivos"]) + ". Primero hay que revisar o implementar."


# ------------------------------------------------------------------ 2) filtro
def _fuentes_borrador(nombre: str, cache: dict) -> bool | None:
    """True si el borrador cita alguna URL o archivo; None si el borrador no existe."""
    if nombre not in cache:
        ruta = BORRADORES / nombre
        if not nombre or not ruta.is_file():
            cache[nombre] = None
        else:
            tx = ruta.read_text(encoding="utf-8", errors="replace")
            cache[nombre] = bool(_URL.search(tx) or _RUTA.search(tx))
    return cache[nombre]


def _regla_simple(t: dict, ahora: datetime, cache: dict, origen: str = "") -> tuple[str, str] | None:
    d = t.get("detalle") or ""
    faltan = [c for c in _CAMPOS if not re.search(rf"(?m)\b{c}:\s*(?!\?)\S", d)]
    if faltan or len(que(t)) < 20:
        return "formato", "le falta " + (", ".join(faltan) if faltan else "un QUE con contenido (menos de 20 letras)")
    mov = _fecha(t.get("actualizada")) or _fecha(t.get("creada"))
    if mov and (ahora - mov).days >= DIAS_CADUCIDAD:
        return "caducada", f"sin moverse desde {mov:%d/%m} ({(ahora - mov).days} dias)"
    if (t.get("importancia") or 3) <= 2 and (t.get("dificultad") or 3) >= 4:
        return "valor_bajo", f"valor {t.get('importancia')} con esfuerzo {t.get('dificultad')}"
    if "filtro:fusion" in (t.get("etiquetas") or []):
        # la fusion es una decision expresa de Damian (03/10, posterior a las de DECISIONES) y no tiene borrador
        # propio: sus fuentes son las propuestas fundidas. Ni 'sin_fuentes' ni 'decision_vigente' la deshacen.
        return None
    borrador = _et(t, "de_borrador:")
    f = _fuentes_borrador(borrador, cache)
    if f is None:
        return "sin_fuentes", f"el borrador {borrador or '(ninguno)'} no existe"
    if not f:
        return "sin_fuentes", f"el borrador {borrador} no cita ni una URL ni un archivo"
    for patron, motivo in DECISIONES:
        if patron.search(d) or patron.search(t.get("titulo") or ""):
            return "decision_vigente", motivo
        if patron.search(origen):
            return "decision_vigente", motivo + f" (sale de: {origen[:70]})"
    return None


def evaluar(tareas: list[dict] | None = None, ahora: datetime | None = None, excedente: bool = False) -> dict:
    """Decide sin tocar nada que propuestas se archivarian y por que. Devuelve {"archivar": [...], "quedan": [...]}.

    Cada entrada de "archivar": {"id", "titulo", "regla", "motivo", "con"} (con = tarea parecida, si la hay).
    """
    tareas = T.cargar()["tareas"] if tareas is None else tareas
    ahora = ahora or datetime.now()
    props = [t for t in tareas if es_propuesta_abierta(t)]
    cache: dict = {}
    titulos = {t["id"]: t.get("titulo") or "" for t in tareas}
    archivar: list[dict] = []
    vivas: list[dict] = []
    for t in props:
        r = _regla_simple(t, ahora, cache, titulos.get(_et(t, "tarea_origen:"), ""))
        if r:
            archivar.append({"id": t["id"], "titulo": que(t), "regla": r[0], "motivo": r[1], "con": ""})
        else:
            vivas.append(t)

    # duplicada: contra tareas de verdad (no propuestas ni revisiones) abiertas o cerradas hace < 30 dias
    limite = ahora - timedelta(days=DIAS_DUPLICADO)
    otras = [(o, palabras(o.get("titulo") or "")) for o in tareas
             if not es_propuesta_abierta(o) and ET_PROPUESTA not in (o.get("etiquetas") or [])
             and "cat:revision" not in (o.get("etiquetas") or [])
             and (o.get("estado") in T.VIVOS or (_fecha(o.get("cerrada")) or ahora) >= limite)]
    pal = {t["id"]: palabras(que(t)) for t in vivas}
    sigue = []
    for t in vivas:
        mejor = max(((parecido(pal[t["id"]], po), o) for o, po in otras), key=lambda x: x[0], default=(0.0, None))
        if mejor[1] is not None and mejor[0] >= UMBRAL_PARECIDO:
            o = mejor[1]
            archivar.append({"id": t["id"], "titulo": que(t), "regla": "duplicada", "con": o["id"],
                             "motivo": f"parecida ({mejor[0]:.2f}) a {o['id']} ({o['estado']}): {o['titulo'][:80]}"})
        else:
            sigue.append(t)

    # fundida: grupos de propuestas parecidas entre si; se queda la de mas puntuacion (a igualdad, la mas antigua)
    sigue.sort(key=lambda t: (-T.puntuacion(t, ahora.date()), T.clave_id(t["id"])))
    quedan: list[dict] = []
    for t in sigue:
        gemela = next((q for q in quedan if parecido(pal[t["id"]], pal[q["id"]]) >= UMBRAL_PARECIDO), None)
        if gemela is not None:
            archivar.append({"id": t["id"], "titulo": que(t), "regla": "fundida", "con": gemela["id"],
                             "motivo": f"parecida a {gemela['id']} ({que(gemela)[:80]}), que se queda"})
        else:
            quedan.append(t)

    # excedente: solo si se pide; lo que sobra por encima del limite, de menos a mas puntuacion
    sobran = quedan[LIMITE_PROPUESTAS:]
    excedentes = [{"id": t["id"], "titulo": que(t), "regla": "excedente", "con": "",
                   "motivo": f"puesto {i + LIMITE_PROPUESTAS + 1} por puntuacion ({T.puntuacion(t, ahora.date()):.1f})"}
                  for i, t in enumerate(sobran)]
    if excedente:
        archivar += excedentes
        quedan = quedan[:LIMITE_PROPUESTAS]
    orden = {r: i for i, r in enumerate(REGLAS)}
    archivar.sort(key=lambda a: (orden[a["regla"]], T.clave_id(a["id"])))
    return {"total": len(props), "archivar": archivar, "quedan": [t["id"] for t in quedan],
            "excedente_posible": excedentes, "excedente_aplicado": excedente}


# ------------------------------------------------------------------ 3) archivar y recuperar
def _registrar(filas: list[dict]) -> None:
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRO.open("a", encoding="utf-8") as f:
        for fila in filas:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")


def archivar(decisiones: list[dict]) -> list[str]:
    """Archiva de una vez (un solo guardado) las propuestas de `decisiones`. Devuelve los ids archivados."""
    if not decisiones:
        return []
    por_id = {d["id"]: d for d in decisiones}
    ahora = T._ahora()
    hechos, fotos = [], []
    with bloqueo(T.CANDADO):
        datos = T.cargar()
        for t in datos["tareas"]:
            d = por_id.get(t["id"])
            if d is None or not es_propuesta_abierta(t):
                continue
            fotos.append({"cuando": ahora, "id": t["id"], "regla": d["regla"], "motivo": d["motivo"],
                          "con": d.get("con", ""), "antes": json.loads(json.dumps(t))})
            t["estado"] = "descartada"
            t["bloqueada_por"] = ""
            t["etiquetas"] = list(dict.fromkeys(list(t.get("etiquetas") or []) + [ET_ARCHIVADA, PRE_REGLA + d["regla"]]))
            t.setdefault("notas", []).append({"cuando": ahora, "texto": (
                f"Archivada por el filtro F0 (T666), regla {NOMBRE_REGLA[d['regla']]}: {d['motivo']}. "
                f"Recuperable: .venv\\Scripts\\python.exe -m nucleo.freno recuperar {t['id']}")})
            t["actualizada"] = ahora
            t["cerrada"] = ahora
            hechos.append(t["id"])
        if hechos:
            # anota en la que se queda las que se le han fundido (sin cambiarle nada mas)
            fundidas: dict[str, list[str]] = {}
            for d in decisiones:
                if d["regla"] == "fundida" and d["id"] in hechos:
                    fundidas.setdefault(d["con"], []).append(d["id"])
            for t in datos["tareas"]:
                if t["id"] in fundidas:
                    t.setdefault("notas", []).append({"cuando": ahora, "texto": (
                        "Filtro F0 (T666): se le funden las propuestas parecidas " + ", ".join(fundidas[t["id"]]) + ".")})
            _registrar(fotos)
            T.guardar(datos)
    return hechos


def fundir(ids: list[str], titulo: str, motivo: str) -> dict:
    """Funde varias propuestas abiertas en UNA tarea nueva (estado 'propuesta', importancia la mas alta, ids de
    origen en el detalle) y archiva las originales con la regla 'fundida' (recuperables). Decision de Damian 03/10
    para las propuestas de seguridad del bot de Telegram."""
    datos = {t["id"]: t for t in T.cargar()["tareas"]}
    props = [datos[i] for i in ids if i in datos and es_propuesta_abierta(datos[i])]
    if len(props) < 2:
        raise ValueError("hacen falta al menos 2 propuestas abiertas para fundir")
    lineas = [f"- {p['id']} (valor {p.get('importancia')}, esfuerzo {p.get('dificultad')}, de "
              f"{_et(p, 'tarea_origen:') or '?'}): {que(p)}" for p in props]
    nueva = T.anadir(
        titulo, estado="propuesta", depende="ia", urgencia=2,
        importancia=max(p.get("importancia") or 3 for p in props),
        dificultad=max(p.get("dificultad") or 3 for p in props), coste=2,
        detalle=(f"QUE: {titulo}\nDONDE: varias (ver propuestas fundidas)\nVALOR: "
                 f"{max(p.get('importancia') or 3 for p in props)} · ESFUERZO: {max(p.get('dificultad') or 3 for p in props)}\n"
                 f"RIESGO: ver cada propuesta\n{motivo}\nPropuestas fundidas ({len(props)}), recuperables con "
                 f".venv\\Scripts\\python.exe -m nucleo.freno recuperar Txxx:\n" + "\n".join(lineas)),
        etiquetas=[ET_PROPUESTA, "prov:claude", "filtro:fusion"]
                  + [f"fundida_de:{p['id']}" for p in props])
    archivar([{"id": p["id"], "regla": "fundida", "con": nueva["id"],
               "motivo": f"fundida en {nueva['id']} ({motivo})"} for p in props])
    return T.buscar(nueva["id"])


def recuperar(tarea_id: str) -> dict:
    """Devuelve una propuesta archivada por el filtro a como estaba (estado, bloqueo y etiquetas)."""
    tid = tarea_id.strip().upper()
    foto = None
    if REGISTRO.is_file():
        for linea in REGISTRO.read_text(encoding="utf-8").splitlines():
            try:
                f = json.loads(linea)
            except ValueError:
                continue
            if f.get("id") == tid:
                foto = f
    if foto is None:
        raise ValueError(f"{tid} no la archivo el filtro F0")
    with bloqueo(T.CANDADO):
        datos = T.cargar()
        t = next((x for x in datos["tareas"] if x["id"] == tid), None)
        if t is None:
            raise ValueError(f"la tarea {tid} no existe")
        if ET_ARCHIVADA not in (t.get("etiquetas") or []):
            raise ValueError(f"{tid} ya no esta archivada por el filtro")
        antes = foto["antes"]
        t["estado"] = antes["estado"]
        t["bloqueada_por"] = antes.get("bloqueada_por", "")
        t["etiquetas"] = [e for e in (t.get("etiquetas") or []) if e != ET_ARCHIVADA and not e.startswith(PRE_REGLA)]
        t["cerrada"] = None
        t["actualizada"] = T._ahora()
        t.setdefault("notas", []).append({"cuando": t["actualizada"],
                                          "texto": "Recuperada del archivo del filtro F0 (T666)."})
        T.guardar(datos)
        return t


# ------------------------------------------------------------------ 4) simular / aplicar con informe
def _informe_md(ev: dict, cola: dict, ahora: datetime, aplicado: bool) -> str:
    por = {r: [a for a in ev["archivar"] if a["regla"] == r] for r in REGLAS}
    lin = [f"# Filtro F0 (T666) - {'APLICADO' if aplicado else 'SIMULACION'} {ahora:%d/%m/%Y %H:%M}", "",
           f"Propuestas abiertas: **{ev['total']}**. Se archivarian: **{len(ev['archivar'])}**. "
           f"Quedarian: **{len(ev['quedan'])}** (limite {LIMITE_PROPUESTAS}).",
           f"Revisiones de Claude pendientes: **{cola['revisiones']}** (limite {LIMITE_REVISIONES}). "
           f"Freno de turnos generadores: **{'PUESTO' if cola['superado'] else 'no'}**"
           + (f" ({'; '.join(cola['motivos'])})" if cola["motivos"] else "") + ".", "",
           "| Regla | Cuantas |", "|---|---|"]
    lin += [f"| {NOMBRE_REGLA[r]} | {len(por[r])} |" for r in REGLAS if r != "excedente"]
    lin += [f"| {NOMBRE_REGLA['excedente']} ({'aplicada' if ev['excedente_aplicado'] else 'NO aplicada, solo informativa'}) "
            f"| {len(ev['excedente_posible'])} |", ""]
    for r in REGLAS:
        filas = por[r] if r != "excedente" else ev["excedente_posible"]
        if not filas:
            continue
        lin += [f"## {NOMBRE_REGLA[r]} ({len(filas)})", ""]
        lin += [f"- {a['id']}: {a['titulo'][:110]} -> {a['motivo']}" for a in filas]
        lin.append("")
    return "\n".join(lin)


def ejecutar(aplicar_de_verdad: bool = False, excedente: bool = False, ahora: datetime | None = None,
             fundir_ids: tuple[str, ...] = (), fundir_titulo: str = "", fundir_motivo: str = "") -> dict:
    """Evalua y, si `aplicar_de_verdad`, archiva. `fundir_ids` se apartan del archivado normal y se funden en una
    tarea nueva (`fundir`) con `fundir_titulo`."""
    ahora = ahora or datetime.now()
    tareas = T.cargar()["tareas"]
    ev = evaluar(tareas, ahora, excedente=excedente)
    aparte = {i.strip().upper() for i in fundir_ids if i.strip()}
    if aparte:
        ev["apartadas_para_fundir"] = [a for a in ev["archivar"] if a["id"] in aparte]
        ev["archivar"] = [a for a in ev["archivar"] if a["id"] not in aparte]
        ev["quedan"] = sorted(set(ev["quedan"]) | aparte)
    hechos, fusion = [], None
    if aplicar_de_verdad:
        hechos = archivar(ev["archivar"])
        if aparte:
            fusion = fundir(sorted(aparte), fundir_titulo or f"{len(aparte)} propuestas fundidas",
                            fundir_motivo or "fusion pedida por Damian")
            ev["fundidas_en"] = fusion["id"]
            ev["quedan"] = sorted((set(ev["quedan"]) - aparte) | {fusion["id"]}, key=T.clave_id)
    cola = estado_cola()
    md = _informe_md(ev, cola, ahora, aplicar_de_verdad)
    if aparte:
        md += (f"\n## Apartadas para fundir ({len(aparte)})"
               + (f" -> {fusion['id']}: {fusion['titulo']}" if fusion else "") + "\n\n"
               + "\n".join(f"- {a['id']}: {a['titulo'][:110]}" for a in ev["apartadas_para_fundir"]) + "\n")
    INFORMES.mkdir(parents=True, exist_ok=True)
    base = INFORMES / f"{'aplicado' if aplicar_de_verdad else 'simulacion'}_{ahora:%Y%m%d_%H%M}"
    base.with_suffix(".md").write_text(md, encoding="utf-8")
    base.with_suffix(".json").write_text(json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"evaluacion": ev, "archivadas": hechos, "fusion": fusion, "cola": cola,
            "informe": str(base.with_suffix(".md"))}


def simular(excedente: bool = False, ahora: datetime | None = None, **fusion) -> dict:
    return ejecutar(False, excedente, ahora, **fusion)


def aplicar(excedente: bool = False, ahora: datetime | None = None, **fusion) -> dict:
    return ejecutar(True, excedente, ahora, **fusion)


# ------------------------------------------------------------------ 4b) parecidas por embeddings (solo informe)
OLLAMA = "http://127.0.0.1:11434"
MODELO_EMBEDDINGS = "bge-m3"          # 567M, multilingue (Damian 03/10: embeddings locales < 8B, coste cero)
UMBRAL_EMBEDDINGS = 0.80              # (Claude 17/10: 0.70 -> 0.80, porque el 03/10 hubo pares de 0.77 que NO eran duplicados) coseno de CANDIDATO (lo decide F1; aqui no se funde). 03/10 con bge-m3: max 0.77, ningun duplicado real


def _embeber(textos: list[str], modelo: str, lote: int = 32) -> list[list[float]]:
    import httpx
    vectores: list[list[float]] = []
    for i in range(0, len(textos), lote):
        r = httpx.post(f"{OLLAMA}/api/embed", timeout=300,
                       json={"model": modelo, "input": textos[i:i + lote], "keep_alive": "2m",
                             "options": {"num_ctx": 4096}})
        r.raise_for_status()
        vectores += r.json()["embeddings"]
    return vectores


def _coseno(a: list[float], b: list[float]) -> float:
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def _refs_para_nuevas(tareas: list[dict]) -> list[dict]:
    """Propuestas ABIERTAS (vivas) y DESCARTADAS contra las que se compara una propuesta nueva (T1007)."""
    from nucleo import descartes
    refs, vistos = [], set()
    for t in tareas:
        if ET_PROPUESTA in (t.get("etiquetas") or []) and t.get("estado") in T.VIVOS:
            refs.append({"id": t["id"], "texto": que(t), "tipo": "abierta"})
            vistos.add(t["id"])
    for d in descartes.registro(tareas):
        if d["id"] not in vistos:
            refs.append({"id": d["id"], "texto": d["texto"], "tipo": "descartada", "motivo": d.get("motivo", "")})
            vistos.add(d["id"])
    for t in tareas:   # tambien las propuestas archivadas por el filtro o descartadas sin pasar por 'idea'
        if ET_PROPUESTA in (t.get("etiquetas") or []) and t.get("estado") == "descartada" and t["id"] not in vistos:
            refs.append({"id": t["id"], "texto": que(t), "tipo": "descartada", "motivo": ""})
    return refs


def parecidas_a_existentes(textos: list[str], tareas: list[dict] | None = None, embeber=None,
                           umbral: float = UMBRAL_EMBEDDINGS) -> list[dict | None]:
    """T1007: para cada texto de una propuesta NUEVA, la propuesta abierta o descartada a la que se parece (o None).

    Con embeddings locales (bge-m3, coseno >= umbral); si Ollama no responde, cae a la similitud lexica del filtro F0
    (UMBRAL_PARECIDO). Tambien compara entre si las nuevas del mismo informe (tipo 'mismo_informe', id None)."""
    tareas = T.cargar()["tareas"] if tareas is None else tareas
    refs = _refs_para_nuevas(tareas)
    if not textos:
        return []
    try:
        emb = embeber or (lambda x: _embeber(x, MODELO_EMBEDDINGS))
        vn = emb(list(textos))
        vr = emb([r["texto"] for r in refs]) if refs else []
        medida, metodo, minimo = (lambda i, j: _coseno(vn[i], vr[j])), "embeddings", umbral
        entre = lambda i, k: _coseno(vn[i], vn[k])
    except Exception:
        pn, pr = [palabras(x) for x in textos], [palabras(r["texto"]) for r in refs]
        medida, metodo, minimo = (lambda i, j: parecido(pn[i], pr[j])), "lexico", UMBRAL_PARECIDO
        entre = lambda i, k: parecido(pn[i], pn[k])
    salida: list[dict | None] = []
    for i in range(len(textos)):
        mejor = max(((medida(i, j), j) for j in range(len(refs))), default=(0.0, -1))
        previa = next((k for k in range(i) if salida[k] is None and entre(i, k) >= minimo), None)
        if mejor[1] >= 0 and mejor[0] >= minimo:
            r = refs[mejor[1]]
            salida.append({"id": r["id"], "tipo": r["tipo"], "motivo": r.get("motivo", ""), "texto": r["texto"][:110],
                           "parecido": round(mejor[0], 3), "metodo": metodo})
        elif previa is not None:
            salida.append({"id": None, "tipo": "mismo_informe", "motivo": "", "texto": textos[previa][:110],
                           "parecido": round(entre(i, previa), 3), "metodo": metodo})
        else:
            salida.append(None)
    return salida


# T1007: el turno "cola" no coge investigaciones mientras el freno F0 este puesto (el "Lanzar ya" manual si).
def cola_sin_investigaciones(plantilla: str, manual: bool = False, tareas: list[dict] | None = None) -> tuple[bool, str]:
    """(True, motivo) si ESTE turno no debe coger investigaciones ahora. Solo afecta a la plantilla 'cola'."""
    if plantilla != "cola" or manual:
        return False, ""
    e = estado_cola(tareas)
    if not e["superado"]:
        return False, ""
    return True, "freno F0: " + "; ".join(e["motivos"]) + ". La cola no coge investigaciones hasta revisar o implementar."


def pares_semanticos(umbral: float = UMBRAL_EMBEDDINGS, modelo: str = MODELO_EMBEDDINGS,
                     tareas: list[dict] | None = None, embeber=None, ahora: datetime | None = None) -> dict:
    """SOLO SIMULACION: pares propuesta~propuesta y propuesta~tarea de verdad (abierta o cerrada hace < 30 dias)
    con coseno >= umbral. No toca la cola: solo escribe el informe en INFORMES."""
    ahora = ahora or datetime.now()
    tareas = T.cargar()["tareas"] if tareas is None else tareas
    embeber = embeber or (lambda textos: _embeber(textos, modelo))
    props = [t for t in tareas if es_propuesta_abierta(t)]
    limite = ahora - timedelta(days=DIAS_DUPLICADO)
    otras = [o for o in tareas if not es_propuesta_abierta(o) and ET_PROPUESTA not in (o.get("etiquetas") or [])
             and "cat:revision" not in (o.get("etiquetas") or [])
             and (o.get("estado") in T.VIVOS or (_fecha(o.get("cerrada")) or ahora) >= limite)]
    vp = embeber([que(t) for t in props]) if props else []
    vo = embeber([o.get("titulo") or "" for o in otras]) if otras and props else []
    entre, contra = [], []
    vd, descartes_ = [], []
    if props:
        from nucleo import descartes   # T688: tambien contra lo DESCARTADO por idea, con su motivo
        descartes_ = descartes.registro(tareas)
        vd = embeber([d["texto"] for d in descartes_]) if descartes_ else []
    contra_desc = []
    for i in range(len(props)):
        for j in range(i + 1, len(props)):
            c = _coseno(vp[i], vp[j])
            if c >= umbral:
                entre.append({"a": props[i]["id"], "b": props[j]["id"], "coseno": round(c, 3),
                              "texto_a": que(props[i])[:110], "texto_b": que(props[j])[:110]})
        for d, v in zip(descartes_, vd):
            c = _coseno(vp[i], v)
            if c >= umbral:
                contra_desc.append({"a": props[i]["id"], "b": d["id"], "coseno": round(c, 3), "causa": d["causa"],
                                    "motivo": d["motivo"], "quien": d["quien"], "cuando": d["cuando"],
                                    "informe": d["informe"], "texto_a": que(props[i])[:110],
                                    "texto_b": d["texto"][:110]})
        for o, v in zip(otras, vo):
            c = _coseno(vp[i], v)
            if c >= umbral:
                contra.append({"a": props[i]["id"], "b": o["id"], "estado_b": o["estado"], "coseno": round(c, 3),
                               "texto_a": que(props[i])[:110], "texto_b": (o.get("titulo") or "")[:110]})
    entre.sort(key=lambda p: -p["coseno"])
    contra.sort(key=lambda p: -p["coseno"])
    contra_desc.sort(key=lambda p: -p["coseno"])
    res = {"modelo": modelo, "umbral": umbral, "propuestas": len(props), "tareas_comparadas": len(otras),
           "descartes_comparados": len(descartes_), "entre_propuestas": entre, "contra_tareas": contra,
           "contra_descartes": contra_desc}
    md = [f"# Parecidas por embeddings ({modelo}) - SIMULACION {ahora:%d/%m/%Y %H:%M}", "",
          f"Umbral coseno {umbral}. {len(props)} propuestas abiertas contra si mismas y contra {len(otras)} tareas. "
          "Nada se ha fundido ni archivado: son CANDIDATOS para el tribunal de F1.", "",
          f"## Entre propuestas ({len(entre)} pares)", ""]
    md += [f"- {p['coseno']:.3f} {p['a']} ~ {p['b']}\n  - {p['texto_a']}\n  - {p['texto_b']}" for p in entre]
    md += ["", f"## Propuesta ~ tarea existente ({len(contra)} pares)", ""]
    md += [f"- {p['coseno']:.3f} {p['a']} ~ {p['b']} ({p['estado_b']})\n  - {p['texto_a']}\n  - {p['texto_b']}"
           for p in contra]
    md += ["", f"## Propuesta ~ DESCARTADO ({len(contra_desc)} pares, {len(descartes_)} descartes por idea)", "",
           "Ya se descarto algo parecido: el motivo anterior va abajo. El tribunal o Damian deciden 'el descarte "
           "sigue valiendo' o 'revalorar'.", ""]
    md += [f"- {p['coseno']:.3f} {p['a']} ~ {p['b']} (DESCARTADO por {p['causa']}, {p['quien'] or '?'}, "
           f"{p['cuando'][:10]})\n  - {p['texto_a']}\n  - {p['texto_b']}\n  - Motivo anterior: {p['motivo'][:300]}"
           for p in contra_desc]
    INFORMES.mkdir(parents=True, exist_ok=True)
    base = INFORMES / f"parecidas_{ahora:%Y%m%d_%H%M}"
    base.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    base.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    res["informe"] = str(base.with_suffix(".md"))
    return res


# ------------------------------------------------------------------ 5) metricas para el Centro
def _semana(d: datetime) -> str:
    a, s, _ = d.isocalendar()
    return f"{a}-S{s:02d}"


def metricas(semanas: int = 6, ahora: datetime | None = None, tareas: list[dict] | None = None) -> dict:
    """Entradas (creadas) y salidas (cerradas o aprobadas) de propuestas y revisiones por semana ISO."""
    ahora = ahora or datetime.now()
    tareas = T.cargar()["tareas"] if tareas is None else tareas
    claves = []
    for i in range(semanas - 1, -1, -1):
        k = _semana(ahora - timedelta(weeks=i))
        if k not in claves:
            claves.append(k)
    filas = {k: {"semana": k, "prop_entran": 0, "prop_salen": 0, "prop_archivadas": 0,
                 "rev_entran": 0, "rev_salen": 0} for k in claves}
    for t in tareas:
        et = t.get("etiquetas") or []
        es_p, es_r = ET_PROPUESTA in et, ET_REVISION in et
        if not (es_p or es_r):
            continue
        c = _fecha(t.get("creada"))
        if c and _semana(c) in filas:
            filas[_semana(c)]["prop_entran" if es_p else "rev_entran"] += 1
        if es_p and t.get("estado") != "propuesta":
            # salida: cerrada (descartada/hecha) o aprobada (pasa a pendiente); para esta ultima, la nota de aprobacion
            s = _fecha(t.get("cerrada"))
            if s is None:
                s = next((_fecha(n.get("cuando")) for n in t.get("notas") or [] if "APROBADA" in (n.get("texto") or "")),
                         None)
            if s and _semana(s) in filas:
                filas[_semana(s)]["prop_salen"] += 1
                if ET_ARCHIVADA in et:
                    filas[_semana(s)]["prop_archivadas"] += 1
        if es_r and t.get("estado") in T.CERRADOS:
            s = _fecha(t.get("cerrada"))
            if s and _semana(s) in filas:
                filas[_semana(s)]["rev_salen"] += 1
    archivadas = sum(1 for t in tareas if ET_ARCHIVADA in (t.get("etiquetas") or []))
    return {"semanas": [filas[k] for k in claves], "cola": estado_cola(tareas), "archivadas": archivadas,
            "generadoras": list(GENERADORAS), "caducidad": DIAS_CADUCIDAD}


# ------------------------------------------------------------------ CLI
def _cli(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    orden, resto = argv[0], argv[1:]
    if orden == "estado":
        print(json.dumps(estado_cola(), ensure_ascii=False, indent=1))
        return 0
    if orden in ("simular", "aplicar"):
        fusion = {}
        if "--fundir" in resto:
            fusion = {"fundir_ids": tuple(resto[resto.index("--fundir") + 1].upper().split(",")),
                      "fundir_titulo": resto[resto.index("--titulo") + 1] if "--titulo" in resto else "",
                      "fundir_motivo": resto[resto.index("--motivo") + 1] if "--motivo" in resto else ""}
        r = ejecutar(orden == "aplicar", excedente="--excedente" in resto, **fusion)
        ev = r["evaluacion"]
        print(f"{orden}: {ev['total']} propuestas, {len(ev['archivar'])} a archivar, {len(ev['quedan'])} quedan"
              + (f", {len(r['archivadas'])} archivadas de verdad" if orden == "aplicar" else "")
              + f". Informe: {r['informe']}")
        return 0
    if orden == "parecidas":
        umbral = float(resto[resto.index("--umbral") + 1]) if "--umbral" in resto else UMBRAL_EMBEDDINGS
        modelo = resto[resto.index("--modelo") + 1] if "--modelo" in resto else MODELO_EMBEDDINGS
        r = pares_semanticos(umbral, modelo)
        print(f"parecidas ({modelo}, umbral {umbral}): {len(r['entre_propuestas'])} pares entre propuestas, "
              f"{len(r['contra_tareas'])} contra tareas. Informe: {r['informe']}")
        return 0
    if orden == "recuperar" and resto:
        for tid in resto:
            print(f"{recuperar(tid)['id']} recuperada")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
