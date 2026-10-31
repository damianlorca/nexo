"""Catalogo de herramientas, repos y skills a auditar para NEXO / Claude / el PC.

Por que existe
--------------
Damian (23/09) va pasando listas de herramientas que "pueden servir". Muchas
se podran integrar, otras conviene no instalarlas pero tenerlas conocidas por
si hacen falta. Pidio una lista tipo cola de tareas donde se vean todas, con
su estado de auditoria/instalacion/pruebas, para ir mirandolas de una en una.

Mismo patron que nucleo/tareas.py: el almacen es memoria/catalogo.json
(versionado en git) y la vista legible se GENERA en el vault
(contexto/proyectos/nexo/catalogo-herramientas.md). No se edita la vista a
mano: se usa este modulo (CLI abajo) para que cualquier IA pueda actualizarlo.

Campos de estado (valores permitidos en VALORES):
  auditado   no | primera_pasada | completo
             primera_pasada = identificado y resumido (que es, riesgo a ojo);
             completo = leido el codigo/contenido real, con informe.
  veredicto  PENDIENTE | ADOPTAR | ADOPTAR_SELECTIVO | REFERENCIA | APARCADO | NO_USAR
  instalado  no | en_curso | parcial | si
  funcional  - | si | no        (¿hace lo que promete aqui?)
  testeado   - | si | no        (¿hay evidencia de prueba real? Principio de Verdad)

Uso:
  py -m nucleo.catalogo lista            # todas, resumen
  py -m nucleo.catalogo pendientes       # las que faltan por auditar a fondo, en orden
  py -m nucleo.catalogo siguiente        # la proxima a auditar
  py -m nucleo.catalogo ver H012
  py -m nucleo.catalogo poner H012 auditado=completo veredicto=REFERENCIA "observaciones=texto"
  py -m nucleo.catalogo anadir "nombre" categoria=memoria "para_que_sirve=..."
  py -m nucleo.catalogo render
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from nucleo.candado import bloqueo
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico

ALMACEN = RAIZ / "memoria" / "catalogo.json"
CANDADO = RAIZ / "memoria" / ".candado_catalogo.lock"
VISTA = RAIZ.parent / "contexto" / "proyectos" / "nexo" / "catalogo-herramientas.md"

VALORES = {
    "auditado": ("no", "primera_pasada", "completo"),
    "veredicto": ("PENDIENTE", "ADOPTAR", "ADOPTAR_SELECTIVO", "REFERENCIA", "APARCADO", "NO_USAR"),
    "instalado": ("no", "en_curso", "parcial", "si"),
    "funcional": ("-", "si", "no"),
    "testeado": ("-", "si", "no"),
}

CAMPOS_TEXTO = (
    "nombre", "identidad", "tipo", "categoria", "para_que_sirve", "aplica_a", "licencia_coste",
    "riesgo", "solapa_con", "confianza", "primera_impresion", "observaciones", "tarea", "origen",
    "informe", "fecha_auditoria",
)


def _plantilla(nombre: str) -> dict:
    d = {c: "" for c in CAMPOS_TEXTO}
    d.update(nombre=nombre, auditado="no", veredicto="PENDIENTE", instalado="no", funcional="-", testeado="-")
    return d


def cargar() -> dict:
    """Si el archivo existe pero esta roto, revienta a proposito (nunca inventa uno vacio).

    Los items pueden venir de antes de que el esquema tuviera un campo (o de una edicion a
    mano incompleta): se completan los que falten con su valor por defecto en vez de dejar que
    render_md reviente con KeyError (turno del 28/09, memoria/catalogo.json H078 sin 'aplica_a').
    """
    if not ALMACEN.is_file():
        return {"version": 1, "actualizado": "", "items": []}
    datos = json.loads(ALMACEN.read_text(encoding="utf-8"))
    for it in datos.get("items", []):
        for c in CAMPOS_TEXTO:
            it.setdefault(c, "")
        it.setdefault("auditado", "no")
        it.setdefault("veredicto", "PENDIENTE")
        it.setdefault("instalado", "no")
        it.setdefault("funcional", "-")
        it.setdefault("testeado", "-")
    return datos


def guardar(datos: dict) -> None:
    datos["actualizado"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    escribir_atomico(ALMACEN, json.dumps(datos, ensure_ascii=False, indent=1) + "\n")
    if VISTA.parent.is_dir():
        # 23/09: con la nota abierta en Obsidian, Windows puede negar el reemplazo (WinError 5).
        # La vista es comodidad: se reintenta y, si no, se deja para el siguiente guardado.
        import time as _t
        for _ in range(4):
            try:
                escribir_atomico(VISTA, render_md(datos))
                break
            except PermissionError:
                _t.sleep(0.7)


def _validar(campo: str, valor: str) -> None:
    if campo in VALORES and valor not in VALORES[campo]:
        raise ValueError(f"{campo}={valor!r} no valido; permitidos: {', '.join(VALORES[campo])}")
    if campo not in VALORES and campo not in CAMPOS_TEXTO:
        raise ValueError(f"campo desconocido: {campo!r}")


def buscar(datos: dict, id_o_nombre: str) -> dict | None:
    aguja = id_o_nombre.strip().lower()
    for it in datos["items"]:
        if it["id"].lower() == aguja:
            return it
    for it in datos["items"]:
        if aguja in it["nombre"].lower():
            return it
    return None


def poner(id_o_nombre: str, **campos) -> dict:
    for c, v in campos.items():
        _validar(c, v)
    with bloqueo(CANDADO):
        datos = cargar()
        it = buscar(datos, id_o_nombre)
        if it is None:
            raise KeyError(f"no existe {id_o_nombre!r} en el catalogo")
        it.update(campos)
        if campos.get("auditado") == "completo" and not campos.get("fecha_auditoria"):
            it["fecha_auditoria"] = datetime.now().strftime("%Y-%m-%d")
        guardar(datos)
    return it


def anadir(nombre: str, **campos) -> dict:
    for c, v in campos.items():
        _validar(c, v)
    with bloqueo(CANDADO):
        datos = cargar()
        if buscar(datos, nombre) and buscar(datos, nombre)["nombre"].lower() == nombre.lower():
            raise ValueError(f"ya existe: {nombre!r}")
        it = _plantilla(nombre)
        it.update(campos)
        n = max((int(x["id"][1:]) for x in datos["items"]), default=0) + 1
        it["id"] = f"H{n:03d}"
        it["orden_auditoria"] = max((x.get("orden_auditoria", 0) for x in datos["items"]), default=0) + 1
        datos["items"].append(it)
        guardar(datos)
    return it


def pendientes(datos: dict | None = None) -> list[dict]:
    datos = datos or cargar()
    return sorted(
        (x for x in datos["items"] if x["auditado"] != "completo" and x["veredicto"] not in ("NO_USAR",)),
        key=lambda x: x.get("orden_auditoria", 9999),
    )


def siguiente() -> dict | None:
    p = pendientes()
    return p[0] if p else None


# ------------------------------------------------------------------ vista

def _celda(t: str, n: int = 160) -> str:
    t = " ".join((t or "").split()).replace("|", "/")
    return t if len(t) <= n else t[: n - 1] + "…"


def render_md(datos: dict | None = None) -> str:
    datos = datos or cargar()
    items = sorted(datos["items"], key=lambda x: x.get("orden_auditoria", 9999))
    total = len(items)
    completos = sum(x["auditado"] == "completo" for x in items)
    pasada = sum(x["auditado"] == "primera_pasada" for x in items)
    instalados = sum(x["instalado"] in ("si", "parcial") for x in items)

    out = [
        "# Catálogo de herramientas a auditar",
        "",
        f"_Generado el {datos.get('actualizado', '')} desde `agente/memoria/catalogo.json`. **No editar a mano**: "
        "usar `py -m nucleo.catalogo` (ver final)._",
        "",
        f"**{total}** herramientas · **{completos}** auditadas a fondo · **{pasada}** con primera pasada "
        f"(identificadas y resumidas) · **{instalados}** instaladas total o parcialmente.",
        "",
        "Leyenda: **Auditado** `no` / `1ª pasada` (identificada, riesgo a ojo) / `completo` (contenido real "
        "leído, con informe). **Veredicto** PENDIENTE · ADOPTAR · ADOPTAR_SELECTIVO · REFERENCIA (conocerla, no "
        "instalar) · APARCADO · NO_USAR. **Funcional / Testeado**: `-` = aún no aplica.",
        "",
        "| ID | Nombre | Categoría | Para qué sirve | Aplica a | Auditado | Veredicto | Instalado | Funcional | Testeado | Tarea |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for x in items:
        aud = {"primera_pasada": "1ª pasada"}.get(x["auditado"], x["auditado"])
        out.append(
            f"| {x['id']} | {_celda(x['nombre'], 40)} | {x['categoria']} | {_celda(x['para_que_sirve'])} | "
            f"{_celda(x['aplica_a'], 40)} | {aud} | {x['veredicto']} | {x['instalado']} | {x['funcional']} | "
            f"{x['testeado']} | {x['tarea']} |"
        )
    out += ["", "## Fichas", ""]
    for x in items:
        out.append(f"### {x['id']} · {x['nombre']}")
        for etiqueta, clave in (
            ("Identidad", "identidad"), ("Tipo", "tipo"), ("Licencia / coste", "licencia_coste"),
            ("Riesgo", "riesgo"), ("Solapa con", "solapa_con"), ("Primera impresión", "primera_impresion"),
            ("Observaciones", "observaciones"), ("Confianza en la identificación", "confianza"),
            ("Origen", "origen"), ("Informe", "informe"), ("Fecha de auditoría", "fecha_auditoria"),
        ):
            if x.get(clave):
                out.append(f"- **{etiqueta}:** {' '.join(str(x[clave]).split())}")
        out.append("")
    out += [
        "---",
        "",
        "## Cómo se usa",
        "",
        "```",
        "py -m nucleo.catalogo siguiente            # la próxima a auditar",
        "py -m nucleo.catalogo ver H012",
        'py -m nucleo.catalogo poner H012 auditado=completo veredicto=REFERENCIA "observaciones=..."',
        'py -m nucleo.catalogo anadir "nombre" categoria=memoria "para_que_sirve=..."',
        "```",
        "",
        "Al auditar a fondo una herramienta: leer su contenido real (no solo el README), dejar el informe en "
        "`contexto/proyectos/nexo/auditorias/<nombre>.md`, apuntarlo en `informe` y actualizar veredicto. "
        "Si se decide ADOPTAR, crear su tarea en `tareas.json` y apuntarla en `tarea`. Instalado/funcional/"
        "testeado solo cambian con evidencia (Principio de Verdad).",
    ]
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------- cli

def _pares(args: list[str]) -> dict:
    campos = {}
    for a in args:
        if "=" not in a:
            raise ValueError(f"se esperaba campo=valor, no {a!r}")
        k, v = a.split("=", 1)
        campos[k.strip()] = v
    return campos


def _cli(argv: list[str]) -> int:
    accion = (argv or ["lista"])[0].lower()
    resto = argv[1:]
    if accion == "lista":
        for x in sorted(cargar()["items"], key=lambda x: x.get("orden_auditoria", 9999)):
            print(f"{x['id']}  {x['auditado']:14s} {x['veredicto']:17s} {x['instalado']:8s} {x['nombre']}")
    elif accion == "pendientes":
        for x in pendientes():
            print(f"{x['id']}  {x['auditado']:14s} {x['nombre']}  [{x['categoria']}]")
    elif accion == "siguiente":
        x = siguiente()
        print(f"{x['id']}  {x['nombre']} -- {x['para_que_sirve']}" if x else "(nada pendiente)")
    elif accion == "ver":
        x = buscar(cargar(), resto[0])
        print(json.dumps(x, ensure_ascii=False, indent=1) if x else "no encontrado")
    elif accion == "poner":
        x = poner(resto[0], **_pares(resto[1:]))
        print(f"{x['id']} actualizado")
    elif accion == "anadir":
        x = anadir(resto[0], **_pares(resto[1:]))
        print(f"anadido {x['id']}  {x['nombre']}")
    elif accion == "render":
        guardar(cargar())
        print(f"regenerado {VISTA}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    from nucleo import consola
    consola.preparar()   # consola cp1252 de Windows: '?' en lo que no cabe, tildes intactas
    raise SystemExit(_cli(sys.argv[1:]))
