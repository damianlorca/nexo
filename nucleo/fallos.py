# -*- coding: utf-8 -*-
"""Failover robusto (T157): tabla TIPO DE ERROR -> ACCION, la misma para todos los proveedores.

Antes cada proveedor de API tenia su copia del bucle de modelos con reglas distintas (Groq enfriaba 30 min con
cualquier 429; Gemini API no anotaba modelos retirados; un 401 devolvia BLOCKED sin enfriar y cada turno volvia a
chocar con la misma clave mala). Ahora:

  tipo           senal                                         accion
  -------------  --------------------------------------------  ----------------------------------------------------
  ok             200 con texto                                 devolver; el modelo queda vivo (modelos_estado)
  vacia          200 sin texto                                 siguiente modelo
  ritmo          429 por minuto (RPM/TPM) o sin mas datos       si Retry-After <= 60 s: esperar y repetir ESE modelo
                                                               una vez; si no, siguiente modelo. Todos -> enfriar
                                                               el proveedor poco ("saturado", 5 min)
  cuota          429/403 con "per day", "daily", "quota",      siguiente modelo (la cuota suele ser por modelo);
                 "RESOURCE_EXHAUSTED", "free-models-per-day"   todos -> enfriar "cuota" (Retry-After si lo dan)
  saturado       500, 502, 503, 504, 529                       siguiente modelo; todos -> enfriar 5 min
  retirado       404, 410                                      anotar en modelos_estado (2 seguidos = retirado) y
                                                               siguiente modelo
  peticion       400, 413, 422 (peticion demasiado grande o    siguiente modelo (otro puede aceptarla); no enfria
                 que ese modelo no admite)
  clave          401, 403 sin texto de cuota                   TERMINAL: BLOCKED y enfriar "bloqueo" (6 h): una
                                                               clave mala no se arregla reintentando
  clave_403      403 sin texto de cuota (T1013)                TERMINAL pero TRANSITORIO: enfriar 30 min; la primera
                                                               llamada tras ese rato es el sondeo: si vuelve a dar
                                                               403 -> "bloqueo" (6 h); si va bien, se olvida
                                                               (un 401 sigue siendo clave: terminal de 6 h)
  sin_creditos   402                                           TERMINAL para el proveedor: enfriar "bloqueo"
  timeout        excepcion *Timeout*                           anotar (3 seguidos = sin servicio), siguiente modelo
  red            otra excepcion de red                         siguiente modelo
  -- web --
  sesion         la web pide iniciar sesion (sesion caducada)  NOT_AVAILABLE y enfriar 1 h: lo arregla Damian
  captcha        navegador.Bloqueo                             BLOCKED (navegador ya para y avisa)
  limite_web     navegador.LimiteUso                           enfriar hasta la hora que muestra la web
  modo / fallo   ModoNoActivo, RespuestaNoVerificada, Chrome   ERROR: siguiente proveedor

Reglas de T157: espera maxima 60 s dentro de una llamada; el cambio de modelo vale solo para esa llamada (no se
toca ninguna configuracion); quien llama con UN modelo elegido (p.ej. Damian, o el tribunal) recibe el error en vez
de otro modelo, porque la lista solo tiene ese. Nada aqui imprime claves: los detalles llevan solo el tipo.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

ESPERA_MAXIMA = 60.0
ENFRIAR_SESION = 3600.0   # web con la sesion caducada: 1 h y se vuelve a mirar

_CUOTA = re.compile(r"per[\s_-]?day|daily|quota|RESOURCE_EXHAUSTED|free-models-per-day|\bTPD\b|\bRPD\b|"
                    r"tokens per day|requests per day|insufficient_quota|limit exceeded for today", re.I)
_CLAVE = re.compile(r"API key not valid|API_KEY_INVALID|invalid api key|invalid_api_key|unauthorized", re.I)
_SESION = re.compile(r"inicia(r)? sesi[oó]n|log ?in|sign ?in|sesi[oó]n caducada|session expired", re.I)


@dataclass(frozen=True)
class Clase:
    tipo: str
    accion: str               # "devolver" | "siguiente" | "repetir" | "terminal"
    enfriar: str | None = None    # tipo de enfriamiento del proveedor si es terminal
    espera: float = 0.0       # segundos antes de repetir (solo "repetir")
    anotar: object = None     # lo que se anota en modelos_estado ("ok", "timeout" o el codigo HTTP)


def _retry_after(cabeceras) -> float | None:
    try:
        v = (cabeceras or {}).get("retry-after") or (cabeceras or {}).get("Retry-After")
        return float(v) if v is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def clasificar(codigo: int | None = None, cuerpo: str = "", cabeceras=None, excepcion: BaseException | None = None,
               texto: str | None = None) -> Clase:
    """Clasifica UN intento contra un modelo. `texto` es el texto ya leido de un 200."""
    if excepcion is not None:
        if "Timeout" in type(excepcion).__name__:
            return Clase("timeout", "siguiente", anotar="timeout")
        return Clase("red", "siguiente")
    if codigo == 200:
        return Clase("ok", "devolver", anotar="ok") if (texto or "").strip() else Clase("vacia", "siguiente")
    cuerpo = cuerpo or ""
    if codigo == 429:
        if _CUOTA.search(cuerpo):
            return Clase("cuota", "siguiente", anotar=429)
        ra = _retry_after(cabeceras)
        if ra is not None and ra <= ESPERA_MAXIMA:
            return Clase("ritmo", "repetir", espera=max(1.0, ra), anotar=429)
        return Clase("ritmo", "siguiente", anotar=429)
    if codigo in (401, 403):
        if _CUOTA.search(cuerpo):
            return Clase("cuota", "siguiente", anotar=codigo)
        if codigo == 403:
            return Clase("clave_403", "terminal", enfriar="transitorio", anotar=codigo)
        return Clase("clave", "terminal", enfriar="bloqueo", anotar=codigo)
    if codigo == 402:
        return Clase("sin_creditos", "terminal", enfriar="bloqueo", anotar=402)
    if codigo in (404, 410):
        return Clase("retirado", "siguiente", anotar=codigo)
    if codigo in (500, 502, 503, 504, 529):
        return Clase("saturado", "siguiente", anotar=codigo)
    if codigo in (400, 413, 422):
        if _CLAVE.search(cuerpo):
            return Clase("clave", "terminal", enfriar="bloqueo", anotar=None)
        return Clase("peticion", "siguiente", anotar=codigo)
    return Clase("otro", "siguiente", anotar=codigo)


def enfriamiento_final(clases: list[Clase]) -> str | None:
    """Tras probar todos los modelos sin exito: que enfriamiento toca al proveedor (None = ninguno)."""
    tipos = {c.tipo for c in clases}
    if not clases:
        return None
    if tipos == {"cuota"}:
        return "cuota"
    if tipos <= {"cuota", "ritmo", "saturado"}:
        return "saturado"
    return None


def clasificar_web(excepcion: BaseException) -> Clase:
    """Excepciones del navegador (extremidades/navegador.py) a la misma tabla."""
    nombre = type(excepcion).__name__
    msg = str(excepcion)
    if nombre == "Bloqueo":
        if _SESION.search(msg):
            return Clase("sesion", "terminal", enfriar="bloqueo")
        return Clase("captcha", "terminal")
    if nombre == "LimiteUso":
        return Clase("limite_web", "terminal", enfriar="limite")
    if _SESION.search(msg):
        return Clase("sesion", "terminal", enfriar="bloqueo")
    return Clase("fallo_web", "siguiente")


def cascada(nombre: str, modelos, rondas: int, espera: float, pedir, leer, dormir=None,
            antes=None):
    """Bucle comun de los proveedores de API. `pedir(modelo)` hace la peticion HTTP (respuesta con status_code,
    json(), y si los tiene text y headers); `leer(json)` saca el texto. `antes(modelo)` puede devolver un Resultado
    para cortar (p.ej. el fail-closed de OpenRouter). Devuelve un proveedores.Resultado."""
    from nucleo import cuota, modelos_estado
    from nucleo.enfriamiento import enfriar, limpiar, transitorio_reciente
    from proveedores import Resultado
    dormir = dormir or time.sleep
    modelos = tuple(modelos)
    fallos: list[str] = []
    clases: list[Clase] = []
    sondeo = transitorio_reciente(nombre)   # T1013: esta llamada es la que sondea tras un 403 suelto
    for ronda, m in [(r, m) for r in range(rondas) for m in modelos]:
        if antes is not None:
            corte = antes(m)
            if corte is not None:
                return corte
        if ronda and m == modelos[0]:
            dormir(min(espera, ESPERA_MAXIMA))
        repetido = False
        while True:
            try:
                r = pedir(m)
            except Exception as e:  # noqa: BLE001 - solo el tipo: el mensaje podria arrastrar la cabecera
                c = clasificar(excepcion=e)
                fallos.append(f"{m}: {type(e).__name__}")
                break
            cuota.registrar(nombre, m, getattr(r, "headers", None))   # T684: cabeceras x-ratelimit-*
            if r.status_code == 200:
                try:
                    texto = (leer(r.json()) or "").strip()
                except Exception:
                    texto = ""
                c = clasificar(200, texto=texto)
                if c.accion == "devolver":
                    modelos_estado.anotar(nombre, m, "ok")
                    if sondeo:
                        limpiar(nombre)
                    return Resultado("OK", texto=texto, meta={"modelo": m})
                fallos.append(f"{m}: respuesta vacia")
                break
            cuerpo = str(getattr(r, "text", "") or "")[:2000]
            c = clasificar(r.status_code, cuerpo=cuerpo, cabeceras=getattr(r, "headers", None))
            fallos.append(f"{m}: HTTP {r.status_code}" + ("" if c.tipo in ("otro",) else f" ({c.tipo})"))
            if c.accion == "repetir" and not repetido:
                repetido = True
                dormir(c.espera)
                continue
            break
        clases.append(c)
        if c.anotar is not None:
            modelos_estado.anotar(nombre, m, c.anotar)
        if c.accion == "terminal":
            tipo_enf = c.enfriar or "bloqueo"
            if tipo_enf == "transitorio" and sondeo:
                tipo_enf = "bloqueo"   # el sondeo tambien dio 403: ya no es un 403 suelto
            enfriar(nombre, tipo_enf, fallos[-1])
            estado = "BLOCKED" if c.tipo in ("clave", "clave_403") else "ERROR"
            return Resultado(estado, detalle="; ".join(fallos), meta={"fallo": c.tipo})
    final = enfriamiento_final(clases)
    if final:
        enfriar(nombre, final, fallos[-1])
    return Resultado("ERROR", detalle="; ".join(fallos), meta={"fallo": clases[-1].tipo if clases else "sin_modelos"})
