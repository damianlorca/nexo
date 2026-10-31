# -*- coding: utf-8 -*-
"""T837: ninguna tarea se queda para siempre con depende=ia sin turno que la pueda coger."""
from __future__ import annotations

from datetime import datetime

import pytest

from nucleo import avisos, enrutado, revision
from nucleo import tareas as T

AHORA = datetime(2026, 10, 13, 12, 0)


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    mem = tmp_path / "memoria"
    mem.mkdir()
    monkeypatch.setattr(T, "ALMACEN", mem / "tareas.json")
    monkeypatch.setattr(T, "VISTA", mem / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "tareas.md")
    monkeypatch.setattr(T, "CANDADO", mem / ".candado_tareas.lock")
    monkeypatch.setattr(enrutado, "CARPETA", tmp_path / "enrutado")


def _t(cat, **c):
    et = [f"cat:{cat}"] + list(c.pop("etiquetas", []))
    return T.anadir(c.pop("titulo", f"Tarea de {cat}"), depende=c.pop("depende", "ia"), etiquetas=et, **c)


@pytest.mark.parametrize("cat,quien", [("investigacion", "turno"), ("redaccion", "turno"), ("codigo", "nadie"),
                                       ("arquitectura", "nadie"), ("propuesta", "nadie"), ("integracion", "nadie")])
def test_destino_por_categoria(cat, quien):
    d = enrutado.destino(_t(cat))
    assert d["quien"] == quien and d["por_que"]
    if quien == "nadie":
        assert "ningun turno" in d["por_que"]


def test_destino_por_dependencia_estado_y_bloqueo():
    assert enrutado.destino(_t("codigo", depende="claude"))["quien"] == "claude"
    assert enrutado.destino(_t("personal", depende="damian"))["quien"] == "damian"
    a = _t("investigacion")
    b = _t("investigacion", bloqueada_por=a["id"])
    assert enrutado.destino(T.buscar(b["id"]))["quien"] == "nadie" and a["id"] in enrutado.destino(T.buscar(b["id"]))["por_que"]
    hecha = _t("codigo")
    T.actualizar(hecha["id"], estado="hecha")
    assert enrutado.destino(T.buscar(hecha["id"]))["quien"] == "cerrada"
    con_borrador = _t("investigacion", etiquetas=["borrador:revisar_claude"])
    assert enrutado.destino(con_borrador)["quien"] == "revision"


def test_con_tests_dados_dice_si_la_coge_el_implementador(monkeypatch):
    from nucleo import piloto_serie
    t = _t("codigo", etiquetas=["tests:dados"])
    monkeypatch.setattr(piloto_serie, "apta", lambda x: None)
    assert enrutado.destino(t)["quien"] == "implementador"
    monkeypatch.setattr(piloto_serie, "apta", lambda x: "R3 (blindados...)")
    d = enrutado.destino(t)
    assert d["quien"] == "nadie" and "R3" in d["por_que"]


def test_enrutar_pasa_a_claude_con_triaje_y_no_toca_lo_demas():
    cod = _t("codigo")
    arq = _t("arquitectura")
    inv = _t("investigacion")
    piez = _t("codigo", etiquetas=["tests:dados"])
    ya = _t("codigo", etiquetas=["triaje:opus"])
    assert enrutado.enrutar(cod["id"]) == {"tarea": cod["id"], "depende": "claude", "triaje": "triaje:sonnet"}
    assert enrutado.enrutar(arq["id"])["triaje"] == "triaje:opus"
    assert enrutado.enrutar(ya["id"])["triaje"] == "triaje:opus"
    assert enrutado.enrutar(inv["id"]) is None and enrutado.enrutar(piez["id"]) is None
    x = T.buscar(cod["id"])
    assert x["depende"] == "claude" and x["estado"] == "pendiente" and any("T837" in n["texto"] for n in x["notas"])


def test_migrar_simula_y_aplica_con_recuento():
    for c in ("codigo", "codigo", "propuesta", "investigacion"):
        _t(c)
    sim = enrutado.migrar(ahora=AHORA)
    assert sim["atascadas"] == 3 and sim["por_categoria"] == {"codigo": 2, "propuesta": 1} and sim["enrutadas"] == 0
    assert T.cargar()["tareas"][0]["depende"] == "ia"
    r = enrutado.migrar(aplicar=True, ahora=AHORA)
    assert r["enrutadas"] == 3 and r["despues"]["claude"] == 3 and r["despues"]["turno"] == 1
    assert "APLICADO" in open(r["informe"], encoding="utf-8").read()
    assert enrutado.migrar(ahora=AHORA)["atascadas"] == 0


def test_al_aprobar_una_propuesta_se_enruta(monkeypatch):
    p = _t("propuesta", estado="propuesta")
    # la parte de revision que importa: tras aprobarla, _enrutar
    T.actualizar(p["id"], estado="pendiente", etiquetas=["cat:propuesta", "propuesta:aprobada"])
    revision._enrutar(p["id"])
    assert T.buscar(p["id"])["depende"] == "claude"


def test_si_el_enrutado_falla_la_aprobacion_sigue(monkeypatch):
    p = _t("propuesta")

    def roto(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(enrutado, "enrutar", roto)
    revision._enrutar(p["id"])
    assert T.buscar(p["id"])["depende"] == "ia"


def test_aviso_si_lleva_mas_de_7_dias_sin_turno(monkeypatch):
    vieja = _t("codigo")
    T.actualizar(vieja["id"], titulo="vieja")
    datos = T.cargar()
    for t in datos["tareas"]:
        t["actualizada"] = "2026-10-01 10:00:00"
    T.guardar(datos)
    _t("investigacion")
    emitidos = []
    monkeypatch.setattr(avisos, "emitir", lambda *a, **k: emitidos.append((a, k)))
    lista = enrutado.sin_turno(AHORA)
    assert [x["id"] for x in lista] == [vieja["id"]]
    assert enrutado.avisar_sin_turno(AHORA) == 1 and "7 días" in emitidos[0][0][1]
    assert enrutado.sin_turno(datetime(2026, 10, 5, 12, 0)) == []


def test_avisar_nunca_rompe(monkeypatch):
    monkeypatch.setattr(enrutado, "sin_turno", lambda *a, **k: 1 / 0)
    assert enrutado.avisar_sin_turno(AHORA) == 0


def test_lo_personal_va_a_damian():
    p = _t("personal")
    T.actualizar(p["id"], depende="ia")
    assert enrutado.enrutar(p["id"])["depende"] == "damian"


def test_t890_el_aviso_de_sin_turno_sale_una_vez_al_dia_aunque_el_planificador_vuelva_cada_hora(monkeypatch):
    vieja = _t("codigo")
    datos = T.cargar()
    for t in datos["tareas"]:
        t["actualizada"] = "2026-10-01 10:00:00"
    T.guardar(datos)
    horas = [datetime(2026, 10, 13, h, 5) for h in range(8, 20)]
    for h in horas:                                     # 12 vueltas el mismo dia, a mas de 1 h una de otra
        monkeypatch.setattr(avisos.time, "time", lambda h=h: h.timestamp())
        assert enrutado.avisar_sin_turno(h) == 1
    assert len(list(avisos.CARPETA.glob("aviso_*.json"))) == 1
    manana = datetime(2026, 10, 14, 8, 5)
    monkeypatch.setattr(avisos.time, "time", lambda: manana.timestamp())
    enrutado.avisar_sin_turno(manana)
    assert len(list(avisos.CARPETA.glob("aviso_*.json"))) == 2 and vieja
