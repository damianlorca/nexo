# -*- coding: utf-8 -*-
"""Bloque 8 (17/10): indice de conversaciones web y retomarlas entre tareas (nucleo/conversaciones.py + trabajo).
Sin red ni Chrome."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from nucleo import conversaciones as C
from nucleo import trabajo
from nucleo import tareas as T
from tests.test_ok_absoluto import CIERRE_OK, REV_CAMBIOS, REV_OK, V0, Api, Web, _auditoria, _correr, cola  # noqa: F401

URL = "https://chatgpt.test/c/compartida"
AHORA = datetime(2026, 10, 17, 12, 0, 0)


def _ts(dias=0, horas=0) -> str:
    return (AHORA - timedelta(days=dias, hours=horas)).strftime("%Y-%m-%d %H:%M:%S")


def _tarea(tid, etiquetas, convs):
    return {"id": tid, "titulo": f"Tarea {tid}", "etiquetas": etiquetas, "conversaciones": convs}


def _conv(url=URL, usos=2, dias=1, estado="ok"):
    return {"url": url, "usos": usos, "estado": estado, "actualizada": _ts(dias=dias)}


def _buscar(tarea, tareas, proveedor="chatgpt", rol="autor"):
    return C.buscar(tarea, proveedor, rol, tareas=tareas, ahora=AHORA)


FUENTE = _tarea("T1", ["cat:investigacion", "tema:orquestacion", "epica:T664"], {"chatgpt:autor": _conv()})
NUEVA = _tarea("T2", ["cat:investigacion", "tema:orquestacion", "epica:T664"], {})


# ------------------------------------------------------------------ indice
def test_indice_una_fila_por_url_con_tareas_mensajes_y_fecha():
    otra = _tarea("T3", ["tema:orquestacion", "epica:T664"], {"chatgpt:autor": _conv(usos=3, dias=0)})
    [fila] = C.indice([FUENTE, otra])
    assert fila["tareas"] == ["T1", "T3"] and fila["mensajes"] == 5
    assert (fila["proveedor"], fila["rol"], fila["tema"], fila["epica"], fila["url"]) == \
        ("chatgpt", "autor", "orquestacion", "T664", URL)
    assert fila["fecha"] == _ts(dias=0)


def test_indice_no_ofrece_estropeadas_ni_las_url_estropeadas_por_otra_tarea():
    rota = _tarea("T3", ["tema:orquestacion", "epica:T664"], {"chatgpt:autor": _conv(estado="estropeada")})
    assert C.indice([FUENTE, rota]) == []
    assert C.indice([_tarea("T4", ["tema:x"], {"chatgpt:autor": {"estado": "ok"}})]) == []     # sin url


# ------------------------------------------------------------------ buscar
def test_retoma_la_del_mismo_proveedor_rol_tema_y_epica():
    assert _buscar(NUEVA, [FUENTE, NUEVA])["url"] == URL


@pytest.mark.parametrize("cambia,motivo", [
    (dict(proveedor="gemini"), "otro proveedor"),
    (dict(rol="revisor"), "los revisores nunca reutilizan"),
])
def test_no_cruza_proveedor_ni_rol(cambia, motivo):
    assert _buscar(NUEVA, [FUENTE, NUEVA], **cambia) is None, motivo


def test_revisor_nunca_aunque_haya_una_conversacion_de_revisor_con_su_tema():
    revisora = _tarea("T1", ["tema:orquestacion", "epica:T664"], {"chatgpt:revisor": _conv()})
    assert _buscar(NUEVA, [revisora, NUEVA], rol="revisor") is None
    assert _buscar(NUEVA, [revisora, NUEVA], rol="autor") is None     # y una de revisor no sirve de autor


def test_otro_tema_otra_epica_o_sin_tema_no_casan():
    assert _buscar(_tarea("T2", ["tema:memoria_contexto", "epica:T664"], {}), [FUENTE]) is None
    assert _buscar(_tarea("T2", ["tema:orquestacion", "epica:T690"], {}), [FUENTE]) is None
    assert _buscar(_tarea("T2", ["tema:orquestacion"], {}), [FUENTE]) is None      # ella no tiene epica, la otra si
    assert _buscar(_tarea("T2", ["cat:investigacion"], {}), [FUENTE]) is None      # sin tema


def test_sin_epica_casa_con_otra_sin_epica():
    f = _tarea("T1", ["tema:orquestacion"], {"chatgpt:autor": _conv()})
    assert _buscar(_tarea("T2", ["tema:orquestacion"], {}), [f])["url"] == URL


def test_limite_de_edad_7_dias():
    assert _buscar(NUEVA, [_tarea("T1", FUENTE["etiquetas"], {"chatgpt:autor": _conv(dias=6)})]) is not None
    assert _buscar(NUEVA, [_tarea("T1", FUENTE["etiquetas"], {"chatgpt:autor": _conv(dias=7)})]) is None


def test_limite_de_mensajes_12():
    assert _buscar(NUEVA, [_tarea("T1", FUENTE["etiquetas"], {"chatgpt:autor": _conv(usos=11)})]) is not None
    assert _buscar(NUEVA, [_tarea("T1", FUENTE["etiquetas"], {"chatgpt:autor": _conv(usos=12)})]) is None
    # los mensajes cuentan en todas las tareas que comparten la URL
    a = _tarea("T1", FUENTE["etiquetas"], {"chatgpt:autor": _conv(usos=7)})
    b = _tarea("T3", FUENTE["etiquetas"], {"chatgpt:autor": _conv(usos=5)})
    assert _buscar(NUEVA, [a, b, NUEVA]) is None


def test_la_propia_conversacion_no_se_ofrece_como_ajena():
    propia = _tarea("T2", FUENTE["etiquetas"], {"chatgpt:autor": _conv()})
    assert _buscar(propia, [propia]) is None


def test_entre_varias_gana_la_mas_reciente():
    vieja = _tarea("T1", FUENTE["etiquetas"], {"chatgpt:autor": _conv(url="https://chatgpt.test/c/vieja", dias=5)})
    reciente = _tarea("T3", FUENTE["etiquetas"], {"chatgpt:autor": _conv(url="https://chatgpt.test/c/reciente", dias=1)})
    assert _buscar(NUEVA, [vieja, reciente, NUEVA])["url"] == "https://chatgpt.test/c/reciente"


# ------------------------------------------------------------------ integracion en la delegacion
@pytest.fixture
def con_tema(cola):    # noqa: F811
    """La tarea de la fixture `cola` pasa a tener tema+epica; otra tarea (hecha) tiene ya la conversacion."""
    T.actualizar(cola["id"], etiquetas=["cat:investigacion", "tema:orquestacion", "epica:T664"])
    previa = T.anadir("Trabajo previo del mismo tema", depende="ia",
                      etiquetas=["cat:arquitectura", "tema:orquestacion", "epica:T664"])
    T.fijar_conversacion(previa["id"], "chatgpt:autor", url="https://chatgpt.test/c/previa", tema="otro-hash",
                         estado="ok")
    T.actualizar(previa["id"], estado="hecha")
    return cola, previa


def test_tarea_sin_conversacion_propia_retoma_la_de_otra_del_mismo_tema(con_tema, monkeypatch):
    t, previa = con_tema
    autor = Web("chatgpt", V0, CIERRE_OK)
    [fila] = _correr(monkeypatch, autor, [Api("gemini_api", REV_OK, REV_OK)])
    assert [ll["url"] for ll in autor.llamadas] == ["https://chatgpt.test/c/previa"] * 2
    conv = _auditoria()["expediente"]["conversacion"]["chatgpt:autor"]
    assert conv["retomada"] and conv["indice"]["tareas"] == [previa["id"]]
    assert fila["auditoria"] == "APROBADA", _auditoria()["puntos"]
    guardada = T.conversacion(t["id"], "chatgpt:autor")
    assert guardada["url"] == "https://chatgpt.test/c/previa" and guardada["retomada_de"] == [previa["id"]]


def test_sin_tema_en_comun_abre_chat_nuevo(cola, monkeypatch):    # noqa: F811
    otra = T.anadir("Otra cosa", depende="ia", etiquetas=["cat:arquitectura", "tema:interfaz_app_voz"])
    T.fijar_conversacion(otra["id"], "chatgpt:autor", url="https://chatgpt.test/c/previa", tema="x", estado="ok")
    T.actualizar(otra["id"], estado="hecha")
    T.actualizar(cola["id"], etiquetas=["cat:investigacion", "tema:orquestacion"])
    autor = Web("chatgpt", V0, CIERRE_OK)
    _correr(monkeypatch, autor, [Api("gemini_api", REV_OK)])
    assert autor.llamadas[0]["url"] is None


def test_si_retomar_falla_se_marca_estropeada_y_se_abre_otra(con_tema, monkeypatch):
    t, previa = con_tema
    autor = Web("chatgpt", V0, CIERRE_OK, falla_url="https://chatgpt.test/c/previa")
    [fila] = _correr(monkeypatch, autor, [Api("gemini_api", REV_OK)])
    assert fila["auditoria"] == "APROBADA", _auditoria()["puntos"]
    conv = _auditoria()["expediente"]["conversacion"]["chatgpt:autor"]
    assert conv["estropeadas"][0]["url"] == "https://chatgpt.test/c/previa"
    assert T.conversacion(t["id"], "chatgpt:autor")["url"] != "https://chatgpt.test/c/previa"
    # la marca vive donde esta la URL: la siguiente tarea del tema ya no se la encuentra
    assert T.conversacion(previa["id"], "chatgpt:autor")["estado"] == "estropeada"
    siguiente = C.buscar(T.anadir("Siguiente", etiquetas=["tema:orquestacion", "epica:T664"]), "chatgpt", "autor")
    assert siguiente["url"] == T.conversacion(t["id"], "chatgpt:autor")["url"]      # la nueva si; la rota, no


def test_los_revisores_no_reutilizan_conversaciones_de_otras_tareas(con_tema, monkeypatch):
    t, previa = con_tema
    T.fijar_conversacion(previa["id"], "gemini:revisor", url="https://gemini.test/app/previa", tema="otro", estado="ok")
    autor = Web("chatgpt", V0, CIERRE_OK)
    revisor = Web("gemini", REV_OK, REV_OK)
    _correr(monkeypatch, autor, [revisor])
    assert revisor.llamadas and all(ll["url"] != "https://gemini.test/app/previa" for ll in revisor.llamadas)
    assert revisor.llamadas[0]["url"] is None
