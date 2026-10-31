# -*- coding: utf-8 -*-
"""Radar de precios (T665, 05/10/2026): el precio de cada candidato, cada dia, con historico y aviso de bajada.

Es un radar mas del motor (nucleo/radar.py): vive en `memoria/radares/precios/config.json` con `"clase": "precios"`
y el turno `radar` lo pasa una vez al dia. Cada fuente es UN producto en UNA tienda:
  {"id": "um870_32_512_amazon", "nombre": "...", "tienda": "amazon.es", "url": "...", "tipo": "jsonld" | "manual",
   "terminos": "como se respeta su web", "activa": false, "motivo_inactiva": "..."}
- `jsonld` lee la ficha publica y saca el precio del JSON-LD schema.org (Product -> offers). Antes mira el robots.txt
  de la tienda; un 403/429 o un desafio anti-bots (Cloudflare) NO se reintenta ni se esquiva: se apunta el error y la
  tienda queda parada ese dia. Sin `terminos` no se lee nunca (regla del motor).
- `manual`: el precio lo apunta alguien que lo ha mirado (`apuntar`), con fecha y quien.
Historico en `historico.jsonl` (una linea por precio visto; nada se borra). El minimo cuenta DESDE el primer precio
registrado (05/10): el primero de cada producto es solo linea base. Si uno baja de su minimo registrado, aviso en el
Centro (nucleo/avisos.py: panel y push; nada de Telegram).

Estado 05/10: NINGUNA tienda se puede leer con codigo. Amazon.es prohibe robots y extraccion de datos en sus condiciones
de uso; el aviso legal de Coolmod prohibe "extraer" su contenido o meterlo en bases de datos; PcComponentes devuelve
403 con desafio de Cloudflare a una peticion normal identificada (robots.txt si permite las fichas). Por eso todas las
fuentes estan inactivas con su motivo y los precios se apuntan a mano.

CLI: .venv\\Scripts\\python.exe -m nucleo.precios instalar | lista | pasada | apuntar <id> <precio> [quien] | historico [id]
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from nucleo import radar

RADAR = "precios"
PAUSA_TIENDA = 5.0     # s entre dos fichas de la misma tienda
_JSONLD = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)


class Bloqueado(RuntimeError):
    """La tienda no deja leerla con codigo (robots.txt, 403/429, desafio anti-bots). No se insiste."""


# ------------------------------------------------------------------ lectura
def _precio(valor) -> float | None:
    """'1.234,56 €', '229.02', 229.02 -> float; None si no se entiende."""
    if isinstance(valor, (int, float)):
        return float(valor)
    s = re.sub(r"[^\d,.]", "", str(valor or ""))
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _productos(dato):
    if isinstance(dato, list):
        for d in dato:
            yield from _productos(d)
    elif isinstance(dato, dict):
        tipo = dato.get("@type")
        if tipo == "Product" or (isinstance(tipo, list) and "Product" in tipo):
            yield dato
        for d in dato.get("@graph") or []:
            yield from _productos(d)


def precio_de_html(html: str) -> dict | None:
    """{precio, disponible, vendedor} del primer Product con oferta en el JSON-LD; None si no hay."""
    for bloque in _JSONLD.findall(html or ""):
        try:
            datos = json.loads(bloque.strip())
        except ValueError:
            continue
        for prod in _productos(datos):
            ofertas = prod.get("offers") or []
            for o in (ofertas if isinstance(ofertas, list) else [ofertas]):
                if not isinstance(o, dict):
                    continue
                p = _precio(o.get("price") if o.get("price") not in (None, "") else o.get("lowPrice"))
                if p is not None and p > 0:
                    vendedor = o.get("seller")
                    return {"precio": round(p, 2),
                            "disponible": "InStock" in str(o.get("availability") or "InStock"),
                            "vendedor": (vendedor.get("name") if isinstance(vendedor, dict) else vendedor) or ""}
    return None


def _robots(url: str, get, cache: dict) -> RobotFileParser:
    host = "{0.scheme}://{0.netloc}".format(urlsplit(url))
    if host not in cache:
        rp = RobotFileParser()
        r = get(host + "/robots.txt")
        if getattr(r, "status_code", 200) >= 400:
            rp.parse([])                       # sin robots.txt: no hay reglas
        else:
            rp.parse((r.text or "").splitlines())
        cache[host] = rp
    return cache[host]


def leer_jsonld(fuente: dict, get=radar._get, robots: dict | None = None) -> dict:
    url = fuente["url"]
    ua = radar.UA["User-Agent"]
    if not _robots(url, get, robots if robots is not None else {}).can_fetch(ua, url):
        raise Bloqueado("robots.txt no permite leer esta ficha")
    r = get(url)
    codigo = getattr(r, "status_code", 200)
    cabeceras = getattr(r, "headers", {}) or {}
    if codigo in (403, 429, 503) or cabeceras.get("cf-mitigated"):
        raise Bloqueado(f"HTTP {codigo}{' (desafio anti-bots)' if cabeceras.get('cf-mitigated') else ''}: no se insiste")
    r.raise_for_status()
    dato = precio_de_html(r.text)
    if not dato:
        raise ValueError("la ficha no trae precio en JSON-LD")
    return dato


# ------------------------------------------------------------------ almacen
def _carpeta():
    return radar.carpeta(RADAR)


def historico(producto: str | None = None) -> list[dict]:
    ruta = _carpeta() / "historico.jsonl"
    if not ruta.exists():
        return []
    salida = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(linea)
        except ValueError:
            continue
        if producto is None or d.get("id") == producto:
            salida.append(d)
    return salida


def _anadir(lineas: list[dict]) -> None:
    from nucleo.candado import bloqueo
    _carpeta().mkdir(parents=True, exist_ok=True)
    with bloqueo(_carpeta() / ".candado"):
        with open(_carpeta() / "historico.jsonl", "a", encoding="utf-8") as f:
            for d in lineas:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")


def minimo(producto: str, antes_de: str | None = None) -> dict | None:
    """La linea con el precio mas bajo registrado (la primera, si empatan); solo las de antes de `antes_de`."""
    lineas = [d for d in historico(producto) if antes_de is None or str(d.get("cuando")) < antes_de]
    return min(lineas, key=lambda d: (d["precio"], d["cuando"])) if lineas else None


def _fuente(producto: str) -> dict:
    for f in radar.cargar_config(RADAR)["fuentes"]:
        if f["id"] == producto:
            return f
    raise KeyError(f"producto desconocido en el radar de precios: {producto}")


def registrar(producto: str, precio: float, ahora: datetime | None = None, origen: str = "codigo",
              extra: dict | None = None, avisar: bool = True) -> dict:
    """Apunta un precio. Si baja del minimo registrado antes, deja un aviso para el Centro."""
    ahora = ahora or datetime.now()
    f = _fuente(producto)
    marca = ahora.isoformat(timespec="seconds")
    previo = minimo(producto, antes_de=marca)
    linea = {"cuando": marca, "id": producto, "nombre": f.get("nombre") or producto, "tienda": f.get("tienda") or "",
             "precio": round(float(precio), 2), "origen": origen, **(extra or {})}
    _anadir([linea])
    resultado = {**linea, "minimo_previo": previo["precio"] if previo else None, "baja": False, "aviso": None}
    if previo and linea["precio"] < previo["precio"]:
        resultado["baja"] = True
        if avisar:
            from nucleo import avisos
            ruta = avisos.emitir(
                "precio", f"Baja de precio: {linea['nombre']}",
                f"{linea['precio']:.2f} € en {linea['tienda']} (mínimo anterior {previo['precio']:.2f} € el "
                f"{previo['cuando'][:10]}). Comprobar a mano antes de comprar. {linea.get('url') or f.get('url', '')}",
                ruta="/", clave=f"precio:{producto}:{linea['precio']:.2f}", urgencia="normal")
            resultado["aviso"] = ruta.name if ruta else None
    return resultado


def apuntar(producto: str, precio: str | float, quien: str = "damian", ahora: datetime | None = None) -> dict:
    p = _precio(precio)
    if p is None or p <= 0:
        raise ValueError(f"precio no valido: {precio!r}")
    return registrar(producto, p, ahora, origen=f"manual:{quien}")


# ------------------------------------------------------------------ pasada (la llama radar.pasada)
def pasada(ahora: datetime | None = None, simular: bool = False, get=radar._get, pausa: float = PAUSA_TIENDA) -> dict:
    """Lee las fuentes activas y apunta su precio. En simulacion no escribe historico ni avisa: solo informa."""
    ahora = ahora or datetime.now()
    cfg = radar.cargar_config(RADAR)
    leidos, errores, saltadas, bajas = {}, {}, {}, []
    robots, visitadas, bloqueadas = {}, set(), set()
    for f in cfg["fuentes"]:
        if f.get("tipo") == "manual":
            continue
        motivo = _motivo(f)
        if motivo:
            saltadas[f["id"]] = motivo
            continue
        tienda = urlsplit(f["url"]).netloc
        if tienda in bloqueadas:
            saltadas[f["id"]] = "la tienda bloqueo una lectura anterior en esta pasada: no se insiste"
            continue
        if tienda in visitadas and pausa:
            time.sleep(pausa)
        visitadas.add(tienda)
        try:
            dato = leer_jsonld(f, get, robots)
        except Bloqueado as e:
            errores[f["id"]] = f"BLOQUEADO: {e}"[:200]
            bloqueadas.add(tienda)
            continue
        except Exception as e:   # noqa: BLE001 - una ficha caida no tumba el resto
            errores[f["id"]] = f"{type(e).__name__}: {e}"[:200]
            continue
        leidos[f["id"]] = dato["precio"]
        if not simular:
            r = registrar(f["id"], dato["precio"], ahora, extra={k: dato[k] for k in ("disponible", "vendedor")})
            if r["baja"]:
                bajas.append({"id": f["id"], "precio": r["precio"], "minimo_previo": r["minimo_previo"]})
    informe ={"radar": RADAR, "cuando": ahora.isoformat(timespec="seconds"), "simular": simular,
               "por_fuente": leidos, "errores": errores, "saltadas": saltadas, "leidos": len(leidos), "repetidos": 0,
               "linea_base": 0, "candidatos": len(leidos), "bajas": bajas,
               "publicadas": [{"id": b["id"], "titulo": f"{b['id']}: {b['precio']} €"} for b in bajas]}
    estado = radar._leer_estado(RADAR, simular)
    estado.update(ultima=informe["cuando"], ultimo={k: informe[k] for k in ("por_fuente", "errores", "saltadas",
                                                                           "leidos", "bajas")})
    radar._escribir(RADAR, f"estado{radar._sufijo(simular)}.json", estado)
    return informe


def _motivo(f: dict) -> str | None:
    if f.get("activa") is False:
        return f.get("motivo_inactiva") or "desactivada"
    if not str(f.get("terminos") or "").strip():
        return "sin terminos comprobados (como se respeta su web): no se lee"
    if f.get("tipo") != "jsonld":
        return f"tipo de lector desconocido: {f.get('tipo')!r}"
    return None


def resumen() -> list[dict]:
    """Por producto: ultimo precio, minimo registrado y si su tienda se lee sola o a mano."""
    salida = []
    for f in radar.cargar_config(RADAR)["fuentes"]:
        h = historico(f["id"])
        m = minimo(f["id"])
        salida.append({"id": f["id"], "nombre": f.get("nombre"), "tienda": f.get("tienda"), "url": f.get("url"),
                       "lectura": "manual" if f.get("tipo") == "manual" else (_motivo(f) or "automatica"),
                       "ultimo": h[-1]["precio"] if h else None, "ultimo_cuando": h[-1]["cuando"] if h else None,
                       "minimo": m["precio"] if m else None, "minimo_cuando": m["cuando"] if m else None})
    return salida


# ------------------------------------------------------------------ configuracion inicial
_AMAZON = ("Condiciones de uso de Amazon.es: la licencia excluye el uso de robots, data mining y herramientas "
           "de extraccion de datos (comprobado 05/10/2026)")
_COOLMOD = ("Aviso legal de Coolmod (s. 6): prohibe extraer el contenido o incorporarlo a bases de datos sin "
            "consentimiento escrito (comprobado 05/10/2026)")
_PCCOM = ("robots.txt permite las fichas a User-agent * (bloquea Python-urllib), pero una peticion normal e "
          "identificada recibe 403 con desafio de Cloudflare (05/10/2026): no se esquiva")

# (id, nombre, tienda, url, precio del 05/10 consultado a mano en la investigacion de T665)
CANDIDATOS = [
    ("um760_16_512_amazon", "Minisforum UM760 Slim 16/512", "amazon.es", "https://www.amazon.es/dp/B0GGB27B6G", 569.00),
    ("um870_32_512_amazon", "Minisforum UM870 Slim 32/512", "amazon.es", "https://www.amazon.es/dp/B0GK6DX23V", 689.00),
    ("um870_32_1tb_amazon", "Minisforum UM870 Slim 32/1TB", "amazon.es", "https://www.amazon.es/dp/B0DLB8FMX7", 749.00),
    ("r7_5700g_pccom", "AMD Ryzen 7 5700G", "pccomponentes.com",
     "https://www.pccomponentes.com/amd-ryzen-7-5700g-46ghz", 229.02),
    ("r7_5700g_amazon", "AMD Ryzen 7 5700G", "amazon.es", "https://www.amazon.es/dp/B0BKQWLPP6", 216.72),
    ("r7_5700g_coolmod", "AMD Ryzen 7 5700G", "coolmod.com",
     "https://www.coolmod.com/amd-ryzen-7-5700g-4-6ghz-socket-am4-boxed-procesador/", 239.96),
    ("r5_5600gt_pccom", "AMD Ryzen 5 5600GT (agotado el 05/10)", "pccomponentes.com",
     "https://www.pccomponentes.com/amd-ryzen-5-5600gt-36-46ghz-box", 149.89),
    ("b550m_ds3h_r2_pccom", "Gigabyte B550M DS3H R2", "pccomponentes.com",
     "https://www.pccomponentes.com/placa-base-gigabyte-b550m-ds3h-r2-am4-micro-atx-ddr4-dual-m-2-128gb-lan-1gbe", 79.94),
    ("ddr4_32_aegis_pccom", "G.Skill Aegis DDR4 3200 32 GB", "pccomponentes.com",
     "https://www.pccomponentes.com/memoria-ram-g-skill-aegis-ddr4-3200mhz-32gb-2x16gb-cl16", 241.99),
    ("nv3_1tb_pccom", "Kingston NV3 1 TB", "pccomponentes.com",
     "https://www.pccomponentes.com/disco-duro-kingston-nv3-1tb-disco-ssd-6000mb-s-nvme-pcie-40-m2-gen4-2280-3d-nand", 149.95),
    ("mwe_gold_550_pccom", "Cooler Master MWE Gold V3 550 W", "pccomponentes.com",
     "https://www.pccomponentes.com/fuente-alimentacion-fuente-de-alimentacion-cooler-master-mwe-gold-v3-550w-certificacion-80-plus-gold-atx-3-1", 64.96),
    ("focus2_tg_pccom", "Fractal Design Focus 2 TG", "pccomponentes.com",
     "https://www.pccomponentes.com/torre-pc-fractal-design-focus-2-tg-mid-tower-cristal-templado-usb-3-2-negro", 64.99),
    ("ironwolf_4tb_pccom", "Seagate IronWolf 4 TB", "pccomponentes.com",
     "https://www.pccomponentes.com/disco-duro-seagate-ironwolf-nas-4tb-disco-interno-hdd-3-5-sata-3", 214.95),
    ("r5_8600g_pccom", "AMD Ryzen 5 8600G (variante AM5)", "pccomponentes.com",
     "https://www.pccomponentes.com/amd-ryzen-5-8600g-43-5ghz-box", 159.99),
]


def config_inicial() -> dict:
    motivos = {"amazon.es": _AMAZON, "coolmod.com": _COOLMOD, "pccomponentes.com": _PCCOM}
    fuentes = [{"id": i, "nombre": n, "tienda": t, "url": u, "tipo": "jsonld", "terminos": motivos[t],
                "activa": False, "motivo_inactiva": "la tienda no permite leerla con codigo: " + motivos[t]}
               for i, n, t, u, _ in CANDIDATOS]
    return {"id": RADAR, "clase": "precios", "nombre": "Precios (T665)", "activo": True, "modo": "real",
            "fuentes": fuentes}


def instalar(ahora: datetime | None = None) -> dict:
    """Crea el config si no existe (no pisa uno editado) y apunta como linea base los precios consultados a mano el
    05/10 en la investigacion de T665, solo para los productos que aun no tengan historico."""
    ruta = _carpeta() / "config.json"
    creado = not ruta.exists()
    if creado:
        radar._escribir(RADAR, "config.json", config_inicial())
    ahora = ahora or datetime(2026, 10, 5, 18, 0)
    base = []
    for i, _, _, _, precio in CANDIDATOS:
        if not historico(i):
            base.append(registrar(i, precio, ahora, origen="manual:claude (investigacion T665, 05/10)",
                                  avisar=False)["id"])
    return {"config_creado": creado, "linea_base": base}


def _cli(argv: list[str]) -> int:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    orden, resto = (argv[0] if argv else "lista"), argv[1:]
    if orden == "instalar":
        print(json.dumps(instalar(), ensure_ascii=False, indent=1))
        return 0
    if orden == "lista":
        for r in resumen():
            print(f"{r['id']:<24} {str(r['ultimo']):>8} € (min {r['minimo']} € {str(r['minimo_cuando'])[:10]})  "
                  f"{r['lectura'][:60]}")
        return 0
    if orden == "pasada":
        inf = pasada()
        print(json.dumps({k: v for k, v in inf.items() if k != "publicadas"}, ensure_ascii=False, indent=1))
        return 0
    if orden == "apuntar" and len(resto) >= 2:
        r = apuntar(resto[0], resto[1], *(resto[2:3] or ["damian"]))
        print(f"{r['id']}: {r['precio']} € (minimo previo {r['minimo_previo']}){'  BAJA: aviso en el Centro' if r['baja'] else ''}")
        return 0
    if orden == "historico":
        for d in historico(resto[0] if resto else None):
            print(f"{d['cuando']}  {d['id']:<24} {d['precio']:>8.2f} €  {d.get('origen', '')}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    import sys
    raise SystemExit(_cli(sys.argv[1:]))
