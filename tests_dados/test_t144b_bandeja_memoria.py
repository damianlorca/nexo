# -*- coding: utf-8 -*-
"""T144 pieza B: bandeja de escrituras en la memoria por capas (lo que escriben las IAs espera aprobacion).

Tests dados (los escribe Claude; el implementador SOLO cambia nucleo/memoria_capas.py). Va DESPUES de la pieza A.
Contrato (ademas de lo de la pieza A):
- Bandeja = CARPETA / "pendientes.jsonl" (un JSON por linea, UTF-8, ensure_ascii=False).
- `anadir` con autor NO directo (paso 3 de la pieza A) ahora ademas guarda en la bandeja
  {"id": "M" + 4 cifras correlativas desde M0001, "capa", "texto" (intacto), "autor" (strip+minusculas),
   "cuando": f"{ahora:%Y-%m-%d %H:%M:%S}", "estado": "pendiente"} y devuelve {"estado": "pendiente", "id": ...}.
  El id siguiente = mayor id de la bandeja + 1 (aunque esten aprobadas o rechazadas).
  Mismo texto (strip) + misma capa + mismo autor ya PENDIENTE -> no se duplica: devuelve el id existente.
- `pendientes() -> list[dict]`: las de estado "pendiente", en orden de la bandeja.
- `aprobar(id, quien, ahora=None) -> dict`: quien no en DIRECTOS -> PermissionError. Id inexistente o no pendiente
  -> KeyError. Si no, escribe con la logica de `anadir` y el autor ORIGINAL de la entrada (la linea dice ese autor,
  no quien aprueba) pero saltandose el paso 3. Resultado:
    escrita   -> la entrada pasa a "aprobada" (+ "por": quien) y devuelve el dict de anadir;
    rechazada por tope -> la entrada SIGUE "pendiente" y devuelve {"estado": "rechazada", "motivo": "tope"}.
- `rechazar(id, quien, motivo="") -> dict`: igual de permisos y KeyError; la entrada pasa a "rechazada" con "por" y
  "motivo" (max. 300); devuelve la entrada.
- La bandeja se reescribe entera de forma atomica (temporal + os.replace) al aprobar o rechazar.
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from nucleo import memoria_capas as M

AHORA = datetime(2026, 10, 12, 9, 30, 15)


@pytest.fixture(autouse=True)
def carpeta(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "CARPETA", tmp_path / "capas")
    return tmp_path / "capas"


def test_ia_va_a_la_bandeja(carpeta):
    r = M.anadir("proyecto", "  Groq limita a 7000 tokens por minuto \n", "Qwen", ahora=AHORA)
    assert r == {"estado": "pendiente", "id": "M0001"}
    e = json.loads((carpeta / "pendientes.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert e == {"id": "M0001", "capa": "proyecto", "texto": "  Groq limita a 7000 tokens por minuto \n",
                 "autor": "qwen", "cuando": "2026-10-12 09:30:15", "estado": "pendiente"}
    assert M.leer("proyecto") == ""


def test_sin_duplicados_pendientes():
    a = M.anadir("proyecto", "dato", "qwen", ahora=AHORA)
    b = M.anadir("proyecto", " dato ", "qwen", ahora=AHORA)
    c = M.anadir("proyecto", "dato", "gemini", ahora=AHORA)
    assert a["id"] == b["id"] == "M0001" and c["id"] == "M0002"
    assert [e["id"] for e in M.pendientes()] == ["M0001", "M0002"]


def test_aprobar_escribe_con_el_autor_original():
    i = M.anadir("proyecto", "dato util", "gemini", ahora=AHORA)["id"]
    with pytest.raises(PermissionError):
        M.aprobar(i, "qwen")
    r = M.aprobar(i, "damian", ahora=AHORA)
    assert r["estado"] == "escrita" and M.leer("proyecto") == "- [2026-10-12 09:30 gemini] dato util\n"
    assert M.pendientes() == []
    with pytest.raises(KeyError):
        M.aprobar(i, "damian")


def test_aprobar_por_encima_del_tope_sigue_pendiente():
    M.anadir("usuario", "x" * 1950, "claude", ahora=AHORA)
    i = M.anadir("usuario", "y" * 100, "qwen", ahora=AHORA)["id"]
    assert M.aprobar(i, "claude", ahora=AHORA) == {"estado": "rechazada", "motivo": "tope"}
    assert [e["id"] for e in M.pendientes()] == [i]


def test_rechazar_y_el_id_sigue_creciendo(carpeta):
    i = M.anadir("diaria", "nota", "turno", ahora=AHORA)["id"]
    e = M.rechazar(i, "claude", "no aporta" * 100)
    assert e["estado"] == "rechazada" and e["por"] == "claude" and len(e["motivo"]) == 300
    assert M.anadir("diaria", "nota", "turno", ahora=AHORA)["id"] == "M0002"
    with pytest.raises(KeyError):
        M.rechazar("M0099", "claude")
