"""T046 — contrato minimo para tratar a Qwen, Gemini, ChatGPT y Claude
como PROVEEDORES DE MODELO intercambiables.

Por que existe este archivo y por que esta en la raiz
-------------------------------------------------------
Hasta ahora cada extremidad que habla con un modelo tiene su propia
forma de llamarse: `extremidades.qwen.pedir(instruccion, texto="",
criterio=False, ...)`, `extremidades.navegador.preguntar(sitio,
prompt, espera=120)`, y Claude se dispara via
`canal.bot._cmd_ahora(argumento)` (pensado para Telegram, no para un
router). Eso esta bien para lo que ya hacen — no se ha tocado nada de
eso — pero significa que nada de fuera puede tratarlos por igual sin
conocer los detalles de cada uno.

Este modulo NO sustituye a extremidades/qwen.py, ni a
extremidades/navegador.py, ni a canal/bot.py: los ENVUELVE. Cada
Provider de aqui es un adaptador delgado que por dentro llama a esas
mismas funciones ya probadas. Cero logica nueva de negocio, cero
reescritura.

Va en la raiz del proyecto (no dentro de extremidades/) a proposito:
ClaudeProvider reutiliza `canal.bot._cmd_ahora` para no duplicar el
disparo de la Rutina, y extremidades/* nunca ha dependido de canal/*
(es al reves: canal/bot.py ya importa de extremidades para imagenes y
triaje). Meter esto dentro de extremidades/ habria invertido esa
direccion. Como proveedores.py es una capa nueva que se apoya en
nucleo + extremidades + canal sin que ninguno de los tres tenga que
depender de otro, vive al lado de ellos, no dentro de ninguno.

Lo que este archivo NO es (todavia)
------------------------------------
- No es el Model Router: nadie decide aqui que proveedor usar para
  que tarea. Eso es trabajo futuro, cuando exista el Router real.
- No cambia el Task Manager ni sus estados.
- No mete a Claude por Playwright: ClaudeProvider sigue usando en
  exclusiva el disparador de Rutinas ya existente
  (`canal.bot._cmd_ahora`), sin tocar esa funcion ni su arquitectura
  (T039 sigue igual). Playwright sobre claude.ai sigue vetado (T038).
- No es Message Bus ni cola: `enviar()` es una llamada sincrona y
  bloqueante, igual que ya eran `qwen.pedir()` y `navegador.preguntar()`.
  Ninguno de los cuatro backends de hoy soporta un async/polling de
  verdad, asi que inventar esa forma ahora seria construir para un
  futuro que no esta decidido.

Contrato minimo (Proveedor, mas abajo)
---------------------------------------
    nombre                      -> identificador corto ("qwen", "gemini"...)
    disponible() -> bool        -> comprobacion barata, sin gastar el modelo
    estado() -> dict            -> {"disponible": bool, "motivo": str}
    enviar(tarea) -> Resultado  -> la unica forma de pedirle algo
    capacidades() -> dict       -> un par de banderas + una nota en texto

No es un `CLAUDE_STATUS` completo (AVAILABLE/LIMITED/LIMIT_REACHED/...)
de la especificacion maestra: eso exigiria saber leer limites reales
de cada proveedor, cosa que hoy no esta implementada en ninguno de los
cuatro y que no hay que inventarse. Con disponible()/estado() basta
para que quien llame sepa que hacer.

IMPORTANTE — Claude no es como los otros tres: `ClaudeProvider.enviar()`
NO devuelve la respuesta de Claude. Dispara un turno de Rutina (T039):
Claude se pone a trabajar por su cuenta, con acceso a todas las
herramientas de Nexo, y el resultado llega mas tarde por Telegram o en
memoria/estado.json — no en la llamada. Un Resultado("OK", ...) de
ClaudeProvider significa "el turno se ha pedido", no "aqui esta la
respuesta". Los otros tres SI devuelven la respuesta real en la misma
llamada. No asumas que los cuatro se comportan igual solo porque
comparten el mismo contrato de metodos.

Como probarlo (de verdad, no solo `estado()`)
-----------------------------------------------
    .venv\\Scripts\\python.exe -c "import proveedores as p; print(p.QwenProvider().enviar('di hola'))"
    .venv\\Scripts\\python.exe -c "import proveedores as p; print(p.GeminiProvider().enviar('di hola'))"
    .venv\\Scripts\\python.exe -c "import proveedores as p; print(p.ChatGPTProvider().enviar('di hola'))"
    .venv\\Scripts\\python.exe -c "import proveedores as p; print(p.ClaudeProvider().estado())"

Ver tambien prueba_proveedores_vivo.py, que hace exactamente esto de
forma automatica y deja el resultado en registros/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# Estados posibles de un Resultado. Con cuatro basta para que quien
# llame sepa que hacer:
#
#   OK            -> vino una respuesta real (o, en Claude, se pidio
#                    el turno correctamente), usala/dala por hecha.
#   NOT_AVAILABLE -> este proveedor no esta configurado/listo (falta
#                    token, falta login, Chrome no esta abierto...):
#                    no es un fallo puntual, es un "todavia no puedes
#                    usar esto".
#   BLOCKED       -> esta configurado pero ahora mismo no responde
#                    (limite alcanzado, captcha, cuenta bloqueada...).
#   ERROR         -> fallo tecnico puntual (red, timeout, excepcion,
#                    respuesta vacia).
ESTADOS_RESULTADO = ("OK", "NOT_AVAILABLE", "BLOCKED", "ERROR")


@dataclass
class Resultado:
    """Lo que devuelve cualquier Provider.enviar(), sea cual sea."""

    estado: str  # uno de ESTADOS_RESULTADO
    texto: str = ""    # la respuesta real, solo si estado == "OK"
    detalle: str = ""  # explicacion legible del porque, si no es OK
    # Evidencia del proveedor (T188: modo Pensar/Pro comprobado en pantalla, metodo de lectura...).
    meta: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.estado == "OK"

    def __str__(self) -> str:  # comodo para probar a mano en consola
        if self.ok:
            return self.texto
        return f"[{self.estado}] {self.detalle or self.texto}"


@runtime_checkable
class Proveedor(Protocol):
    """El contrato minimo. Duck typing: no hace falta heredar de esto,
    cualquier objeto con estos cuatro miembros ya lo cumple — igual
    que extremidades/qwen.py no hereda de nada y aun asi encaja en el
    patron de inventario de extremidades/base.py."""

    nombre: str

    def disponible(self) -> bool: ...

    def estado(self) -> dict: ...

    def enviar(self, tarea: str) -> Resultado: ...

    def capacidades(self) -> dict: ...


# ------------------------------------------------------------- Qwen

class QwenProvider:
    """Envuelve extremidades/qwen.py. Modelo local via Ollama/LM Studio."""

    nombre = "qwen"

    def disponible(self) -> bool:
        try:
            from extremidades import qwen
            return qwen.disponible()
        except Exception:
            return False

    def estado(self) -> dict:
        ok = self.disponible()
        return {
            "disponible": ok,
            "motivo": "" if ok else "Ollama/LM Studio no responden ahora mismo.",
        }

    def enviar(self, tarea: str) -> Resultado:
        try:
            from extremidades import qwen
        except Exception as e:
            return Resultado("ERROR", detalle=f"no se pudo cargar qwen: {e}")

        if not qwen.disponible():
            return Resultado(
                "NOT_AVAILABLE",
                detalle="Ollama/LM Studio no responden ahora mismo.",
            )

        try:
            texto = qwen.pedir(tarea)
        except Exception as e:
            return Resultado("ERROR", detalle=str(e))

        if not texto or not texto.strip():
            return Resultado("ERROR", detalle="Qwen no devolvio nada.")

        return Resultado("OK", texto=texto)

    def capacidades(self) -> dict:
        return {
            "razona": False,
            "web": False,
            "gasta_plan_claude": False,
            "notas": "modelo local (Ollama), rapido, sin razonamiento profundo",
        }


# ------------------------------------------------ Gemini y ChatGPT
#
# Los dos usan exactamente el mismo mecanismo por debajo
# (extremidades/navegador.py, la misma cuenta nexoclaude@sepio.net):
# comparten una clase base y solo cambia el `sitio`.

class _ProveedorNavegador:
    """Base comun para Gemini y ChatGPT. No se instancia directamente."""

    # T147: cada envio es un tema/tarea distinto -> conversacion nueva (no arrastrar contexto).
    nueva_conversacion = True
    modo_preferido: bool | str = True  # T147: Gemini 'ampliado' por defecto; 'pro' como respaldo

    sitio: str = ""
    nombre: str = ""

    def disponible(self) -> bool:
        # Comprobacion barata y real: si el Chrome de pruebas (perfil
        # chrome-perfil) esta arriba en el puerto CDP. NO arranca
        # Chrome ni comprueba la sesion de Google/OpenAI (eso solo se
        # sabe intentando preguntar de verdad).
        try:
            from extremidades import navegador
            return navegador.activo()
        except Exception:
            return False

    def estado(self) -> dict:
        ok = self.disponible()
        return {
            "disponible": ok,
            "motivo": (
                ""
                if ok
                else "Chrome (chrome-perfil) no esta abierto. Llama a "
                     "navegador.arrancar() antes de usar este proveedor."
            ),
        }

    def enviar(self, tarea: str) -> Resultado:
        try:
            from extremidades import navegador
        except Exception as e:
            return Resultado("ERROR", detalle=f"no se pudo cargar navegador: {e}")

        if not navegador.activo():
            return Resultado("NOT_AVAILABLE", detalle=self.estado()["motivo"])

        navegador.ULTIMA_EVIDENCIA.pop(self.sitio, None)
        try:
            texto = navegador.preguntar(self.sitio, tarea, nueva=self.nueva_conversacion, modo=self.modo_preferido,
                                        url=getattr(self, '_url_continuar', None))
            self.url = navegador.ULTIMA_URL.get(self.sitio)
        except navegador.Bloqueo as e:
            # navegador._revisar_bloqueo() ya para y avisa sola ante
            # captcha/bloqueo: aqui solo se traduce a BLOCKED, nunca
            # se intenta evadir nada.
            self._al_bloqueo(e)
            return Resultado("BLOCKED", detalle=str(e))
        except navegador.LimiteUso as e:
            # T667: la web anuncia su limite de uso -> descansa hasta la hora de reinicio que muestra.
            self._al_limite(e)
            return Resultado("NOT_AVAILABLE", detalle=str(e), meta=dict(navegador.ULTIMA_EVIDENCIA.get(self.sitio) or {}))
        except navegador.FalloNavegador as e:
            # T157: la web pide iniciar sesion (sesion caducada): reintentar no sirve hasta que Damian entre. Se
            # enfria 1 h para que los turnos sigan con otros proveedores en vez de chocar en cada tarea.
            from nucleo import fallos
            if fallos.clasificar_web(e).tipo == "sesion":
                from nucleo.enfriamiento import enfriar
                enfriar(self.nombre, "sesion", f"sesion caducada: {str(e)[:120]}", segundos=fallos.ENFRIAR_SESION)
                return Resultado("NOT_AVAILABLE", detalle=f"{self.sitio}: sesion caducada ({e})",
                                 meta={"fallo": "sesion"})
            # T188/T193: modo no activo, respuesta sin verificar o Chrome ocupado. Nunca OK:
            # quien llama (router, trabajo) pasa al siguiente proveedor.
            if isinstance(e, navegador.ModoNoActivo):
                _aviso_modo(self.sitio, str(e))  # T189: ChatGPT y Gemini sin modo -> aviso en la web
            return Resultado("ERROR", detalle=f"{type(e).__name__}: {e}",
                             meta=dict(navegador.ULTIMA_EVIDENCIA.get(self.sitio) or {}))
        except Exception as e:
            return Resultado("ERROR", detalle=str(e))

        meta = dict(navegador.ULTIMA_EVIDENCIA.get(self.sitio) or {})
        if meta.get("modo_pedido") not in (None, "ninguno"):
            _aviso_modo(self.sitio, None)
        if not texto or not texto.strip():
            return Resultado("ERROR", detalle=f"{self.sitio} no devolvio nada.", meta=meta)

        return Resultado("OK", texto=texto, meta=meta)

    def capacidades(self) -> dict:
        return {
            "razona": True,
            "web": True,
            "gasta_plan_claude": False,
            "notas": "via navegador (Playwright/CDP), cuenta nexoclaude@sepio.net",
        }

    def _al_bloqueo(self, e) -> None:
        """ChatGPT y Gemini: solo BLOCKED (como siempre). Claude web lo sobreescribe."""

    def _al_limite(self, e) -> None:
        from nucleo.enfriamiento import enfriar
        enfriar(self.nombre, "limite", str(e), segundos=max(60.0, float(e.hasta) - __import__("time").time()))


def _aviso_modo(sitio: str, detalle: str | None) -> None:
    """detalle=None: el modo se verifico bien. Un fallo aqui nunca rompe el envio."""
    try:
        from nucleo import avisos
        if detalle is None:
            avisos.modo_ok(sitio)
        else:
            avisos.modo_fallido(sitio, detalle)
    except Exception:
        pass


def _continuar(self, tarea: str, url: str | None = None) -> Resultado:
    """Sigue en la MISMA conversacion: la del ultimo enviar() o `url` (T183: la guardada en la tarea)."""
    url = url or getattr(self, "url", None)
    if not url:
        return Resultado("ERROR", detalle="no hay conversacion previa que continuar")
    self._url_continuar = url
    try:
        return self.enviar(tarea)
    finally:
        self._url_continuar = None


_ProveedorNavegador.continuar = _continuar


class ClaudeWebProvider(_ProveedorNavegador):
    """Claude web de NEXO (T667, Damian 04/10): cuenta PROPIA de NEXO (plan Free) con la sesion ya iniciada en el
    Chrome de NEXO. NUNCA se tocan credenciales. Igual que ChatGPT/Gemini web: candado exclusivo, modelo y esfuerzo
    comprobados en pantalla en fallo cerrado (Sonnet 5.5 + Alto), lectura por turnos verificados.
    - Aviso de limite: enfria hasta la hora de reinicio que muestre la web.
    - Captcha o verificacion: se para ESTE proveedor (enfriamiento largo) y se avisa a Damian. Nunca se resuelve.
    Familia anthropic. En el tribunal solo como revisor extra de APELACION, al final y con cupo (nucleo/tribunal.py).
    No es ClaudeProvider (ese dispara una Rutina de Claude Code con el plan de Damian)."""

    sitio = "claude"
    nombre = "claude_web"
    PARADA_BLOQUEO = 30 * 24 * 3600   # hasta que Damian lo resuelva y lo reactive

    def disponible(self) -> bool:
        from nucleo.enfriamiento import enfriado
        return super().disponible() and enfriado(self.nombre) is None

    def estado(self) -> dict:
        from nucleo.enfriamiento import enfriado
        base = super().estado()
        e = enfriado(self.nombre)
        if base["disponible"] and e:
            return {"disponible": False, "motivo": f"En pausa ({e})"}
        return base

    def _al_bloqueo(self, e) -> None:
        from nucleo.enfriamiento import enfriar
        enfriar(self.nombre, "bloqueo", str(e), segundos=self.PARADA_BLOQUEO)
        try:
            from nucleo import avisos
            avisos.emitir("bloqueo", "Claude web de NEXO parado: captcha o verificación",
                          "Claude web (cuenta de NEXO) pide una verificación o un captcha. NEXO no lo intenta: "
                          "resuélvelo tú a mano en el Chrome de NEXO. Después reactívalo con "
                          ".venv\\Scripts\\python.exe -m nucleo.enfriamiento limpiar claude_web",
                          ruta="/proveedores", clave="claude_web:bloqueo")
        except Exception:
            pass

    def capacidades(self) -> dict:
        return {"razona": True, "web": True, "gasta_plan_claude": False,
                "notas": "via navegador (Playwright/CDP), cuenta propia de NEXO en claude.ai (plan Free); "
                         "solo revisor extra de apelacion del tribunal (T667)"}


class GeminiProvider(_ProveedorNavegador):
    sitio = "gemini"
    nombre = "gemini"


class ChatGPTProvider(_ProveedorNavegador):
    sitio = "chatgpt"
    nombre = "chatgpt"


# ------------------------------------------------------------ Claude
#
# Reutiliza tal cual canal.bot._cmd_ahora, que ya sabe leer el token
# de la rutina, disparar el POST y traducir los codigos de respuesta a
# texto en espanol (ya es una funcion pura pensada para probarse sin
# Telegram real, ver prueba_comandos_bot.py). No se toca esa funcion
# ni la arquitectura de Rutinas (T039): este Provider solo CLASIFICA
# el texto que ya devuelve, para que quien llame no tenga que parsear
# espanol.

class ClaudeProvider:
    """Envuelve el disparador de Rutinas de canal/bot.py (T039).
    NO usa la API de pago de Claude ni Playwright sobre claude.ai
    (T038 sigue cerrado). Ver el aviso del docstring del modulo:
    enviar() no devuelve la respuesta de Claude, solo confirma que el
    turno se ha pedido."""

    nombre = "claude"

    def disponible(self) -> bool:
        try:
            from nucleo.config import valor
        except Exception:
            return False

        return bool(valor("rutina.token_api", "")) and bool(valor("rutina.id", ""))

    def estado(self) -> dict:
        ok = self.disponible()
        return {
            "disponible": ok,
            "motivo": (
                ""
                if ok
                else "Falta configurar secretos.toml [rutina] "
                     "(token_api / id) — ver /ahora en Telegram, T039."
            ),
        }

    def enviar(self, tarea: str) -> Resultado:
        if not self.disponible():
            return Resultado(
                "NOT_AVAILABLE",
                detalle="Falta el token de la rutina en secretos.toml "
                        "([rutina] token_api / id). Ver T039.",
            )

        try:
            from canal import bot
        except Exception as e:
            return Resultado("ERROR", detalle=f"no se pudo cargar canal.bot: {e}")

        try:
            texto = bot._cmd_ahora(tarea)
        except Exception as e:
            return Resultado("ERROR", detalle=str(e))

        # _cmd_ahora nunca lanza para estos casos: siempre devuelve
        # texto humano en espanol, y se distingue por como empieza.
        if texto.startswith("📨"):
            return Resultado("OK", texto=texto)

        if texto.startswith("Todavía no puedo pedir un turno inmediato"):
            return Resultado("NOT_AVAILABLE", detalle=texto)

        if "límite diario" in texto:
            return Resultado("BLOCKED", detalle=texto)

        # "No he podido avisar..." (red) o "La rutina no se ha podido
        # disparar..." (4xx/5xx de la API) caen aqui.
        return Resultado("ERROR", detalle=texto)

    def capacidades(self) -> dict:
        return {
            "razona": True,
            "web": False,
            "gasta_plan_claude": True,
            "notas": (
                "via disparador de Rutinas (Claude Code), no API de pago. "
                "Dispara un turno completo con acceso a las herramientas de "
                "Nexo; no da la respuesta en la misma llamada como los otros "
                "tres proveedores."
            ),
        }


# ------------------------------------------------------- Gemini por API
#
# T136 (23/09): API oficial con plan gratuito, clave de la cuenta de NEXO
# en secretos.toml [gemini] api_key. Cumple los terminos (a diferencia de
# automatizar la web) y no depende del DOM. La clave va SIEMPRE en la
# cabecera x-goog-api-key, nunca en la URL. Ante 503 (demanda) o 429
# (cuota) prueba el siguiente modelo de la lista.

MODELOS_GEMINI_API = ("gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-flash-latest")


class GeminiAPIProvider:
    nombre = "gemini_api"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"

    def __init__(self, modelos: tuple[str, ...] = MODELOS_GEMINI_API, timeout: float = 60.0,
                 rondas: int = 3, espera: float = 20.0):
        self.modelos = modelos
        self.rondas = rondas
        self.espera = espera
        self.timeout = timeout
        self.ultimo_modelo = ""

    def _clave(self) -> str:
        try:
            from nucleo.config import valor
            k = valor("gemini.api_key", "") or ""
        except Exception:
            return ""
        return "" if ("PEGA_AQUI" in k or "AQUI_TU" in k) else k

    def disponible(self) -> bool:
        from nucleo.enfriamiento import enfriado
        return bool(self._clave()) and enfriado(self.nombre) is None

    def estado(self) -> dict:
        from nucleo.enfriamiento import enfriado
        if not self._clave():
            return {"disponible": False, "motivo": "Falta secretos.toml [gemini] api_key (T136)."}
        e = enfriado(self.nombre)
        return {"disponible": e is None, "motivo": f"En enfriamiento ({e})" if e else ""}

    def enviar(self, tarea: str, buscar: bool = False) -> Resultado:
        """buscar=True activa la busqueda de Google (grounding) de la API."""
        clave = self._clave()
        if not clave:
            return Resultado("NOT_AVAILABLE", detalle=self.estado()["motivo"])
        import httpx
        from nucleo import fallos
        cuerpo = {"contents": [{"parts": [{"text": tarea}]}]}
        if buscar:
            cuerpo["tools"] = [{"google_search": {}}]
        # T157: tabla de fallos comun (nucleo/fallos.py). 429/503 -> siguiente modelo; todos -> enfriar; clave mala
        # (400 API_KEY_INVALID, 401, 403) -> BLOCKED y enfriado; 404 -> modelo retirado (modelos_estado).
        r = fallos.cascada(self.nombre, self.modelos, self.rondas, self.espera,
                           pedir=lambda m: httpx.post(self.URL.format(m=m), headers={"x-goog-api-key": clave},
                                                      json=cuerpo, timeout=self.timeout),
                           leer=lambda j: "".join(x.get("text", "") for x in j["candidates"][0]["content"]["parts"]))
        if r.ok:
            self.ultimo_modelo = r.meta.get("modelo", "")
        return r

    def capacidades(self) -> dict:
        return {"razona": True, "web": False, "gasta_plan_claude": False,
                "notas": "API oficial Gemini, plan gratuito, cuenta nexoclaude@sepio.net (T136)."}


# --------------------------------------------------------- Groq por API
#
# T162 (24/09): API oficial de Groq, plan gratuito, compatible con OpenAI.
# Aporta un generador/revisor de API que NO es Gemini ni web: cuando Gemini API
# da 429 y el navegador no esta activo (caso real del turno 24/09 03:32, la tarea
# se quedaba sin generador), Groq es el respaldo. Clave en secretos.toml [groq] api_key.
# La clave va SIEMPRE en la cabecera Authorization: Bearer, nunca en la URL.
# Modelos por defecto (confirmar IDs exactos al crear la cuenta): gpt-oss y qwen.

# 04/10 (T667): qwen/qwen3-32b retirado de Groq (HTTP 404) -> qwen/qwen3.8-27b (prueba de banco del tribunal).
MODELOS_GROQ = ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b")


class GroqProvider:
    nombre = "groq"
    URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, modelos: tuple[str, ...] | None = None, timeout: float = 60.0,
                 rondas: int = 2, espera: float = 20.0, incluir_fuera_de_uso: bool = False):
        # secretos.toml [groq] modelos = ["...", "..."] sobreescribe la lista por defecto.
        if modelos is None:
            try:
                from nucleo.config import valor
                modelos = tuple(valor("groq.modelos", []) or MODELOS_GROQ)
            except Exception:
                modelos = MODELOS_GROQ
        self.modelos = tuple(modelos)
        self.rondas = rondas
        self.espera = espera
        self.timeout = timeout
        self.ultimo_modelo = ""
        self.incluir_fuera_de_uso = incluir_fuera_de_uso   # T320: solo el sondeo prueba los retirados

    def _vivos(self) -> tuple[str, ...]:
        """Modelos en uso: los retirados o sin servicio (nucleo.modelos_estado) se saltan."""
        if self.incluir_fuera_de_uso:
            return self.modelos
        from nucleo import modelos_estado
        return modelos_estado.en_uso(self.nombre, self.modelos)

    def _clave(self) -> str:
        try:
            from nucleo.config import valor
            k = valor("groq.api_key", "") or ""
        except Exception:
            return ""
        return "" if ("PEGA_AQUI" in k or "AQUI_TU" in k) else k

    def disponible(self) -> bool:
        from nucleo.enfriamiento import enfriado
        return bool(self._clave()) and bool(self._vivos()) and enfriado(self.nombre) is None

    def estado(self) -> dict:
        from nucleo.enfriamiento import enfriado
        if not self._clave():
            return {"disponible": False, "motivo": "Falta secretos.toml [groq] api_key (T162)."}
        e = enfriado(self.nombre)
        return {"disponible": e is None, "motivo": f"En enfriamiento ({e})" if e else ""}

    def enviar(self, tarea: str) -> Resultado:
        clave = self._clave()
        if not clave:
            return Resultado("NOT_AVAILABLE", detalle=self.estado()["motivo"])
        import httpx
        from nucleo import fallos
        modelos = self._vivos()
        if not modelos:
            return Resultado("NOT_AVAILABLE", detalle="todos los modelos de Groq estan retirados o sin servicio (T320)")
        r = fallos.cascada(self.nombre, modelos, self.rondas, self.espera,   # T157: tabla de fallos comun
                           pedir=lambda m: httpx.post(self.URL, headers={"Authorization": f"Bearer {clave}"},
                                                      json={"model": m, "messages": [{"role": "user", "content": tarea}]},
                                                      timeout=self.timeout),
                           leer=lambda j: j["choices"][0]["message"]["content"])
        if r.ok:
            self.ultimo_modelo = r.meta.get("modelo", "")
        return r

    def capacidades(self) -> dict:
        return {"razona": True, "web": False, "gasta_plan_claude": False,
                "notas": "API Groq (OpenAI-compatible), plan gratuito, LPU rapido. Respaldo de Gemini API (T162)."}


# ---------------------------------------------------------------- NVIDIA build.nvidia.com (T227, 27/09)
# API OpenAI-compatible del catalogo de build.nvidia.com: gratis para desarrollo con limite de peticiones
# (~40 RPM por modelo). Damian 27/09: SOLO modelos gratuitos, nada de NVIDIA AI Enterprise de pago; por
# eso hay lista blanca y secretos.toml [nvidia] modelos solo puede elegir DENTRO de ella.
# NVIDIA registra entradas y salidas: solo textos no sensibles (el auditor ya bloquea datos privados).
# Uso principal: revisor independiente con gpt-oss-20b en la nube (T182 sin cargar 13 GB en el PC).
# Clave en secretos.toml [nvidia] api_key (nvapi-...), siempre en la cabecera, nunca en la URL ni en logs.
# T261 (28/09): mini-banco por rol (revisor/autor/clasificador) contra el catalogo real; resultados y
# los descartados (lentos o sin respuesta en el momento de probar) en documentacion/proveedores/
# NVIDIA_MODELOS_GRATIS.md. Los tres añadidos son de otra familia que gpt-oss (independencia real de
# revision): nemotron-3-super-120b-a12b (NVIDIA, rapido y fiable en los tres roles), mistral-nemotron
# (Mistral, fiable en revisor/autor) y glm-5.3-flash (Z.ai; modelo de razonamiento: necesita el
# max_tokens por defecto de este proveedor, no uno pequeño, o se queda sin texto final).
# 04/10 (T667, banco herramientas_nube/_banco_tribunal_0410.py): FUERA mistral-nemotron (HTTP 410, retirado) y
# glm-5.3-flash (sin respuesta en 120 s); DENTRO nemotron-3-ultra-550b (Free Endpoint, banco OK; solo apelacion).
# 24/10 (bloque 18; prueba del coordinador en registros/probar_nvidia_1024.txt + etiqueta "Free Endpoint" de
# build.nvidia.com comprobada a mano): DENTRO los que responden hoy; nemotron-3.5-super-vl es de VISION (lee los
# fotogramas de los reels antes que Gemini). super-120b sigue con la etiqueta pero da 404: lo saca modelos_estado.
MODELOS_NVIDIA_GRATIS = ("openai/gpt-oss-20b", "openai/gpt-oss-120b", "nvidia/nemotron-3-super-120b-a12b",
                         "nvidia/nemotron-3-ultra-550b-a55b", "nvidia/nemotron-3.5-lightning-30b-a3b",
                         "minimaxai/minimax-m3.1-flash", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
                         "stepfun-ai/step-5-preview", "nvidia/nemotron-3.5-super-vl-120b-a12b")
MODELO_NVIDIA_VISION = "nvidia/nemotron-3.5-super-vl-120b-a12b"


def modelos_nvidia_config() -> tuple[str, ...]:
    """config nvidia.modelos dentro de la lista blanca, en su orden (T1039: ultra el primero desde el 24/10)."""
    try:
        from nucleo.config import valor
        modelos = tuple(valor("nvidia.modelos", []) or ())
    except Exception:
        modelos = ()
    return tuple(m for m in modelos if m in MODELOS_NVIDIA_GRATIS) or MODELOS_NVIDIA_GRATIS[:1]


def modelo_nvidia_principal() -> str:
    """T1039: el primer modelo VIVO (nucleo.modelos_estado) de config nvidia.modelos, sin nombres fijos en el codigo.
    Si ninguno sigue vivo, el primero de la config (el proveedor dira que no esta disponible)."""
    lista = modelos_nvidia_config()
    try:
        from nucleo import modelos_estado
        vivos = modelos_estado.en_uso(NvidiaProvider.nombre, lista)
    except Exception:
        vivos = ()
    return (vivos or lista)[0]


def id_corto_nvidia(modelo: str) -> str:
    """'nvidia/nemotron-3-ultra-550b-a55b' -> 'nvidia:nemotron-3-ultra' (el id que ya usaban tribunal e implementador)."""
    import re
    return "nvidia:" + re.sub(r"-\d+(\.\d+)?b(-a\d+(\.\d+)?b)?$", "", modelo.rsplit("/", 1)[-1])


class NvidiaProvider:
    nombre = "nvidia"
    URL = "https://integrate.api.nvidia.com/v1/chat/completions"

    def __init__(self, modelos: tuple[str, ...] | None = None, timeout: float = 120.0,
                 rondas: int = 1, espera: float = 20.0, max_tokens: int = 4096, incluir_fuera_de_uso: bool = False):
        if modelos is None:
            try:
                from nucleo.config import valor
                modelos = tuple(valor("nvidia.modelos", []) or MODELOS_NVIDIA_GRATIS[:1])
            except Exception:
                modelos = MODELOS_NVIDIA_GRATIS[:1]
        self.modelos = tuple(m for m in modelos if m in MODELOS_NVIDIA_GRATIS)
        self.rechazados = tuple(m for m in modelos if m not in MODELOS_NVIDIA_GRATIS)
        self.rondas, self.espera, self.timeout, self.max_tokens = rondas, espera, timeout, max_tokens
        self.ultimo_modelo = ""
        self.incluir_fuera_de_uso = incluir_fuera_de_uso   # T320: solo el sondeo prueba los retirados

    def _vivos(self) -> tuple[str, ...]:
        """Modelos en uso: los retirados o sin servicio (nucleo.modelos_estado) se saltan."""
        if self.incluir_fuera_de_uso:
            return self.modelos
        from nucleo import modelos_estado
        return modelos_estado.en_uso(self.nombre, self.modelos)

    def _clave(self) -> str:
        try:
            from nucleo.config import valor
            k = valor("nvidia.api_key", "") or ""
        except Exception:
            return ""
        return "" if ("PEGA_AQUI" in k or "AQUI_TU" in k) else k

    def disponible(self) -> bool:
        from nucleo.enfriamiento import enfriado
        return bool(self._clave()) and bool(self._vivos()) and enfriado(self.nombre) is None

    def estado(self) -> dict:
        from nucleo.enfriamiento import enfriado
        if not self._clave():
            return {"disponible": False, "motivo": "Falta secretos.toml [nvidia] api_key (T227)."}
        if not self.modelos:
            return {"disponible": False, "motivo": "Ningun modelo de la lista blanca gratuita (T227)."}
        e = enfriado(self.nombre)
        return {"disponible": e is None, "motivo": f"En enfriamiento ({e})" if e else ""}

    def enviar(self, tarea: str) -> Resultado:
        clave = self._clave()
        if not clave or not self.modelos:
            return Resultado("NOT_AVAILABLE", detalle=self.estado()["motivo"])
        import httpx
        from nucleo import fallos
        modelos = self._vivos()
        if not modelos:
            return Resultado("NOT_AVAILABLE", detalle="todos los modelos de NVIDIA estan retirados o sin servicio (T320)")
        # T157: tabla de fallos comun. 402 (sin creditos) = terminal y enfriado largo; 429 de ritmo = enfriado corto.
        r = fallos.cascada(self.nombre, modelos, self.rondas, self.espera,
                           pedir=lambda m: httpx.post(self.URL, headers={"Authorization": f"Bearer {clave}",
                                                                         "Accept": "application/json"},
                                                      json={"model": m, "messages": [{"role": "user", "content": tarea}],
                                                            "max_tokens": self.max_tokens}, timeout=self.timeout),
                           leer=lambda j: j["choices"][0]["message"]["content"])
        if r.ok:
            self.ultimo_modelo = r.meta.get("modelo", "")
        return r

    def capacidades(self) -> dict:
        return {"razona": True, "web": False, "gasta_plan_claude": False,
                "notas": "API NVIDIA build.nvidia.com (OpenAI-compatible), solo modelos gratuitos (lista blanca). "
                         "Revisor independiente con gpt-oss-20b (T227/T182). Registra entradas: nada sensible."}


# ---------------------------------------------------------------- OpenRouter (T162, Damian 04/10)
# API OpenAI-compatible con modelos GRATIS de familias que no teniamos. La cuenta tiene limite de 0 USD y FALLA CERRADO:
# solo se llama a un modelo cuyo id termina en ":free" (lista blanca + comprobacion en cada peticion). Un modelo que
# no sea :free no se llama nunca, venga de la lista, de secretos.toml [openrouter] modelos o de quien sea.
# Los modelos de la lista salen del banco del 04/10 (herramientas_nube/_banco_openrouter_0410.py); OpenRouter
# retira y mete modelos :free cada semana: nucleo/modelos_estado.py (T320) saca los retirados solo.
# Clave en secretos.toml [openrouter] api_key (sk-or-...), siempre en la cabecera; NUNCA en logs, URL ni detalles.
# 24/10: fuera inkling:free (403: solo responde dentro de herramientas de programacion).
MODELOS_OPENROUTER_FREE = ("poolside/laguna-s-2.1:free", "cohere/north-mini-code:free")


def es_modelo_free(modelo: str) -> bool:
    return isinstance(modelo, str) and modelo.endswith(":free") and len(modelo) > len(":free")


class OpenRouterProvider:
    nombre = "openrouter"
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, modelos: tuple[str, ...] | None = None, timeout: float = 120.0,
                 rondas: int = 1, espera: float = 20.0, max_tokens: int = 4096, incluir_fuera_de_uso: bool = False):
        if modelos is None:
            try:
                from nucleo.config import valor
                modelos = tuple(valor("openrouter.modelos", []) or MODELOS_OPENROUTER_FREE)
            except Exception:
                modelos = MODELOS_OPENROUTER_FREE
        self.modelos = tuple(m for m in modelos if es_modelo_free(m))          # fail-closed
        self.rechazados = tuple(m for m in modelos if not es_modelo_free(m))   # no :free: nunca se llaman
        self.rondas, self.espera, self.timeout, self.max_tokens = rondas, espera, timeout, max_tokens
        self.ultimo_modelo = ""
        self.incluir_fuera_de_uso = incluir_fuera_de_uso

    def _vivos(self) -> tuple[str, ...]:
        if self.incluir_fuera_de_uso:
            return self.modelos
        from nucleo import modelos_estado
        return modelos_estado.en_uso(self.nombre, self.modelos)

    def _clave(self) -> str:
        try:
            from nucleo.config import valor
            k = valor("openrouter.api_key", "") or ""
        except Exception:
            return ""
        return "" if ("PEGA_AQUI" in k or "AQUI_TU" in k) else k

    def disponible(self) -> bool:
        from nucleo.enfriamiento import enfriado
        return bool(self._clave()) and bool(self._vivos()) and enfriado(self.nombre) is None

    def estado(self) -> dict:
        from nucleo.enfriamiento import enfriado
        if not self._clave():
            return {"disponible": False, "motivo": "Falta secretos.toml [openrouter] api_key (T162)."}
        if not self.modelos:
            return {"disponible": False, "motivo": "Ningun modelo con id :free (fail-closed, T162)."}
        e = enfriado(self.nombre)
        return {"disponible": e is None, "motivo": f"En enfriamiento ({e})" if e else ""}

    def enviar(self, tarea: str) -> Resultado:
        clave = self._clave()
        if not clave or not self.modelos:
            return Resultado("NOT_AVAILABLE", detalle=self.estado()["motivo"])
        import httpx
        from nucleo import fallos
        modelos = self._vivos()
        if not modelos:
            return Resultado("NOT_AVAILABLE", detalle="todos los modelos de OpenRouter estan retirados o sin servicio (T320)")

        def solo_free(m):   # segunda barrera: aunque alguien toque self.modelos despues de crear el objeto
            return None if es_modelo_free(m) else Resultado("BLOCKED", detalle=f"{m}: no es :free, no se llama (fail-closed)")
        # T157: tabla de fallos comun; el 429 "free-models-per-day" es cuota diaria (enfriado largo).
        r = fallos.cascada(self.nombre, modelos, self.rondas, self.espera, antes=solo_free,
                           pedir=lambda m: httpx.post(self.URL, headers={"Authorization": f"Bearer {clave}",
                                                                         "Accept": "application/json", "X-Title": "NEXO"},
                                                      json={"model": m, "messages": [{"role": "user", "content": tarea}],
                                                            "max_tokens": self.max_tokens}, timeout=self.timeout),
                           leer=lambda j: j["choices"][0]["message"]["content"])
        if r.ok:
            self.ultimo_modelo = r.meta.get("modelo", "")
        return r

    def capacidades(self) -> dict:
        return {"razona": True, "web": False, "gasta_plan_claude": False,
                "notas": "API OpenRouter (OpenAI-compatible), SOLO modelos con id :free (fail-closed), cuenta con limite "
                         "de 0 USD. Familias nuevas para el tribunal (T162). Registra entradas: nada sensible."}


# T078: medir cada envio real de cada proveedor (registros/uso_proveedores.jsonl).
from nucleo.uso_proveedores import medido as _medido  # noqa: E402

for _clase in (QwenProvider, GeminiProvider, ChatGPTProvider, ClaudeProvider, GeminiAPIProvider, GroqProvider,
               NvidiaProvider, OpenRouterProvider):
    if "enviar" in _clase.__dict__:
        _clase.enviar = _medido(_clase.__dict__["enviar"])
_ProveedorNavegador.enviar = _medido(_ProveedorNavegador.__dict__["enviar"])

# T549: interruptor manual por proveedor (nucleo/enfriamiento.apagar; Damian, desde la web: Proveedores). Va por
# FUERA de _medido: un proveedor apagado ni se llama ni cuenta como uso. Cubre tambien a quien llama sin preguntar
# disponible() (el router con ChatGPT y Gemini web).
from functools import wraps as _wraps  # noqa: E402

from nucleo.enfriamiento import apagado as _apagado  # noqa: E402


def _con_interruptor(clase) -> None:
    enviar, disponible, estado = clase.enviar, clase.disponible, clase.estado

    @_wraps(enviar)
    def enviar_(self, *a, **k):
        motivo = _apagado(self.nombre)
        if motivo:
            return Resultado("NOT_AVAILABLE", detalle=f"{self.nombre}: {motivo}")
        return enviar(self, *a, **k)

    @_wraps(disponible)
    def disponible_(self) -> bool:
        return _apagado(self.nombre) is None and disponible(self)

    @_wraps(estado)
    def estado_(self) -> dict:
        motivo = _apagado(self.nombre)
        if motivo:
            return {"disponible": False, "motivo": motivo[:1].upper() + motivo[1:], "apagado": True}
        return estado(self)

    clase.enviar, clase.disponible, clase.estado = enviar_, disponible_, estado_


CON_INTERRUPTOR = (QwenProvider, ClaudeWebProvider, GeminiProvider, ChatGPTProvider, ClaudeProvider, GeminiAPIProvider,
                   GroqProvider, NvidiaProvider, OpenRouterProvider)
for _clase in CON_INTERRUPTOR:
    _con_interruptor(_clase)
