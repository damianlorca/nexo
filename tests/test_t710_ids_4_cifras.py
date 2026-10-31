# -*- coding: utf-8 -*-
"""T710: NEXO llega a T1000. Las regex de ids no pueden cortar 'T1000' en 'T100' y nada debe ordenar ids como
texto ('T1000' < 'T200')."""
from __future__ import annotations

import re

from interfaz import humano
from nucleo import chat_tarea, trabajo, turnos, uso_claude
from nucleo import tareas as T

IDS = ("T999", "T1000", "T1001")


def test_regex_de_ids_cogen_el_id_entero():
    texto = "mira T999, T1000 y T1001 (no T10000x ni xT1000)"
    assert uso_claude._ID.findall(texto) == list(IDS)
    m = uso_claude._TAREAS_CLI.search(".venv\\Scripts\\python.exe -m nucleo.tareas verificar T1001 'ok'")
    assert m and m.group(1) == "T1001"
    assert humano._REFERENCIAS.sub("", "Hecho (ver T1000 y T1001)") == "Hecho"
    for i in IDS:
        assert turnos._ID_TAREA.match(i)


def test_tarea_personal_de_cuatro_cifras_no_sale_hacia_otra_ia(monkeypatch):
    """El filtro de privacidad: con T\\d{3}\\b una personal T1000 citada en un prompt NO se detectaba."""
    monkeypatch.setattr(T, "es_personal", lambda t: t["id"] in ("T999", "T1000"))
    datos = T.cargar()
    datos["siguiente_id"] = 999
    T.guardar(datos)
    for i in range(3):
        T.anadir(f"x{i}")
    assert trabajo._personales_citadas("usa T1000, T999, T1001 y T10") == ["T999", "T1000"]


def test_clave_id_ordena_por_numero():
    assert sorted(["T1001", "T200", "T999", "T1000", "T050"], key=T.clave_id) == ["T050", "T200", "T999", "T1000",
                                                                                     "T1001"]
    assert T.clave_id("raro") > T.clave_id("T99999")


def test_ordenadas_desempata_por_numero_de_id():
    a = T.anadir("A", importancia=3, urgencia=3)
    datos = T.cargar()
    base = next(t for t in datos["tareas"] if t["id"] == a["id"])
    gemelas = [dict(base, id=i) for i in ("T1000", "T999", "T1001")]
    assert [t["id"] for t in T.ordenadas(gemelas)] == ["T999", "T1000", "T1001"]


def test_el_generador_da_t1000_tras_t999():
    datos = T.cargar()
    datos["siguiente_id"] = 999
    T.guardar(datos)
    assert [T.anadir(f"x{i}")["id"] for i in range(3)] == list(IDS)
    assert chat_tarea  # el chat valida ids con la misma forma (T\d{3,})
    assert re.fullmatch(r"T\d{3,}", "T1000")
