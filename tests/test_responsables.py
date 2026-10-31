# -*- coding: utf-8 -*-
"""Guardia de responsables (Damian, 05/10): a Damian solo le queda lo que depende de sus datos, su dinero o sus
cuentas, sus gustos o decisiones suyas, o su presencia fisica. Lo demas pasa a Claude, en cualquier camino
(alta directa, orden, triaje, reclasificacion), y el repaso periodico avisa si alguna se cuela."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from nucleo import ordenes, planificador, responsables as R, tareas as T


@pytest.fixture
def cola(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "v" / "tareas.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".lock")


@pytest.mark.parametrize("titulo,etiquetas,motivo", [
    ("Decidir las fusiones del informe de parecidas", [], None),            # T435: trabajo de Claude/tribunal
    ("Integrar Alexa con el brief", [], None),
    ("Cita con el medico", [], "datos"),
    ("Pagar la matricula", [], "dinero"),
    ("Revocar el token del bot en BotFather", [], "dinero"),
    ("Radar de viajes", ["cat:personal"], "datos"),
    ("WAVER", ["suyo:gustos"], "gustos"),
    ("Prueba real del brief con Damián delante", [], "presencia"),
])
def test_motivo(titulo, etiquetas, motivo):
    assert R.motivo({"titulo": titulo, "etiquetas": etiquetas}) == motivo


def test_alta_sin_razon_pasa_a_claude_con_nota(cola):
    t = T.anadir("Decidir las fusiones del informe", depende="damian", etiquetas=["prov:damian", "triaje:damian"])
    assert t["depende"] == "claude" and t["etiquetas"] == ["prov:claude", "triaje:sonnet"]
    assert R.NOTA in t["notas"][-1]["texto"] and "depende=damian" in t["notas"][-1]["texto"]
    assert T.buscar(t["id"])["depende"] == "claude"


def test_alta_con_razon_se_queda_con_damian(cola):
    t = T.anadir("Firmar los papeles de la beca", depende="damian", etiquetas=["prov:damian"])
    assert t["depende"] == "damian" and t["etiquetas"] == ["prov:damian"] and not t["notas"]


def test_solo_etiqueta_triaje_damian_tambien_se_corrige(cola):
    t = T.anadir("Revisar el log del vigia", depende="ia", etiquetas=["triaje:damian"])
    assert t["depende"] == "ia" and t["etiquetas"] == ["triaje:sonnet"]


def test_reclasificar_a_damian_sin_razon_no_cuela(cola):
    t = T.anadir("Arreglar el oyente del altavoz", depende="ia")
    T.actualizar(t["id"], depende="damian")
    assert T.buscar(t["id"])["depende"] == "claude"
    T.actualizar(t["id"], depende="damian", etiquetas=["suyo:presencia"])
    assert T.buscar(t["id"])["depende"] == "damian"


def test_cambiar_solo_el_estado_no_toca_el_responsable(cola, monkeypatch):
    t = T.anadir("Firmar", depende="damian")
    monkeypatch.setattr(R, "PALABRAS", {})          # aunque cambiaran las reglas, un cambio de estado no reasigna
    T.actualizar(t["id"], estado="en_curso")
    assert T.buscar(t["id"])["depende"] == "damian"


def test_orden_personal_se_queda_y_orden_tecnica_no_va_a_damian(cola, monkeypatch):
    monkeypatch.setattr(ordenes.K, "clasificar", lambda t: "personal")
    r = ordenes.procesar("recordarme la cita del dentista", canal="web", trabajar=False)
    assert T.buscar(r["tarea"])["depende"] == "damian"      # cat:personal = sus datos
    monkeypatch.setattr(ordenes.K, "clasificar", lambda t: "codigo")
    r = ordenes.procesar("arreglar el test del planificador", canal="web", trabajar=False)
    assert T.buscar(r["tarea"])["depende"] != "damian"


def test_triaje_que_pone_prov_damian_sin_categoria_personal_se_corrige(cola):
    t = T.anadir("Comparar proveedores de embeddings", depende="ia")
    T.actualizar(t["id"], etiquetas=["cat:investigacion", "prov:damian"])   # lo que haria un triaje equivocado
    assert T.buscar(t["id"])["etiquetas"] == ["cat:investigacion", "prov:claude"]


def test_repaso_encuentra_las_colocadas_a_mano_y_es_solo_lectura(cola):
    ok = T.anadir("Firmar", depende="damian")
    mala = T.anadir("Revisar logs", depende="ia")
    datos = T.cargar()
    for t in datos["tareas"]:
        if t["id"] == mala["id"]:
            t["depende"] = "damian"            # editado a mano en el JSON, sin pasar por la guardia
    T.guardar(datos)
    r = R.repaso()
    assert [x["id"] for x in r["mal_asignadas"]] == [mala["id"]]
    assert T.buscar(mala["id"])["depende"] == "damian" and R.ultimo_repaso()["mal_asignadas"] == r["mal_asignadas"]
    assert not R.es_suya(T.buscar(mala["id"])) and R.es_suya(T.buscar(ok["id"]))


def test_repaso_si_toca_una_vez_por_hora(cola):
    t0 = datetime(2026, 10, 5, 12, 0)
    assert R.repaso_si_toca(t0) is not None
    assert R.repaso_si_toca(t0 + timedelta(minutes=30)) is None
    assert R.repaso_si_toca(t0 + timedelta(minutes=61)) is not None


def test_el_planificador_lanza_el_repaso(cola, tmp_path, monkeypatch):
    monkeypatch.setattr(planificador, "ESTADO", tmp_path / "plan.json")
    monkeypatch.setattr(planificador, "EN_MARCHA", tmp_path / "en_marcha.json")
    monkeypatch.setattr(planificador, "CANDADO", tmp_path / ".plan.lock")
    monkeypatch.setattr(planificador.turnos, "cargar", lambda: {"turnos": []})
    hecho = planificador.tick(datetime(2026, 10, 5, 12, 0), lanzar=lambda e: 0)
    assert hecho["responsables"] is not None and R.ultimo_repaso() is not None
