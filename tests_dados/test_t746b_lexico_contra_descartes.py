# -*- coding: utf-8 -*-
"""Seguimiento de T746: en freno.pares_semanticos el modo LEXICO tambien compara contra lo DESCARTADO, y
`descartes.registro` se llama UNA sola vez.

Tests dados (los escribe Claude; el implementador SOLO cambia nucleo/freno.py). Van JUNTO con
test_t746_parecidas_fallback_lexico.py (modo lexico con UMBRAL_LEXICO, "metodo", "fallo_embeddings"): T844 hace las
dos cosas desde principal, con UNA sola pasada de comparacion (la similitud y el umbral cambian segun el modo; el bucle
no se duplica). Contrato de este archivo:
- `descartes.registro(tareas)` se llama EXACTAMENTE una vez por llamada a pares_semanticos cuando hay propuestas
  abiertas (cero veces si no hay ninguna), en los dos modos. Va FUERA del try de los embeddings: si registro lanza
  una excepcion, esta se PROPAGA (no es un fallo de embeddings ni activa el modo lexico).
- En modo lexico, cada propuesta se compara con cada descarte: `parecido(palabras(que(prop)), palabras(d["texto"]))`
  y entra en "contra_descartes" si es >= UMBRAL_LEXICO, con LAS MISMAS claves que en modo embeddings
  (a, b, coseno [redondeado a 3], causa, motivo, quien, cuando, informe, texto_a, texto_b), ordenado de mayor a menor.
- "descartes_comparados" = numero de descartes del registro, en los dos modos.
- Precedencia: si CUALQUIER llamada a embeber falla (tambien la de los textos de los descartes, aunque la de las
  propuestas haya ido bien), TODO el resultado es lexico; nunca se mezclan cosenos y Jaccard.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from nucleo import descartes, freno

AHORA = datetime(2026, 10, 12, 9, 0)

DESC = [{"id": "T500", "texto": "Crear un registro local de skills con busqueda por nombre y descripcion",
         "causa": "descartada", "motivo": "ya lo cubre el catalogo", "quien": "damian",
         "cuando": "2026-10-01 10:00:00", "informe": "", "origen": ""},
        {"id": "T501", "texto": "Pintar el logo de verde fosforito para la app movil",
         "causa": "descartada", "motivo": "no aporta", "quien": "claude",
         "cuando": "2026-10-02 10:00:00", "informe": "", "origen": ""}]


def _p(tid, que):
    return {"id": tid, "titulo": f"[Propuesta de T1] {que}", "detalle": f"QUE: {que}", "estado": "propuesta",
            "etiquetas": ["cat:propuesta"], "notas": [], "creada": "2026-10-10 10:00:00", "cerrada": None}


def _caido(textos):
    raise ConnectionError("Ollama no responde")


@pytest.fixture
def llamadas(tmp_path, monkeypatch):
    monkeypatch.setattr(freno, "INFORMES", tmp_path)
    n = []

    def falso(tareas=None):
        n.append(1)
        return [dict(d) for d in DESC]
    monkeypatch.setattr(descartes, "registro", falso)
    return n


def _tareas():
    return [_p("T901", "Crear registro local de skills con busqueda por nombre y por descripcion corta"),
            _p("T903", "Medir la temperatura de la GPU cada hora y avisar")]


def test_lexico_compara_contra_descartes(llamadas):
    r = freno.pares_semanticos(embeber=_caido, tareas=_tareas(), ahora=AHORA)
    assert r["metodo"] == "lexico"
    assert [(p["a"], p["b"]) for p in r["contra_descartes"]] == [("T901", "T500")]
    p = r["contra_descartes"][0]
    assert set(p) == {"a", "b", "coseno", "causa", "motivo", "quien", "cuando", "informe", "texto_a", "texto_b"}
    assert p["coseno"] >= freno.UMBRAL_LEXICO and p["motivo"] == "ya lo cubre el catalogo"
    assert r["descartes_comparados"] == 2


def test_registro_una_vez_en_modo_lexico(llamadas):
    freno.pares_semanticos(embeber=_caido, tareas=_tareas(), ahora=AHORA)
    assert len(llamadas) == 1


def test_registro_una_vez_en_modo_embeddings(llamadas):
    r = freno.pares_semanticos(umbral=0.9, embeber=lambda t: [[1.0, 0.0] for _ in t], tareas=_tareas(), ahora=AHORA)
    assert r["metodo"] == "embeddings"
    assert len(llamadas) == 1
    assert r["descartes_comparados"] == 2 and len(r["contra_descartes"]) == 4   # 2 propuestas x 2 descartes


def test_sin_propuestas_no_se_llama_al_registro(llamadas):
    freno.pares_semanticos(embeber=_caido, tareas=[], ahora=AHORA)
    assert llamadas == []


def test_fallo_al_embeber_descartes_hace_todo_lexico(llamadas):
    def solo_falla_descartes(textos):
        if any("fosforito" in t for t in textos):
            raise TimeoutError("bge-m3 se ha quedado sin memoria")
        return [[1.0, 0.0] for _ in textos]
    r = freno.pares_semanticos(umbral=0.9, embeber=solo_falla_descartes, tareas=_tareas(), ahora=AHORA)
    assert r["metodo"] == "lexico" and "sin memoria" in r["fallo_embeddings"]
    assert r["entre_propuestas"] == []                  # Jaccard bajo entre T901 y T903: nada de cosenos 1.0
    assert [(p["a"], p["b"]) for p in r["contra_descartes"]] == [("T901", "T500")]


def test_fallo_del_registro_se_propaga(tmp_path, monkeypatch):
    monkeypatch.setattr(freno, "INFORMES", tmp_path)

    def roto(tareas=None):
        raise ValueError("registro roto")
    monkeypatch.setattr(descartes, "registro", roto)
    with pytest.raises(ValueError):
        freno.pares_semanticos(embeber=lambda t: [[1.0, 0.0] for _ in t], tareas=_tareas(), ahora=AHORA)
