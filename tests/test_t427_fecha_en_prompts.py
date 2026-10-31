# -*- coding: utf-8 -*-
"""T427: los prompts de delegacion (trabajo, tribunal, chat de tarea) llevan la fecha y hora de Madrid."""
from __future__ import annotations

from datetime import date, datetime, timezone

from nucleo import ahora, chat_tarea, tribunal


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_madrid_verano_e_invierno(monkeypatch):
    monkeypatch.setattr(ahora, "madrid", ahora.madrid)      # la funcion real, con o sin tzdata
    assert ahora.madrid(utc(2026, 7, 1, 10, 0)).strftime("%H:%M") == "12:00"       # CEST (+2)
    assert ahora.madrid(utc(2026, 1, 15, 10, 0)).strftime("%H:%M") == "11:00"      # CET (+1)


def test_regla_europea_sin_tzdata_cambia_el_ultimo_domingo(monkeypatch):
    import builtins
    real = builtins.__import__

    def sin_zoneinfo(nombre, *a, **k):
        if nombre == "zoneinfo":
            raise ImportError("sin tzdata")
        return real(nombre, *a, **k)
    monkeypatch.setattr(builtins, "__import__", sin_zoneinfo)
    assert ahora.madrid(utc(2026, 10, 25, 0, 59)).strftime("%H:%M") == "02:59"     # aun verano
    assert ahora.madrid(utc(2026, 10, 25, 1, 0)).strftime("%H:%M") == "02:00"      # ya invierno
    assert ahora.madrid(utc(2026, 3, 29, 0, 59)).strftime("%H:%M") == "01:59"      # aun invierno
    assert ahora.madrid(utc(2026, 3, 29, 1, 0)).strftime("%H:%M") == "03:00"       # ya verano


def test_linea_y_no_se_repite():
    ya = utc(2026, 10, 18, 12, 5)                       # domingo
    assert ahora.linea(ya) == "Fecha y hora actuales (Madrid): domingo 18/10/2026 14:05."
    una = ahora.con_fecha("hola", ya)
    assert una.startswith(ahora.MARCA) and una.endswith("\nhola")
    assert ahora.con_fecha(una, ya) == una


def test_prompt_del_tribunal_lleva_la_fecha():
    e = {"textos_propuestas": [], "es_inv": False, "tipo": "general", "texto": "borrador", "titulo": "t"}
    p = tribunal.prompt(e, "primera")
    assert p.startswith(ahora.MARCA) and "BORRADOR:" in p


def test_prompts_del_chat_de_tarea_llevan_la_fecha():
    t = {"id": "T001", "titulo": "x", "estado": "pendiente"}
    assert chat_tarea._prompt_interpretar("hola", t, date(2026, 10, 18)).startswith(ahora.MARCA)
    assert chat_tarea._prompt_duda(t, "que tal").startswith(ahora.MARCA)


def test_el_envio_de_trabajo_antepone_la_fecha(monkeypatch):
    from nucleo import trabajo

    class Prov:
        nombre = "gemini_api"
        enviados: list[str] = []

        def enviar(self, prompt, **k):
            Prov.enviados.append(prompt)
            from proveedores import Resultado
            return Resultado("OK", texto="respuesta")
    d = trabajo.Delegacion.__new__(trabajo.Delegacion)
    d.interno, d.factor, d.exp = False, 1.0, {"llamadas": []}
    monkeypatch.setattr(trabajo.auditor, "revisar_prompt", lambda *a, **k: [])
    d._llamar(Prov(), "pregunta de prueba", "autor", "general")
    assert Prov.enviados[0].startswith(ahora.MARCA) and Prov.enviados[0].endswith("pregunta de prueba")
