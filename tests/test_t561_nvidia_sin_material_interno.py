# -*- coding: utf-8 -*-
"""T561: el material marcado como interno o privado no sale hacia NVIDIA Trial (auditor y trabajo).

El tribunal NO se toca: con material interno y autor ChatGPT, sin NVIDIA solo quedarian 2 familias (decision de Damian)."""
from __future__ import annotations

from nucleo import auditor
from proveedores import Resultado


def test_bloqueo_proveedor():
    assert "NVIDIA Trial" in auditor.bloqueo_proveedor("nvidia", interno=True)
    assert "privado" in auditor.bloqueo_proveedor("nvidia", privado=True)
    assert auditor.bloqueo_proveedor("nvidia") == ""                       # material normal: puede
    for otro in ("groq", "gemini_api", "chatgpt", "qwen"):
        assert auditor.bloqueo_proveedor(otro, interno=True) == ""         # el resto no se toca


def test_revisar_prompt_marca_dato_privado_solo_para_nvidia_con_material_interno():
    p = auditor.revisar_prompt("Resume la cola de tareas", "generar", interno=True, proveedor="nvidia")
    assert any(x.startswith("dato privado") and "NVIDIA Trial" in x for x in p)
    assert not any("NVIDIA" in x for x in auditor.revisar_prompt("Resume la cola", "generar", interno=True,
                                                                  proveedor="groq"))
    assert not any("NVIDIA" in x for x in auditor.revisar_prompt("Resume algo publico", "generar", proveedor="nvidia"))


class Prov:
    def __init__(self, nombre):
        self.nombre = nombre
        self.enviados = []

    def enviar(self, prompt, **k):
        self.enviados.append(prompt)
        return Resultado("OK", texto="respuesta")


def _delegacion(interno):
    from nucleo import trabajo
    d = trabajo.Delegacion.__new__(trabajo.Delegacion)
    d.interno, d.factor, d.exp = interno, 1.0, {"llamadas": []}
    return d


def test_trabajo_no_envia_material_interno_a_nvidia_y_si_a_groq():
    nv, gq = Prov("nvidia"), Prov("groq")
    r = _delegacion(True)._llamar(nv, "analiza la cola", "autor", "generar")
    assert not r.ok and nv.enviados == [] and "NVIDIA Trial" in r.detalle
    assert _delegacion(True)._llamar(gq, "analiza la cola", "autor", "generar").ok and len(gq.enviados) == 1


def test_trabajo_sigue_enviando_material_normal_a_nvidia():
    nv = Prov("nvidia")
    assert _delegacion(False)._llamar(nv, "explica que es un PID", "autor", "general").ok and len(nv.enviados) == 1
