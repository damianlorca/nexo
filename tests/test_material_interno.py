# -*- coding: utf-8 -*-
"""T232 (Damian 27/09): etiqueta material:interno para analizar el propio NEXO con una IA externa.

El limpiador de relleno (recorte a 1200 car. y borrado de ids T###) esta bien para temas externos, pero
dejo a ChatGPT con 1 de 85 tareas. Con material:interno el detalle va entero (tope 40.000) y con sus ids;
los datos privados y las claves se siguen bloqueando. Las tareas cat:personal nunca salen hacia fuera.
"""
from __future__ import annotations

import pytest

from nucleo import auditor, trabajo
from nucleo import tareas as T
from tests.test_ok_absoluto import CIERRE_OK, REV_OK, V0, V1, Api, Web, _correr, cola  # noqa: F401

LISTA = "\n".join(f"T{100 + i} | Tarea numero {i} de la cola | imp 3 urg 3 | pendiente | cat:codigo | detalle {i}"
                  for i in range(85))


def _interna(cola, detalle=LISTA):
    etiquetas = list(cola["etiquetas"]) + [trabajo.MATERIAL_INTERNO]
    return T.actualizar(cola["id"], detalle=detalle, etiquetas=etiquetas)


# ------------------------------------------------------------------ 1) prompt entero y con ids
def test_material_interno_va_entero_y_con_sus_ids(cola):
    t = _interna(cola)
    p = trabajo._prompt_gen(t, "investigacion")
    assert "T100 |" in p and "T184 |" in p and len(p) > 1200
    assert p.count("\nT1") == 85


def test_sin_la_etiqueta_se_sigue_limpiando(cola):
    t = T.actualizar(cola["id"], detalle=LISTA)
    p = trabajo._prompt_gen(t, "investigacion")
    assert "T100" not in p and len(trabajo._limpiar_interno(LISTA)) <= 1200


def test_material_interno_tiene_tope_de_40000(cola):
    t = _interna(cola, detalle="x " * 30000)
    p = trabajo._prompt_gen(t, "investigacion")
    assert trabajo.TOPE_MATERIAL == 40000 and 40000 <= len(p) < 40000 + 4000


# ------------------------------------------------------------------ 1) el auditor
def test_auditor_permite_ids_y_tamano_solo_con_material_interno():
    prompt = "Analiza estas tareas:\n" + LISTA * 2
    normal = auditor.revisar_prompt(prompt, "generar")
    assert any("codigo interno" in p for p in normal) and any("tope" in p for p in normal)
    assert auditor.revisar_prompt(prompt, "generar", interno=True) == []


def test_auditor_con_material_interno_sigue_bloqueando_privados_y_claves():
    for sucio in ("T101 | escribe a persona@ejemplo.com", "T101 | mira C:\\Users\\alguien\\x.txt",
                  "T101 | clave sk-" + "a" * 30, "T101 | ver secretos.toml"):
        problemas = auditor.revisar_prompt(sucio, "generar", interno=True)
        assert any(p.startswith("dato privado") for p in problemas), sucio


def test_material_interno_pasa_el_ciclo_y_la_auditoria_c(cola, monkeypatch):
    _interna(cola)
    autor = Web("chatgpt", V0, V1 + CIERRE_OK)
    [fila] = _correr(monkeypatch, autor, [Api("gemini_api", REV_OK, REV_OK)])
    assert "T184 |" in autor.llamadas[0]["prompt"]
    assert "c_prompt" not in (fila.get("fallos_auditoria") or []), fila


def test_material_interno_con_dato_privado_no_se_envia(cola, monkeypatch):
    _interna(cola, detalle=LISTA + "\nT999 | avisa a persona@ejemplo.com")
    autor = Web("chatgpt", V0)
    [fila] = _correr(monkeypatch, autor, [])
    assert autor.llamadas == [] and "no enviado" in fila["intentos"][0]["error"]


def test_material_interno_con_una_tarea_personal_no_se_envia(cola, monkeypatch):
    personal = T.anadir("Asunto personal", etiquetas=["cat:personal"])
    _interna(cola, detalle=LISTA + f"\n{personal['id']} | Asunto personal")
    autor = Web("chatgpt", V0)
    [fila] = _correr(monkeypatch, autor, [])
    assert autor.llamadas == [] and "personal" in fila["intentos"][0]["error"]


# ------------------------------------------------------------------ 2) listas sin cat:personal
def test_lista_para_ia_externa_excluye_las_personales(cola):
    T.anadir("Beca del master", etiquetas=["cat:personal", "tema:contenido_personal"], detalle="dinero de casa")
    T.anadir("Arreglar el vigia", etiquetas=["cat:codigo"], detalle="taskkill con /T")
    lineas = T.lista_para_ia_externa()
    texto = "\n".join(lineas)
    assert "Arreglar el vigia" in texto and cola["titulo"] in texto
    assert "Beca" not in texto and "dinero de casa" not in texto


def test_lista_para_ia_externa_tapa_datos_privados(cola):
    T.anadir("Escribir", etiquetas=["cat:codigo"], detalle="mandar a persona@ejemplo.com desde C:\\Users\\x\\y.txt")
    texto = "\n".join(T.lista_para_ia_externa())
    assert "persona@ejemplo.com" not in texto and "C:\\Users" not in texto
    assert auditor.revisar_prompt(texto, "generar", interno=True) == []
