# -*- coding: utf-8 -*-
"""T163: una revision web solo cuenta si trae FALLOS/OMISIONES/MEJORAS/AÑADIR. Sin red: proveedores falsos."""
from __future__ import annotations

from unittest import mock

import pytest

from nucleo import trabajo
from proveedores import Resultado

COMPLETA = ("FALLOS:\n- \"dato\" dudoso\nOMISIONES:\n- falta coste\nMEJORAS:\n- ninguno\nAÑADIR:\n- riesgos\n"
            "GRAVEDAD: MEDIA\nVEREDICTO: CAMBIOS_NECESARIOS")
SOLO_VEREDICTO = "VEREDICTO: APROBADO"  # caso real 23/09: Gemini web, 19 caracteres
TAREA = {"id": "T9", "titulo": "x"}


class Revisor:
    """Proveedor de pega que responde por turnos (una respuesta por llamada)."""

    def __init__(self, nombre, *respuestas):
        self.nombre, self.respuestas, self.llamadas = nombre, list(respuestas), []

    def disponible(self):
        return True

    def enviar(self, prompt, buscar=False):
        self.llamadas.append(prompt)
        texto = self.respuestas.pop(0) if self.respuestas else ""
        return Resultado("OK", texto=texto) if texto else Resultado("ERROR", detalle="sin respuesta")


def _revisar(*revisores):
    with mock.patch.object(trabajo, "_revisores", return_value=list(revisores)):
        return trabajo._revisar(TAREA, "borrador", "chatgpt")


def test_el_caso_real_solo_veredicto_no_es_revision():
    assert trabajo._formato_valido(SOLO_VEREDICTO) == (False, ["FALLOS", "OMISIONES", "MEJORAS", "AÑADIR"])


def test_revision_completa_es_valida():
    assert trabajo._formato_valido(COMPLETA) == (True, [])


@pytest.mark.parametrize("texto", [
    COMPLETA.replace("FALLOS:", "**FALLOS:**").replace("AÑADIR:", "## AÑADIR"),
    COMPLETA.replace("AÑADIR", "ANADIR"),                        # sin eñe (teclado/modelo)
    COMPLETA.replace("OMISIONES:", "2) Omisiones:"),              # numerada y en minusculas
    COMPLETA.replace("MEJORAS:", "### MEJORAS"),                  # cabecera Markdown sin dos puntos
])
def test_variantes_de_cabecera_que_se_aceptan(texto):
    assert trabajo._formato_valido(texto)[0]


def test_una_palabra_en_mitad_de_frase_no_cuenta_como_seccion():
    texto = ("No veo fallos ni omisiones; las mejoras y lo que hay que añadir son menores.\n"
             "GRAVEDAD: BAJA\nVEREDICTO: APROBADO")
    assert trabajo._secciones_faltan(texto) == ["FALLOS", "OMISIONES", "MEJORAS", "AÑADIR"]


def test_secciones_sin_veredicto_ni_gravedad_no_valen():
    texto = "FALLOS:\n- ninguno\nOMISIONES:\n- ninguno\nMEJORAS:\n- ninguno\nAÑADIR:\n- ninguno"
    assert trabajo._formato_valido(texto) == (False, ["VEREDICTO/GRAVEDAD"])


def test_solo_veredicto_se_rechaza_y_se_reintenta_una_vez_con_formato_reforzado():
    g = Revisor("gemini_api", SOLO_VEREDICTO, COMPLETA)
    revs = _revisar(g)
    assert len(g.llamadas) == 2
    assert "tu respuesta anterior no seguia el formato" in g.llamadas[1]
    assert "FALLOS, OMISIONES, MEJORAS, AÑADIR" in g.llamadas[1].replace("faltaban: ", "")
    assert len(revs) == 1 and revs[0]["reintento"] is True and revs[0]["gravedad"] == "MEDIA"


def test_si_el_reintento_tampoco_trae_secciones_no_cuenta():
    g = Revisor("gemini_api", SOLO_VEREDICTO, SOLO_VEREDICTO)
    assert _revisar(g) == [] and len(g.llamadas) == 2  # un solo reintento, no un bucle


def test_revision_valida_a_la_primera_no_gasta_reintento():
    g = Revisor("gemini_api", COMPLETA)
    revs = _revisar(g)
    assert len(g.llamadas) == 1 and revs[0]["reintento"] is False


def test_un_revisor_rechazado_deja_paso_al_siguiente():
    malo = Revisor("gemini", SOLO_VEREDICTO, "me parece bien")
    bueno = Revisor("groq", COMPLETA)
    revs = _revisar(malo, bueno)
    assert [r["revisor"] for r in revs] == ["groq"]


def test_el_rol_del_revisor_sigue_pidiendo_las_cuatro_secciones():
    """Si alguien cambia el rol, el filtro exigiria secciones que el revisor ya no conoce."""
    rol = (trabajo.RAIZ / "roles" / "revisor_borrador.md").read_text(encoding="utf-8")
    assert trabajo._secciones_faltan(rol) == []
