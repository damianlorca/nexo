# -*- coding: utf-8 -*-
"""T186 pieza D: ejecutor de ACCIONES DIRECTAS de lista blanca, por canal, que confirma siempre.

Tests dados (los escribe Claude; el implementador SOLO crea nucleo/orden_ejecutor.py). Contrato:
`ejecutar(accion: dict, canal: str) -> {"estado": str, "respuesta": str}` con estado en
EJECUTADA | NO_PERMITIDA | NO_SOPORTADA | ERROR. `accion` tiene la forma que devuelve
nucleo.orden_accion.detectar (pieza A); este modulo NO la importa.

Orden de comprobacion (la primera que aplica gana):
1. Canal: PERMITIDAS = {"web": {"estado_tarea", "asignar", "prioridad", "turnos", "aviso"}} (constante del modulo).
   Un canal que no esta (telegram, turno...) -> NO_PERMITIDA, sin tocar nada. (Damian 27/09: nada nuevo en Telegram.)
2. Accion desconocida (no esta en PERMITIDAS["web"]) -> NO_SOPORTADA.
3. Acciones sobre una tarea (estado_tarea, asignar, prioridad): T = nucleo.tareas; `T.buscar(id)` y si no devuelve
   una tarea con ESE id exacto -> ERROR ("no existe" en la respuesta). asignar y prioridad sobre una tarea con
   estado en T.CERRADOS -> ERROR ("cerrada" en la respuesta), sin cambios.
4. Efecto:
   - estado_tarea: no escribe nada; respuesta con id, estado y titulo (max. 80 car.).
   - asignar: T.actualizar(id, depende=a) y T.anotar(id, nota que contiene "asignada a <a>").
   - prioridad: importancia = min(5, imp + 1) si sentido 1; max(1, imp - 1) si -1; T.actualizar + T.anotar
     (nota con "importancia X -> Y"). Ya en el tope (5 al subir, 1 al bajar): EJECUTADA sin escribir nada,
     respuesta con "ya estaba".
   - turnos: nucleo.turnos.activar() o nucleo.turnos.desactivar("orden web de Damian"); respuesta = lo que devuelven.
   - aviso: minutos == 0 -> nucleo.avisos.emitir(tipo="orden", titulo="Aviso pedido por Damian",
     cuerpo=accion["texto"][:400]); minutos > 0 -> NO_SOPORTADA ("programados" en la respuesta), sin emitir.
Las APIs se llaman por su modulo (`turnos.desactivar(...)`, `avisos.emitir(...)`, `T.actualizar(...)`), sin importar
funciones sueltas, para que los dobles de los tests las sustituyan.
5. Cualquier excepcion de las APIs -> ERROR con el tipo y el mensaje en la respuesta; NUNCA se propaga.
La respuesta nunca esta vacia.
"""
from __future__ import annotations

import pytest

from nucleo import avisos, turnos
from nucleo import orden_ejecutor as E
from nucleo import tareas as T


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    mem = tmp_path / "memoria"
    mem.mkdir()
    monkeypatch.setattr(T, "ALMACEN", mem / "tareas.json")
    monkeypatch.setattr(T, "VISTA", mem / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "tareas.md")
    monkeypatch.setattr(T, "CANDADO", mem / ".candado_tareas.lock")
    monkeypatch.setattr(turnos, "BANDERA", mem / "TURNOS_DESACTIVADOS")
    monkeypatch.setattr(avisos, "CARPETA", tmp_path / "avisos")


def _nueva(**c):
    return T.anadir(c.pop("titulo", "Medir la GPU"), **c)


def test_canal_no_permitido_no_toca_nada():
    t = _nueva(importancia=3)
    r = E.ejecutar({"accion": "prioridad", "tarea": t["id"], "sentido": 1}, "telegram")
    assert r["estado"] == "NO_PERMITIDA" and r["respuesta"]
    assert T.buscar(t["id"])["importancia"] == 3


def test_accion_desconocida():
    assert E.ejecutar({"accion": "borrar", "tarea": "T001"}, "web")["estado"] == "NO_SOPORTADA"


def test_estado_tarea():
    t = _nueva(titulo="Medir la temperatura de la GPU " + "x" * 200)
    r = E.ejecutar({"accion": "estado_tarea", "tarea": t["id"]}, "web")
    assert r["estado"] == "EJECUTADA" and t["id"] in r["respuesta"] and "pendiente" in r["respuesta"]
    assert "x" * 81 not in r["respuesta"]


def test_tarea_que_no_existe():
    r = E.ejecutar({"accion": "asignar", "tarea": "T999", "a": "claude"}, "web")
    assert r["estado"] == "ERROR" and "no existe" in r["respuesta"]


def test_asignar():
    t = _nueva(depende="ia")
    r = E.ejecutar({"accion": "asignar", "tarea": t["id"], "a": "claude"}, "web")
    x = T.buscar(t["id"])
    assert r["estado"] == "EJECUTADA" and x["depende"] == "claude"
    assert any("asignada a claude" in n["texto"] for n in x["notas"])


def test_no_se_toca_una_cerrada():
    t = _nueva(importancia=3)
    T.actualizar(t["id"], estado="hecha")
    r = E.ejecutar({"accion": "prioridad", "tarea": t["id"], "sentido": 1}, "web")
    assert r["estado"] == "ERROR" and "cerrada" in r["respuesta"] and T.buscar(t["id"])["importancia"] == 3


def test_prioridad_sube_y_tope():
    t = _nueva(importancia=4)
    r = E.ejecutar({"accion": "prioridad", "tarea": t["id"], "sentido": 1}, "web")
    assert r["estado"] == "EJECUTADA" and T.buscar(t["id"])["importancia"] == 5
    assert any("importancia 4 -> 5" in n["texto"] for n in T.buscar(t["id"])["notas"])
    notas = len(T.buscar(t["id"])["notas"])
    r = E.ejecutar({"accion": "prioridad", "tarea": t["id"], "sentido": 1}, "web")
    assert r["estado"] == "EJECUTADA" and "ya estaba" in r["respuesta"] and len(T.buscar(t["id"])["notas"]) == notas


def test_prioridad_baja():
    t = _nueva(importancia=1)
    assert "ya estaba" in E.ejecutar({"accion": "prioridad", "tarea": t["id"], "sentido": -1}, "web")["respuesta"]


def test_turnos():
    r = E.ejecutar({"accion": "turnos", "activar": False}, "web")
    assert r["estado"] == "EJECUTADA" and turnos.desactivados() == "orden web de Damian"
    r = E.ejecutar({"accion": "turnos", "activar": True}, "web")
    assert r["estado"] == "EJECUTADA" and turnos.desactivados() is None and "ACTIVADOS" in r["respuesta"]


def test_aviso_ya_y_programado(tmp_path):
    r = E.ejecutar({"accion": "aviso", "minutos": 0, "texto": "mandame un push"}, "web")
    assert r["estado"] == "EJECUTADA"
    assert [a["titulo"] for a in avisos.recientes()] == ["Aviso pedido por Damian"]
    r = E.ejecutar({"accion": "aviso", "minutos": 5, "texto": "mandame un push en 5 min"}, "web")
    assert r["estado"] == "NO_SOPORTADA" and "programados" in r["respuesta"]
    assert len(avisos.recientes()) == 1


def test_excepcion_no_se_propaga(monkeypatch):
    def roto(*a, **k):
        raise OSError("disco lleno")
    monkeypatch.setattr(turnos, "desactivar", roto)
    r = E.ejecutar({"accion": "turnos", "activar": False}, "web")
    assert r["estado"] == "ERROR" and "OSError" in r["respuesta"] and "disco lleno" in r["respuesta"]
