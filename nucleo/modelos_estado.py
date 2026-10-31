# -*- coding: utf-8 -*-
"""Estado de los modelos de las API gratuitas (T320, Damian 04/10): detectar modelos RETIRADOS o sin servicio.

Caso real del primer uso del tribunal (04/10): mistral-nemotron (NVIDIA) devolvia HTTP 410, qwen3-32b (Groq)
HTTP 404 y glm-5.3-flash no respondia en 120 s, y nada avisaba: cada llamada perdia tiempo y, en Groq, un solo
modelo retirado bloqueaba toda la llamada.

Senales (las anotan GroqProvider y NvidiaProvider tras cada intento, memoria/modelos_estado.json):
  - HTTP 404 o 410 = el modelo ya no existe: tras MIN_RETIRADO senales SEGUIDAS (sin ningun OK entre medias)
    queda RETIRADO. Se guarda la evidencia (cuando y codigo de cada senal).
  - Timeout (sin respuesta) = MIN_SIN_SERVICIO seguidos -> SIN_SERVICIO.
  - Un 200 con texto borra las senales y rehabilita el modelo.
Un modelo retirado o sin servicio sale de las listas EN USO (los proveedores y el tribunal lo saltan) sin tocar el
codigo, y se avisa UNA vez a la web/push (nucleo.avisos). `sondear()` lo vuelve a probar con una llamada minima
(lo usa el banco de modelos T320); `rehabilitar()` lo devuelve a mano.
CLI: .venv\\Scripts\\python.exe -m nucleo.modelos_estado estado | sondear | rehabilitar <proveedor> <modelo>
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from nucleo.candado import bloqueo
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico

ESTADO = RAIZ / "memoria" / "modelos_estado.json"
CANDADO = RAIZ / "memoria" / ".candado_modelos_estado.lock"
MIN_RETIRADO = 2            # senales 404/410 seguidas para darlo por retirado
MIN_SIN_SERVICIO = 3        # timeouts seguidos para darlo por sin servicio
MAX_SENALES = 10
RETIRADO, SIN_SERVICIO, VIVO = "retirado", "sin_servicio", "vivo"
CODIGOS_RETIRADO = (404, 410)


def _clave(proveedor: str, modelo: str) -> str:
    return f"{proveedor}/{modelo}"


def _leer() -> dict:
    try:
        d = json.loads(ESTADO.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar(d: dict) -> None:
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(ESTADO, json.dumps(d, ensure_ascii=False, indent=1))


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def anotar(proveedor: str, modelo: str, resultado: str | int) -> str:
    """Anota el resultado de UN intento con ese modelo: 'ok', 'timeout', otro texto (se ignora) o un codigo HTTP.
    Devuelve el estado del modelo tras anotarlo (vivo | retirado | sin_servicio)."""
    if not modelo:
        return VIVO
    k = _clave(proveedor, modelo)
    with bloqueo(CANDADO):
        d = _leer()
        e = d.setdefault(k, {"estado": VIVO, "senales": []})
        antes = e["estado"]
        if resultado == "ok":
            e.update(estado=VIVO, senales=[], ultimo_ok=_ahora())
            if antes != VIVO:
                e["rehabilitado"] = _ahora()
        elif resultado == "timeout" or resultado in CODIGOS_RETIRADO:
            tipo = "timeout" if resultado == "timeout" else int(resultado)
            # las senales de otro tipo cortan la racha: 410, 410 cuenta; 410, timeout, 410 no.
            if e["senales"] and e["senales"][-1]["codigo"] != tipo:
                e["senales"] = []
            e["senales"] = (e["senales"] + [{"cuando": _ahora(), "codigo": tipo}])[-MAX_SENALES:]
            n = len(e["senales"])
            if tipo == "timeout" and n >= MIN_SIN_SERVICIO and antes == VIVO:
                e.update(estado=SIN_SERVICIO, desde=_ahora())
            elif tipo != "timeout" and n >= MIN_RETIRADO and antes != RETIRADO:
                e.update(estado=RETIRADO, desde=_ahora())
        # cualquier otro resultado (429, 5xx, error de red, respuesta vacia): no dice nada del modelo
        _guardar(d)
        despues = e["estado"]
    if despues != antes and despues != VIVO:
        _avisar(proveedor, modelo, despues, e)
    return despues


def _avisar(proveedor: str, modelo: str, estado: str, e: dict) -> None:
    try:
        from nucleo import avisos
        senal = ", ".join(f"HTTP {s['codigo']}" if s["codigo"] != "timeout" else "sin respuesta"
                          for s in e["senales"][-3:])
        que = "RETIRADO (ya no existe)" if estado == RETIRADO else "SIN SERVICIO (no responde)"
        avisos.emitir("modelo_retirado", f"Modelo {que}: {modelo}",
                      f"{proveedor}/{modelo}: {senal}. NEXO ya no lo usa; si vuelve, `python -m nucleo.modelos_estado "
                      f"sondear` lo rehabilita.", ruta="/", clave=f"modelo:{proveedor}/{modelo}:{estado}")
    except Exception:
        pass   # avisar nunca debe romper una llamada a un proveedor


def estado_de(proveedor: str, modelo: str) -> str:
    return (_leer().get(_clave(proveedor, modelo)) or {}).get("estado", VIVO)


def fuera_de_uso(proveedor: str, modelo: str) -> bool:
    return estado_de(proveedor, modelo) != VIVO


def en_uso(proveedor: str, modelos) -> tuple:
    """Los `modelos` que siguen vivos (conserva el orden)."""
    d = _leer()
    return tuple(m for m in modelos if (d.get(_clave(proveedor, m)) or {}).get("estado", VIVO) == VIVO)


def rehabilitar(proveedor: str, modelo: str) -> bool:
    with bloqueo(CANDADO):
        d = _leer()
        e = d.get(_clave(proveedor, modelo))
        if not e:
            return False
        e.update(estado=VIVO, senales=[], rehabilitado=_ahora())
        _guardar(d)
    return True


def resumen() -> list[dict]:
    """Los modelos con alguna senal o fuera de uso, para el panel."""
    return [{"modelo": k, "estado": e.get("estado", VIVO), "desde": e.get("desde", ""), "senales": e.get("senales", []),
             "ultimo_ok": e.get("ultimo_ok", "")} for k, e in sorted(_leer().items())
            if e.get("estado", VIVO) != VIVO or e.get("senales")]


def sondear(fabrica=None, pausa: float = 3.0) -> list[dict]:
    """Prueba cada modelo conocido de Groq, NVIDIA y OpenRouter (los retirados tambien) con una llamada minima y deja el
    resultado anotado (los propios proveedores anotan). `fabrica(proveedor, modelo)` -> objeto con .enviar(texto)
    (los tests la sustituyen: nunca red). Devuelve [{modelo, antes, despues, resultado}]."""
    import proveedores as P
    def real(prov, m):
        if prov == "groq":
            return P.GroqProvider(modelos=(m,), rondas=1, incluir_fuera_de_uso=True)
        if prov == "openrouter":
            return P.OpenRouterProvider(modelos=(m,), incluir_fuera_de_uso=True)
        return P.NvidiaProvider(modelos=(m,), incluir_fuera_de_uso=True)

    fabrica = fabrica or real
    salida = []
    for prov, modelos in (("groq", P.MODELOS_GROQ), ("nvidia", P.MODELOS_NVIDIA_GRATIS),
                          ("openrouter", P.MODELOS_OPENROUTER_FREE)):
        for m in modelos:
            antes = estado_de(prov, m)
            try:
                r = fabrica(prov, m).enviar("Responde solo con la palabra OK.")
                res = r.estado
            except Exception as ex:
                res = f"{type(ex).__name__}"
            salida.append({"modelo": f"{prov}/{m}", "antes": antes, "despues": estado_de(prov, m), "resultado": res})
            time.sleep(pausa)
    return salida


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    a = sys.argv[1:]
    if a[:1] == ["sondear"]:
        for f in sondear():
            print(f)
    elif a[:1] == ["rehabilitar"] and len(a) == 3:
        print("rehabilitado" if rehabilitar(a[1], a[2]) else "ese modelo no estaba anotado")
    else:
        for f in resumen() or [{"estado": "ningun modelo con senales ni fuera de uso"}]:
            print(f)
