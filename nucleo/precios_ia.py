# -*- coding: utf-8 -*-
"""Radar de precios por IA (T665, decidido el 05/10): una vez a la semana se pregunta a ChatGPT web (y, si falla,
a Gemini web), con el navegador y las cuentas de NEXO, el precio actual de cada candidato de nucleo/precios.py.

Por que: ninguna tienda se deja leer con codigo (ver nucleo/precios.py). La IA busca en la web; NEXO no se fia:
- se le pide JSON con el enlace de la tienda, el nombre EXACTO del producto y el precio;
- solo se apunta si el enlace es de una tienda espanola (dominio .es o tienda espanola conocida) y el nombre es el
  mismo modelo exacto (patrones de MODELOS: 5700G no vale por 5700GE, 32 GB no vale por 16 GB...);
- lo demas se descarta CON MOTIVO (queda en memoria/radares/precios/ia.jsonl, una linea por pregunta);
- todo aviso de bajada dice "comprobar a mano antes de comprar" (nucleo/precios.registrar).
La pregunta solo lleva el nombre del producto (nada de memoria/ ni del vault). La respuesta es contenido externo:
solo se leen de ella un numero, una URL y un nombre, y nunca se siguen instrucciones que traiga.

CLI: .venv\\Scripts\\python.exe -m nucleo.precios_ia pasada [--simular] | toca
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from nucleo import precios, radar

CADA = timedelta(days=7)
PROVEEDORES = ("chatgpt", "gemini")

# Tiendas espanolas con dominio que no es .es (el resto tiene que acabar en .es).
TIENDAS_ES = ("pccomponentes.com", "coolmod.com", "wipoid.com", "izarmicro.net", "app-informatica.com",
              "life-informatica.com", "versus-gamers.com", "ldlc.com/es-es", "alternate.es", "neobyte.es")

# id -> (patrones que el nombre exacto TIENE que cumplir, patrones que NO puede tener). Sobre el nombre en minusculas.
MODELOS = {
    "um760_16_512_amazon": ([r"\bum760\b", r"\b16\s?gb\b", r"\b512\s?gb\b"], [r"\bum760\s?pro\b"]),
    "um870_32_512_amazon": ([r"\bum870\b", r"\b32\s?gb\b", r"\b512\s?gb\b"], []),
    "um870_32_1tb_amazon": ([r"\bum870\b", r"\b32\s?gb\b", r"\b1\s?tb\b"], []),
    "r7_5700g_pccom": ([r"\bryzen\s?7\b", r"\b5700g\b"], [r"5700ge\b", r"5700x"]),
    "r7_5700g_amazon": ([r"\bryzen\s?7\b", r"\b5700g\b"], [r"5700ge\b", r"5700x"]),
    "r7_5700g_coolmod": ([r"\bryzen\s?7\b", r"\b5700g\b"], [r"5700ge\b", r"5700x"]),
    "r5_5600gt_pccom": ([r"\bryzen\s?5\b", r"\b5600gt\b"], [r"5600g\b", r"5600x"]),
    "b550m_ds3h_r2_pccom": ([r"\bb550m\b", r"\bds3h\b", r"\br2\b"], [r"\bac\b", r"wifi"]),
    "ddr4_32_aegis_pccom": ([r"\baegis\b", r"\bddr4\b", r"\b3200\b", r"\b32\s?gb\b"], []),
    "nv3_1tb_pccom": ([r"\bnv3\b", r"\b1\s?tb\b"], [r"\b2\s?tb\b", r"\b500\s?gb\b"]),
    "mwe_gold_550_pccom": ([r"\bmwe\b", r"\bgold\b", r"\bv3\b", r"\b550\s?w?\b"], [r"\b650\b", r"\b750\b"]),
    "focus2_tg_pccom": ([r"\bfocus\s?2\b"], [r"\brgb\b"]),
    "ironwolf_4tb_pccom": ([r"\bironwolf\b", r"\b4\s?tb\b"], [r"\bpro\b"]),
    "r5_8600g_pccom": ([r"\bryzen\s?5\b", r"\b8600g\b"], [r"8600gt", r"8600x"]),
}

PREGUNTA = (
    "Busca en la web el precio ACTUAL en una tienda española del producto «{nombre}» (exactamente este modelo; "
    "si en {tienda} no está, otra tienda española). Contesta SOLO con un JSON, sin nada más: "
    '{{"precio": 123.45, "tienda": "dominio de la tienda", "url": "enlace directo a la ficha del producto", '
    '"nombre_exacto": "nombre del producto tal como sale en la ficha"}}. Si no lo encuentras con enlace a la '
    'ficha, contesta {{"precio": null, "motivo": "..."}}. No inventes precios ni enlaces.'
)


def _carpeta():
    return radar.carpeta(precios.RADAR)


def _registro(lineas: list[dict]) -> None:
    _carpeta().mkdir(parents=True, exist_ok=True)
    with open(_carpeta() / "ia.jsonl", "a", encoding="utf-8") as f:
        for d in lineas:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def leer_registro() -> list[dict]:
    try:
        texto = (_carpeta() / "ia.jsonl").read_text(encoding="utf-8")
    except OSError:
        return []
    salida = []
    for l in texto.splitlines():
        try:
            salida.append(json.loads(l))
        except ValueError:
            continue
    return salida


def ultima_pasada() -> datetime | None:
    pasadas = [d["cuando"] for d in leer_registro() if d.get("tipo") == "pasada"]
    return datetime.fromisoformat(max(pasadas)) if pasadas else None


def toca(ahora: datetime | None = None) -> bool:
    ultima = ultima_pasada()
    return ultima is None or (ahora or datetime.now()) - ultima >= CADA


# ------------------------------------------------------------------ validar (sin red)
def extraer_json(texto: str) -> dict | None:
    """El primer objeto JSON de la respuesta (con o sin ```json). None si no hay."""
    for m in re.finditer(r"\{[^{}]*\}", texto or "", re.S):
        try:
            d = json.loads(m.group(0))
        except ValueError:
            continue
        if isinstance(d, dict):
            return d
    return None


def tienda_espanola(url: str) -> str | None:
    """El dominio si el enlace es https a una tienda espanola; None si no."""
    try:
        partes = urlsplit(str(url or "").strip())
    except ValueError:
        return None
    host = (partes.hostname or "").lower().removeprefix("www.")
    if partes.scheme != "https" or not host:
        return None
    if host.endswith(".es"):
        return host
    for t in TIENDAS_ES:
        dominio, _, ruta = t.partition("/")
        if (host == dominio or host.endswith("." + dominio)) and (not ruta or partes.path.lower().startswith("/" + ruta)):
            return host
    return None


def mismo_modelo(producto: str, nombre_exacto: str) -> str | None:
    """None si el nombre es el mismo modelo exacto; si no, el motivo."""
    if producto not in MODELOS:
        return "producto sin patron de modelo exacto: no se apunta nada"
    nombre = re.sub(r"\s+", " ", str(nombre_exacto or "").lower())
    if not nombre:
        return "sin nombre exacto del producto"
    si, no = MODELOS[producto]
    for p in si:
        if not re.search(p, nombre):
            return f"no es el mismo modelo (falta {p!r} en «{nombre_exacto[:80]}»)"
    for p in no:
        if re.search(p, nombre):
            return f"es otro modelo ({p!r} en «{nombre_exacto[:80]}»)"
    return None


def validar(producto: str, respuesta: str) -> dict:
    """{ok, motivo, precio, tienda, url, nombre_exacto}. Solo ok con enlace espanol y mismo modelo exacto."""
    d = extraer_json(respuesta)
    if d is None:
        return {"ok": False, "motivo": "la respuesta no trae JSON"}
    if d.get("precio") in (None, "", 0):
        return {"ok": False, "motivo": f"no lo encontro: {str(d.get('motivo') or '')[:120]}"}
    precio = precios._precio(d.get("precio"))
    if precio is None or not 1 <= precio <= 20000:
        return {"ok": False, "motivo": f"precio no valido: {str(d.get('precio'))[:40]}"}
    tienda = tienda_espanola(d.get("url"))
    base = {"precio": precio, "url": str(d.get("url") or "")[:300], "nombre_exacto": str(d.get("nombre_exacto") or "")[:200]}
    if tienda is None:
        return {"ok": False, "motivo": "sin enlace https a una tienda espanola", **base}
    motivo = mismo_modelo(producto, base["nombre_exacto"])
    if motivo:
        return {"ok": False, "motivo": motivo, **base, "tienda": tienda}
    return {"ok": True, "motivo": "", **base, "tienda": tienda}


# ------------------------------------------------------------------ preguntar (con navegador)
def _preguntar_web(proveedor: str, texto: str) -> str:
    import proveedores
    p = proveedores.ChatGPTProvider() if proveedor == "chatgpt" else proveedores.GeminiProvider()
    r = p.enviar(texto)
    if not r.ok:
        raise RuntimeError(f"{proveedor}: {r.estado} {r.detalle[:120]}")
    return r.texto


def pasada(ahora: datetime | None = None, simular: bool = False, preguntar=_preguntar_web) -> dict:
    """Pregunta por cada candidato. Apunta solo lo valido; en simulacion no escribe historico ni avisa."""
    ahora = ahora or datetime.now()
    apuntados, descartados, lineas = {}, {}, []
    for f in radar.cargar_config(precios.RADAR)["fuentes"]:
        pid = f["id"]
        if pid not in MODELOS:
            continue
        nombre = re.sub(r"\s*\(.*?\)", "", f.get("nombre") or pid).strip()
        texto = PREGUNTA.format(nombre=nombre, tienda=f.get("tienda") or "una tienda española")
        v, quien = {"ok": False, "motivo": "ningun proveedor contesto"}, ""
        for prov in PROVEEDORES:
            try:
                v = validar(pid, preguntar(prov, texto))
                quien = prov
                break
            except Exception as e:   # noqa: BLE001 - un proveedor caido no tumba la pasada
                v = {"ok": False, "motivo": f"{prov} no contesto: {type(e).__name__}: {str(e)[:100]}"}
        lineas.append({"cuando": ahora.isoformat(timespec="seconds"), "tipo": "respuesta", "id": pid,
                       "proveedor": quien, **v})
        if not v["ok"]:
            descartados[pid] = v["motivo"]
            continue
        apuntados[pid] = v["precio"]
        if not simular:
            precios.registrar(pid, v["precio"], ahora, origen=f"ia:{quien}_web",
                              extra={"tienda": v["tienda"], "url": v["url"], "nombre_exacto": v["nombre_exacto"]})
    if not simular:
        lineas.append({"cuando": ahora.isoformat(timespec="seconds"), "tipo": "pasada",
                       "apuntados": len(apuntados), "descartados": len(descartados)})
        _registro(lineas)
    return {"cuando": ahora.isoformat(timespec="seconds"), "simular": simular, "apuntados": apuntados,
            "descartados": descartados}


def _cli(argv: list[str]) -> int:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    orden = argv[0] if argv else ""
    if orden == "toca":
        print(f"ultima pasada: {ultima_pasada()}; toca ahora: {toca()}")
        return 0
    if orden == "pasada":
        print(json.dumps(pasada(simular="--simular" in argv), ensure_ascii=False, indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    import sys
    raise SystemExit(_cli(sys.argv[1:]))
