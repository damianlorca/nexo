# -*- coding: utf-8 -*-
"""Incremento 8: nada que parezca un secreto llega al navegador."""
from __future__ import annotations

import pytest

from interfaz import ocultar

O = ocultar.OCULTO
# Claves de pega con la forma de las reales (ninguna es valida).
FALSAS = [
    "sk-FALSOXXXXXXXXXXXXXXXXXXXX",
    "sk-FALSOXXXXXXXXXXXXXXXXXXXX",
    "AIzaSyA1b2C3d4E5f6G7h8I9j0KlMnOpQrStUv",
    "gsk_abcdefghijklmnopqrstuvwxyz123456",
    "ghp_abcdefghijklmnopqrstuvwxyz0123",
    "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abcdefghijklmnop",
    "Xy7kP2mQ9rT4vW8zA1bC3dE5fG6hJ0kL",
]


@pytest.mark.parametrize("secreto", FALSAS)
def test_patrones_conocidos_se_ocultan_dentro_de_un_texto(secreto):
    r = ocultar.texto(f"llamada con {secreto} y sigue")
    assert secreto not in r and O in r and r.startswith("llamada con ") and r.endswith(" y sigue")


@pytest.mark.parametrize("entrada", [
    "api_key=abc123secreto", "API-KEY: abc123secreto", '"token": "abc123secreto"', "password=hunter22",
    "set GEMINI_API_KEY=abc123secreto", "clave: abc123secreto", "Authorization: Bearer abc.def.ghi123",
    "http://127.0.0.1:8765/entrar?t=AbCdEfGhIjKlMnOpQr_st",
])
def test_nombre_igual_valor_conserva_el_nombre(entrada):
    r = ocultar.texto(entrada)
    assert "abc123secreto" not in r and "hunter22" not in r and "abc.def.ghi123" not in r
    assert "AbCdEfGhIjKlMnOpQr_st" not in r and O in r


def test_texto_normal_no_se_toca():
    for s in ("git commit -m 'arreglo'", "Get-Content registros\trazas.jsonl -Tail 3",
              "f482c7f4a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6", "duracion 0.76 s", "codigo=0",
              "interfaz_8766_inc4_20260924_224457.log",
              "NEXO_HANDOFF_2026-09-24_t12_nombre_de_fichero", "2026-09-24T10_11_12_345Z-debug-0"):
        assert ocultar.texto(s) == s


def test_valor_oculta_claves_sensibles_de_texto_y_respeta_numeros():
    linea = {"proveedor": "groq", "api_key": "loquesea", "tokens": 1234, "Authorization": "x y",
             "anidado": {"session_id": "abc", "lista": ["sk-FALSOXXXXXXXXXXXXXXXXXXXX", "ok"]}, "vacio": None}
    r = ocultar.valor(linea)
    assert r == {"proveedor": "groq", "api_key": O, "tokens": 1234, "Authorization": O,
                 "anidado": {"session_id": O, "lista": [O, "ok"]}, "vacio": None}
    assert linea["api_key"] == "loquesea"  # no muta el original


# ------------------------------------------------------------------ code-review bloque 7-9
@pytest.mark.parametrize("entrada, secreto", [
    ("SECRET_KEY=abc123xyz", "abc123xyz"),
    ("set AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "bPxRfiCYEXAMPLEKEY"),
    ("X-API-KEY: abcd1234", "abcd1234"),
    ('password="mi clave con espacios"', "con espacios"),
    ("token: 'abc'", "abc'"),
    ("clave suelta wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY en base64", "K7MDENG"),
])
def test_nombres_compuestos_comillas_y_base64(entrada, secreto):
    r = ocultar.texto(entrada)
    assert secreto not in r and O in r


@pytest.mark.parametrize("s", ["sort(key=lambda t: t['id'])", "monkey=banana", "keyboard=es",
                               "documentacion/T049_RUNTIME_LOCAL", "memoria/borradores/T153_20260924_0017.md"])
def test_codigo_y_rutas_no_se_ocultan(s):
    assert ocultar.texto(s) == s
