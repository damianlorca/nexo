"""Router minimo, determinista y por reglas explicitas (T067 + T044).

Primera ruta autonoma real y pequeña de Nexo, tal y como la definio Damian
el 13/09: TAREA -> CLASIFICACION -> DECISION -> PROVEEDOR -> EJECUCION ->
VERIFICACION -> FALLO/ESCALADO -> EVIDENCIA, de principio a fin, sin que
una sesion de Claude tenga que intervenir manualmente en cada paso.

T044 (13/09, ronda siguiente a T067): cuando Qwen agota su intento y su
unico reintento sin conseguir un resultado que supere la verificacion
mecanica, el Router prueba UNA vez con Gemini (`proveedores.GeminiProvider`,
ya construido y probado en T046) antes de escalar. Es el unico cambio de
esta ronda: mismas dos categorias de siempre (`resumen`, `extraccion`),
mismas reglas fijas, mismos verificadores -- Gemini es un fallback, no un
proveedor nuevo que el Router aprenda a elegir por su cuenta. Si Qwen
resuelve la tarea, Gemini no se llama nunca.

T082 (23/09): si Gemini TAMBIEN falla, se prueba UNA vez con ChatGPT
(`proveedores.ChatGPTProvider`, mismo mecanismo de navegador que Gemini)
antes de escalar. Mismas reglas: un intento, sin reintento, misma
verificacion mecanica.

H16 (26/09, decidido por Damian): el orden pasa a Qwen -> ChatGPT ->
Gemini (API si hay clave, luego web) -> escalado. ChatGPT responde
mejor. Mismo trato para todos: un intento, sin reintento, misma
verificacion mecanica.

Por que vive en la raiz (junto a proveedores.py) y no en nucleo/
------------------------------------------------------------------
Este modulo depende de proveedores.py (T046) y, a traves de el, de
extremidades/. nucleo/ es la capa base de la que depende todo lo demas;
meter aqui un modulo que depende de algo construido POR ENCIMA de nucleo
invertiria esa direccion (el mismo razonamiento que ya explica por que
proveedores.py vive en la raiz y no dentro de extremidades/, ver su
propio docstring). Router.py se apoya en nucleo.registro (evidencia) +
proveedores.py (ejecucion) + extremidades.qwen (clasificacion), igual
que proveedores.py se apoya en nucleo + extremidades + canal.

Que es y que NO es
-------------------
Es un Router minimo por reglas fijas (si/entonces), sin aprendizaje, que
usa piezas YA CONSTRUIDAS Y PROBADAS:
  - proveedores.QwenProvider (T046) como proveedor por defecto.
  - proveedores.GeminiProvider (T046) como UNICO fallback, solo cuando
    Qwen agota sus intentos en `resumen`/`extraccion` -- nunca como
    proveedor de primera eleccion, nunca en otras categorias.
  - extremidades.qwen.clasificar()/pedir() como el obrero real (T050: la
    clasificacion y el resumen/extraccion cortos son, segun la evidencia
    de FAST, las funciones con mas fiabilidad de qwen2.5:7b).
  - nucleo.registro.registrar_evidencia() como registro de evidencia
    (Pieza 1), encadenado con un unico execution_id por llamada a
    procesar().

NO es el Router V3 de T053/FASE4_E (10 tipos de decision, aprendizaje
por evidencia), ni un watchdog general, ni un pipeline multi-IA. No
anade categorias nuevas ni un Model Router que elija entre Qwen/Gemini
por criterio -- Gemini solo entra cuando Qwen ya ha fallado dos veces
(intento + reintento) en una tarea que de todas formas ya iba a Qwen.
No esta conectado a canal/bot.py ni a ningun flujo de Telegram en vivo
-- sigue siendo un modulo de produccion aislado y controlado, probado
con prueba_router_minimo.py.

Mapeo del ciclo pedido por Damian sobre el vocabulario YA EXISTENTE de
nucleo/registro.py (FASES_VALIDAS/ORIGENES_VALIDOS/ROLES_VALIDOS, sin
anadir ningun valor nuevo):
  TAREA          -> fase "peticion"
  CLASIFICACION +
  DECISION       -> fase "decision" (categoria elegida y ruta resultante)
  PROVEEDOR +
  EJECUCION      -> fase "ejecucion" (una entrada por intento, con
                    `proveedor` = "qwen" o "gemini" segun quien la hizo)
  VERIFICACION   -> fase "verificacion" (tambien con `proveedor`, para
                    poder distinguir la de Qwen de la de Gemini)
  FALLO          -> fase "error" (fallo del proveedor) y/o "reintento"
                    (reintento de Qwen tras verificacion fallida, O el
                    cambio de proveedor a Gemini tras agotar Qwen -- se
                    distinguen por `accion`/`proveedor`, sin fase nueva)
  ESCALADO       -> fase "escalado" (Qwen Y Gemini agotados/fallidos, o
                    la categoria no es enrutable, o la peticion esta mal
                    formada)
  EXITO          -> fase "resultado" (con `proveedor` = quien la resolvio)

Watchdog minimo (no general): el timeout de Qwen lo pone ya
extremidades.qwen.pedir() (TIMEOUT_TRABAJO=240s, reutilizado tal cual);
el de Gemini lo pone navegador.preguntar() (tambien reutilizado tal
cual, sin tocar extremidades/navegador.py). Este modulo solo anade un
tope fijo de 1 reintento para Qwen y, si eso tampoco basta, exactamente
1 intento con Gemini antes de escalar -- nunca un bucle sin fin.
"""

from __future__ import annotations

import json
import re
import time

from nucleo.registro import logger, nuevo_execution_id, registrar_evidencia
from proveedores import ChatGPTProvider, GeminiAPIProvider, GeminiProvider, QwenProvider

log = logger("router")

# Categorias que sabe clasificar este Router. "otro" es el cajon de
# desague deliberado: cualquier tarea que no sea resumen/extraccion se
# escala sin gastar una llamada al modelo (regla explicita, no aprendida).
CATEGORIAS_TAREA = ["resumen", "extraccion", "otro"]

# De esas categorias, las unicas que este Router sabe procesar (con Qwen
# primero y Gemini como fallback). Elegidas por Damian el 13/09 segun la
# evidencia de T050 (FAST: qwen2.5:7b 12/12 correcto en resumen corto y
# en extraccion estructurada corta). No incluye razonamiento complejo,
# planificacion autonoma ni coding abierto: eso queda explicitamente
# fuera de esta primera ruta.
RUTAS_QWEN = frozenset({"resumen", "extraccion"})

# Tope fijo de reintentos SOLO para Qwen (watchdog minimo, no general).
# Gemini, como fallback, recibe exactamente 1 intento -- no tiene su
# propio reintento: si falla, se escala.
MAX_REINTENTOS_QWEN = 1


def _preview(texto: str, n: int = 160) -> str:
    texto = (texto or "").strip().replace("\n", " ")
    return texto if len(texto) <= n else texto[: n - 1] + "…"


def _extraer_json(texto: str) -> dict | None:
    """Intenta parsear un JSON. Si el modelo anadio texto alrededor,
    busca el primer bloque {...} y lo intenta tambien. Nunca lanza."""

    texto = (texto or "").strip()

    try:
        dato = json.loads(texto)
        return dato if isinstance(dato, dict) else None
    except Exception:
        pass

    bloque = re.search(r"\{.*\}", texto, flags=re.DOTALL)

    if not bloque:
        return None

    try:
        dato = json.loads(bloque.group(0))
        return dato if isinstance(dato, dict) else None
    except Exception:
        return None


def _verificar_resumen(original: str, resultado: str) -> tuple[bool, str]:
    """Verificacion mecanica de un resumen: no vacio, distinto del
    original y con menos palabras que el original.

    Sencilla a proposito: no juzga fidelidad de contenido (¿inventa
    datos?). T050 ya documento que eso no tiene comprobacion automatica
    fiable -- inventar una aqui seria peor que no tenerla. Reutilizada
    tal cual de T067 para Qwen Y para Gemini -- el mismo criterio para
    cualquier proveedor que responda a esta categoria.
    """

    resultado = (resultado or "").strip()

    if not resultado:
        return False, "resultado vacio"

    if resultado.strip() == (original or "").strip():
        return False, "el resultado es identico al texto original (no resumio nada)"

    palabras_in = len((original or "").split())
    palabras_out = len(resultado.split())

    if palabras_in > 0 and palabras_out >= palabras_in:
        return False, (
            f"el resumen ({palabras_out} palabras) no es mas corto que el "
            f"original ({palabras_in} palabras)"
        )

    return True, f"resumen valido: {palabras_out}/{palabras_in} palabras"


def _verificar_extraccion(claves: list[str], resultado: str) -> tuple[bool, str]:
    """Verificacion mecanica de una extraccion: el resultado debe ser un
    JSON valido con EXACTAMENTE las claves pedidas, ni de mas ni de
    menos. Reutilizada tal cual de T067 para Qwen Y para Gemini."""

    dato = _extraer_json(resultado)

    if dato is None:
        return False, "el resultado no es un JSON valido"

    esperadas = set(claves)
    obtenidas = set(dato.keys())

    if obtenidas != esperadas:
        faltan = esperadas - obtenidas
        sobran = obtenidas - esperadas
        detalle = []
        if faltan:
            detalle.append(f"faltan: {sorted(faltan)}")
        if sobran:
            detalle.append(f"sobran: {sorted(sobran)}")
        return False, "claves incorrectas (" + "; ".join(detalle) + ")"

    return True, f"JSON valido con las {len(esperadas)} claves esperadas"


def procesar(
    texto: str,
    claves_extraccion: list[str] | None = None,
    solo_local: bool = False,
) -> dict:
    """Ciclo completo TAREA -> ... -> EVIDENCIA para una tarea.

    `texto` es la peticion en lenguaje natural, incluyendo ya el
    contenido a resumir o de donde extraer datos (igual que ya reciben
    instruccion+contenido extremidades.qwen.pedir()). `claves_extraccion`
    es obligatorio cuando la tarea se clasifique como "extraccion" (son
    las claves que se le exige al proveedor en el JSON, y con las que se
    verifica mecanicamente lo que devuelva); si falta, se escala sin
    llamar a ningun modelo (peticion mal formada).

    Devuelve un dict con al menos `execution_id`, `estado` ("OK" o
    "ESCALADO") y `categoria`; si `estado` es "OK" incluye tambien
    `proveedor` (quien la resolvio: "qwen" o, tras el fallback, "gemini")
    y `texto`. Nunca lanza: cualquier fallo termina en escalado,
    registrado como evidencia, nunca en una excepcion sin registrar.

    `solo_local=True` (N01, H11): si Qwen no lo resuelve, se escala en vez
    de probar ChatGPT/Gemini. Para texto que no debe salir del PC (los
    mensajes sueltos de Telegram).
    """

    execution_id = nuevo_execution_id()

    registrar_evidencia(
        "peticion",
        execution_id=execution_id,
        accion="tarea_recibida",
        resultado=_preview(texto),
    )

    categoria = _clasificar(texto, execution_id)

    if categoria not in RUTAS_QWEN:
        return _escalar(
            execution_id, categoria,
            motivo=(
                f"categoria '{categoria}' no enrutable a ningun proveedor "
                "en esta ruta"
            ),
        )

    if categoria == "extraccion" and not claves_extraccion:
        return _escalar(
            execution_id, categoria,
            motivo="tarea de extraccion sin claves_extraccion: peticion mal formada",
        )

    return _ejecutar_con_watchdog(
        execution_id, categoria, texto, claves_extraccion, solo_local=solo_local,
    )


def _clasificar(texto: str, execution_id: str) -> str:
    from extremidades import qwen

    categoria = qwen.clasificar(texto, CATEGORIAS_TAREA, por_defecto="otro")

    registrar_evidencia(
        "decision",
        execution_id=execution_id,
        actor="nexo_decidio",
        rol="planner",
        proveedor="qwen",
        accion="clasificar_y_decidir_ruta",
        resultado=categoria,
    )

    return categoria


def _escalar(execution_id: str, categoria: str, motivo: str) -> dict:
    log.info("escalado (%s): %s", execution_id, motivo)

    registrar_evidencia(
        "escalado",
        execution_id=execution_id,
        actor="nexo_decidio",
        rol="planner",
        accion="escalar",
        escalado=True,
        error=motivo,
        resultado=categoria,
    )

    return {
        "execution_id": execution_id,
        "estado": "ESCALADO",
        "categoria": categoria,
        "motivo": motivo,
    }


def _un_intento(
    execution_id: str,
    categoria: str,
    claves: list[str],
    texto_original: str,
    prompt: str,
    proveedor,
    reintento: int | None,
) -> tuple[dict | None, str, str | None]:
    """Una llamada a UN proveedor (Qwen o Gemini) + su verificacion.

    Devuelve (resultado, motivo, estado_proveedor):
      - `resultado` es el dict final de procesar() si esta llamada tuvo
        exito (el proveedor respondio Y la verificacion la acepto), o
        None si no.
      - `motivo` explica el fallo (cadena vacia si hubo exito).
      - `estado_proveedor` es el `Resultado.estado` crudo ("NOT_AVAILABLE"
        /"BLOCKED"/"ERROR") cuando quien fallo fue el PROVEEDOR (para que
        quien llama pueda decidir si tiene sentido reintentar), o None
        cuando el proveedor respondio pero fallo la VERIFICACION (fallo
        de contenido, no de disponibilidad).
    """

    inicio = time.perf_counter()
    resultado = proveedor.enviar(prompt)
    duracion = round(time.perf_counter() - inicio, 3)

    registrar_evidencia(
        "ejecucion",
        execution_id=execution_id,
        actor="tool_ejecuto",
        rol="worker",
        proveedor=proveedor.nombre,
        accion=categoria,
        estado=resultado.estado,
        duracion=duracion,
        reintento=reintento,
    )

    if not resultado.ok:
        registrar_evidencia(
            "error",
            execution_id=execution_id,
            actor="tool_ejecuto",
            proveedor=proveedor.nombre,
            error=resultado.detalle or resultado.estado,
            reintento=reintento,
        )

        motivo = f"{proveedor.nombre} {resultado.estado}: {resultado.detalle}"

        return None, motivo, resultado.estado

    if categoria == "resumen":
        ok, motivo_verif = _verificar_resumen(texto_original, resultado.texto)
    else:
        ok, motivo_verif = _verificar_extraccion(claves, resultado.texto)

    registrar_evidencia(
        "verificacion",
        execution_id=execution_id,
        actor="verificador_confirmo",
        rol="verifier",
        proveedor=proveedor.nombre,
        verificacion="EVIDENCE_VERIFIED" if ok else "GENERATED",
        estado="OK" if ok else "FALLO",
        resultado=motivo_verif,
        reintento=reintento,
    )

    if not ok:
        return None, f"verificacion fallida ({proveedor.nombre}): {motivo_verif}", None

    registrar_evidencia(
        "resultado",
        execution_id=execution_id,
        actor="verificador_confirmo",
        rol="verifier",
        proveedor=proveedor.nombre,
        estado="OK",
        resultado=_preview(resultado.texto),
    )

    return {
        "execution_id": execution_id,
        "estado": "OK",
        "categoria": categoria,
        "proveedor": proveedor.nombre,
        "texto": resultado.texto,
    }, "", None


def _ejecutar_con_watchdog(
    execution_id: str,
    categoria: str,
    texto: str,
    claves_extraccion: list[str] | None,
    solo_local: bool = False,
) -> dict:
    if categoria == "extraccion":
        claves = list(claves_extraccion or [])
        prompt = (
            f"{texto}\n\nDevuelve SOLO un objeto JSON valido, sin texto "
            "adicional ni explicaciones, con exactamente estas claves: "
            f"{', '.join(claves)}."
        )
    else:
        claves = []
        prompt = texto

    intentos_totales = 0

    # --- Qwen: intento + (como mucho) 1 reintento -----------------------
    proveedor_qwen = QwenProvider()
    motivo_qwen = ""

    for intento in range(MAX_REINTENTOS_QWEN + 1):
        intentos_totales += 1

        resultado, motivo_qwen, estado_prov = _un_intento(
            execution_id, categoria, claves, texto, prompt,
            proveedor_qwen, intento or None,
        )

        if resultado is not None:
            resultado["intentos"] = intentos_totales
            return resultado

        # NOT_AVAILABLE/BLOCKED no van a cambiar reintentando dentro de
        # la misma llamada: se pasa directo al fallback de Gemini. Un
        # ERROR puntual o un fallo de verificacion si se reintenta una
        # vez (watchdog minimo: un reintento, no un bucle sin fin).
        if estado_prov in ("NOT_AVAILABLE", "BLOCKED") or intento >= MAX_REINTENTOS_QWEN:
            break

        registrar_evidencia(
            "reintento",
            execution_id=execution_id,
            actor="nexo_decidio",
            rol="planner",
            proveedor="qwen",
            accion="reintentar_tras_verificacion_fallida",
            reintento=intento + 1,
            error=motivo_qwen,
        )

    if solo_local:
        return _escalar(
            execution_id, categoria,
            motivo=f"Qwen agoto sus intentos ({motivo_qwen}); solo_local: no se prueba fuera del PC",
        )

    # --- Qwen agoto sus intentos: UN intento con ChatGPT (H16, 26/09) ---
    registrar_evidencia(
        "reintento",
        execution_id=execution_id,
        actor="nexo_decidio",
        rol="planner",
        proveedor="chatgpt",
        accion="fallback_a_chatgpt_tras_agotar_qwen",
        error=motivo_qwen,
    )

    intentos_totales += 1

    resultado, motivo_chatgpt, _estado_prov_chatgpt = _un_intento(
        execution_id, categoria, claves, texto, prompt,
        ChatGPTProvider(), None,
    )

    if resultado is not None:
        resultado["intentos"] = intentos_totales
        return resultado

    # --- ChatGPT tambien fallo: ultimo recurso Gemini ---
    registrar_evidencia(
        "reintento",
        execution_id=execution_id,
        actor="nexo_decidio",
        rol="planner",
        proveedor="gemini",
        accion="fallback_a_gemini_tras_fallar_chatgpt",
        error=motivo_chatgpt,
    )

    # T136 (23/09): primero Gemini por API oficial (si hay clave), luego la web.
    # Mismo trato: un intento cada uno, misma verificacion mecanica.
    motivos_gemini = []
    api = GeminiAPIProvider()
    candidatos = ([api] if api.disponible() else []) + [GeminiProvider()]
    for proveedor_gemini in candidatos:
        intentos_totales += 1
        resultado, motivo, _estado = _un_intento(
            execution_id, categoria, claves, texto, prompt,
            proveedor_gemini, None,
        )

        if resultado is not None:
            resultado["intentos"] = intentos_totales
            return resultado

        motivos_gemini.append(f"{proveedor_gemini.nombre}: {motivo}")

    motivo_gemini = "; ".join(motivos_gemini)

    return _escalar(
        execution_id, categoria,
        motivo=(
            f"Qwen agoto sus intentos ({motivo_qwen}); fallback a ChatGPT "
            f"tambien fallo ({motivo_chatgpt}); ultimo intento con Gemini "
            f"tambien fallo ({motivo_gemini})"
        ),
    )
