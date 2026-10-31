# -*- coding: utf-8 -*-
"""T230 pieza 2: "Aparcar hasta..." de verdad (nucleo, web y vuelta sola con aviso push)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from interfaz import presentar, vigilancia
from interfaz.push import Almacen, Notificador
from interfaz.vigilancia import Vigilante
from nucleo import avisos
from nucleo import tareas as T

HOY = date(2026, 9, 28)


def _post(cliente, csrf, url, **datos):
    return cliente.post(url, data=datos, headers={"X-CSRF-Token": csrf})


def _tarea(id_):
    return next(t for t in T.cargar()["tareas"] if t["id"] == id_)


def _vence_hoy(id_):
    """Simula que ya ha llegado el dia de vuelta (aparcar no deja poner hoy)."""
    datos = T.cargar()
    next(t for t in datos["tareas"] if t["id"] == id_)["aparcada_hasta"] = date.today().isoformat()
    T.guardar(datos)


# --------------------------------------------------------------------- nucleo
def test_aparcar_guarda_fecha_y_estado_anterior_y_vuelve_solo_ese_dia():
    t = T.anadir("x")
    T.actualizar(t["id"], estado="bloqueada")
    T.aparcar(t["id"], "2026-10-05", hoy=HOY)
    g = _tarea(t["id"])
    assert (g["estado"], g["aparcada_hasta"], g["estado_antes_de_aparcar"]) == ("aparcada", "2026-10-05", "bloqueada")
    assert "Aparcada hasta el 05/10/2026" in g["notas"][-1]["texto"]
    assert T.despertar_aparcadas(date(2026, 10, 4)) == []                  # la vispera, nada
    assert [v["id"] for v in T.despertar_aparcadas(date(2026, 10, 5))] == [t["id"]]
    g = _tarea(t["id"])
    assert g["estado"] == "bloqueada" and "aparcada_hasta" not in g and "estado_antes_de_aparcar" not in g
    assert g["notas"][-1]["texto"].startswith("Ha vuelto sola")


def test_despertar_no_toca_las_aparcadas_sin_fecha_de_antes():
    t = T.anadir("vieja aparcada")
    T.actualizar(t["id"], estado="aparcada")
    assert T.despertar_aparcadas(date(2030, 1, 1)) == [] and _tarea(t["id"])["estado"] == "aparcada"


@pytest.mark.parametrize("hasta,motivo", [("2026-09-28", "a partir de mañana"), ("2026-09-01", "a partir de mañana"),
                                          ("mañana", "AAAA-MM-DD"), ("2030-01-01", "dos años")])
def test_fechas_invalidas(hasta, motivo):
    t = T.anadir("x")
    with pytest.raises(T.NoSePuedeAparcar, match=motivo):
        T.aparcar(t["id"], hasta, hoy=HOY)
    assert _tarea(t["id"])["estado"] == "pendiente"


def test_no_se_aparca_una_cerrada_y_la_inexistente_da_none():
    t = T.anadir("x")
    T.completar(t["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    with pytest.raises(T.NoSePuedeAparcar, match="cerrada"):
        T.aparcar(t["id"], "2026-10-01", hoy=HOY)
    assert T.aparcar("T999", "2026-10-01", hoy=HOY) is None


def test_reaparcar_conserva_el_estado_de_antes_y_recuperar_lo_devuelve():
    t = T.anadir("x")
    T.actualizar(t["id"], estado="en_curso")
    T.aparcar(t["id"], "2026-10-01", hoy=HOY)
    T.aparcar(t["id"], "2026-10-09", hoy=HOY)                              # cambiar la fecha
    assert _tarea(t["id"])["estado_antes_de_aparcar"] == "en_curso"
    T.recuperar(t["id"])
    g = _tarea(t["id"])
    assert g["estado"] == "en_curso" and "aparcada_hasta" not in g


def test_cambiar_el_estado_a_mano_borra_la_fecha_de_vuelta():
    t = T.anadir("x")
    T.aparcar(t["id"], "2026-10-01", hoy=HOY)
    T.actualizar(t["id"], estado="pendiente")
    g = _tarea(t["id"])
    assert "aparcada_hasta" not in g and "estado_antes_de_aparcar" not in g


def test_atajos_manana_semana_y_mes():
    assert presentar.atajos_aparcar(date(2026, 9, 28)) == [
        ("Mañana", date(2026, 9, 29)), ("1 semana", date(2026, 10, 5)), ("1 mes", date(2026, 10, 28))]
    assert presentar.atajos_aparcar(date(2027, 1, 31))[2][1] == date(2027, 2, 28)
    assert presentar.atajos_aparcar(date(2026, 12, 15))[2][1] == date(2027, 1, 15)


# ------------------------------------------------------------------------ web
def test_ficha_ofrece_aparcar_con_atajos_que_funcionan(cliente, csrf):
    t = T.anadir("Para luego")
    r = cliente.get(f"/tareas/{t['id']}").text
    manana = (date.today() + timedelta(days=1)).isoformat()
    assert "Aparcar hasta…" in r and f'name="hasta" value="{manana}"' in r and f'hx-post="/tareas/{t["id"]}/aparcar"' in r
    r = _post(cliente, csrf, f"/tareas/{t['id']}/aparcar", hasta=manana)
    assert "Aparcada hasta el" in r.text and "vuelve sola" in r.text and "Recuperarla ahora" in r.text
    assert _tarea(t["id"])["aparcada_hasta"] == manana
    assert "Para luego" not in cliente.get("/tareas").text                 # sale de pendientes
    assert "Para luego" in cliente.get("/tareas", params={"estado": "aparcadas"}).text
    assert "1 aparcada</a>" in cliente.get("/centro/resumen").text
    r = _post(cliente, csrf, f"/tareas/{t['id']}/recuperar")
    assert "vuelve a estar en pendientes" in r.text and _tarea(t["id"])["estado"] == "pendiente"


def test_aparcar_mal_no_toca_nada(cliente, csrf):
    t = T.anadir("x")
    r = _post(cliente, csrf, f"/tareas/{t['id']}/aparcar", hasta=date.today().isoformat())
    assert r.headers["hx-retarget"] == "#error-aparcar" and "a partir de mañana" in r.text
    r = _post(cliente, csrf, "/tareas/T999/aparcar", hasta="2099-01-01")
    assert r.headers["hx-retarget"] == "#error-aparcar"
    assert _tarea(t["id"])["estado"] == "pendiente"


def test_aparcar_y_recuperar_sin_csrf_dan_403(cliente, csrf):
    t = T.anadir("x")
    assert cliente.post(f"/tareas/{t['id']}/aparcar", data={"hasta": "2099-01-01"}).status_code == 403
    assert cliente.post(f"/tareas/{t['id']}/recuperar").status_code == 403
    assert _tarea(t["id"])["estado"] == "pendiente"


def test_cerrada_no_ofrece_aparcar(cliente, csrf):
    t = T.anadir("x")
    T.completar(t["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    assert "Aparcar hasta…" not in cliente.get(f"/tareas/{t['id']}").text


# ---------------------------------------------------------- vuelta sola + push
def test_vigilancia_despierta_la_tarea_y_su_aviso_sale_como_push():
    t = T.anadir("Revisar seguro")
    T.aparcar(t["id"], date.today() + timedelta(days=1))
    _vence_hoy(t["id"])
    v = Vigilante(bus=None)
    v.revisar()                                # 1a pasada: foto inicial; todavia no despierta
    assert _tarea(t["id"])["estado"] == "aparcada"
    eventos = [e for e in v.revisar() if e[0] == "aviso"]
    assert _tarea(t["id"])["estado"] == "pendiente"
    assert len(eventos) == 1 and eventos[0][1]["tipo"] == "recordatorio" and t["id"] in eventos[0][1]["titulo"]
    push = Notificador(Almacen(avisos.CARPETA.parent / "push"), enviar=lambda *a: 201).aviso_de("aviso", eventos[0][1])
    assert push["ruta"] == f"/tareas/{t['id']}" and "ha vuelto" in push["titulo"]


def test_vigilancia_mira_las_aparcadas_cada_cierto_tiempo(monkeypatch):
    llamadas = []
    monkeypatch.setattr(T, "despertar_aparcadas", lambda: llamadas.append(1) or [])
    v = Vigilante(bus=None)
    v.revisar()
    v.revisar()
    v.revisar()
    assert len(llamadas) == 1                  # la 2a pasada mira; la 3a cae dentro de CADA_APARCADAS
    monkeypatch.setattr(vigilancia, "CADA_APARCADAS", 0.0)
    v.revisar()
    assert len(llamadas) == 2
