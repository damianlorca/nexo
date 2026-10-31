# -*- coding: utf-8 -*-
"""T687 parte A: auditoria ampliada de cierres (propuestas descartadas, aprobadas sin implementar, candidatos del
vigia, 'hecha' sin testear). SOLO INFORME: no cambia ninguna tarea. Datos como dicts, sin tocar memoria/."""
from __future__ import annotations

import json
from datetime import datetime

from nucleo import auditoria_cierres as A

AHORA = datetime(2026, 10, 5, 12, 0)


def _t(tid, titulo, estado="pendiente", etiquetas=(), notas=(), testeado=False, creada="2026-09-27 10:00:00", **kw):
    return {"id": tid, "titulo": titulo, "detalle": kw.pop("detalle", ""), "estado": estado, "etiquetas": list(etiquetas),
            "notas": [{"cuando": "2026-09-28 10:00:00", "texto": n} for n in notas], "testeado": testeado,
            "creada": creada, "cerrada": None, **kw}


def _prop(tid, titulo, estado="descartada", notas=(), extra=(), detalle=""):
    return _t(tid, f"[Propuesta de T100] {titulo}", estado, ["cat:propuesta", "tarea_origen:T100"] + list(extra), notas,
              detalle=detalle)


def _fila(res, seccion, tid):
    return next(f for f in res[seccion] if f["id"] == tid)


# ------------------------------------------------------------------ propuestas descartadas
def test_descartada_por_borrador_malo_sin_reaparecer_se_reabre():
    ts = [_t("T100", "Investigar skills", "descartada", ["cat:investigacion"]), _prop("T200", "Cargar skills bajo demanda con registro por descripcion",
                notas=["Descartada (borrador descartado, T150): Sesion de veredictos: contenido inventado"])]
    f = _fila(A.auditar(AHORA, ts, escribir=False), "propuestas_descartadas", "T200")
    assert f["propuesta"] == "reabrir" and f["causa"] == "borrador"


def test_descartada_por_borrador_con_origen_viva_no_se_pierde():
    origen = _t("T100", "Investigar skills", "pendiente", ["cat:investigacion"])
    ts = [origen, _prop("T200", "Cargar skills bajo demanda con registro",
                        notas=["Descartada (borrador descartado, T150): contenido inventado"])]
    f = _fila(A.auditar(AHORA, ts, escribir=False), "propuestas_descartadas", "T200")
    assert f["propuesta"] == "descarte valido" and f["origen_estado"] == "pendiente"


def test_descartada_por_borrador_malo_pero_la_idea_volvio_es_descarte_valido():
    ts = [_prop("T200", "Cargar skills bajo demanda con registro por descripcion",
                notas=["Descartada (borrador descartado, T150): contenido inventado"]),
          _prop("T300", "Registro de skills con carga bajo demanda por descripcion", estado="pendiente",
                extra=["propuesta:aprobada"])]
    f = _fila(A.auditar(AHORA, ts, escribir=False), "propuestas_descartadas", "T200")
    assert f["propuesta"] == "descarte valido" and f["volvio_en"] == ["T300"]


def test_descartada_al_aprobar_el_borrador_es_decision_de_idea():
    ts = [_prop("T200", "Sandbox de ejecucion para skills",
                notas=["Descartada (descartada por Claude al aprobar el borrador, T143): Windows Home no tiene sandbox"])]
    f = _fila(A.auditar(AHORA, ts, escribir=False), "propuestas_descartadas", "T200")
    assert f["propuesta"] == "descarte valido" and f["causa"] == "idea" and "Windows Home" in f["motivo"]


def test_descartada_sin_nota_ni_marca_va_a_revisar_a_mano_y_fundida_es_valida():
    ts = [_prop("T200", "Algo sin motivo registrado"),
          _prop("T201", "Otra cosa fundida", extra=["fundida_en:T999"])]
    r = A.auditar(AHORA, ts, escribir=False)
    assert _fila(r, "propuestas_descartadas", "T200")["propuesta"] == "revisar a mano"
    assert _fila(r, "propuestas_descartadas", "T201")["propuesta"] == "descarte valido"


def test_descartada_con_aprobada_a_la_vez_se_revisa_a_mano():
    ts = [_prop("T200", "Cosa aprobada y luego descartada", extra=["propuesta:aprobada"])]
    f = _fila(A.auditar(AHORA, ts, escribir=False), "propuestas_descartadas", "T200")
    assert f["propuesta"] == "revisar a mano"


# ------------------------------------------------------------------ aprobadas sin implementar
def test_aprobada_viva_sin_implementar_se_verifica_con_su_antiguedad():
    ts = [_prop("T245", "Skill Registry", estado="pendiente", extra=["propuesta:aprobada"],
                notas=["APROBADA por Claude (T243): ok"])]
    ts[0]["creada"] = "2026-09-27 10:00:00"
    f = _fila(A.auditar(AHORA, ts, escribir=False), "aprobadas_sin_implementar", "T245")
    assert f["propuesta"] == "verificar" and f["dias"] == 8


def test_aprobada_que_se_integra_en_otra_tarea_es_descarte_valido():
    ts = [_prop("T245", "Skill Registry", estado="pendiente", extra=["propuesta:aprobada"],
                notas=["Damian 03/10 (auditoria T674): se integra dentro de T678 (F3, T669)."])]
    f = _fila(A.auditar(AHORA, ts, escribir=False), "aprobadas_sin_implementar", "T245")
    assert f["propuesta"] == "descarte valido" and "T678" in f["por_que"]


def test_aprobada_hecha_no_sale_en_sin_implementar():
    ts = [_prop("T245", "Skill Registry", estado="hecha", extra=["propuesta:aprobada"])]
    assert A.auditar(AHORA, ts, escribir=False)["aprobadas_sin_implementar"] == []


# ------------------------------------------------------------------ hechas sin testear
def test_hecha_sin_testear_se_verifica_y_las_testeadas_o_vivas_no_salen():
    ts = [_t("T1", "Hecha sin evidencia", "hecha"), _t("T2", "Hecha con evidencia", "hecha", testeado=True),
          _t("T3", "Viva", "pendiente")]
    r = A.auditar(AHORA, ts, escribir=False)
    assert [f["id"] for f in r["hechas_sin_testear"]] == ["T1"]
    assert r["hechas_sin_testear"][0]["propuesta"] == "verificar"


# ------------------------------------------------------------------ candidatos del vigia
def _lote(nombres):
    return {"candidatos": [{"fuente": "github", "id": n, "nombre": n, "url": f"https://github.com/{n}",
                            "descripcion": "x"} for n in nombres]}


def test_candidato_del_lote_sin_rastro_va_a_revisar_a_mano_y_con_rastro_se_distingue():
    lote_t = _t("T298", "Vigia de novedades", "descartada", ["cat:investigacion", "turno:lote"],
                detalle="LOTE: lote_20261001.json")
    ts = [lote_t,
          _prop("T400", "Integrar a/uno como MCP", estado="pendiente", detalle="Fuente https://github.com/a/uno"),
          _prop("T401", "Probar b/dos", estado="descartada", notas=["Descartada (borrador descartado, T9): mal"],
                detalle="https://github.com/b/dos")]
    lotes = {"lote_20261001.json": _lote(["a/uno", "b/dos", "c/tres"])}
    r = A.auditar(AHORA, ts, lotes=lotes, borradores={}, escribir=False)
    por = {f["candidato"]: f for f in r["candidatos_lotes"]}
    assert por["a/uno"]["propuesta"] == "sin accion" and por["a/uno"]["rastro"] == ["T400"]
    assert por["b/dos"]["propuesta"] == "revisar a mano"          # solo rastro en una descartada por borrador
    assert por["c/tres"]["propuesta"] == "revisar a mano" and por["c/tres"]["rastro"] == []


def test_candidato_mencionado_en_el_borrador_del_lote_no_se_da_por_perdido():
    lote_t = _t("T298", "Vigia", "hecha", ["cat:investigacion", "turno:lote"], detalle="LOTE: lote_20261001.json")
    lotes = {"lote_20261001.json": _lote(["c/tres"])}
    borr = {"T298_20261001_0300.md": "Hallazgos: c/tres no sirve porque duplica el router local."}
    r = A.auditar(AHORA, [lote_t], lotes=lotes, borradores=borr, escribir=False)
    f = r["candidatos_lotes"][0]
    assert f["propuesta"] == "descarte valido" and "borrador" in f["por_que"]


# ------------------------------------------------------------------ informe
def test_escribe_informe_md_y_json_sin_tocar_las_tareas(tmp_path):
    ts = [_prop("T200", "Algo sin motivo registrado"), _t("T1", "Hecha sin evidencia", "hecha")]
    antes = json.dumps(ts, sort_keys=True)
    r = A.auditar(AHORA, ts, lotes={}, borradores={}, escribir=True, carpeta=tmp_path)
    assert json.dumps(ts, sort_keys=True) == antes
    md = (tmp_path / "auditoria_cierres_20261005_1200.md").read_text(encoding="utf-8")
    assert "SOLO INFORME" in md and "T200" in md and "revisar a mano" in md
    assert json.loads((tmp_path / "auditoria_cierres_20261005_1200.json").read_text(encoding="utf-8"))["resumen"]
    assert r["informe"].endswith(".md")
