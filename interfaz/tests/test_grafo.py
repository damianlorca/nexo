# -*- coding: utf-8 -*-
"""T251: grafo de NEXO (node-link) y pestaña Grafo. Solo relaciones que ya estan guardadas."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

from interfaz import grafo
from interfaz.seguridad import CSP
from nucleo import registro, trabajo
from nucleo import tareas as T

VENDOR = Path(__file__).resolve().parents[1] / "estatico" / "vendor"


# ------------------------------------------------------------------ utilidades (tambien para recalcular hashes)
def _cadena_js(s: str, i: int) -> tuple[str, int]:
    """Lee el literal de cadena JS que empieza en s[i] (comilla simple o doble). Devuelve (texto, fin)."""
    comilla, i, salida = s[i], i + 1, []
    escapes = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}
    while s[i] != comilla:
        c = s[i]
        if c == "\\":
            n = s[i + 1]
            if n == "u":
                salida.append(chr(int(s[i + 2:i + 6], 16)))
                i += 6
                continue
            if n == "x":
                salida.append(chr(int(s[i + 2:i + 4], 16)))
                i += 4
                continue
            salida.append(escapes.get(n, n))
            i += 2
            continue
        salida.append(c)
        i += 1
    return "".join(salida), i + 1


def estilos_vis_network() -> list[str]:
    """El CSS que el build standalone de vis-network mete en <style> (llamadas qA("...") del .min.js)."""
    s = (VENDOR / "vis-network.min.js").read_text(encoding="utf-8")
    textos = []
    for m in re.finditer(r"qA\((?=[\"'])", s):
        texto, _ = _cadena_js(s, m.end())
        textos.append(texto)
    return textos


def hash_csp(texto: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(texto.encode("utf-8")).digest()).decode() + "'"


def _borrador(nombre: str, cabecera: str) -> None:
    (trabajo.BORRADORES / nombre).write_text(cabecera + "\n# Borrador\ntexto\n", encoding="utf-8")


def _nodos(g):
    return {n["id"]: n for n in g["nodes"]}


def _aristas(g):
    return {(l["source"], l["target"], l["tipo"]) for l in g["links"]}


# ------------------------------------------------------------------ construir
def test_nodos_con_titulo_en_palabras_y_estado(entorno):
    a = T.anadir("Investigar Graphify y ver si sirve para la interfaz de NEXO", etiquetas=["tema:interfaz_app_voz"])
    g = grafo.construir()
    n = _nodos(g)[a["id"]]
    assert n["titulo"] == f"{a['id']} · Investigar Graphify y ver si sirve para la interfaz de NEXO"
    assert n["etiqueta"].startswith(f"{a['id']} · Investigar") and n["etiqueta"].endswith("…")
    assert (n["tipo"], n["estado"], n["clase"], n["grupo"]) == ("tarea", "Por hacer", "por-hacer", "por_hacer")
    assert n["tema"] == "Web, app y voz" and n["url"] == f"/tareas/{a['id']}"
    assert g["directed"] is True and g["multigraph"] is False and "relaciones" in g["graph"]


def test_aristas_solo_de_relaciones_guardadas(entorno):
    origen = T.anadir("Origen", depende="damian", etiquetas=["suyo:gustos"])   # guardia de responsables
    otra = T.anadir("Otra")
    rev = T.anadir("Revisar borrador", etiquetas=["cat:revision", "revision:borrador", f"tarea_origen:{origen['id']}",
                                                   f"de_borrador:{origen['id']}_20260928_0001.md"])
    prop = T.anadir("[Propuesta] algo", estado="propuesta", bloqueada_por=rev["id"],
                    etiquetas=["cat:propuesta", f"tarea_origen:{origen['id']}", f"de_borrador:{origen['id']}_20260928_0001.md"])
    junto = T.anadir("Junto", etiquetas=[f"junto_a:{otra['id']}"])
    libre = T.anadir("Texto libre", bloqueada_por="Falta que Damian decida")      # no es un id: sin arista
    fantasma = T.anadir("Apunta a nada", bloqueada_por="T999", etiquetas=["tarea_origen:T998"])
    _borrador(f"{origen['id']}_20260928_0001.md",
              "<!-- ESCALAR | auditoria BLOQUEADA | autor chatgpt | revisores gemini (Pro), gemini_api | mejoras 1/3 -->")
    g = grafo.construir()
    b = f"borrador:{origen['id']}_20260928_0001.md"
    assert _aristas(g) == {
        (origen["id"], rev["id"], "origen"), (origen["id"], prop["id"], "origen"),
        (rev["id"], b, "revisa"), (b, prop["id"], "propone"), (prop["id"], rev["id"], "espera"),
        (origen["id"], b, "borrador"), (b, "ia:chatgpt", "escrito"), (b, "ia:gemini", "revisado"),
        (b, "ia:gemini_api", "revisado"), (junto["id"], otra["id"], "junto"), (origen["id"], "ia:damian", "damian")}
    n = _nodos(g)
    assert (n[rev["id"]]["tipo"], n[prop["id"]]["tipo"], n[b]["tipo"]) == ("revision", "propuesta", "borrador")
    assert n[b]["estado"] == "Esperando a Claude" and n[b]["ias"] == ["chatgpt", "gemini", "gemini_api"]
    assert n[b]["url"] == f"/borrador?f={origen['id']}_20260928_0001.md"
    assert not any(libre["id"] in (s, d) or fantasma["id"] in (s, d) for s, d, _ in _aristas(g))
    assert "T999" not in n and "T998" not in n


def test_veredicto_de_claude_colorea_el_borrador(entorno):
    o = T.anadir("Origen")
    nombre = f"{o['id']}_20260927_1200.md"
    rev = T.anadir("Revisar", etiquetas=["revision:borrador", f"de_borrador:{nombre}"])
    T.anotar(rev["id"], f"Revision de Claude del borrador {nombre}: APROBADO. Todo bien comprobado.")
    T.completar(rev["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    otro = f"{o['id']}_20260926_1200.md"                               # sin revision: de antes de T192
    _borrador(nombre, "<!-- BORRADOR de chatgpt | revisor gemini | VEREDICTO OK -->")
    _borrador(otro, "<!-- BORRADOR de groq | revisor ninguno -->")
    n = _nodos(grafo.construir())
    assert (n[f"borrador:{nombre}"]["estado"], n[f"borrador:{nombre}"]["clase"]) == ("Aprobado por Claude", "comprobada")
    assert n[f"borrador:{otro}"]["estado"] == "Sin revisión de Claude" and n[f"borrador:{otro}"]["ias"] == ["groq"]
    assert n[f"borrador:{nombre}"]["fecha"] == "2026-09-27"


def test_delegaciones_y_turnos(entorno):
    t = T.anadir("Delegada")
    datos = T.cargar()
    datos["tareas"][0]["conversaciones"] = {"chatgpt:autor": {"usos": 1}, "gemini:revisor": {"usos": 1}}
    T.guardar(datos)
    (registro.CARPETA / "turno_nexo_20260928_184703.json").write_text(json.dumps({
        "inicio": "2026-09-28T18:47:03", "nombre_turno": "Revisión de código",
        "pasos": {"trabajo": {"filas": [{"tarea": t["id"], "autor": "groq", "revisor": "gemini (Pro)"},
                                        {"tarea": "T404", "autor": "chatgpt"}]}}}), encoding="utf-8")
    (registro.CARPETA / "turno_nexo_20260928_000000.json").write_text("{roto", encoding="utf-8")
    g = grafo.construir()
    turno = "turno:turno_nexo_20260928_184703"
    assert {(t["id"], "ia:chatgpt", "delegada"), (t["id"], "ia:gemini", "delegada"), (turno, t["id"], "turno")} <= _aristas(g)
    n = _nodos(g)[turno]
    assert n["etiqueta"] == "Turno 28/09 18:47 · Revisión de código" and n["ias"] == ["groq", "gemini", "chatgpt"]
    assert "2 tarea(s)" in n["frase"]


def test_escala_de_mas_de_300_nodos(entorno):
    # Bloque 21: un solo guardado (con T.anadir eran 320 reescrituras del almacen entero: 13-16 s solo en preparar)
    datos = T.cargar()
    for i in range(320):
        t = T.plantilla(f"Tarea {i}", etiquetas=[f"tarea_origen:T{(i // 2) + 1:03d}"] if i else [])
        t["id"] = "T{:03d}".format(datos["siguiente_id"])
        datos["siguiente_id"] += 1
        datos["tareas"].append(t)
    T.guardar(datos)
    g = grafo.construir()
    assert len(g["nodes"]) == 320 and len(g["links"]) == 319


# ------------------------------------------------------------------ web
def test_pestana_y_pagina(cliente, csrf):
    r = cliente.get("/grafo")
    assert r.status_code == 200
    assert 'href="/grafo" aria-current="page"' in r.text
    assert '<script src="/estatico/vendor/vis-network.min.js" defer></script>' in r.text
    assert '<script src="/estatico/grafo.js" defer></script>' in r.text
    assert "<script>" not in r.text                      # nada en linea (CSP)
    for campo in ('name="q"', 'name="estado"', 'name="tema"', 'name="ia"', 'name="desde"', 'name="hasta"',
                  'name="tipo" value="borrador"', 'data-zoom="encajar"', 'id="grafo-ficha"'):
        assert campo in r.text


def test_datos_node_link(cliente, csrf):
    a = T.anadir("Uno")
    T.anadir("Dos", bloqueada_por=a["id"])
    r = cliente.get("/grafo/datos")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    assert "no-store" in r.headers["cache-control"]
    g = r.json()
    assert {"directed", "multigraph", "graph", "nodes", "links"} <= set(g) and len(g["links"]) == 1


def test_datos_con_tareas_json_roto(cliente, csrf):
    T.ALMACEN.write_text("{roto", encoding="utf-8")
    r = cliente.get("/grafo/datos")
    assert r.status_code == 503 and "error" in r.json()


def test_sin_sesion_no_hay_datos(cliente):
    r = cliente.get("/grafo/datos", follow_redirects=False)
    assert r.status_code in (302, 303, 401, 403) and "nodes" not in r.text


# ------------------------------------------------------------------ vendor y CSP
def test_vis_network_vendorizado_con_su_sha256():
    datos = (VENDOR / "vis-network.min.js").read_bytes()
    sha = base64.b64encode(hashlib.sha256(datos).digest()).decode()
    versiones = (VENDOR / "VERSIONES.txt").read_text(encoding="utf-8")
    assert f"vis-network@9.1.6/standalone/umd/vis-network.min.js  {len(datos)}  {sha}" in versiones


def test_csp_deja_solo_el_css_de_vis_network_por_hash():
    estilos = estilos_vis_network()
    assert len(estilos) == 7
    for texto in estilos + [""]:          # "": vis inserta el <style> vacio antes de ponerle el texto
        assert hash_csp(texto) in CSP
    assert "unsafe-inline" not in CSP
