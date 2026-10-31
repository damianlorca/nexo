# -*- coding: utf-8 -*-
"""Bloque 10 (17/10): remates de las fichas de reels. Todo con dobles, sin red."""
from __future__ import annotations

import pytest

from nucleo import reels_calidad as C
from nucleo import reels_ficha as F
from nucleo import reels_huecos as H


def _e(nombre, tipo="dato", **kw):
    return dict({"tipo": tipo, "nombre": nombre, "dueno": None, "url": None, "que_es": "", "para_que": "",
                 "categorias": ["trading"], "fuentes": [], "confianza": "media", "en_promesa": False,
                 "origen": "modelo", "verificado": True}, **kw)


# ---- 3a) el dato de idea central no se corta a media frase
def test_recortar_no_parte_frases():
    corto = "Perderse los 8 dias mas importantes del mercado en un anio te habria costado el 80 % de las ganancias."
    assert C.recortar(corto, 200) == corto
    largo = ("Perderse los 8 dias mas importantes del mercado en un anio te habria costado el 80 % de las ganancias. "
             "Y ademas ocurre justo antes de los anuncios de la Fed, no despues, segun dos economistas del banco central.")
    r = C.recortar(largo, 110)
    assert len(r) <= 110 and r.endswith("ganancias.")
    r = C.recortar("palabra " * 40, 50)
    assert len(r) <= 50 and r.endswith("palabra…")


def test_la_afirmacion_larga_se_recorta_entera_en_el_elemento_dato():
    texto = "Una frase completa con cifras 80 %. " * 10
    ficha = F.normalizar({"tema": "t", "resumen": "r", "afirmacion_principal": {"texto": texto}, "elementos": []}, "mat")
    dato = [e for e in ficha["elementos"] if e["origen"] == "afirmacion"][0]
    assert len(dato["nombre"]) <= 200 and dato["nombre"].endswith(".")


# ---- 3b) rehacer nunca pierde
def test_rehacer_con_menos_elementos_fusiona_con_la_anterior_sin_duplicados():
    previa = {"_n_ficha": 5, "elementos": [
        _e("El 80 % de las ganancias llega en 8 dias del anio", verificado=False),
        _e("Retorno medio de 49 puntos basicos antes del anuncio", verificado=False),
        _e("S&P 500", que_es="indice"),
        _e("24-hour slices", "tecnica"),
        _e("Resumen viejo", origen="afirmacion")]}
    nueva = {"elementos": [_e("S&P 500", que_es="indice"), _e("the paper")]}
    assert F.conservar_anteriores(nueva, previa) == 3          # no repite S&P ni recupera la afirmacion (se recalcula)
    nombres = [e["nombre"] for e in nueva["elementos"]]
    assert "Retorno medio de 49 puntos basicos antes del anuncio" in nombres and "24-hour slices" in nombres
    recuperadas = [e for e in nueva["elementos"] if e.get("origen") == "ficha_anterior"]
    assert len(recuperadas) == 3 and {e["origen_previo"] for e in recuperadas} == {"modelo"}
    assert nueva["fusion_anterior"] == {"nuevos": 2, "anadidos": 3, "version_mayor": 5}
    assert F.conservar_anteriores(nueva, previa) == 0           # idempotente: ya estan


def test_la_fusion_no_duplica_cifras_redactadas_casi_igual():
    previa = {"_n_ficha": 4, "elementos": [_e("Perderse los 8 dias mas importantes del mercado"),
                                           _e("Otra cifra distinta de 12 puntos basicos")]}
    nueva = {"elementos": [_e("Perderse los 8 dias mas importantes del mercado del anio")]}
    assert F.conservar_anteriores(nueva, previa) == 1
    assert len(nueva["elementos"]) == 2


def test_si_la_pasada_nueva_no_trae_menos_se_mantiene_la_regla_estricta():
    previa = {"_n_ficha": 1, "elementos": [_e("Un dato suelto", verificado=False), _e("Crea el tuyo", "idea_proyecto")]}
    nueva = {"elementos": [_e("S&P 500")]}
    assert F.conservar_anteriores(nueva, previa) == 0 and "fusion_anterior" not in nueva


# ---- 3c) cuenta solo para cuentas o personas
@pytest.mark.parametrize("nombre,que_es,tipo,esperado", [
    ("Federal Reserve", "Banco central de los Estados Unidos, responsable de la politica monetaria", "cuenta", "organizacion"),
    ("Federal Reserve", "Banco central de los Estados Unidos", "dato", "organizacion"),
    ("OpenAI", "Empresa de inteligencia artificial", "cuenta", "organizacion"),
    ("MIT", "Universidad de Massachusetts", "dato", "organizacion"),
    ("Two New York Fed economists", "Dos economistas del Banco de la Reserva Federal de Nueva York", "cuenta", None),
    ("@quantpapers", "cuenta de divulgacion", "dato", "cuenta"),
    ("Ana Perez", "Profesora de la Universidad de Sevilla, investigadora", "cuenta", None),
    ("S&P 500", "Indice bursatil que agrupa a las 500 mayores empresas", "dato", None),
])
def test_cuenta_solo_para_cuentas_o_personas(nombre, que_es, tipo, esperado):
    assert C.retipar(_e(nombre, tipo, que_es=que_es)) == esperado


def test_organizacion_es_un_tipo_y_sus_sinonimos_no_son_cuenta():
    assert "organizacion" in F.TIPOS
    assert F.tipo_normal("empresa") == "organizacion" and F.tipo_normal("organismo") == "organizacion"
    assert F.tipo_normal("persona") == "cuenta"


def test_normalizar_pasa_la_cuenta_institucional_a_organizacion():
    crudo = {"tema": "t", "resumen": "r", "elementos": [
        {"tipo": "cuenta", "nombre": "Federal Reserve", "que_es": "Banco central de los Estados Unidos"}]}
    ficha = F.normalizar(crudo, "Federal Reserve")
    assert [e["tipo"] for e in ficha["elementos"] if e["nombre"] == "Federal Reserve"] == ["organizacion"]


# ---- 3d) 'sin uso claro'
def test_sin_uso_claro_es_un_para_que_valido_y_no_cuenta_como_repetido():
    a, b = _e("A", "herramienta", para_que=C.SIN_USO), _e("B", "herramienta", para_que=C.SIN_USO)
    assert C.para_que_pobre(a, [a, b]) == ""


def test_el_para_que_pobre_que_no_se_arregla_queda_como_sin_uso_claro_y_sin_alerta():
    rep = "Revisar los cambios antes de que Claude los guarde en el repositorio"
    ficha = {"tema": "t", "resumen": "r", "afirmacion_principal": "", "elementos": [
        _e("A", "herramienta", que_es="Algo util de verdad", para_que=rep),
        _e("B", "herramienta", que_es="Otra cosa util", para_que=rep),
        _e("C", "herramienta", que_es="Tercera", para_que="")]}
    alertas = F.cerrar_calidad(ficha)
    assert [e["para_que"] for e in ficha["elementos"]] == [C.SIN_USO] * 3
    assert not [a for a in alertas if "para que" in a]


def test_los_prompts_piden_sin_uso_claro():
    assert "sin uso claro" in F.PROMPT and "sin uso claro" in F.PROMPT_CORREGIR
    assert "organizacion" in F.PROMPT


# ---- 3e) huecos: lo que una IA reproduce no es hueco; lo que solo tiene el autor, si
def _ficha(promete, elementos, **ll):
    return {"codigo": "C1", "url": "u", "autor": "a", "tema": "mods",
            "llamada": dict({"hay": True, "tipo": "comenta", "palabra": "MODS", "promete": promete}, **ll),
            "completitud": {"faltan": 0, "prometidos": 4}, "elementos": elementos}


MODS = [_e(f"Modo {i}", "herramienta", categorias=["ia_prompts"],
           que_es="Modo de Claude Code que hace algo concreto y util para el flujo de trabajo") for i in range(4)]


def test_los_prompts_de_unos_mods_que_el_reel_explica_no_son_hueco():
    ev = H.evaluar(_ficha("te envio por privado la guia con el prompt de cada mod", MODS))
    assert ev["cubierto"] and "puede reproducir una IA" in ev["motivo"] and "Modo 0" in ev["motivo"]
    assert H.hueco(_ficha("la guia con el prompt de cada mod", MODS)) is None


def test_un_prompt_de_algo_que_el_reel_no_explica_sigue_siendo_hueco():
    vacios = [_e("Modo X", "herramienta", categorias=["ia_prompts"])]
    ev = H.evaluar(_ficha("el prompt completo", vacios))
    assert not ev["cubierto"] and "material privado" in ev["faltas"][0]


@pytest.mark.parametrize("promete", ["el excel con los datos", "el PDF", "the dataset", "las cifras exactas"])
def test_lo_que_solo_tiene_el_autor_si_es_hueco(promete):
    ev = H.evaluar(_ficha(promete, MODS))
    assert not ev["cubierto"] and "material privado" in ev["faltas"][0]


def test_listas_y_enlaces_de_lo_que_el_reel_nombra_no_son_hueco_pero_si_lo_que_falta():
    assert H.evaluar(_ficha("los enlaces de cada herramienta", MODS))["cubierto"]
    f = _ficha("la lista completa de los 20 repos", MODS)
    f["completitud"] = {"faltan": 16, "prometidos": 20}
    assert not H.evaluar(f)["cubierto"]
    assert "no nombra" in H.evaluar(_ficha("la lista completa", []))["faltas"][0]


def test_nombrado_en_publico_sigue_cubierto():
    assert H.evaluar(_ficha("el excel", MODS, nombrado_en_publico=True))["cubierto"]
