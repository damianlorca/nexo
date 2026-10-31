"""Prueba real de router.py (T067 + T044) — ruta minima con fallback a Gemini.

Demuestra, sin intervencion manual de Claude entre pasos, el ciclo
completo que pidio Damian el 13/09, ahora con el fallback de T044:

    TAREA -> CLASIFICACION -> DECISION -> PROVEEDOR -> EJECUCION ->
    VERIFICACION -> FALLO/ESCALADO -> EVIDENCIA

    Qwen -> reintento Qwen -> Gemini -> verificacion -> escalado

Secciones:

  0. Verificacion mecanica, directa y determinista, SIN llamar a ningun
     modelo (igual que en T067).

  1-2. Extremo a extremo REALES sin forzar nada (igual que en T067):
     resumen y extraccion resueltos por Qwen a la primera. Comprueban
     tambien que Gemini NO se invoca cuando Qwen resuelve la tarea.

  3-4. Camino de escalado por regla, sin llamar a ningun proveedor para
     ejecutar la tarea (categoria "otro"; extraccion sin claves) — igual
     que en T067.

  5. NUEVO (T044) — Qwen falla dos veces (forzado en el adaptador:
     `router.QwenProvider` se sustituye por un proveedor de prueba que
     devuelve contenido real pero que NO supera `_verificar_extraccion` —
     esto demuestra a la vez el caso "hay contenido pero falla la
     verificacion mecanica"), y Gemini se invoca DE VERDAD (llamada real
     contra el navegador, sin mockear `GeminiProvider`) y resuelve la
     tarea. El resultado final debe venir de Gemini.

     Nota sobre por que este caso usa "extraccion" y no "resumen": en la
     primera version de esta prueba se uso "resumen", y Gemini SI
     respondio de verdad, pero su respuesta (mas conversacional, con
     contexto añadido) no quedo mas corta que el original y
     `_verificar_resumen` la rechazo correctamente -- el Router hizo
     exactamente lo que debia (llamar de verdad, verificar, escalar),
     pero ese texto de prueba no demostraba el camino "Gemini responde y
     SUPERA la verificacion". "extraccion" evita ese problema: su
     verificacion (JSON con claves exactas) no penaliza que Gemini sea
     mas o menos conversacional, porque `_extraer_json` ya busca el
     bloque {...} aunque venga rodeado de texto. No se toco ni
     `_verificar_resumen` ni `_verificar_extraccion` ni ninguna otra
     pieza de router.py para conseguir esto -- solo se cambio el dato de
     entrada de esta prueba.

  6. NUEVO (T044) — Qwen falla dos veces igual que en el caso 5, y esta
     vez Gemini TAMBIEN se fuerza a fallar (mockeado). Resultado final:
     escalado, con la cadena completa de ambos proveedores.

     Nota honesta sobre el caso 6: forzar un fallo REAL y reproducible
     de Gemini exigiria desconectar o romper la sesion de Chrome
     compartida (navegador.py), lo cual seria alterar el entorno de
     produccion — justo lo que esta ronda prohibe. Por eso, a diferencia
     del caso 5 (donde Gemini SI se invoca de verdad y debe responder
     bien), aqui se sustituye `router.GeminiProvider` por un proveedor de
     prueba que devuelve un fallo controlado, sin tocar el codigo real
     de `proveedores.py` ni de `extremidades/navegador.py`. El Router
     mismo (clasificacion, reglas, verificacion, evidencia) sigue
     ejecutandose sin mockear nada de eso.

Para cada caso, se relee registros/evidencia.jsonl filtrando por su
execution_id y se comprueba que la cadena de fases es exactamente la
esperada -- la prueba de que se puede reconstruir la cadena de
ejecucion, distinguiendo intento de Qwen, reintento de Qwen, fallback a
Gemini y resultado/escalado final, sin interpretar texto libre.

No dispara ChatGPT ni Claude (fuera de alcance de esta ruta). Deja el
resultado en registros/prueba_router_minimo.txt.
"""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import logging  # noqa: E402
logging.disable(logging.INFO)

import router  # noqa: E402
import proveedores  # noqa: E402
from nucleo.registro import leer_evidencia  # noqa: E402

# 23/09: el Router intenta Gemini API antes que la web si hay clave. En estas pruebas
# se desactiva para no llamar a la API real; el camino API tiene su propia prueba.
import router as _router_sin_api  # noqa: E402


class _SinGeminiAPI:
    nombre = "gemini_api"

    def disponible(self):
        return False


_router_sin_api.GeminiAPIProvider = _SinGeminiAPI



SALIDA = RAIZ / "registros" / "prueba_router_minimo.txt"
SALIDA.parent.mkdir(parents=True, exist_ok=True)

lineas: list[str] = []
fallos = 0


def anotar(texto: str = "") -> None:
    print(texto, flush=True)
    lineas.append(str(texto))
    SALIDA.write_text("\n".join(lineas), encoding="utf-8")


def comprobar(titulo: str, condicion: bool, detalle: str = "") -> None:
    global fallos

    if condicion:
        anotar(f"  VALE  {titulo}")
    else:
        fallos += 1
        anotar(f"  FALLA {titulo} {detalle}")


def cadena_fases(execution_id: str) -> list[str]:
    return [e["fase"] for e in leer_evidencia(execution_id=execution_id)]


def proveedores_usados(execution_id: str) -> list[str]:
    return [
        e.get("proveedor") for e in leer_evidencia(execution_id=execution_id)
        if e.get("proveedor") in ("qwen", "gemini")
    ]


class ProveedorFalso:
    """Sustituto de prueba para QwenProvider/GeminiProvider.

    No toca proveedores.py: solo se usa via unittest.mock.patch sobre el
    nombre `router.QwenProvider`/`router.GeminiProvider`, para forzar de
    forma reproducible una condicion concreta (fallo, o contenido que no
    supera la verificacion) sin depender del comportamiento real de un
    modelo o de una sesion de navegador.
    """

    def __init__(self, nombre: str, resultados: list) -> None:
        self.nombre = nombre
        self._cola = list(resultados)
        self.llamadas = 0

    def enviar(self, tarea: str) -> proveedores.Resultado:
        indice = min(self.llamadas, len(self._cola) - 1)
        self.llamadas += 1
        return self._cola[indice]


anotar(f"ROUTER MINIMO EN VIVO (T067 + T044)  {time.strftime('%Y-%m-%d %H:%M:%S')}")
anotar("=" * 60)


anotar("\n0. Verificacion mecanica, directa y determinista (sin modelo)")

try:
    ok, motivo = router._verificar_resumen(
        "Este es un texto de ejemplo con bastantes palabras para probar "
        "que el resumen mecanico detecta correctamente que un resultado "
        "mas corto es valido cuando de verdad lo es.",
        "Texto de ejemplo para probar el resumen.",
    )
    comprobar("resumen valido se acepta", ok, motivo)

    ok, motivo = router._verificar_resumen(
        "Texto corto.",
        "Texto corto.",
    )
    comprobar("resumen identico al original se rechaza", not ok, motivo)

    ok, motivo = router._verificar_resumen(
        "Poco.",
        "Esto es mas largo que el original y por tanto no es un resumen valido.",
    )
    comprobar("resumen mas largo que el original se rechaza", not ok, motivo)

    ok, motivo = router._verificar_extraccion(
        ["nombre", "ciudad"],
        '{"nombre": "Ana", "ciudad": "Valencia"}',
    )
    comprobar("extraccion con claves exactas se acepta", ok, motivo)

    ok, motivo = router._verificar_extraccion(
        ["nombre", "ciudad"],
        '{"nombre": "Ana", "ciudad": "Valencia", "edad": 30}',
    )
    comprobar(
        "extraccion con una clave de mas (deliberadamente rota) se rechaza",
        not ok, motivo,
    )

    ok, motivo = router._verificar_extraccion(
        ["nombre", "ciudad"],
        "esto no es json en absoluto",
    )
    comprobar("extraccion sin JSON valido se rechaza", not ok, motivo)
except Exception:
    fallos += 1
    anotar("EXCEPCION en verificacion mecanica:")
    anotar(traceback.format_exc())


anotar("\n1. Caso real: resumen resuelto por Qwen a la primera (Gemini no se invoca)")

try:
    texto_resumen = (
        "Nexo es el agente personal autonomo de Damian. Coordina IA local "
        "y modelos externos como Gemini, ChatGPT y Claude, junto con "
        "herramientas y control del PC, para planificar, ejecutar, "
        "verificar y completar tareas con la minima supervision humana "
        "necesaria. El objetivo de Nexo es maximizar la capacidad de "
        "trabajo total mediante una asignacion inteligente de recursos, "
        "priorizando la IA local cuando es suficiente y reservando los "
        "modelos premium para las tareas donde de verdad aporten un "
        "valor diferencial."
    )
    tarea = f"Resume el siguiente texto en una frase corta:\n\n{texto_resumen}"

    r = router.procesar(tarea)
    anotar(f"  procesar() -> {r}")

    comprobar("estado OK", r.get("estado") == "OK", str(r))
    comprobar("categoria == resumen", r.get("categoria") == "resumen", str(r))
    comprobar("proveedor final es qwen", r.get("proveedor") == "qwen", str(r))
    comprobar("hay texto de resultado", bool((r.get("texto") or "").strip()))

    fases = cadena_fases(r["execution_id"])
    anotar(f"  cadena de evidencia: {fases}")
    comprobar(
        "cadena de evidencia reconstruible y completa",
        fases == ["peticion", "decision", "ejecucion", "verificacion", "resultado"],
        str(fases),
    )
    comprobar(
        "Gemini no fue invocado",
        "gemini" not in proveedores_usados(r["execution_id"]),
        str(proveedores_usados(r["execution_id"])),
    )
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso resumen:")
    anotar(traceback.format_exc())


anotar("\n2. Caso real: extraccion resuelta por Qwen a la primera (Gemini no se invoca)")

try:
    tarea = (
        "Extrae los datos de la siguiente frase: "
        "\"El proyecto Nexo lo lleva Damian y esta en fase de construccion "
        "de su primera ruta autonoma.\""
    )
    claves = ["responsable", "proyecto"]

    r = router.procesar(tarea, claves_extraccion=claves)
    anotar(f"  procesar() -> {r}")

    comprobar("estado OK", r.get("estado") == "OK", str(r))
    comprobar("categoria == extraccion", r.get("categoria") == "extraccion", str(r))
    comprobar("proveedor final es qwen", r.get("proveedor") == "qwen", str(r))
    comprobar("hay texto de resultado", bool((r.get("texto") or "").strip()))

    fases = cadena_fases(r["execution_id"])
    anotar(f"  cadena de evidencia: {fases}")
    comprobar(
        "cadena de evidencia reconstruible y completa",
        fases == ["peticion", "decision", "ejecucion", "verificacion", "resultado"],
        str(fases),
    )
    comprobar(
        "Gemini no fue invocado",
        "gemini" not in proveedores_usados(r["execution_id"]),
        str(proveedores_usados(r["execution_id"])),
    )
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso extraccion:")
    anotar(traceback.format_exc())


anotar("\n3. Caso real: 'otro' -> escalado directo, sin ejecutar ninguna tarea en Qwen ni en Gemini")

try:
    tarea = "Cuentame un chiste sobre gatos."

    r = router.procesar(tarea)
    anotar(f"  procesar() -> {r}")

    comprobar("estado ESCALADO", r.get("estado") == "ESCALADO", str(r))
    comprobar("categoria == otro", r.get("categoria") == "otro", str(r))

    fases = cadena_fases(r["execution_id"])
    anotar(f"  cadena de evidencia: {fases}")
    comprobar(
        "escalado sin pasar por 'ejecucion' (clasifica, pero no ejecuta ninguna tarea)",
        fases == ["peticion", "decision", "escalado"],
        str(fases),
    )
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 'otro':")
    anotar(traceback.format_exc())


anotar("\n4. Caso real: extraccion mal formada (sin claves) -> escalado sin llamar a ningun proveedor")

try:
    tarea = "Extrae los datos de esta frase: \"Damian vive en Valencia.\""

    r = router.procesar(tarea, claves_extraccion=None)
    anotar(f"  procesar() -> {r}")

    comprobar("estado ESCALADO", r.get("estado") == "ESCALADO", str(r))

    fases = cadena_fases(r["execution_id"])
    anotar(f"  cadena de evidencia: {fases}")
    comprobar(
        "escalado sin pasar por 'ejecucion' (peticion mal formada)",
        fases == ["peticion", "decision", "escalado"],
        str(fases),
    )
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso extraccion mal formada:")
    anotar(traceback.format_exc())


anotar(
    "\n5. NUEVO T044 — Qwen falla 2 veces con contenido real que no supera "
    "la verificacion (forzado en el adaptador); Gemini se invoca DE VERDAD "
    "y resuelve la tarea (extraccion, ver nota del docstring sobre por "
    "que no se uso resumen)"
)

try:
    from extremidades import navegador

    if not navegador.activo():
        anotar("  Chrome no estaba activo, arrancando...")
        navegador.arrancar()

    tarea5 = (
        "Extrae los datos de la siguiente frase: "
        "\"La tarea T044 la completo Damian anadiendo un fallback real a "
        "Gemini dentro del Router de Nexo.\""
    )
    claves5 = ["responsable", "tarea"]

    # Qwen "falla" devolviendo texto sin JSON: hay contenido real, pero
    # _verificar_extraccion lo rechaza (no es JSON valido). Esto
    # demuestra a la vez el caso 4 (contenido presente que no supera la
    # verificacion mecanica) en las dos llamadas de Qwen.
    falso_qwen = ProveedorFalso("qwen", [
        proveedores.Resultado("OK", texto="No puedo procesar esa peticion."),
        proveedores.Resultado("OK", texto="No puedo procesar esa peticion."),
    ])

    # H16 (26/09): ChatGPT va antes que Gemini. Se fuerza su fallo para seguir
    # probando aqui el Gemini REAL.
    falso_chatgpt_5 = ProveedorFalso("chatgpt", [
        proveedores.Resultado("ERROR", detalle="fallo forzado de prueba (caso 5, H16: ChatGPT antes que Gemini)"),
    ])

    with mock.patch("router.QwenProvider", return_value=falso_qwen), \
         mock.patch("router.ChatGPTProvider", return_value=falso_chatgpt_5):
        r5 = router.procesar(tarea5, claves_extraccion=claves5)

    anotar(f"  procesar() -> {r5}")

    comprobar(
        "Qwen (forzado) fue llamado 2 veces: intento + reintento",
        falso_qwen.llamadas == 2, str(falso_qwen.llamadas),
    )
    comprobar("estado OK", r5.get("estado") == "OK", str(r5))
    comprobar("proveedor final es gemini", r5.get("proveedor") == "gemini", str(r5))
    comprobar("hay texto de resultado", bool((r5.get("texto") or "").strip()))

    fases5 = cadena_fases(r5["execution_id"])
    anotar(f"  cadena de evidencia: {fases5}")
    comprobar(
        "cadena distingue intento Qwen, reintento Qwen, fallback a Gemini "
        "y resultado final",
        fases5 == [
            "peticion", "decision",
            "ejecucion", "verificacion",       # intento Qwen
            "reintento",                        # reintento (Qwen)
            "ejecucion", "verificacion",        # reintento Qwen
            "reintento",                        # fallback a ChatGPT (H16)
            "ejecucion", "error",               # intento ChatGPT (forzado)
            "reintento",                        # fallback a Gemini
            "ejecucion", "verificacion",        # intento Gemini
            "resultado",
        ],
        str(fases5),
    )
    ejecuciones_qwen_5 = [
        e for e in leer_evidencia(execution_id=r5["execution_id"])
        if e.get("fase") == "ejecucion" and e.get("proveedor") == "qwen"
    ]
    comprobar(
        "las 2 llamadas fallidas de Qwen no se sobrescriben (siguen en la evidencia)",
        len(ejecuciones_qwen_5) == 2,
        str(ejecuciones_qwen_5),
    )
    comprobar(
        "Gemini aparece como proveedor usado",
        "gemini" in proveedores_usados(r5["execution_id"]),
        str(proveedores_usados(r5["execution_id"])),
    )
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 5 (fallback real a Gemini):")
    anotar(traceback.format_exc())


anotar(
    "\n6. NUEVO T044 — Qwen falla 2 veces (igual que el caso 5) y Gemini "
    "TAMBIEN falla (forzado en el adaptador, ver nota del docstring); "
    "resultado final: escalado"
)

try:
    texto_resumen_6 = (
        "El registro de evidencia de la Pieza 1 permite reconstruir una "
        "cadena completa de ejecucion leyendo un unico archivo, sin tener "
        "que interpretar texto libre ni adivinar que paso en cada paso "
        "intermedio del proceso."
    )
    tarea6 = f"Resume el siguiente texto en una frase muy corta:\n\n{texto_resumen_6}"

    falso_qwen_6 = ProveedorFalso("qwen", [
        proveedores.Resultado("OK", texto=tarea6),
        proveedores.Resultado("OK", texto=tarea6),
    ])
    falso_gemini_6 = ProveedorFalso("gemini", [
        proveedores.Resultado(
            "ERROR",
            detalle="fallo forzado de prueba (caso 6, adaptador real no modificado)",
        ),
    ])

    falso_chatgpt_6 = ProveedorFalso("chatgpt", [
        proveedores.Resultado(
            "ERROR",
            detalle="fallo forzado de prueba (caso 6, T082: ChatGPT tras Gemini)",
        ),
    ])

    with mock.patch("router.QwenProvider", return_value=falso_qwen_6), \
         mock.patch("router.GeminiProvider", return_value=falso_gemini_6), \
         mock.patch("router.ChatGPTProvider", return_value=falso_chatgpt_6):
        r6 = router.procesar(tarea6)

    anotar(f"  procesar() -> {r6}")

    comprobar(
        "Qwen (forzado) fue llamado 2 veces: intento + reintento",
        falso_qwen_6.llamadas == 2, str(falso_qwen_6.llamadas),
    )
    comprobar(
        "Gemini (forzado) fue llamado 1 vez: el unico intento de fallback",
        falso_gemini_6.llamadas == 1, str(falso_gemini_6.llamadas),
    )
    comprobar("estado ESCALADO", r6.get("estado") == "ESCALADO", str(r6))
    comprobar(
        "el motivo del escalado menciona a Qwen y a Gemini",
        "qwen" in r6.get("motivo", "").lower() and "gemini" in r6.get("motivo", "").lower(),
        str(r6),
    )

    fases6 = cadena_fases(r6["execution_id"])
    anotar(f"  cadena de evidencia: {fases6}")
    comprobar(
        "cadena completa: intento+reintento Qwen, fallback, fallo Gemini y escalado",
        fases6 == [
            "peticion", "decision",
            "ejecucion", "verificacion",   # intento Qwen
            "reintento",                    # reintento (Qwen)
            "ejecucion", "verificacion",    # reintento Qwen
            "reintento",                    # fallback a ChatGPT (H16)
            "ejecucion", "error",           # intento ChatGPT (falla el proveedor)
            "reintento",                    # fallback a Gemini
            "ejecucion", "error",           # intento Gemini (falla el proveedor)
            "escalado",
        ],
        str(fases6),
    )
except Exception:
    fallos += 1
    anotar("EXCEPCION en caso 6 (fallback tambien falla, escalado):")
    anotar(traceback.format_exc())


anotar("\n" + ("TODO VALE" if fallos == 0 else f"{fallos} FALLOS"))
anotar("FIN")
