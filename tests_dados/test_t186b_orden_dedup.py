# -*- coding: utf-8 -*-
"""T186 pieza B: una orden nueva ¿repite una tarea abierta o cerrada hace poco? Sin IA.

Tests dados (los escribe Claude; el implementador SOLO crea nucleo/orden_dedup.py). Contrato:
`buscar(texto: str, tareas: list[dict], ahora: datetime | None = None, dias: int = 7) -> dict | None`.
Funcion PURA (no carga ni escribe tareas; `tareas` siempre llega como argumento).

- Candidatas: tareas con estado en tareas.VIVOS, o en tareas.CERRADOS con "cerrada" (formato "%Y-%m-%d %H:%M:%S")
  a menos de `dias` dias de `ahora` (>= ahora - dias). Nunca las que llevan la etiqueta "cat:revision".
  Una cerrada sin fecha "cerrada" no es candidata.
- Texto de cada candidata: si su "detalle" contiene la linea "Orden literal de Damián (<canal>):", lo que va DESPUES
  de esa linea (el literal); si no, su "titulo".
- Normalizado para comparar IDENTICAS: minusculas, sin tildes, solo [a-z0-9] separados por un espacio.
- Precedencia: 1) identica (normalizados iguales y no vacios) -> {"id", "tipo": "identica", "similitud": 1.0,
  "estado"}; 2) si no, la mas parecida con freno.parecido(freno.palabras(a), freno.palabras(b)) >=
  freno.UMBRAL_PARECIDO -> {"id", "tipo": "parecida", "similitud": round(x, 3), "estado"}; 3) None.
- Empates: la de "creada" mas reciente; si tambien empatan, la de id mayor (numerico: T1000 > T999).
- Texto de menos de 3 raices: solo cuenta la identica (parecido() devuelve 0).
"""
from __future__ import annotations

from datetime import datetime

from nucleo import orden_dedup as D

AHORA = datetime(2026, 10, 12, 12, 0)


def _t(tid, titulo, estado="pendiente", cerrada=None, creada="2026-10-01 10:00:00", literal=None, et=()):
    det = f"Orden literal de Damián (web):\n{literal}" if literal is not None else "detalle cualquiera"
    return {"id": tid, "titulo": titulo, "detalle": det, "estado": estado, "cerrada": cerrada, "creada": creada,
            "etiquetas": list(et)}


def test_identica_aunque_cambien_tildes_y_signos():
    ts = [_t("T148", "otro titulo", literal="Investiga \"claude red\"")]
    assert D.buscar("investiga claude red!", ts, AHORA) == {"id": "T148", "tipo": "identica", "similitud": 1.0,
                                                             "estado": "pendiente"}


def test_identica_gana_a_parecida():
    ts = [_t("T900", "Crear registro local de skills con busqueda por nombre y descripcion corta"),
          _t("T901", "x", literal="crear un registro local de skills con busqueda por nombre")]
    r = D.buscar("Crear un registro local de skills con búsqueda por nombre", ts, AHORA)
    assert r["id"] == "T901" and r["tipo"] == "identica"


def test_parecida_por_palabras():
    ts = [_t("T900", "Crear registro local de skills con busqueda por nombre y descripcion corta")]
    r = D.buscar("crear un registro local de skills con busqueda por nombre y descripcion", ts, AHORA)
    assert r["id"] == "T900" and r["tipo"] == "parecida" and r["similitud"] >= 0.5


def test_cerrada_hace_poco_si_y_antigua_no():
    reciente = _t("T1", "Medir la temperatura de la GPU cada hora", "hecha", cerrada="2026-10-06 12:00:00")
    vieja = _t("T2", "Medir la temperatura de la GPU cada hora", "hecha", cerrada="2026-10-04 11:59:59")
    sin_fecha = _t("T3", "Medir la temperatura de la GPU cada hora", "descartada")
    assert D.buscar("medir la temperatura de la gpu cada hora", [vieja, sin_fecha], AHORA) is None
    assert D.buscar("medir la temperatura de la gpu cada hora", [vieja, reciente], AHORA)["id"] == "T1"
    assert D.buscar("medir la temperatura de la gpu cada hora", [vieja], AHORA, dias=30)["id"] == "T2"


def test_revisiones_nunca():
    ts = [_t("T5", "Medir la temperatura de la GPU cada hora", et=["cat:revision"])]
    assert D.buscar("Medir la temperatura de la GPU cada hora", ts, AHORA) is None


def test_empate_la_mas_reciente_y_luego_id_mayor():
    a = _t("T999", "Medir la temperatura de la GPU cada hora", creada="2026-10-01 10:00:00")
    b = _t("T1000", "Medir la temperatura de la GPU cada hora", creada="2026-10-01 10:00:00")
    c = _t("T50", "Medir la temperatura de la GPU cada hora", creada="2026-09-01 10:00:00")
    assert D.buscar("Medir la temperatura de la GPU cada hora", [a, c, b], AHORA)["id"] == "T1000"
    d = _t("T51", "Medir la temperatura de la GPU cada hora", creada="2026-10-02 10:00:00")
    assert D.buscar("Medir la temperatura de la GPU cada hora", [a, b, d], AHORA)["id"] == "T51"


def test_texto_corto_solo_identica():
    ts = [_t("T7", "claude red")]
    assert D.buscar("claude red", ts, AHORA)["tipo"] == "identica"
    assert D.buscar("claude roja", ts, AHORA) is None


def test_distinta_no_es_duplicada():
    ts = [_t("T8", "Medir la temperatura de la GPU cada hora y avisar")]
    assert D.buscar("Investigar Remotion para editar videos", ts, AHORA) is None


def test_vacia():
    assert D.buscar("", [_t("T9", "")], AHORA) is None
