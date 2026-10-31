# -*- coding: utf-8 -*-
"""Seguridad de la interfaz: token por arranque, sesiones, CSRF, rate-limit y cabeceras.

Flujo (DECISIONES.md, "Autenticacion"):
  1. Al arrancar se genera un token aleatorio y se escribe en memoria/interfaz_token.txt.
  2. abrir_nexo.bat abre /entrar?t=<token>. Si es valido se crea una sesion en memoria y
     se entrega la cookie HttpOnly + SameSite=Strict. El token no viaja en cada peticion.
  3. Cada sesion tiene su token CSRF; TODO metodo no seguro (POST...) debe traerlo en la
     cabecera X-CSRF-Token (HTMX lo pone con hx-headers en <body>).
Las sesiones viven en memoria: reiniciar la web las invalida, igual que el token.

Hito movil: por Tailscale Serve no hace falta token. Si la peticion llega por Serve (por_serve) con
Tailscale-User-Login = el dueno de la tailnet, el middleware crea la sesion solo (via "tailnet")
y pone la cookie en esa misma respuesta. Otro login -> 403. Fuera de Serve la cabecera se ignora.

El middleware es ASGI puro (no BaseHTTPMiddleware) para no interferir con el streaming SSE.
"""
from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from collections import deque

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import cookie_parser
from starlette.responses import HTMLResponse, Response

from interfaz.config import Ajustes

COOKIE = "nexo_sesion"
CABECERA_CSRF = "x-csrf-token"
CABECERA_CSRF_RESPUESTA = "x-nexo-csrf"
MAX_SESIONES = 50
CABECERA_SESION_NUEVA = "x-nexo-sesion-nueva"

# /manifest.webmanifest, /sw.js y /sin-conexion: sin datos; el navegador los pide sin cookie (rutas/pwa.py).
RUTAS_PUBLICAS = ("/entrar", "/salud", "/manifest.webmanifest", "/sw.js", "/sin-conexion")
PREFIJOS_PUBLICOS = ("/estatico/",)
METODOS_SEGUROS = ("GET", "HEAD")

# T251: el build standalone de vis-network (vendor/, pestaña Grafo) mete su CSS en 7 <style>. Se dejan pasar
# SOLO esos textos, por su hash exacto (nada de 'unsafe-inline'), mas el del <style> VACIO: vis lo inserta vacio
# y luego le pone el texto, y Chrome comprueba en los dos momentos (visto en la prueba real). Si se cambia la version de vis-network hay
# que recalcularlos: test_grafo.py::test_csp_deja_solo_el_css_de_vis_network_por_hash lo comprueba.
ESTILOS_VIS_NETWORK = (
    "'sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU='",   # "" (el <style> recien creado, aun vacio)
    "'sha256-OutIf5hnp68ctx4ThtV5J02g5HTJ5bbu/hkNfqVXWWo='", "'sha256-4cgFR0//m8/eHo2G/esYsuZetUHlzCUWYM59sfgE9zY='",
    "'sha256-uepMTym1NwItBa/XV6ef6fQobLL0A0CNVDM5km5L+nQ='", "'sha256-gGUn/VMBXCeWm86qX/pOf+4ZDSbe0JcaXXb4rJjw1mA='",
    "'sha256-QuPewnJYr+SnQiTnCNHFBw99ExTsz9f8w5320PimEPw='", "'sha256-IY7YKNHjbzQ1NfAKrBZvBZohgXMtxrqB9PaqhAaT3vg='",
    "'sha256-QE7TOEDW7YIlMzvUUnm8boDWeNBN7PBbaaYJjnp34WI='",
)

CSP = ("default-src 'none'; script-src 'self'; style-src 'self' " + " ".join(ESTILOS_VIS_NETWORK) + "; img-src 'self' data:; "
       "connect-src 'self'; font-src 'self'; manifest-src 'self'; worker-src 'self'; "
       "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")

CABECERAS = {
    "content-security-policy": CSP,
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


class Seguridad:
    def __init__(self, ajustes: Ajustes):
        self.ajustes = ajustes
        self.token = secrets.token_urlsafe(32)
        self._sesiones: dict[str, dict] = {}
        self._fallos: deque[float] = deque()
        self._candado = threading.Lock()

    # ------------------------------------------------------------ token
    def guardar_token(self) -> None:
        f = self.ajustes.token_fichero
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(self.token, encoding="utf-8")

    def borrar_token(self) -> None:
        try:
            if self.ajustes.token_fichero.read_text(encoding="utf-8") == self.token:
                self.ajustes.token_fichero.unlink()
        except OSError:
            pass

    def token_valido(self, t: str) -> bool:
        return secrets.compare_digest((t or "").encode("utf-8"), self.token.encode("utf-8"))

    # ------------------------------------------------------- rate-limit
    def limitado(self) -> bool:
        with self._candado:
            limite = time.monotonic() - self.ajustes.ventana_login
            while self._fallos and self._fallos[0] < limite:
                self._fallos.popleft()
            return len(self._fallos) >= self.ajustes.intentos_login

    def fallo(self) -> None:
        with self._candado:
            self._fallos.append(time.monotonic())

    # ---------------------------------------------------------- sesiones
    def crear_sesion(self, via: str = "token") -> str:
        sid = secrets.token_urlsafe(32)
        with self._candado:
            self._sesiones[sid] = {"csrf": secrets.token_urlsafe(32), "creada": time.time(), "via": via}
            # Tope: por identidad se crea una sesion por cada peticion sin cookie valida (curl por la
            # tailnet, carreras tras reiniciar...). Un solo usuario: se tira la mas antigua (dict = orden).
            while len(self._sesiones) > MAX_SESIONES:
                self._sesiones.pop(next(iter(self._sesiones)))
        return sid

    def sesion(self, sid: str | None) -> dict | None:
        if not sid:
            return None
        with self._candado:
            return self._sesiones.get(sid)

    def cerrar(self, sid: str | None) -> None:
        with self._candado:
            self._sesiones.pop(sid or "", None)


def por_serve(scope, ajustes: Ajustes) -> bool:
    """La peticion llega por Tailscale Serve: desde 127.0.0.1, con el Host de la tailnet y por HTTPS.

    Serve conecta desde 127.0.0.1 conservando el Host (comprobado el 25/09). Cualquiera de fuera
    del PC no puede llegar aqui (la web solo escucha en 127.0.0.1); un programa del propio PC si
    podria fingirlo: riesgo aceptado por Damian (DECISIONES.md), el mismo que leer el token.

    Dos formas segun como se lance uvicorn (comprobado el 25/09):
    - Con --proxy-headers (lo que hace por defecto, y el vigia): como el par directo es 127.0.0.1
      (de confianza para uvicorn), reescribe client con X-Forwarded-For (la IP 100.x del movil)
      y scheme con X-Forwarded-Proto. Entonces scheme == "https" SOLO si el par directo era
      127.0.0.1 y dijo https: eso es Serve.
    - Sin proxy-headers: client sigue siendo 127.0.0.1 y la cabecera X-Forwarded-Proto intacta."""
    if not ajustes.tailnet_host:
        return False
    cab = Headers(scope=scope)
    if cab.get("host") not in ajustes.hosts_tailnet:
        return False
    if scope.get("scheme") == "https":
        return True
    cliente = scope.get("client") or ("", 0)
    return cliente[0] == "127.0.0.1" and cab.get("x-forwarded-proto") == "https"


def cookie_segura(scope, ajustes: Ajustes) -> bool:
    return ajustes.cookie_secure or por_serve(scope, ajustes)


CABECERA_LOGIN = "tailscale-user-login"
DUENO, AJENO = "dueno", "ajeno"


def identidad(scope, ajustes: Ajustes) -> str | None:
    """DUENO / AJENO segun el login que pone Tailscale Serve, o None si no aplica (no llega por
    Serve, no hay dueno configurado o no trae login: p. ej. un dispositivo con tag)."""
    if not ajustes.tailnet_dueno or not por_serve(scope, ajustes):
        return None
    login = (Headers(scope=scope).get(CABECERA_LOGIN) or "").strip().lower()
    if not login:
        return None
    return DUENO if secrets.compare_digest(login.encode("utf-8"),
                                           ajustes.tailnet_dueno.strip().lower().encode("utf-8")) else AJENO


def poner_cookie(cabeceras: MutableHeaders, sid: str, segura: bool) -> None:
    valor = f"{COOKIE}={sid}; HttpOnly; Path=/; SameSite=strict" + ("; Secure" if segura else "")
    cabeceras.append("set-cookie", valor)


def _pagina_rechazo(titulo: str, texto: str, codigo: int) -> Response:
    from interfaz.vistas import plantillas
    html = plantillas.get_template("rechazo.html").render(titulo=titulo, texto=texto)
    return HTMLResponse(html, status_code=codigo)


class MiddlewareSeguridad:
    """Host/Origin locales, sesion obligatoria, CSRF en metodos no seguros y cabeceras.

    No hay CORS: nunca se emite Access-Control-Allow-*, y cualquier peticion no segura
    con Origin ajeno o Sec-Fetch-Site=cross-site se rechaza.
    """

    def __init__(self, app, seguridad: Seguridad):
        self.app = app
        self.seg = seguridad

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def enviar(mensaje):
            if mensaje["type"] == "http.response.start":
                cab = MutableHeaders(scope=mensaje)
                for k, v in CABECERAS.items():
                    cab[k] = v
                if not scope["path"].startswith(PREFIJOS_PUBLICOS):
                    cab["cache-control"] = "no-store"
                else:
                    # Estaticos: revalidar siempre (304 si no cambio). Sin esto el navegador los cacheaba
                    # "a ojo" y tras actualizar seguia con el nexo.js viejo (visto el 26/09).
                    cab["cache-control"] = "no-cache"
                estado = scope.get("state", {})
                nueva = estado.get("sid_nueva")
                if nueva:
                    poner_cookie(cab, nueva, segura=True)  # solo se crean por Serve (HTTPS)
                    cab[CABECERA_SESION_NUEVA] = "1"
                # El CSRF de la sesion ACTUAL en cada respuesta: si la web se reinicio y la sesion se
                # renovo por identidad, nexo.js cambia el de la pagina sin recargar (si no, PARADA
                # daria 403 hasta recargar a mano). Solo lo lee JS del mismo origen (sin CORS).
                sesion = estado.get("sesion_csrf")
                if sesion:
                    cab[CABECERA_CSRF_RESPUESTA] = sesion
            await send(mensaje)

        rechazo = self._comprobar(scope)
        if rechazo is not None:
            await rechazo(scope, receive, enviar)
            return
        await self.app(scope, receive, enviar)

    def _comprobar(self, scope) -> Response | None:
        cab = Headers(scope=scope)
        aj = self.seg.ajustes
        metodo = scope["method"]
        ruta = scope["path"]

        if cab.get("host") not in aj.hosts:
            return Response("Host no permitido", status_code=400, media_type="text/plain")

        if metodo not in METODOS_SEGUROS:
            origen = cab.get("origin")
            if origen and origen not in aj.origenes:
                return Response("Origen no permitido", status_code=403, media_type="text/plain")
            if cab.get("sec-fetch-site") == "cross-site":
                return Response("Peticion cruzada no permitida", status_code=403, media_type="text/plain")

        if ruta in RUTAS_PUBLICAS or ruta.startswith(PREFIJOS_PUBLICOS):
            return None

        sid = cookie_parser(cab.get("cookie", "")).get(COOKIE)
        sesion = self.seg.sesion(sid)
        if sesion is None:
            quien = identidad(scope, aj)
            if quien == AJENO:
                return _pagina_rechazo(
                    "Usuario no autorizado",
                    "Tu usuario de Tailscale no es el dueño de este NEXO.", 403)
            if quien == DUENO:
                sid = self.seg.crear_sesion(via="tailnet")
                sesion = self.seg.sesion(sid)
                scope.setdefault("state", {})["sid_nueva"] = sid
        if sesion is not None:
            # Antes del CSRF: tambien el 403 tiene que llevar el token bueno (ver enviar()).
            scope.setdefault("state", {})["sesion_csrf"] = sesion["csrf"]
        if sesion is None:
            return _pagina_rechazo(
                "Sesión no iniciada",
                "Abre NEXO con interfaz\\scripts\\abrir_nexo.bat (usa el token de este arranque).",
                401)

        if metodo not in METODOS_SEGUROS:
            enviado = cab.get(CABECERA_CSRF, "")
            if not secrets.compare_digest(enviado.encode("utf-8"), sesion["csrf"].encode("utf-8")):
                return Response("CSRF inválido: recarga la página", status_code=403, media_type="text/plain")

        scope.setdefault("state", {})
        scope["state"]["sesion"] = sesion
        scope["state"]["sid"] = sid
        return None


# ------------------------------------------------------------- logs sin secretos
_TOKEN_EN_URL = re.compile(r"([?&]t=)[^&\s\"]*")


class FiltroToken(logging.Filter):
    """Tacha el token de /entrar?t=... en el log de accesos de uvicorn."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_TOKEN_EN_URL.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args)
        if isinstance(record.msg, str):
            record.msg = _TOKEN_EN_URL.sub(r"\1***", record.msg)
        return True


def instalar_filtro_logs() -> None:
    for nombre in ("uvicorn.access", "uvicorn.error"):
        registro = logging.getLogger(nombre)
        if not any(isinstance(f, FiltroToken) for f in registro.filters):
            registro.addFilter(FiltroToken())
