# -*- coding: utf-8 -*-
"""T145 pieza A: politica de permisos POR CANAL (una orden de la web o de Telegram no puede lo que Claude en sesion).

Tests dados (los escribe Claude; el implementador SOLO crea nucleo/permisos_canal.py). NO toca nucleo/permisos.py
(blindado): esta pieza es solo la tabla y la consulta; engancharla a permisos.py lo hace Claude con el diff a Damian.

Contrato:
- `CAPACIDADES` (tupla, en este orden): "leer_estado", "crear_tarea", "accion_directa", "borrador_ia_externa",
  "escribir_codigo", "ejecutar_comando", "enviar_privado_fuera".
- `POLITICA`: dict canal -> frozenset de capacidades permitidas. Canales y permisos EXACTOS:
    "claude_sesion": todas MENOS "enviar_privado_fuera"
    "web":           leer_estado, crear_tarea, accion_directa, borrador_ia_externa
    "telegram":      leer_estado, crear_tarea            (Damian 27/09: nada nuevo en Telegram)
    "turno":         leer_estado, crear_tarea, borrador_ia_externa
    "implementador": leer_estado, escribir_codigo        (solo en su worktree: lo vigila la puerta, no esta tabla)
  "enviar_privado_fuera" (memoria/, vault, secretos hacia un proveedor externo) no lo tiene NINGUN canal.
- `permitido(canal: str, capacidad: str) -> tuple[bool, str]`. Fallo CERRADO; precedencia de comprobaciones:
    1. capacidad desconocida -> (False, motivo con "capacidad desconocida");
    2. canal desconocido, vacio o None -> (False, motivo con "canal desconocido");
    3. capacidad no permitida al canal -> (False, motivo con el canal y la capacidad);
    4. si no -> (True, "").
  canal y capacidad se comparan tras strip() y en minusculas ("Web " == "web"); nada mas se normaliza.
- `capacidades(canal) -> list[str]`: las permitidas, en el orden de CAPACIDADES; [] si el canal no existe.
"""
from __future__ import annotations

import pytest

from nucleo import permisos_canal as PC

TODAS = ("leer_estado", "crear_tarea", "accion_directa", "borrador_ia_externa", "escribir_codigo",
         "ejecutar_comando", "enviar_privado_fuera")


def test_capacidades_en_orden():
    assert PC.CAPACIDADES == TODAS


@pytest.mark.parametrize("canal,esperado", [
    ("claude_sesion", list(TODAS[:-1])),
    ("web", ["leer_estado", "crear_tarea", "accion_directa", "borrador_ia_externa"]),
    ("telegram", ["leer_estado", "crear_tarea"]),
    ("turno", ["leer_estado", "crear_tarea", "borrador_ia_externa"]),
    ("implementador", ["leer_estado", "escribir_codigo"]),
    ("whatsapp", []),
])
def test_tabla(canal, esperado):
    assert PC.capacidades(canal) == esperado


def test_nadie_envia_lo_privado_fuera():
    for canal in PC.POLITICA:
        assert PC.permitido(canal, "enviar_privado_fuera")[0] is False


def test_permitido_y_normalizado():
    assert PC.permitido(" Web ", "Accion_Directa") == (True, "")


@pytest.mark.parametrize("canal,cap,trozo", [
    ("web", "borrar_todo", "capacidad desconocida"),
    ("whatsapp", "borrar_todo", "capacidad desconocida"),     # 1 gana a 2
    ("whatsapp", "leer_estado", "canal desconocido"),
    ("", "leer_estado", "canal desconocido"),
    (None, "leer_estado", "canal desconocido"),
])
def test_fallo_cerrado(canal, cap, trozo):
    ok, motivo = PC.permitido(canal, cap)
    assert ok is False and trozo in motivo


def test_no_permitida_nombra_canal_y_capacidad():
    ok, motivo = PC.permitido("telegram", "accion_directa")
    assert ok is False and "telegram" in motivo and "accion_directa" in motivo


def test_la_web_no_ejecuta_comandos_ni_escribe_codigo():
    assert not PC.permitido("web", "ejecutar_comando")[0]
    assert not PC.permitido("web", "escribir_codigo")[0]
