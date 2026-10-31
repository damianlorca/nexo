"""Extremidad: navegador por CDP.

Rescatado de lo que ya funcionaba en pruebas/: Playwright NO abre su
propio Chrome, se engancha por CDP a una instancia aparte con tu
sesion ya iniciada. Es lo que menos se parece a un robot y lo unico
que aguanto en pie.

Reglas de uso, acordadas y no negociables:
- Nunca con la cuenta principal de Google. Cuenta secundaria.
- Volumen bajo, con pausas, nunca en bucle desatendido.
- Si sale un captcha o un bloqueo, se para y se avisa. No se evade.

Verificado en vivo el 12/09/2026 con Gemini y ChatGPT (cuenta
nexoclaude@sepio.net, autenticada en ambos sitios en el perfil
chrome-perfil): preguntar(sitio, prompt) responde de verdad en los
dos.

Historial de la extraccion de texto (para no repetir el tanteo):
1ª version: asumia que "antes" (texto de la pagina justo antes de
enviar) era un prefijo EXACTO de "ultimo" (texto tras la respuesta) y
cortaba con len(antes). En la practica la pagina cambia un poco al
enviar y eso desplazaba el corte, colando un trozo de la etiqueta
"Gemini ha dicho" partida por la mitad.
2ª version (esta): calcula el prefijo comun real en vez de asumir la
longitud, y ademas corta por la ULTIMA aparicion de tu propio prompt
dentro del texto nuevo (Gemini/ChatGPT reescriben tu mensaje en
pantalla antes de responder) — todo lo que hay DESPUES de esa ultima
aparicion es turno de la IA. Luego quita la etiqueta de turno
("Gemini ha dicho"/"ChatGPT ha dicho") si queda como primera linea,
el pie fijo de disclaimer (busqueda case-insensitive, cada sitio lo
redacta distinto: "Gemini no es humano. Puede cometer errores" vs
"ChatGPT puede cometer errores. Considera verificar...") si aparece,
y la insignia de modelo (p.ej. "Flash") si queda suelta al final tras
2+ lineas en blanco.

ChatGPT (12/09): en una cuenta recien estrenada, ChatGPT muestra un
anuncio/tour a pantalla completa ("La creacion de imagenes ha
mejorado enormemente" o similar) que intercepta los clics y hace que
caja.click() salte un TimeoutError aunque el elemento sea visible.
Se corrige pulsando Escape un par de veces antes de buscar la caja de
texto: cierra estos overlays de anuncio/tour en la inmensa mayoria de
webs sin afectar al resto de la pagina. Tambien deja un boton suelto
("Pensar", el selector de modo de razonamiento) pegado al pie de
disclaimer -- se quita solo porque cae detras del punto de corte del
pie.

27/09 (T188/T193): lectura por TURNOS verificados, modo en fallo cerrado y candado
exclusivo del Chrome. Ver el bloque "T188 / T193" mas abajo.
"""

from __future__ import annotations

import os
import re
import time
import unicodedata
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path

from nucleo.config import valor
from nucleo.registro import logger, traza
from manos import shell


log = logger("extremidades.navegador")


class Bloqueo(RuntimeError):
    """Captcha o bloqueo. Se para y se avisa a Damian."""


SENALES_BLOQUEO = (
    "captcha",
    "verify you are human",
    "unusual activity",
    "actividad inusual",
    "confirma que eres humano",
    "too many requests",
    # Claude web de NEXO (T667, 04/10): verificacion de Cloudflare o del telefono. Nunca se resuelve: se para.
    "verifica que eres humano",
    "verifica que eres un humano",
    "verifying you are human",
    "just a moment",
    "verify your phone",
    "verifica tu número",
    "verificar tu número",
)

# Pie fijo que las IAs repiten bajo cada respuesta: si aparece, todo lo
# que sigue no es parte de la respuesta.
#
# B10 de N02: antes bastaba el fragmento suelto "puede cometer errores",
# y eso cortaba respuestas reales que contenian la frase ("un becario
# puede cometer errores..."). El pie de verdad siempre nombra a la IA
# ("Gemini no es humano. Puede cometer errores", "ChatGPT puede cometer
# errores. Considera verificar..."). 23/09: ChatGPT anade ademas una
# encuesta de satisfaccion que se colaba en el resultado (visto en
# prueba_chatgpt_vivo.py).
_PIE = re.compile(
    r"(?:gemini|chatgpt|claude)[^\n]{0,40}?puede cometer errores"
    r"|te está resultando útil esta conversación",
    re.IGNORECASE,
)


def _inicio_pie(texto: str) -> int:
    """Posicion donde empieza el pie (o la encuesta), o -1 si no hay."""

    m = _PIE.search(texto)

    return m.start() if m else -1


# Etiqueta de turno que antecede a la respuesta de la IA.
SUFIJOS_TURNO_IA = ("ha dicho", "said", "dijo:", "said:")  # 27/09: "ChatGPT dijo:"


def puerto() -> int:
    return int(valor("navegador.puerto_cdp", 9333))


def activo() -> bool:
    import httpx

    try:
        r = httpx.get(f"http://127.0.0.1:{puerto()}/json/version", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def arrancar(aprobado: bool = False) -> dict:
    """Abre el Chrome de pruebas con el puerto de depuracion.

    Instancia aparte con su propio perfil: no toca tu Chrome de diario.
    """

    if activo():
        return {"ya_estaba": True, "puerto": puerto()}

    chrome = valor(
        "navegador.chrome",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    )

    perfil = valor("navegador.perfil", "")

    # T262: que siga trabajando igual con la ventana minimizada o tapada (sin frenar temporizadores ni render).
    comando = (
        f'& "{chrome}" --remote-debugging-port={puerto()} '
        f'--user-data-dir="{perfil}" --no-first-run --no-default-browser-check '
        f'--disable-backgrounding-occluded-windows --disable-renderer-backgrounding '
        f'--disable-background-timer-throttling'
    )

    resultado = shell.lanzar(comando, nombre="chrome_agente", aprobado=aprobado)

    for _ in range(20):
        time.sleep(1)

        if activo():
            log.info("chrome listo en el puerto %d", puerto())
            return resultado

    raise RuntimeError(
        f"Chrome no ha abierto el puerto {puerto()}. Mira "
        f"{resultado.get('log')}"
    )


# Zonas de la pagina donde un captcha o bloqueo real no aparece: navegacion y turnos.
SELECTOR_NO_BLOQUEO = (
    "nav, aside, [role=navigation], "
    "user-query, model-response, [data-message-author-role], "
    '[data-testid="user-message"], [data-testid="assistant-message"], [data-testid="sidebar"], '
    # Anunciador oculto de Gemini para lectores de pantalla: repite el titulo del
    # razonamiento ("Defining CAPTCHA Purpose"). No se excluye todo [aria-live]: un
    # aviso real de limite podria ir en una region asi.
    ".cdk-live-announcer-element"
)


def _navegacion(pagina) -> tuple[str, ...]:
    """Textos de la navegacion de la pagina (barra lateral, historial), el mas largo primero.

    27/09 (caso real): la lista "Recientes" de Gemini y ChatGPT muestra los titulos
    de chats viejos ("Para que sirve un captcha") y hacia saltar el bloqueo en todas
    las peticiones siguientes. Un captcha real no sale en la navegacion. En Gemini la
    barra esta dentro de <main> (bard-sidenav[role=navigation]): por eso no vale
    mirar solo <main>. Si la pagina no responde, no se quita nada.

    Tambien los turnos de la conversacion (Gemini: user-query/model-response;
    ChatGPT: [data-message-author-role]). Mismo caso del 27/09: la pregunta que
    pinta Gemini no coincide caracter a caracter con la enviada y el titulo del
    razonamiento ("Defining CAPTCHA Purpose") no esta en el texto de la
    respuesta, asi que quitar el prompt y la respuesta como texto no bastaba.
    Mismo riesgo que B6: lo que diga la IA dentro de su respuesta no cuenta.
    """

    try:
        textos = pagina.locator(SELECTOR_NO_BLOQUEO).all_inner_texts()
    except Exception:
        return ()

    return tuple(sorted((x for x in textos if x and x.strip()), key=len, reverse=True))


def _revisar_bloqueo(texto: str, conversacion: tuple[str, ...] = ()) -> None:
    """Para si la pagina muestra un captcha o bloqueo.

    B6 de N02: el texto de la pagina incluye la conversacion, asi que una
    pregunta o respuesta que HABLE de captchas o de "too many requests"
    disparaba un Bloqueo falso. Lo que se pase en `conversacion` (el
    prompt, la respuesta, la navegacion de _navegacion()) se quita antes de
    buscar las senales.
    """

    for trozo in conversacion:
        if trozo and trozo.strip():
            texto = texto.replace(trozo, " ")

    # Prueba real T262 (28/09): la pagina y la barra se leen en dos momentos; si entre medias ChatGPT anade
    # el titulo del chat nuevo a "Recientes", el bloque entero ya no coincide. Se quita tambien linea a linea.
    for trozo in conversacion:
        for linea in sorted({l.strip() for l in (trozo or "").splitlines() if len(l.strip()) >= 4},
                            key=len, reverse=True):
            texto = texto.replace(linea, " ")

    # Como antes: solo la parte de arriba de la pagina, donde salen los avisos.
    bajo = texto[:4000].lower()

    for senal in SENALES_BLOQUEO:
        if senal in bajo:
            raise Bloqueo(
                f"Detectado bloqueo o captcha ({senal}). "
                "Se para aqui: esto lo resuelves tu a mano."
            )


def _cerrar_overlays(pagina) -> None:
    """Cierra anuncios/tours a pantalla completa que tapan la pagina.

    Visto en ChatGPT con cuentas recien estrenadas: un overlay de
    "novedades" intercepta los clics aunque el elemento de debajo sea
    visible. Escape los cierra en la inmensa mayoria de webs.
    """

    for _ in range(2):
        pagina.keyboard.press("Escape")
        pagina.wait_for_timeout(400)

    # 23/09: Gemini muestra "Dedica un momento a verificar tu edad" (cuenta de NEXO sin edad
    # verificada) y Escape no lo cierra. "Ahora no" es inocuo; verificar la edad es cosa de Damian.
    try:
        ahora_no = pagina.locator(".cdk-overlay-container button", has_text="Ahora no")
        if ahora_no.count():
            ahora_no.first.click(timeout=3000)
            pagina.wait_for_timeout(600)
            log.info("cerrado el aviso de verificacion de edad ('Ahora no')")
    except Exception:
        pass


def _extraer_respuesta(antes: str, ultimo: str, prompt: str) -> str:
    """Saca solo la respuesta de la IA del texto completo de la pagina.

    Ver el docstring del modulo para el porque de cada paso.
    """

    prefijo = len(os.path.commonprefix([antes, ultimo]))

    if prefijo < len(antes) * 0.5:
        nuevo = ultimo
    else:
        nuevo = ultimo[prefijo:].strip()

    # Corta por la ULTIMA vez que aparece tu propio prompt: Gemini/ChatGPT
    # lo repiten en pantalla (a veces dos veces) antes de responder.
    i = nuevo.rfind(prompt)

    if i != -1:
        nuevo = nuevo[i + len(prompt):].strip()

    # Quita la etiqueta de turno si quedo como primera linea.
    primera, _, resto = nuevo.partition("\n")

    if primera.strip().lower().endswith(SUFIJOS_TURNO_IA):
        nuevo = resto.lstrip("\n")

    # Quita el pie fijo de disclaimer y todo lo de despues (incluye
    # cualquier boton/insignia que quede pegado tras el, como el
    # selector "Pensar" de ChatGPT). Busqueda case-insensitive porque
    # cada sitio lo redacta distinto.
    j = _inicio_pie(nuevo)

    if j != -1:
        inicio = nuevo.rfind("\n", 0, j)
        nuevo = nuevo[:inicio].strip() if inicio != -1 else nuevo[:j].strip()

    # La insignia del modelo (p.ej. "Flash") a veces queda suelta al
    # final, separada del texto por un hueco de 2+ lineas en blanco:
    # ese hueco grande es la senal de que es una insignia, no la
    # respuesta (una respuesta real no deja ese salto).
    partes = nuevo.rstrip().rsplit("\n\n\n", 1)

    if len(partes) == 2 and partes[1].strip() and "\n" not in partes[1].strip():
        if len(partes[1].strip()) <= 20:
            nuevo = partes[0].strip()

    return nuevo.strip()


# ---------------------------------------------------------------- T188 / T193 (27/09)
#
# Historia: T076 (23/09) leia la respuesta del ULTIMO MENSAJE DE LA IA en el DOM
# ([data-message-author-role]) y, si no lo encontraba en 30-180 s, caia a un metodo de
# respaldo (diff del texto de toda la pagina) que daba OK por su cuenta. El 27/09 se vio
# el fallo completo: ChatGPT cambio su DOM (ya no hay data-message-author-role ni
# data-testid="stop-button"), la lectura DOM fallaba SIEMPRE, el respaldo tardaba ~3 min
# y, con otro proceso usando el mismo Chrome, devolvio OK con texto de OTRA conversacion.
# El boton Pensar tambien cambio (ya no lleva la clase __composer-pill) y los prompts se
# enviaban sin Pensar.
#
# Ahora:
# - El HTML de la pagina se convierte en TURNOS (usuario/IA) con un mini-parser de la
#   stdlib (leer_turnos). Es una funcion pura: se usa igual en vivo y en los tests con
#   DOM grabado (tests/datos/navegador/).
# - Una respuesta solo vale si el ultimo mensaje del usuario es EXACTAMENTE nuestro prompt
#   (espacios normalizados), es un mensaje NUEVO (no estaba antes de enviar) y la respuesta
#   va detras y tambien es nueva (evaluar_turnos). Si no: RespuestaNoVerificada, nunca OK.
# - El respaldo (diff de pagina) solo se usa si el turno de usuario YA esta verificado por
#   DOM y lo que falla es encontrar el turno de la IA. Sin esa verificacion no hay respaldo.
# - Modo (Pensar / Pro): FALLO CERRADO. Si no se confirma, se recarga y se reintenta una
#   vez; si sigue sin estar, NO se envia (ModoNoActivo). Tras enviar se relee el modo en
#   la pantalla y queda en la evidencia (ULTIMA_EVIDENCIA y registros/trazas.jsonl).
# - Candado exclusivo del Chrome de NEXO (en_exclusiva): un solo proceso cada vez.


class FalloNavegador(RuntimeError):
    """El navegador no puede dar una respuesta VERIFICADA. Nunca se convierte en OK."""


class ModoNoActivo(FalloNavegador):
    """Se pidio Pensar/Pro y no se pudo confirmar: no se envia (fallo cerrado, T188)."""


class RespuestaNoVerificada(FalloNavegador):
    """No se puede demostrar que la respuesta es la de NUESTRO prompt (T193)."""


class LimiteUso(FalloNavegador):
    """La web muestra su aviso de limite de uso. `hasta` = epoch de la hora de reinicio que muestra (o un rato fijo)."""

    def __init__(self, mensaje: str, hasta: float):
        super().__init__(mensaje)
        self.hasta = hasta


# Aviso de limite de Claude web (plan Free). Sin hora en pantalla se enfria este rato (las ventanas de uso del plan
# gratuito son de unas horas: SIN VERIFICAR).
LIMITE_SIN_HORA = 5 * 3600
_SENAL_LIMITE = re.compile(r"(?i)(has alcanzado (el|tu) l[ií]mite|l[ií]mite de (mensajes|uso)|te has quedado sin "
                           r"mensajes|sin mensajes gratuitos|out of (free )?messages|message limit|usage limit|"
                           r"reached your (usage |message )?limit)")
_HORA_LIMITE = re.compile(r"(?i)(?:a las|hasta las|hasta|at|until)\s+(\d{1,2})(?:[:.](\d{2}))?\s*"
                          r"(a\.?\s?m\.?|p\.?\s?m\.?|h\b)?")


def _hora(epoch: float) -> str:
    return time.strftime("%d/%m %H:%M", time.localtime(epoch))


def limite_uso(texto: str, ahora: float | None = None) -> float | None:
    """Epoch hasta el que dura el limite que anuncia `texto`, o None si no anuncia ninguno."""
    from datetime import datetime, timedelta

    ahora = time.time() if ahora is None else ahora
    m = _SENAL_LIMITE.search(texto or "")
    if not m:
        return None
    hora = _HORA_LIMITE.search(texto[m.start():m.start() + 400])
    if not hora:
        return ahora + LIMITE_SIN_HORA
    h, mi = int(hora.group(1)), int(hora.group(2) or 0)
    sufijo = (hora.group(3) or "").lower().replace(".", "").replace(" ", "")
    if sufijo.startswith("p") and h < 12:
        h += 12
    elif sufijo.startswith("a") and h == 12:
        h = 0
    if h > 23 or mi > 59:
        return ahora + LIMITE_SIN_HORA
    base = datetime.fromtimestamp(ahora)
    objetivo = base.replace(hour=h, minute=mi, second=0, microsecond=0)
    if objetivo <= base:
        objetivo += timedelta(days=1)
    return objetivo.timestamp()


def _revisar_limite(texto: str, conversacion: tuple[str, ...] = ()) -> float | None:
    """Como _revisar_bloqueo: quita la conversacion y la navegacion y busca el aviso de limite."""
    for trozo in sorted((t for t in conversacion if t and t.strip()), key=len, reverse=True):
        texto = texto.replace(trozo, " ")
    return limite_uso(texto)


class ChromeOcupado(FalloNavegador):
    """Otro proceso tiene el Chrome de NEXO y no lo solto a tiempo (T193)."""


def ruta_candado() -> Path:
    from nucleo.config import RAIZ

    return Path(RAIZ) / "registros" / "chrome_nexo.lock"


@contextmanager
def en_exclusiva(motivo: str, espera: float | None = None):
    """Uso exclusivo del Chrome de NEXO entre procesos. El segundo espera; si se agota, ChromeOcupado."""

    from nucleo import candado

    espera = float(valor("navegador.espera_candado", 600)) if espera is None else espera
    try:
        with candado.exclusivo(ruta_candado(), espera_maxima=espera, motivo=motivo):
            yield
    except candado.Ocupado as e:
        raise ChromeOcupado(f"El Chrome de NEXO lo esta usando otro proceso: {e}.") from None


# ------------------------------------------------------------ mini-DOM (stdlib)

_VACIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
           "track", "wbr"}


class _Nodo:
    __slots__ = ("tag", "attrs", "hijos", "padre")

    def __init__(self, tag: str, attrs: dict, padre):
        self.tag, self.attrs, self.hijos, self.padre = tag, attrs, [], padre

    def clases(self) -> list[str]:
        return (self.attrs.get("class") or "").split()


class _Arbol(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raiz = _Nodo("#raiz", {}, None)
        self.actual = self.raiz

    def _nodo(self, tag, attrs):
        n = _Nodo(tag, {k: (v if v is not None else "") for k, v in attrs}, self.actual)
        self.actual.hijos.append(n)
        return n

    def handle_starttag(self, tag, attrs):
        n = self._nodo(tag, attrs)
        if tag not in _VACIOS:
            self.actual = n

    def handle_startendtag(self, tag, attrs):
        self._nodo(tag, attrs)

    def handle_endtag(self, tag):
        n = self.actual
        while n is not self.raiz and n.tag != tag:
            n = n.padre
        if n is not self.raiz:
            self.actual = n.padre

    def handle_data(self, data):
        self.actual.hijos.append(data)


def _parsear(html: str) -> _Nodo:
    arbol = _Arbol()
    arbol.feed(html or "")
    arbol.close()
    return arbol.raiz


_ATRIB = re.compile(r'\[\s*([\w:-]+)\s*(?:([~^$*]?=)\s*"([^"]*)")?\s*\]|\.([\w-]+)')


def _compilar(selector: str) -> list[list[tuple]]:
    """CSS minimo: 'tag', '.clase', '[a]', '[a="v"]', '[a^=|$=|*=|~="v"]', descendiente (espacio) y ','."""

    alternativas = []
    for alt in selector.split(","):
        partes, buf, prof = [], "", 0
        for c in alt.strip():
            prof += (c == "[") - (c == "]")
            if c.isspace() and prof == 0:
                if buf:
                    partes.append(buf)
                buf = ""
            else:
                buf += c
        if buf:
            partes.append(buf)
        compuestos = []
        for p in partes:
            m = re.match(r"[a-zA-Z][\w-]*|\*", p)
            tag = m.group(0).lower() if m and m.group(0) != "*" else None
            conds = [(a, op, v, cl) for a, op, v, cl in _ATRIB.findall(p[m.end() if m else 0:])]
            compuestos.append((tag, conds))
        if compuestos:
            alternativas.append(compuestos)
    return alternativas


def _cumple(n: _Nodo, compuesto) -> bool:
    tag, conds = compuesto
    if tag and n.tag != tag:
        return False
    for a, op, v, clase in conds:
        if clase:
            if clase not in n.clases():
                return False
            continue
        if a not in n.attrs:
            return False
        x = n.attrs[a]
        if (op == "=" and x != v) or (op == "^=" and not x.startswith(v)) or (op == "$=" and not x.endswith(v)) \
                or (op == "*=" and v not in x) or (op == "~=" and v not in x.split()):
            return False
    return True


def _encaja(n: _Nodo, alternativas) -> bool:
    for partes in alternativas:
        if not _cumple(n, partes[-1]):
            continue
        i, p = len(partes) - 2, n.padre
        while i >= 0 and p is not None:
            if _cumple(p, partes[i]):
                i -= 1
            p = p.padre
        if i < 0:
            return True
    return False


def _elementos(n: _Nodo):
    for h in n.hijos:
        if isinstance(h, _Nodo):
            yield h
            yield from _elementos(h)


def _buscar(n: _Nodo, selector: str, incluir_propio: bool = False) -> list[_Nodo]:
    alts = _compilar(selector)
    fuera = [n] if incluir_propio and _encaja(n, alts) else []
    return fuera + [e for e in _elementos(n) if _encaja(e, alts)]


_SALTAR = {"script", "style", "svg", "button", "template", "noscript", "mat-icon", "gem-icon", "input",
           "textarea", "select"}
_PARRAFO = {"p", "pre", "ul", "ol", "table", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "hr"}
_CABECERAS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_LINEA = {"div", "li", "tr", "section", "article", "header", "footer", "figure", "details", "summary", "dd", "dt"}
_CLASES_OCULTAS = {"cdk-visually-hidden", "sr-only", "screen-reader-user-query-label"}


def _oculto(n: _Nodo) -> bool:
    return "hidden" in n.attrs or n.attrs.get("aria-hidden") == "true" or bool(_CLASES_OCULTAS & set(n.clases()))


# T189 (27/09): pildoras de cita de la web ("GitHub +1" en ChatGPT, chips de fuentes en Gemini). No
# son texto de la respuesta: se quitan del texto y sus enlaces se guardan aparte como fuentes.
_TAGS_CITA = {"source-footnote", "sources-carousel", "sources-carousel-inline", "source-inline-chip",
              "source-inline-chips"}


def _es_cita(n: _Nodo) -> bool:
    if n.tag in _TAGS_CITA:
        return True
    if "citation" in (n.attrs.get("data-testid") or "").lower():
        return True
    # 04/10 (T667): Gemini envuelve la FRASE citada en <span class="citation-4 citation-end-4">: eso es texto de la
    # respuesta, no una pildora (se borraba entera; el tribunal perdio el voto 'P4: ...'). La pildora va dentro
    # (source-footnote) y ya cae por su etiqueta.
    return any("citation" in c.lower() and not re.fullmatch(r"citation(-end)?-\d+", c.lower()) for c in n.clases())


def _sin_rastreo(url: str) -> str:
    """Quita utm_* (ChatGPT anade ?utm_source=chatgpt.com a cada cita)."""
    base, _, query = url.partition("?")
    resto = "&".join(p for p in query.split("&") if p and not p.lower().startswith("utm_"))
    return base + (f"?{resto}" if resto else "")


def _enlaces(n: _Nodo) -> list[str]:
    return [_sin_rastreo(a.attrs["href"]) for a in [n] + list(_elementos(n))
            if a.tag == "a" and str(a.attrs.get("href", "")).startswith(("http://", "https://"))]


def _texto(n: _Nodo, fuentes: list[str] | None = None, menciones: bool = False) -> str:
    """Texto visible de un nodo, parecido a innerText (bloques en lineas, listas con '- ' o 'N. ').

    Las pildoras de cita no entran en el texto; si se pasa `fuentes`, sus enlaces se anaden ahi.
    `menciones`: lee tambien las pildoras de enlace de ChatGPT (<a data-inline-mention-interactive aria-hidden>):
    en el mensaje del usuario son texto que escribimos nosotros (la URL o el [texto: URL]) (T682, 11/10).
    """

    trozos: list[tuple[str, bool]] = []

    def rec(x, pre: bool):
        if isinstance(x, str):
            trozos.append((x if pre else re.sub(r"\s+", " ", x), pre))
            return
        if x.tag in _SALTAR or (_oculto(x) and not (menciones and "data-inline-mention-interactive" in x.attrs)):
            return
        if _es_cita(x):
            if fuentes is not None:
                fuentes.extend(u for u in _enlaces(x) if u not in fuentes)
            return
        if x.tag == "br":
            trozos.append(("\n", False))
            return
        if x.tag == "math":  # KaTeX: la fuente LaTeX, no la MathML letra a letra
            fuente = _buscar(x, "annotation")
            trozos.append((f" ${_plano(fuente[0])}$ " if fuente else _plano(x), False))
            return
        corte = "\n\n" if x.tag in _PARRAFO else ("\n" if x.tag in _LINEA else "")
        trozos.append((corte, False))
        if x.tag == "li":
            padre = x.padre
            if padre is not None and padre.tag == "ol":
                n_item = sum(1 for h in padre.hijos if isinstance(h, _Nodo) and h.tag == "li"
                             and padre.hijos.index(h) <= padre.hijos.index(x))
                trozos.append((f"{n_item}. ", False))
            else:
                trozos.append(("- ", False))
        if x.tag in ("td", "th"):
            trozos.append((" | ", False))
        if x.tag in _CABECERAS:
            # T265 (28/09): la web pinta '### TITULO' como <h3>; sin la marca los revisores veian el
            # texto sin cabecera y culpaban al autor (ESCALAR falsos).
            trozos.append(("#" * int(x.tag[1]) + " ", False))
        for h in x.hijos:
            rec(h, pre or x.tag == "pre")
        trozos.append((corte, False))

    rec(n, False)
    fuera, buf = [], []

    def volcar():
        if buf:
            fuera.append(re.sub(r" *\n *", "\n", "".join(buf)))
            buf.clear()

    for t, pre in trozos:
        if pre:
            volcar()
            fuera.append(t)
        else:
            buf.append(t)
    volcar()
    texto = re.sub(r"(?m)^(-|\d+\.)[ \t]*\n+", r"\1 ", "".join(fuera))  # <li><p>: la vineta en su linea
    texto = re.sub(r"(?m)^(#{1,6})[ \t]+", r"\1 ", texto)  # '###  X' -> '### X'
    texto = re.sub(r"(?m)^#{1,6} ?(\n|$)", "", texto)  # cabecera vacia
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def _plano(n: _Nodo) -> str:
    """Todo el texto del nodo en una linea (incluye botones; sin svg)."""

    partes = []

    def rec(x):
        if isinstance(x, str):
            partes.append(x)
        elif x.tag not in ("svg", "script", "style"):
            for h in x.hijos:
                rec(h)

    rec(n)
    return " ".join("".join(partes).split())


# ------------------------------------------------------------ turnos de la conversacion
#
# Por sitio: que elemento es un turno de usuario / de la IA, donde esta su texto y que
# atributo lo identifica (para saber si es NUEVO). Primero lo visto en vivo el 27/09;
# detras, lo anterior por si la web vuelve atras.
TURNOS = {
    "chatgpt": {
        "usuario": '[data-chatgpt-search-unit-key$=":user"], [data-message-author-role="user"]',
        "texto_usuario": "[data-user-message-bubble]",
        "ia": '[data-chatgpt-search-unit-key$=":assistant"], [data-message-author-role="assistant"]',
        "texto_ia": '[data-markdown-text-style="assistant-message"], .markdown',
        "ids": ("data-chatgpt-search-message-ids", "data-message-id"),
    },
    "gemini": {
        "usuario": "user-query",
        "texto_usuario": ".query-text",
        "ia": "model-response",
        "texto_ia": "message-content",
        "ids": ("id",),
    },
    # Claude web de NEXO (T667, DOM visto en vivo el 04/10). Los turnos no llevan id propio: vale la regla de
    # evaluar_turnos para turnos sin id (y siempre se usa conversacion nueva). El h2.sr-only "Claude ha
    # respondido: ..." de cada respuesta es oculto y no entra en el texto.
    "claude": {
        "usuario": '[data-testid="user-message"]',
        "texto_usuario": '[data-testid="user-message"]',
        "ia": '[data-testid="assistant-message"]',
        "texto_ia": ".standard-markdown, .progressive-markdown",
        "ids": (),
    },
}
# Generando: boton de parar o el texto de la IA marcado como ocupado.
SELECTOR_GENERANDO = {
    "chatgpt": 'button[aria-label^="Detener"], button[aria-label^="Stop"], [data-testid="stop-button"]',
    "gemini": 'button[aria-label^="Detener"], button[aria-label^="Stop"]',
    "claude": '[data-is-streaming="true"], button[aria-label^="Detener"], button[aria-label^="Stop"]',
}
ARRANQUE_DOM = 45.0      # si en este tiempo nuestra pregunta no es el ultimo mensaje -> fallo
QUIETO_DOM = 4.0         # segundos con el texto de la respuesta sin cambiar y sin generar
RESPALDO_TRAS = 90.0     # con el turno de usuario verificado y sin turno de IA reconocible


def _normalizar(texto: str) -> str:
    return " ".join((texto or "").split()).lower()


def _exacto(texto: str) -> str:
    """Para comparar prompts: mismo texto salvo espacios/saltos y simbolos de formato markdown.

    27/09 (prueba real): ChatGPT pinta el mensaje del usuario como markdown (`codigo` sale como
    <code>codigo</code>, sin las comillas invertidas) y Gemini parte las lineas en <p>. Se quitan
    en los DOS lados los simbolos que la web convierte en formato; las palabras y su orden se
    siguen exigiendo iguales.
    """

    texto = unicodedata.normalize("NFC", texto or "").replace("\u200b", "").replace("\ufeff", "")
    texto = re.sub(r"!?\[([^\]]*)\]\([^)\s]*\)", r"\1", texto)  # enlaces markdown -> su texto
    # T682 (11/10): ChatGPT pinta cada URL del mensaje del usuario como una "pildora" de mencion
    # (<a ... aria-hidden="true">) que no se lee como texto: '(https://github.com/x/y)' salia como '()' y
    # el 38 % de las mejoras del autor fallaban con "el ultimo mensaje del usuario no es nuestro prompt".
    # La pildora se traga ademas la puntuacion pegada a la URL ('”', ')', '.', ','). Se comparan las PALABRAS
    # (letras y digitos) en el mismo orden, sin URLs: un prompt distinto sigue sin coincidir.
    texto = _URL.sub(" ", texto)
    texto = re.sub(r"[`*_~#>|\\-]", "", texto)
    return " ".join(re.findall(r"[^\W_]+", texto))


_URL = re.compile(r"\b(?:https?://|www\.)[^\s()\[\]<>\u00ab\u00bb\"\u201c\u201d']*")


# T333 (28/09): con prompts largos (~9.000 car.) ChatGPT muestra el mensaje del usuario RECORTADO ("Mostrar
# mas") y la comparacion exacta fallaba a los 45 s con "el ultimo mensaje del usuario no es nuestro prompt"
# aunque empezaba por el. Un texto recortado cuenta como nuestro prompt solo si es PREFIJO del prompt, trae
# al menos MIN_PREFIJO_RECORTADO caracteres y el prompt es de verdad mas largo (un prompt corto sigue
# exigiendo igualdad exacta: nada de dar por bueno el mensaje de otra ejecucion).
MIN_PREFIJO_RECORTADO = 1000
_MARCA_RECORTE = re.compile(r"\s*(?:\.\.\.|…|mostrar\s+m[aá]s|ver\s+m[aá]s|show\s+more)\s*$", re.I)


def _mismo_prompt(texto: str, prompt: str) -> bool:
    a, b = _exacto(texto), _exacto(prompt)
    if a == b:
        return True
    visto = _exacto(_MARCA_RECORTE.sub("", a))
    return len(visto) >= MIN_PREFIJO_RECORTADO and len(b) > len(visto) and b.startswith(visto)


def _id_turno(nodo: _Nodo, atributos: tuple) -> str:
    for n in [nodo] + list(_elementos(nodo)):
        for a in atributos:
            if n.attrs.get(a):
                return n.attrs[a]
    return ""


CABECERA_FUENTES = "Fuentes enlazadas en la respuesta (extraidas por NEXO de las citas de la web):"
MAX_FUENTES = 15


def leer_turnos(html: str, sitio: str) -> list[dict]:
    """[{rol: 'usuario'|'ia', texto, id, ocupado, razono}] en orden de la conversacion."""

    cfg = TURNOS[sitio]
    alt_u, alt_i = _compilar(cfg["usuario"]), _compilar(cfg["ia"])
    turnos = []

    def turno(rol: str, nodo: _Nodo) -> dict:
        partes = _buscar(nodo, cfg[f"texto_{rol}"], incluir_propio=True)
        if rol == "usuario":
            texto = _texto(partes[0] if partes else nodo, menciones=True)
        else:
            # Solo el contenido mas externo (un .markdown dentro de otro no se repite).
            externos = [p for p in partes if not any(q is not p and _es_ancestro(q, p) for q in partes)]
            fuentes: list[str] = []
            texto = "\n\n".join(t for t in (_texto(p, fuentes) for p in externos) if t)
            if texto and fuentes:
                texto += "\n\n" + CABECERA_FUENTES + "\n" + "\n".join(f"- {u}" for u in fuentes[:MAX_FUENTES])
        ocupado = any(e.attrs.get("aria-busy") == "true" or e.attrs.get("data-is-streaming") == "true"
                      for e in [nodo] + list(_elementos(nodo)))
        razono = any("has-thoughts" in e.clases() for e in [nodo] + list(_elementos(nodo)))
        return {"rol": rol, "texto": texto, "id": _id_turno(nodo, cfg["ids"]), "ocupado": ocupado,
                "razono": razono}

    def rec(n: _Nodo):
        for h in n.hijos:
            if not isinstance(h, _Nodo):
                continue
            if _encaja(h, alt_u):
                turnos.append(turno("usuario", h))
            elif _encaja(h, alt_i):
                turnos.append(turno("ia", h))
            else:
                rec(h)

    rec(_parsear(html))
    return turnos


def _es_ancestro(a: _Nodo, b: _Nodo) -> bool:
    p = b.padre
    while p is not None:
        if p is a:
            return True
        p = p.padre
    return False


def generando(html: str, sitio: str, turnos: list[dict] | None = None) -> bool:
    """La IA sigue escribiendo: boton de parar visible o el ultimo turno de la IA ocupado."""

    if _buscar(_parsear(html), SELECTOR_GENERANDO[sitio]):
        return True
    turnos = leer_turnos(html, sitio) if turnos is None else turnos
    return bool(turnos) and turnos[-1]["rol"] == "ia" and turnos[-1]["ocupado"]


def evaluar_turnos(antes: list[dict], despues: list[dict], prompt: str) -> tuple[str, str]:
    """(estado, dato). Unico 'ok' posible: nuestro prompt es el ultimo mensaje del usuario,
    es NUEVO respecto a `antes` y hay texto de la IA detras que tampoco estaba antes.

    estados: 'sin_turnos' | 'ajeno' (el ultimo mensaje del usuario no es el nuestro) |
    'viejo' (es igual pero ya estaba antes de enviar) | 'esperando' (aun sin texto de la IA) | 'ok'.
    """

    usuarios = [i for i, t in enumerate(despues) if t["rol"] == "usuario"]
    if not usuarios:
        return "sin_turnos", "no reconozco ningun mensaje del usuario en la pagina"
    iu = usuarios[-1]
    u = despues[iu]
    if not _mismo_prompt(u["texto"], prompt):
        return "ajeno", f"el ultimo mensaje del usuario no es nuestro prompt: {u['texto'][:100]!r}"

    ids_antes = {t["id"] for t in antes if t["id"]}
    if u["id"]:
        nuevo = u["id"] not in ids_antes
    else:  # sin id: nuevo si hay mas mensajes del usuario que antes o el ultimo de antes era otro
        antes_u = [t for t in antes if t["rol"] == "usuario"]
        nuevo = len(usuarios) > len(antes_u) or not antes_u or not _mismo_prompt(antes_u[-1]["texto"], prompt)
    if not nuevo:
        return "viejo", "nuestro prompt ya estaba en la conversacion antes de enviar (no se ha publicado)"

    ia = [t for t in despues[iu + 1:] if t["rol"] == "ia"]
    if any(t["id"] and t["id"] in ids_antes for t in ia):
        return "viejo", "la respuesta tras nuestro prompt ya estaba antes de enviar"
    texto = "\n\n".join(t["texto"] for t in ia if t["texto"].strip())
    return ("ok", texto) if texto else ("esperando", "")


def modo_en_pantalla(html: str, sitio: str, etiqueta_confirmada: str = "") -> dict:
    """Lo que la pantalla dice del modo. {'ok': bool, 'detalle': str, ...}.

    chatgpt: el boton 'Pensar' del compositor con aria-pressed=true.
    gemini: el boton del selector de modo dice 'actualmente Pro ...', o (11/10, menu sin Pro) dice lo mismo
    que cuando _fijar_modo confirmo el modo en el menu (etiqueta_confirmada); y si el ultimo turno de
    la IA razono (clase has-thoughts), tambien consta.
    """

    raiz = _parsear(html)
    if sitio == "chatgpt":
        botones = [b for b in _buscar(raiz, 'form[data-chatgpt-composer] button[aria-pressed], '
                                            'button.__composer-pill') if _plano(b) == "Pensar"]
        if not botones:
            return {"ok": False, "pensar": None, "detalle": "chatgpt: no hay boton Pensar en pantalla"}
        activo_ = botones[-1].attrs.get("aria-pressed") == "true"
        return {"ok": activo_, "pensar": activo_, "detalle": f"chatgpt: Pensar {'ACTIVO' if activo_ else 'apagado'}"}
    if sitio == "gemini":
        botones = _buscar(raiz, '[data-test-id="bard-mode-menu-button"]')
        etiqueta = ""
        if botones:       # 17/10: el aria-label vive en el <button> interior del contenedor
            etiqueta = botones[0].attrs.get("aria-label") or next(
                (b.attrs["aria-label"] for b in _buscar(botones[0], "button") if b.attrs.get("aria-label")), "")
        actual = etiqueta.lower().split("actualmente", 1)[-1] if etiqueta else ""
        pro = bool(re.search(r"\bpro\b", actual)) or bool(etiqueta_confirmada and etiqueta == etiqueta_confirmada)
        turnos = leer_turnos(html, "gemini")
        razono = bool(turnos) and turnos[-1]["rol"] == "ia" and turnos[-1]["razono"]
        return {"ok": pro, "pro": pro, "razono": razono, "etiqueta": etiqueta,
                "detalle": f"gemini: {etiqueta or 'sin selector de modo'}" + ("; razono (has-thoughts)" if razono else "")}
    if sitio == "claude":
        botones = _buscar(raiz, SELECTOR_MODELO_CLAUDE)
        return modo_claude(botones[0].attrs.get("aria-label", "") if botones else "")
    return {"ok": True, "detalle": ""}


# Claude web de NEXO (T667): plan Free. Lo mejor que ofrece: Sonnet 5.5 con esfuerzo Alto ("Extra" y "Max"
# gastan 5 veces o mas del limite). El selector lo dice en su aria-label: "Modelo: Sonnet 5.5 Alto".
SELECTOR_MODELO_CLAUDE = '[data-testid="model-selector-dropdown"]'
MODELO_CLAUDE = "Sonnet 5.5"
ESFUERZO_CLAUDE = "Alto"
ESFUERZOS_CLAUDE = ("Bajo", "Medio", "Alto", "Extra", "Máx", "Max")


def modo_claude(etiqueta: str) -> dict:
    """Modelo y esfuerzo leidos del aria-label del selector de Claude. ok solo con los exigidos."""
    resto = re.sub(r"(?i)^\s*(modelo|model)\s*:\s*", "", etiqueta or "").strip()
    palabras = resto.split()
    esfuerzo = palabras[-1] if palabras and palabras[-1] in ESFUERZOS_CLAUDE else ""
    modelo = " ".join(palabras[:-1] if esfuerzo else palabras)
    ok = modelo.lower() == MODELO_CLAUDE.lower() and esfuerzo == ESFUERZO_CLAUDE
    return {"ok": ok, "modelo": modelo, "esfuerzo": esfuerzo, "etiqueta": etiqueta,
            "detalle": f"claude: {etiqueta or 'sin selector de modelo'}"}


# Lineas sueltas de botones de la interfaz que se cuelan en el texto (visto 23/09 en ChatGPT).
LINEAS_INTERFAZ = {"añadir a la biblioteca", "copiar", "copiar código", "editar", "mostrar más", "mostrar menos",
                   "fuentes", "compartir",
                   # 27/09 (T189, borrador T177): etiquetas de turno y marcas de la web leidas del body.
                   "chatgpt dijo:", "chatgpt ha dicho:", "tú dijiste:", "has dicho:", "gemini ha dicho",
                   "gemini ha dicho:", "última respuesta", "ultima respuesta", "show more", "chatgpt said:",
                   "you said:"}
# Prefijos de lineas de interfaz del modo razonamiento (23/09: "Ha pensado durante 31s").
PREFIJOS_INTERFAZ = ("ha pensado durante", "pensó durante", "thought for", "razonado durante")
# Contador de una pildora de cita leida del body ("GitHub" / "+1" en lineas sueltas).
_CONTADOR_CITA = re.compile(r"^\+\d{1,2}$")
# T229 (27/09, borrador T166): ChatGPT web mete anuncios en la respuesta: 3 lineas cortas
# (anunciante / producto / eslogan) y debajo "Anuncio" + "Opciones del anuncio".
ETIQUETAS_ANUNCIO = {"anuncio", "patrocinado", "sponsored"}
OPCIONES_ANUNCIO = {"opciones del anuncio", "ad options", "acerca de este anuncio", "about this ad"}
_LINEAS_ANUNCIO = 3


def _lineas_de_anuncio(lineas: list[str]) -> set[int]:
    """Indices del bloque de anuncio: la etiqueta, sus opciones y hasta 3 lineas cortas encima."""
    quitar = set()
    for i, l in enumerate(lineas):
        if l.strip().lower() in OPCIONES_ANUNCIO:
            quitar.add(i)
        if l.strip().lower() not in ETIQUETAS_ANUNCIO:
            continue
        quitar.add(i)
        k, n = i - 1, 0
        while k >= 0 and n < _LINEAS_ANUNCIO:
            previa = lineas[k].strip()
            if previa and (len(previa) > 80 or re.match(r"[#>|*\-\[]|\d+[.)]", previa)):
                break
            quitar.add(k)
            n += bool(previa)
            k -= 1
    return quitar


def _es_etiqueta_cita(linea: str) -> bool:
    """'GitHub', 'arxiv.org', 'Wikipedia': nombre corto de fuente sin puntuacion de frase."""
    l = linea.strip()
    return 0 < len(l) <= 30 and len(l.split()) <= 3 and not re.search(r"[:;,!?¿¡]|\.$", l)


def _limpiar_respuesta(texto: str) -> str:
    """Quita lineas de la interfaz, pildoras de cita sueltas, anuncios (T229) y el pie/encuesta (_PIE)."""

    lineas = texto.splitlines()
    quitar = _lineas_de_anuncio(lineas)
    for i, l in enumerate(lineas):
        if _CONTADOR_CITA.match(l.strip()):
            quitar.add(i)
            if i > 0 and _es_etiqueta_cita(lineas[i - 1]):
                quitar.add(i - 1)
    texto = "\n".join(l for i, l in enumerate(lineas)
                      if i not in quitar
                      and l.strip().lower() not in LINEAS_INTERFAZ
                      and not l.strip().lower().startswith(PREFIJOS_INTERFAZ))

    j = _inicio_pie(texto)

    if j != -1:
        inicio = texto.rfind("\n", 0, j)
        texto = texto[:inicio] if inicio != -1 else texto[:j]

    return texto.strip()


URL_NUEVA = {"gemini": "https://gemini.google.com/app", "chatgpt": "https://chatgpt.com/",
             "claude": "https://claude.ai/new"}
# URL de la ultima conversacion usada por sitio: para CONTINUAR en el mismo chat (revision final).
ULTIMA_URL: dict[str, str] = {}
# Evidencia de la ultima pregunta por sitio (modo antes/despues de enviar, metodo de lectura...).
ULTIMA_EVIDENCIA: dict[str, dict] = {}
# aria-label del selector de Gemini cuando el menu confirmo el modo, por preferido (modo_en_pantalla tras enviar).
ETIQUETA_GEMINI_CONFIRMADA: dict[str, str] = {}


# Menu de modo de Gemini. La web cambia los nombres (11/10: "3.1 Pro" + "Razonamiento ampliado" pasaron a
# "Automatico" (Gemini 3 models) + nivel "Min." / "Medio" / "Max."): se reconoce por SINONIMOS, nunca por un
# nombre exacto. 17/10 (captura real, tests/datos/navegador/gemini_menu_17_10.html): "3.1 Pro" y "4 Argon" siguen
# en el menu pero BLOQUEADOS (candado, data-mode-id "upsell_*": no se activan) y los niveles Min./Medio/Max. cuelgan
# de un item plegable "Nivel de razonamiento" que hay que desplegar. Modelo, por orden de preferencia: Automatico
# (que solo cuenta con el nivel maximo: con poco razonamiento puede ir a Flash, fallo cerrado); Pro solo si el
# menu lo ofrece SIN bloquear (menu antiguo). Lo bloqueado o plegable nunca es candidato.
MODELOS_GEMINI = (("automatico", "auto"), ("pro",))
AMPLIADO_GEMINI = ("razonamiento ampliado", "max", "maximo", "muy exhaustivo")
# 'pro' (respaldo cuando el ampliado se niega, trabajo.py): en el menu nuevo, Automatico + nivel medio.
MEDIO_GEMINI = ("medio", "profundidad equilibrada")


def _norm_modo(texto: str) -> str:
    """'  Máx. ' -> 'max': minusculas, sin tildes, sin punto final."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.lower().split()).rstrip(".").strip()


def _casa(item: dict, sinonimos, sublabel: bool = False) -> bool:
    textos = [_norm_modo(item["etiqueta"])] + ([_norm_modo(item.get("sublabel", ""))] if sublabel else [])
    for t in textos:
        for s in sinonimos:
            if t == s or t.startswith(s + " ") or s in t.split():
                return True
    return False


def items_modo_gemini_html(html: str) -> list[dict]:
    """Opciones del menu de modo de Gemini leidas de un DOM con el menu abierto (tests y diagnostico)."""
    raiz = _parsear(html)
    out = []
    for it in _buscar(raiz, 'gem-menu[data-test-id="gem-mode-menu"] gem-menu-item'):
        cont = _buscar(it, "gem-menu-item-content")
        propio = cont[0] if cont else it          # el item plegable contiene los niveles: solo se lee su contenido
        lab = _buscar(propio, "span.label")
        sub = _buscar(propio, ".sublabel")
        iconos = [m.attrs.get("data-mat-icon-name") for m in _buscar(propio, "mat-icon")]
        out.append({"etiqueta": _plano(lab[0]).strip() if lab else "",
                    "sublabel": _plano(sub[0]).strip() if sub else "",
                    "sel": bool(cont) and "selected" in cont[0].clases(),
                    "bloqueado": (it.attrs.get("data-mode-id") or "").startswith("upsell") or "lock" in iconos,
                    "plegable": "expandable" in it.clases(),
                    "plegado": "expandable" in it.clases() and it.attrs.get("aria-expanded") != "true"})
    return out


def plan_modo_gemini(items: list[dict], preferido: str = "ampliado") -> dict:
    """Que pulsar en el menu de Gemini. {'modelo': item|None, 'nivel': item|None, 'nivel_obligatorio': bool,
    'desconocido': str} ('desconocido' != '' = la web ha cambiado y no se reconoce: no se envia y se avisa)."""
    libres = [i for i in items if not i.get("bloqueado") and not i.get("plegable")]
    plegable = next((i for i in items if i.get("plegable")), None)
    modelo = None
    for grupo in MODELOS_GEMINI:
        modelo = next((i for i in libres if _casa(i, grupo)), None)
        if modelo:
            break
    if modelo is None:
        return {"modelo": None, "nivel": None, "nivel_obligatorio": True, "plegable": None,
                "desconocido": "no reconozco ningun modelo activable (ni Automatico ni Pro sin candado)"}
    es_pro = _casa(modelo, ("pro",))
    if preferido == "pro" and es_pro:
        return {"modelo": modelo, "nivel": None, "nivel_obligatorio": False, "plegable": None, "desconocido": ""}
    sinonimos = MEDIO_GEMINI if preferido == "pro" else AMPLIADO_GEMINI
    nivel = next((i for i in libres if i is not modelo and _casa(i, sinonimos, sublabel=True)), None)
    if nivel is None and es_pro is False and plegable is not None and plegable.get("plegado"):
        # los niveles estan dentro del item plegable: hay que desplegarlo y volver a leer (no es un menu desconocido)
        return {"modelo": modelo, "nivel": None, "nivel_obligatorio": True, "plegable": plegable, "desconocido": ""}
    # Con Pro, el ampliado es un extra: si el menu no lo ofrece, basta Pro (T147). Con Automatico es obligatorio.
    obligatorio = not es_pro
    desconocido = "" if nivel or not obligatorio else (
        f"'{modelo['etiqueta']}' sin nivel reconocible ({'/'.join(sinonimos)})")
    return {"modelo": modelo, "nivel": nivel, "nivel_obligatorio": obligatorio, "plegable": None,
            "desconocido": desconocido}


def modo_gemini_confirmado(items: list[dict], preferido: str = "ampliado") -> tuple[bool, str]:
    """Lo que el menu (reabierto DESPUES de pulsar) dice. Ok solo si estan marcados el modelo y el nivel del plan."""
    plan = plan_modo_gemini(items, preferido)
    if plan["desconocido"]:
        return False, plan["desconocido"]
    if plan["plegable"] is not None:
        return False, "el nivel de razonamiento esta plegado: no se puede leer"
    if not plan["modelo"]["sel"]:
        return False, f"'{plan['modelo']['etiqueta']}' no esta marcado"
    if plan["nivel"] is not None and not plan["nivel"]["sel"]:
        return False, f"'{plan['nivel']['etiqueta']}' no esta marcado"
    return True, ""


def _avisar_menu_gemini(items: list[dict], motivo: str) -> None:
    """La web de Gemini ha vuelto a cambiar su menu: aviso en el Centro (uno por menu distinto)."""
    nombres = [i["etiqueta"] for i in items]
    try:
        from nucleo import avisos
        avisos.emitir("navegador", "Gemini web ha cambiado su menú de modo",
                      f"{motivo}. Opciones que ofrece: {nombres}. NEXO no envía nada a Gemini web hasta "
                      "reconocerlas (sinónimos en extremidades/navegador.py, MODELOS_GEMINI / AMPLIADO_GEMINI).",
                      ruta="/", clave="gemini_menu:" + "|".join(_norm_modo(n) for n in nombres))
    except Exception:
        pass


def _items_modo_gemini(pagina) -> list[dict]:
    """Opciones del menu de modo de Gemini (menu ya abierto), con su locator en 'loc'."""
    items = pagina.locator('gem-menu[data-test-id="gem-mode-menu"] gem-menu-item')
    out = []
    for i in range(items.count()):
        it = items.nth(i)
        propio = it.locator("gem-menu-item-content").first      # el item plegable contiene los niveles
        etiqueta = (propio.locator("span.label").first.inner_text() or "").strip()
        sub = propio.locator(".sublabel")
        sublabel = (sub.first.inner_text() or "").strip() if sub.count() else ""
        clase = propio.get_attribute("class") or ""
        clase_item = (it.get_attribute("class") or "").split()
        iconos = [m.get_attribute("data-mat-icon-name") for m in propio.locator("mat-icon").all()]
        out.append({"etiqueta": etiqueta, "sublabel": sublabel, "sel": "selected" in clase.split(), "loc": it,
                    "bloqueado": (it.get_attribute("data-mode-id") or "").startswith("upsell") or "lock" in iconos,
                    "plegable": "expandable" in clase_item,
                    "plegado": "expandable" in clase_item and it.get_attribute("aria-expanded") != "true"})
    return out


def _leer_menu_gemini(pagina, preferido: str) -> tuple[list[dict], dict]:
    """Items y plan con el menu abierto; si el nivel esta dentro del item plegable, se despliega y se vuelve a leer."""
    items = _items_modo_gemini(pagina)
    plan = plan_modo_gemini(items, preferido)
    if plan["plegable"] is not None:
        plan["plegable"]["loc"].click(timeout=5000)
        pagina.wait_for_timeout(1200)
        items = _items_modo_gemini(pagina)
        plan = plan_modo_gemini(items, preferido)
    return items, plan


SELECTOR_ITEMS_GEMINI = 'gem-menu[data-test-id="gem-mode-menu"] gem-menu-item'


def _menu_gemini_abierto(pagina) -> bool:
    return pagina.locator(SELECTOR_ITEMS_GEMINI).count() > 0


def _abrir_menu_gemini(pagina, boton) -> None:
    """Abre el menu de modo. 17/10 (probado en vivo): Escape lo oculta pero el componente se queda 'abierto' y el
    SIGUIENTE clic en el boton no abre nada (solo se reinicia); por eso, si tras el clic no hay items, se reintenta."""
    for _ in range(2):
        boton.first.click(timeout=8000)
        pagina.wait_for_timeout(1200)
        if _menu_gemini_abierto(pagina):
            return


def _cerrar_menu_gemini(pagina, boton) -> None:
    """Cierra el menu SIN Escape: un clic mas en el boton lo cierra y deja el componente limpio."""
    if _menu_gemini_abierto(pagina):
        boton.first.click(timeout=8000)
        pagina.wait_for_timeout(600)


def _etiqueta_boton_modo(boton) -> str:
    """aria-label del selector de modo: 17/10 ya no esta en el contenedor sino en el <button> de dentro."""
    propia = boton.get_attribute("aria-label")
    if propia:
        return propia
    dentro = boton.locator("button[aria-label]")
    return (dentro.first.get_attribute("aria-label") or "") if dentro.count() else ""


def _boton_pensar(pagina):
    """Boton 'Pensar' del compositor de ChatGPT (27/09: ya sin la clase __composer-pill), o None."""

    for selector in ("form[data-chatgpt-composer] button[aria-pressed]", "button.__composer-pill"):
        loc = pagina.locator(selector, has_text="Pensar")
        if loc.count():
            return loc.first
    return None


ESPERA_CONTROLES = 25.0     # s que se espera a que la web pinte el control de modo (ventana minimizada: ~20 s)


def _esperar(buscar, segundos: float | None = None, paso: float = 0.5):
    """Lo que devuelva buscar() en cuanto no sea None, o None tras `segundos`.

    Prueba real T262 (28/09): con la ventana minimizada y la web en una pestana de fondo, Gemini tarda
    en pintar el selector de modo tras abrir un chat nuevo; mirarlo una sola vez daba 'no encuentro el
    selector'. No se trae la ventana al frente para acelerarlo (Damian la ha minimizado)."""
    limite = time.time() + (ESPERA_CONTROLES if segundos is None else segundos)
    while True:
        encontrado = buscar()
        if encontrado is not None or time.time() >= limite:
            return encontrado
        time.sleep(paso)


def _fijar_modo(pagina, sitio: str, preferido: str = "ampliado") -> tuple[bool, str]:
    """T147/T188: Gemini en 'Pro' (+ 'Razonamiento ampliado' si existe) y ChatGPT con 'Pensar'.

    (confirmado, detalle). Confirmado = leido en la pantalla DESPUES de pulsar, no 'he hecho clic'.
    """
    try:
        if sitio == "chatgpt":
            for intento in range(3):
                boton = _esperar(lambda: _boton_pensar(pagina))
                if boton is None:
                    return False, "chatgpt: no encuentro el boton Pensar"
                if boton.get_attribute("aria-pressed") == "true":
                    return True, "chatgpt: Pensar ACTIVO" + (" (activado)" if intento else " (ya estaba)")
                boton.click(timeout=5000)
                pagina.wait_for_timeout(1200)
            return False, "chatgpt: NO se pudo activar Pensar (sigue aria-pressed=false)"
        if sitio == "gemini":
            # Damian 23/09: hay que elegir primero '3.1 Pro' y DESPUES volver a abrir el menu y
            # activar 'Razonamiento ampliado' (es un extra encima de Pro, no un modo aparte).
            boton = pagina.locator('[data-test-id="bard-mode-menu-button"]')
            if _esperar(lambda: boton if boton.count() else None) is None:
                return False, "gemini: no encuentro el selector de modo"
            # 11/10: los nombres cambian; plan_modo_gemini los reconoce por sinonimos (modelo y luego nivel).
            pasos = []
            for parte in ("modelo", "nivel"):
                _abrir_menu_gemini(pagina, boton)
                items, plan = _leer_menu_gemini(pagina, preferido)
                if plan["desconocido"]:
                    _cerrar_menu_gemini(pagina, boton)
                    _avisar_menu_gemini(items, plan["desconocido"])
                    return False, (f"gemini: {plan['desconocido']} -> MENU: {[i['etiqueta'] for i in items]} | "
                                   f"boton: {_etiqueta_boton_modo(boton.first)}")
                item = plan[parte]
                if item is None:
                    _cerrar_menu_gemini(pagina, boton)
                    continue
                if item["sel"]:
                    _cerrar_menu_gemini(pagina, boton)
                    pasos.append(f"'{item['etiqueta']}' ya activo")
                    continue
                item["loc"].click(timeout=5000)
                pagina.wait_for_timeout(1500)
                _cerrar_overlays(pagina)
                pasos.append(f"'{item['etiqueta']}' pulsado")
            # verificacion final reabriendo el menu
            _abrir_menu_gemini(pagina, boton)
            items, _plan = _leer_menu_gemini(pagina, preferido)
            activos = [i["etiqueta"] for i in items if i["sel"]]
            _cerrar_menu_gemini(pagina, boton)
            ok, motivo = modo_gemini_confirmado(items, preferido)
            etiqueta = _etiqueta_boton_modo(boton.first)
            if ok:
                ETIQUETA_GEMINI_CONFIRMADA[preferido] = etiqueta
            detalle = (f"gemini: {'; '.join(pasos)} -> ACTIVOS: {activos} | boton: {etiqueta}"
                       + (f" | NO: {motivo}" if motivo else ""))
            return ok, detalle
        if sitio == "claude":
            return _fijar_modo_claude(pagina)
    except Exception as e:
        try:
            if sitio == "gemini":
                _cerrar_menu_gemini(pagina, pagina.locator('[data-test-id="bard-mode-menu-button"]'))
            else:
                pagina.keyboard.press("Escape")
        except Exception:
            pass
        return False, f"{sitio}: no pude fijar el modo ({type(e).__name__}: {str(e)[:80]})"
    return True, ""


def _etiqueta_claude(pagina) -> str:
    b = pagina.locator(SELECTOR_MODELO_CLAUDE)
    return (b.first.get_attribute("aria-label") or "") if b.count() else ""


def _fijar_modo_claude(pagina) -> tuple[bool, str]:
    """Sonnet 5.5 + esfuerzo Alto. Confirmado = leido en el aria-label del selector DESPUES de pulsar."""
    boton = pagina.locator(SELECTOR_MODELO_CLAUDE)
    if _esperar(lambda: boton if boton.count() else None) is None:
        return False, "claude: no encuentro el selector de modelo"
    pasos = []
    estado = modo_claude(_etiqueta_claude(pagina))
    if estado["ok"]:
        return True, f"{estado['detalle']} (ya estaba)"
    if estado["modelo"].lower() != MODELO_CLAUDE.lower():
        boton.first.click(timeout=8000)
        pagina.wait_for_timeout(1200)
        item = pagina.locator('[role="menu"] [role="menuitemradio"]', has_text=MODELO_CLAUDE)
        if not item.count():
            pagina.keyboard.press("Escape")
            return False, f"claude: no encuentro '{MODELO_CLAUDE}' en el menu de modelos ({estado['detalle']})"
        item.first.click(timeout=5000)
        pagina.wait_for_timeout(1200)
        pasos.append(f"'{MODELO_CLAUDE}' pulsado")
        estado = modo_claude(_etiqueta_claude(pagina))
    if estado["esfuerzo"] != ESFUERZO_CLAUDE:
        boton.first.click(timeout=8000)
        pagina.wait_for_timeout(1200)
        esf = pagina.locator('[role="menu"] [role="menuitem"]', has_text="Esfuerzo")
        if not esf.count():
            pagina.keyboard.press("Escape")
            return False, f"claude: no encuentro 'Esfuerzo' en el menu ({estado['detalle']})"
        esf.first.hover(timeout=5000)
        pagina.wait_for_timeout(1200)
        opcion = pagina.locator('[role="menu"] [role="menuitemradio"]', has_text=ESFUERZO_CLAUDE)
        if not opcion.count():
            pagina.keyboard.press("Escape")
            return False, f"claude: no encuentro el esfuerzo '{ESFUERZO_CLAUDE}' ({estado['detalle']})"
        opcion.first.click(timeout=5000)
        pagina.wait_for_timeout(1200)
        pagina.keyboard.press("Escape")
        pasos.append(f"esfuerzo '{ESFUERZO_CLAUDE}' pulsado")
    estado = modo_claude(_etiqueta_claude(pagina))
    return estado["ok"], f"{estado['detalle']} ({'; '.join(pasos) or 'sin cambios'})"


def _asegurar_modo(pagina, sitio: str, preferido: str = "ampliado") -> str:
    """Compatibilidad (herramientas_delegacion/prueba_modos_vivo.py): solo el detalle."""

    return _fijar_modo(pagina, sitio, preferido)[1]


def _html(pagina) -> str:
    return pagina.evaluate("() => document.body ? document.body.outerHTML : ''")


def _guardar_dom(sitio: str, html: str, motivo: str) -> str:
    """Copia del DOM cuando algo falla: para arreglar selectores sin reproducir el fallo."""

    try:
        from nucleo.config import RAIZ

        carpeta = Path(RAIZ) / "registros" / "navegador_fallos"
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / f"{sitio}_{time.strftime('%Y%m%d_%H%M%S')}.html"
        ruta.write_text(f"<!-- {motivo} -->\n{html}", encoding="utf-8")
        return str(ruta)
    except Exception:
        return ""


def _fallo(evidencia: dict, error: FalloNavegador, html: str = "") -> FalloNavegador:
    """Registra el fallo (trazas + DOM) y devuelve la excepcion para lanzarla."""

    evidencia.update(resultado="FALLO", error=str(error))
    if html:
        evidencia["dom"] = _guardar_dom(evidencia.get("sitio", "x"), html, str(error))
    ULTIMA_EVIDENCIA[evidencia.get("sitio", "")] = evidencia
    try:
        traza("navegador_pregunta", **evidencia)
    except Exception:
        pass
    log.warning("%s: FALLO %s", evidencia.get("sitio"), error)
    return error


def _esperar_respuesta(pagina, sitio: str, prompt: str, espera: float, turnos_antes: list[dict],
                       texto_antes: str) -> tuple[str, str, str]:
    """(texto, metodo, html_final) de la respuesta VERIFICADA a este prompt, o RespuestaNoVerificada."""

    inicio = time.time()
    nuestro_desde = None
    ultimo, quieto_desde = None, time.time()
    cuerpo, cuerpo_quieto = "", time.time()
    html = ""

    while time.time() < inicio + espera:
        pagina.wait_for_timeout(1500)
        html = _html(pagina)
        turnos = leer_turnos(html, sitio)
        estado, dato = evaluar_turnos(turnos_antes, turnos, prompt)

        if estado in ("sin_turnos", "ajeno", "viejo"):
            if nuestro_desde is not None:
                raise RespuestaNoVerificada(f"{sitio}: nuestra pregunta ya no es la ultima de la conversacion ({dato})")
            if time.time() - inicio > ARRANQUE_DOM:
                raise RespuestaNoVerificada(f"{sitio}: en {ARRANQUE_DOM:.0f} s nuestra pregunta no aparece como "
                                            f"ultimo mensaje ({dato})")
            continue

        nuestro_desde = nuestro_desde or time.time()
        gen = generando(html, sitio, turnos)

        if estado == "esperando":
            # Respaldo: SOLO con el turno de usuario ya verificado y sin turno de IA reconocible.
            if not gen and time.time() - nuestro_desde > RESPALDO_TRAS:
                actual = pagina.inner_text("body")
                if actual != cuerpo:
                    cuerpo, cuerpo_quieto = actual, time.time()
                elif time.time() - cuerpo_quieto > 8:
                    nuevo = _extraer_respuesta(texto_antes, cuerpo, prompt)
                    if nuevo and nuevo not in texto_antes:
                        log.warning("%s: turno de la IA no reconocido en el DOM; uso el respaldo con el turno "
                                    "de usuario verificado (revisar TURNOS)", sitio)
                        return nuevo, "respaldo (turno de usuario verificado por DOM)", html
            continue

        if dato != ultimo:
            ultimo, quieto_desde = dato, time.time()
        elif not gen and time.time() - quieto_desde >= QUIETO_DOM:
            log.info("%s: respuesta verificada por DOM (%d car.): %r", sitio, len(dato), dato[:120])
            return dato, "dom", html

    raise RespuestaNoVerificada(f"{sitio}: sin respuesta completa y verificada en {espera:.0f} s"
                                + (" (a medias: no vale)" if ultimo else ""))


def _caja_texto(pagina, sitio: str):
    especificos = {"chatgpt": 'form[data-chatgpt-composer] [contenteditable="true"]',
                   "gemini": 'rich-textarea [contenteditable="true"]',
                   "claude": '[data-testid="chat-input"][contenteditable="true"]'}
    for selector in (especificos[sitio], '[contenteditable="true"]', "textarea", '[role="textbox"]'):
        elementos = pagina.locator(selector)
        for i in range(elementos.count() - 1, -1, -1):
            if elementos.nth(i).is_visible():
                return elementos.nth(i)
    return None


def preguntar(sitio: str, prompt: str, espera: int = 120, nueva: bool = False, modo: bool | str = True,
              url: str | None = None) -> str:
    """Escribe un prompt en una web de IA y devuelve la respuesta VERIFICADA.

    sitio: "gemini" o "chatgpt".
    nueva=True abre una conversacion nueva antes (T147: tema nuevo -> no arrastrar contexto).
    modo=True exige Gemini Pro (+ Razonamiento ampliado) / ChatGPT Pensar: si no se confirma, NO
    se envia (ModoNoActivo). 'pro' = Gemini solo Pro.
    Lanza FalloNavegador (ModoNoActivo, RespuestaNoVerificada, ChromeOcupado) en vez de devolver
    algo que no se pueda demostrar. Uso exclusivo del Chrome de NEXO mientras dura.
    """

    sitio = sitio.lower()
    dominio = {"gemini": "gemini.google.com", "chatgpt": "chatgpt.com", "claude": "claude.ai"}.get(sitio)

    if not dominio:
        raise ValueError(f"Sitio no soportado: {sitio}")

    if not activo():
        raise RuntimeError(
            "El Chrome de pruebas no esta abierto. Llama antes a arrancar()."
        )

    with en_exclusiva(f"preguntar a {sitio}"):
        return _preguntar(sitio, dominio, prompt, espera, nueva, modo, url)


def estado_ventana(pagina) -> str:
    """'normal' | 'minimized' | 'maximized' | 'fullscreen' de la ventana de la pestana, o 'desconocido'."""
    try:
        cdp = pagina.context.new_cdp_session(pagina)
        try:
            return cdp.send("Browser.getWindowForTarget")["bounds"].get("windowState") or "desconocido"
        finally:
            cdp.detach()
    except Exception:
        return "desconocido"


def al_frente(pagina) -> str:
    """T262 (Damian 27/09): bring_to_front() restaura una ventana minimizada, y la del Chrome de NEXO volvia
    a saltar en medio de la pantalla en cada pregunta. Si Damian la ha minimizado, se respeta: todo lo que
    hace NEXO en la pagina va por CDP y no necesita la ventana visible. Devuelve el estado de la ventana."""
    estado = estado_ventana(pagina)
    if estado == "minimized":
        log.info("ventana minimizada: no se trae al frente (T262)")
    else:
        pagina.bring_to_front()
    return estado


def _id_ventana(pagina):
    try:
        cdp = pagina.context.new_cdp_session(pagina)
        try:
            return cdp.send("Browser.getWindowForTarget")["windowId"]
        finally:
            cdp.detach()
    except Exception:
        return None


def _abrir_pestana(navegador, url: str):
    """Damian 04/10: UNA sola ventana con pestanas. Abre `url` como pestana de FONDO en la ventana que ya hay (no la
    activa, asi una ventana minimizada sigue minimizada). Prueba real del 04/10: con la ventana minimizada y Gemini y
    ChatGPT en pestanas de fondo, los dos fijan su modo y responden (flags de arrancar()). Si CDP no deja, pestana."""
    contexto = navegador.contexts[0]
    try:
        sesion = navegador.new_browser_cdp_session()
        with contexto.expect_page() as info:
            sesion.send("Target.createTarget", {"url": url, "newWindow": False, "background": True})
        pagina = info.value
        pagina.wait_for_load_state("domcontentloaded")
        return pagina
    except Exception as e:
        log.warning("no se pudo abrir %s como pestana de fondo (%s): pestana nueva", url, type(e).__name__)
        pagina = contexto.new_page()
        pagina.goto(url, wait_until="domcontentloaded")
        return pagina


def _en_ventana_principal(navegador, pagina):
    """Si la pagina quedo en otra ventana (las de antes del 04/10, una por web), se reabre como pestana de fondo en la
    ventana principal (la de la primera pestana) y se cierra la vieja: la conversacion va en su URL."""
    otras = [x for c in navegador.contexts for x in c.pages if x is not pagina]
    if not otras:
        return pagina
    principal, mia = _id_ventana(otras[0]), _id_ventana(pagina)
    if principal is None or mia is None or mia == principal:
        return pagina
    nueva = _abrir_pestana(navegador, pagina.url)
    log.info("%s vuelve como pestana a la ventana principal", pagina.url[:60])
    pagina.close()
    return nueva


def _preguntar(sitio, dominio, prompt, espera, nueva, modo, url) -> str:
    from playwright.sync_api import sync_playwright

    preferido = modo if isinstance(modo, str) else "ampliado"
    evidencia = {"sitio": sitio, "modo_pedido": (preferido if modo else "ninguno"), "prompt_car": len(prompt),
                 "hora": time.strftime("%Y-%m-%d %H:%M:%S")}

    with sync_playwright() as p:
        navegador = p.chromium.connect_over_cdp(f"http://127.0.0.1:{puerto()}")

        if not navegador.contexts:
            raise RuntimeError("Chrome sin contextos.")

        pagina = None

        for contexto in navegador.contexts:
            for candidata in contexto.pages:
                if dominio in candidata.url:
                    pagina = candidata
                    break

        if pagina is None:
            # Damian 04/10: pestana de fondo en la unica ventana (minimizada o no, se respeta como este).
            pagina = _abrir_pestana(navegador, f"https://{dominio}/")
            pagina.wait_for_timeout(4000)
        else:
            pagina = _en_ventana_principal(navegador, pagina)

        evidencia["ventana"] = al_frente(pagina)

        def ir():
            if url:
                if pagina.url.split("?")[0] != url:
                    pagina.goto(url, wait_until="domcontentloaded")
                    pagina.wait_for_timeout(3500)
            elif nueva:
                pagina.goto(URL_NUEVA[sitio], wait_until="domcontentloaded")
                pagina.wait_for_timeout(3500)

        ir()

        if modo:
            ok, detalle = False, ""
            for intento in range(2):
                _cerrar_overlays(pagina)
                ok, detalle = _fijar_modo(pagina, sitio, preferido)
                log.info("modo (intento %d): %s", intento + 1, detalle)
                if ok:
                    break
                if intento == 0:  # reintento con la pagina recargada
                    if url or nueva:
                        pagina.goto(url or URL_NUEVA[sitio], wait_until="domcontentloaded")
                    else:
                        pagina.reload(wait_until="domcontentloaded")
                    pagina.wait_for_timeout(3500)
            evidencia["modo_antes"] = detalle
            if not ok:
                raise _fallo(evidencia, ModoNoActivo(f"{sitio}: no se confirma el modo {preferido}; NO se envia "
                                                     f"({detalle})"), _html(pagina))

        _revisar_bloqueo(pagina.inner_text("body"), _navegacion(pagina))
        if sitio == "claude":
            hasta = _revisar_limite(pagina.inner_text("body"), _navegacion(pagina))
            if hasta:
                raise _fallo(evidencia, LimiteUso(f"claude: limite de uso hasta {_hora(hasta)}; NO se envia",
                                                  hasta=hasta))

        _cerrar_overlays(pagina)

        caja = _caja_texto(pagina, sitio)

        if caja is None:
            raise RuntimeError(f"No encuentro donde escribir en {dominio}.")

        texto_antes = pagina.inner_text("body")
        turnos_antes = leer_turnos(_html(pagina), sitio)

        caja.click(timeout=10000)
        caja.fill(prompt)

        if modo and sitio == "claude":
            # Igual que Pensar en ChatGPT: se relee el modelo justo antes de Enter.
            ok, detalle = _fijar_modo(pagina, "claude")
            if not ok:
                caja.fill("")
                raise _fallo(evidencia, ModoNoActivo(f"claude: modelo o esfuerzo cambiados justo antes de enviar; "
                                                     f"NO se envia ({detalle})"), _html(pagina))
            caja.click(timeout=10000)

        if modo and sitio == "chatgpt":
            # Damian vio 'Pensar' apagado al enviar: se comprueba otra vez justo antes de Enter.
            ok, detalle = _fijar_modo(pagina, "chatgpt")
            log.info("antes de enviar: %s", detalle)
            if not ok:
                caja.fill("")
                raise _fallo(evidencia, ModoNoActivo(f"chatgpt: Pensar apagado justo antes de enviar; NO se envia "
                                                     f"({detalle})"), _html(pagina))
            caja.click(timeout=10000)

        caja.press("Enter")

        # Con Pensar / Razonamiento ampliado la respuesta tarda mas (23/09: ChatGPT paso de 30 s).
        if modo:
            espera = max(espera, 420)

        try:
            texto, metodo, html = _esperar_respuesta(pagina, sitio, prompt, espera, turnos_antes, texto_antes)
        except RespuestaNoVerificada as e:
            if sitio == "claude":   # el aviso de limite puede salir en vez de la respuesta
                hasta = _revisar_limite(pagina.inner_text("body"), (prompt,) + _navegacion(pagina))
                if hasta:
                    raise _fallo(evidencia, LimiteUso(f"claude: limite de uso hasta {_hora(hasta)} ({e})",
                                                      hasta=hasta), _html(pagina)) from None
            raise _fallo(evidencia, e, _html(pagina)) from None

        evidencia["metodo"] = metodo
        pantalla = modo_en_pantalla(html, sitio, ETIQUETA_GEMINI_CONFIRMADA.get(preferido, "") if sitio == "gemini" else "")
        evidencia["modo_tras_enviar"] = pantalla["detalle"]
        if modo and not pantalla["ok"]:
            raise _fallo(evidencia, ModoNoActivo(f"{sitio}: tras enviar la pantalla no confirma el modo "
                                                 f"({pantalla['detalle']}); la respuesta no vale"), html)

        _revisar_bloqueo(pagina.inner_text("body"), (prompt, texto) + _navegacion(pagina))
        nuevo = _limpiar_respuesta(texto)
        ULTIMA_URL[sitio] = pagina.url.split("?")[0]
        evidencia.update(resultado="OK", url=ULTIMA_URL[sitio], respuesta_car=len(nuevo))
        ULTIMA_EVIDENCIA[sitio] = evidencia
        try:
            traza("navegador_pregunta", **evidencia)
        except Exception:
            pass

        # Pausa deliberada: el volumen bajo es lo que mantiene la cuenta viva.
        time.sleep(3)

        # Antes [-8000:] cortaba el PRINCIPIO de un informe largo (version final + cierre).
        return nuevo[:30000]


def descargar_ultima_imagen(destino_carpeta: str | Path | None = None) -> Path:
    """Pulsa el boton de descarga de Gemini y guarda la imagen.

    Esta via ya estaba comprobada: la descarga nativa funciona donde
    el fetch del blob fallaba.
    """

    from playwright.sync_api import sync_playwright

    from nucleo.config import salidas

    carpeta = Path(destino_carpeta) if destino_carpeta else salidas()

    with en_exclusiva("descargar imagen de gemini"), sync_playwright() as p:
        navegador = p.chromium.connect_over_cdp(f"http://127.0.0.1:{puerto()}")

        pagina = None

        for contexto in navegador.contexts:
            for candidata in contexto.pages:
                if "gemini.google.com" in candidata.url:
                    pagina = candidata

        if pagina is None:
            raise RuntimeError("No hay ninguna pestana de Gemini abierta.")

        al_frente(pagina)

        for selector in (
            'button[aria-label*="Descargar"]',
            'button[aria-label*="download"]',
            'button[data-tooltip*="Descargar"]',
        ):
            botones = pagina.locator(selector)

            for i in range(botones.count() - 1, -1, -1):
                boton = botones.nth(i)

                if not boton.is_visible():
                    continue

                with pagina.expect_download(timeout=15000) as info:
                    boton.click()

                descarga = info.value

                destino = carpeta / descarga.suggested_filename

                descarga.save_as(str(destino))

                log.info("imagen descargada: %s", destino.name)

                return destino

    raise RuntimeError("No he encontrado ningun boton de descarga.")
