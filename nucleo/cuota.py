# -*- coding: utf-8 -*-
"""Decision adaptativa segun la cuota restante de cada proveedor (T684, parte adaptativa de T079).

Reglas del requisito (documentacion/REQ_TURNO_NOCTURNO_ADAPTATIVO.md): preferir la fuente ESTRUCTURADA, no inventar
fechas de recarga ni limites, lo no fiable es UNKNOWN, reevaluar durante el turno y criterio de parada explicito.

Fuente: las cabeceras x-ratelimit-* que devuelven las API compatibles con OpenAI (Groq: -requests/-tokens con su
reset; OpenRouter y NVIDIA cuando las mandan). Las anota nucleo/fallos.cascada tras cada llamada (OK o 429) en
memoria/cuota.json, por modelo. Gemini API y las webs no dan cuota legible: UNKNOWN (las webs solo avisan al
llegar al limite, y eso ya lo recoge el enfriamiento).

Uso:
  margen(prov)            fraccion 0..1 que queda (la del MEJOR modelo del proveedor), 0 si esta enfriado o apagado,
                          None = UNKNOWN (sin dato, dato caducado o sin limite conocido). Si el reset que dio la
                          propia API ya paso, la ventana se ha recargado y el dato deja de valer (UNKNOWN).
  reordenar(proveedores)  orden estable de una cascada: los que estan casi agotados (< UMBRAL_BAJO) pasan al final
                          para repartir el trabajo ANTES de agotar uno; UNKNOWN se queda donde estaba.
  seguir(proveedores)     criterio de parada del turno: sigue si alguno tiene margen >= UMBRAL_PARADA o es UNKNOWN
                          y no esta enfriado; si todos estan agotados o enfriados, para con el motivo.
CLI: .venv\\Scripts\\python.exe -m nucleo.cuota estado
"""
from __future__ import annotations

import json
import re
import sys
import time

from nucleo.candado import bloqueo
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico

ALMACEN = RAIZ / "memoria" / "cuota.json"
CANDADO = RAIZ / "memoria" / ".candado_cuota.lock"
UMBRAL_BAJO = 0.15        # por debajo, el proveedor pasa al final de la cascada
UMBRAL_PARADA = 0.03      # por debajo en TODOS los conocidos (y sin UNKNOWN), el turno para
CADUCA_SIN_RESET = 3600   # dato sin hora de recarga: vale como mucho 1 h

_DURACION = re.compile(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m(?!s))?(?:(\d+(?:\.\d+)?)s)?(?:(\d+(?:\.\d+)?)ms)?$")


def _segundos(v) -> float | None:
    """'2m59.56s', '7.66s', '120ms', '30' -> segundos. Un epoch en ms (OpenRouter) -> segundos que faltan."""
    if v is None:
        return None
    s = str(v).strip()
    try:
        n = float(s)
        if n > 1e11:                      # epoch en milisegundos
            return max(0.0, n / 1000 - time.time())
        if n > 1e9:                       # epoch en segundos
            return max(0.0, n - time.time())
        return n
    except ValueError:
        pass
    m = _DURACION.match(s)
    if not m or not any(m.groups()):
        return None
    h, mi, se, ms = (float(x) if x else 0.0 for x in m.groups())
    return h * 3600 + mi * 60 + se + ms / 1000


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def leer_cabeceras(cabeceras) -> dict | None:
    """Saca de las cabeceras lo que se sabe de cuota. None si no traen nada estructurado."""
    try:
        c = {str(k).lower(): v for k, v in dict(cabeceras or {}).items()}
    except Exception:
        return None
    filas = {}
    for tipo, sufijos in (("peticiones", ("-requests", "")), ("tokens", ("-tokens",))):
        for suf in sufijos:
            limite, queda = _num(c.get(f"x-ratelimit-limit{suf}")), _num(c.get(f"x-ratelimit-remaining{suf}"))
            if limite and queda is not None:
                filas[tipo] = {"limite": limite, "queda": queda,
                               "reset_s": _segundos(c.get(f"x-ratelimit-reset{suf}"))}
                break
    return filas or None


def _leer() -> dict:
    try:
        return json.loads(ALMACEN.read_text(encoding="utf-8"))
    except Exception:
        return {}


def registrar(proveedor: str, modelo: str, cabeceras, ahora: float | None = None) -> None:
    """Lo llama fallos.cascada tras cada respuesta. Nunca rompe la llamada."""
    try:
        datos = leer_cabeceras(cabeceras)
        if not datos:
            return
        ahora = time.time() if ahora is None else ahora
        with bloqueo(CANDADO):
            d = _leer()
            d.setdefault(proveedor, {})[modelo] = {"cuando": ahora, **datos}
            ALMACEN.parent.mkdir(parents=True, exist_ok=True)
            escribir_atomico(ALMACEN, json.dumps(d, ensure_ascii=False, indent=1))
    except Exception:
        pass


def _margen_modelo(e: dict, ahora: float) -> float | None:
    fracciones = []
    for tipo in ("peticiones", "tokens"):
        x = e.get(tipo)
        if not x:
            continue
        reset = x.get("reset_s")
        caduca = e["cuando"] + (reset if reset is not None else CADUCA_SIN_RESET)
        if ahora >= caduca:
            continue                      # ventana recargada o dato viejo: no se sabe
        fracciones.append(max(0.0, min(1.0, x["queda"] / x["limite"])))
    return min(fracciones) if fracciones else None


def margen(proveedor: str, ahora: float | None = None) -> float | None:
    from nucleo.enfriamiento import enfriado
    if enfriado(proveedor):
        return 0.0
    ahora = time.time() if ahora is None else ahora
    valores = [m for m in (_margen_modelo(e, ahora) for e in _leer().get(proveedor, {}).values()) if m is not None]
    return max(valores) if valores else None


def reordenar(proveedores: list, ahora: float | None = None) -> list:
    """Orden estable: los casi agotados (margen conocido < UMBRAL_BAJO) al final."""
    def bajo(p):
        m = margen(getattr(p, "nombre", str(p)), ahora)
        return m is not None and m < UMBRAL_BAJO
    return [p for p in proveedores if not bajo(p)] + [p for p in proveedores if bajo(p)]


def seguir(nombres, ahora: float | None = None) -> tuple[bool, str]:
    """Criterio de parada del turno: (True, "") si queda algun proveedor con cuota; si no, (False, motivo)."""
    nombres = list(nombres)
    if not nombres:
        return False, "ningun proveedor disponible"
    margenes = {n: margen(n, ahora) for n in nombres}
    if any(m is None or m >= UMBRAL_PARADA for m in margenes.values()):
        return True, ""
    return False, "cuota agotada o proveedores enfriados: " + ", ".join(f"{n} {m:.0%}" for n, m in margenes.items())


def estado(ahora: float | None = None) -> list[dict]:
    from nucleo.enfriamiento import enfriado
    nombres = ["groq", "nvidia", "openrouter", "gemini_api", "chatgpt", "gemini", "claude_web", "qwen"]
    nombres += [n for n in _leer() if n not in nombres]
    filas = []
    for n in nombres:
        m = margen(n, ahora)
        filas.append({"proveedor": n, "margen": None if m is None else round(m, 3),
                      "estado": "UNKNOWN" if m is None else ("ENFRIADO" if enfriado(n) else
                                                            ("BAJO" if m < UMBRAL_BAJO else "OK"))})
    return filas


# ------------------------------------------------------------------ presupuesto diario por consumidor (6b)
# Gemini API (y las webs) no dan cuota legible: UNKNOWN. Para que un consumidor de fondo (el lote de reels) no deje
# sin cuota al tribunal, se lleva aqui una cuenta PROPIA por dia: cuantas peticiones ha hecho cada consumidor a cada
# proveedor hoy, y se le permite como mucho `fraccion` del `total_dia` que se estima para ese proveedor. Nada de esto
# inventa la cuota real: es un tope de convivencia, configurable por quien lo usa.
PRESUPUESTO = RAIZ / "memoria" / "cuota_presupuesto.json"
CANDADO_PRESUPUESTO = RAIZ / "memoria" / ".candado_cuota_presupuesto.lock"


def _hoy(ahora: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() if ahora is None else ahora))


def _leer_presupuesto() -> dict:
    try:
        return json.loads(PRESUPUESTO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def tope_diario(total_dia: int, fraccion: float) -> int:
    """Peticiones/dia que le tocan a un consumidor: el entero por debajo de total*fraccion (minimo 0)."""
    return max(0, int(total_dia * max(0.0, min(1.0, fraccion))))


def gastado_hoy(proveedor: str, consumidor: str, ahora: float | None = None) -> int:
    return int(_leer_presupuesto().get(_hoy(ahora), {}).get(proveedor, {}).get(consumidor, 0))


def queda_hoy(proveedor: str, consumidor: str, total_dia: int, fraccion: float, ahora: float | None = None) -> int:
    return max(0, tope_diario(total_dia, fraccion) - gastado_hoy(proveedor, consumidor, ahora))


# Reparto de la cuota diaria de Gemini API (6c, 12/10): el tribunal tiene reservada la mitad y nadie mas puede
# gastarla; reels tiene como mucho el 20 % (su fraccion) y el resto de turnos comparten lo que queda.
RESERVA_TRIBUNAL = 0.50
TRIBUNAL = "tribunal"


def gastado_otros_hoy(proveedor: str, ahora: float | None = None) -> int:
    """Peticiones de hoy de todos los consumidores que NO son el tribunal."""
    fila = _leer_presupuesto().get(_hoy(ahora), {}).get(proveedor, {})
    return int(sum(v for k, v in fila.items() if k != TRIBUNAL))


def permite(proveedor: str, consumidor: str, total_dia: int, fraccion: float, n: int = 1,
            ahora: float | None = None) -> bool:
    """True si al consumidor le quedan `n` peticiones de hoy, el proveedor no esta enfriado y (si no es el tribunal)
    entre todos los demas no se toca la reserva del tribunal."""
    from nucleo.enfriamiento import enfriado
    if enfriado(proveedor):
        return False
    if consumidor != TRIBUNAL and gastado_otros_hoy(proveedor, ahora) + n > tope_diario(total_dia, 1 - RESERVA_TRIBUNAL):
        return False
    return queda_hoy(proveedor, consumidor, total_dia, fraccion, ahora) >= n


def gastar(proveedor: str, consumidor: str, n: int = 1, ahora: float | None = None) -> int:
    """Anota `n` peticiones de hoy (y olvida los dias anteriores). Devuelve lo gastado hoy. Nunca rompe la llamada."""
    try:
        hoy = _hoy(ahora)
        with bloqueo(CANDADO_PRESUPUESTO):
            d = _leer_presupuesto()
            d = {hoy: d.get(hoy, {})}
            fila = d[hoy].setdefault(proveedor, {})
            fila[consumidor] = int(fila.get(consumidor, 0)) + n
            PRESUPUESTO.parent.mkdir(parents=True, exist_ok=True)
            escribir_atomico(PRESUPUESTO, json.dumps(d, ensure_ascii=False, indent=1))
            return fila[consumidor]
    except Exception:
        return 0


if __name__ == "__main__":
    from nucleo import ayuda
    ayuda.atender(__doc__)
    if sys.argv[1:2] == ["estado"]:
        for f in estado():
            print(f"{f['proveedor']:<12} {f['estado']:<9} {'' if f['margen'] is None else format(f['margen'], '.0%')}")
    else:
        print(__doc__)
