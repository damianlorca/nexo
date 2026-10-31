# -*- coding: utf-8 -*-
"""Tests de nucleo/aprobaciones.py (T077). Todo en tmp_path: nunca memoria/ real."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta

import pytest

from nucleo import aprobaciones as ap

T0 = datetime(2026, 9, 25, 10, 0, 0)


@pytest.fixture(autouse=True)
def almacen(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "ALMACEN", tmp_path / "aprobaciones.json")
    monkeypatch.setattr(ap, "HISTORIAL", tmp_path / "aprobaciones_historial.jsonl")
    monkeypatch.setattr(ap, "CANDADO", tmp_path / ".candado.lock")
    return tmp_path


# ------------------------------------------------------------------ alta

def test_alta_crea_pendiente_persistente():
    s = ap.solicitar("ejecutar comando", "git push origin x", origen="mcp", ahora=T0)

    assert s["id"] == "A0001"
    assert s["estado"] == "pendiente"
    assert s["vence"] == "2026-09-26 10:00:00"
    # persiste: otra lectura desde disco la ve
    assert ap.ver("A0001")["detalle"] == "git push origin x"
    assert json.loads(ap.ALMACEN.read_text(encoding="utf-8"))["siguiente_id"] == 2


def test_alta_repetida_no_duplica():
    a = ap.solicitar("ejecutar comando", "winget install x", ahora=T0)
    b = ap.solicitar("ejecutar comando", "winget install x", ahora=T0 + timedelta(minutes=5))

    assert a["id"] == b["id"]
    assert len(ap.cargar()["solicitudes"]) == 1


def test_alta_distinta_si_cambia_el_detalle():
    a = ap.solicitar("ejecutar comando", "git push", ahora=T0)
    b = ap.solicitar("ejecutar comando", "git push --force", ahora=T0)

    assert a["id"] != b["id"]


def test_huella_no_confunde_accion_y_detalle():
    assert ap.huella("ab", "c") != ap.huella("a", "bc")


def test_alta_tras_denegar_crea_una_nueva():
    a = ap.solicitar("x", "y", ahora=T0)
    ap.denegar(a["id"], ahora=T0)
    b = ap.solicitar("x", "y", ahora=T0)

    assert b["id"] != a["id"] and b["estado"] == "pendiente"


# -------------------------------------------------------------- listar

def test_pendientes_lista_solo_pendientes_vigentes():
    a = ap.solicitar("x", "1", ahora=T0)
    b = ap.solicitar("x", "2", ahora=T0)
    ap.solicitar("x", "3", ahora=T0, ttl=timedelta(minutes=1))
    ap.aprobar(a["id"], ahora=T0)

    ids = [s["id"] for s in ap.pendientes(ahora=T0 + timedelta(minutes=2))]

    assert ids == [b["id"]]


def test_pendientes_no_escribe(almacen):
    ap.solicitar("x", "1", ahora=T0, ttl=timedelta(minutes=1))
    antes = ap.ALMACEN.read_text(encoding="utf-8")

    ap.pendientes(ahora=T0 + timedelta(hours=1))

    assert ap.ALMACEN.read_text(encoding="utf-8") == antes


def test_sin_almacen_la_cola_esta_vacia():
    assert ap.pendientes() == []
    assert ap.historial() == []


# ----------------------------------------------------- aprobar / denegar

def test_aprobar():
    s = ap.solicitar("x", "y", ahora=T0)
    r = ap.aprobar(s["id"], motivo="vale", ahora=T0 + timedelta(minutes=1))

    assert r["estado"] == "aprobada"
    assert r["vence"] == "2026-09-25 12:01:00"  # TTL_APROBADA = 2 h desde que se aprueba
    assert r["eventos"][-1]["motivo"] == "vale"


def test_denegar():
    s = ap.solicitar("x", "y", ahora=T0)
    r = ap.denegar(s["id"], motivo="no", ahora=T0)

    assert r["estado"] == "denegada"


def test_una_decision_no_se_reescribe():
    s = ap.solicitar("x", "y", ahora=T0)
    ap.denegar(s["id"], ahora=T0)

    with pytest.raises(ap.EstadoInvalido):
        ap.aprobar(s["id"], ahora=T0)

    assert ap.ver(s["id"])["estado"] == "denegada"


def test_id_inexistente():
    with pytest.raises(ap.NoEncontrada):
        ap.aprobar("A9999")


# -------------------------------------------------------------- caducar

def test_silencio_cuenta_como_no():
    s = ap.solicitar("x", "y", ahora=T0)

    assert ap.caducar(ahora=T0 + timedelta(hours=23)) == []
    assert ap.caducar(ahora=T0 + timedelta(hours=24)) == [s["id"]]
    assert ap.ver(s["id"])["estado"] == "caducada"


def test_no_se_aprueba_lo_caducado_aunque_no_se_haya_barrido():
    s = ap.solicitar("x", "y", ahora=T0)

    with pytest.raises(ap.EstadoInvalido):
        ap.aprobar(s["id"], ahora=T0 + timedelta(days=2))

    # y queda escrito como caducada, con su evento
    v = ap.ver(s["id"])
    assert v["estado"] == "caducada"
    assert v["eventos"][-1]["tipo"] == "caducada"


def test_aprobada_sin_usar_caduca():
    s = ap.solicitar("x", "y", ahora=T0)
    ap.aprobar(s["id"], ahora=T0)

    assert ap.caducar(ahora=T0 + timedelta(hours=3)) == [s["id"]]

    with pytest.raises(ap.EstadoInvalido):
        ap.consumir(s["id"], "x", "y", ahora=T0 + timedelta(hours=3))


# ------------------------------------------------------------- consumir

def test_consumir_vale_una_sola_vez():
    s = ap.solicitar("ejecutar comando", "git push", ahora=T0)
    ap.aprobar(s["id"], ahora=T0)

    r = ap.consumir(s["id"], "ejecutar comando", "git push", ahora=T0)
    assert r["estado"] == "usada"

    with pytest.raises(ap.EstadoInvalido):
        ap.consumir(s["id"], "ejecutar comando", "git push", ahora=T0)


def test_consumir_exige_la_accion_exacta():
    s = ap.solicitar("ejecutar comando", "git push origin nube/N04", ahora=T0)
    ap.aprobar(s["id"], ahora=T0)

    with pytest.raises(ap.NoCoincide):
        ap.consumir(s["id"], "ejecutar comando", "git push --force origin principal", ahora=T0)

    # el intento fallido no gasta la aprobacion buena, pero queda en el historial
    assert ap.ver(s["id"])["estado"] == "aprobada"
    assert ap.historial()[-1]["tipo"] == "rechazo_consumo"


def test_no_se_consume_lo_pendiente_ni_lo_denegado():
    a = ap.solicitar("x", "1", ahora=T0)
    b = ap.solicitar("x", "2", ahora=T0)
    ap.denegar(b["id"], ahora=T0)

    for s, det in ((a, "1"), (b, "2")):
        with pytest.raises(ap.EstadoInvalido):
            ap.consumir(s["id"], "x", det, ahora=T0)


# ------------------------------------------------------------ historial

def test_historial_registra_todo_el_ciclo():
    s = ap.solicitar("x", "y", origen="mcp", ahora=T0)
    ap.aprobar(s["id"], quien="damian", ahora=T0)
    ap.consumir(s["id"], "x", "y", ahora=T0)

    tipos = [e["tipo"] for e in ap.historial()]
    assert tipos == ["alta", "aprobada", "usada"]
    assert [e["tipo"] for e in ap.ver(s["id"])["eventos"]] == tipos
    assert ap.historial()[1]["quien"] == "damian"
    assert ap.verificar_historial() == (True, None)


def test_historial_detecta_una_linea_editada():
    s = ap.solicitar("x", "y", ahora=T0)
    ap.denegar(s["id"], ahora=T0)
    ap.solicitar("x", "z", ahora=T0)

    lineas = ap.HISTORIAL.read_text(encoding="utf-8").splitlines()
    lineas[1] = lineas[1].replace('"denegada"', '"aprobada"')  # alguien maquilla la decision
    ap.HISTORIAL.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    # la linea editada sigue apuntando bien a la anterior; lo que se rompe es la siguiente
    assert ap.verificar_historial() == (False, 3)


def test_historial_detecta_una_linea_borrada():
    for d in "abc":
        ap.solicitar("x", d, ahora=T0)

    lineas = ap.HISTORIAL.read_text(encoding="utf-8").splitlines()
    del lineas[1]
    ap.HISTORIAL.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    assert ap.verificar_historial() == (False, 2)


# ------------------------------------------------------------------ disco

def test_almacen_roto_no_se_pisa():
    ap.ALMACEN.write_text("{ esto no es json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        ap.solicitar("x", "y")

    assert ap.ALMACEN.read_text(encoding="utf-8") == "{ esto no es json"


def test_escritura_atomica_si_revienta_a_mitad_no_toca_el_bueno(monkeypatch):
    ap.solicitar("x", "1", ahora=T0)
    bueno = ap.ALMACEN.read_text(encoding="utf-8")

    import os

    def falla(*a, **k):
        raise OSError("corte simulado")

    monkeypatch.setattr(os, "replace", falla)

    with pytest.raises(OSError):
        ap.solicitar("x", "2", ahora=T0)

    assert ap.ALMACEN.read_text(encoding="utf-8") == bueno
    assert not list(ap.ALMACEN.parent.glob(".*.tmp"))


def test_concurrencia_no_pierde_solicitudes():
    hilos, por_hilo = 6, 10

    def trabajo(n):
        for i in range(por_hilo):
            ap.solicitar("x", f"{n}-{i}", ahora=T0)

    ts = [threading.Thread(target=trabajo, args=(n,)) for n in range(hilos)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    sols = ap.cargar()["solicitudes"]
    assert len(sols) == hilos * por_hilo
    assert len({s["id"] for s in sols}) == hilos * por_hilo
    assert ap.verificar_historial() == (True, None)


# -------------------------------------------------------------------- CLI

def test_cli(capsys):
    s = ap.solicitar("ejecutar comando", "winget install x")

    assert ap.main(["pendientes"]) == 0
    assert s["id"] in capsys.readouterr().out

    assert ap.main(["aprobar", s["id"], "ok", "desde", "cli"]) == 0
    assert ap.ver(s["id"])["eventos"][-1]["motivo"] == "ok desde cli"

    assert ap.main(["denegar", s["id"]]) == 1  # ya no esta pendiente
    assert ap.main(["verificar"]) == 0
    assert ap.main(["orden-que-no-existe"]) == 1


# ------------------------------------------- plazos con el PC apagado (A0015, 05/10)

def test_aprobada_no_caduca_por_el_tiempo_apagado():
    """A0015: aprobada a las 19:43 (vale 2 h), PC apagado de 20:00 a 22:10: al volver sigue valiendo."""
    s = ap.solicitar("ejecutar comando", "git apply x.patch", ahora=T0)
    ap.aprobar(s["id"], ahora=T0 + timedelta(minutes=2))
    ap.latir(T0 + timedelta(minutes=15))                       # ultimo latido antes de apagar

    vuelta = T0 + timedelta(hours=2, minutes=30)               # ya pasaron las 2 h de reloj
    assert ap.ver(s["id"])["estado"] == "aprobada"
    ap.consumir(s["id"], "ejecutar comando", "git apply x.patch", ahora=vuelta)   # antes del latido: vale
    assert ap.ver(s["id"])["estado"] == "usada"


def test_latido_tras_hueco_alarga_y_lo_apunta():
    s = ap.solicitar("x", "y", ahora=T0)                        # vence T0 + 24 h
    ap.latir(T0)
    hueco = ap.latir(T0 + timedelta(hours=10))
    v = ap.ver(s["id"])

    assert hueco == timedelta(hours=10)
    assert v["vence"] == "2026-09-26 20:00:00"
    assert v["eventos"][-1]["tipo"] == "plazo_ampliado"
    assert ap.verificar_historial() == (True, None)


def test_latidos_seguidos_no_alargan():
    s = ap.solicitar("x", "y", ahora=T0)
    for m in range(0, 10):
        assert ap.latir(T0 + timedelta(minutes=m)) == timedelta(0)
    assert ap.ver(s["id"])["vence"] == "2026-09-26 10:00:00"


def test_encendido_si_caduca():
    s = ap.solicitar("x", "y", ahora=T0)
    ap.aprobar(s["id"], ahora=T0)
    for m in range(0, 125, 1):
        ap.latir(T0 + timedelta(minutes=m))
    assert ap.caducar(T0 + timedelta(minutes=125)) == [s["id"]]


def test_sin_latido_como_antes():
    s = ap.solicitar("x", "y", ahora=T0)
    assert ap.caducar(T0 + timedelta(hours=25)) == [s["id"]]


def test_pendientes_no_esconde_lo_del_hueco_aun_sin_aplicar():
    s = ap.solicitar("x", "y", ahora=T0)
    ap.latir(T0)
    assert [p["id"] for p in ap.pendientes(ahora=T0 + timedelta(hours=30))] == [s["id"]]
