# -*- coding: utf-8 -*-
"""T140/T186 pieza F: nucleo.ordenes.procesar usa las piezas A-E (accion directa, duplicados, prioridad, handoff).

Tests dados (los escribe Claude; el implementador SOLO cambia nucleo/ordenes.py). Va DESPUES de las piezas A-E
(nucleo/orden_accion.py, orden_dedup.py, orden_prioridad.py, orden_ejecutor.py, handoff.py), ya fusionadas.
Contrato de `procesar(texto, canal="telegram", trabajar=True) -> dict` (siempre con "estado" y "respuesta" no vacia):

0. Texto de menos de 4 caracteres (tras strip) -> "VACIA" (como ahora).
1. ACCION DIRECTA: `orden_accion.detectar(texto)`; si devuelve una accion, `orden_ejecutor.ejecutar(accion, canal)`:
   - EJECUTADA -> {"estado": "EJECUTADA", "accion": <nombre>, "respuesta": <la del ejecutor>}. NO se crea tarea.
   - ERROR     -> {"estado": "ERROR", "accion": <nombre>, "respuesta": <la del ejecutor>}. NO se crea tarea.
   - NO_PERMITIDA / NO_SOPORTADA -> sigue como una orden normal (pasos 2-4) y el resultado lleva ademas
     "accion_no_ejecutada": <respuesta del ejecutor>, que tambien va al FINAL de "respuesta" (despues de todo lo
     demas, incluido el aviso de descartes).
2. DUPLICADO: `orden_dedup.buscar(texto, tareas.cargar()["tareas"])`; si encuentra una -> se anota la orden literal
   en ESA tarea (nota con el texto completo y el canal), NO se crea otra, NO se clasifica, y se devuelve
   {"estado": "DUPLICADA", "tarea": id, "tipo": "identica"|"parecida", "respuesta": con el id}.
   Si buscar lanza una excepcion, se sigue como si no hubiera duplicado (la orden nunca se pierde por esto).
3. PRIORIDAD: `orden_prioridad.estimar(texto)` da importancia y urgencia de la tarea nueva (ya no 4/4 fijas);
   si "sin_estimar", la tarea lleva la etiqueta "prioridad:sin_estimar". Nota en la tarea con la justificacion.
   Si estimar lanza una excepcion: 3/3 y "prioridad:sin_estimar".
4. Lo de siempre (clasificar, DELEGABLE/personal/escalado, literal intacto en el detalle). Ademas, en ESCALADO:
   `handoff.anotar(id, texto, motivo, canal=canal)` (texto = la orden sin espacios en los extremos, la misma
   que va al detalle) con un motivo que nombra la categoria; si handoff falla, la
   orden sigue (estado ESCALADO igual).
5. Si algo no previsto lanza una excepcion antes de crear la tarea (p. ej. el clasificador) -> {"estado": "ERROR",
   "respuesta": que contiene "NO se ha guardado"}. Nunca se propaga ni se calla.
Los modulos se usan por su nombre (`orden_accion.detectar`, `handoff.anotar`...) para que los dobles funcionen.
"""
from __future__ import annotations

import pytest

from nucleo import clasificador, handoff, orden_dedup, orden_prioridad, ordenes, turnos
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
    monkeypatch.setattr(handoff, "RUTA", mem / "handoff_claude.jsonl")
    monkeypatch.setattr(clasificador, "clasificar", lambda t: "codigo")


def _n():
    return len(T.cargar()["tareas"])


def test_accion_directa_ejecutada_no_crea_tarea():
    t = T.anadir("Idea de monetizacion con cartelitos", depende="ia")
    antes = _n()
    r = ordenes.procesar(f"cambia {t['id']} a Claude", canal="web")
    assert r["estado"] == "EJECUTADA" and r["accion"] == "asignar" and r["respuesta"]
    assert T.buscar(t["id"])["depende"] == "claude" and _n() == antes


def test_accion_con_error_no_crea_tarea():
    r = ordenes.procesar("cambia T999 a Claude", canal="web")
    assert r["estado"] == "ERROR" and "no existe" in r["respuesta"] and _n() == 0


def test_accion_no_permitida_por_canal_sigue_como_orden():
    r = ordenes.procesar("apaga los turnos", canal="telegram", trabajar=False)
    assert r["estado"] == "ESCALADO" and r["accion_no_ejecutada"]
    assert r["respuesta"].endswith(r["accion_no_ejecutada"])
    assert turnos.desactivados() is None and _n() == 1


def test_aviso_programado_no_soportado_queda_apuntado():
    texto = "mándame una notificación push al teléfono en 5 min para comprobar que funcionan"
    r = ordenes.procesar(texto, canal="web", trabajar=False)
    assert "programados" in r["accion_no_ejecutada"]
    assert texto in T.buscar(r["tarea"])["detalle"]


def test_duplicada_se_anota_en_la_existente():
    r1 = ordenes.procesar("investigar y auditar claude red", canal="web", trabajar=False)
    r2 = ordenes.procesar("Investigar y auditar \"Claude Red\"", canal="web", trabajar=False)
    assert r2["estado"] == "DUPLICADA" and r2["tarea"] == r1["tarea"] and r2["tipo"] == "identica"
    assert r1["tarea"] in r2["respuesta"] and _n() == 1
    assert any("Claude Red" in n["texto"] and "web" in n["texto"] for n in T.buscar(r1["tarea"])["notas"])


def test_duplicada_no_clasifica(monkeypatch):
    ordenes.procesar("medir la temperatura de la GPU cada hora", canal="web", trabajar=False)

    def no(t):
        raise AssertionError("no se clasifica un duplicado")
    monkeypatch.setattr(clasificador, "clasificar", no)
    assert ordenes.procesar("medir la temperatura de la gpu cada hora", canal="web")["estado"] == "DUPLICADA"


def test_si_falla_el_deduplicado_la_orden_sigue(monkeypatch):
    def roto(*a, **k):
        raise RuntimeError("dedup roto")
    monkeypatch.setattr(orden_dedup, "buscar", roto)
    r = ordenes.procesar("arregla el bug del bot", canal="web", trabajar=False)
    assert r["estado"] == "ESCALADO" and _n() == 1


def test_prioridad_estimada_y_sin_estimar():
    r = ordenes.procesar("urgente: el bot no arranca, es importante", canal="web", trabajar=False)
    t = T.buscar(r["tarea"])
    assert (t["importancia"], t["urgencia"]) == (4, 5) and "prioridad:sin_estimar" not in t["etiquetas"]
    r = ordenes.procesar("arregla el bug del panel de turnos", canal="web", trabajar=False)
    t = T.buscar(r["tarea"])
    assert (t["importancia"], t["urgencia"]) == (3, 3) and "prioridad:sin_estimar" in t["etiquetas"]


def test_si_falla_la_prioridad_3_3(monkeypatch):
    def roto(texto):
        raise RuntimeError("x")
    monkeypatch.setattr(orden_prioridad, "estimar", roto)
    t = T.buscar(ordenes.procesar("arregla el bug del bot", canal="web", trabajar=False)["tarea"])
    assert (t["importancia"], t["urgencia"]) == (3, 3) and "prioridad:sin_estimar" in t["etiquetas"]


def test_escalado_deja_handoff_con_el_literal():
    texto = "arregla el bug del bot\n  con el literal  intacto"
    r = ordenes.procesar(texto, canal="web", trabajar=False)
    p = handoff.pendientes()
    assert [(e["tarea"], e["orden"], e["canal"]) for e in p] == [(r["tarea"], texto.strip(), "web")]
    assert "codigo" in p[0]["motivo"]


def test_si_falla_el_handoff_sigue_escalado(monkeypatch):
    def roto(*a, **k):
        raise OSError("disco")
    monkeypatch.setattr(handoff, "anotar", roto)
    assert ordenes.procesar("arregla el bug del bot", canal="web", trabajar=False)["estado"] == "ESCALADO"


def test_personal_y_delegable_no_van_al_handoff(monkeypatch):
    monkeypatch.setattr(clasificador, "clasificar", lambda t: "investigacion")
    assert ordenes.procesar("investiga Remotion para editar videos", canal="web", trabajar=False)["estado"] == "ENCOLADA"
    assert handoff.pendientes() == []


def test_fallo_antes_de_guardar_lo_dice(monkeypatch):
    def roto(t):
        raise ConnectionError("Ollama caido")
    monkeypatch.setattr(clasificador, "clasificar", roto)
    r = ordenes.procesar("arregla el bug del bot", canal="web", trabajar=False)
    assert r["estado"] == "ERROR" and "NO se ha guardado" in r["respuesta"] and _n() == 0
