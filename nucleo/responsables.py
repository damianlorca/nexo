# -*- coding: utf-8 -*-
"""Guardia de responsables (pedida por Damian el 05/10).

A Damian solo le puede quedar una tarea (depende=damian, prov:damian o triaje:damian) si de verdad depende de el:
  - datos:     sus datos personales (cat:personal, salud, papeles...)
  - dinero:    su dinero o sus cuentas (cobros, pagos, becas, tokens, contraseñas, Instagram...)
  - gustos:    sus gustos o una decision subjetiva suya (fechas que le vengan bien, sus proyectos)
  - presencia: su presencia fisica (grabar, firmar, una prueba con el delante)
Todo lo demas es trabajo de Claude, de la IA o del tribunal.

La razon sale, por este orden, de una etiqueta explicita `suyo:<motivo>` (la pone quien lo decide a sabiendas:
la web cuando Damian elige "Te toca a ti", o una nota de coordinacion), de `cat:personal`, o de palabras claras
del titulo/detalle. Sin razon, `corregir` la pasa a Claude y deja una nota. Lo aplica el core de tareas en cada
alta y cada cambio (nucleo/tareas.py), asi que vale igual para ordenes, turnos, triaje y tribunal.
`repaso()` es solo lectura: lo lanza el planificador de vez en cuando y el Centro avisa si sale alguna.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

MOTIVOS = {
    "datos": "sus datos personales",
    "dinero": "su dinero o sus cuentas",
    "gustos": "sus gustos o una decisión suya",
    "presencia": "su presencia física",
}
PREFIJO = "suyo:"
NOTA = "Guardia de responsables"

# Solo palabras claras: un falso positivo deja una tarea ajena a Damian, asi que mejor quedarse corto.
PALABRAS = {
    "dinero": r"\bpag(ar|o|os|ue)\b|\bcobr(ar|o|os)\b|factura|\bbanco\b|dinero|€|\beuros?\b|\bbecas?\b|matr[ií]cula"
              r"|suscripci[oó]n|contrase[ñn]a|\btoken del\b|\btoken de\b|botfather|instagram|\bsu cuenta\b"
              r"|iniciar sesi[oó]n|\bdeclaraci[oó]n de la renta\b|hacienda",
    "datos": r"m[ée]dico|\bsalud\b|\bdni\b|pasaporte|\bsus datos\b|empadronamiento",
    "gustos": r"\bsus gustos\b|\ble gust|\ble vengan? bien\b|\bprefiere\b|\belegir tema\b|\bsubjetiv",
    "presencia": r"\bgrabar\b|\bfirmar\b|\bfirma de\b|\bcita\b|en persona|presencial|con dami[aá]n delante",
}
_RX = {m: re.compile(p, re.I) for m, p in PALABRAS.items()}

CADA = timedelta(hours=1)
REPASO = Path(__file__).resolve().parent.parent / "memoria" / "responsables_repaso.json"


def es_de_damian(t: dict) -> bool:
    et = t.get("etiquetas") or []
    return t.get("depende") == "damian" or "prov:damian" in et or "triaje:damian" in et


def motivo(t: dict) -> str | None:
    """Por que la tarea es de Damian (clave de MOTIVOS), o None si no hay razon."""
    et = t.get("etiquetas") or []
    for e in et:
        if e.startswith(PREFIJO) and e[len(PREFIJO):] in MOTIVOS:
            return e[len(PREFIJO):]
    if "cat:personal" in et:
        return "datos"
    mq = str(t.get("motivo_quien") or "").strip().lower()   # formato v2 (T1010): quien=damian + motivo_quien
    for m in MOTIVOS:
        if mq.startswith(m):
            return m
    texto = f"{t.get('titulo') or ''}\n{t.get('detalle') or ''}"
    for m, rx in _RX.items():
        if rx.search(texto):
            return m
    return None


def es_suya(t: dict) -> bool:
    """Lo que puede salir en "Te toca": atribuida a Damian Y con una razon valida."""
    return es_de_damian(t) and motivo(t) is not None


def corregir(t: dict) -> str | None:
    """Si la tarea esta atribuida a Damian sin razon, la pasa a Claude (en el sitio) y devuelve la nota; si no, None."""
    if not es_de_damian(t) or motivo(t) is not None:
        return None
    antes = []
    if t.get("depende") == "damian":
        t["depende"] = "claude"
        antes.append("depende=damian")
    et = []
    for e in t.get("etiquetas") or []:
        nueva = {"prov:damian": "prov:claude", "triaje:damian": "triaje:sonnet"}.get(e, e)
        if nueva != e:
            antes.append(e)
        if nueva not in et:
            et.append(nueva)
    t["etiquetas"] = et
    return (f"{NOTA}: no depende de los datos, el dinero o las cuentas, los gustos ni la presencia de Damián; "
            f"pasa a Claude (antes: {', '.join(antes)}). Si de verdad es suya, ponle la etiqueta "
            f"suyo:{'|'.join(MOTIVOS)}.")


def mal_asignadas(tareas: list[dict], vivos: tuple | None = None) -> list[dict]:
    from nucleo import tareas as T
    vivos = vivos or T.VIVOS
    return [t for t in tareas if t.get("estado") in vivos and es_de_damian(t) and motivo(t) is None]


def repaso(ahora: datetime | None = None) -> dict:
    """Solo lectura sobre las tareas: guarda en REPASO las vivas mal asignadas (para el aviso del Centro)."""
    from nucleo import tareas as T
    malas = mal_asignadas(T.cargar()["tareas"])
    res = {"cuando": (ahora or datetime.now()).isoformat(timespec="seconds"),
           "mal_asignadas": [{"id": t["id"], "titulo": t["titulo"]} for t in malas]}
    REPASO.parent.mkdir(parents=True, exist_ok=True)
    REPASO.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def repaso_si_toca(ahora: datetime | None = None, cada: timedelta = CADA) -> dict | None:
    """Lo llama el planificador en cada tick: repasa si el ultimo repaso tiene mas de `cada` (o no hay)."""
    ahora = ahora or datetime.now()
    ultimo = ultimo_repaso()
    try:
        if ultimo and ahora - datetime.fromisoformat(ultimo["cuando"]) < cada:
            return None
    except (KeyError, TypeError, ValueError):
        pass
    return repaso(ahora)


def ultimo_repaso() -> dict | None:
    try:
        return json.loads(REPASO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _cli(argv: list[str]) -> int:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    from nucleo import tareas as T
    if argv[:1] == ["repaso"]:
        r = repaso()
        print(f"{len(r['mal_asignadas'])} mal asignadas")
        for x in r["mal_asignadas"]:
            print(f"  {x['id']}  {x['titulo']}")
        return 0
    for t in T.ordenadas([x for x in T.cargar()["tareas"] if x["estado"] in T.VIVOS and es_de_damian(x)]):
        print(f"{t['id']}  {motivo(t) or 'SIN RAZON'}  {t['titulo'][:90]}")
    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    import sys
    raise SystemExit(_cli(sys.argv[1:]))
