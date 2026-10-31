# -*- coding: utf-8 -*-
"""T559: separar los estados de cada modelo del banco T320: catalogado / endpoint / descargable / probado.

Tests dados (los escribe Claude; el implementador SOLO cambia nucleo/banco_modelos.py). Contrato de la funcion nueva
`estados_modelos(inv: dict, filas: list[dict]) -> dict[str, dict]` (pura: no lee ni escribe archivos):
- `inv` tiene la forma de memoria/modelos/inventario.json: {"proveedores": {prov: [{"id", "nota"}...]}, ...}.
- `filas` son filas de banco.jsonl: {"proveedor", "modelo", "codigo", "error", ...}.
- Clave: "proveedor:modelo". Valor: {"catalogado", "endpoint", "descargable", "probado", "estado"}:
  - catalogado: el modelo esta en `inv`.
  - endpoint: catalogado y su proveedor NO es "ollama" (se usa por API).
  - descargable: catalogado y su proveedor es "ollama" (corre en el PC).
  - probado: hay al menos una fila suya con codigo 200 y error vacio ("" o ausente).
  - estado, por este ORDEN de precedencia (gana la primera que se cumpla):
      1. "retirado"    si NO esta catalogado (solo aparece en `filas`: ya no esta en el inventario), aunque se probara;
      2. "probado"     si probado;
      3. "endpoint" o "descargable" segun su proveedor.
- Un modelo con filas solo de error (codigo != 200 o error no vacio) NO esta probado.
"""
from __future__ import annotations

from nucleo import banco_modelos as B

INV = {"cuando": "2026-10-11 10:00:00", "errores": {},
       "proveedores": {"groq": [{"id": "openai/gpt-oss-20b", "nota": "ctx 131072"},
                                {"id": "qwen/qwen3.8-27b", "nota": "ctx 131072"}],
                       "ollama": [{"id": "qwen2.5:7b", "nota": "7B local"}]}}

FILAS = [{"proveedor": "groq", "modelo": "openai/gpt-oss-20b", "codigo": 200, "error": ""},
         {"proveedor": "groq", "modelo": "qwen/qwen3.8-27b", "codigo": 429, "error": "cuota"},
         {"proveedor": "groq", "modelo": "qwen/qwen3.8-27b", "codigo": 200, "error": "timeout"},
         {"proveedor": "nvidia", "modelo": "viejo/modelo-1", "codigo": 200}]


def test_estados_de_cada_modelo():
    e = B.estados_modelos(INV, FILAS)
    assert e["groq:openai/gpt-oss-20b"] == {"catalogado": True, "endpoint": True, "descargable": False,
                                            "probado": True, "estado": "probado"}
    assert e["groq:qwen/qwen3.8-27b"]["probado"] is False
    assert e["groq:qwen/qwen3.8-27b"]["estado"] == "endpoint"
    assert e["ollama:qwen2.5:7b"] == {"catalogado": True, "endpoint": False, "descargable": True,
                                      "probado": False, "estado": "descargable"}


def test_modelo_que_ya_no_esta_en_el_inventario_sale_como_retirado():
    e = B.estados_modelos(INV, FILAS)
    assert e["nvidia:viejo/modelo-1"]["catalogado"] is False
    assert e["nvidia:viejo/modelo-1"]["probado"] is True
    assert e["nvidia:viejo/modelo-1"]["estado"] == "retirado"


def test_sin_datos_devuelve_vacio():
    assert B.estados_modelos({"proveedores": {}}, []) == {}


def test_no_lee_archivos(monkeypatch, tmp_path):
    monkeypatch.setattr(B, "INVENTARIO", tmp_path / "no_existe.json")
    monkeypatch.setattr(B, "RESULTADOS", tmp_path / "no_existe.jsonl")
    assert len(B.estados_modelos(INV, [])) == 3
