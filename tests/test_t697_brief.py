# -*- coding: utf-8 -*-
"""T697: el texto del brief hablado (nucleo/brief.py). Sin red: Open-Meteo y el iCal son dobles."""
from __future__ import annotations

import json
import logging
import urllib.error
from datetime import date, datetime

from nucleo import brief

AHORA = datetime(2026, 10, 5, 8, 30)   # lunes
URL_SECRETA = "https://calendar.google.com/calendar/ical/x/private-SECRETO123/basic.ics"


def _tiempo_json(lluvia_hoy=(), lluvia_manana=()):
    horas, mm, prob = [], [], []
    for d in ("2026-10-05", "2026-10-06"):
        for h in range(24):
            horas.append(f"{d}T{h:02d}:00")
            llueve = h in (lluvia_hoy if d.endswith("05") else lluvia_manana)
            mm.append(1.0 if llueve else 0.0)
            prob.append(80 if llueve else 5)
    return json.dumps({
        "daily": {"time": ["2026-10-05", "2026-10-06"], "weather_code": [3, 61],
                  "temperature_2m_max": [26.4, 27.0], "temperature_2m_min": [18.6, 20.0],
                  "precipitation_probability_max": [5, 80]},
        "hourly": {"time": horas, "precipitation": mm, "precipitation_probability": prob}}).encode()


ICAL = "\r\n".join([
    "BEGIN:VCALENDAR",
    "BEGIN:VEVENT", "UID:a", "DTSTART:20261005T080000Z", "DTEND:20261005T090000Z", "SUMMARY:Dentista\\, revisión", "END:VEVENT",
    "BEGIN:VEVENT", "UID:b", "DTSTART;VALUE=DATE:20261008", "DTEND;VALUE=DATE:20261009", "SUMMARY:Video", "END:VEVENT",
    # semanal los lunes y miercoles desde septiembre, con una excepcion movida y otra quitada
    "BEGIN:VEVENT", "UID:c", "DTSTART;TZID=Europe/Madrid:20260907T190000", "RRULE:FREQ=WEEKLY;BYDAY=MO,WE",
    "EXDATE;TZID=Europe/Madrid:20261007T190000", "SUMMARY:Gimnasio", "END:VEVENT",
    "BEGIN:VEVENT", "UID:c", "RECURRENCE-ID;TZID=Europe/Madrid:20261005T190000", "DTSTART;TZID=Europe/Madrid:20261005T200000",
    "SUMMARY:Gimnasio (tarde)", "END:VEVENT",
    "BEGIN:VEVENT", "UID:d", "DTSTART:20261006T100000", "STATUS:CANCELLED", "SUMMARY:Cancelado", "END:VEVENT",
    "BEGIN:VEVENT", "UID:e", "DTSTART:20250101T100000", "RRULE:FREQ=DAILY;COUNT=3", "SUMMARY:Viejo", "END:VEVENT",
    "BEGIN:VEVENT", "UID:f", "DTSTART:20261009T120000", "SUMMARY:Comida larga con un título que sigue en la",
    "  línea siguiente", "END:VEVENT",
    "END:VCALENDAR"])


def test_hora():
    assert brief.frase_hora(AHORA) == "Son las 8:30 del lunes 5 de octubre."


def test_tiempo_con_tramos_de_lluvia():
    texto = brief.frase_tiempo(json.loads(_tiempo_json(lluvia_hoy=(5, 14, 15, 16), lluvia_manana=(9, 10))), AHORA)
    assert "Hoy, nublado, entre 19 y 26 grados; puede llover de 14 a 17." in texto   # las 5 ya pasaron
    assert "Mañana, con lluvia débil, entre 20 y 27 grados; puede llover de 9 a 11." in texto


def test_tiempo_sin_lluvia_y_con_fallo():
    assert "llover" not in brief.tiempo(AHORA, obtener=lambda url: _tiempo_json())
    assert "api.open-meteo.com" in brief.url_tiempo(1, 2)

    def caido(url):
        raise urllib.error.URLError("sin red")
    assert brief.tiempo(AHORA, obtener=caido) == "No he podido mirar el tiempo."


def test_ical_rango_recurrencias_excepciones_y_cancelados():
    inicio = datetime(2026, 10, 5)
    eventos = brief.eventos_en(ICAL, inicio, datetime(2026, 10, 12))
    resumenes = [(x, r) for x, r in eventos]
    textos = [r for _, r in resumenes]
    assert "Dentista, revisión" in textos
    assert (date(2026, 10, 8), "Video") in resumenes
    assert (datetime(2026, 10, 5, 20, 0), "Gimnasio (tarde)") in resumenes
    assert (datetime(2026, 10, 5, 19, 0), "Gimnasio") not in resumenes      # movida por RECURRENCE-ID
    assert (datetime(2026, 10, 7, 19, 0), "Gimnasio") not in resumenes      # EXDATE
    assert (datetime(2026, 10, 12, 19, 0), "Gimnasio") not in resumenes     # fuera del rango
    assert "Cancelado" not in textos and "Viejo" not in textos
    assert "Comida larga con un título que sigue en la línea siguiente" in textos
    assert [x for x, _ in eventos] == sorted([x for x, _ in eventos],
                                             key=lambda x: x if isinstance(x, datetime) else datetime.combine(x, datetime.min.time()))


def test_rrule_mensual_por_ordinal_y_count_until():
    ev = {"inicio": datetime(2026, 1, 13, 9), "rrule": {"FREQ": "MONTHLY", "BYDAY": "2TU"}, "exdates": set(), "fin": None}
    assert brief.ocurrencias(ev, datetime(2026, 10, 1), datetime(2026, 11, 1)) == [datetime(2026, 10, 13, 9)]
    ev = {"inicio": datetime(2026, 10, 1, 9), "rrule": {"FREQ": "DAILY", "UNTIL": "20261006T000000Z"},
          "exdates": set(), "fin": None}
    assert len(brief.ocurrencias(ev, datetime(2026, 10, 5), datetime(2026, 10, 12))) == 1


def test_calendario_frase_y_url_nunca_en_logs(monkeypatch, caplog):
    monkeypatch.setattr(brief, "valor", lambda ruta, defecto=None: URL_SECRETA if ruta == "calendario.ical_url" else defecto)
    texto = brief.calendario(AHORA, obtener=lambda url: ICAL.encode())
    assert texto.startswith("Hoy en tu calendario:")
    assert "Esta semana:" in texto and "el jueves, todo el día, Video" in texto

    def caido(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    with caplog.at_level(logging.DEBUG):
        assert brief.calendario(AHORA, obtener=caido) == "No he podido leer el calendario."
    assert "SECRETO123" not in caplog.text and "HTTP 404" in caplog.text


def test_calendario_sin_url_se_salta(monkeypatch):
    monkeypatch.setattr(brief, "valor", lambda ruta, defecto=None: defecto)
    assert brief.calendario(AHORA, obtener=lambda url: 1 / 0) == ""


def _t(id_, titulo, estado, depende="ia", cerrada=None, imp=3, etiquetas=()):
    return {"id": id_, "titulo": titulo, "estado": estado, "depende": depende, "cerrada": cerrada,
            "importancia": imp, "urgencia": 3, "etiquetas": list(etiquetas), "limite": None, "detalle": ""}


def test_nexo_sin_tareas_personales_ni_privados():
    tareas = [
        _t("T1", "[Propuesta de T059] Tribunal de día (de T261, ADOPTAR)", "hecha", cerrada="2026-10-05 01:00:00", imp=5),
        _t("T2", "Beca secreta", "hecha", cerrada="2026-10-05 02:00:00", imp=5, etiquetas=["cat:personal"]),
        _t("T3", "Algo de hace días", "hecha", cerrada="2026-09-01 02:00:00"),
        _t("T4", "Revisar C:\\Users\\damia\\x.txt", "pendiente", depende="damian", etiquetas=["suyo:gustos"]),
        _t("T5", "Mi médico", "pendiente", depende="damian", etiquetas=["cat:personal"]),
    ]
    texto = brief.frase_nexo(AHORA, tareas=tareas, decisiones=2)
    assert "ha cerrado 1 tarea. Lo más importante: Tribunal de día." in texto
    assert "Tienes 2 decisiones esperando" in texto
    assert "Te tocan 2 tareas; la primera: Revisar [privado]" in texto      # la personal cuenta, pero sin titulo
    for privado in ("Beca", "médico", "damia", "Propuesta", "T059", "hace días"):
        assert privado not in texto


def test_componer_orden_y_tope(monkeypatch):
    monkeypatch.setattr(brief, "valor", lambda ruta, defecto=None: URL_SECRETA if ruta == "calendario.ical_url" else defecto)
    monkeypatch.setattr(brief, "nexo", lambda ahora: "Resumen de NEXO.")

    def obtener(url):
        return _tiempo_json() if "open-meteo" in url else ICAL.encode()
    texto = brief.componer(AHORA, obtener=obtener)
    i = [texto.index(x) for x in ("Son las", "Hoy, nublado", "Hoy en tu calendario", "Resumen de NEXO")]
    assert i == sorted(i)
    assert "SECRETO123" not in texto
    largo = brief.recortar("Una frase. " * 300)
    assert len(largo.split()) <= brief.MAX_PALABRAS and largo.endswith(".")


def test_lluvia_debil_sin_horas_sobre_el_umbral_dice_la_franja_probable():
    d = json.loads(_tiempo_json())
    d["daily"]["weather_code"][1] = 61                       # manana "con lluvia debil"
    for i, h in enumerate(d["hourly"]["time"]):
        if h.startswith(d["daily"]["time"][1]):
            hora = int(h[11:13])
            d["hourly"]["precipitation_probability"][i] = {15: 30, 16: 40, 17: 35, 9: 10}.get(hora, 0)
            d["hourly"]["precipitation"][i] = 0.1 if hora in (15, 16, 17) else 0
    texto = brief.frase_tiempo(d, AHORA)
    assert "Mañana, con lluvia débil" in texto and "posible lluvia débil hacia las 15-18 h" in texto
    assert "puede llover" not in texto


def test_franja_probable_sin_nada_es_none():
    horas = [datetime(2026, 10, 6, h) for h in range(24)]
    assert brief.franja_probable(horas, [0] * 24, [0] * 24, date(2026, 10, 6)) is None


def test_lo_mas_importante_es_trabajo_nuevo_con_resumen_humano():
    viejo = "2026-09-11 10:00:00"
    tareas = [
        {**_t("T1", "Sistema de tareas por prioridad", "hecha", cerrada="2026-10-05 01:00:00", imp=5), "creada": viejo,
         "notas": [{"cuando": "2026-10-05 01:00:00", "texto": "[verificado] prueba_tareas.py"}]},
        _t("T2", "Revisar borrador de T133: auditar", "hecha", cerrada="2026-10-05 01:00:00", imp=5),
        {**_t("T3", "Integrar: modelos de NVIDIA", "hecha", cerrada="2026-10-05 01:00:00", imp=5),
         "notas": [{"cuando": "2026-10-05 01:00:00", "texto": "Integracion ya hecha antes de esta tarea"}]},
        {**_t("T4", "Interruptor por proveedor en la web", "hecha", cerrada="2026-10-05 02:00:00", imp=4),
         "creada": "2026-10-01 10:00:00", "resumen_humano": "Ahora puedes apagar un proveedor desde la web con un botón.",
         "notas": [{"cuando": "2026-10-05 02:00:00", "texto": "Commit a85a238 con tests"}]},
    ]
    texto = brief.frase_nexo(AHORA, tareas=tareas, decisiones=0)
    assert "ha cerrado 4 tareas, 1 de trabajo nuevo." in texto
    assert "Lo más importante: Interruptor por proveedor en la web: ahora puedes apagar un proveedor" in texto
    for fuera in ("Sistema de tareas", "borrador", "NVIDIA"):
        assert fuera not in texto


def test_te_toca_solo_lo_suyo_y_en_claro():
    tareas = [
        _t("T1", "Decidir las fusiones del informe de parecidas", "pendiente", depende="damian"),   # no es suya
        {**_t("T2", "WAVER", "pendiente", depende="damian", etiquetas=["suyo:gustos"]),
         "resumen_humano": "Decidir qué haces con tu proyecto WAVER."},
        _t("T3", "Opcional: revocar el token del bot de Telegram en BotFather", "pendiente", depende="damian"),
    ]
    texto = brief.frase_nexo(AHORA, tareas=tareas, decisiones=0)
    assert "Te tocan 2 tareas" in texto and "fusiones" not in texto
    assert "Decidir qué haces con tu proyecto WAVER" in texto and "Opcional" not in texto
