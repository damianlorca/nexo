# -*- coding: utf-8 -*-
"""Bloque 10 (17/10): `rehacer --todas`, reanudable, que el turno de reels ejecuta sin reels nuevos. Todo con dobles."""
from __future__ import annotations

import json
import urllib.error
from types import SimpleNamespace

import pytest

from extremidades import reels
from nucleo import avisos


@pytest.fixture
def mundo(tmp_path, monkeypatch):
    carpeta = tmp_path / "reels"
    carpeta.mkdir()
    codigos = ["R1", "R2", "R3", "R4"]
    coleccion = tmp_path / "coleccion.json"
    coleccion.write_text(json.dumps({"reels": [{"codigo": c} for c in codigos]}), encoding="utf-8")
    for c in codigos:
        (carpeta / f"{c}.json").write_text(json.dumps({"codigo": c}), encoding="utf-8")
        (carpeta / f"{c}.ficha.json").write_text(json.dumps({"elementos": [{"nombre": "a"}] * 3}), encoding="utf-8")
    monkeypatch.setattr(reels, "CARPETA", carpeta)
    monkeypatch.setattr(reels, "COLECCION", coleccion)
    monkeypatch.setattr(reels, "REHACER", carpeta / "rehacer_todas.json")
    monkeypatch.setattr(reels, "LOTE", carpeta / "lote.json")
    monkeypatch.setattr(reels, "CONFIG", carpeta / "config.json")
    monkeypatch.setattr(avisos, "CARPETA", tmp_path / "avisos")
    return SimpleNamespace(carpeta=carpeta, coleccion=coleccion, tmp=tmp_path)


def _ok(llamadas):
    def fn(codigo, coleccion=None):
        llamadas.append(codigo)
        return {"elementos": [1, 2, 3, 4], "fusion_anterior": {"anadidos": 1}}
    return fn


def _tanda(mundo, **k):
    base = dict(coleccion=mundo.coleccion, ram=lambda: 9000, parada=lambda: None, dormir=lambda s: None)
    return reels.rehacer_todas(**{**base, **k})


def test_cola_rehacer_solo_reels_con_ficha_y_capa_bruta(mundo):
    (mundo.carpeta / "R2.ficha.json").unlink()
    (mundo.carpeta / "R3.json").unlink()
    assert reels.cola_rehacer(mundo.coleccion) == ["R1", "R4"]


def test_rehace_de_una_en_una_es_reanudable_y_avisa_solo_al_final(mundo):
    avisados, llamadas = [], []
    r = _tanda(mundo, maximo=3, rehacer_fn=_ok(llamadas), avisar=avisados.append)
    assert llamadas == ["R1", "R2", "R3"] and r["motivo_fin"] == "tope de 3 por tanda" and r["quedan"] == 1
    assert avisados == []                                    # aun quedan: sin aviso
    estado = json.loads(reels.REHACER.read_text(encoding="utf-8"))
    assert estado["hechos"]["R1"]["antes"] == 3 and estado["hechos"]["R1"]["despues"] == 4
    assert estado["hechos"]["R1"]["fusion"] == 1
    r = _tanda(mundo, maximo=3, rehacer_fn=_ok(llamadas), avisar=avisados.append)
    assert llamadas == ["R1", "R2", "R3", "R4"] and r["quedan"] == 0 and r["motivo_fin"] == "cola vacia"
    assert len(avisados) == 1
    _tanda(mundo, rehacer_fn=_ok(llamadas), avisar=avisados.append)      # ya no hay nada: ni repite ni avisa otra vez
    assert llamadas == ["R1", "R2", "R3", "R4"] and len(avisados) == 1


def test_el_aviso_del_centro_dice_fichas_listas_y_que_no_hay_propuestas(mundo):
    _tanda(mundo, rehacer_fn=_ok([]))
    emitidos = avisos.recientes()
    assert len(emitidos) == 1 and emitidos[0]["titulo"] == "Fichas de reels listas para revisar"
    assert "crear_propuestas sigue en false" in emitidos[0]["cuerpo"]


def test_para_con_parada_poca_ram_hora_limite_cuota_y_saturacion(mundo):
    from datetime import datetime, timedelta
    llamadas = []
    assert _tanda(mundo, rehacer_fn=_ok(llamadas), parada=lambda: "PARADA")["motivo_fin"] == "parada de NEXO"
    assert "poca RAM" in _tanda(mundo, rehacer_fn=_ok(llamadas), ram=lambda: 500)["motivo_fin"]
    assert _tanda(mundo, rehacer_fn=_ok(llamadas), hasta=datetime.now() - timedelta(minutes=1))["motivo_fin"] == "hora limite"
    # Bloque 23 (K0062): no empieza un reel a menos de RESERVA_REEL min de la hora limite (uno tarda hasta 32 min)
    assert _tanda(mundo, rehacer_fn=_ok(llamadas),
                  hasta=datetime.now() + timedelta(minutes=reels.RESERVA_REEL - 1))["motivo_fin"] == "hora limite"
    assert llamadas == []
    assert _tanda(mundo, rehacer_fn=_ok(llamadas), maximo=1,
                  hasta=datetime.now() + timedelta(minutes=reels.RESERVA_REEL + 5))["hechos"]
    llamadas.clear()

    def sin_cuota(c, coleccion=None):
        raise reels.SinCuotaGemini("agotado")
    r = _tanda(mundo, rehacer_fn=sin_cuota)
    assert r["motivo_fin"].startswith("Gemini sin cuota") and not r["fallos"]
    esperas = []

    def saturado(c, coleccion=None):
        raise urllib.error.HTTPError("u", 503, "x", {}, None)
    r = _tanda(mundo, rehacer_fn=saturado, dormir=esperas.append)
    assert r["motivo_fin"] == "saturado 3 veces seguidas" and esperas == [reels.PAUSA_SATURADO] * 2
    assert json.loads(reels.REHACER.read_text(encoding="utf-8"))["fallos"] == {}      # saturar no es culpa del reel


def test_un_reel_roto_suma_fallo_se_aparta_a_los_3_y_no_impide_el_aviso(mundo):
    avisados = []

    def roto(codigo, coleccion=None):
        if codigo == "R2":
            raise ValueError("ficha rota")
        return {"elementos": [1]}
    for _ in range(3):
        _tanda(mundo, rehacer_fn=roto, avisar=avisados.append)
    estado = json.loads(reels.REHACER.read_text(encoding="utf-8"))
    assert estado["fallos"]["R2"]["n"] == 3 and sorted(estado["hechos"]) == ["R1", "R3", "R4"]
    assert reels.cola_rehacer(mundo.coleccion) == [] and len(avisados) == 1


def test_otra_version_de_las_reglas_vuelve_a_empezar(mundo, monkeypatch):
    _tanda(mundo, rehacer_fn=_ok([]), avisar=lambda e: None)
    assert reels.cola_rehacer(mundo.coleccion) == []
    monkeypatch.setattr(reels, "VERSION_REHECHO", "b11")
    assert reels.cola_rehacer(mundo.coleccion) == ["R1", "R2", "R3", "R4"]


def test_el_turno_rehace_cuando_no_hay_reels_nuevos_y_no_crea_propuestas(mundo, monkeypatch):
    from nucleo import reels_huecos, reels_tareas
    monkeypatch.setattr(reels_tareas, "crear", lambda p: pytest.fail("no debe crear propuestas"))
    monkeypatch.setattr(reels_huecos, "registrar", lambda f: pytest.fail("no debe registrar huecos"))
    assert reels.cola_lote(mundo.coleccion, carpeta=mundo.carpeta) == []
    assert reels.turno(simular=True) == {"simulado": True, "pendientes": 0, "rehacer_pendientes": 4}
    ordenes = []

    def correr(args, **k):
        ordenes.append((args, k.get("timeout")))
        return SimpleNamespace(stdout='log\n{"hechos": ["R1"], "fallos": [], "motivo_fin": "tope", "quedan": 3}',
                               returncode=0, stderr="")
    r = reels.turno(correr=correr, minutos=120)
    args, timeout = ordenes[0]
    # Bloque 23 (K0062): la tanda se corta MARGEN_HASTA (6) min antes del tope, como el lote (antes 3: 117)
    assert ".venv-reels" in args[0] and args[3:6] == ["rehacer", "--todas", "--max"] and args[args.index("--minutos") + 1] == "114"
    assert timeout == 7200 and r == {"rehecho": {"hechos": ["R1"], "fallos": [], "motivo_fin": "tope", "quedan": 3},
                                     "rehacer_pendientes": 3}
    assert "error" in reels.turno(correr=lambda a, **k: SimpleNamespace(stdout="", returncode=1, stderr="boom"))


def test_con_reels_nuevos_van_primero_y_rehacer_desactivado_no_hace_nada(mundo, monkeypatch):
    (mundo.carpeta / "R3.ficha.json").unlink()                # R3: reel nuevo sin ficha
    ordenes = []

    def correr(args, **k):
        ordenes.append(args)
        return SimpleNamespace(stdout='{"hechos": [], "fallos": [], "motivo_fin": "cola vacia"}', returncode=0, stderr="")
    reels.turno(correr=correr)
    assert ordenes[0][3] == "lote"
    mundo.carpeta.joinpath("config.json").write_text(json.dumps({"rehacer_todas": False}), encoding="utf-8")
    (mundo.carpeta / "R3.ficha.json").write_text("{}", encoding="utf-8")
    assert reels.turno(simular=True) == {"simulado": True, "pendientes": 0}


def test_el_planificador_cuenta_el_trabajo_de_rehacer(mundo):
    from nucleo import plantillas_turno
    assert plantillas_turno.candidatas({"plantilla": "reels"}) == 4
