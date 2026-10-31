# -*- coding: utf-8 -*-
"""T288 (Damian 28/09): un revisor no puede subir a ALTA (y disparar ESCALAR, que gasta a Claude) solo
por no poder comprobar un dato. Casos reales 27-28/09 (T174 agentskills.io, T199 OpenClaw, T200 Hermes
Agent): Gemini/NVIDIA marcaron como alucinacion datos que eran ciertos. Sin red: nucleo.verificar_hechos
va mockeado."""
from __future__ import annotations

from unittest import mock

from nucleo import auditor, trabajo
from tests.test_ok_absoluto import CAMBIOS, V0, V1, Web, Api, cola  # noqa: F401 (fixture 'cola')

# Caso real T174 (agentskills.io): el revisor no podia comprobar la URL y marco GRAVEDAD ALTA.
REV_NO_VERIF_ALTA = (
    'FALLOS:\n- "URL oficial: https://agentskills.io" [NO VERIFICABLE: no tengo busqueda web activa]\n'
    "OMISIONES:\n- ninguno\nMEJORAS:\n- ninguno\nAÑADIR:\n- ninguno\n"
    "GRAVEDAD: ALTA\nVEREDICTO: CAMBIOS_NECESARIOS"
)
# Un FALSO con prueba real (el revisor SI comprobo la fuente y la contradice).
REV_FALSO_ALTA = (
    'FALLOS:\n- "licencia MIT" [FALSO: el repo declara Apache-2.0 segun github.com/x/y/blob/main/LICENSE]\n'
    "OMISIONES:\n- ninguno\nMEJORAS:\n- ninguno\nAÑADIR:\n- ninguno\n"
    "GRAVEDAD: ALTA\nVEREDICTO: CAMBIOS_NECESARIOS"
)
# Mezcla de un dato tildado NO VERIFICABLE con otros FALLOS sin etiquetar (formato viejo, mixto):
# no se recorta la ALTA porque no todo el mundo sigue el formato nuevo todavia.
REV_MIXTA_ALTA = (
    'FALLOS:\n- "URL oficial: https://x.test" [NO VERIFICABLE: sin busqueda]\n- la fecha no cuadra\n'
    "OMISIONES:\n- ninguno\nMEJORAS:\n- ninguno\nAÑADIR:\n- ninguno\n"
    "GRAVEDAD: ALTA\nVEREDICTO: CAMBIOS_NECESARIOS"
)
CONFIRMADO_CIERTO = {"confirmado": True, "detalle": "https://agentskills.io: responde 200"}
CONFIRMADO_FALSO = {"confirmado": False, "detalle": "https://agentskills.io: responde 404, la URL no existe"}
NO_CONCLUYENTE = {"confirmado": None, "detalle": "sin URL ni repositorio de GitHub que comprobar"}


# ------------------------------------------------------------------ unidad: _gravedad_efectiva
def test_no_verificable_solo_no_sube_a_alta_si_nexo_confirma_que_es_cierto():
    with mock.patch("nucleo.verificar_hechos.verificar_item", return_value=CONFIRMADO_CIERTO):
        grav, clasif = trabajo._gravedad_efectiva(REV_NO_VERIF_ALTA)
    assert grav == "MEDIA"
    assert clasif[0]["tipo"] == "NO_VERIFICABLE"
    assert clasif[0]["verificacion_nexo"] == CONFIRMADO_CIERTO


def test_no_verificable_solo_no_sube_a_alta_si_nexo_no_puede_concluir():
    with mock.patch("nucleo.verificar_hechos.verificar_item", return_value=NO_CONCLUYENTE):
        grav, _ = trabajo._gravedad_efectiva(REV_NO_VERIF_ALTA)
    assert grav == "MEDIA"


def test_no_verificable_sigue_en_alta_si_nexo_comprueba_que_es_falso():
    with mock.patch("nucleo.verificar_hechos.verificar_item", return_value=CONFIRMADO_FALSO) as m:
        grav, clasif = trabajo._gravedad_efectiva(REV_NO_VERIF_ALTA)
    assert grav == "ALTA"
    assert clasif[0]["verificacion_nexo"]["confirmado"] is False
    m.assert_called_once()


def test_falso_con_prueba_mantiene_alta_sin_llamar_a_verificar():
    with mock.patch("nucleo.verificar_hechos.verificar_item") as m:
        grav, clasif = trabajo._gravedad_efectiva(REV_FALSO_ALTA)
    assert grav == "ALTA" and clasif[0]["tipo"] == "FALSO"
    m.assert_not_called()   # ya hay prueba: no hace falta que NEXO compruebe nada


def test_formato_viejo_sin_etiquetas_respeta_la_gravedad_declarada():
    from tests.test_ok_absoluto import REV_ALTA
    grav, clasif = trabajo._gravedad_efectiva(REV_ALTA)
    assert grav == "ALTA"
    assert all(c["tipo"] is None for c in clasif)


def test_mezcla_de_etiquetado_y_sin_etiquetar_no_se_recorta():
    grav, _ = trabajo._gravedad_efectiva(REV_MIXTA_ALTA)
    assert grav == "ALTA"


# ------------------------------------------------------------------ integracion: no escala a Claude
def _correr(monkeypatch, autor, revisores):
    monkeypatch.setattr(trabajo, "_generadores", lambda cat: [autor])
    monkeypatch.setattr(trabajo, "_revisores", lambda nombre: [r for r in revisores
                                                              if auditor.familia(r.nombre) != auditor.familia(nombre)])
    return trabajo.ciclo(max_tareas=1)


@mock.patch("nucleo.verificar_hechos.verificar_item", return_value=CONFIRMADO_CIERTO)
def test_dato_real_marcado_no_verificable_no_escala_a_claude(_m, cola, monkeypatch):
    # Caso real T174: dos rondas ALTA/NO_VERIFICABLE por un dato que en realidad era cierto.
    autor = Web("chatgpt", V0, V1 + CAMBIOS, V1 + CAMBIOS)
    rev = Api("gemini_api", REV_NO_VERIF_ALTA, REV_NO_VERIF_ALTA)
    [fila] = _correr(monkeypatch, autor, [rev])
    assert fila["veredicto"] != "ESCALAR", fila


@mock.patch("nucleo.verificar_hechos.verificar_item", return_value=CONFIRMADO_FALSO)
def test_dato_realmente_falso_si_escala_tras_comprobarlo_nexo(_m, cola, monkeypatch):
    autor = Web("chatgpt", V0, V1 + CAMBIOS, V1 + CAMBIOS)
    rev = Api("gemini_api", REV_NO_VERIF_ALTA, REV_NO_VERIF_ALTA)
    [fila] = _correr(monkeypatch, autor, [rev])
    assert fila["veredicto"] == "ESCALAR", fila


# ------------------------------------------------------------------ T334: FALSO con prueba debil
def _rev_falso(detalle: str) -> str:
    return (f'FALLOS:\n- "Node 24 es LTS" [FALSO: {detalle}]\n'
            "OMISIONES:\n- ninguno\nMEJORAS:\n- ninguno\nAÑADIR:\n- ninguno\n"
            "GRAVEDAD: ALTA\nVEREDICTO: CAMBIOS_NECESARIOS")


def test_t334_falso_con_prueba_debil_se_comprueba_como_un_no_verificable():
    # Caso real T201/T202: groq/nvidia con conocimiento de 2024 marcaron FALSO datos ciertos.
    for detalle in ("mi conocimiento llega hasta 2024", "es una fecha futura", "no lo encuentro en ninguna fuente",
                    "la URL generica no lleva a esa pagina", ""):
        with mock.patch("nucleo.verificar_hechos.verificar_item", return_value=CONFIRMADO_CIERTO) as m:
            grav, clasif = trabajo._gravedad_efectiva(_rev_falso(detalle))
        assert grav == "MEDIA", detalle
        assert clasif[0]["prueba_debil"] is True
        m.assert_called_once()


def test_t334_falso_debil_sigue_en_alta_si_nexo_comprueba_que_es_falso():
    with mock.patch("nucleo.verificar_hechos.verificar_item", return_value=CONFIRMADO_FALSO):
        grav, _ = trabajo._gravedad_efectiva(_rev_falso("mi conocimiento llega hasta 2024"))
    assert grav == "ALTA"


def test_t334_falso_con_prueba_real_no_se_toca():
    with mock.patch("nucleo.verificar_hechos.verificar_item") as m:
        grav, clasif = trabajo._gravedad_efectiva(_rev_falso("nodejs.org/en/about/previous-releases lo lista como Current, no LTS"))
    assert grav == "ALTA" and clasif[0]["prueba_debil"] is False
    m.assert_not_called()
