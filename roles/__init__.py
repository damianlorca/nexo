"""Biblioteca de roles (prompts de sistema) para las IAs de Nexo.

Por que existe
--------------
Hasta el 23/09 extremidades/qwen.py usaba un unico prompt generico para
todo. Los roles especializados (revisor, verificador, programador) se
adaptaron de agency-agents (github.com/msitarzewski/agency-agents, MIT,
(c) Michael Sitarzewski y colaboradores): se conserva su estructura
(reglas concretas + formato de salida fijo) pero condensada y en
espanol, porque en este PC la inferencia local va solo por CPU y cada
token de prompt de sistema cuesta tiempo de prefill en cada llamada
(los originales tienen 1.300-2.500 palabras; estos, ~150-200).

Cada rol termina en una linea "VEREDICTO: ..." (o en campos fijos) para
que la salida se pueda verificar MECANICAMENTE, igual que router.py
verifica resumen/extraccion -- no a ojo.

Esto NO cambia nada de lo que ya funciona: qwen.py, router.py y
proveedores.py no importan este modulo todavia. Se conectara cuando el
banco de pruebas de roles locales (T100, rediseñado con guardas de RAM)
demuestre si mejora o no frente al prompt generico.

El clasificador NO tiene archivo aqui a proposito: para clasificar, un
modelo pequeno rinde mejor con un prompt minimo (el de qwen.clasificar)
que con una persona larga.
"""

from __future__ import annotations

import re
from pathlib import Path

CARPETA = Path(__file__).resolve().parent

# Veredictos validos por rol. Cualquier otra cosa en la linea final
# cuenta como "sin veredicto" (None), nunca como aprobado.
VEREDICTOS = {
    "revisor": ("APROBADO", "CAMBIOS_NECESARIOS"),
    "verificador": ("VERIFICADO", "NO_VERIFICADO", "INSUFICIENTE"),
}

_RE_VEREDICTO = re.compile(r"^\s*VEREDICTO:\s*([A-Z_]+)\s*$", re.MULTILINE)


def listar() -> list[str]:
    return sorted(p.stem for p in CARPETA.glob("*.md") if p.stem != "LEEME")


def cargar(nombre: str) -> str:
    """Texto del prompt de sistema del rol. Lanza KeyError si no existe."""

    p = CARPETA / f"{nombre}.md"

    if not p.is_file():
        raise KeyError(f"rol desconocido: {nombre!r} (hay: {', '.join(listar())})")

    return p.read_text(encoding="utf-8").strip()


def veredicto(nombre: str, salida: str) -> str | None:
    """Extrae el veredicto de la salida de un rol, o None si no es valido.

    Se toma la ULTIMA linea "VEREDICTO: X" (un modelo puede citar el
    formato antes de responder). Si X no esta entre los permitidos para
    ese rol, devuelve None: un veredicto mal formado nunca se trata como
    aprobacion.
    """

    permitidos = VEREDICTOS.get(nombre)

    if not permitidos:
        raise KeyError(f"el rol {nombre!r} no emite veredicto")

    encontrados = _RE_VEREDICTO.findall(salida or "")

    if not encontrados:
        return None

    ultimo = encontrados[-1]

    return ultimo if ultimo in permitidos else None


def veredicto_verificador(salida: str) -> tuple[str | None, str]:
    """Veredicto del verificador, con respaldo deducido de sus filas.

    Devuelve (veredicto, origen). origen es "explicito" si el modelo escribio
    la linea VEREDICTO, "deducido" si no la escribio pero SI rellenó las filas
    "AFIRMACION | evidencia | OK/FALTA" (todas OK -> VERIFICADO; alguna FALTA
    -> NO_VERIFICADO), o "ninguno" si no hay ni lo uno ni lo otro.

    Por que (banco T100 v2, 23/09): llama3.2:3b acerto 5/5 filas OK/FALTA
    con 0 aprobaciones falsas pero omitio SIEMPRE la linea final, asi que
    con solo el veredicto explicito salia 0/5. Deducirlo de las filas es tan
    mecanico como leer la linea final: no se interpreta texto libre.
    """

    explicito = veredicto("verificador", salida)

    if explicito:
        return explicito, "explicito"

    marcas = []

    for linea in (salida or "").splitlines():
        if linea.count("|") < 2 or linea.strip().upper().startswith("AFIRMACION"):
            continue

        marca = linea.rsplit("|", 1)[-1].strip().upper()

        if marca in ("OK", "FALTA"):
            marcas.append(marca)

    if not marcas:
        return None, "ninguno"

    return ("VERIFICADO" if all(m == "OK" for m in marcas) else "NO_VERIFICADO"), "deducido"


def campos_codigo(salida: str) -> dict:
    """Para el rol 'codigo': extrae el codigo corregido y los campos fijos.

    Formato (3a version, 23/09): CODIGO / codigo completo corregido /
    FIN_CODIGO. Las dos anteriores (diff unificado; CAMBIO -/+ por linea)
    fallaron en el banco T100: los modelos pequeños SABIAN el arreglo pero
    no respetaban el formato. Reescribir el codigo si lo hacen bien, y la
    diferencia se calcula MECANICAMENTE con lineas_cambiadas(): un cambio
    de mas (p.ej. tildes en un docstring) cuenta igual, asi que se sigue
    midiendo que el cambio sea minimo.
    """

    texto = (salida or "").replace("\r\n", "\n")
    # Apertura: la linea "CODIGO" o, si el modelo la cambia por una valla
    # ```python (visto con llama3.2:3b), esa valla. El cierre FIN_CODIGO
    # sigue siendo obligatorio.
    m = re.search(r"^(?:CODIGO|```[a-z]*)\s*\n(.*?)^FIN_CODIGO\s*$", texto, re.MULTILINE | re.DOTALL)
    codigo = None

    if m:
        lineas = [l for l in m.group(1).split("\n") if not l.strip().startswith("```")]
        codigo = "\n".join(lineas).strip("\n")

    fuera = re.search(r"^FUERA_DE_ALCANCE:\s*(.*)$", texto, re.MULTILINE)
    interp = re.search(r"^INTERPRETACION:\s*(.*)$", texto, re.MULTILINE)

    return {
        "ok": bool(codigo) and bool(fuera) and bool(interp),
        "codigo": codigo,
        "fuera_de_alcance": fuera.group(1).strip() if fuera else None,
        "interpretacion": interp.group(1).strip() if interp else None,
    }


def lineas_cambiadas(original: str, corregido: str) -> int:
    """Cuantas lineas difieren entre original y corregido (difflib).

    Ignora espacios al final de linea y lineas en blanco al principio y al
    final. Una linea sustituida cuenta 1; si se borran 2 y se anaden 3,
    cuenta 3 (el mayor de los dos lados de cada bloque).
    """

    import difflib

    a = [l.rstrip() for l in original.strip("\n").split("\n")]
    b = [l.rstrip() for l in corregido.strip("\n").split("\n")]
    total = 0

    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op != "equal":
            total += max(i2 - i1, j2 - j1)

    return total
