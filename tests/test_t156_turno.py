# -*- coding: utf-8 -*-
"""T156: el turno no arranca sin candidatas y una tarea se bloquea tras N fallos seguidos del turno."""
from __future__ import annotations


import pytest

from nucleo import tareas as T
from nucleo import trabajo
from proveedores import Resultado


@pytest.fixture
def cola(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "x.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado")
    monkeypatch.setattr(trabajo, "BORRADORES", tmp_path / "borradores")
    monkeypatch.setattr(trabajo, "_web", lambda: True)
    return T.anadir("Investigar X", depende="ia", etiquetas=["cat:investigacion"], detalle="Evaluar X.")


# ------------------------------------------------------------------ contador en el core
def test_bloquea_al_tercer_fallo_seguido(cola):
    for n in (1, 2):
        t = T.fallo_turno(cola["id"], "gemini: 429")
        assert t["fallos_turno"] == n and t["estado"] == "pendiente"
    t = T.fallo_turno(cola["id"], "gemini: 429")
    assert t["estado"] == "bloqueada" and "3 fallos seguidos" in t["bloqueada_por"] and "gemini: 429" in t["bloqueada_por"]
    assert [n["texto"][:30] for n in t["notas"]][-1].startswith("Turno de NEXO: fallo 3/3")


def test_un_exito_corta_la_racha(cola):
    T.fallo_turno(cola["id"], "x")
    T.fallo_turno(cola["id"], "x")
    T.exito_turno(cola["id"])
    assert T.fallo_turno(cola["id"], "x")["estado"] == "pendiente"


def test_reabrir_a_mano_pone_el_contador_a_cero(cola):
    for _ in range(3):
        T.fallo_turno(cola["id"], "x")
    t = T.actualizar(cola["id"], estado="pendiente", bloqueada_por="")
    assert "fallos_turno" not in t
    assert T.fallo_turno(cola["id"], "x")["fallos_turno"] == 1


def test_fallo_de_tarea_inexistente_no_revienta(cola):
    assert T.fallo_turno("T999", "x") is None
    T.exito_turno("T999")


# ------------------------------------------------------------------ trabajo.ciclo
class Caido:
    nombre = "chatgpt"
    modo_preferido = True

    def disponible(self):
        return True

    def enviar(self, prompt, buscar=False, _url=None):
        return Resultado("ERROR", detalle="la web no carga")

    def continuar(self, prompt, url=None):
        return self.enviar(prompt)


def test_ciclo_sin_borrador_cuenta_fallos_y_bloquea(cola, monkeypatch):
    monkeypatch.setattr(trabajo, "_generadores", lambda cat: [Caido()])
    for n in (1, 2, 3):
        [fila] = trabajo.ciclo(max_tareas=1)
        assert fila["fallos_seguidos"] == n
    assert T.buscar(cola["id"])["estado"] == "bloqueada"
    assert trabajo.candidatas() == []          # el siguiente turno ya no la reintenta
    assert trabajo.ciclo(max_tareas=1) == []


# ------------------------------------------------------------------ turno_nexo
# T231 (28/09): la puerta cuenta el trabajo de la PLANTILLA elegida (nucleo/plantillas_turno.py). El paso
# "router" salio del turno (cerraba tareas sin OK absoluto), y con el su test de fallos del router.
@pytest.fixture
def turno(tmp_path, monkeypatch, cola):
    import turno_nexo
    monkeypatch.setattr(turno_nexo, "REGISTROS", tmp_path / "registros")
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: None)
    monkeypatch.setattr(turno_nexo.parada, "cierre_pedido", lambda: False)
    monkeypatch.setattr(turno_nexo.parada, "limpiar_cierre", lambda: None)
    monkeypatch.setattr(turno_nexo.turnos, "desactivados", lambda: None)
    return turno_nexo


def test_sin_candidatas_no_arranca_ni_avisa(turno, monkeypatch):
    from nucleo import avisos
    tomado = []
    monkeypatch.setattr(turno, "_tomar_candado", lambda: tomado.append(1) or True)
    monkeypatch.setattr(turno, "candidatas", lambda ctx: {ctx["plantilla"]: 0})
    reg = turno.turno(avisar=True)
    assert "sin candidatas" in reg["abortado"] and not tomado and reg["pasos"] == {}
    assert avisos.recientes() == [] and reg["aviso_push"] is False


def test_con_candidatas_si_arranca(turno, monkeypatch):
    monkeypatch.setattr(turno, "candidatas", lambda ctx: {ctx["plantilla"]: 1})
    monkeypatch.setattr(turno, "_tomar_candado", lambda: False)   # para aqui: basta con ver que paso la puerta
    reg = turno.turno(avisar=False)
    assert "candado" in reg["abortado"] and reg["candidatas"]["cola"] == 1


def test_si_la_puerta_falla_el_turno_sigue(turno, monkeypatch):
    def rota(ctx):
        raise RuntimeError("cola rota")
    monkeypatch.setattr(turno, "candidatas", rota)
    reg = {}
    assert turno._hay_trabajo(reg, {"plantilla": "cola"}) is True and "cola rota" in reg["candidatas_error"]


def test_candidatas_real_cuenta_trabajo_sin_modelos(turno):
    assert turno.candidatas(turno.turnos.contexto()) == {"cola": 1}
