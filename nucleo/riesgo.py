# -*- coding: utf-8 -*-
"""Matriz de riesgo fija (T668, F2 de la epica T664; plan §4).

El nivel lo calcula CODIGO a partir de las rutas, del diff y de las etiquetas de la tarea. Ninguna IA lo baja:
una etiqueta `riesgo:Rn` (la del tribunal es `riesgo:R3`) solo lo sube.

    R0  documentacion, notas                                    automatico
    R1  tests, plantillas y CSS, prompts/roles, herramientas_*  veto de Damian 8 h ANTES (antes pasa por el tribunal: 3/3 decide, si no cae a Damian) de implementar (silencio = si)
    R2  nucleo no blindado, proveedores, router, canal, memoria, dependencias nuevas, rutas desconocidas, >300 lineas
                                                                OK de Damian DESPUES, sobre el diff real (7 dias,
                                                                silencio = no; como mucho MAX_R2 abiertas)
    R3  blindados, .claude/ y CLAUDE.md, secretos, borrados, dinero, red nueva, y los CONTROLES del implementador
        (su puerta, esta matriz, sus aprobaciones, la parada, sus tests dados y la orden de Claude)
                                                                nunca el implementador: Claude + diff a Damian

Enlace con la cola N04 (nucleo/aprobaciones.py): el veto R1 es una solicitud `tipo="veto"` de "implementar Txxx";
el OK R2 es una solicitud normal de "fusionar Txxx" cuya huella lleva el sha256 del diff, asi que un si vale solo
para ESE diff. El bot de Telegram no las ve (pendientes() sin incluir_matriz); se deciden en el Centro de la web.

CLI:
    python -m nucleo.riesgo rutas <ruta> [<ruta>...]
    python -m nucleo.riesgo diff [<archivo.diff>]        (sin archivo: lee la entrada estandar)
    python -m nucleo.riesgo tarea Txxx                   (nivel previsto antes de implementar)
    python -m nucleo.riesgo bandeja
"""
from __future__ import annotations

import hashlib
import re
import sys
import unicodedata
from datetime import datetime, timedelta
from functools import lru_cache

from nucleo import aprobaciones as ap
from nucleo.config import RAIZ

NIVELES = ("R0", "R1", "R2", "R3")
MAX_R2 = 10                       # Damian 04/10: con 10 OK R2 esperando, el implementador no produce mas R2
TESTS_DADOS = "tests:dados"
MAX_LINEAS_R1 = 300               # plan §5.2: R0/R1 como mucho ~300 lineas cambiadas
TTL_VETO = ap.TTL_VETO           # T967 (17/10): 8 h, el silencio sigue valiendo como si
TRIBUNAL_R1 = True                # T967: el veto de "implementar" pasa antes por nucleo/tribunal_r1.py
TTL_OK_R2 = timedelta(days=7)
TTL_USO = timedelta(days=7)       # cuanto vale un si (o el silencio) antes de usarse

# ------------------------------------------------------------------ reglas por ruta
_R3_EXACTAS = {"nucleo/permisos.py", "nucleo/instancia.py", "nucleo/config.py"}
_R3_PREFIJOS = ("manos/", ".claude/", "chrome-perfil/")
_R3_NOMBRES = {"secretos.toml", "claude.md", "agents.md"}
# 11/10: el implementador no puede tocar lo que lo controla (antes era R2: con un OK de Damian sobre un diff largo podia
# acabar cambiando su propia puerta o su propio nivel de riesgo). Solo endurece: nada que antes fuera R3 baja.
_R3_CONTROLES = {"nucleo/riesgo.py", "nucleo/puerta.py", "nucleo/implementador.py", "nucleo/piloto_serie.py",
                 "nucleo/aprobaciones.py", "nucleo/parada.py", "documentacion/prompts/claude_bandeja.md",
                 # T1020: el guardian de aprobaciones y lo que el reutiliza para decidir
                 "nucleo/guardian.py", "nucleo/tribunal_r1.py", "nucleo/revisor.py"}
_R3_CONTROLES_PREFIJOS = ("tests_dados/",)
_DEPENDENCIAS = re.compile(r"(^|/)(requirements[^/]*\.txt|pyproject\.toml|setup\.py|setup\.cfg|package(-lock)?\.json|"
                           r"pnpm-lock\.yaml|yarn\.lock)$|^interfaz/estatico/vendor/")
_R1_PREFIJOS = ("tests/", "interfaz/tests/", "interfaz/plantillas/", "roles/", "documentacion/prompts/")
_R1_ESTATICO = re.compile(r"^interfaz/estatico/.+\.(css|html|svg|png|ico|webmanifest)$")
_CODIGO = re.compile(r"\.(py|js|mjs|ts|ps1|psm1|bat|cmd|sh)$")

# ------------------------------------------------------------------ reglas por contenido (lineas anadidas)
_SECRETO = re.compile(
    r"(nvapi-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(proj-|ant-)?[A-Za-z0-9_-]{20,}|"
    r"gsk_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|xox[bpas]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"(?i:(api[_-]?key|token|secret|password|contrase[nñ]a)\s*[:=]\s*[\"'][^\"'\s]{16,}[\"']))")
_SECRETO_CODIGO = re.compile(r"(?i)(secretos\.toml|(^|[\"'/\\ ])\.env\b|chrome-perfil)")
_DINERO = re.compile(r"(?i)(\bstripe\b|\bpaypal\b|\bcheckout\b|\bpayments?\b|\bcharge\.create|\bpagar\b|\bpagos?\b|"
                     r"\btarjeta\b|\bcomprar\b|\bfactura)")
_URL = re.compile(r"https?://([A-Za-z0-9.-]+)")
HOSTS_PERMITIDOS = {
    "127.0.0.1", "localhost", "openrouter.ai", "chatgpt.com", "api.groq.com", "console.groq.com", "api.github.com",
    "github.com", "ollama.com", "integrate.api.nvidia.com", "build.nvidia.com", "gemini.google.com", "ai.google.dev",
    "generativelanguage.googleapis.com", "api.anthropic.com", "claude.ai", "doi.org", "www.w3.org", "huggingface.co",
    "export.arxiv.org", "api.semanticscholar.org", "api.openalex.org", "api.telegram.org",
}
_IMPORT = re.compile(r"^\s*(?:from\s+([A-Za-z_][\w]*)[\w.]*\s+import\b|import\s+([A-Za-z_][\w]*))")


def _rango(n: str) -> int:
    return NIVELES.index(n)


def _max(*ns: str) -> str:
    return max(ns, key=_rango)


def _norm(ruta: str) -> str:
    r = ruta.strip().strip('"').replace("\\", "/")
    while r.startswith("./"):
        r = r[2:]
    return r


def nivel_ruta(ruta: str) -> tuple[str, str]:
    """(nivel, motivo) de UNA ruta del repo."""
    r = _norm(ruta)
    base = r.rsplit("/", 1)[-1].lower()
    if r in _R3_EXACTAS or r.startswith(_R3_PREFIJOS) or base in _R3_NOMBRES or base == ".env" \
            or base.startswith(".env."):
        return "R3", f"{r}: blindado, secretos o reglas de Claude"
    if r.lower() in _R3_CONTROLES or r.startswith(_R3_CONTROLES_PREFIJOS):
        return "R3", f"{r}: control del implementador (puerta, riesgo, aprobaciones, parada o sus tests dados)"
    if _DEPENDENCIAS.search(r):
        return "R2", f"{r}: dependencia nueva o cambiada"
    if r.startswith("memoria/"):
        return "R2", f"{r}: datos de memoria"
    if r.startswith(_R1_PREFIJOS) or r.startswith("herramientas_") or _R1_ESTATICO.match(r):
        return "R1", f"{r}: tests, interfaz, prompts o herramientas"
    if r.lower().endswith(".md") or r.startswith("documentacion/"):
        return "R0", f"{r}: documentacion"
    return "R2", f"{r}: codigo o ruta no clasificada"


# ------------------------------------------------------------------ diff
def _bloques(diff: str) -> list[dict]:
    """Un dict por archivo del diff: ruta, origen (si es renombrado), borrado, lineas anadidas y quitadas."""
    archivos: list[dict] = []
    actual = None
    for linea in (diff or "").splitlines():
        if linea.startswith("diff --git "):
            m = re.match(r"diff --git a/(.+?) b/(.+)$", linea)
            actual = {"ruta": _norm(m.group(2)) if m else linea[11:], "origen": _norm(m.group(1)) if m else "",
                      "borrado": False, "anadidas": [], "quitadas": 0, "renombrado": False}
            archivos.append(actual)
            continue
        if actual is None:
            continue
        if linea.startswith("deleted file mode"):
            actual["borrado"] = True
        elif linea.startswith("rename from ") or linea.startswith("rename to "):
            actual["renombrado"] = True
        elif linea.startswith("+++ ") or linea.startswith("--- "):
            continue
        elif linea.startswith("+"):
            actual["anadidas"].append(linea[1:])
        elif linea.startswith("-"):
            actual["quitadas"] += 1
    return archivos


def rutas_de_diff(diff: str) -> list[str]:
    return [b["ruta"] for b in _bloques(diff)]


@lru_cache(maxsize=1)
def _paquetes_locales() -> frozenset[str]:
    nombres = set()
    for p in RAIZ.iterdir():
        if p.is_dir() and not p.name.startswith((".", "_")):
            nombres.add(p.name)
        elif p.suffix == ".py":
            nombres.add(p.stem)
    return frozenset(nombres)


@lru_cache(maxsize=1)
def _requisitos_cache() -> frozenset[str]:
    """Modulos de terceros que NEXO ya usa: los de requirements*.txt y los que ya se importan en el codigo."""
    conocidos = set()
    for req in RAIZ.glob("requirements*.txt"):
        for linea in req.read_text(encoding="utf-8", errors="replace").splitlines():
            nombre = re.split(r"[=<>\[; ]", linea.strip(), maxsplit=1)[0]
            if nombre and not nombre.startswith("#"):
                conocidos.add(nombre.lower().replace("-", "_"))
    for carpeta in [RAIZ] + [p for p in RAIZ.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))
                             and p.name not in ("memoria", "registros", "node_modules", "chrome-perfil")]:
        patron = "*.py" if carpeta == RAIZ else "**/*.py"
        for py in carpeta.glob(patron):
            try:
                texto = py.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for linea in texto.splitlines():
                m = _IMPORT.match(linea)
                if m:
                    conocidos.add((m.group(1) or m.group(2)).lower())
    return frozenset(conocidos)


def _requisitos() -> set[str]:
    return set(_requisitos_cache())


def _import_nuevo(linea: str) -> str | None:
    m = _IMPORT.match(linea)
    if not m:
        return None
    mod = m.group(1) or m.group(2)
    if mod in sys.stdlib_module_names or mod == "__future__" or mod in _paquetes_locales():
        return None
    return None if mod.lower() in _requisitos() else mod


def calcular(rutas=(), diff: str = "", etiquetas=()) -> dict:
    """Nivel de riesgo de un cambio: el mas alto de todas las reglas que se cumplen. {"nivel", "motivos"}."""
    niveles: list[tuple[str, str]] = []
    for r in rutas:
        niveles.append(nivel_ruta(r))
    total = 0
    for b in _bloques(diff):
        niveles.append(nivel_ruta(b["ruta"]))
        if b["renombrado"] and b["origen"] != b["ruta"]:
            niveles.append(nivel_ruta(b["origen"]))
        if b["borrado"]:
            niveles.append(("R3", f"{b['ruta']}: borra un archivo (se archiva en _archivo/, no se borra)"))
        total += len(b["anadidas"]) + b["quitadas"]
        codigo = bool(_CODIGO.search(b["ruta"]))
        for linea in b["anadidas"]:
            if _SECRETO.search(linea) or (codigo and _SECRETO_CODIGO.search(linea)):
                niveles.append(("R3", f"{b['ruta']}: posible secreto o acceso a secretos"))
            if not codigo:
                continue
            for host in _URL.findall(linea):
                if host.lower() not in HOSTS_PERMITIDOS:
                    niveles.append(("R3", f"{b['ruta']}: red nueva ({host})"))
            if _DINERO.search(linea):
                niveles.append(("R3", f"{b['ruta']}: dinero o pagos"))
            if b["ruta"].endswith(".py"):
                mod = _import_nuevo(linea)
                if mod:
                    niveles.append(("R2", f"{b['ruta']}: dependencia nueva ({mod})"))
    if not niveles:
        niveles.append(("R2", "sin rutas conocidas: se supone R2"))
    nivel = _max(*(n for n, _ in niveles))
    if total > MAX_LINEAS_R1 and _rango(nivel) < _rango("R2"):
        nivel = "R2"
        niveles.append(("R2", f"{total} lineas cambiadas (> {MAX_LINEAS_R1} para R0/R1)"))
    for e in etiquetas or ():
        m = re.fullmatch(r"riesgo:(R[0-3])", str(e))
        if m and _rango(m.group(1)) > _rango(nivel):
            nivel = m.group(1)
            niveles.append((nivel, f"etiqueta {e} (solo sube)"))
    motivos = list(dict.fromkeys(m for n, m in niveles if n == nivel))
    return {"nivel": nivel, "motivos": motivos}


# ------------------------------------------------------------------ nivel previsto (antes de implementar)
_RUTA_TXT = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:py|md|html|css|js|json|toml|txt|ps1|ya?ml))\b"
                       r"|(?<![\w/.-])((?:manos|nucleo|tests|canal|interfaz|roles|memoria|documentacion|"
                       r"herramientas_\w+|\.claude)/)")
_ZONAS = (("R0", ("documentacion", "readme", "indice", "vault", "notas", "informe")),
          ("R1", ("tests", "test", "plantilla", "css", "prompt")))


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def previsto(tarea: dict) -> dict:
    """Nivel ANTES de implementar, por las rutas que nombra la tarea (titulo y DONDE). Sin rutas: por la zona;
    zona desconocida = R2. El definitivo lo da el diff real (fusion)."""
    detalle = tarea.get("detalle") or ""
    m = re.search(r"(?im)^DONDE:?\s*(.*)$", detalle)
    donde = m.group(1) if m else ""
    texto = f"{tarea.get('titulo', '')}\n{donde}"
    rutas = [a or b for a, b in _RUTA_TXT.findall(texto)]
    if re.search(r"\bREADME\b", texto) and not any(r.lower().endswith("readme.md") for r in rutas):
        rutas.append("README.md")
    if rutas:
        r = calcular(rutas=rutas, etiquetas=tarea.get("etiquetas") or ())
    else:
        zona = _sin_tildes(donde)
        nivel, motivo = "R2", f"zona '{donde.strip()}' sin rutas: se supone R2"
        for n, palabras in _ZONAS:
            if any(re.search(rf"\b{p}\b", zona) for p in palabras):
                nivel, motivo = n, f"zona '{donde.strip()}'"
                break
        r = {"nivel": nivel, "motivos": [motivo]}
        for e in tarea.get("etiquetas") or ():
            mm = re.fullmatch(r"riesgo:(R[0-3])", str(e))
            if mm and _rango(mm.group(1)) > _rango(r["nivel"]):
                r = {"nivel": mm.group(1), "motivos": [f"etiqueta {e} (solo sube)"]}
    r["rutas"] = rutas
    return r


# ------------------------------------------------------------------ enlace con la cola N04
def _ahora() -> datetime:
    return datetime.now().replace(microsecond=0)


def _sha(diff: str) -> str:
    return hashlib.sha256((diff or "").encode("utf-8")).hexdigest()


def _ultima(accion: str, detalle: str) -> dict | None:
    h = ap.huella(accion, detalle)
    for s in reversed(ap.cargar()["solicitudes"]):
        if s["huella"] == h:
            return s
    return None


def fusion_deshecha(tid: str) -> bool:
    """Bloque 23 (29/10): True si principal tiene fusiones de la puerta para `tid` y TODAS se deshicieron (git revert).
    Caso T844: la salud revirtio la fusion que gasto el OK A0097; la rama reaplico el mismo diff (mismo sha) y la
    solicitud 'usada' cerraba la tarea para siempre. Sin git (o sin fusiones) = False: nada cambia."""
    from nucleo import cierre_auto as CA
    salida = CA._git("log", CA.RAMA, "--first-parent", "--format=%s", "-F", f"--grep=Fusiona impl/{tid}:")
    commits = [{"asunto": l.strip()} for l in salida.splitlines() if l.strip()]
    fusiones = [c for c in commits if c["asunto"].startswith(f"Fusiona impl/{tid}:")]
    return bool(fusiones) and not any(c["asunto"].startswith(f"Fusiona impl/{tid}:") for c in CA.vigentes(commits))


def _usada_y_deshecha(s: dict | None, tid: str) -> bool:
    return s is not None and s["estado"] == "usada" and fusion_deshecha(tid)


def r2_pendientes(ahora: datetime | None = None) -> int:
    return sum(1 for s in ap.pendientes(ahora=ahora, incluir_matriz=True) if s.get("nivel") == "R2")


def cupo_r2_lleno(ahora: datetime | None = None) -> bool:
    return r2_pendientes(ahora) >= MAX_R2


def _avisar(titulo: str, cuerpo: str, clave: str, urgencia: str) -> None:
    from nucleo import avisos
    try:
        avisos.emitir("riesgo", titulo, cuerpo, ruta="/#t-riesgo", clave=clave, urgencia=urgencia)
    except OSError:
        pass   # sin aviso la solicitud sigue en la cola y en el Centro


def _lleno(ahora) -> str:
    return (f"hay {MAX_R2} R2 esperando tu OK (maximo {MAX_R2}): el implementador no produce mas R2 hasta que "
            "bajen")


def autorizacion(tarea: dict, ahora: datetime | None = None) -> dict:
    """¿Puede el implementador EMPEZAR esta tarea? {"puede", "nivel", "motivo", "solicitud", "destino"}."""
    ahora = ahora or _ahora()
    p = previsto(tarea)
    nivel = p["nivel"]
    r = {"puede": False, "nivel": nivel, "motivo": "", "solicitud": None, "destino": "implementador",
         "motivos": p["motivos"]}
    if nivel == "R0":
        return {**r, "puede": True, "motivo": "R0: automatico"}
    if nivel == "R3":
        return {**r, "destino": "claude", "motivo": "R3: nunca el implementador; Claude prepara el parche y Damian ve el diff"}
    if nivel == "R2":
        if cupo_r2_lleno(ahora):
            return {**r, "motivo": _lleno(ahora)}
        return {**r, "puede": True, "motivo": "R2: se implementa y el OK se pide despues, sobre el diff real"}
    accion, detalle = f"implementar {tarea['id']}", f"R1 {tarea.get('titulo', '')}"
    ap.caducar(ahora=ahora)
    s = _ultima(accion, detalle)
    if s is None or s["estado"] == "caducada":
        s = ap.solicitar(accion, detalle, nivel="R1", origen="riesgo", ahora=ahora, ttl=TTL_VETO, tipo="veto",
                         ttl_aprobada=TTL_USO, extra={"tarea": tarea["id"], "titulo": tarea.get("titulo", ""),
                                                      "motivos": p["motivos"]},
                         espera_tribunal=ap.ESPERA_TRIBUNAL if TRIBUNAL_R1 else None)
        _avisar(f"Se implementará {tarea['id']} en {int(TTL_VETO.total_seconds() // 3600)} h salvo que digas NO", tarea.get("titulo", ""),
                f"riesgo:{s['id']}", "normal")
    r["solicitud"] = s["id"]
    if s["estado"] == "pendiente":
        return {**r, "motivo": f"R1: esperando el veto de Damian hasta {s['vence']} (silencio = si)"}
    if s["estado"] == "denegada":
        return {**r, "motivo": "R1: vetada por Damian"}
    return {**r, "puede": True, "motivo": "R1: nadie la veto" if s["estado"] == "aprobada" else "R1: veto ya superado"}


def resumir_diff(diff: str, maximo: int = 3000) -> str:
    cab = [f"{b['ruta']} (+{len(b['anadidas'])} -{b['quitadas']}{', BORRADO' if b['borrado'] else ''})"
           for b in _bloques(diff)]
    cuerpo = "\n".join(l for l in (diff or "").splitlines()
                       if l[:1] in "+-" and not l.startswith(("+++", "---")))
    texto = "\n".join(cab) + "\n\n" + cuerpo
    return texto if len(texto) <= maximo else texto[:maximo] + "\n[...recortado]"


# Damian 13/10 (R2 sin cuello de botella): una pieza con tests dados por Claude que ya paso la puerta entera (suite verde,
# tests dados intactos, auditor y revisor APROBAR) baja de "OK de Damian" (R2) a "se fusiona sola a las 8 h salvo
# veto" (R1). Solo si TODO lo que la hace R2 es codigo normal: nada de dependencias, memoria/, diffs grandes ni rutas
# sensibles (lo R3 -blindados, secretos, dinero, red nueva, .claude, controles- nunca llega aqui).
_SENSIBLE = re.compile(r"(?i)(permis|guardia|segur|secret|credencial|auth|token|cripto|sesion|\.claude/)")
_R2_NORMAL = ": codigo o ruta no clasificada"


def r1_por_tests_dados(tarea: dict, diff: str, c: dict | None = None) -> str:
    """'' si este diff R2 puede ir por veto R1; si no, por que sigue en R2."""
    if TESTS_DADOS not in (tarea.get("etiquetas") or []):
        return "sin tests dados por Claude"
    c = c or calcular(diff=diff, etiquetas=tarea.get("etiquetas") or ())
    if c["nivel"] != "R2":
        return f"el diff es {c['nivel']}"
    lineas = sum(len(b["anadidas"]) + b["quitadas"] for b in _bloques(diff))
    if lineas > MAX_LINEAS_R1:
        return f"{lineas} lineas cambiadas (> {MAX_LINEAS_R1} para R1)"
    sensibles = [r for r in rutas_de_diff(diff) if _SENSIBLE.search(r)]
    if sensibles:
        return f"toca rutas sensibles ({', '.join(sensibles[:3])})"
    otros = [m for m in c["motivos"] if not m.endswith(_R2_NORMAL)]
    if otros:
        return "; ".join(otros[:3])
    return ""


def fusion(tarea: dict, diff: str, nivel_aprobado: str, resumen: str = "", ahora: datetime | None = None,
           puerta_ok: bool = False) -> dict:
    """¿Se puede fusionar ESTE diff? Nivel real sobre el diff (solo sube). {"puede", "nivel_real", "motivo",
    "solicitud", "destino", "motivos"}. Si hace falta OK R2, deja la solicitud (atada al sha del diff) y avisa.
    puerta_ok=True (solo lo pasa la puerta tras suite, auditor y revisor en verde): una pieza con tests dados y diff
    R2 de codigo normal va por veto R1 de 8 h (r1_por_tests_dados)."""
    ahora = ahora or _ahora()
    c = calcular(diff=diff, etiquetas=tarea.get("etiquetas") or ())
    real = _max(c["nivel"], nivel_aprobado) if nivel_aprobado == "R3" else c["nivel"]
    r = {"puede": False, "nivel_real": real, "motivo": "", "solicitud": None, "destino": "implementador",
         "motivos": c["motivos"]}
    if real == "R3":
        return {**r, "destino": "claude", "motivo": "el diff real es R3: no se fusiona; pasa a Claude + Damian"}
    if real in ("R0", "R1") and _rango(real) <= _rango(nivel_aprobado):
        return {**r, "puede": True, "motivo": f"{real}: dentro de lo aprobado ({nivel_aprobado})"}
    accion, detalle = f"fusionar {tarea['id']}", f"R2 sha256:{_sha(diff)}"
    ap.caducar(ahora=ahora)
    # Bloque 23: si el OK de este mismo diff ya se gasto en una fusion que se deshizo, Damian vuelve a decidir: OK R2
    # nuevo (silencio = no), sin la via del veto R1 ni el tribunal del guardian (puerta_ok va a False en la solicitud).
    rehacer = _usada_y_deshecha(_ultima(f"fusionar {tarea['id']}", f"R1 veto sha256:{_sha(diff)}"), tarea["id"])         or _usada_y_deshecha(_ultima(accion, detalle), tarea["id"])
    if puerta_ok and real == "R2" and not rehacer and not r1_por_tests_dados(tarea, diff, c):
        # 12/10 (bloque 5): si Damian ya dio su OK R2 a ESTE diff (p. ej. antes de que existiera la via R1), ese OK
        # vale: no se abre un veto de 8 h encima de algo ya aprobado.
        previa = _ultima(accion, detalle)
        if previa is not None and previa["estado"] == "aprobada":
            return {**r, "puede": True, "solicitud": previa["id"], "motivo": "OK de Damian para este diff"}
        return _fusion_por_veto(tarea, diff, resumen, ahora, {**r, "nivel_real": "R1"})
    s = _ultima(accion, detalle)
    if s is None or (rehacer and s["estado"] == "usada"):
        if cupo_r2_lleno(ahora):
            return {**r, "motivo": _lleno(ahora)}
        subida = "" if real == "R2" and nivel_aprobado == "R2" else f" (aprobada como {nivel_aprobado}, el diff es {real})"
        if rehacer:
            subida += " (su fusion anterior se deshizo: decides de nuevo)"
        s = ap.solicitar(accion, detalle, nivel="R2", origen="riesgo", ahora=ahora, ttl=TTL_OK_R2,
                         ttl_aprobada=TTL_USO,
                         extra={"tarea": tarea["id"], "titulo": tarea.get("titulo", ""), "resumen": resumen,
                                "diff_resumido": resumir_diff(diff), "motivos": c["motivos"],
                                "nivel_aprobado": nivel_aprobado, "nivel_real": real,
                                "fusion_deshecha": rehacer,
                                "puerta_ok": puerta_ok and not rehacer})   # T1020: el guardian solo manda al tribunal R2 con puerta en verde
        _avisar(f"{tarea['id']} espera tu OK{subida}", resumen or tarea.get("titulo", ""), f"riesgo:{s['id']}",
                "normal")
    r["solicitud"] = s["id"]
    estado = s["estado"]
    if estado == "aprobada":
        return {**r, "puede": True, "motivo": "OK de Damian para este diff"}
    motivo = {"pendiente": f"esperando tu OK hasta {s['vence']}", "denegada": "rechazada por Damian",
              "caducada": "caducada: 7 dias sin respuesta = NO", "usada": "ese OK ya se uso"}[estado]
    return {**r, "motivo": motivo}


def _fusion_por_veto(tarea: dict, diff: str, resumen: str, ahora: datetime, r: dict) -> dict:
    accion, detalle = f"fusionar {tarea['id']}", f"R1 veto sha256:{_sha(diff)}"
    ap.caducar(ahora=ahora)
    s = _ultima(accion, detalle)
    if s is None or s["estado"] == "caducada":
        s = ap.solicitar(accion, detalle, nivel="R1", origen="riesgo", ahora=ahora, ttl=TTL_VETO, tipo="veto",
                         ttl_aprobada=TTL_USO,
                         extra={"tarea": tarea["id"], "titulo": tarea.get("titulo", ""), "resumen": resumen,
                                "diff_resumido": resumir_diff(diff), "motivos": r["motivos"], "fusion": True,
                                "nivel_aprobado": "R1"},
                         espera_tribunal=ap.ESPERA_TRIBUNAL if TRIBUNAL_R1 else None)   # T967: misma regla que implementar
        _avisar(f"{tarea['id']} se fusionará sola en 8 h salvo que la vetes", resumen or tarea.get("titulo", ""),
                f"riesgo:{s['id']}", "normal")
    r["solicitud"] = s["id"]
    estado = s["estado"]
    if estado == "aprobada":
        return {**r, "puede": True, "motivo": "R1 (tests dados + puerta): nadie la veto en 8 h"}
    motivo = {"pendiente": f"R1 (tests dados + puerta): se fusiona sola tras {s['vence']} salvo veto",
              "denegada": "vetada por Damian", "usada": "ese visto bueno ya se uso"}.get(estado, estado)
    return {**r, "motivo": motivo}


def bandeja(ahora: datetime | None = None, incluir_r3: bool = False) -> dict:
    """Lo que el Centro pinta: R1 que se haran salvo veto, R2 esperando OK y (si se pide) tareas R3."""
    ahora = ahora or _ahora()
    ps = ap.pendientes(ahora=ahora, incluir_matriz=True)

    def fila(s):
        x = s.get("extra") or {}
        return {"id": s["id"], "tarea": x.get("tarea", ""), "titulo": x.get("titulo", ""), "vence": s["vence"],
                "resumen": x.get("resumen", ""), "diff_resumido": x.get("diff_resumido", ""),
                "motivos": x.get("motivos", []), "nivel_aprobado": x.get("nivel_aprobado", ""),
                "fusion": bool(x.get("fusion")), "tribunal": s.get("tribunal") or {},
                "estado_tribunal": (s.get("tribunal") or {}).get("estado", "")}

    r2 = [fila(s) for s in ps if s.get("nivel") == "R2"]
    m = {"r1": [fila(s) for s in ps if s.get("nivel") == "R1"], "r2": r2, "r2_max": MAX_R2,
         "r2_lleno": len(r2) >= MAX_R2, "r3": [],
         # T890: R1 vetados hace menos de 7 dias cuya tarea sigue abierta (boton "Deshacer veto")
         "vetadas": [{**fila(s), "vetada_el": ap._txt(ap._fecha_veto(s) or ahora)}
                     for s in ap.vetos_deshacibles(ahora=ahora)]}
    if incluir_r3:
        from nucleo import tareas as T
        m["r3"] = [{"id": t["id"], "titulo": t["titulo"]} for t in T.cargar()["tareas"]
                   if "riesgo:R3" in (t.get("etiquetas") or []) and t.get("estado") in ("pendiente", "esperando")]
    return m


# ------------------------------------------------------------------ CLI
def _cli(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv or argv[0] not in ("rutas", "diff", "tarea", "bandeja"):
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "rutas":
        r = calcular(rutas=args)
    elif cmd == "diff":
        texto = open(args[0], encoding="utf-8").read() if args else sys.stdin.read()
        r = calcular(diff=texto)
    elif cmd == "tarea":
        from nucleo import tareas as T
        t = T.buscar(args[0]) if args else None
        if not t:
            print("Tarea no encontrada")
            return 1
        r = previsto(t)
    else:
        m = bandeja(incluir_r3=True)
        print(f"R1 (se hara salvo veto): {len(m['r1'])} · R2 esperando OK: {len(m['r2'])}/{m['r2_max']} · "
              f"R3 abiertas: {len(m['r3'])}")
        for x in m["r1"] + m["r2"]:
            print(f"  {x['id']} {x['tarea']} {x['titulo'][:70]} (vence {x['vence']})")
        return 0
    print(r["nivel"])
    for m in r["motivos"]:
        print(f"  - {m}")
    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(_cli(sys.argv[1:]))
