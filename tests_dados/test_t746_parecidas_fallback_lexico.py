# -*- coding: utf-8 -*-
"""T746: freno.pares_semanticos sigue funcionando cuando fallan los embeddings (Ollama caido, bge-m3 no cargado...).

Tests dados (los escribe Claude; el implementador SOLO cambia nucleo/freno.py). Contrato:
- Si `embeber(...)` lanza CUALQUIER excepcion, pares_semanticos NO la propaga: repite la comparacion con similitud
  LEXICA local sin IA: `parecido(palabras(texto_a), palabras(texto_b))` (las funciones que ya hay en freno.py).
- En modo lexico el umbral es la constante nueva `UMBRAL_LEXICO = 0.5` (el `umbral` de coseno no se usa) y los pares
  guardan su valor en la clave "coseno" igual que ahora (redondeado a 3 decimales), para no romper el informe.
- El resultado lleva "metodo": "lexico" y "fallo_embeddings": el texto de la excepcion (max. 200 car.). Con
  embeddings que funcionan, "metodo": "embeddings" y no hay clave "fallo_embeddings".
- El informe .md dice en su primera linea "fallback lexico" cuando se usa el modo lexico.
- Sigue siendo SOLO informe: no toca la cola.
"""
from __future__ import annotations

from datetime import datetime

from nucleo import freno

AHORA = datetime(2026, 10, 12, 9, 0)


def _p(tid, que, estado="propuesta"):
    return {"id": tid, "titulo": f"[Propuesta de T1] {que}", "detalle": f"QUE: {que}", "estado": estado,
            "etiquetas": ["cat:propuesta"], "notas": [], "creada": "2026-10-10 10:00:00", "cerrada": None}


def _caido(textos):
    raise ConnectionError("Ollama no responde en 127.0.0.1:11434")


def _tareas():
    return [_p("T901", "Crear un registro local de skills con busqueda por nombre y descripcion"),
            _p("T902", "Crear registro local de skills con busqueda por nombre y por descripcion corta"),
            _p("T903", "Medir la temperatura de la GPU cada hora y avisar")]


def test_sin_embeddings_usa_similitud_lexica(tmp_path, monkeypatch):
    monkeypatch.setattr(freno, "INFORMES", tmp_path)
    r = freno.pares_semanticos(embeber=_caido, tareas=_tareas(), ahora=AHORA)
    assert r["metodo"] == "lexico"
    assert "Ollama no responde" in r["fallo_embeddings"]
    assert [(p["a"], p["b"]) for p in r["entre_propuestas"]] == [("T901", "T902")]
    assert r["entre_propuestas"][0]["coseno"] >= freno.UMBRAL_LEXICO


def test_umbral_lexico_es_0_5():
    assert freno.UMBRAL_LEXICO == 0.5


def test_informe_lexico_lo_dice(tmp_path, monkeypatch):
    monkeypatch.setattr(freno, "INFORMES", tmp_path)
    r = freno.pares_semanticos(embeber=_caido, tareas=_tareas(), ahora=AHORA)
    primera = (tmp_path / "parecidas_20261012_0900.md").read_text(encoding="utf-8").splitlines()[0]
    assert "fallback lexico" in primera.lower()
    assert r["informe"].endswith(".md")


def test_fallo_embeddings_se_recorta_a_200(tmp_path, monkeypatch):
    monkeypatch.setattr(freno, "INFORMES", tmp_path)

    def largo(textos):
        raise RuntimeError("x" * 1000)
    r = freno.pares_semanticos(embeber=largo, tareas=_tareas(), ahora=AHORA)
    assert len(r["fallo_embeddings"]) <= 200


def test_con_embeddings_que_funcionan_nada_cambia(tmp_path, monkeypatch):
    monkeypatch.setattr(freno, "INFORMES", tmp_path)
    r = freno.pares_semanticos(umbral=0.9, embeber=lambda textos: [[1.0, 0.0] for _ in textos],
                               tareas=_tareas(), ahora=AHORA)
    assert r["metodo"] == "embeddings" and "fallo_embeddings" not in r
    assert len(r["entre_propuestas"]) == 3          # vectores iguales: los 3 pares


def test_lexico_no_compara_textos_muy_cortos(tmp_path, monkeypatch):
    monkeypatch.setattr(freno, "INFORMES", tmp_path)
    r = freno.pares_semanticos(embeber=_caido, tareas=[_p("T1", "Hola"), _p("T2", "Hola")], ahora=AHORA)
    assert r["entre_propuestas"] == []              # parecido() devuelve 0 con menos de 3 raices
