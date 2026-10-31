"""Revisor de acciones ambar, fase F1 de T154: solo reglas, sin modelo.

Por que existe esto
-------------------
Con NEXO trabajando solo, cada ambar para el trabajo hasta que Damian
contesta. Muchas son obvias. El revisor despacha lo obvio y le deja a
Damian solo lo dudoso. Diseno completo: documentacion/T154_REVISOR_AMBAR.md.

F1 es deliberadamente tonta: reglas fijas en codigo (no en config, para
que cambiarlas pida un diff) y ningun modelo. Tres respuestas posibles:

- permitir: SOLO si la accion encaja ENTERA en la lista blanca;
- preguntar: todo lo demas (lo decide Damian);
- denegar: F1 no deniega nunca. Lo rojo ya lo corta nucleo/permisos.py
  antes de llegar aqui, y denegar por reglas lo ambar seria pisar a Damian.

Asimetria: la lista "nunca auto" se mira ANTES que la blanca. Si una
accion encaja en las dos (no deberia), gana preguntar.

Damian 05/10 (solo le llega lo suyo, y explicado):
- lo que SOLO LEE (Get-Content, Select-String, git log/diff/show/status,
  schtasks /Query, GET a este PC...) se permite aunque nombre un blindado;
  no cuenta para el disyuntor y pasa aunque este abierto. Secretos, nunca;
- cada decision queda en memoria/revisor_decisiones.jsonl (tambien las que
  pasan a Damian), ademas del historial encadenado de la cola;
- explicar(): que se quiere hacer, para que, quien lo pide, riesgo y que
  pasa si dice que no, para la web (Bandejas, Centro) y el push.

Disyuntor
---------
Si el agente entra en bucle (5 peticiones del mismo origen en 10 min) el
disyuntor se abre y el revisor deja de permitir nada: todo a Damian.
Solo Damian lo cierra (`python -m nucleo.revisor cerrar`). No se cierra
solo con el tiempo, a proposito. En F2 (con modelo) tambien se abrira
con 3 denegaciones o 3 fallos del modelo seguidos.

No esta enganchado a nada: el punto de enganche es manos/servidor_mcp.py
(blindado), despues de N04.patch. Ver el documento de diseno, seccion 5.

CLI:
    python -m nucleo.revisor estado
    python -m nucleo.revisor cerrar
    python -m nucleo.revisor abrir [motivo]
    python -m nucleo.revisor decisiones [n]
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

from nucleo import aprobaciones
from nucleo.candado import bloqueo
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico


ESTADO = RAIZ / "memoria" / "revisor_estado.json"
CANDADO = RAIZ / "memoria" / ".candado_revisor.lock"

BUCLE_PETICIONES = 5
BUCLE_VENTANA = timedelta(minutes=10)

FORMATO = aprobaciones.FORMATO
QUIEN = "revisor:reglas"


def _re(p: str) -> re.Pattern:
    return re.compile(p, re.IGNORECASE)


# Nunca se permite solo, pase lo que pase. Defensa en profundidad: la lista
# blanca ya es estrecha, pero si alguien la ensancha mal, esto sigue parando.
# Las NUNCA_AUTO_SIEMPRE primeras paran tambien lo que solo lee; las demas no:
# leer un blindado o consultar una tarea programada no cambia nada (Damian 05/10).
NUNCA_AUTO_SIEMPRE = 4
NUNCA_AUTO = (
    (_re(r"\bgit\s+push\b"), "git push: en el PC subiria el historial privado (CLAUDE.md)"),
    (_re(r"secretos|\.env\b|token|password|contrase|credential|clipboard"), "toca secretos"),
    (_re(r"https?://\S+\.(exe|msi|ps1|bat|cmd|scr)\b"), "descarga un ejecutable"),
    (_re(r"set-executionpolicy|set-mppreference|setx\b|localuser|localgroup"), "cambia el sistema"),
    (_re(r"nucleo[\\/](permisos|instancia|config|aprobaciones|revisor)\.py|manos[\\/]"), "archivo blindado"),
    (_re(r"aprobaciones(_historial|_latido)?\.json|revisor_(estado|decisiones)\.json"), "estado de control"),
    (_re(r"schtasks|scheduledtask|new-service|\\run\b|startup"), "se queda en el arranque"),
)

# Lo unico que se permite solo. fullmatch: la accion ENTERA tiene que ser
# esto, sin nada detras (ni `;`, ni `|`, ni argumentos de mas).
_PY = r"(?:\.venv[\\/]Scripts[\\/]python\.exe|python)"
LISTA_BLANCA = (
    (
        "ejecutar comando",
        _re(rf"(?:{_PY}\s+-m\s+)?pip\s+install\s+(?:-q\s+|--quiet\s+)?-r\s+(?:requisitos\.txt|requirements-interfaz\.txt)"),
        "instala las dependencias fijadas del propio repo",
    ),
)


# ------------------------------------------------------- solo lectura
#
# Damian 05/10: lo que solo LEE no le llega aunque nombre un blindado
# (Get-Content nucleo\permisos.py | Select-Object -First 40). permisos.py
# (blindado) solo da por verde una linea simple de ordenes inertes; lo demas
# llega aqui y se mira con reglas propias, de lista blanca: cada orden de la
# linea tiene que ser de las que solo leen, y cualquier cosa rara (escapes,
# .NET, redirecciones, rutas fuera del repo, asignar propiedades, metodos
# que no sean de texto) devuelve "no es lectura" y sigue el camino normal.

ORDENES_LECTURA = frozenset({
    "cat", "type", "gc", "dir", "ls", "gci", "gi", "sls", "findstr", "echo",
    "select", "sort", "measure", "where", "?", "%", "ft", "fl", "fw", "group", "compare", "diff",
    "select-object", "sort-object", "measure-object", "where-object", "foreach-object", "group-object",
    "compare-object", "select-string", "format-table", "format-list", "format-wide", "format-hex",
    "out-string", "out-null", "write-output", "write-host", "test-path", "resolve-path", "join-path",
    "split-path", "convertfrom-json", "convertto-json", "convertfrom-csv",
})
# Get-* es "obtener" por convencion de PowerShell; estos no.
GET_NO = frozenset({"get-credential", "get-clipboard", "get-secret", "get-secretinfo", "get-storedcredential"})
CLAVES_PS = frozenset({"if", "else", "elseif", "foreach", "try", "catch", "finally", "in"})
GIT_LECTURA = frozenset({"log", "diff", "show", "status", "blame", "rev-parse", "ls-files", "shortlog",
                         "describe", "cat-file", "ls-tree"})
WEB_LOCAL = frozenset({"invoke-webrequest", "invoke-restmethod", "iwr", "irm", "curl"})
METODOS_TEXTO = frozenset({"tostring", "trim", "trimend", "trimstart", "substring", "split", "replace",
                           "contains", "startswith", "endswith", "tolower", "toupper", "indexof",
                           "lastindexof", "padleft", "padright", "getvalue"})

_REDIR_INOCUA = re.compile(r"\s*(?:2>&1|[2*]?>\s*\$null)", re.IGNORECASE)
_RARO = re.compile(r"`|@['\"]|::|\$env:|\b(?:env|hk\w*|cert|variable|function|wsman):", re.IGNORECASE)
_RUTA_ABS = re.compile(r"(?<![\w/])(?:[a-z]:[\\/]|\\\\)[^\s'\";|,)]*", re.IGNORECASE)
_METODO = re.compile(r"\.([a-z_]\w*)\s*\(", re.IGNORECASE)
_IGUAL_OK = re.compile(r"(?:\$\w+\s*\+?|--[\w-]+)$")
_SEPARADOR = re.compile(r"[;|{(\n]")
_URL = re.compile(r"https?://([^/\s'\":]+)", re.IGNORECASE)
_WEB_ESCRIBE = re.compile(r"\s-(?:method\s+(?!get\b)|body\b|outfile\b|infile\b|x\s|d\s|o\s|t\s|f\s)|--(?:data|output|upload|form)",
                          re.IGNORECASE)


def _quitar_cadenas(cmd: str) -> str | None:
    """Vacia las cadenas: '...' es literal; "..." tambien salvo $(...), que se deja para mirarlo.
    None si hay comillas sin cerrar."""

    cmd = re.sub(r"'[^']*'", "''", cmd)

    def doble(m: re.Match) -> str:
        dentro = m.group(1)
        if "$(" not in dentro:
            return '""'
        # Solo lo que va de la primera $( al ultimo ): el texto de alrededor no se ejecuta.
        return '"" ' + dentro[dentro.index("$(") + 1:dentro.rindex(")") + 1] + " "

    cmd = re.sub(r'"([^"]*)"', doble, cmd)

    return None if ("'" in cmd.replace("''", "") or '"' in cmd.replace('""', "")) else cmd


def no_es_lectura(cmd: str) -> str | None:
    """None si la linea entera solo lee; si no, el motivo (para el registro)."""

    from nucleo.config import RAIZ as raiz

    if _RARO.search(cmd):
        return "escapes, .NET, variables de entorno o unidades especiales"
    if ".." in cmd or re.search(r"(?:^|\s)~", cmd):
        return "ruta relativa fuera del repo"
    base = str(raiz).lower().rstrip("\\/")
    for r in _RUTA_ABS.findall(cmd):
        if not r.lower().replace("/", "\\").startswith(base.replace("/", "\\")):
            return f"ruta fuera del repo: {r[:60]}"
    if re.search(r"-membername\b", cmd, re.IGNORECASE):
        return "ForEach-Object -MemberName llama a metodos"

    limpio = _quitar_cadenas(_REDIR_INOCUA.sub(" ", cmd))
    if limpio is None:
        return "comillas sin cerrar"
    if re.search(r"[<>&]", limpio):
        return "redireccion o llamada con &"
    for m in re.finditer(r"(?<![=!<>])=(?!=)", limpio):
        if not _IGUAL_OK.search(limpio[:m.start()]):
            return "asigna algo que no es una variable simple"
    for metodo in _METODO.findall(limpio):
        if metodo.lower() not in METODOS_TEXTO:
            return f"llama al metodo {metodo}"

    web = False
    trozos = _SEPARADOR.split(re.sub(r"(\$\w+\s*\+?)=", r"\1;", limpio))
    for trozo in trozos:
        palabras = trozo.split()
        if not palabras:
            continue
        primera = palabras[0].lower().lstrip("})")
        if not primera or primera[0] in "$-[0123456789\"'})+,!" or primera in CLAVES_PS:
            continue
        if primera.endswith(".exe"):
            primera = primera[:-4]
        if primera in ("%", "foreach-object") and len(palabras) > 1 and not palabras[1].lower().startswith(
                ("-process", "-begin", "-end")):
            return "ForEach-Object sin bloque llama a metodos"
        if primera == "git":
            resto = [p for p in palabras[1:] if p.lower() != "--no-pager"]
            if not resto or resto[0].lower() not in GIT_LECTURA:
                return f"git {resto[0] if resto else ''} no es de lectura".strip()
            if any(p.lower().startswith(("--output", "--ext-diff", "--textconv")) for p in resto):
                return "git con --output o programas externos"
            continue
        if primera == "schtasks":
            if [p.lower() for p in palabras[1:2]] != ["/query"] or re.search(
                    r"/(create|delete|change|run|end)\b", trozo, re.IGNORECASE):
                return "schtasks que no es /Query"
            continue
        if primera in WEB_LOCAL:
            web = True
            continue
        if primera in ORDENES_LECTURA or (primera.startswith("get-") and primera not in GET_NO):
            continue
        return f"'{palabras[0][:40]}' no es una orden de solo lectura"

    if web:
        hosts = {h.lower() for h in _URL.findall(cmd)}
        if not hosts or not hosts <= {"localhost", "127.0.0.1", "[::1]"}:
            return "consulta web fuera de este PC"
        if _WEB_ESCRIBE.search(cmd):
            return "consulta web que envia o guarda datos"

    return None


@dataclass(frozen=True)
class Veredicto:
    decision: str   # permitir | preguntar | denegar
    riesgo: int     # 1-5
    motivo: str
    fuente: str     # que regla (o el disyuntor) decidio


# ------------------------------------------------------------ disyuntor

def _ahora() -> datetime:
    return datetime.now().replace(microsecond=0)


def cargar_estado() -> dict:
    """Si el archivo esta roto, se trata como ABIERTO: ante la duda, a Damian."""

    if not ESTADO.is_file():
        return {"abierto": False, "motivo": "", "desde": None, "recientes": []}

    try:
        datos = json.loads(ESTADO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"abierto": True, "motivo": "estado del revisor ilegible", "desde": None, "recientes": []}

    datos.setdefault("abierto", False)
    datos.setdefault("recientes", [])

    return datos


def _guardar(datos: dict) -> None:
    escribir_atomico(ESTADO, json.dumps(datos, ensure_ascii=False, indent=2) + "\n")


def abrir(motivo: str, ahora: datetime | None = None) -> dict:
    ahora = ahora or _ahora()

    with bloqueo(CANDADO):
        datos = cargar_estado()
        datos.update(abierto=True, motivo=motivo, desde=ahora.strftime(FORMATO))
        _guardar(datos)

        return datos


def cerrar() -> dict:
    """Solo Damian. Vacia tambien el contador de bucle."""

    with bloqueo(CANDADO):
        datos = {"abierto": False, "motivo": "", "desde": None, "recientes": []}
        _guardar(datos)

        return datos


def _anotar_peticion(origen: str, ahora: datetime) -> dict:
    """Cuenta la peticion y abre el disyuntor si el mismo origen esta en bucle."""

    with bloqueo(CANDADO):
        datos = cargar_estado()
        limite = ahora - BUCLE_VENTANA

        recientes = [
            (o, t) for o, t in datos.get("recientes", [])
            if datetime.strptime(t, FORMATO) > limite
        ]
        recientes.append((origen, ahora.strftime(FORMATO)))
        datos["recientes"] = recientes

        if not datos["abierto"] and sum(1 for o, _ in recientes if o == origen) >= BUCLE_PETICIONES:
            datos.update(
                abierto=True,
                motivo=f"{BUCLE_PETICIONES} peticiones de '{origen}' en {BUCLE_VENTANA}: posible bucle",
                desde=ahora.strftime(FORMATO),
            )

        _guardar(datos)

        return datos


# ------------------------------------------------------------- revisar

def _lectura(solicitud: dict) -> Veredicto | None:
    """Damian 05/10: lo que solo lee se permite aunque nombre un blindado. Los secretos, nunca."""

    if solicitud.get("nivel", "ambar") != "ambar" or solicitud.get("accion") != "ejecutar comando":
        return None

    detalle = solicitud.get("detalle", "")
    texto = f"{solicitud.get('accion', '')} {detalle}"

    if any(patron.search(texto) for patron, _ in NUNCA_AUTO[:NUNCA_AUTO_SIEMPRE]):
        return None
    if no_es_lectura(detalle) is not None:
        return None

    return Veredicto("permitir", 1, "solo lee (no cambia nada)", "solo_lectura")


def revisar(solicitud: dict, estado: dict | None = None) -> Veredicto:
    """Solo decide; no toca la cola ni el disco."""

    # Leer no se para ni con el disyuntor abierto: un bucle que solo lee no rompe nada.
    lectura = _lectura(solicitud)
    if lectura is not None:
        return lectura

    estado = estado if estado is not None else cargar_estado()
    accion = solicitud.get("accion", "")
    detalle = solicitud.get("detalle", "")

    if estado.get("abierto"):
        return Veredicto("preguntar", 3, f"disyuntor abierto: {estado.get('motivo', '')}", "disyuntor")

    if solicitud.get("nivel", "ambar") != "ambar":
        return Veredicto("preguntar", 5, "no es ambar: el revisor no lo mira", "nivel")

    texto = f"{accion} {detalle}"

    for patron, motivo in NUNCA_AUTO:
        if patron.search(texto):
            return Veredicto("preguntar", 4, motivo, f"nunca_auto:{patron.pattern[:40]}")

    for accion_ok, patron, motivo in LISTA_BLANCA:
        if accion == accion_ok and patron.fullmatch(detalle.strip()):
            return Veredicto("permitir", 1, motivo, f"lista_blanca:{motivo}")

    motivo = no_es_lectura(detalle) if accion == "ejecutar comando" else ""
    return Veredicto("preguntar", 3, "cambia algo y no esta en la lista blanca"
                     + (f" ({motivo})" if motivo else ""), "por_defecto")


def _ruta_registro():
    # Junto al estado: los tests que lo mueven a tmp_path se llevan tambien el registro.
    return ESTADO.with_name("revisor_decisiones.jsonl")


def _registrar(solicitud: dict, v: Veredicto, ahora: datetime) -> None:
    """(b) Damian 05/10: cada decision del revisor queda escrita, tambien las que pasan a Damian."""

    linea = {"cuando": ahora.strftime(FORMATO), "id": solicitud.get("id"), "origen": solicitud.get("origen"),
             "accion": solicitud.get("accion"), "detalle": str(solicitud.get("detalle") or "")[:300],
             "decision": "a Damian" if v.decision == "preguntar" else v.decision,
             "riesgo": v.riesgo, "motivo": v.motivo, "fuente": v.fuente}
    try:
        with _ruta_registro().open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")
    except OSError:
        pass  # el registro nunca para el trabajo; la decision ya esta en el historial de la cola


def decisiones(n: int = 50) -> list[dict]:
    try:
        lineas = _ruta_registro().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for l in lineas[-n:]:
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def procesar(solicitud: dict, ahora: datetime | None = None) -> Veredicto:
    """Revisa una solicitud recien dada de alta y actua sobre la cola.

    permitir -> aprobaciones.aprobar(quien="revisor:reglas"); queda en el
    historial encadenado quien lo decidio. preguntar -> no toca nada: sigue
    pendiente para Damian. Si la solicitud ya no esta pendiente, no hace nada.
    Cada decision va tambien a memoria/revisor_decisiones.jsonl.
    """

    ahora = ahora or _ahora()
    v = _lectura(solicitud)

    # T1020: el guardian manda. Apagado (Ajustes), el revisor tampoco aprueba nada; y lo que siempre decide Damian
    # (p. ej. leer memoria/perfil_privado, que aqui pasaba por lectura) no lo aprueba el revisor.
    from nucleo import guardian
    if not guardian.permite_revisor(solicitud):
        v = Veredicto("preguntar", 4, "el guardián lo deja a Damián (apagado o es de los que siempre decide él)",
                      "guardian")
        _registrar(solicitud, v, ahora)
        return v

    if v is None:  # lo que solo lee no cuenta para el disyuntor de bucle
        estado = _anotar_peticion(solicitud.get("origen") or "desconocido", ahora)
        v = revisar(solicitud, estado)

    if v.decision == "permitir" and solicitud.get("estado") == "pendiente":
        try:
            aprobaciones.aprobar(solicitud["id"], quien=QUIEN, motivo=v.motivo, ahora=ahora)
        except aprobaciones.EstadoInvalido:
            v = Veredicto("preguntar", 3, "la solicitud ya no estaba pendiente", "cola")

    _registrar(solicitud, v, ahora)

    return v


# --------------------------------------------- (c) explicar a Damian
#
# Damian 05/10: lo que de verdad le llega trae, en la web y en el push, que se
# quiere hacer, para que, quien lo pide, que riesgo tiene y que pasa si dice
# que no. Sin modelo: tabla fija de casos conocidos. Lo que no esta en la
# tabla se dice tal cual ("no se sabe para que: si no lo sabes, deniega").

_CASOS = (
    # (patron sobre "accion detalle", que, para que, riesgo, si dice que no)
    (_re(r"\bgit\s+push\b"), "Subir código de NEXO a GitHub.",
     "Publicar cambios fuera del PC.",
     "ALTO: el historial local tiene datos privados; lo correcto es publicar_nube.py, no git push.",
     "No se sube nada. Lo normal es decir que NO."),
    # T230 (Centro v2): un commit guarda en el historial; antes un "git add ...; git commit ..." caia en "parche" por
    # nombrar un .patch en el mensaje. Si ademas hay un git apply de verdad, manda el parche (el caso siguiente).
    (_re(r"(?s)^(?!.*\bgit\s+apply\b)(?=.*\bgit\s+commit\b)"), "Guardar en el historial (git) un cambio.",
     "Dejar anotado en el repositorio de NEXO un cambio ya hecho en los archivos.",
     "BAJO: queda en el historial local y se puede deshacer; no sube nada fuera del PC.",
     "El cambio queda sin guardar en el historial; los archivos siguen como estén."),
    (_re(r"\bgit\s+apply\b|\.patch\b"), "Aplicar un parche (un cambio de código ya escrito y guardado en un archivo).",
     "Meter en NEXO un cambio que se preparó antes como propuesta.",
     "MEDIO: cambia código; si toca un archivo de control, cambia lo que NEXO puede hacer solo.",
     "El parche no se aplica y el cambio sigue esperando como propuesta."),
    (_re(r"\bgit\s+(checkout|restore|reset)\b"), "Deshacer cambios de un archivo y dejarlo como en el último commit.",
     "Volver a un estado limpio antes de otro paso.",
     "MEDIO: lo que no estuviera guardado en un commit se pierde.",
     "El archivo se queda como está."),
    (_re(r"\b(pip|npm|choco|scoop)\s+(install|uninstall)\b|\bwinget\b"), "Instalar o quitar programas o librerías.",
     "Que una pieza de NEXO tenga lo que necesita para funcionar.",
     "MEDIO: entra código de fuera en el PC.",
     "No se instala nada; la pieza que lo necesitaba sigue sin funcionar."),
    (_re(r"invoke-webrequest|invoke-restmethod|\b(iwr|irm|curl|wget)\b|downloadfile|bitstransfer"),
     "Conectarse a una web desde el PC (consultar o descargar).",
     "Comprobar algo en internet o traerse un archivo.",
     "MEDIO: si descarga algo, ese archivo entra en el PC.",
     "No se conecta a nada."),
    (_re(r"schtasks|scheduledtask|new-service|\\run\b|startup"),
     "Crear o cambiar algo que se arranca solo con Windows (tarea programada o servicio).",
     "Que algo de NEXO se ejecute solo a ciertas horas o al encender.",
     "ALTO: se queda funcionando aunque nadie lo mire.",
     "No se programa nada."),
    (_re(r"set-executionpolicy|set-mppreference|setx\b|localuser|localgroup"),
     "Cambiar la configuración de Windows (seguridad, usuarios o variables del sistema).",
     "No lo dice la petición.", "ALTO: afecta a todo el PC, no solo a NEXO.", "Windows se queda como está."),
    (_re(r"nucleo[\\/](permisos|instancia|config|aprobaciones|revisor)\.py|manos[\\/]|guardia_python|settings\.json"),
     "Cambiar un archivo de control de NEXO (permisos, aprobaciones o sus «manos»).",
     "Mejorar o arreglar las reglas de lo que NEXO puede hacer solo.",
     "ALTO: un agente que cambia sus propias reglas puede quitarse límites. Mira el diff antes.",
     "El archivo de control no cambia."),
    (_re(r"^lanzar proceso"), "Arrancar un programa que se queda funcionando en segundo plano.",
     "No lo dice la petición.", "MEDIO: sigue funcionando después.", "No se arranca."),
    (_re(r"^ejecutar python"), "Ejecutar un script de Python.", "No lo dice la petición.",
     "MEDIO: el script puede hacer cualquier cosa que su código diga.", "No se ejecuta."),
    (_re(r"^(escribir|archivar)"), "Escribir o archivar un archivo.", "No lo dice la petición.",
     "MEDIO: cambia archivos.", "El archivo no cambia."),
)

_QUIEN = {
    "mcp": "Claude (una sesión, el coordinador u otra, que usa las «manos» de NEXO desde fuera).",
    "chat_tarea": "Tú, desde el chat de una tarea.",
}
# Version corta para "Lo pide ..." (Centro v2: «Lo pide Claude»).
_QUIEN_CORTO = {"mcp": "Claude", "chat_tarea": "tú, desde el chat de una tarea"}


def explicar(s: dict) -> dict:
    """Explicacion en lenguaje claro de una solicitud de la cola (para la web y el push)."""

    accion = str(s.get("accion") or "")
    detalle = str(s.get("detalle") or "")
    texto = f"{accion} {detalle}"
    extra = s.get("extra") or {}
    origen = str(s.get("origen") or "")

    que, para_que, riesgo, si_no = (f"{accion}.", "No lo dice la petición.",
                                    "Sin clasificar: el revisor no lo reconoce.", "No se hace.")
    for patron, *caso in _CASOS:
        if patron.search(texto):
            que, para_que, riesgo, si_no = caso
            break

    if extra.get("para_que") or extra.get("resumen"):
        para_que = str(extra.get("para_que") or extra.get("resumen"))
    if para_que == "No lo dice la petición.":
        para_que += " Si no sabes para qué es, di que no: quien lo pidió puede volver a pedirlo explicándolo."

    quien = _QUIEN.get(origen) or (f"{origen}." if origen else "No se sabe (la petición no lo dice).")
    corto = _QUIEN_CORTO.get(origen) or origen or "no se sabe quién"
    vence = str(s.get("vence") or "")[:16]
    if vence:
        si_no += f" Si no contestas antes del {vence}, cuenta como NO."

    try:
        por_que = revisar(s, estado={"abierto": False}).motivo
    except Exception:
        por_que = ""

    return {"que": que, "para_que": para_que, "quien": quien, "quien_corto": corto, "riesgo": riesgo, "si_no": si_no,
            "por_que_a_ti": por_que,
            "frase": f"{que} Lo pide {corto}. Riesgo: {riesgo.split(':')[0]}."}


# ------------------------------------------------------------------ CLI

def main(argv: list[str]) -> int:
    orden = argv[0] if argv else "estado"

    if orden == "estado":
        d = cargar_estado()
        print(f"Disyuntor {'ABIERTO' if d['abierto'] else 'cerrado'}"
              + (f" desde {d.get('desde')}: {d.get('motivo')}" if d["abierto"] else ""))
    elif orden == "cerrar":
        cerrar()
        print("Disyuntor cerrado.")
    elif orden == "abrir":
        abrir(" ".join(argv[1:]) or "abierto a mano")
        print("Disyuntor abierto.")
    elif orden == "decisiones":
        for d in decisiones(int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 20):
            print(f"{d['cuando']} {d.get('id')} {d['decision']:9} {d['motivo'][:60]} | {d['detalle'][:70]}")
    else:
        print(__doc__.split("CLI:")[1])
        return 1

    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    sys.exit(main(sys.argv[1:]))
