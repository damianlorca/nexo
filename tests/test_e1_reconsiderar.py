# -*- coding: utf-8 -*-
"""E1 (epica T686, 05/10): los descartes por borrador y los candidatos perdidos del vigia se reconsideran con el
tribunal por lotes (uno por tarea origen / lote), como mucho MAX_VIVOS a la vez y sin pasar del freno F0.
Dobles: sin red (proveedores falsos del tribunal), tareas y tribunal en tmp_path."""
from __future__ import annotations

import json

import pytest

from nucleo import auditoria_cierres as AC
from nucleo import descartes, enfriamiento, freno, reconsiderar, revision, tribunal
from nucleo import tareas as T
from tests.test_t667_tribunal import Falso


def veredicto(props, glob="APROBAR"):
    lin = [f"GLOBAL: {glob} | motivo del global bastante claro"]
    lin += [f"P{i}: {v} | motivo de la fila {i}" for i, v in enumerate(props, 1)]
    return "\n".join(lin + ["FALLOS:", "- ninguno", "FIN_DICTAMEN"])


@pytest.fixture
def entorno(tmp_path, monkeypatch, reloj_falso):
    monkeypatch.setattr(enfriamiento, "ALMACEN", tmp_path / "enfriamiento.json")
    monkeypatch.setattr(revision, "BORRADORES", tmp_path / "borradores")
    reloj_falso(tribunal)
    guion: dict = {}
    llamadas: list = []
    monkeypatch.setattr(tribunal, "_proveedor", lambda c: Falso(guion, c.id, llamadas))
    monkeypatch.setattr(tribunal, "_verificar_item", lambda texto: {"confirmado": None, "detalle": "sin url"})
    return {"guion": guion, "llamadas": llamadas}


def descartadas(origen_titulo="Script de banco puntual", n=2):
    o = T.anadir(origen_titulo, estado="descartada")
    ps = [T.anadir(f"[Propuesta de {o['id']}] Idea {i}", detalle=f"QUE: idea {i} | DONDE: banco", estado="descartada",
                   etiquetas=["cat:propuesta", f"tarea_origen:{o['id']}"]) for i in range(n)]
    return o, ps


def informe(filas_p, filas_v=()):
    AC.INFORMES.mkdir(parents=True, exist_ok=True)
    (AC.INFORMES / "auditoria_cierres_20261005_0033.json").write_text(json.dumps(
        {"propuestas_descartadas": filas_p, "candidatos_lotes": list(filas_v)}), encoding="utf-8")


def fila(p, o, propuesta="reabrir"):
    return {"id": p["id"], "titulo": p["titulo"], "origen": o["id"], "motivo": "borrador malo", "propuesta": propuesta}


def test_lotes_por_tarea_origen_y_del_vigia_sin_repetir(entorno):
    o1, p1 = descartadas(n=3)
    o2, p2 = descartadas(n=1)
    informe([fila(p, o1) for p in p1] + [fila(p, o2) for p in p2] + [fila(p2[0], o2, "descarte valido")],
            [{"lote": "T298", "candidato": "x/repo", "url": "https://github.com/x/repo", "propuesta": "revisar a mano",
              "rastro": []},
             {"lote": "T298", "candidato": "y/ya", "propuesta": "revisar a mano", "rastro": [p1[0]["id"]]}])
    ls = reconsiderar.lotes()
    assert [l["nombre"] for l in ls] == [f"reconsiderar_{o1['id']}", f"reconsiderar_{o2['id']}",
                                         "reconsiderar_vigia_T298"]
    assert [len(l["items"]) for l in ls] == [3, 1, 1]          # y/ya ya va en el lote de propuestas de o1
    assert ls[2]["items"][0]["clave"] == "V:x/repo"


def test_encola_como_mucho_dos_lotes_y_nada_con_el_freno_superado(entorno, monkeypatch):
    lotes = [descartadas(n=1) for _ in range(3)]
    informe([fila(ps[0], o) for o, ps in lotes])
    r = reconsiderar.encolar()
    assert len(r["encolados"]) == 2
    assert reconsiderar.encolar()["encolados"] == []                 # sin hueco: siguen vivos los dos
    exps = tribunal.expedientes()
    assert all(e["fase"] == "tribunal" and e["tipo"] == "reconsideracion" for e in exps.values())
    with tribunal._editar() as d:
        for e in d.values():
            e["fase"] = "resuelto"
    monkeypatch.setattr(freno, "LIMITE_PROPUESTAS", 0)
    for _ in range(1):
        T.anadir("propuesta abierta", estado="propuesta")
    r = reconsiderar.encolar()
    assert r["encolados"] == [] and r["motivo"].startswith("freno F0")


def test_tribunal_unanime_reabre_unas_y_confirma_el_descarte_de_otras(entorno):
    o, ps = descartadas(n=2)
    informe([fila(p, o) for p in ps])
    entorno["guion"]["*"] = [veredicto(["APROBAR", "RECHAZAR"])]
    r = tribunal.ciclo()
    assert r["sincronizado"]["reconsiderar"]["encolados"] == [f"reconsiderar_{o['id']}"]
    e = tribunal.expedientes()[f"reconsiderar_{o['id']}"]
    assert e["fase"] == "resuelto" and e["reconsiderar"]["reabiertas"] == [ps[0]["id"]]
    assert T.buscar(ps[0]["id"])["estado"] == "propuesta"
    assert T.buscar(ps[1]["id"])["estado"] == "descartada"
    # el descarte confirmado pasa a ser de IDEA: entra en el registro de T688 y deja de pedir 'reabrir'
    assert AC._causa(T.buscar(ps[1]["id"])) == "idea"
    assert ps[1]["id"] in {d["id"] for d in descartes.registro()}
    assert "idea DESCARTADA" in entorno["llamadas"][0][1]


def test_lo_aprobado_que_no_cabe_bajo_el_freno_espera_y_se_suelta_despues(entorno, monkeypatch):
    o, ps = descartadas(n=2)
    informe([fila(p, o) for p in ps])
    monkeypatch.setattr(freno, "LIMITE_PROPUESTAS", 1)
    entorno["guion"]["*"] = [veredicto(["APROBAR", "APROBAR"])]
    tribunal.ciclo()
    e = tribunal.expedientes()[f"reconsiderar_{o['id']}"]
    assert e["fase"] == reconsiderar.FASE_FRENO and e["reconsiderar"]["espera_freno"] == [ps[1]["id"]]
    assert freno.estado_cola()["propuestas"] == 1                   # nunca pasa del limite
    T.actualizar(ps[0]["id"], estado="pendiente")                   # se decide la abierta: hay hueco
    assert reconsiderar.soltar()["sueltas"] == [ps[1]["id"]]
    assert tribunal.expedientes()[f"reconsiderar_{o['id']}"]["fase"] == "resuelto"


def test_candidato_del_vigia_rechazado_queda_como_descarte_con_motivo_y_aprobado_como_propuesta(entorno):
    lote = T.anadir("Lote del vigia", estado="hecha")
    informe([], [{"lote": lote["id"], "candidato": "a/uno", "url": "https://github.com/a/uno", "descripcion": "uno",
                  "propuesta": "revisar a mano", "rastro": []},
                 {"lote": lote["id"], "candidato": "b/dos", "url": "https://github.com/b/dos", "descripcion": "dos",
                  "propuesta": "revisar a mano", "rastro": []}])
    entorno["guion"]["*"] = [veredicto(["RECHAZAR", "APROBAR"])]
    tribunal.ciclo()
    ts = {t["titulo"]: t for t in T.cargar()["tareas"]}
    rech = next(t for k, t in ts.items() if "a/uno" in k)
    apr = next(t for k, t in ts.items() if "b/dos" in k)
    assert rech["estado"] == "descartada" and AC._causa(rech) == "idea"
    assert apr["estado"] == "propuesta" and f"tarea_origen:{lote['id']}" in apr["etiquetas"]


def test_todos_rechazan_confirma_el_lote_entero(entorno):
    o, ps = descartadas(n=2)
    informe([fila(p, o) for p in ps])
    entorno["guion"]["*"] = [veredicto(["RECHAZAR", "RECHAZAR"], glob="RECHAZAR")]
    tribunal.ciclo()
    e = tribunal.expedientes()[f"reconsiderar_{o['id']}"]
    assert e["fase"] == "resuelto" and sorted(e["reconsiderar"]["confirmadas"]) == sorted(p["id"] for p in ps)
    assert all(T.buscar(p["id"])["estado"] == "descartada" for p in ps)


def test_desacuerdo_va_a_apelacion_y_su_rechazo_unanime_confirma(entorno):
    o, ps = descartadas(n=1)
    informe([fila(p, o) for p in ps])
    entorno["guion"]["*"] = [veredicto(["APROBAR"]), veredicto(["RECHAZAR"], glob="RECHAZAR")]
    tribunal.ciclo()
    e = tribunal.expedientes()[f"reconsiderar_{o['id']}"]
    assert e["dictamenes"]["apelacion"] and e["fase"] == "resuelto"
    assert e["reconsiderar"]["confirmadas"] == [ps[0]["id"]] and T.buscar(ps[0]["id"])["estado"] == "descartada"


def test_damian_aprueba_desde_su_bandeja_y_reabre(entorno):
    o, ps = descartadas(n=1)
    informe([fila(p, o) for p in ps])
    reconsiderar.encolar()
    nombre = f"reconsiderar_{o['id']}"
    with tribunal._editar() as d:
        d[nombre]["fase"] = "damian"
        d[nombre]["lineas"] = ["dividido", "dividido", "dividido"]
    tribunal.decidir_damian(nombre, "aprobar")
    assert tribunal.expedientes()[nombre]["fase"] == "resuelto"
    assert T.buscar(ps[0]["id"])["estado"] == "propuesta"


def test_un_expediente_de_reconsideracion_no_se_cierra_como_resuelto_fuera(entorno):
    o, ps = descartadas(n=1)
    informe([fila(p, o) for p in ps])
    reconsiderar.encolar()
    assert tribunal._sincronizar()["fuera"] == []
    assert tribunal.candidatas() >= 1
