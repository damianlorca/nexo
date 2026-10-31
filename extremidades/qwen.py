"""Extremidad: Qwen local en Ollama (LM Studio de reserva). El obrero.

No piensa: cumple ordenes. Se le dan tareas mecanicas y de mucho
volumen, que gratis e ilimitadas en el PC salen mejor que gastando
contexto del cerebro.

Dos modelos: uno pequeno y rapido para faena mecanica, otro mayor
para cuando hace falta algo de criterio.


DOS COSAS QUE SE APRENDIERON MIDIENDO, no leyendo (11/09/2026)
-------------------------------------------------------------

1. **qwen3 razona antes de contestar, y ese razonamiento gasta
   tokens del presupuesto aunque no salga en la respuesta.** Medido
   contra Ollama: la misma pregunta de clasificar, con
   `max_tokens=20`, devolvio CADENA VACIA tras 74,8 segundos
   (finish_reason='length': se gasto los 20 tokens pensando). Con
   `max_tokens=400` contesto 'no urgente' en 9,1 segundos.

   O sea que apretar el presupuesto no es que salga mas barato: es
   que no sale nada, y encima tarda mas. De ahi `MINIMO_TOKENS`.

2. **Hay que poner timeout a mano.** El cliente de OpenAI trae 600
   segundos por defecto. Eso, detras de un puente que corta a los
   50, es la diferencia entre un error legible y un "no devuelve
   nada" sin diagnostico posible.
"""

from __future__ import annotations

import re
import unicodedata

from openai import OpenAI

from nucleo.config import valor
from nucleo.registro import logger


log = logger("extremidades.qwen")

INSTRUCCION = (
    "Eres una herramienta de ejecucion, no un asistente. "
    "Haces exactamente lo que se te pide, sin anadir comentarios, "
    "sin proponer alternativas y sin explicar tu razonamiento. "
    "Devuelves solo el resultado."
)

# Presupuesto minimo de tokens para cualquier peticion. Por debajo
# de esto qwen3 se queda pensando y devuelve vacio. Ver la nota 1.
MINIMO_TOKENS = 600

# Techo del reintento automatico. Si ni con esto contesta, es que
# pasa otra cosa y hay que mirarlo, no seguir subiendo.
TECHO_TOKENS = 8000

# Cuanto se espera antes de dar algo por muerto.
TIMEOUT_SONDEO = 5.0      # solo para ver si el runtime esta vivo
TIMEOUT_TRABAJO = 240.0   # una peticion de verdad, modelo grande incluido


def _abrir(url: str, timeout: float) -> OpenAI:
    return OpenAI(base_url=url, api_key="local", timeout=timeout, max_retries=1)


def _cliente(timeout: float = TIMEOUT_TRABAJO) -> tuple[OpenAI, bool]:
    """Devuelve el cliente y si estamos en la via de reserva.

    Ollama primero porque corre como servicio; LM Studio despues,
    que necesita la ventana abierta.
    """

    principal = valor("qwen.url", "http://localhost:11434/v1")

    try:
        # El sondeo va con timeout corto: si el runtime esta colgado,
        # mejor enterarse en 5 segundos que en diez minutos.
        _abrir(principal, TIMEOUT_SONDEO).models.list()

        return _abrir(principal, timeout), False

    except Exception:
        pass

    reserva = valor("qwen.url_reserva", "http://localhost:1234/v1")

    _abrir(reserva, TIMEOUT_SONDEO).models.list()

    log.info("Ollama no responde, uso LM Studio")

    return _abrir(reserva, timeout), True


def disponible() -> bool:
    try:
        _cliente()
        return True
    except Exception as e:
        log.warning("ningun runtime local responde: %s", e)
        return False


def modelos() -> list[str]:
    try:
        cliente, _ = _cliente(TIMEOUT_SONDEO)
        return [m.id for m in cliente.models.list().data]
    except Exception:
        return []


def pedir(
    instruccion: str,
    texto: str = "",
    criterio: bool = False,
    max_tokens: int = 2000,
    timeout: float = TIMEOUT_TRABAJO,
) -> str:
    """Manda una tarea al obrero.

    criterio=True usa el modelo grande. Por defecto va el rapido.
    """

    cliente, reserva = _cliente(timeout)

    clave = "modelo_criterio" if criterio else "modelo_obrero"

    if reserva:
        clave += "_reserva"

    modelo = valor(f"qwen.{clave}", "qwen3:4b")

    contenido = f"{instruccion}\n\n{texto}".strip()

    # Nunca por debajo del minimo: ver la nota 1 de la cabecera.
    presupuesto = max(int(max_tokens), MINIMO_TOKENS)

    if presupuesto != max_tokens:
        log.info(
            "subo max_tokens de %d a %d: por debajo de %d qwen3 se queda "
            "pensando y devuelve vacio",
            max_tokens, presupuesto, MINIMO_TOKENS,
        )

    salida, corte = _una_vuelta(cliente, modelo, contenido, presupuesto)

    # Vacio + 'length' = se lo gasto todo razonando y no llego a
    # escribir la respuesta. Se repite con mas margen en vez de
    # devolver un vacio que nadie va a interpretar como un fallo.
    if not salida and corte == "length":
        ampliado = min(presupuesto * 3, TECHO_TOKENS)

        if ampliado > presupuesto:
            log.info(
                "%s se quedo sin tokens pensando con %d. Repito con %d.",
                modelo, presupuesto, ampliado,
            )

            salida, corte = _una_vuelta(cliente, modelo, contenido, ampliado)

    if not salida:
        log.warning(
            "el modelo %s no ha devuelto nada (motivo de corte: %s). "
            "Si pone 'length', ni con %d tokens le ha dado tiempo a "
            "contestar: mirar la peticion.",
            modelo, corte, min(presupuesto * 3, TECHO_TOKENS),
        )

    return salida


def _una_vuelta(
    cliente: OpenAI, modelo: str, contenido: str, presupuesto: int
) -> tuple[str, str | None]:
    """Una llamada. Devuelve (respuesta limpia, motivo de corte)."""

    # 23/09: con Ollama se usa la API NATIVA (/api/chat) para fijar num_ctx. La via /v1
    # ignora num_ctx y cargaba qwen2.5:7b con 32K de contexto (6,9 GB, lento): medido con
    # `ollama ps` durante el revisor del turno. LM Studio (reserva) sigue por /v1.
    base = str(getattr(cliente, "base_url", ""))
    if ":11434" in base:
        import httpx
        url = base.rstrip("/").removesuffix("/v1") + "/api/chat"
        cuerpo = {
            "model": modelo, "stream": False, "keep_alive": "5m",
            "messages": [{"role": "system", "content": INSTRUCCION}, {"role": "user", "content": contenido}],
            # num_ctx 4096 por defecto: regla de CLAUDE.md (antes 8192; N02, 25/09).
            "options": {"num_ctx": int(valor("qwen.num_ctx", 4096)), "num_predict": presupuesto, "temperature": 0.2},
        }
        d = httpx.post(url, json=cuerpo, timeout=cliente.timeout).json()
        if "error" in d:
            raise RuntimeError(f"Ollama: {d['error']}")
        corte = "length" if d.get("done_reason") == "length" else "stop"
        return _sin_razonamiento((d.get("message") or {}).get("content") or ""), corte

    respuesta = cliente.chat.completions.create(
        model=modelo,
        messages=[
            {"role": "system", "content": INSTRUCCION},
            {"role": "user", "content": contenido},
        ],
        max_tokens=presupuesto,
        temperature=0.2,
    )

    eleccion = respuesta.choices[0]

    return _sin_razonamiento(eleccion.message.content or ""), eleccion.finish_reason


def _sin_razonamiento(texto: str) -> str:
    """Quita el bloque <think>...</think> si el runtime lo deja pasar.

    Ollama ya lo separa por su cuenta, pero LM Studio y otros no
    siempre, y un resumen que empieza por el monologo del modelo no
    sirve para nada.
    """

    limpio = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL | re.IGNORECASE)

    # Si se quedo a medias y nunca cerro la etiqueta, nos quedamos
    # con lo que haya despues de la apertura.
    if "<think>" in limpio.lower():
        limpio = re.split(r"<think>", limpio, flags=re.IGNORECASE)[0]

    return limpio.strip()


def resumir(texto: str, palabras: int = 150) -> str:
    return pedir(
        f"Resume el texto en {palabras} palabras como maximo, en espanol. "
        "Solo el resumen.",
        texto,
        # Holgado a proposito: el razonamiento va por dentro del mismo
        # presupuesto, asi que hay que pagarlo ademas del resumen.
        # NO subir esto "para ahorrar el reintento". Esta probado y
        # sale peor:
        #
        #   920 de partida + reintento a 2.760 -> 182,7 s
        #   2.500 de partida, sin reintento    -> 304,8 s
        #
        # qwen3 no trata el presupuesto como un tope del que salir
        # cuanto antes, sino como espacio para pensar: cuanto mas le
        # das, mas rato divaga. Se deja bajo y que pedir() reintente
        # si hace falta. (Una medida contra una, con el equipo
        # ocupado: no es concluyente, pero es la unica evidencia que
        # hay y va en contra de subirlo.)
        max_tokens=max(MINIMO_TOKENS, 600 + palabras * 8),
    )


def _normalizar(texto: str) -> str:
    """Minusculas, sin acentos y sin puntuacion, para poder comparar."""

    plano = unicodedata.normalize("NFKD", texto.lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))

    return re.sub(r"[^a-z0-9 ]+", " ", plano).strip()


def clasificar(texto: str, categorias: list[str], por_defecto: str = "") -> str:
    """Clasifica el texto en una de las categorias dadas.

    Devuelve `por_defecto` (cadena vacia si no se dice otra cosa)
    cuando el modelo no contesta con ninguna categoria reconocible.


    CUIDADO CON COMO SE ELIGE LA CATEGORIA
    --------------------------------------

    La version anterior hacia esto:

        for c in categorias:
            if c.lower() in salida.lower():
                return c

    Con categorias ['urgente', 'no urgente'] y el modelo diciendo
    "no urgente", devolvia 'urgente': LA CONTRARIA. Lo mismo con
    spam / no spam, util / inutil, accion / sin accion. Cinco de
    cinco casos probados salian invertidos, en silencio y sin dar
    ningun error.

    Ahora se compara entero primero y, si hay que buscar dentro, se
    elige la coincidencia MAS LARGA, que es la especifica.
    """

    if not categorias:
        raise ValueError("Hay que dar al menos una categoria.")

    opciones = ", ".join(categorias)

    bruto = pedir(
        f"Clasifica el texto en UNA de estas categorias: {opciones}. "
        "Responde solo con la categoria, exactamente como esta escrita, "
        "sin nada mas.",
        texto,
    )

    elegida = _elegir_categoria(bruto, categorias)

    if elegida is None:
        log.warning(
            "el modelo no ha dado ninguna categoria valida. Dijo: %r. "
            "Categorias: %s", bruto, opciones,
        )

        return por_defecto

    return elegida


def _elegir_categoria(bruto: str, categorias: list[str]) -> str | None:
    """De lo que ha dicho el modelo, saca la categoria. O None."""

    dicho = _normalizar(bruto)

    if not dicho:
        return None

    normalizadas = [(c, _normalizar(c)) for c in categorias]

    # 1. La respuesta ES una categoria, tal cual.
    for original, norm in normalizadas:
        if dicho == norm:
            return original

    # 2. La respuesta empieza por una categoria ("no urgente." o
    #    "no urgente - porque el plazo ya paso"). La mas larga gana.
    empiezan = [
        (original, norm) for original, norm in normalizadas
        if norm and (dicho == norm or dicho.startswith(norm + " "))
    ]

    if empiezan:
        return max(empiezan, key=lambda par: len(par[1]))[0]

    # 3. La categoria aparece dentro de la respuesta. Aqui es donde
    #    se equivocaba: hay que quedarse con la MAS LARGA, no con la
    #    primera de la lista. Ademas se exige que encaje en limites
    #    de palabra, para que 'util' no salte dentro de 'inutil'.
    dentro = [
        (original, norm) for original, norm in normalizadas
        if norm and re.search(rf"(?:^|\s){re.escape(norm)}(?:\s|$)", dicho)
    ]

    if dentro:
        return max(dentro, key=lambda par: len(par[1]))[0]

    return None


def lote(instruccion: str, textos: list[str], criterio: bool = False) -> list[str]:
    """La razon de existir de esta extremidad: muchos de golpe."""

    salidas = []

    for i, texto in enumerate(textos, 1):
        log.info("lote %d/%d", i, len(textos))

        try:
            salidas.append(pedir(instruccion, texto, criterio))
        except Exception as e:
            salidas.append(f"ERROR: {e}")

    return salidas
