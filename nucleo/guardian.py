# -*- coding: utf-8 -*-
"""T1020 (Damian 18/10): guardian de aprobaciones. Diseno: documentacion/diseno/GUARDIAN_APROBACIONES.md.

Mira cada solicitud nueva de la cola (nucleo/aprobaciones.py: ambar, R1, R2) en cuanto entra (gancho en
`aprobaciones.solicitar`) y, por si el gancho falla, en el barrido del planificador cada minuto. Hace tres cosas:

1. EXPLICAR (siempre): ficha en llano en `extra.explicacion` (fuera de la huella): que hace, sobre que (rutas con su
   papel), tipo, si se puede deshacer, quien lo pide y para que, recomendacion. Analisis DETERMINISTA (lexer de
   comandos de nucleo/permisos.py, que no se toca, + nucleo/revisor.no_es_lectura + ast para `python -c`); Qwen
   local (qwen2.5:7b, num_ctx 4096, num_predict 120) solo redacta la frase, en el proceso de fondo. Todo pasa por
   auditor.tapar antes de mostrarse o enviarse.
2. DECIDIR, por este orden (la primera regla que encaja manda):
     siempre  -> Damian: secretos o claves, perfil_privado, vault privado, cambiar blindados o controles R3, dinero o
                 cuentas, borrar de verdad, git push, R3. Nunca decide el guardian.
     solo     -> aprueba el guardian (quien=guardian): SOLO LECTURA dentro del repo o de herramientas_externas.
     tribunal -> 3 familias distintas (nucleo/tribunal_r1.py, solo API): escrituras con respaldo, archivar, borrar
                 lo regenerable, ejecutar scripts del repo, aplicar un parche que no toca controles y las R2 con la
                 puerta en verde. 3/3 decide; division o proveedores caidos -> Damian con los dictamenes.
     resto    -> Damian, explicado.
   Las R1 las sigue juzgando tribunal_r1 (aqui solo se explican). Lo rojo nunca llega a la cola.
3. El minichat de cada solicitud que llega a Damian esta en nucleo/chat_aprobacion.py.

Interruptor (Ajustes): apagado = no decide nada (ni el revisor de reglas): todo a Damian, con ficha y minichat.
Es un control R3: solo lo cambia Claude.

CLI:
    .venv\\Scripts\\python.exe -m nucleo.guardian estado
    .venv\\Scripts\\python.exe -m nucleo.guardian explicar A0064
    .venv\\Scripts\\python.exe -m nucleo.guardian barrer
    .venv\\Scripts\\python.exe -m nucleo.guardian trabajar      (lo lanza el planificador: tribunal + frases de Qwen)
    .venv\\Scripts\\python.exe -m nucleo.guardian activar|desactivar
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from nucleo import aprobaciones as ap
from nucleo.candado import bloqueo
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico

ESTADO = RAIZ / "memoria" / "guardian.json"
REGISTRO = RAIZ / "memoria" / "guardian_decisiones.jsonl"
CANDADO = RAIZ / "memoria" / ".candado_guardian.lock"
EXTERNAS = RAIZ.parent / "herramientas_externas"
CONTEXTO = RAIZ.parent / "contexto"
VAULT_NEXO = CONTEXTO / "proyectos" / "nexo"
PYTHON = RAIZ / ".venv" / "Scripts" / "python.exe"

QUIEN = "guardian"
VERSION = 1                       # sube si cambia el analisis: el barrido rehace las fichas de lo pendiente
GANCHO = True                     # tests/conftest lo apaga; los tests del guardian lo encienden
LANZADOR = None                   # los tests lo sustituyen: nunca un proceso real desde un tick de prueba
CADA_BARRIDO = timedelta(seconds=60)
ESPERA_TRIBUNAL = timedelta(minutes=20)   # pasado esto sin dictamen, a Damian
MAX_TRIBUNAL = 3                  # solicitudes por pasada del proceso de fondo
MAX_QWEN = 5

MODELO_QWEN = "qwen2.5:7b"
URL_OLLAMA = "http://localhost:11434"
NUM_CTX = 4096
NUM_PREDICT = 120
TIMEOUT_QWEN = 40.0

NEXO_DECIDE = {"guardian": "NEXO solo", "tribunal": "el tribunal de 3 IAs", "revisor:reglas": "NEXO solo"}

TIPOS = {
    "lee": "Solo lee (no cambia nada)",
    "escribe": "Escribe (con copia o historial de lo anterior)",
    "archiva": "Archiva (se puede recuperar de _archivo/)",
    "borra": "Borra de verdad",
    "borra_regenerable": "Borra algo que se vuelve a generar solo",
    "ejecuta": "Ejecuta código",
    "red": "Sale a internet",
    "sistema": "Cambia el sistema o instala programas",
    "codigo": "Cambia el código de NEXO",
    "tarea": "Cambia una tarea",
    "otro": "Otra acción",
}
DESHACER = {
    "lee": "No hace falta: no cambia nada.",
    "escribe": "Sí: queda una copia del archivo anterior (o el historial de git) para volver atrás.",
    "archiva": "Sí: se recupera sacándolo de _archivo/.",
    "borra": "No: lo borrado no se puede recuperar.",
    "borra_regenerable": "No hace falta: NEXO lo vuelve a generar cuando lo necesita.",
    "ejecuta": "Depende de lo que haga el programa: lo que cambie no se deshace solo.",
    "red": "No: lo que se envía o se descarga no se puede deshacer.",
    "sistema": "Solo a mano (desinstalando o volviendo a cambiar el ajuste).",
    "codigo": "Sí: con git se puede revertir el cambio.",
    "tarea": "Sí: el cambio queda anotado en la tarea y se puede deshacer.",
    "otro": "No se sabe.",
}
RIESGO = {"lee": "BAJO", "escribe": "MEDIO", "archiva": "BAJO", "borra": "ALTO", "borra_regenerable": "BAJO",
          "ejecuta": "MEDIO", "red": "ALTO", "sistema": "ALTO", "codigo": "MEDIO", "tarea": "BAJO", "otro": "MEDIO"}

# ------------------------------------------------------------------ rutas
_EXT = (r"py|pyc|json|jsonl|md|toml|txt|patch|diff|env|example|sample|template|html|js|css|ps1|bat|cmd|log|ya?ml|"
        r"csv|ini|cfg|sh|sqlite|db|pem|key|pfx|lock")
_RUTA_ABS = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\)[^\s'\";|,()]*")
_RUTA_REL = re.compile(rf"(?<![\w$:/\\.])(?:[\w.-]+[\\/])+[\w.-]*|(?<![\w$:/\\])[\w-]*(?:\.[\w-]+)*\.(?:{_EXT})\b",
                       re.IGNORECASE)
_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_NO_SECRETO = (".example", ".sample", ".template", ".dist")
_SECRETO_NOMBRE = re.compile(r"^(secretos.*|\.env(\..*)?|id_rsa.*|id_ed25519.*|.*\.(pem|key|pfx|p12)|credentials?\.json|"
                             r"token\.json|cookies(\.sqlite)?|login data)$", re.IGNORECASE)
_REGENERABLE = re.compile(r"(^|[\\/])(__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|node_modules|\.cache|build|dist|"
                          r"tmp|temp)([\\/]|$)|\.(pyc|tmp)$", re.IGNORECASE)
# Controles del propio guardian (R3: solo los cambia Claude), ademas de lo que ya es R3 en nucleo/riesgo.py.
_CONTROLES = {"nucleo/guardian.py", "nucleo/tribunal_r1.py", "nucleo/revisor.py", "nucleo/chat_aprobacion.py",
              "nucleo/guardia_python.py", "memoria/guardian.json", "memoria/guardian_decisiones.jsonl",
              "memoria/aprobaciones.json", "memoria/aprobaciones_historial.jsonl", "memoria/aprobaciones_latido.json",
              "memoria/revisor_estado.json", "memoria/revisor_decisiones.jsonl"}

# ------------------------------------------------------------------ texto del comando
_SECRETO_TXT = re.compile(r"secretos|\.env\b(?!\.(?:example|sample|template|dist)\b)|id_rsa|id_ed25519|\.pem\b|"
                          r"credential|password|contrase[nñ]a|api[_-]?key|\btokens?\b|clipboard|chrome-perfil|"
                          r"login data|cookies", re.IGNORECASE)
_PRIVADO_TXT = re.compile(r"perfil_privado", re.IGNORECASE)
_VAULT_TXT = re.compile(r"(^|[\\/])contexto[\\/](?!proyectos[\\/]nexo([\\/]|$))", re.IGNORECASE)
_DINERO_TXT = re.compile(r"\bstripe\b|\bpaypal\b|(?<!git )\bcheckout\b|\bpagar\b|\bpagos?\b|\btarjeta\b|\bcomprar\b|\bfactura|"
                         r"\btransferencia\b|\bbizum\b|\bcrear\s+cuenta\b|\bsign\s*up\b|\bregistrarse\b", re.IGNORECASE)
_GIT_PUSH = re.compile(r"\bgit\s+(-c\s+\S+\s+)*push\b", re.IGNORECASE)
_GIT_APPLY = re.compile(r"\bgit\s+(?:apply|am)\b(?P<resto>[^;|&\n]*)", re.IGNORECASE)
_GIT_GUARDA = re.compile(r"^\s*git\s+(add|commit|mv|stash\s+push|tag)\b", re.IGNORECASE)
_GIT_PIERDE = re.compile(r"\bgit\s+(checkout|restore|reset|stash\s+(drop|clear)|rebase|branch\s+-D)\b", re.IGNORECASE)
_MOVER_ARCHIVO = re.compile(r"\b(move-item|mv|move)\b[^;|&\n]*[\\/ ]_archivo[\\/]", re.IGNORECASE)
_PY_SCRIPT = re.compile(r'^\s*(?:&\s*)?"?(?:[^"\s]*[\\/])?pythonw?(?:\.exe)?"?\s+(?P<rest>.+)$', re.IGNORECASE)
_PY_C = re.compile(r"""^\s*(?:&\s*)?"?(?:\.venv[\\/]Scripts[\\/])?python(?:\.exe)?"?\s+-c\s+"""
                   r"""(?:"(?P<d>[^"`$]*)"|'(?P<s>[^']*)')\s*$""", re.IGNORECASE)
_RECURSIVO = re.compile(r"\s-r(ecurse)?\b|\s-depth\b|\brg\b|\bgrep\s+-\w*r|\bfindstr\b[^|;]*\s/s\b|"
                        r"\bdir\b[^|;]*\s/s\b|\s/s\b", re.IGNORECASE)
# Leer una ruta que se calcula ($variable o (expresion)): no se puede comprobar que no sea un secreto.
_RUTA_CALCULADA = re.compile(r"(?:get-content|\bgc\b|\bcat\b|\btype\b|select-string|\bsls\b|import-csv|import-clixml|"
                             r"get-item\b|\bgi\b|format-hex)\s+(?:-(?:literal)?path\s+)?[$(]|-(?:literal)?path\s+[$(]|"
                             r"\[char\]", re.IGNORECASE)
_COMODIN = re.compile(r"[\w.\\/:-]*[*?][\w.*?\\/:-]*")
_SENSIBLES = ("secretos.toml", ".env", ".env.local", ".env.production", "id_rsa", "id_ed25519", "credentials.json",
              "token.json", "cookies", "perfil_privado", "clave.key", "cert.pem")
_MATH = re.compile(r"\[(?:system\.)?math\]::(?:min|max|abs|round|floor|ceiling|truncate)\s*\(", re.IGNORECASE)


def _ahora() -> datetime:
    return datetime.now().replace(microsecond=0)


def _txt(d: datetime) -> str:
    return d.strftime(ap.FORMATO)


# ------------------------------------------------------------------ interruptor y estado
def _leer_estado() -> dict:
    try:
        d = json.loads(ESTADO.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def activo() -> bool:
    """Interruptor de Ajustes. Sin archivo, encendido; ilegible, APAGADO (ante la duda, todo a Damian)."""
    if not ESTADO.is_file():
        return True
    d = _leer_estado()
    return d.get("activo", True) is True if d else False


def poner_activo(valor: bool, quien: str = "damian:web") -> dict:
    with bloqueo(CANDADO):
        d = _leer_estado()
        d.update(activo=bool(valor), cambiado=_txt(_ahora()), por=quien)
        escribir_atomico(ESTADO, json.dumps(d, ensure_ascii=False, indent=1) + "\n")
    _anotar({"cuando": _txt(_ahora()), "evento": "interruptor", "activo": bool(valor), "quien": quien})
    return d


def _anotar(linea: dict) -> None:
    try:
        REGISTRO.parent.mkdir(parents=True, exist_ok=True)
        with REGISTRO.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")
    except OSError:
        pass   # el registro nunca para el trabajo; la decision ya esta en el historial encadenado de la cola


def decisiones(n: int = 50) -> list[dict]:
    try:
        lineas = REGISTRO.read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []
    salida = []
    for l in lineas:
        try:
            salida.append(json.loads(l))
        except ValueError:
            continue
    return salida


# ------------------------------------------------------------------ rutas: donde estan y que papel tienen
def _resolver(r: str) -> Path | None:
    r = r.strip().strip("'\"").rstrip(".,;:")
    if not r:
        return None
    try:
        p = Path(r)
        return (p if p.is_absolute() else RAIZ / p).resolve()
    except (OSError, ValueError):
        return None


def _dentro(p: Path, base: Path) -> bool:
    try:
        p.relative_to(base.resolve())
        return True
    except ValueError:
        return False


def marcas_ruta(p: Path) -> set[str]:
    """secreto | plantilla | privado | vault | control | repo | externa | fuera."""
    m: set[str] = set()
    nombre = p.name.lower()
    partes = {x.lower() for x in p.parts}
    if nombre.startswith(".env") and nombre.endswith(_NO_SECRETO):
        m.add("plantilla")
    elif _SECRETO_NOMBRE.match(nombre) or "chrome-perfil" in partes:
        m.add("secreto")
    if "perfil_privado" in partes:
        m.add("privado")
    if _dentro(p, CONTEXTO) and not _dentro(p, VAULT_NEXO):
        m.add("vault")
    if _dentro(p, RAIZ):
        m.add("repo")
        rel = p.relative_to(RAIZ.resolve()).as_posix()
        from nucleo import riesgo
        from nucleo.permisos import ARCHIVOS_BLINDADOS
        es_r3 = riesgo.nivel_ruta(rel)[0] == "R3" and "plantilla" not in m
        if es_r3 or rel.lower() in _CONTROLES or Path(rel) in ARCHIVOS_BLINDADOS:
            m.add("control")
    elif _dentro(p, EXTERNAS):
        m.add("externa")
    elif not _dentro(p, VAULT_NEXO):
        m.add("fuera")
    return m


def _mostrar(p: Path) -> str:
    """La ruta como la ve Damian: relativa al repo o a herramientas_externas; si no, la absoluta (luego se tapa)."""
    for base, pref in ((RAIZ, ""), (EXTERNAS, "herramientas_externas/"), (VAULT_NEXO, "vault NEXO/")):
        if _dentro(p, base):
            return pref + p.relative_to(base.resolve()).as_posix()
    return str(p)


def papel(p: Path, m: set[str] | None = None) -> str:
    m = marcas_ruta(p) if m is None else m
    rel = _mostrar(p).lower()
    if "secreto" in m:
        return "archivo con claves o datos de acceso (secreto)"
    if "plantilla" in m:
        return "plantilla de configuración sin claves"
    if "privado" in m:
        return "datos privados de Damián"
    if "vault" in m:
        return "notas privadas de Damián (vault)"
    if "control" in m:
        return "archivo de control de NEXO (permisos, aprobaciones o sus reglas)"
    if "externa" in m:
        return "herramienta externa descargada (fuera del repo de NEXO)"
    if "fuera" in m:
        return "fuera de las carpetas de NEXO"
    if _REGENERABLE.search(rel):
        return "archivos temporales que se regeneran solos"
    for pref, txt in (("memoria/", "datos de trabajo de NEXO"), ("tests/", "pruebas automáticas"),
                      ("interfaz/tests/", "pruebas automáticas"), ("documentacion/", "documentación de NEXO"),
                      ("herramientas_nube/", "script auxiliar de NEXO"), ("_archivo/", "archivo de cosas viejas"),
                      ("nucleo/", "código de NEXO"), ("interfaz/", "la web de NEXO"), ("vault nexo/", "documentación de NEXO")):
        if rel.startswith(pref):
            return txt
    return "carpeta" if p.is_dir() else "archivo de NEXO"


def rutas_de(texto: str) -> list[Path]:
    """Rutas que aparecen en un comando (absolutas, con carpeta o con extension conocida). Sin URLs."""
    limpio = _COMODIN.sub(" ", _URL.sub(" ", texto or ""))   # los comodines los mira comodin_sensible
    vistas, salida = set(), []
    for m in list(_RUTA_ABS.finditer(limpio)) + list(_RUTA_REL.finditer(_RUTA_ABS.sub(" ", limpio))):
        p = _resolver(m.group(0))
        if p is not None and re.fullmatch(r"pythonw?(\.exe)?", p.name, re.IGNORECASE):
            continue   # el interprete no es "sobre que" actua la orden
        if p is not None and str(p).lower() not in vistas:
            vistas.add(str(p).lower())
            salida.append(p)
    return salida


# ------------------------------------------------------------------ ¿solo lee?
_LIBRES = {"json", "re", "collections", "itertools", "math", "statistics", "datetime", "textwrap", "difflib", "pprint",
           "string", "unicodedata", "hashlib", "functools", "operator", "fnmatch", "glob", "csv", "pathlib", "tomllib",
           "ast", "typing", "decimal", "fractions", "bisect", "heapq", "time"}
_PROHIBIDAS = {"exec", "eval", "compile", "__import__", "breakpoint", "input", "getattr", "setattr", "delattr",
               "globals", "locals", "vars", "memoryview", "help"}
_ESCRIBEN = {"write", "writelines", "write_text", "write_bytes", "unlink", "rename", "rmdir", "mkdir", "touch",
             "chmod", "symlink_to", "hardlink_to", "link_to", "rmtree", "remove", "removedirs", "makedirs", "system",
             "popen", "kill", "truncate", "save", "savefig", "dump_to", "send", "connect", "urlopen", "run",
             "call", "check_output", "spawn", "startfile", "copy", "copyfile", "copytree", "move"}


def _modo_lectura(nodo: ast.AST | None) -> bool:
    return nodo is None or (isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)
                            and set(nodo.value) <= set("rbt"))


def _constante(nodo: ast.AST | None) -> bool:
    return isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)


def _es_path_constante(nodo: ast.AST) -> bool:
    """Path('constante') o pathlib.Path('constante'): la unica forma de leer con Path que se acepta."""
    if not isinstance(nodo, ast.Call) or not nodo.args or not all(_constante(a) for a in nodo.args):
        return False
    f = nodo.func
    return isinstance(f, ast.Name) and f.id == "Path" or isinstance(f, ast.Attribute) and f.attr == "Path"


def _arg_recursivo(n: ast.Call) -> bool:
    return any(k.arg == "recursive" for k in n.keywords) or any(
        _constante(a) and "**" in a.value for a in n.args)


def python_solo_lee(codigo: str) -> str | None:
    """None si el codigo de `python -c` solo lee (sin escritura, sin red, sin subprocesos); si no, el motivo.
    Lista blanca: modulos de texto/datos, open() solo en lectura, nada de dunder ni de exec/eval/getattr."""
    try:
        arbol = ast.parse(codigo)
    except SyntaxError:
        return "no se entiende el código"
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] not in _LIBRES:
                    return f"importa {a.name}"
        elif isinstance(n, ast.ImportFrom):
            if (n.module or "").split(".")[0] not in _LIBRES or n.level:
                return f"importa {n.module}"
        elif isinstance(n, ast.Attribute) and n.attr.startswith("__"):
            return "usa atributos internos de Python"
        elif isinstance(n, ast.Name) and n.id in _PROHIBIDAS:
            return f"usa {n.id}"
        elif isinstance(n, (ast.Global, ast.Nonlocal, ast.Delete)):
            return "cambia variables o borra"
        elif isinstance(n, ast.Call):
            f = n.func
            kw = {k.arg: k.value for k in n.keywords}
            if isinstance(f, ast.Name) and f.id == "open":
                if not _modo_lectura(n.args[1] if len(n.args) > 1 else kw.get("mode")):
                    return "abre un archivo para escribir"
                if not _constante(n.args[0] if n.args else kw.get("file")):
                    return "abre un archivo cuyo nombre se calcula (no se puede comprobar cuál)"
            elif isinstance(f, ast.Name) and f.id == "Path" or isinstance(f, ast.Attribute) and f.attr == "Path":
                if not all(_constante(a) for a in n.args):
                    return "construye una ruta que se calcula (no se puede comprobar cuál)"
            elif isinstance(f, ast.Attribute):
                if f.attr in ("open", "read_text", "read_bytes") and not _es_path_constante(f.value):
                    return "lee un archivo cuyo nombre se calcula (no se puede comprobar cuál)"
                if f.attr in ("rglob", "walk") or f.attr == "glob" and _arg_recursivo(n):
                    return "recorre todas las subcarpetas (podría leer lo privado)"
                if f.attr == "open" and not _modo_lectura(n.args[0] if n.args else kw.get("mode")):
                    return "abre un archivo para escribir"
                if f.attr == "replace" and len(n.args) < 2:
                    return "renombra un archivo"          # Path.replace(destino); str.replace(a, b) lleva dos
                if f.attr in _ESCRIBEN:
                    return f"llama a {f.attr}"
            if "file" in kw:
                return "escribe en un archivo con print(file=...)"
    return None


def _normalizar_ps(cmd: str) -> str:
    """Lo unico que se acepta de mas sobre revisor.no_es_lectura: [Math]::Min/Max/... (calculo puro) y los escapes
    `n `t `r `0 DENTRO de comillas dobles. Las rutas de herramientas_externas cuentan como del repo."""
    c = _MATH.sub("(", cmd)
    c = re.sub(r'"[^"]*"', lambda m: re.sub(r"`[ntr0]", " ", m.group(0)), c)
    for m in _RUTA_ABS.findall(c):
        p = _resolver(m)
        if p is not None and ".." not in m and _dentro(p, EXTERNAS):
            c = c.replace(m, "externa")
    return c


def comando_solo_lee(cmd: str) -> str | None:
    """None si la linea solo lee; si no, el motivo. `python -c` con ast; PowerShell con revisor.no_es_lectura."""
    from nucleo import revisor
    from nucleo.permisos import BORRADO, ROJOS
    if ROJOS.search(cmd) or BORRADO.search(cmd):
        return "borra o es una orden prohibida"
    m = _PY_C.match(cmd)
    if m:
        return python_solo_lee(m.group("d") if m.group("d") is not None else m.group("s"))
    if _RECURSIVO.search(cmd):
        return "busca en todas las subcarpetas (podría leer lo privado)"
    if _RUTA_CALCULADA.search(cmd):
        return "lee una ruta que se calcula (no se puede comprobar cuál)"
    return revisor.no_es_lectura(_normalizar_ps(cmd))


# ------------------------------------------------------------------ git apply: ¿que toca el parche?
def destinos_parche(cmd: str) -> list[str] | None:
    """Rutas que cambia el parche de un `git apply <archivo>`. None si no se puede leer (entonces: Damian)."""
    m = _GIT_APPLY.search(cmd)
    if not m:
        return None
    archivos = [a for a in m.group("resto").split() if not a.startswith("-")]
    if not archivos:
        return None
    destinos: list[str] = []
    for a in archivos:
        p = _resolver(a)
        if p is None or not p.is_file() or not _dentro(p, RAIZ):
            return None
        try:
            texto = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        destinos += re.findall(r"(?m)^\+\+\+ b/(\S+)", texto) + re.findall(r"(?m)^diff --git a/\S+ b/(\S+)", texto)
    return sorted(set(destinos)) or None


# ------------------------------------------------------------------ analisis
def _resultado(tipo: str, regla: str, motivo: str, rutas: list[Path], que: str) -> dict:
    return {"tipo": tipo, "regla": regla, "motivo": motivo, "rutas": rutas, "que": que}


def _nombres(rutas: list[Path], maximo: int = 3) -> str:
    n = [_mostrar(p).rsplit("/", 1)[-1] or _mostrar(p) for p in rutas[:maximo]]
    return ", ".join(n) + ("…" if len(rutas) > maximo else "")


def comodin_sensible(texto: str) -> str:
    """Un comodin (*.toml, .env*, memoria/*) que abarca un secreto o lo privado: lo devuelve; si no, ''. Dentro del
    repo o de herramientas_externas se expande de verdad (sin recursion) y se mira cada archivo; fuera, o con **, se
    compara el nombre con los sensibles conocidos (ante la duda, sensible)."""
    import fnmatch
    import glob
    for m in _COMODIN.findall(_URL.sub(" ", texto or "")):
        m = m.strip("'\",;")
        base = re.split(r"[\\/]", m)[-1].lower()
        if not base or "**" in m:
            if m:
                return m
            continue
        carpeta = _resolver(re.split(r"[\\/](?=[^\\/]*$)", m)[0]) if re.search(r"[\\/]", m) else RAIZ.resolve()
        if carpeta is not None and "*" not in str(carpeta) and "?" not in str(carpeta) and (
                _dentro(carpeta, RAIZ) or _dentro(carpeta, EXTERNAS)):
            for f in glob.glob(str(carpeta / base))[:2000]:
                if marcas_ruta(Path(f).resolve()) & {"secreto", "privado", "vault"}:
                    return m
            continue
        if any(fnmatch.fnmatch(n, base) for n in _SENSIBLES):
            return m
    return ""


def _siempre(texto: str, marcas: set[str]) -> str:
    """Motivo de la regla 1 (siempre Damian) que no depende de si lee o escribe; '' si no encaja."""
    if "secreto" in marcas or _SECRETO_TXT.search(texto):
        return "toca secretos o claves"
    if comodin_sensible(texto):
        return f"usa un comodín ({comodin_sensible(texto)}) que también abarca secretos o datos privados"
    if "privado" in marcas or _PRIVADO_TXT.search(texto):
        return "toca tus datos privados (perfil_privado)"
    if "vault" in marcas or _VAULT_TXT.search(texto):
        return "toca tus notas privadas (vault)"
    if _DINERO_TXT.search(texto):
        return "tiene que ver con dinero o cuentas"
    if _GIT_PUSH.search(texto):
        return "git push: subiría el historial privado (lo correcto es publicar_nube.py)"
    return ""


def _modulo_como_ruta(cmd: str) -> list[Path]:
    """`python -m nucleo.aprobaciones ...` -> nucleo/aprobaciones.py (para ver si ejecuta un control)."""
    m = re.search(r"\s-m\s+([A-Za-z_][\w.]*)", cmd)
    if not m:
        return []
    base = RAIZ / Path(*m.group(1).split("."))
    return [p for p in (base.with_suffix(".py"), base / "__main__.py") if p.is_file()][:1]


def _analizar_comando(accion: str, cmd: str) -> dict:
    from nucleo.permisos import AMBAR, BORRADO, ROJOS
    rutas = rutas_de(cmd) + _modulo_como_ruta(cmd)
    envoltorio = bool(_PY_SCRIPT.match(cmd))   # guardia_python.py como envoltorio de un script: no se "toca"
    if envoltorio:
        rutas = [p for p in rutas if p.name.lower() != "guardia_python.py"]
    marcas = set().union(*(marcas_ruta(p) for p in rutas)) if rutas else set()
    sobre = _nombres(rutas)
    motivo = _siempre(cmd, marcas)
    if motivo:
        return _resultado("otro", "siempre", motivo, rutas, f"Ejecutar una orden que {motivo}.")
    if accion == "ejecutar comando":
        no = comando_solo_lee(cmd)
        if no is None:
            if "fuera" in marcas:
                return _resultado("lee", "resto", "lee fuera de las carpetas de NEXO", rutas,
                                  f"Leer {sobre} (fuera de las carpetas de NEXO).")
            py = bool(_PY_C.match(cmd))
            que = (f"Leer {sobre or 'datos de NEXO'} con un pequeño programa de Python que solo lee." if py
                   else f"Leer o buscar texto en {sobre or 'archivos de NEXO'} (solo lectura).")
            return _resultado("lee", "solo", "solo lee dentro del repo o de herramientas_externas, sin secretos", rutas,
                              que)
    if ROJOS.search(cmd):
        return _resultado("borra", "siempre", "lleva algo que NEXO tiene prohibido (rojo)", rutas,
                          "Ejecutar una orden que lleva algo prohibido (aunque sea en un texto).")
    if BORRADO.search(cmd):
        # sobre la ruta relativa al repo: la carpeta del repo puede colgar de un \Temp\ (worktrees) y no por eso es cache
        if rutas and all(_REGENERABLE.search(_mostrar(p)) for p in rutas) and not marcas & {"control", "fuera"}:
            return _resultado("borra_regenerable", "tribunal", "borra solo lo regenerable (cachés, temporales, build)",
                              rutas, f"Borrar {sobre} (archivos que se regeneran solos).")
        return _resultado("borra", "siempre", "borra de verdad y no hay copia", rutas,
                          f"Borrar {sobre or 'archivos'}.")
    if _GIT_APPLY.search(cmd):
        destinos = destinos_parche(cmd)
        if destinos is None:
            return _resultado("codigo", "siempre", "no puedo leer el parche para saber qué cambia", rutas,
                              "Aplicar un parche (un cambio de código ya escrito).")
        control = [d for d in destinos if "control" in marcas_ruta((RAIZ / d).resolve())]
        lista = ", ".join(destinos[:3]) + ("…" if len(destinos) > 3 else "")
        if control:
            return _resultado("codigo", "siempre", f"el parche cambia archivos de control ({', '.join(control[:3])})",
                              rutas, f"Aplicar un parche que cambia {lista}.")
        return _resultado("codigo", "tribunal", "aplica un parche que no toca controles", rutas,
                          f"Aplicar un parche que cambia {lista}.")
    partes = [p.strip() for p in re.split(r"[;\n]|&&", cmd) if p.strip()]
    solo_git = bool(partes) and all(_GIT_GUARDA.match(p) or re.match(r"\s*git\s+(log|status|diff|show)\b", p, re.I)
                                    for p in partes)
    if "control" in marcas:
        return _resultado("codigo", "siempre", "no es solo lectura y nombra un archivo de control de NEXO", rutas,
                          f"Guardar en el historial (git) un cambio en {sobre} (archivo de control de NEXO)." if solo_git
                          else f"Ejecutar una orden que puede cambiar {sobre} (archivo de control de NEXO).")
    if _MOVER_ARCHIVO.search(cmd):
        return _resultado("archiva", "tribunal", "archiva en _archivo/", rutas, f"Mover {sobre} a _archivo/.")
    if _GIT_PIERDE.search(cmd):
        return _resultado("borra", "resto", "puede perder cambios que no estén guardados en git", rutas,
                          "Deshacer cambios de archivos con git.")
    if AMBAR.search(cmd):
        tipo = "red" if re.search(r"invoke-web|invoke-rest|\b(iwr|irm|curl|wget)\b|download|bits", cmd, re.I) \
            else "sistema"
        return _resultado(tipo, "resto", "instala, descarga o cambia el sistema", rutas,
                          "Conectarse a internet o descargar." if tipo == "red" else
                          "Instalar programas o cambiar la configuración del sistema.")
    if "fuera" in marcas:
        return _resultado("otro", "resto", "actúa fuera de las carpetas de NEXO", rutas, f"Una orden sobre {sobre}.")
    partes = [p.strip() for p in re.split(r"[;\n]|&&", cmd) if p.strip()]
    if partes and all(_GIT_GUARDA.match(p) for p in partes):
        return _resultado("escribe", "tribunal", "guarda en el historial de git (se puede deshacer)", rutas,
                          "Guardar en el historial (git) un cambio.")
    m = _PY_SCRIPT.match(cmd)
    if m and len(partes) == 1:
        resto = m.group("rest").split()
        objetivo = resto[1] if resto[:1] == ["-m"] and len(resto) > 1 else resto[0] if resto else ""
        if resto[:1] == ["-m"] and objetivo.split(".")[0] in ("nucleo", "herramientas_nube", "extremidades", "interfaz"):
            return _resultado("ejecuta", "tribunal", "ejecuta un módulo del repo", rutas,
                              f"Ejecutar el módulo {objetivo} de NEXO.")
        scripts = [p for p in rutas if p.suffix.lower() == ".py"]
        if scripts and all("repo" in marcas_ruta(p) and "control" not in marcas_ruta(p) and p.is_file()
                           for p in scripts):
            return _resultado("ejecuta", "tribunal", "ejecuta un script del repo", rutas,
                              f"Ejecutar el script {_nombres(scripts)}.")
    return _resultado("otro", "resto", "no encaja en ninguna regla conocida", rutas,
                      "Ejecutar una orden en el PC." if accion == "ejecutar comando" else
                      "Arrancar un programa en segundo plano.")


def analizar(s: dict) -> dict:
    """Analisis determinista de una solicitud: {tipo, regla (siempre|solo|tribunal|resto|r1), motivo, rutas, que}."""
    accion = str(s.get("accion") or "")
    detalle = str(s.get("detalle") or "")
    nivel = s.get("nivel") or "ambar"
    extra = s.get("extra") or {}
    if nivel == "R3":
        return _resultado("codigo", "siempre", "es R3: solo Claude y Damián", [], f"{accion}.")
    if nivel in ("R1", "R2"):
        tarea, titulo = extra.get("tarea", ""), extra.get("titulo", "")
        fusion = accion.startswith("fusionar")
        que = (f"Fusionar en NEXO el cambio ya programado de la tarea {tarea}: {titulo}." if fusion
               else f"Dejar que el implementador programe la tarea {tarea}: {titulo}.")
        if nivel == "R1":
            return _resultado("codigo", "r1", "R1: la juzga el tribunal de R1 (silencio = sí)", [], que)
        motivos = " ".join(str(m) for m in extra.get("motivos") or [])
        if "R3" in motivos or "blindado" in motivos or "control" in motivos:
            return _resultado("codigo", "siempre", "el cambio toca controles", [], que)
        if extra.get("puerta_ok") is not True:
            return _resultado("codigo", "resto", "R2 sin constancia de que la puerta pasara en verde", [], que)
        return _resultado("codigo", "tribunal", "R2 con la puerta en verde (suite, auditor y revisor)", [], que)
    if accion.startswith("chat_tarea:"):
        return _resultado("tarea", "resto", "es un cambio que pediste tú en el chat de una tarea: confírmalo", [],
                          "Hacer el cambio que pediste en el chat de una tarea.")
    if accion in ("leer", "listar", "cwd"):
        p = _resolver(detalle)
        rutas = [p] if p is not None else []
        marcas = marcas_ruta(p) if p is not None else {"fuera"}
        motivo = _siempre(detalle, marcas)
        que = {"leer": f"Leer el archivo {_nombres(rutas)}.", "listar": f"Ver qué archivos hay en {_nombres(rutas)}.",
               "cwd": f"Trabajar dentro de la carpeta {_nombres(rutas)}."}[accion]
        if motivo:
            return _resultado("lee", "siempre", motivo, rutas, que)
        if marcas & {"repo", "externa"}:
            return _resultado("lee", "solo", "solo lee dentro del repo o de herramientas_externas, sin secretos",
                              rutas, que)
        return _resultado("lee", "resto", "lee fuera de las carpetas de NEXO", rutas, que)
    if accion in ("escribir", "archivar", "ejecutar_python"):
        p = _resolver(detalle.split(" sha256:")[0])
        rutas = [p] if p is not None else []
        marcas = marcas_ruta(p) if p is not None else {"fuera"}
        nombre = _nombres(rutas)
        tipo = {"escribir": "escribe", "archivar": "archiva", "ejecutar_python": "ejecuta"}[accion]
        que = {"escribir": f"Escribir el archivo {nombre}.", "archivar": f"Mover {nombre} a _archivo/ (no se borra).",
               "ejecutar_python": f"Ejecutar el script {nombre}."}[accion]
        motivo = _siempre(detalle, marcas) or ("cambia o ejecuta un archivo de control de NEXO" if "control" in marcas
                                               else "")
        if motivo:
            return _resultado(tipo, "siempre", motivo, rutas, que)
        if "repo" in marcas or (tipo == "escribe" and "externa" in marcas):
            return _resultado(tipo, "tribunal", {"escribe": "escribe con respaldo", "archiva": "archiva en _archivo/",
                                                 "ejecuta": "ejecuta un script del repo"}[tipo], rutas, que)
        return _resultado(tipo, "resto", "fuera de las carpetas de NEXO", rutas, que)
    if accion in ("ejecutar comando", "lanzar proceso"):
        return _analizar_comando(accion, detalle)
    return _resultado("otro", "resto", "acción que el guardián no conoce", [], f"{accion}.")


# ------------------------------------------------------------------ ficha en llano
def _tapar(texto: str) -> str:
    from nucleo import auditor
    return auditor.tapar(texto)


def _para_que(s: dict) -> str:
    extra = s.get("extra") or {}
    return str(extra.get("motivo") or extra.get("para_que") or extra.get("resumen") or "").strip()


_RECOMIENDA = {
    "solo": "Aprobar: solo lee y no toca nada privado. Lo aprueba NEXO sin preguntarte.",
    "tribunal": "Lo decide el tribunal de 3 IAs de familias distintas; si no se ponen de acuerdo, te llega a ti.",
    "r1": "Lo mira el tribunal de R1; si no dices nada en el plazo, se hace.",
}


def ficha(s: dict, a: dict | None = None) -> dict:
    """Ficha en llano (determinista). Mismas claves que revisor.explicar (que, para_que, quien, quien_corto, riesgo,
    si_no, por_que_a_ti, frase) mas sobre, tipo, tipo_llano, deshacer, recomendacion, regla y motivo_regla."""
    from nucleo import revisor
    a = a or analizar(s)
    origen = str(s.get("origen") or "")
    para_que = _para_que(s) or "No lo ha dicho."
    quien = revisor._QUIEN.get(origen) or (f"{origen}." if origen else "No se sabe (la petición no lo dice).")
    corto = revisor._QUIEN_CORTO.get(origen) or origen or "no se sabe quién"
    tipo = a["tipo"]
    riesgo = RIESGO[tipo] if a["regla"] != "siempre" else "ALTO"
    regla = a["regla"]
    if regla in ("siempre", "resto"):
        recomendacion = f"Decides tú: {a['motivo']}."
        if regla == "siempre" and "secret" in a["motivo"]:
            recomendacion += " Lo normal es decir que NO salvo que sepas para qué es."
        elif tipo == "borra":
            recomendacion += " Di que SÍ solo si hay copia o no te importa perderlo."
        elif tipo == "codigo":
            recomendacion += " Mira el cambio antes de aprobarlo."
        elif para_que == "No lo ha dicho.":
            recomendacion += " No ha dicho para qué: si no lo sabes, di que no (puede volver a pedirlo explicándolo)."
    else:
        recomendacion = _RECOMIENDA[regla]
    sobre = [{"ruta": _tapar(_mostrar(p)), "papel": papel(p)} for p in a["rutas"][:6]]
    si_no = "No se hace."
    vence = str(s.get("vence") or "")[:16]
    if vence and s.get("tipo") != "veto":
        si_no += f" Si no contestas antes del {vence}, cuenta como NO."
    que = _tapar(a["que"])
    ex = {"version": VERSION, "que": que, "para_que": _tapar(para_que), "quien": quien, "quien_corto": corto,
          "sobre": sobre, "tipo": tipo, "tipo_llano": TIPOS[tipo], "deshacer": DESHACER[tipo],
          "riesgo": f"{riesgo}: {TIPOS[tipo].lower()}.", "si_no": si_no, "recomendacion": _tapar(recomendacion),
          "regla": regla, "motivo_regla": _tapar(a["motivo"]),
          "por_que_a_ti": _tapar(a["motivo"]) if regla in ("siempre", "resto") else "",
          "frase": f"{que} Lo pide {corto}. Riesgo: {riesgo}."}
    return ex


def explicacion(s: dict) -> dict:
    """La ficha para pintar: la guardada (con la frase de Qwen si la hay) o, si no hay, la determinista de ahora."""
    guardada = (s.get("extra") or {}).get("explicacion") or {}
    ex = ficha(s) if guardada.get("version") != VERSION else dict(guardada)
    if guardada.get("frase_llana") and guardada.get("version") == VERSION:
        ex["que_original"] = ex["que"]
        ex["que"] = guardada["frase_llana"]
        ex["frase"] = f"{guardada['frase_llana']} Lo pide {ex['quien_corto']}. Riesgo: {ex['riesgo'].split(':')[0]}."
    trib = s.get("tribunal") or {}
    if trib.get("estado") == "bandeja" and trib.get("dictamenes") is not None:
        votos = [d.get("voto") for d in trib.get("dictamenes") or []]
        ex["recomendacion"] = (f"El tribunal no decidió ({trib.get('motivo') or 'sin acuerdo'}): "
                               f"{votos.count('APROBAR')} a favor, {votos.count('VETAR')} en contra. Decides tú.")
        ex["dictamenes"] = [{"quien": d.get("familia") or d.get("id"), "voto": d.get("voto"),
                             "motivo": _tapar(str(d.get("motivo") or ""))} for d in trib.get("dictamenes") or []]
    elif trib.get("estado") == "pendiente" and trib.get("via") == "guardian":
        ex["recomendacion"] = "El tribunal de 3 IAs lo está mirando ahora; si no se ponen de acuerdo, te llegará."
    return ex


# ------------------------------------------------------------------ decidir
def _registrar(s: dict, a: dict, decision: str) -> None:
    _anotar({"cuando": _txt(_ahora()), "id": s.get("id"), "nivel": s.get("nivel"), "accion": s.get("accion"),
             "detalle": _tapar(str(s.get("detalle") or ""))[:200], "regla": a["regla"], "decision": decision,
             "motivo": a["motivo"]})


def permite_revisor(s: dict) -> bool:
    """El revisor de reglas (nucleo/revisor.py) solo puede aprobar si el guardian esta encendido y la solicitud no es
    de las que siempre decide Damian (p. ej. leer memoria/perfil_privado, que el revisor tomaba por lectura)."""
    if not activo():
        return False
    try:
        return analizar(s)["regla"] != "siempre"
    except Exception:   # noqa: BLE001 - ante la duda, a Damian
        return False


def procesar(s: dict, ahora: datetime | None = None) -> dict:
    """Explica una solicitud y, si esta pendiente y el guardian encendido, aplica la regla. Devuelve la solicitud."""
    a = analizar(s)
    ex = ficha(s, a)
    encendido = activo()
    if s.get("estado") != "pendiente":
        decision = "nada"
    elif not encendido and a["regla"] != "r1":
        decision = "apagado"
    else:
        decision = {"solo": "aprobada", "tribunal": "tribunal", "r1": "r1"}.get(a["regla"], "damian")
    if decision == "tribunal" and s.get("tribunal"):
        decision = "tribunal"   # ya estaba con el tribunal (barrido repetido)
    ex["decision_guardian"] = decision
    try:
        s = ap.anotar_explicacion(s["id"], ex)
    except (ap.NoEncontrada, OSError, ValueError):
        return s
    try:
        if decision == "aprobada":
            s = ap.aprobar(s["id"], quien=QUIEN, motivo=a["motivo"], ahora=ahora)
        elif decision == "tribunal" and not s.get("tribunal"):
            s = ap.a_tribunal(s["id"], a["motivo"], ahora=ahora)
    except ap.EstadoInvalido:
        return ap.ver(s["id"])
    if decision != "nada":
        _registrar(s, a, decision)
    return s


def al_solicitar(s: dict) -> dict:
    """Gancho de aprobaciones.solicitar: solo lo determinista (rapido). Qwen y el tribunal van en el proceso de fondo."""
    if not GANCHO:
        return s
    return procesar(s)


def _por_procesar(s: dict) -> bool:
    ex = (s.get("extra") or {}).get("explicacion") or {}
    if ex.get("version") != VERSION:
        return True
    return ex.get("decision_guardian") == "apagado" and activo()


def tribunal_pendientes() -> list[dict]:
    return [s for s in ap.cargar()["solicitudes"] if s["estado"] == "pendiente"
            and (s.get("tribunal") or {}).get("estado") == "pendiente" and s["tribunal"].get("via") == "guardian"]


def _sin_frase(s: dict) -> bool:
    ex = (s.get("extra") or {}).get("explicacion") or {}
    return (s["estado"] == "pendiente" and ex.get("version") == VERSION and not ex.get("frase_llana")
            and not ex.get("frase_intentada") and ex.get("decision_guardian") in ("damian", "apagado", "tribunal"))


def barrer(ahora: datetime | None = None) -> dict:
    """Lo que el gancho no vio (o vio con el guardian apagado) y el tribunal que no contesto a tiempo."""
    ahora = ahora or _ahora()
    ap.caducar(ahora=ahora)
    hechos = {"procesadas": [], "a_damian": []}
    for s in ap.cargar()["solicitudes"]:
        if s["estado"] == "pendiente" and _por_procesar(s):
            procesar(s, ahora)
            hechos["procesadas"].append(s["id"])
    for s in tribunal_pendientes():
        try:
            desde = datetime.strptime(s["tribunal"].get("desde") or "", ap.FORMATO)
        except ValueError:
            desde = ahora - ESPERA_TRIBUNAL
        if ahora - desde >= ESPERA_TRIBUNAL:
            try:
                ap.registrar_tribunal(s["id"], "bandeja", [], f"el tribunal no contestó en "
                                      f"{int(ESPERA_TRIBUNAL.total_seconds() // 60)} min: decides tú", ahora=ahora)
                hechos["a_damian"].append(s["id"])
            except ap.EstadoInvalido:
                pass
    return hechos


def hay_trabajo_de_fondo() -> bool:
    return bool(tribunal_pendientes()) or any(_sin_frase(s) for s in ap.cargar()["solicitudes"])


def _vivo(pid: int) -> bool:
    from nucleo import planificador
    return planificador._vivo(pid)


def barrido_si_toca(ahora: datetime | None = None, lanzar=None) -> str | None:
    """Lo llama el tick del planificador (cada 20 s): como mucho una pasada por minuto. Si queda tribunal o frases
    de Qwen, lanza `python -m nucleo.guardian trabajar` en un proceso aparte (uno cada vez)."""
    ahora = ahora or _ahora()
    with bloqueo(CANDADO):
        est = _leer_estado()
        try:
            ultimo = datetime.strptime(str(est.get("barrido") or ""), ap.FORMATO)
        except ValueError:
            ultimo = None
        if ultimo is not None and timedelta(0) <= ahora - ultimo < CADA_BARRIDO:
            return None
        est["barrido"] = _txt(ahora)
        escribir_atomico(ESTADO, json.dumps(est, ensure_ascii=False, indent=1) + "\n")
    hechos = barrer(ahora)
    txt = f"guardian: {len(hechos['procesadas'])} vistas, {len(hechos['a_damian'])} del tribunal a Damian"
    if not hay_trabajo_de_fondo():
        return txt
    pid = int(est.get("pid") or 0)
    if pid and _vivo(pid):
        return txt + f"; trabajo de fondo en marcha (pid {pid})"
    lanzar = lanzar or LANZADOR or (lambda: subprocess.Popen(
        [str(PYTHON), "-m", "nucleo.guardian", "trabajar"], cwd=str(RAIZ), stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).pid)
    nuevo = lanzar()
    with bloqueo(CANDADO):
        est = _leer_estado()
        est.update(pid=nuevo, lanzado=_txt(ahora))
        escribir_atomico(ESTADO, json.dumps(est, ensure_ascii=False, indent=1) + "\n")
    return txt + f"; lanzado el trabajo de fondo (pid {nuevo})"


# ------------------------------------------------------------------ proceso de fondo: tribunal y Qwen
def juzgar(s: dict, limite: float | None = None) -> dict:
    """Pasa UNA solicitud AMBAR o R2 por el tribunal de 3 familias (solo API) y aplica el resultado."""
    from nucleo import auditor
    from nucleo import tareas as T
    from nucleo import tribunal_r1 as R
    if s.get("nivel") == "R2":
        extra = s.get("extra") or {}
        tarea = T.buscar(extra.get("tarea", "")) if extra.get("tarea") else None
        texto = R.prompt_fusion(tarea, extra) if tarea else ""
    else:
        texto = R.prompt_aprobacion(s, explicacion(s))
    texto = auditor.tapar(texto)
    if not texto:
        dicts, motivo, resultado = [], "no encuentro la tarea de esta R2: decides tú", "bandeja"
    elif auditor.motivos_privados(texto):
        dicts, resultado = [], "bandeja"
        motivo = "tiene datos privados que no pueden salir del PC: decides tú"
    else:
        dicts, fallos = R._reunir({}, limite, texto, web=False)
        resultado, motivo = R.decidir(dicts)
        if fallos and resultado == "bandeja" and len(dicts) < 3:
            motivo += "; fallos: " + ", ".join(f["id"] for f in fallos)
    try:
        r = ap.registrar_tribunal(s["id"], resultado, dicts, motivo)
    except ap.EstadoInvalido:
        return ap.ver(s["id"])
    _anotar({"cuando": _txt(_ahora()), "id": s["id"], "nivel": s.get("nivel"), "accion": s.get("accion"),
             "regla": "tribunal", "decision": {"aprobar": "aprobada", "vetar": "denegada"}.get(resultado, "damian"),
             "motivo": motivo})
    return r


def _qwen(prompt: str) -> str:
    """Una llamada a Ollama local. '' si no esta, si hay OTRO modelo cargado (un modelo cada vez) o si falla."""
    try:
        import httpx
        cargados = [m.get("name", "") for m in httpx.get(f"{URL_OLLAMA}/api/ps", timeout=2).json().get("models", [])]
        if any(n and n != MODELO_QWEN for n in cargados):
            return ""
        r = httpx.post(f"{URL_OLLAMA}/api/chat", timeout=TIMEOUT_QWEN, json={
            "model": MODELO_QWEN, "stream": False, "think": False, "keep_alive": 0,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"num_ctx": NUM_CTX, "num_predict": NUM_PREDICT, "temperature": 0.2}})
        if r.status_code != 200:
            return ""
        return ((r.json().get("message") or {}).get("content") or "").strip()
    except Exception:   # noqa: BLE001 - sin Qwen se queda la frase determinista
        return ""


def prompt_frase(s: dict, ex: dict) -> str:
    sobre = "; ".join(f"{x['ruta']} ({x['papel']})" for x in ex.get("sobre") or []) or "-"
    return _tapar(
        "Explica en UNA frase corta en español llano (máximo 25 palabras), para alguien que no programa, qué quiere "
        "hacer esta petición en su ordenador. Sin código, sin rutas completas, sin números de petición. Empieza por "
        "un verbo en infinitivo.\n"
        f"Acción: {s.get('accion')}\nOrden exacta: {str(s.get('detalle') or '')[:500]}\nTipo: {ex.get('tipo_llano')}\n"
        f"Sobre: {sobre}\nDescripción automática: {ex.get('que')}\nFrase:")


def _limpiar(texto: str) -> str:
    t = " ".join(str(texto or "").replace("\n", " ").split()).strip(" \"'«»")
    if len(t) < 12 or len(t) > 220:
        return ""
    return t if t.endswith((".", "!", "?")) else t + "."


def redactar(s: dict) -> str:
    """Frase de Qwen para una solicitud que espera a Damian; se guarda en extra.explicacion.frase_llana."""
    guardada = (s.get("extra") or {}).get("explicacion") or {}
    ex = dict(guardada) if guardada.get("version") == VERSION else ficha(s)
    frase = _tapar(_limpiar(_qwen(prompt_frase(s, ex))))
    ex["frase_intentada"] = _txt(_ahora())
    if frase:
        ex["frase_llana"] = frase
    try:
        ap.anotar_explicacion(s["id"], ex)
    except (ap.NoEncontrada, OSError):
        pass
    return frase


def trabajar(limite_s: float = 900.0) -> dict:
    """Proceso de fondo: primero el tribunal (alguien espera para seguir), luego las frases de Qwen."""
    limite = time.time() + limite_s
    hechos = {"tribunal": {}, "frases": 0}
    for s in tribunal_pendientes()[:MAX_TRIBUNAL]:
        if time.time() > limite:
            break
        r = juzgar(s, limite)
        hechos["tribunal"][s["id"]] = (r.get("tribunal") or {}).get("resultado") or r["estado"]
    for s in [x for x in ap.cargar()["solicitudes"] if _sin_frase(x)][:MAX_QWEN]:
        if time.time() > limite:
            break
        hechos["frases"] += 1 if redactar(s) else 0
    return hechos


# ------------------------------------------------------------------ para el Centro
def para_damian(solicitudes: list[dict]) -> list[dict]:
    """Quita lo que el tribunal del guardian aun esta mirando (no es de Damian todavia)."""
    return [s for s in solicitudes if not ((s.get("tribunal") or {}).get("estado") == "pendiente"
                                           and s["tribunal"].get("via") == "guardian")]


def resueltos_desde(desde: datetime, maximo: int = 50) -> list[dict]:
    """Permisos que ha resuelto NEXO (guardian, tribunal o revisor de reglas) desde `desde`, lo mas reciente antes."""
    salida = []
    for s in ap.cargar()["solicitudes"]:
        for e in reversed(s.get("eventos") or []):
            if e.get("tipo") in ("aprobada", "denegada") and e.get("quien") in NEXO_DECIDE:
                if e.get("cuando", "") >= _txt(desde):
                    ex = explicacion(s)
                    salida.append({"id": s["id"], "cuando": e["cuando"], "aprobada": e["tipo"] == "aprobada",
                                   "quien": NEXO_DECIDE[e["quien"]], "que": ex["que"], "motivo": _tapar(e.get("motivo") or ""),
                                   "enlace": f"/aprobacion/{s['id']}"})
                break
    salida.sort(key=lambda x: x["cuando"], reverse=True)
    return salida[:maximo]


# ------------------------------------------------------------------ CLI
def _cli(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    orden = argv[0] if argv else "estado"
    if orden == "estado":
        print(f"Guardian {'ENCENDIDO' if activo() else 'APAGADO'}; tribunal pendiente: "
              f"{[s['id'] for s in tribunal_pendientes()]}")
        for d in decisiones(10):
            print(f"{d.get('cuando')} {d.get('id', '')} {d.get('decision', d.get('evento', ''))}: {d.get('motivo', '')}")
    elif orden == "explicar" and len(argv) > 1:
        s = ap.ver(argv[1])
        print(json.dumps({**explicacion(s), "_analisis": analizar(s)["regla"]}, ensure_ascii=False, indent=1,
                         default=str))
    elif orden == "barrer":
        print(barrer())
    elif orden == "trabajar":
        print(trabajar())
    elif orden in ("activar", "desactivar"):
        poner_activo(orden == "activar", quien="cli")
        print(f"Guardian {'ENCENDIDO' if orden == 'activar' else 'APAGADO'}.")
    else:
        print(__doc__.split("CLI:")[1])
        return 1
    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    sys.exit(_cli(sys.argv[1:]))
