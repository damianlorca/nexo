# -*- coding: utf-8 -*-
"""T140 pieza E: handoff formal a Claude para lo que NEXO no puede resolver solo (codigo, arquitectura...).

Tests dados (los escribe Claude; el implementador SOLO crea nucleo/handoff.py). Contrato:
- Constante `RUTA` = RAIZ / "memoria" / "handoff_claude.jsonl" (RAIZ = carpeta del repo); los tests la cambian.
  Un JSON por linea, UTF-8, ensure_ascii=False. Si el archivo no existe, no hay entradas.
- `anotar(tarea: str, orden: str, motivo: str, contexto: str = "", canal: str = "web",
          ahora: datetime | None = None) -> dict`
  Entrada: {"tarea", "orden" (literal INTACTO, sin recortar ni limpiar), "motivo" (max. 300 car.),
  "contexto" (max. 2000 car.), "canal", "cuando" ("%Y-%m-%d %H:%M:%S" de `ahora`), "recogido": None}.
  Sin duplicados: si ya hay una entrada SIN recoger de la misma tarea, no se escribe nada y se devuelve esa.
  `tarea` vacia o `orden` vacia (tras strip) -> ValueError, sin escribir.
- `pendientes() -> list[dict]`: las entradas con "recogido" None, de la mas antigua a la mas nueva (orden del archivo).
  Una linea que no es JSON valido se salta (no rompe la lectura) y no se pierde al reescribir.
- `recoger(tarea: str, nota: str, ahora: datetime | None = None) -> int`: marca TODAS las entradas sin recoger de
  esa tarea con "recogido": {"cuando": ..., "nota": nota[:300]}; devuelve cuantas marco (0 si ninguna). Reescribe el
  archivo entero de forma atomica (temporal + os.replace) conservando el orden y las lineas no validas tal cual.
- Una tarea ya recogida puede volver a anotarse (entrada nueva).
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from nucleo import handoff as H

AHORA = datetime(2026, 10, 12, 12, 0, 0)


@pytest.fixture(autouse=True)
def ruta(tmp_path, monkeypatch):
    r = tmp_path / "handoff_claude.jsonl"
    monkeypatch.setattr(H, "RUTA", r)
    return r


def test_vacio_sin_archivo():
    assert H.pendientes() == []
    assert H.recoger("T1", "nada") == 0


def test_anotar_guarda_el_literal_intacto(ruta):
    orden = "  arregla el bug del bot\ncon saltos   y espacios  "
    e = H.anotar("T900", orden, "categoria codigo: necesita a Claude", contexto="c" * 5000, ahora=AHORA)
    assert e == {"tarea": "T900", "orden": orden, "motivo": "categoria codigo: necesita a Claude",
                 "contexto": "c" * 2000, "canal": "web", "cuando": "2026-10-12 12:00:00", "recogido": None}
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 1 and json.loads(lineas[0]) == e
    assert H.pendientes() == [e]


def test_sin_duplicados_de_la_misma_tarea(ruta):
    a = H.anotar("T900", "orden 1", "m", ahora=AHORA)
    b = H.anotar("T900", "orden 2", "otro motivo", ahora=AHORA)
    assert b == a and len(ruta.read_text(encoding="utf-8").splitlines()) == 1


def test_vacios_dan_error(ruta):
    with pytest.raises(ValueError):
        H.anotar("", "orden", "m")
    with pytest.raises(ValueError):
        H.anotar("T1", "   ", "m")
    assert not ruta.exists()


def test_recoger_y_volver_a_anotar(ruta):
    H.anotar("T1", "uno", "m", ahora=AHORA)
    H.anotar("T2", "dos", "m", ahora=AHORA)
    assert H.recoger("T1", "hecho en 740f0db", ahora=AHORA) == 1
    assert [e["tarea"] for e in H.pendientes()] == ["T2"]
    assert H.recoger("T1", "otra vez") == 0
    H.anotar("T1", "uno bis", "m", ahora=AHORA)
    assert [e["tarea"] for e in H.pendientes()] == ["T2", "T1"]
    todas = [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines()]
    assert todas[0]["recogido"] == {"cuando": "2026-10-12 12:00:00", "nota": "hecho en 740f0db"}


def test_linea_rota_no_rompe_ni_se_pierde(ruta):
    H.anotar("T1", "uno", "m", ahora=AHORA)
    with ruta.open("a", encoding="utf-8") as f:
        f.write("esto no es json\n")
    H.anotar("T2", "dos", "m", ahora=AHORA)
    assert [e["tarea"] for e in H.pendientes()] == ["T1", "T2"]
    H.recoger("T2", "ok", ahora=AHORA)
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert lineas[1] == "esto no es json" and len(lineas) == 3


def test_motivo_recortado():
    assert len(H.anotar("T3", "o", "m" * 999, ahora=AHORA)["motivo"]) == 300
