# -*- coding: utf-8 -*-
"""Auto-etiquetado para el Router (T082): anade "router:auto" (y
"router:claves:...") a tareas de memoria/tareas.json que DE VERDAD son
candidatas para consumidor_router.py/router.py -- no tareas que "hablan"
de resumir o extraer, sino tareas cuyo campo `detalle` ES el contenido
en si (texto a resumir, o datos de los que extraer campos), tal y como
exige consumidor_router.consumir_tarea() (usa tarea["detalle"] tal cual
como `texto` para router.procesar()).

Por que NO basta con "clasificar con Qwen y etiquetar lo que salga"
---------------------------------------------------------------------
router._verificar_resumen() solo comprueba que el resultado no este
vacio, sea distinto del original y tenga menos palabras -- no comprueba
fidelidad (T067 ya documenta esto como limitacion deliberada). Si se
etiqueta una tarea normal de Nexo (una descripcion de que hacer, no
contenido a resumir) con "router:auto", el Router la "resumiria" de
todas formas -- cualquier texto mas corto y distinto pasa esa
verificacion -- y consumidor_router.consumir_tarea() la marcaria HECHA
automaticamente con ese resultado sin sentido: cerraria trabajo real
del backlog con basura, sin que nadie se entere hasta revisar a mano.

Por eso este script exige DOS senales antes de etiquetar, no una:

  1. Filtro ESTRUCTURAL propio (`_parece_contenido`, barato, sin
     llamar a ningun modelo): el `detalle` tiene que parecer contenido
     en si (largo, sin marcas de ser una descripcion de tarea de Nexo)
     y no una instruccion/accion sobre el propio proyecto.
  2. Solo si (1) pasa, se clasifica con extremidades.qwen.clasificar()
     (la misma funcion que usa router._clasificar(), CATEGORIAS_TAREA
     identico) y se exige "resumen" o "extraccion".

Si cualquiera de las dos falla, la tarea NO se etiqueta -- por diseno,
en modo seguro: mejor dejar una tarea elegible sin etiquetar (sigue
disponible para revision manual) que etiquetarla mal.

Para "extraccion" ademas hace falta saber que CLAVES exigir. Este
script nunca las inventa: busca un patron explicito en el propio
`detalle` ("claves: a, b, c" o "campos: a, b, c"); si no lo encuentra,
NO etiqueta -- se reporta aparte como "candidata sin claves detectables,
revisar a mano" en vez de arriesgar una extraccion mal definida.

Modo de uso
-----------
Por defecto corre en DRY RUN (no escribe nada, solo informa). Hace
falta --aplicar para escribir las etiquetas de verdad -- metodo
incremental de la Constitucion: primero se revisa el listado, luego se
aplica.

    python auto_etiquetado_router.py             # solo informa
    python auto_etiquetado_router.py --aplicar    # aplica etiquetas
"""

from __future__ import annotations

import re
import sys

from nucleo import tareas as T
from router import CATEGORIAS_TAREA


ETIQUETA_AUTO = "router:auto"
PREFIJO_CLAVES = "router:claves:"

# Longitud minima para que un `detalle` merezca la pena considerarse
# "contenido a resumir/extraer" -- una instruccion de tarea normal de
# Nexo puede ser larga tambien, asi que esto es necesario pero no
# suficiente (se combina con los marcadores de abajo).
LONGITUD_MINIMA = 120

# Marcadores que delatan que el `detalle` es una descripcion de tarea
# DE Nexo (habla del propio proyecto, de Damian, de un archivo, de otra
# tarea) y no contenido externo a resumir/extraer. Basta con que
# aparezca UNO para descartar la tarea como candidata.
MARCADORES_TAREA_NEXO = [
    r"\bnexo\b",
    r"\bdami[aá]n\b",
    r"\bclaude\b",
    r"\bconstituci[oó]n\b",
    r"\btarea[s]?\.json\b",
    r"\btarea[s]?\.md\b",
    r"\brouter\.py\b",
    r"\bconsumidor_router\b",
    r"\.py\b",
    r"\bT\d{3,}\b",
    r"\bveredicto\b",
]

# Primeras palabras tipicas de una instruccion/accion sobre el propio
# backlog de Nexo (imperativo o participio de "encargo"), frente a un
# texto narrativo/externo que empieza de cualquier otra forma.
VERBOS_INSTRUCCION_INICIO = (
    "investigado", "investigar", "adoptar", "evaluar", "revisar",
    "crear", "disenar", "diseñar", "definir", "implementar", "escribir",
    "completar", "corregir", "auditar", "analizar", "anadir", "añadir",
    "construir", "probar", "testear", "documentar", "registrar",
    "decidir", "comprobar", "verificar",
)

RE_CLAVES = re.compile(
    r"(?:claves|campos)\s*:\s*([^\.\n]+)",
    re.IGNORECASE,
)

RE_CLAVE_VALIDA = re.compile(r"^[a-zA-Z_áéíóúÁÉÍÓÚñÑ][a-zA-Z0-9_áéíóúÁÉÍÓÚñÑ]*$")


def _parece_contenido(detalle: str) -> tuple[bool, str]:
    """True si `detalle` parece contenido en si (texto/datos externos),
    no una descripcion de tarea de Nexo. Devuelve (ok, motivo)."""

    texto = (detalle or "").strip()

    if len(texto) < LONGITUD_MINIMA:
        return False, f"detalle demasiado corto ({len(texto)} car., minimo {LONGITUD_MINIMA})"

    bajo = texto.lower()

    for patron in MARCADORES_TAREA_NEXO:
        if re.search(patron, bajo):
            return False, f"contiene un marcador de tarea-de-Nexo ({patron})"

    primera_palabra = bajo.split()[0].strip(".,:;()\"'") if bajo.split() else ""

    if primera_palabra in VERBOS_INSTRUCCION_INICIO:
        return False, f"empieza como una instruccion/accion ('{primera_palabra}...')"

    return True, "sin marcadores de tarea-de-Nexo, longitud suficiente"


def _claves_de_detalle(detalle: str) -> list[str] | None:
    m = RE_CLAVES.search(detalle or "")

    if not m:
        return None

    brutos = [c.strip() for c in m.group(1).split(",") if c.strip()]

    if not brutos:
        return None

    claves = []
    for c in brutos:
        if not RE_CLAVE_VALIDA.match(c):
            return None
        claves.append(c)

    return claves


def _ya_etiquetada(tarea: dict) -> bool:
    return ETIQUETA_AUTO in (tarea.get("etiquetas") or [])


def evaluar_candidatas() -> dict:
    """Recorre las tareas vivas de Nexo (depende=ia) y decide, para cada
    una, si es candidata segura a "router:auto". No escribe nada."""

    from extremidades import qwen

    vivas = [
        t for t in T.listar(depende="ia")
        if t["estado"] in ("pendiente", "en_curso") and not _ya_etiquetada(t)
    ]

    etiquetables: list[tuple[dict, str, list[str] | None]] = []
    descartadas_estructura: list[tuple[dict, str]] = []
    descartadas_clasificacion: list[tuple[dict, str]] = []
    extraccion_sin_claves: list[dict] = []
    fallos_clasificacion: list[tuple[dict, str]] = []

    for t in vivas:
        detalle = t.get("detalle") or ""

        ok, motivo = _parece_contenido(detalle)

        if not ok:
            descartadas_estructura.append((t, motivo))
            continue

        try:
            categoria = qwen.clasificar(detalle, CATEGORIAS_TAREA, por_defecto="otro")
        except Exception as e:
            fallos_clasificacion.append((t, str(e)))
            continue

        if categoria not in ("resumen", "extraccion"):
            descartadas_clasificacion.append((t, categoria))
            continue

        if categoria == "extraccion":
            claves = _claves_de_detalle(detalle)

            if not claves:
                extraccion_sin_claves.append(t)
                continue

            etiquetables.append((t, categoria, claves))
        else:
            etiquetables.append((t, categoria, None))

    return {
        "total_vivas_sin_etiqueta": len(vivas),
        "etiquetables": etiquetables,
        "descartadas_estructura": descartadas_estructura,
        "descartadas_clasificacion": descartadas_clasificacion,
        "extraccion_sin_claves": extraccion_sin_claves,
        "fallos_clasificacion": fallos_clasificacion,
    }


def aplicar(etiquetables: list[tuple[dict, str, list[str] | None]], discrepancias: list[tuple[str, str]] | None = None) -> list[str]:
    """Escribe de verdad las etiquetas sobre memoria/tareas.json.
    Devuelve la lista de ids tocados."""

    tocadas = []

    for t, categoria, claves in etiquetables:
        # T421: en extraccion, claves tiene que ser lista/tupla no vacia de str no vacios; si no, se salta
        if categoria == "extraccion":
            if not isinstance(claves, (list, tuple)):
                continue
            if not claves:
                continue
            if not all(isinstance(c, str) and c for c in claves):
                continue

        # T422: un fallo en una tarea no corta las demas; se reporta en `discrepancias`
        try:
            nuevas_etiquetas = list(t.get("etiquetas") or [])
            nuevas_etiquetas.append(ETIQUETA_AUTO)

            if categoria == "extraccion" and claves:
                nuevas_etiquetas.append(PREFIJO_CLAVES + ",".join(claves))

            T.actualizar(t["id"], etiquetas=nuevas_etiquetas)
            T.anotar(
                t["id"],
                f"auto_etiquetado_router.py: etiquetada '{ETIQUETA_AUTO}' "
                f"(categoria={categoria}"
                + (f", claves={claves}" if claves else "")
                + ") tras pasar el filtro estructural + clasificacion Qwen.",
            )

            tocadas.append(t["id"])
        except Exception as e:
            if discrepancias is not None:
                discrepancias.append((t["id"], str(e)))

    return tocadas


def _resumen_legible(r: dict) -> str:
    partes = [
        f"Tareas vivas de Nexo sin '{ETIQUETA_AUTO}' revisadas: {r['total_vivas_sin_etiqueta']}",
        f"Etiquetables (pasan filtro estructural + Qwen): {len(r['etiquetables'])}",
    ]

    for t, categoria, claves in r["etiquetables"]:
        extra = f" claves={claves}" if claves else ""
        partes.append(f"  - {t['id']} [{categoria}]{extra}  {t['titulo'][:70]}")

    partes.append(
        f"Descartadas por filtro estructural (no parecen contenido externo): "
        f"{len(r['descartadas_estructura'])}"
    )
    partes.append(
        f"Descartadas por clasificacion Qwen (no dio resumen/extraccion): "
        f"{len(r['descartadas_clasificacion'])}"
    )

    if r.get("fallos_clasificacion"):
        partes.append(
            f"Fallos de clasificacion Qwen: {len(r['fallos_clasificacion'])}"
        )
        for t, motivo in r["fallos_clasificacion"]:
            partes.append(f"  - {t['id']}  {motivo}  {t['titulo'][:70]}")

    if r["extraccion_sin_claves"]:
        partes.append(
            f"Clasificadas como extraccion pero SIN claves detectables en "
            f"detalle (revisar a mano, no etiquetadas): "
            f"{len(r['extraccion_sin_claves'])}"
        )
        for t in r["extraccion_sin_claves"]:
            partes.append(f"  - {t['id']}  {t['titulo'][:70]}")

    return "\n".join(partes)


def _cli(argv: list[str]) -> int:
    aplicar_de_verdad = "--aplicar" in argv

    r = evaluar_candidatas()

    print(_resumen_legible(r))

    if not r["etiquetables"]:
        print("\nNada que etiquetar. No se ha tocado memoria/tareas.json.")

        return 0

    if not aplicar_de_verdad:
        print(
            "\nDRY RUN: no se ha escrito nada. Ejecuta con --aplicar para "
            "aplicar estas etiquetas de verdad."
        )

        return 0

    discrepancias: list[tuple[str, str]] = []
    tocadas = aplicar(r["etiquetables"], discrepancias)

    print(f"\nAPLICADO: {len(tocadas)} tarea(s) etiquetada(s): {', '.join(tocadas)}")

    if discrepancias:
        print(f"\nDISCREPANCIAS / FALLOS PARCIALES ({len(discrepancias)}):")
        for tid, motivo in discrepancias:
            print(f"  - {tid}: {motivo}")
        return 1

    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(_cli(sys.argv[1:]))
