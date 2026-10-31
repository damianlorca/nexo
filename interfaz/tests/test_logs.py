# -*- coding: utf-8 -*-
"""Incremento 8: Logs (lista filtrable con limite, sin secretos, aviso de logs_perdidos, borradores)."""
from __future__ import annotations

import json

from interfaz import lecturas, ocultar
from interfaz.vigilancia import Vigilante
from nucleo import registro, trabajo

SECRETO = "sk-FALSOXXXXXXXXXXXXXXXXXXXX"


def _escribir(fuente, *lineas):
    ruta = registro.CARPETA / f"{fuente}.jsonl"
    with ruta.open("a", encoding="utf-8") as f:
        for x in lineas:
            f.write((x if isinstance(x, str) else json.dumps(x)) + "\n")


def _base():
    _escribir("trazas", {"t": "2026-09-25 10:00:01", "evento": "comando", "comando": "git status", "codigo": 0},
              {"t": "2026-09-25 10:00:05", "evento": "comando", "comando": f"curl -H 'Authorization: Bearer {SECRETO}'"})
    _escribir("evidencia", {"t": "2026-09-25 10:00:03", "fase": "tool", "estado": "OK", "api_key": "loquesea"})
    _escribir("uso_proveedores",
              {"cuando": "2026-09-25T10:00:02", "proveedor": "groq", "estado": "OK", "entrada": 1, "salida": 2, "segundos": 1.0},
              {"cuando": "2026-09-25T10:00:04", "proveedor": "gemini_api", "estado": "ERROR", "entrada": 1, "salida": 0, "segundos": 9.0},
              "{linea rota")


# ------------------------------------------------------------------ pagina
def test_pagina_filtros_limite_y_disparadores(cliente, csrf):
    r = cliente.get("/logs")
    assert r.status_code == 200
    for trozo in ('name="fuente"', 'name="proveedor"', 'name="estado"', 'name="limite"',
                  'hx-include="#filtros-logs"', "nexo:log from:body throttle:2s",
                  'hx-get="/logs/perdidos" hx-trigger="nexo:logs_perdidos from:body"',
                  "nexo:logs_perdidos from:body, nexo:reconciliar", 'hx-get="/logs/borradores"'):
        assert trozo in r.text
    assert '<option value="100" selected>' in r.text  # limite por defecto


def test_requieren_sesion(cliente):
    for url in ("/logs/lista", "/logs/borradores", "/logs/perdidos"):
        assert cliente.get(url).status_code == 401


# ------------------------------------------------------------------ lista
def test_lista_vacia(cliente, csrf):
    assert "Los registros están vacíos." in cliente.get("/logs/lista").text
    assert "Ninguna línea con estos filtros." in cliente.get("/logs/lista", params={"estado": "x"}).text


def test_lista_mezcla_ficheros_por_hora_y_oculta_secretos(cliente, csrf):
    _base()
    r = cliente.get("/logs/lista").text
    assert SECRETO not in r and "loquesea" not in r and ocultar.OCULTO in r
    horas = [h for h in ("10:00:05", "10:00:04", "10:00:03", "10:00:02", "10:00:01") if h in r]
    assert horas == sorted(horas, reverse=True) and len(horas) == 5
    assert [r.index(h) for h in horas] == sorted(r.index(h) for h in horas)  # la mas reciente arriba
    assert "5 líneas" in r


def test_filtros_por_fichero_proveedor_y_estado(cliente, csrf):
    _base()
    r = cliente.get("/logs/lista", params={"fuente": "uso_proveedores"}).text
    assert "groq" in r and "gemini_api" in r and "git status" not in r
    r = cliente.get("/logs/lista", params={"proveedor": "groq"}).text
    assert "groq" in r and "gemini_api" not in r and "1 línea" in r
    r = cliente.get("/logs/lista", params={"estado": "error"}).text
    assert "gemini_api" in r and "groq" not in r
    r = cliente.get("/logs/lista", params={"fuente": "../secretos", "limite": 7}).text  # valores raros -> por defecto
    assert "5 líneas" in r


def test_limite_recorta_y_lo_dice(cliente, csrf):
    _escribir("trazas", *[{"t": f"2026-09-25 10:{i // 60:02d}:{i % 60:02d}", "evento": f"ev{i}"} for i in range(120)])
    r = cliente.get("/logs/lista", params={"limite": 50}).text
    assert "50 líneas de 120 (límite 50)" in r and "ev119" in r and "ev69" not in r


def test_error_de_lectura_da_panel_de_error(cliente, csrf, monkeypatch):
    def rompe(**_):
        raise OSError("disco")
    monkeypatch.setattr(lecturas, "lineas_log", rompe)
    r = cliente.get("/logs/lista")
    assert r.status_code == 200 and 'role="alert"' in r.text and 'hx-get="/logs/lista"' in r.text


# ------------------------------------------------------------------ logs_perdidos
def test_aviso_de_lineas_saltadas(cliente, csrf):
    r = cliente.get("/logs/perdidos").text
    assert 'role="status"' in r and "Se saltaron líneas en tiempo real" in r


# ------------------------------------------------------------------ secretos fuera del SSE y del Centro
def test_vigilancia_oculta_secretos_antes_de_publicar(ajustes):
    from interfaz.eventos import Bus
    v = Vigilante(Bus())
    _escribir("trazas", {"t": "x", "evento": "inicio"})
    v.revisar()  # foto inicial
    _escribir("trazas", {"t": "y", "evento": "comando", "comando": f"set OPENAI_API_KEY={SECRETO}", "token": "abc"})
    [(tipo, datos)] = v.revisar()
    assert tipo == "log" and SECRETO not in json.dumps(datos) and datos["linea"]["token"] == ocultar.OCULTO


def test_trazas_del_centro_sin_secretos(cliente, csrf):
    _base()
    r = cliente.get("/centro/acciones/trazas").text
    assert SECRETO not in r and "git status" in r


# ------------------------------------------------------------------ borradores
def test_borradores_recientes(cliente, csrf):
    assert "Todavía no hay borradores." in cliente.get("/logs/borradores").text
    (trabajo.BORRADORES / "T001_20260925_1000.md").write_text("hola", encoding="utf-8")
    r = cliente.get("/logs/borradores").text
    assert 'href="/borrador?f=T001_20260925_1000.md"' in r


# ------------------------------------------------------------------ code-review bloque 7-9
def test_trazas_del_centro_ocultan_antes_de_recortar():
    # La clave empieza en la posicion 148: recortando antes (a 160) quedaban 12 caracteres sueltos.
    _escribir("trazas", {"t": "z", "evento": "comando", "comando": "x" * 148 + SECRETO})
    [traza] = lecturas.ultimas_trazas(1)
    assert SECRETO[:8] not in traza["detalle"] and len(traza["detalle"]) <= 160


def test_vigilancia_oculta_antes_de_recortar_una_linea_gigante():
    from interfaz import vigilancia
    bruta = ("y" * (vigilancia.MAX_CARACTERES_LINEA - 10) + SECRETO).encode()
    linea = vigilancia._linea(bruta)
    assert linea["recortada"] and SECRETO[:8] not in linea["texto"]
