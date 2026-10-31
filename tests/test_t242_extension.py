# -*- coding: utf-8 -*-
"""T242: extension de los borradores adaptable por tarea (etiqueta extension:corta|normal|larga,
300/600/1500 palabras aprox.), en vez del limite fijo de antes. Los recortes de reenvio a
revisores/mejoras (nucleo.trabajo) y el LIMITE_PROMPT del auditor (nucleo.auditor) escalan con la
misma extension para no cortar nunca un borrador largo de verdad. Sin red ni Chrome."""
from __future__ import annotations

from nucleo import auditor, trabajo
from nucleo import tareas as T
from tests.test_ok_absoluto import CIERRE_OK, REV_OK, Api, Web, _correr, cola  # noqa: F401

MARCA_FINAL = "MARCA_FINAL_T242"
# ~12000 caracteres: mas que el tope de "normal" (7000) y menos que el de "larga" (17500).
RELLENO_12000 = ("Parrafo de contenido de prueba para T242 sobre una extension larga. " * 172)[:12000 - len(MARCA_FINAL)]


def _con_extension(cola, extension):
    etiquetas = list(cola["etiquetas"]) + [f"extension:{extension}"]
    return T.actualizar(cola["id"], etiquetas=etiquetas)


# ------------------------------------------------------------------ mapeo de palabras
def test_extension_por_defecto_es_normal_600_palabras():
    assert trabajo._extension({}) == "normal"
    assert trabajo._palabras({}) == 600


def test_etiqueta_extension_cambia_las_palabras_objetivo():
    assert trabajo._palabras({"etiquetas": ["extension:corta"]}) == 300
    assert trabajo._palabras({"etiquetas": ["extension:normal"]}) == 600
    assert trabajo._palabras({"etiquetas": ["extension:larga"]}) == 1500


def test_etiqueta_invalida_no_rompe_y_cae_en_normal():
    assert trabajo._extension({"etiquetas": ["extension:enorme"]}) == "normal"


def test_instruccion_lleva_las_palabras_de_la_etiqueta():
    t = {"etiquetas": ["extension:larga"]}
    assert "maximo 1500 palabras" in trabajo._instruccion(t, "investigacion")
    assert "Las 1500 palabras no incluyen" in trabajo._instruccion(t, "investigacion")
    assert "maximo 1500 palabras" in trabajo._instruccion(t, "redaccion")
    assert "maximo 1500 palabras" in trabajo._instruccion(t, "resumen")


# ------------------------------------------------------------------ tope de reenvio (Delegacion)
def test_tope_version_escala_con_la_extension(cola):
    for extension, esperado in (("corta", 3500), ("normal", 7000), ("larga", 17500)):
        t = _con_extension(cola, extension)
        d = trabajo.Delegacion(t, "investigacion")
        assert d.tope_version == esperado, extension


# ------------------------------------------------------------------ LIMITE_PROMPT del auditor
def test_limite_prompt_de_revision_escala_con_el_factor():
    base = auditor.LIMITE_PROMPT["revision"]
    assert auditor.revisar_prompt("x" * (base + 1), "revision", factor=1.0)
    assert auditor.revisar_prompt("x" * (base + 1), "revision", factor=17500 / 7000) == []


def test_limite_prompt_de_generar_no_escala_nunca():
    base = auditor.LIMITE_PROMPT["generar"]
    assert auditor.revisar_prompt("x" * (base + 1), "generar", factor=17500 / 7000)


# ------------------------------------------------------------------ integracion: llega entero
def test_borrador_largo_extension_larga_llega_entero_al_revisor(cola, monkeypatch):
    _con_extension(cola, "larga")
    v0 = "ENTENDIMIENTO:\nSe pide un informe largo.\n### INFORME\n" + RELLENO_12000 + MARCA_FINAL + "."
    autor = Web("chatgpt", v0, v0 + CIERRE_OK)
    rev = Api("gemini_api", REV_OK, REV_OK)
    _correr(monkeypatch, autor, [rev])
    [llamada_revisor] = [ll for ll in rev.llamadas]
    assert MARCA_FINAL in llamada_revisor["prompt"], "el borrador largo llego cortado al revisor"


def test_borrador_igual_de_largo_con_extension_normal_si_se_corta(cola, monkeypatch):
    _con_extension(cola, "normal")
    v0 = "ENTENDIMIENTO:\nSe pide un informe.\n### INFORME\n" + RELLENO_12000 + MARCA_FINAL + "."
    autor = Web("chatgpt", v0, v0 + CIERRE_OK)
    rev = Api("gemini_api", REV_OK, REV_OK)
    _correr(monkeypatch, autor, [rev])
    [llamada_revisor] = [ll for ll in rev.llamadas]
    assert MARCA_FINAL not in llamada_revisor["prompt"], "con extension normal deberia seguir cortando a 7000"
