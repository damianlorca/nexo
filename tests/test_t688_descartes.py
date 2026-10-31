# -*- coding: utf-8 -*-
"""T688 (pieza 1): registro de descartes consultable y aviso al re-proponer. El detector de parecidas (freno,
T435) compara tambien contra lo DESCARTADO y adjunta el motivo anterior. Solo informe: no cambia ninguna tarea."""
from __future__ import annotations

from datetime import datetime

from nucleo import descartes, freno

AHORA = datetime(2026, 10, 5, 12, 0)


def _t(tid, titulo, estado="descartada", etiquetas=(), notas=(), resultado=None, cerrada="2026-09-28 10:00:00", detalle=""):
    t = {"id": tid, "titulo": titulo, "detalle": detalle, "estado": estado, "etiquetas": list(etiquetas),
         "notas": [{"cuando": "2026-09-28 10:00:00", "texto": n} for n in notas], "testeado": False,
         "creada": "2026-09-27 10:00:00", "cerrada": cerrada}
    if resultado:
        t["resultado"] = resultado
    return t


def _inv_descartada(tid="T178", titulo="Investigar Blkit"):
    return _t(tid, titulo, "hecha", ["cat:investigacion"],
              resultado={"decision": "DESCARTAR", "motivo": "no aporta frente a lo que NEXO ya tiene", "quien": "claude",
                         "cuando": "2026-10-03 23:00:00"})


def _prop_idea(tid="T207", titulo="[Propuesta de T167] Sandbox de ejecucion para skills"):
    return _t(tid, titulo, "descartada", ["cat:propuesta", "tarea_origen:T167", "de_borrador:T167_x.md"],
              ["Descartada (descartada por Claude al aprobar el borrador, T206): Windows Home no tiene sandbox"])


def _prop_borrador(tid="T208", titulo="[Propuesta de T167] Otra cosa distinta de verdad"):
    return _t(tid, titulo, "descartada", ["cat:propuesta"],
              ["Descartada (borrador descartado, T206): contenido inventado"])


# ------------------------------------------------------------------ el registro
def test_registro_incluye_resultado_descartar_e_idea_mala_y_excluye_borrador_malo():
    reg = descartes.registro([_inv_descartada(), _prop_idea(), _prop_borrador(),
                              _t("T9", "Sin motivo", "descartada"), _t("T10", "Viva", "pendiente")])
    ids = {r["id"]: r for r in reg}
    assert set(ids) == {"T178", "T207"}
    assert ids["T178"]["causa"] == "resultado" and "NEXO ya tiene" in ids["T178"]["motivo"]
    assert ids["T178"]["quien"] == "claude" and ids["T178"]["cuando"].startswith("2026-10-03")
    assert ids["T207"]["causa"] == "idea" and "Windows Home" in ids["T207"]["motivo"]
    assert ids["T207"]["informe"] == "T167_x.md"


# ------------------------------------------------------------------ buscar (sin IA)
def test_buscar_reconoce_el_mismo_nombre_aunque_el_texto_sea_corto():
    reg = descartes.registro([_inv_descartada()])
    for texto in ("Blkit", "Investigar Blkit para el chat", "mira blkit.dev a ver si sirve"):
        r = descartes.buscar(texto, reg)
        assert [x["id"] for x in r] == ["T178"], texto
        assert "NEXO ya tiene" in r[0]["motivo"]


def test_buscar_reconoce_la_misma_idea_con_otras_palabras_y_no_confunde_lo_distinto():
    reg = descartes.registro([_prop_idea()])
    assert descartes.buscar("Sandbox de ejecucion para las skills que corran codigo", reg)[0]["id"] == "T207"
    assert descartes.buscar("Cola de tareas con prioridad por coste", reg) == []
    assert descartes.buscar("Investigar", reg) == []         # un verbo de encargo solo no es un nombre


# ------------------------------------------------------------------ freno.pares_semanticos
def test_pares_semanticos_adjunta_los_descartados_con_su_motivo(tmp_path, monkeypatch):
    monkeypatch.setattr(freno, "INFORMES", tmp_path)
    nueva = _t("T700", "[Propuesta de T50] Sandbox de ejecucion para skills de terceros", "propuesta",
               ["cat:propuesta"], detalle="QUE: Sandbox de ejecucion para skills de terceros")
    ts = [nueva, _prop_idea(), _prop_borrador()]
    vec = {"Sandbox de ejecucion para skills de terceros": [1.0, 0.0],
           "Sandbox de ejecucion para skills": [0.95, 0.1],
           "Otra cosa distinta de verdad": [0.0, 1.0]}

    def falso(textos):
        return [vec.get(x, [0.5, 0.5]) for x in textos]

    r = freno.pares_semanticos(umbral=0.9, embeber=falso, tareas=ts, ahora=AHORA)
    assert len(r["contra_descartes"]) == 1
    p = r["contra_descartes"][0]
    assert p["a"] == "T700" and p["b"] == "T207" and "Windows Home" in p["motivo"]
    md = (tmp_path / "parecidas_20261005_1200.md").read_text(encoding="utf-8")
    assert "DESCARTADO" in md and "Windows Home" in md


def test_pares_semanticos_sin_propuestas_o_sin_descartes_no_rompe(tmp_path, monkeypatch):
    monkeypatch.setattr(freno, "INFORMES", tmp_path)
    r = freno.pares_semanticos(embeber=lambda x: [[1.0, 0.0] for _ in x], tareas=[_t("T1", "x", "pendiente")], ahora=AHORA)
    assert r["contra_descartes"] == []
