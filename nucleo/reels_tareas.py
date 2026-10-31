# -*- coding: utf-8 -*-
"""T859 bloque 6, pasos 5 y 6: de las fichas de reels a propuestas POR TEMA (REELS.md, "Ficha completa por reel").

  deduplicar   cada elemento contra el catalogo (memoria/catalogo.json), las tareas vivas y cerradas y los
               DESCARTES (T688). Si ya existe, no se duplica: se anota la fuente nueva en lo existente.
  plan         sin escribir nada: lo que se crearia.
                 - investigacion POR TEMA (flujo T674): una por reel y tema con TODOS sus elementos dentro (los
                   20 repos de un reel = UNA comparativa frente a lo que NEXO ya usa); su RESULTADO por elemento
                   (ADOPTAR/ADAPTAR/DESCARTAR) crea despues las hijas "Integrar" en piezas tests:dados;
                 - tarea PERSONAL propuesta para Damian (cursos, ofertas, cosas que solo puede pedir el);
                 - conocimiento sin accion (trading, negocio, datos, consejos) a la base privada por categoria;
                 - anotaciones en lo que ya existia.
  crear        lo aplica: las propuestas entran por el circuito de revision/tribunal (un borrador con su seccion
               PROPUESTAS IMPLEMENTABLES registrado en T859) y respetan el freno (si la cola esta llena, lo que no
               cabe queda en memoria/perfil_privado/reels/plan_pendiente.json para otra tanda).

T966 (17/10): TOPE_TANDA propuestas por tanda (las de mas importancia, agrupadas por tema); el resto de la tanda va a
la base de conocimiento. Lo que pide saltarse permisos o dar autonomia total sale de las propuestas ("Fuera", con aviso
de seguridad); modelos sin censura y descargas de video se marcan para Damian; lo obsoleto se descarta. Los huecos
reales de Damian (reels_huecos.tarea_hueco) son tareas suyas aparte: no entran en el tope.

PRIVADO: a tareas.json (git) no va ni la URL ni el codigo de ningun reel ni la lista de la coleccion: solo el
conocimiento derivado (nombres de repos/herramientas) y "fuente: ficha privada de reel". El mapa elemento -> reel
vive en memoria/perfil_privado/reels/fuentes.json.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from nucleo import reels_calidad as C
from nucleo.config import RAIZ

CARPETA = RAIZ / "memoria" / "perfil_privado" / "reels"
CONOCIMIENTO = RAIZ / "memoria" / "perfil_privado" / "conocimiento"
TAREA_ORIGEN = "T859"
TECNICOS = {"repo", "herramienta", "web", "modelo", "tecnica", "idea_proyecto"}
TOPE_TANDA = 10
CATS_ACCION = {"nexo", "ia_prompts", "herramientas", "diseno", "contenido"}
IMPORTANCIA = {"nexo": 4, "ia_prompts": 4, "herramientas": 3, "diseno": 3, "contenido": 3, "carrera": 3}


def _plano(texto: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (texto or "").lower())


def _repo(e: dict) -> str | None:
    r = (e.get("resolucion") or {}).get("canonico")
    if r:
        return r
    if e.get("tipo") == "repo" and e.get("dueno"):
        return f"{e['dueno']}/{e['nombre']}"
    return None


def nombre_completo(e: dict) -> str:
    return _repo(e) or e.get("nombre") or e.get("url") or "?"


# ------------------------------------------------------------------ 5. deduplicado
def _palabras(texto: str) -> set[str]:
    from nucleo import descartes
    return descartes._nucleo(texto)


def _mismo_nombre(e: dict, texto: str, pal_texto: set[str]) -> bool:
    from nucleo import descartes
    r = _repo(e)
    if r and r.lower() in (texto or "").lower():
        return True
    n = _palabras(e.get("nombre") or "")
    if not descartes._distintivo(n):
        return False
    return n <= pal_texto


def indice(catalogo: list[dict], tareas: list[dict]) -> list[dict]:
    """Lo que ya existe en NEXO, con su texto y sus palabras."""
    out = []
    for h in catalogo:
        texto = f"{h.get('nombre', '')} {h.get('identidad', '')}"
        out.append({"donde": "catalogo", "id": h.get("id"), "estado": h.get("veredicto"), "texto": texto,
                    "pal": _palabras(h.get("nombre", "")) | _palabras(h.get("identidad", "").split(" ")[0])})
    for t in tareas:
        et = t.get("etiquetas") or []
        if "turno:lote" in et or "cat:revision" in et:
            continue
        texto = t.get("titulo") or ""
        out.append({"donde": "tarea", "id": t["id"], "estado": t.get("estado"), "texto": texto,
                    "pal": _palabras(texto)})
    return out


def deduplicar(e: dict, idx: list[dict], reg: list[dict]) -> dict | None:
    """El primero que ya cubre el elemento: descarte (T688) > catalogo > tarea. None si es nuevo."""
    from nucleo import descartes
    for d in descartes.buscar(nombre_completo(e), reg):
        if d.get("por") == "mismo nombre":
            return {"donde": "descarte", "id": d["id"], "estado": "descartada", "motivo": (d.get("motivo") or "")[:200]}
    for donde in ("catalogo", "tarea"):
        for x in idx:
            if x["donde"] == donde and _mismo_nombre(e, x["texto"], x["pal"]):
                return {"donde": donde, "id": x["id"], "estado": x["estado"]}
    return None


# ------------------------------------------------------------------ 6. plan por tema
def destino(e: dict) -> str:
    if (e.get("seguridad") or {}).get("nivel") == "damian":
        return "personal"                       # T966: modelos sin censura / descargas de video: lo decide Damian
    cats = set(e.get("categorias") or [])
    if "trading" in cats:
        return "conocimiento:trading"
    if e.get("tipo") == "curso_oferta" or "carrera" in cats:
        return "personal"
    if e.get("tipo") in TECNICOS and cats & CATS_ACCION:
        return "investigacion"
    if e.get("tipo") in TECNICOS and "sin_clasificar" in cats and e.get("tipo") == "repo":
        return "investigacion"
    cat = next((c for c in e.get("categorias") or [] if c != "sin_clasificar"), "sin_clasificar")
    return f"conocimiento:{cat}"


_PERSONAL = re.compile(r"(?i)\bstudent|estudiante|\.edu\b|descuento|discount|beca|scholarship|curso|course|"
                       r"certificaci|certification|pr[aá]cticas|internship|oferta de empleo")


def _tema_personal(f: dict) -> bool:
    """Reel cuyo tema es algo que solo puede pedir/hacer Damian (descuentos de estudiante, becas, cursos...)."""
    p = f.get("promesa") or {}
    return bool(_PERSONAL.search(" ".join(str(x or "") for x in (f.get("tema"), p.get("texto")))))


def _destino_en(e: dict, f: dict) -> str:
    """Como destino(), pero si el reel marca que es lo prometido, lo que NO es de la promesa (repos de fondo en una
    pagina 'trending', el anuncio del pie...) no genera tarea: va a la base como contexto (bloque 6, reel de rea)."""
    d = destino(e)
    marcados = any(x.get("en_promesa") for x in f.get("elementos", []))
    if d in ("investigacion", "personal") and marcados and not e.get("en_promesa"):
        cat = next((c for c in e.get("categorias") or [] if c != "sin_clasificar"), "sin_clasificar")
        return f"conocimiento:{cat}"
    return d


def _fila(e: dict, f: dict) -> dict:
    """Una fila de conocimiento (base privada) de un elemento de una ficha."""
    return {"nombre": nombre_completo(e), "tipo": e["tipo"], "que_es": e.get("que_es"), "para_que": e.get("para_que"),
            "url": (e.get("resolucion") or {}).get("url") or e.get("url"), "reel": f.get("codigo"),
            "tema": f.get("tema"), "ya": e.get("existente")}


def _linea(e: dict) -> str:
    r = e.get("resolucion") or {}
    extra = []
    if r.get("estrellas") is not None:
        extra.append(f"{r['estrellas']}★")
    if r.get("licencia"):
        extra.append(r["licencia"])
    if r.get("ultima_actividad"):
        extra.append(f"activo {r['ultima_actividad'][:10]}")
    if r.get("existe") is None:
        extra.append("SIN RESOLVER")
    if not e.get("verificado", True):
        extra.append("dudoso: no visto en el reel")
    txt = f"- {nombre_completo(e)}" + (f" ({', '.join(extra)})" if extra else "")
    if e.get("que_es"):
        txt += f": {e['que_es']}"
    if e.get("para_que"):
        txt += f" → {e['para_que']}"
    return txt


def _descartable(e: dict) -> bool:
    """Lo citado por escrito que luego no existe (falso dueno/repo) no va a ninguna tarea."""
    return e.get("origen") == "citas" and (e.get("resolucion") or {}).get("existe") is False


def plan(fichas: list[dict], catalogo: list[dict] | None = None, tareas: list[dict] | None = None,
         reg: list[dict] | None = None) -> dict:
    if catalogo is None:
        from nucleo import catalogo as C
        catalogo = C.cargar()["items"]
    if tareas is None:
        from nucleo import tareas as T
        tareas = T.cargar()["tareas"]
    if reg is None:
        from nucleo import descartes
        reg = descartes.registro(tareas)
    idx = indice(catalogo, tareas)
    salida = {"tareas": [], "conocimiento": {}, "anotaciones": [], "excluidos": [], "fuentes": {},
              "avisos_seguridad": [], "a_base_por_tope": 0}
    for f in fichas:
        grupos: dict[str, list[dict]] = {}
        for e in f.get("elementos", []):
            sg = e.get("seguridad") or {}
            if sg.get("nivel") in ("peligro", "obsoleto"):       # T966: nunca como investigacion
                etiqueta = "SEGURIDAD" if sg["nivel"] == "peligro" else "Obsoleto"
                salida["excluidos"].append({"reel": f.get("codigo"), "nombre": nombre_completo(e),
                                            "motivo": f"{etiqueta}: {sg.get('motivo')}", "seguridad": sg["nivel"]})
                if sg["nivel"] == "peligro":
                    salida["avisos_seguridad"].append(f"{nombre_completo(e)}: {sg.get('motivo')}")
                continue
            if _descartable(e):
                salida["excluidos"].append({"reel": f.get("codigo"), "nombre": nombre_completo(e),
                                            "motivo": "citado pero no existe en GitHub"})
                continue
            ex = deduplicar(e, idx, reg)
            e["existente"] = ex
            salida["fuentes"].setdefault(nombre_completo(e), []).append(f.get("codigo"))
            if ex and ex["donde"] in ("catalogo", "tarea"):
                salida["anotaciones"].append({"donde": ex["donde"], "id": ex["id"], "elemento": nombre_completo(e),
                                              "reel": f.get("codigo"), "tema": f.get("tema")})
            grupos.setdefault(_destino_en(e, f), []).append(e)
        # Bloque 6 (reel de descuentos .edu): si el reel es sobre todo accion de Damian, lo suyo va junto en su
        # tarea personal (salvo repos, que si se investigan), en vez de partirse en dos tareas por categoria.
        es_personal = _tema_personal(f) or len(grupos.get("personal", [])) >= len(grupos.get("investigacion", []))
        if es_personal and grupos.get("investigacion"):
            mover = [e for e in grupos["investigacion"] if e["tipo"] != "repo"]
            grupos["investigacion"] = [e for e in grupos["investigacion"] if e["tipo"] == "repo"]
            grupos.setdefault("personal", []).extend(mover)
            if not grupos["investigacion"]:
                del grupos["investigacion"]
        for dest, elems in grupos.items():
            if dest.startswith("conocimiento:"):
                cat = dest.split(":", 1)[1]
                salida["conocimiento"].setdefault(cat, []).extend(_fila(e, f) for e in elems)
                continue
            nuevos = [e for e in elems if not e.get("existente")]
            ya = [e for e in elems if e.get("existente") and e["existente"]["donde"] != "descarte"]
            descartados = [e for e in elems if (e.get("existente") or {}).get("donde") == "descarte"]
            if not nuevos:
                salida["excluidos"].append({"reel": f.get("codigo"), "nombre": f"{dest}: {f.get('tema')}",
                                            "motivo": "todo lo del tema ya existe o ya se descarto"})
                continue
            t = _tarea(dest, f, nuevos, ya, descartados)
            t["_filas"] = [(_cat_de(e), _fila(e, f)) for e in nuevos]
            salida["tareas"].append(t)
    _topar(salida)
    from nucleo import reels_huecos
    for f in fichas:                      # T966: los huecos reales de Damian, como tareas suyas (aparte del tope)
        h = reels_huecos.hueco(f)
        if h:
            salida["tareas"].append(reels_huecos.tarea_hueco(h))
    return salida


def _cat_de(e: dict) -> str:
    return next((c for c in e.get("categorias") or [] if c != "sin_clasificar"), "sin_clasificar")


def _topar(salida: dict) -> None:
    """T966: como mucho TOPE_TANDA propuestas por tanda, las de mas importancia y agrupadas por tema; el resto de la
    tanda no se pierde: sus elementos van a la base de conocimiento (conocimiento sin accion, por categoria)."""
    tareas = sorted(salida["tareas"], key=lambda t: (-t["importancia"], t.get("tema") or "", t["titulo"]))
    dentro, fuera = tareas[:TOPE_TANDA], tareas[TOPE_TANDA:]
    for t in fuera:
        for cat, fila in t.get("_filas") or []:
            salida["conocimiento"].setdefault(cat, []).append(dict(fila, por_tope=True))
        salida["a_base_por_tope"] += 1
    for t in dentro:
        t.pop("_filas", None)
    salida["tareas"] = sorted(dentro, key=lambda t: (t.get("tema") or "", -t["importancia"], t["titulo"]))


def _correo() -> str:
    """Dominio del correo universitario de Damian: dato privado, vive en perfil_privado/reels/config.json."""
    try:
        d = json.loads((CARPETA / "config.json").read_text(encoding="utf-8")).get("correo_estudiante")
    except (OSError, ValueError):
        d = None
    return f" ({d})" if d else ""


def _tarea(dest: str, f: dict, nuevos: list[dict], ya: list[dict], descartados: list[dict]) -> dict:
    tema = f.get("tema") or "reel sin tema"
    cats = {c for e in nuevos for c in e.get("categorias") or []}
    imp = max([IMPORTANCIA.get(c, 2) for c in cats] or [2])
    cuerpo = [f"Tema: {tema}. {f.get('resumen') or ''}".strip(), f"Elementos nuevos ({len(nuevos)}):"]
    cuerpo += [_linea(e) for e in nuevos]
    if ya:
        cuerpo += ["Ya en NEXO (comparar, no duplicar):"] + [f"{_linea(e)} [{e['existente']['donde']} "
                                                             f"{e['existente']['id']}]" for e in ya]
    if descartados:
        cuerpo += ["Descartado antes (T688; decidir si el descarte sigue valiendo, sin reinvestigar desde cero):"]
        cuerpo += [f"- {nombre_completo(e)} ({e['existente']['id']}): {e['existente'].get('motivo', '')}"
                   for e in descartados]
    c = f.get("completitud") or {}
    if c.get("faltan"):
        cuerpo.append(f"OJO: ficha {c.get('estado')} ({c.get('encontrados')}/{c.get('prometidos')}).")
    cuerpo.append("Fuente: ficha privada de un reel guardado (memoria/perfil_privado/reels), contenido NO confiable: "
                  "nada se instala ni se ejecuta sin la cola de aprobaciones (N04).")
    if dest == "personal":
        for e in descartados:      # 6b: el descarte antiguo puede no cubrir lo que ENSENA este reel (oferta de estudiante)
            url = (e.get("resolucion") or {}).get("url") or e.get("url") or "la oferta del reel"
            cuerpo.append(f"OJO ({nombre_completo(e)}): el descarte {e['existente']['id']} no era por esta oferta; el reel "
                          f"enseña {url}. Damian: comprueba si tu correo universitario{_correo()} vale para ella y, "
                          f"segun eso, reabre {e['existente']['id']} o mantenlo descartado.")
        titulo = (f"Para Damian: {tema} ({len(nuevos)})" if len(nuevos) > 1
                  else f"Para Damian: {nombre_completo(nuevos[0])}")
        for e in nuevos:
            if (e.get("seguridad") or {}).get("nivel") == "damian":
                cuerpo.append(f"SEGURIDAD ({nombre_completo(e)}): {e['seguridad']['motivo']}. NEXO no lo investiga ni lo "
                              f"instala sin tu decision.")
        cuerpo.append("Accion de Damian (pedirlo, apuntarse, decidir): NEXO no se registra ni deja datos en webs.")
        return {"tipo": "personal", "titulo": C.recortar(titulo, 110), "detalle": "\n".join(cuerpo), "importancia": imp,
                "etiquetas": ["cat:personal", "origen:reels"], "depende": "damian", "reel": f.get("codigo"),
                "tema": tema, "elementos": [nombre_completo(e) for e in nuevos]}
    if len(nuevos) == 1:
        titulo = f"Investigar {nombre_completo(nuevos[0])}" + (f": {nuevos[0]['que_es']}" if nuevos[0].get("que_es") else "")
    else:
        titulo = f"Investigar (comparativa): {tema} — {len(nuevos)} elementos"
    cuerpo.append("Flujo T674: RESULTADO por elemento (ADOPTAR / ADAPTAR / DESCARTAR + motivo); cada ADOPTAR/ADAPTAR "
                  "crea su hija 'Integrar: ...' en piezas tests:dados (adaptacion + implementacion), que se verifica.")
    return {"tipo": "investigacion", "titulo": C.recortar(titulo, 110), "detalle": "\n".join(cuerpo), "importancia": imp,
            "etiquetas": ["cat:investigacion", "origen:reels"], "depende": "ia", "reel": f.get("codigo"),
            "tema": tema, "elementos": [nombre_completo(e) for e in nuevos]}


def plan_md(p: dict) -> str:
    lineas = [f"## Tareas que se crearían ({len(p['tareas'])}) — como propuestas por el tribunal"
              f" (tope {TOPE_TANDA} por tanda; {p.get('a_base_por_tope', 0)} más a la base de conocimiento)"]
    tema_previo = None
    for i, t in enumerate(p["tareas"], 1):
        if t.get("tema") != tema_previo:
            tema_previo = t.get("tema")
            lineas += [f"#### Tema: {tema_previo or '(sin tema)'}", ""]
        lineas += [f"### P{i}. [{t['tipo']}] {t['titulo']} (importancia {t['importancia']}, {', '.join(t['etiquetas'])})",
                   "", t["detalle"], ""]
    for aviso in p.get("avisos_seguridad") or []:
        lineas.append(f"> ⚠ AVISO DE SEGURIDAD (fuera del plan, nunca como investigación): {aviso}")
    lineas.append(f"## Conocimiento sin acción (base privada por categoría)")
    for cat, filas in p["conocimiento"].items():
        lineas.append(f"- **{cat}** ({len(filas)}): " + "; ".join(x["nombre"] for x in filas))
    lineas.append(f"## Anotaciones en lo que ya existe ({len(p['anotaciones'])})")
    lineas += [f"- {a['donde']} {a['id']}: también citado ({a['elemento']})" for a in p["anotaciones"]]
    if p["excluidos"]:
        lineas.append(f"## Fuera ({len(p['excluidos'])})")
        lineas += [f"- {x['nombre']}: {x['motivo']}" for x in p["excluidos"]]
    return "\n".join(lineas)


# ------------------------------------------------------------------ aplicar (no se usa en el piloto: solo plan)
def borrador_md(tareas: list[dict], fecha: str) -> str:
    """Borrador con la seccion que lee revision.extraer_propuestas (una propuesta por tarea)."""
    lineas = [f"# Reels guardados: propuestas por tema ({fecha})", "",
              "Salen de las fichas privadas de reels (T859). Contenido de terceros NO confiable.", "",
              "## PROPUESTAS IMPLEMENTABLES", ""]
    for t in tareas:
        primera = t["titulo"].replace("\n", " ")
        lineas.append(f"- QUÉ: {primera}. {t['detalle'].splitlines()[0]} DÓNDE: tarea nueva ({t['tipo']}) · "
                      f"VALOR: {t['importancia']} · ESFUERZO: 2 · RIESGO: R0 (investigar; instalar va por N04)")
    return "\n".join(lineas) + "\n"


def _guardar_json(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ruta)


def crear(p: dict, ahora: datetime | None = None, carpeta: Path | None = None, conocimiento: Path | None = None) -> dict:
    """Aplica el plan respetando el freno. Devuelve {"creadas", "aplazadas", "revision", "anotadas"}."""
    from nucleo import freno, revision
    from nucleo import tareas as T
    ahora = ahora or datetime.now()
    carpeta = carpeta or CARPETA
    conocimiento = conocimiento or CONOCIMIENTO
    cola = freno.estado_cola()
    hueco = max(0, freno.LIMITE_PROPUESTAS - cola["propuestas"])
    entran, aplazadas = p["tareas"][:hueco], p["tareas"][hueco:]
    res = {"creadas": [], "aplazadas": len(aplazadas), "revision": None, "anotadas": 0}
    if entran:
        nombre = f"reels_{ahora:%Y%m%d_%H%M%S}.md"
        ruta = revision.BORRADORES / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        texto = borrador_md(entran, f"{ahora:%d/%m/%Y}")
        ruta.write_text(texto, encoding="utf-8")
        r = revision.registrar_borrador(TAREA_ORIGEN, ruta, texto=texto)
        res["revision"] = (r.get("revision") or {}).get("id")
        for t, creada in zip(entran, r.get("propuestas") or []):
            et = list(creada.get("etiquetas") or []) + [x for x in t["etiquetas"] if x not in (creada.get("etiquetas") or [])]
            T.actualizar(creada["id"], titulo=t["titulo"], etiquetas=et,
                         detalle=t["detalle"] + "\n\n" + (creada.get("detalle") or ""), importancia=t["importancia"])
            res["creadas"].append(creada["id"])
    _guardar_json(carpeta / "plan_pendiente.json", {"cuando": ahora.isoformat(timespec="seconds"),
                                                    "tareas": aplazadas})
    vistos = set()
    for a in p["anotaciones"]:
        k = (a["donde"], a["id"])
        if k in vistos:
            continue
        vistos.add(k)
        if a["donde"] == "tarea":
            T.anotar(a["id"], f"T859: tambien citado en un reel guardado ({a['elemento']}; ficha privada).")
            res["anotadas"] += 1
    fuentes = carpeta / "fuentes.json"
    previo = json.loads(fuentes.read_text(encoding="utf-8")) if fuentes.exists() else {}
    for nombre, reels in p["fuentes"].items():
        previo[nombre] = sorted(set(previo.get(nombre, [])) | set(reels))
    _guardar_json(fuentes, previo)
    for cat, filas in p["conocimiento"].items():
        ruta = conocimiento / f"{cat}.json"
        base = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else []
        claves = {_plano(x["nombre"]) for x in base}
        base += [x for x in filas if _plano(x["nombre"]) not in claves]
        _guardar_json(ruta, base)
    return res


def cargar_fichas(codigos: list[str] | None = None, carpeta: Path | None = None) -> list[dict]:
    carpeta = carpeta or CARPETA
    rutas = [carpeta / f"{c}.ficha.json" for c in codigos] if codigos else sorted(carpeta.glob("*.ficha.json"))
    out = []
    for r in rutas:
        d = json.loads(r.read_text(encoding="utf-8"))
        d.pop("anteriores", None)
        out.append(d)
    return out


def _cli(argv: list[str]) -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["plan"]:
        print(plan_md(plan(cargar_fichas(argv[1:] or None))))
        return 0
    print(__doc__)
    print("Uso: .venv\\Scripts\\python.exe -m nucleo.reels_tareas plan [CODIGO...]   (solo enseña; no crea nada)")
    return 0 if argv[:1] in ([], ["-h"], ["--help"]) else 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    import sys
    sys.exit(_cli(sys.argv[1:]))
