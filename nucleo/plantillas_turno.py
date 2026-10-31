# -*- coding: utf-8 -*-
"""Que hace un turno segun su plantilla (T231). Lo usa turno_nexo.py; la configuracion vive en nucleo/turnos.py.

Todas las plantillas acaban en nucleo.trabajo.ciclo(): OK absoluto + auditor + circuito de revision T192.
Ninguna escribe codigo: lo unico que escriben es tareas.json (tareas de turno y 'propuesta'), borradores y
auditorias en memoria/. Las de revisar y el vigia tienen ademas una guardia (foto de hashes antes/despues).

  cola            tareas delegables de la cola por prioridad (o las tareas concretas elegidas).
  investigacion   solo cat:investigacion.
  correcciones    tareas de codigo que son errores: el turno DIAGNOSTICA y PROPONE la correccion (no la
                  aplica); los archivos que cita la tarea van enteros como material.
  revisar_codigo  el turno crea una tarea-lote con PIEZAS de codigo (archivo + lineas) y la delega. Un
                  cursor en memoria/turnos_estado.json hace que turnos seguidos recorran todo el proyecto.
  revisar_archivos  igual, con documentacion, memoria y configuracion (sin datos privados).
  vigia           T272: novedades de fuentes fijas (nucleo/vigia.py), deduplicadas, en una tarea-lote.
Los hallazgos salen como PROPUESTAS IMPLEMENTABLES -> tareas 'propuesta' que Claude revisa (T192).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from nucleo import tareas as T
from nucleo import turnos

RAIZ = Path(__file__).resolve().parent.parent
ESTADO = RAIZ / "memoria" / "turnos_estado.json"

PRE_PLANTILLA = "plantilla:"
ET_LOTE = "turno:lote"
# 28/09: con 24.000/30.000 los lotes fallaban con TODOS los proveedores (ChatGPT web no llegaba a enviar el
# texto, Groq 413 "Payload Too Large", Gemini se negaba). Damian: lotes de 8.000-10.000 caracteres.
PIEZA_MAX = 8500             # caracteres (con numeros de linea) de una pieza de archivo
LOTE_MAX = 9500              # caracteres de material por lote
PROPIAS = ("revisar_codigo", "revisar_archivos", "vigia")   # el turno crea su propia tarea
SOBRE_COLA = ("cola", "investigacion", "correcciones")

# Nunca salen hacia otra IA ni se miran: entornos, archivo, datos privados y salidas de ejecucion.
_FUERA_DIRS = {".venv", "venv", "_archivo", ".claude", ".git", "registros", "__pycache__", "graft", "chrome-perfil",
               "piper", "salidas", "_respaldos", "_descargas", "node_modules", "vendor", "tests", "borradores",
               "catalogo_borradores", "chats_tareas", "_revision_logos", "auditoria", "avisos", "vigia", "handoffs-turno"}
_FUERA_ARCHIVOS = {"secretos.toml", ".env", "becas.md", "tareas.md", "historial_telegram.json"}
EXT_CODIGO = (".py", ".js", ".ps1", ".bat")
EXT_ARCHIVOS = (".md", ".toml", ".ini", ".txt")

# Un titulo de ERROR de verdad (no "a prueba de fallos" ni "tabla de tipos de error"): 28/09, primera
# simulacion real, cogia T186 y T157, que son mejoras. Tambien vale la etiqueta tipo:bug / bug.
_ERROR = re.compile(r"(?i)\b(?:bug|arregl\w*|corregir|corrige|correcci[oó]n de|no funciona|no arranca|"
                    r"se cuelga|roto|rota|traceback|excepci[oó]n|regresi[oó]n|fallan?|"
                    r"(?:error|fallo)(?:es|s)? (?:en|al|del|con|que))\b")
_RUTA = re.compile(r"\b((?:[\w.-]+/)*[\w.-]+\.(?:py|js|ps1|bat|md|toml))\b")


# ------------------------------------------------------------------ utilidades
def _et(t: dict, prefijo: str) -> str:
    return next((e[len(prefijo):] for e in t.get("etiquetas") or [] if e.startswith(prefijo)), "")


def plantilla_de(t: dict) -> str:
    """Plantilla de una tarea creada por un turno ('' si es una tarea normal de la cola)."""
    pid = _et(t, PRE_PLANTILLA)
    return pid if pid in turnos.PLANTILLAS else ""


def _estado() -> dict:
    try:
        d = json.loads(ESTADO.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar_estado(d: dict) -> None:
    from nucleo.escritura import escribir_atomico
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(ESTADO, json.dumps(d, ensure_ascii=False, indent=1))


def _tapar(texto: str) -> str:
    """Quita lo que el auditor considera privado (rutas del PC, correos, nombre del fichero de secretos, claves)."""
    from nucleo import auditor
    return auditor.tapar(texto, "[omitido]")   # antes no tapaba la ruta entera: dejaba "[omitido]usuario\..."


# ------------------------------------------------------------------ archivos y piezas
def _recorrer(raiz: Path, fuera: set[str]) -> list[Path]:
    """Archivos del proyecto. Con git: solo los versionados (git ls-files; rapido y sin worktrees ni restos de
    otras herramientas). Sin git (tests en tmp_path): os.walk sin carpetas ocultas ni las de `fuera`."""
    import os
    if (raiz / ".git").exists():
        try:
            r = subprocess.run(["git", "-C", str(raiz), "ls-files", "-z"], capture_output=True, timeout=30,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode == 0:
                rutas = [raiz / x for x in r.stdout.decode("utf-8", "replace").split("\0") if x]
                return [p for p in rutas if not any(d in fuera or d.startswith(".")
                                                    for d in p.relative_to(raiz).parts[:-1]) and p.is_file()]
        except (OSError, subprocess.SubprocessError):
            pass
    salida = []
    for base, dirs, nombres in os.walk(raiz):
        dirs[:] = sorted(d for d in dirs if d not in fuera and not d.startswith("."))
        salida += [Path(base) / n for n in nombres]
    return salida


# T675 (Damian 27/09: "Telegram: NADA nuevo"): los turnos de revision no recorren el bot. El 03/10 el filtro F0
# archivo 32 propuestas por "contradice una decision de Damian"; casi todas salian de revisar canal/bot.py.
# Para volver a revisarlo basta con vaciar estas dos constantes.
SIN_TELEGRAM_DIRS = ("canal",)
SIN_TELEGRAM_ARCHIVOS = ("docs/TELEGRAM.md",)


def _permitido(rel: Path) -> bool:
    partes = rel.parts
    if partes[0] in SIN_TELEGRAM_DIRS or rel.as_posix() in SIN_TELEGRAM_ARCHIVOS:
        return False
    if any(p in _FUERA_DIRS or p.startswith(".") for p in partes[:-1]) or rel.name in _FUERA_ARCHIVOS:
        return False
    if partes[0] == "herramientas_nube" and rel.name.startswith("_"):
        return False   # scripts sueltos de una sesion
    if partes[0] == "memoria" and (len(partes) > 2 or rel.suffix != ".md"):
        return False   # de memoria/ solo los .md de primer nivel (sin tareas.md ni becas.md)
    return True


def archivos(tipo: str, raiz: Path | None = None) -> list[str]:
    """Rutas relativas (con '/') que revisa cada plantilla, ordenadas."""
    raiz = raiz or RAIZ
    ext = EXT_CODIGO if tipo == "revisar_codigo" else EXT_ARCHIVOS
    salida = []
    for p in _recorrer(raiz, _FUERA_DIRS):
        if p.suffix.lower() not in ext:
            continue
        rel = p.relative_to(raiz)
        if _permitido(rel):
            salida.append(rel.as_posix())
    return sorted(salida)


def _numeradas(lineas: list[str], desde: int) -> str:
    return "\n".join(f"{desde + i}| {l}" for i, l in enumerate(lineas))


def _trocear(rel: str, lineas: list[str], desde: int = 1, hasta: int | None = None) -> list[tuple[str, int, int, int]]:
    """Parte las lineas [desde, hasta] en trozos cuyo texto numerado (lo que se envia) no pasa de PIEZA_MAX."""
    hasta = min(hasta or len(lineas), len(lineas))
    salida, ini, tam = [], desde, 0
    for i in range(desde, hasta + 1):
        coste = len(str(i)) + 3 + len(lineas[i - 1])      # "N| linea\n"
        if tam + coste > PIEZA_MAX and i > ini:
            salida.append((rel, ini, i - 1, tam))
            ini, tam = i, 0
        tam += coste
    if hasta >= ini:
        salida.append((rel, ini, hasta, tam))
    return salida


def _piezas_tam(tipo: str, raiz: Path | None = None) -> list[tuple[str, int, int, int]]:
    raiz = raiz or RAIZ
    salida = []
    for rel in archivos(tipo, raiz):
        try:
            lineas = (raiz / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        if lineas:
            salida += _trocear(rel, lineas)
    return salida


def piezas(tipo: str, raiz: Path | None = None) -> list[tuple[str, int, int]]:
    """(ruta, linea_desde, linea_hasta) de todo lo revisable, en trozos de <= PIEZA_MAX caracteres."""
    return [p[:3] for p in _piezas_tam(tipo, raiz)]


def _clave(p) -> tuple[str, int]:
    """Orden del cursor: (ruta, linea). 28/09: comparado como texto, 'a.py:95' iba despues de 'a.py:180'."""
    return (p[0], int(p[1]))


def _cursor(valor: str) -> tuple[str, int]:
    ruta, _, linea = (valor or "").rpartition(":")
    return (ruta, int(linea)) if linea.isdigit() else ("", 0)


def siguiente_lote(tipo: str, raiz: Path | None = None, avanzar: bool = True) -> list[tuple[str, int, int]]:
    """Las piezas del siguiente lote (<= LOTE_MAX caracteres REALES) a partir del cursor; al acabar el proyecto
    vuelve a empezar."""
    todas = _piezas_tam(tipo, raiz)
    if not todas:
        return []
    est = _estado()
    cursor = _cursor((est.get("cursor") or {}).get(tipo, ""))
    orden = [p for p in todas if _clave(p) > cursor] or todas
    lote, tam = [], 0
    for p in orden:
        if lote and tam + p[3] > LOTE_MAX:
            break
        lote.append(p[:3])
        tam += p[3]
    if avanzar:
        vueltas = est.setdefault("vueltas", {})
        if orden is todas and cursor:
            vueltas[tipo] = vueltas.get(tipo, 0) + 1
        est.setdefault("cursor", {})[tipo] = f"{lote[-1][0]}:{lote[-1][1]}"
        _guardar_estado(est)
    return lote


def texto_piezas(lote: list[tuple[str, int, int]], raiz: Path | None = None, tope: int = LOTE_MAX) -> str:
    raiz = raiz or RAIZ
    partes, total = [], 0
    for ruta, a, b in lote:
        try:
            lineas = (raiz / ruta).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            partes.append(f"===== {ruta} (ya no existe) =====")
            continue
        b = min(b, len(lineas))
        bloque = f"===== {ruta} (lineas {a}-{b} de {len(lineas)}) =====\n" + _tapar(_numeradas(lineas[a - 1:b], a))
        if total + len(bloque) > tope:
            bloque = bloque[:max(0, tope - total)]
        partes.append(bloque)
        total += len(bloque)
        if total >= tope:
            break
    return "\n\n".join(partes)


def _lote_de_detalle(detalle: str) -> list[tuple[str, int, int]]:
    m = re.search(r"PIEZAS:\s*(.+)", detalle or "")
    if not m:
        return []
    salida = []
    for trozo in m.group(1).split(";"):
        mm = re.match(r"\s*(.+?):(\d+)-(\d+)\s*$", trozo)
        if mm:
            salida.append((mm.group(1), int(mm.group(2)), int(mm.group(3))))
    return salida


# ------------------------------------------------------------------ instruccion y material (los usa trabajo.py)
FORMATO_REVISION = (
    "Entrega en espanol (maximo {palabras} palabras) con estas secciones EN ESTE ORDEN:\n"
    "1) Que has revisado (archivos y alcance).\n"
    "2) Hallazgos: cada uno con archivo y linea (o seccion), que pasa y por que es un problema. Si no hay "
    "hallazgos reales, dilo; no rellenes.\n"
    "3) Dudas abiertas.\n"
    "Si el material es un TRAMO de un archivo mas largo (la cabecera dice 'lineas X-Y de N'), revisa solo ese tramo: "
    "lo que dependa de otras partes va en Dudas abiertas. No respondas BLOQUEO por falta del resto del archivo "
    "(28/09: un lote se quedo parado pidiendo las lineas anteriores).\n")
FORMATO_VIGIA = (
    "Entrega en espanol (maximo {palabras} palabras) con estas secciones EN ESTE ORDEN:\n"
    "1) Novedades elegidas (como mucho 5): nombre, fuente (URL tal cual aparece en la lista), fecha y por que "
    "interesa.\n"
    "2) Descartadas: una linea con el motivo general.\n"
    "3) Dudas abiertas.\n"
    "En cada PROPUESTA escribe en QUE: 'investigar <nombre> (<URL de la lista>, <fecha>): <por que interesa>'.\n"
    "VALOR con esta escala, sin inflar (28/09: salian todas con 5):\n"
    "  5 = resuelve un problema ABIERTO de la lista NECESIDADES DE NEXO; cita su id (T###) en QUE. Como mucho una.\n"
    "  4 = mejora claramente una necesidad abierta; cita su id (T###).\n"
    "  3 = interesante para NEXO pero sin necesidad abierta concreta.\n"
    "  1-2 = curiosidad o encaje dudoso.\n"
    "Sin un id T### de la lista, el VALOR se deja como mucho en 3 aunque pongas mas.\n")
FORMATO_CORRECCION = (
    "Entrega en espanol (maximo {palabras} palabras) con estas secciones EN ESTE ORDEN:\n"
    "1) Diagnostico: causa probable, archivo y linea (si el material lo permite) y como lo sabes.\n"
    "2) Correccion propuesta: que cambiar y donde, concreto (puedes escribir el parche como texto; NO se aplica).\n"
    "3) Como comprobarla (test o prueba) y riesgos.\n")
FORMATO_ANALISIS = (
    "Entrega en espanol (maximo {palabras} palabras) con estas secciones EN ESTE ORDEN:\n"
    "1) Que se pide y en que estado esta.\n"
    "2) Plan concreto para hacerlo (pasos, archivos, pruebas).\n"
    "3) Riesgos y dudas abiertas.\n")
FORMATOS = {"revision": FORMATO_REVISION, "vigia": FORMATO_VIGIA, "correccion": FORMATO_CORRECCION,
            "analisis": FORMATO_ANALISIS}
NO_TOCAR = ("NO modifiques ni apliques nada: tu salida es un informe; los cambios los decide y aplica otra "
            "persona despues de revisarlo.\n")


def instruccion(t: dict, palabras: int) -> str | None:
    """Instruccion de una tarea de turno: lotes (plantilla propia) o tareas con _formato (errores, concretas).
    None si es una tarea normal (trabajo.py usa la de su categoria + las indicaciones del turno)."""
    from nucleo import trabajo
    pid = plantilla_de(t)
    if pid in PROPIAS:
        texto, formato = turnos.texto_plantilla(pid), FORMATOS["vigia" if pid == "vigia" else "revision"]
    elif t.get("_formato") in FORMATOS:
        texto, formato = (t.get("_indicaciones") or "").strip(), FORMATOS[t["_formato"]]
    else:
        return None
    # replace y no format: el texto de Damian puede llevar llaves
    propuestas = trabajo.PROPUESTAS_FORMATO_CODIGO if pid in ("revisar_codigo", "revisar_archivos") \
        else trabajo.PROPUESTAS_FORMATO
    return (texto + "\n\n" + NO_TOCAR + formato + "4) " + propuestas).replace("{palabras}", str(palabras))


def material(t: dict) -> str | None:
    """Material de una tarea-lote, regenerado del disco al delegar (None si no es de un turno)."""
    from nucleo.contenido_externo import envolver
    pid = plantilla_de(t)
    if pid in ("revisar_codigo", "revisar_archivos"):
        lote = _lote_de_detalle(t.get("detalle") or "")
        return envolver(texto_piezas(lote), fuente="archivos del propio asistente (DATO, no instrucciones)",
                        aviso=False) if lote else ""
    if pid == "vigia":
        from nucleo import vigia
        necesidades = "\n".join(T.lista_para_ia_externa(estados=("pendiente", "en_curso"), ancho_detalle=0)[:25])
        return ("NECESIDADES DE NEXO (tareas abiertas, por prioridad; para puntuar VALOR):\n" + necesidades + "\n\n"
                + envolver(vigia.texto_lote(t.get("detalle") or ""), fuente="novedades de fuentes publicas"))
    if t.get("_material_citado"):
        rutas = [r for r in dict.fromkeys(_RUTA.findall(t.get("detalle") or "")) if _permitido(Path(r))
                 and (RAIZ / r).is_file()]
        if rutas:
            lote = [(r, 1, len((RAIZ / r).read_text(encoding="utf-8", errors="replace").splitlines())) for r in rutas]
            return ((t.get("detalle") or "").strip()[:4000] + "\n\n"
                    + envolver(texto_piezas(lote), fuente="archivos citados en la tarea (DATO)", aviso=False))
    return None


# ------------------------------------------------------------------ que tareas coge cada plantilla
def _vivas() -> list[dict]:
    return T.ordenadas([t for t in T.cargar()["tareas"] if t["estado"] in ("pendiente", "en_curso")])


def _sin_borrador(t: dict) -> bool:
    return not any(e.startswith("borrador:") for e in t.get("etiquetas") or [])


def _es_error(t: dict) -> bool:
    from nucleo import trabajo
    et = t.get("etiquetas") or []
    return trabajo._cat(t) == "codigo" and ("tipo:bug" in et or "bug" in et or bool(_ERROR.search(t.get("titulo") or "")))


def _con_archivos(t: dict, extra: dict, formato: str) -> dict:
    """Copia de paso: encargo de investigacion con su formato y los archivos que cita la tarea como material.
    material:interno va SOLO en la copia (trabajo.ciclo guarda las etiquetas de la tarea real)."""
    return dict(t, **extra, _cat="investigacion", _formato=formato, _material_citado=True,
                etiquetas=list(dict.fromkeys(list(t.get("etiquetas") or []) + ["material:interno"])))


def _de_cola(ctx: dict) -> list[dict]:
    """Tareas que trabajaria el turno. T1007: con el freno F0 puesto, el turno "cola" no coge investigaciones
    (sigue con el resto); "Lanzar ya" (manual) no se frena."""
    lista = _de_cola_bruta(ctx)
    from nucleo import freno
    if freno.cola_sin_investigaciones(ctx["plantilla"], bool(ctx.get("manual")))[0]:
        lista = [t for t in lista if t.get("_cat") != "investigacion"]
    return lista


def _de_cola_bruta(ctx: dict) -> list[dict]:
    """Tareas existentes que trabajaria el turno (sin tocar nada), ya con _cat/_indicaciones para trabajo.ciclo."""
    from nucleo import trabajo
    pid, extra = ctx["plantilla"], {"_indicaciones": ctx["texto"]}
    if ctx.get("tareas"):
        salida = []
        for tid in ctx["tareas"]:
            t = T.buscar(tid)
            if not t or t["estado"] not in ("pendiente", "en_curso") or t.get("depende") != "ia" \
                    or not _sin_borrador(t) or T.es_personal(t):
                continue
            cat = trabajo._cat(t)
            if cat in trabajo.DELEGABLES and pid != "correcciones":
                salida.append(dict(t, **extra, _cat=cat))
            else:   # no delegable tal cual (o turno de errores): diagnostico/plan + propuestas, nunca codigo
                salida.append(_con_archivos(t, extra, "correccion" if pid == "correcciones" or _es_error(t)
                                            else "analisis"))
        return salida
    if pid == "correcciones":
        return [_con_archivos(t, extra, "correccion") for t in _vivas()
                if t.get("depende") == "ia" and _sin_borrador(t) and _es_error(t) and not plantilla_de(t)
                and not T.es_personal(t)]
    base = [t for t in trabajo.candidatas() if not plantilla_de(t)]
    if pid == "investigacion":
        base = [t for t in base if trabajo._cat(t) == "investigacion"]
    return [dict(t, **extra, _cat=trabajo._cat(t)) for t in base]


def _tam_lote(lote: list[tuple[str, int, int]]) -> int:
    return len(texto_piezas(lote, tope=10 ** 9))


def _rehacer_si_grande(t: dict) -> list[dict]:
    """Un lote pendiente hecho con el tamano viejo se descarta y sus PIEZAS se rehacen en lotes pequenos."""
    pid = plantilla_de(t)
    lote = _lote_de_detalle(t.get("detalle") or "")
    if pid not in ("revisar_codigo", "revisar_archivos") or not lote or _tam_lote(lote) <= LOTE_MAX:
        return [t]
    trozos = []
    for ruta, a, b in lote:
        try:
            lineas = (RAIZ / ruta).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        trozos += _trocear(ruta, lineas, a, b)
    nuevos, actual, tam = [], [], 0
    for x in trozos:
        if actual and tam + x[3] > LOTE_MAX:
            nuevos.append(actual)
            actual, tam = [], 0
        actual.append(x[:3])
        tam += x[3]
    if actual:
        nuevos.append(actual)
    creadas = [_crear_lote(pid, n, i) for i, n in enumerate(nuevos, 1)]
    T.actualizar(t["id"], estado="descartada")
    T.anotar(t["id"], f"Lote demasiado grande para los proveedores ({_tam_lote(lote)} car.): rehecho en "
                      f"{', '.join(c['id'] for c in creadas)} (lotes de <= {LOTE_MAX}).")
    return creadas


def _lotes_pendientes(pid: str) -> list[dict]:
    """Lotes de un turno anterior que no llegaron a tener borrador (fallo de proveedor): se reintentan antes."""
    return [t for t in _vivas() if plantilla_de(t) == pid and _sin_borrador(t)]


def candidatas(ctx: dict) -> int:
    """Cuanto trabajo hay (puerta T156), sin crear nada ni cargar modelos."""
    pid = ctx["plantilla"]
    if pid in SOBRE_COLA:
        return len(_de_cola(ctx))
    if pid == "tribunal":
        from nucleo import tribunal
        return tribunal.candidatas()
    if pid == "implementador":
        from nucleo import piloto_serie
        return piloto_serie.candidatas()
    if pid == "radar":
        from nucleo import radar
        return radar.candidatas(ctx.get("texto") or "")
    if pid == "kuzushi":
        from nucleo import kuzushi
        return kuzushi.candidatas()
    if pid == "modelos":
        from nucleo import banco_modelos
        return banco_modelos.candidatas_diario()
    if pid == "reels":
        from extremidades import reels
        return (len(reels.cola_lote(estado=reels._leer_estado_lote(reels.LOTE)))
                + (len(reels.cola_rehacer()) if reels.config_lote().get("rehacer_todas", True) else 0))
    if pid == "vigia":
        from nucleo import vigia
        return len(_lotes_pendientes(pid)) + (0 if vigia.hecho_hoy() else 1)
    return len(_lotes_pendientes(pid)) + (1 if piezas(pid) else 0)


def _crear_lote(pid: str, lote: list[tuple[str, int, int]], n: int) -> dict:
    etiqueta = {"revisar_codigo": "Revision de codigo", "revisar_archivos": "Revision de archivos"}[pid]
    rutas = sorted({p[0] for p in lote})
    return T.anadir(
        f"{etiqueta} (turno {datetime.now():%d/%m}, lote {n}): {', '.join(rutas)[:120]}",
        detalle=(f"Tarea creada por un turno de NEXO (plantilla {pid}, solo lectura). El material se lee del "
                 f"disco al delegar.\nPIEZAS: " + "; ".join(f"{r}:{a}-{b}" for r, a, b in lote)),
        importancia=3, urgencia=2, dificultad=2, coste=1, depende="ia",
        etiquetas=["cat:investigacion", "material:interno", "extension:larga", f"{PRE_PLANTILLA}{pid}", ET_LOTE])


def preparar(ctx: dict, simular: bool = False) -> list[dict]:
    """Lista de tareas para trabajo.ciclo(lista=...). En las plantillas propias crea (o reutiliza) los lotes."""
    pid, maximo = ctx["plantilla"], ctx["max_tareas"]
    if pid in SOBRE_COLA:
        return _de_cola(ctx)[:maximo]
    pendientes = _lotes_pendientes(pid)
    if not simular:
        pendientes = [x for t in pendientes for x in _rehacer_si_grande(t)]
    salida = [dict(t, _cat="investigacion") for t in pendientes][:maximo]
    if pid == "vigia":
        from nucleo import vigia
        if not salida and not vigia.hecho_hoy():
            if simular:
                return [{"id": "(nuevo)", "titulo": "Vigia de novedades de hoy", "_cat": "investigacion"}]
            t = vigia.crear_lote()
            if t:
                salida.append(dict(t, _cat="investigacion"))
        return salida
    n = 0
    while len(salida) < maximo:
        lote = siguiente_lote(pid, avanzar=not simular)
        if not lote:
            break
        n += 1
        if simular:
            salida.append({"id": "(nuevo)", "titulo": f"lote {n}: {', '.join(sorted({p[0] for p in lote}))[:100]}",
                           "_cat": "investigacion"})
            break   # sin avanzar el cursor, el segundo lote seria el mismo
        salida.append(dict(_crear_lote(pid, lote, n), _cat="investigacion"))
    return salida


# ------------------------------------------------------------------ guardia de solo lectura
EXT_FOTO = EXT_CODIGO + EXT_ARCHIVOS + (".html", ".css", ".json")


def foto(raiz: Path | None = None) -> dict[str, str]:
    """Hash de cada archivo del proyecto que un turno NO debe tocar (codigo, docs, config; nada de memoria/)."""
    raiz = raiz or RAIZ
    salida = {}
    for p in _recorrer(raiz, (_FUERA_DIRS - {"tests", "vendor"}) | {"memoria", "canal"}):
        if p.suffix.lower() not in EXT_FOTO:
            continue
        rel = p.relative_to(raiz)
        try:
            salida[rel.as_posix()] = hashlib.sha1(p.read_bytes()).hexdigest()
        except OSError:
            continue
    return salida


def cambios(antes: dict[str, str], despues: dict[str, str]) -> list[str]:
    return sorted(k for k in set(antes) | set(despues) if antes.get(k) != despues.get(k))


# 28/09: comparar fotos antes/despues culpaba al turno de lo que editaba OTRA sesion a la vez (falsa alarma
# de las 18:17: era Claude editando nucleo/planificador.py). La guardia de verdad mira solo las escrituras
# del PROPIO proceso del turno, con un audit hook de Python (lo que hagan otros procesos no lo ve).
_EVENTOS_ESCRITURA = {"open", "os.rename", "os.replace", "os.remove", "os.unlink", "os.rmdir", "os.truncate",
                      "shutil.copyfile", "shutil.move", "shutil.rmtree", "os.mkdir"}
PERMITIDAS = ("memoria", "registros", "salidas", "_archivo", "chrome-perfil")   # lo que un turno si puede escribir
_guardia = {"activa": False, "escritos": set(), "instalada": False}


def _es_escritura(evento: str, args) -> bool:
    import os
    if evento != "open":
        return True
    modo, flags = (args[1] if len(args) > 1 else "r"), (args[2] if len(args) > 2 else 0)
    if isinstance(modo, str):
        return any(c in modo for c in "wax+")
    return bool((flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC))


def _vigilar(evento, args):
    if not _guardia["activa"] or evento not in _EVENTOS_ESCRITURA or not args:
        return
    import os
    rutas = args[1:2] if evento == "shutil.copyfile" else (args[:2] if evento in ("os.rename", "os.replace",
                                                                                   "shutil.move") else args[:1])
    if not _es_escritura(evento, args):
        return
    raiz = os.path.normcase(os.path.abspath(RAIZ))
    for r in rutas:
        if isinstance(r, int):
            continue
        try:
            ruta = os.path.normcase(os.path.abspath(os.fsdecode(os.fspath(r))))
        except TypeError:
            continue
        if not ruta.startswith(raiz + os.sep):
            continue
        partes = Path(os.path.relpath(ruta, raiz)).parts
        if partes and (partes[0] in PERMITIDAS or "__pycache__" in partes or partes[0].startswith(".")):
            continue
        _guardia["escritos"].add(Path(*partes).as_posix())


class GuardiaEscritura:
    """with GuardiaEscritura() as g: ... ; g.escritos -> archivos del proyecto que escribio ESTE proceso."""

    def __enter__(self):
        import sys
        if not _guardia["instalada"]:
            sys.addaudithook(_vigilar)   # no se puede quitar: se desactiva con la bandera
            _guardia["instalada"] = True
        _guardia["escritos"] = set()
        _guardia["activa"] = True
        return self

    def __exit__(self, *exc):
        _guardia["activa"] = False
        self.escritos = sorted(_guardia["escritos"])
        return False


def por_que_nada(ctx: dict) -> str:
    """Explicacion en palabras normales de por que la plantilla no tiene trabajo (para la web y el aviso)."""
    pid = ctx["plantilla"]
    if pid == "vigia":
        from nucleo import vigia
        if vigia.hecho_hoy():
            return "el vigía de novedades ya pasó hoy (va una vez al día) y su lote de hoy ya está trabajado; vuelve mañana"
        return "el vigía no encontró novedades nuevas"
    if pid == "implementador":
        from nucleo import piloto_serie
        return piloto_serie.por_que_nada()
    if ctx.get("tareas"):
        return (f"las tareas pedidas ({', '.join(ctx['tareas'])}) no están disponibles: hechas, bloqueadas, de "
                "Damián, personales o ya esperando la revisión de Claude")
    if pid == "cola":
        from nucleo import freno
        frenada, motivo = freno.cola_sin_investigaciones(pid, bool(ctx.get("manual")))
        if frenada:
            return motivo + " Y no hay otras tareas pendientes que un turno pueda hacer."
    return {"cola": "no había tareas pendientes que un turno pueda hacer (investigación, redacción o resumen sin "
                    "borrador esperando revisión)",
            "investigacion": "no había investigación pendiente sin borrador esperando revisión",
            "correcciones": "no había errores de código pendientes (tareas cat:codigo con BUG/error en el título o "
                            "la etiqueta tipo:bug)",
            "revisar_codigo": "no se encontró código que revisar",
            "revisar_archivos": "no se encontraron archivos que revisar",
            "tribunal": "el tribunal no tenía borradores que revisar (ni casos de calibración pendientes)",
            "radar": "todos los radares activos ya pasaron hoy (van una vez al día)",
            "modelos": "el banco de modelos ya midió hoy (va una vez al día)",
            "kuzushi": "Kuzushi ya observó hoy (va una vez al día)"}.get(
        pid, "no había trabajo para esta plantilla")


TOPE_SIN_NECESIDAD = 3


def calibrar_propuestas(origen: dict, propuestas: list[dict]) -> list[str]:
    """Vigia (28/09): una propuesta solo pasa de VALOR 3 si cita la tarea T### abierta que resuelve. Devuelve
    los ids rebajados (se anota en cada uno). Las demas plantillas no se tocan."""
    if plantilla_de(origen) != "vigia":
        return []
    abiertas = {t["id"] for t in T.cargar()["tareas"] if t["estado"] in ("pendiente", "en_curso")}
    rebajadas = []
    for p in propuestas:
        que = (p.get("detalle") or "").split("\n", 1)[0]
        citadas = set(re.findall(r"\bT\d{3,}\b", que)) & abiertas
        if (p.get("importancia") or 0) > TOPE_SIN_NECESIDAD and not citadas:
            T.actualizar(p["id"], importancia=TOPE_SIN_NECESIDAD)
            T.anotar(p["id"], f"Vigia: VALOR {p.get('importancia')} rebajado a {TOPE_SIN_NECESIDAD}: no cita ninguna "
                              "necesidad abierta de NEXO (T###) que resuelva.")
            rebajadas.append(p["id"])
    return rebajadas
