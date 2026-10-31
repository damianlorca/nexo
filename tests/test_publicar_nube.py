# -*- coding: utf-8 -*-
"""El espejo publico no lleva el chat_id real de Telegram (decidido por Damian el
27/09): config.toml va al espejo (decision 7) pero con [canal] chat_id = 0.
Solo se prueba la funcion de redaccion: sin git, sin red."""
from __future__ import annotations

import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("publicar_nube", RAIZ / "herramientas_nube" / "publicar_nube.py")
pn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pn)

CONFIG = (
    b"[qwen]\r\nmodelo_obrero = \"qwen2.5:7b\"\r\n\r\n"
    b"[canal]\r\n# comentario\r\nchat_id = 987654321\r\n\r\n"
    b"[otra]\r\nchat_id_de_otra_cosa = 5\r\n"
)


def test_chat_id_de_config_toml_sale_a_cero():
    nuevo, n = pn.redactar("config.toml", CONFIG)
    assert b"987654321" not in nuevo
    assert b"chat_id = 0\r\n" in nuevo
    assert n == 1


def test_el_resto_de_config_toml_no_cambia():
    nuevo, _ = pn.redactar("config.toml", CONFIG)
    assert nuevo.replace(b"chat_id = 0\r\n", b"chat_id = 987654321\r\n") == CONFIG


def test_chat_id_a_cero_no_cuenta_como_sustitucion():
    nuevo, n = pn.redactar("config.toml", b"[canal]\nchat_id = 0\n")
    assert n == 0 and nuevo == b"[canal]\nchat_id = 0\n"


def test_otros_archivos_no_se_tocan_por_el_chat_id():
    datos = b"chat_id = 987654321\n"
    assert pn.redactar("tests/algo.py", datos) == (datos, 0)


def test_los_tokens_se_siguen_redactando():
    token = b"123456789:" + b"B" * 35
    nuevo, n = pn.redactar("cualquiera.py", b"t = '" + token + b"'")
    assert token not in nuevo and n == 1
