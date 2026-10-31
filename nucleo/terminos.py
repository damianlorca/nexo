# -*- coding: utf-8 -*-
"""T550: el vigia vigila los terminos de uso de los servicios que usa NEXO (Gemini/Google y ChatGPT/OpenAI).

NEXO respeta los terminos de cada servicio (Damian): si cambian, hay que enterarse. Una vez al dia (dentro del
turno vigia, nucleo/vigia.crear_lote) se lee cada pagina de TERMINOS, se saca su texto, se compara su huella con
la guardada y, si cambia: aviso en el Centro (nucleo/avisos) + tarea de revision con las frases que cambian.
La primera lectura solo guarda la linea base. Se lee con codigo, sin IA ni navegador.

OpenAI responde 403 a lectores automaticos (no se disfraza el agente para saltarlo): se intenta su ultima copia
en archive.org. Una pagina que no se puede leer queda como "sin leer" (nunca como "sin cambios") y, si lleva
DIAS_SIN_LEER dias asi, avisa en el Centro. El centro de privacidad de Gemini se probo y queda fuera: su texto
cambia en cada lectura (contenido dinamico) y daria falsas alarmas.

Estado: memoria/vigia/terminos.json y el ultimo texto de cada pagina en memoria/vigia/terminos/ (fuera de git).
CLI: .venv\\Scripts\\python.exe -m nucleo.terminos comprobar | estado
"""
from __future__ import annotations

import difflib
import hashlib
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from nucleo import vigia

TERMINOS = (
    {"clave": "gemini_api_terminos", "nombre": "Gemini API: términos adicionales",
     "url": "https://ai.google.dev/gemini-api/terms"},
    {"clave": "google_terminos", "nombre": "Google: términos del servicio",
     "url": "https://policies.google.com/terms?hl=es"},
    {"clave": "google_ia_usos_prohibidos", "nombre": "Google: política de usos prohibidos de la IA generativa",
     "url": "https://policies.google.com/terms/generative-ai/use-policy?hl=es"},
    {"clave": "openai_terminos", "nombre": "OpenAI: términos de uso",
     "url": "https://openai.com/policies/terms-of-use/", "archivo": True},
    {"clave": "openai_service_terms", "nombre": "OpenAI: service terms",
     "url": "https://openai.com/policies/service-terms/", "archivo": True},
    {"clave": "openai_politicas_uso", "nombre": "OpenAI: políticas de uso",
     "url": "https://openai.com/policies/usage-policies/", "archivo": True},
)
DIAS_SIN_LEER = 7
MIN_CARACTERES = 1500          # menos que esto no es la pagina de terminos (bloqueo, error, portada)
MAX_FRASES_DIFF = 12


def carpeta() -> Path:
    return vigia.CARPETA / "terminos"


def texto(pagina: str) -> str:
    t = re.sub(r"(?is)<(script|style|noscript|svg|template)[^>]*>.*?</\1>", " ", pagina)
    t = re.sub(r"(?s)<!--.*?-->", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return " ".join(html.unescape(t).split())


def _leer_directo(url: str) -> str:
    r = vigia._get(url, {"Accept": "text/html"})
    r.raise_for_status()
    return r.text


def _leer_archivo(url: str) -> str:
    """Ultima copia de la pagina en archive.org (para quien bloquea lectores automaticos)."""
    r = vigia._get("https://archive.org/wayback/available", params={"url": url})
    r.raise_for_status()
    copia = (r.json().get("archived_snapshots") or {}).get("closest") or {}
    if not copia.get("timestamp"):
        raise LookupError("sin copia en archive.org")
    r = vigia._get(f"https://web.archive.org/web/{copia['timestamp']}id_/{url}", {"Accept": "text/html"})
    r.raise_for_status()
    return r.text


def leer(t: dict, directo=_leer_directo, archivo=_leer_archivo) -> tuple[str, str]:
    """(texto, fuente). LookupError/HTTP/red si no se puede leer."""
    fallos = []
    for fuente, fn in (("directa", directo), ("archive.org", archivo if t.get("archivo") else None)):
        if fn is None:
            continue
        try:
            txt = texto(fn(t["url"]))
            if len(txt) >= MIN_CARACTERES:
                return txt, fuente
            fallos.append(f"{fuente}: solo {len(txt)} caracteres")
        except Exception as e:   # noqa: BLE001
            codigo = getattr(getattr(e, "response", None), "status_code", None)
            fallos.append(f"{fuente}: {f'HTTP {codigo}' if codigo else type(e).__name__}")
    raise LookupError("; ".join(fallos))


def huella(txt: str) -> str:
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()


def _frases(txt: str) -> list[str]:
    return [f.strip() for f in re.split(r"(?<=[.;:!?])\s+", txt) if f.strip()]


def cambios(antes: str, ahora: str, maximo: int = MAX_FRASES_DIFF) -> list[str]:
    """Frases quitadas (-) y nuevas (+), como mucho `maximo`."""
    salida = []
    for linea in difflib.unified_diff(_frases(antes), _frases(ahora), lineterm="", n=0):
        if linea[:1] in "+-" and not linea.startswith(("+++", "---")):
            salida.append(f"{linea[0]} {linea[1:][:300]}")
    return salida[:maximo] + ([f"... y {len(salida) - maximo} líneas más"] if len(salida) > maximo else [])


def comprobar(ahora: datetime | None = None, leer_=leer, avisar=None, crear_tarea=None) -> dict:
    """Lee cada pagina y compara. {clave: "base"|"igual"|"cambio"|"sin leer: ..."}."""
    from nucleo import avisos
    from nucleo import tareas as T
    ahora = ahora or datetime.now()
    avisar = avisar or (lambda titulo, cuerpo, ruta, clave: avisos.emitir("terminos", titulo, cuerpo, ruta=ruta,
                                                                          clave=clave))
    crear_tarea = crear_tarea or (lambda titulo, detalle: T.anadir(
        titulo, detalle=detalle, importancia=4, urgencia=3, dificultad=2, coste=1, depende="claude",
        etiquetas=["terminos", "area:seguridad", "origen:T550"]))
    estado = vigia._leer("terminos.json", {})
    carpeta().mkdir(parents=True, exist_ok=True)
    hoy = ahora.strftime("%Y-%m-%d")
    resultado = {}
    for t in TERMINOS:
        e = estado.setdefault(t["clave"], {})
        try:
            txt, fuente = leer_(t)
        except Exception as ex:   # noqa: BLE001
            e.setdefault("sin_leer_desde", hoy)
            e["error"] = str(ex)[:200]
            resultado[t["clave"]] = f"sin leer: {e['error']}"
            dias = (ahora - datetime.strptime(e["sin_leer_desde"], "%Y-%m-%d")).days
            if dias >= DIAS_SIN_LEER:
                avisar(f"No puedo leer: {t['nombre']}", f"Lleva {dias} días sin poder leerse ({e['error']}). "
                       "Mientras, NEXO no sabe si esos términos han cambiado.", "/turnos",
                       f"terminos_sin_leer:{t['clave']}:{hoy}")
            continue
        e.pop("sin_leer_desde", None)
        e.pop("error", None)
        h = huella(txt)
        guardado = carpeta() / f"{t['clave']}.txt"
        e.update(comprobado=ahora.strftime("%Y-%m-%d %H:%M"), fuente=fuente, largo=len(txt))
        if not e.get("huella"):
            resultado[t["clave"]] = "base"
        elif e["huella"] == h:
            resultado[t["clave"]] = "igual"
        else:
            try:
                antes = guardado.read_text(encoding="utf-8")
            except OSError:
                antes = ""
            lineas = cambios(antes, txt)
            tarea = crear_tarea(f"Revisar cambio de términos: {t['nombre']} ({ahora:%d/%m})",
                                f"T550: el vigía ve un cambio en {t['url']} (leído por {fuente}). Comprobar si "
                                "afecta a cómo usa NEXO ese servicio y, si hace falta, proponer el cambio.\n"
                                "FRASES QUE CAMBIAN:\n" + ("\n".join(lineas) or "(sin texto anterior guardado)"))
            avisar(f"Cambian los términos: {t['nombre']}", f"{len(lineas)} cambios; revisión en "
                   f"{tarea['id'] if tarea else 'una tarea'}.", f"/tareas/{tarea['id']}" if tarea else "/",
                   f"terminos:{t['clave']}:{h[:12]}")
            e["cambio"] = ahora.strftime("%Y-%m-%d")
            resultado[t["clave"]] = "cambio"
        e["huella"] = h
        guardado.write_text(txt, encoding="utf-8")
    vigia._escribir("terminos.json", estado)
    return resultado


def _cli(argv: list[str]) -> int:
    if argv[:1] == ["comprobar"]:
        for k, v in comprobar().items():
            print(f"{k}: {v}")
        return 0
    if argv[:1] == ["estado"]:
        print(json.dumps(vigia._leer("terminos.json", {}), ensure_ascii=False, indent=1))
        return 0
    print("uso: python -m nucleo.terminos comprobar | estado")
    return 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(_cli(sys.argv[1:]))
