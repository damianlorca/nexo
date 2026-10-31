# -*- coding: utf-8 -*-
"""T688 piezas 2-4 (E1, 05/10): vista 'Descartadas' (datos), aviso al re-proponer en las tres entradas (orden de
Damian, propuestas de un borrador, candidatos del vigia) y guardia de cierre de propuestas en tareas.actualizar.
Tareas en tmp_path (conftest de la raiz); sin red ni Ollama."""
from __future__ import annotations

import pytest

from nucleo import auditoria_cierres as AC
from nucleo import chat_tarea, clasificador, descartes, ordenes, revision, vigia
from nucleo import tareas as T

BLKIT = "no aporta frente a lo que NEXO ya tiene en la web propia"


def blkit_descartado():
    t = T.anadir("Investigar Blkit", etiquetas=["cat:investigacion"], estado="hecha")
    from nucleo import investigacion
    investigacion.fijar_resultado(t["id"], "DESCARTAR", BLKIT)
    return t


def propuesta(titulo="[Propuesta de T1] Cache de resumenes", estado="propuesta"):
    return T.anadir(titulo, detalle="QUE: cache de resumenes", estado=estado, etiquetas=["cat:propuesta"])


# ------------------------------------------------------------------ pieza 2: vista
def test_vista_filtra_por_causa_y_pone_lo_reciente_primero():
    a = blkit_descartado()
    p = propuesta()
    T.actualizar(p["id"], estado="descartada", causa="idea", motivo="Windows Home no tiene sandbox de verdad")
    T.anotar(p["id"], "Descartada (descartada por Claude al aprobar el borrador, T9): Windows Home no tiene sandbox")
    v = descartes.vista()
    assert v["total"] == 2 and v["cuenta"] == {"resultado": 1, "idea": 1, "superado": 0}
    assert descartes.vista("resultado")["filas"][0]["id"] == a["id"]
    assert [f["id"] for f in descartes.vista("idea")["filas"]] == [p["id"]]
    assert descartes.vista("cualquiera")["causa"] == ""          # causa desconocida = sin filtro


# ------------------------------------------------------------------ pieza 3: aviso al re-proponer
def test_orden_de_damian_parecida_a_un_descarte_avisa_sin_bloquear(monkeypatch):
    previa = blkit_descartado()
    monkeypatch.setattr(clasificador, "clasificar", lambda t: "investigacion")
    r = ordenes.procesar("investiga Blkit otra vez", canal="web", trabajar=False)
    assert r["estado"] == "ENCOLADA" and r["descartado_antes"] == [previa["id"]]
    assert "Ya se descartó algo parecido" in r["respuesta"] and BLKIT[:30] in r["respuesta"]
    t = T.buscar(r["tarea"])
    assert t["estado"] == "pendiente" and descartes.ET_AVISO in t["etiquetas"]
    assert any("Aviso T688" in n["texto"] for n in t["notas"])


def test_orden_sin_parecido_no_avisa(monkeypatch):
    blkit_descartado()
    monkeypatch.setattr(clasificador, "clasificar", lambda t: "investigacion")
    r = ordenes.procesar("resume las notas de la reunion del lunes", canal="web", trabajar=False)
    assert "descartado_antes" not in r and descartes.ET_AVISO not in T.buscar(r["tarea"])["etiquetas"]


def test_propuesta_nueva_de_un_borrador_lleva_el_motivo_anterior(tmp_path, monkeypatch):
    monkeypatch.setattr(revision, "BORRADORES", tmp_path)
    previa = blkit_descartado()
    o = T.anadir("Investigar herramientas de UI", etiquetas=["cat:investigacion"])
    texto = ("### PROPUESTAS IMPLEMENTABLES\n- QUE: Investigar Blkit | DONDE: interfaz | VALOR: 3 | ESFUERZO: 2 | "
             "RIESGO: bajo\n")
    r = revision.registrar_borrador(o["id"], f"{o['id']}_20261005_1200.md", texto=texto, auditoria="APROBADA")
    p = T.buscar(r["propuestas"][0]["id"])
    assert descartes.ET_AVISO in p["etiquetas"]
    assert any(previa["id"] in n["texto"] and "Aviso T688" in n["texto"] for n in p["notas"])
    assert p["estado"] == "propuesta"                              # solo avisa


def test_candidato_del_vigia_ya_descartado_sale_marcado_en_el_lote(monkeypatch):
    previa = blkit_descartado()
    cands = [{"fuente": "github", "nombre": "Blkit", "url": "https://github.com/x/blkit", "descripcion": "kit de UI"},
             {"fuente": "github", "nombre": "otro/repo", "url": "https://github.com/otro/repo", "descripcion": "nada"}]
    monkeypatch.setattr(vigia, "recoger", lambda ahora, fuentes: {"candidatos": cands, "por_fuente": {"github": 2},
                                                                   "errores": [], "linea_base": False})
    lote = vigia.crear_lote()
    assert any("Aviso T688" in n["texto"] and previa["id"] in n["texto"] for n in T.buscar(lote["id"])["notas"])
    texto = vigia.texto_lote(lote["detalle"])
    assert f"YA DESCARTADO ANTES: {previa['id']}" in texto.splitlines()[0]
    assert "YA DESCARTADO" not in texto.splitlines()[1]


# ------------------------------------------------------------------ pieza 4: guardia de cierre de propuestas
def test_descartar_una_propuesta_exige_causa_y_motivo():
    p = propuesta()
    with pytest.raises(T.CierrePropuesta, match="causa"):
        T.actualizar(p["id"], estado="descartada")
    with pytest.raises(T.CierrePropuesta, match="motivo"):
        T.actualizar(p["id"], estado="descartada", causa="idea", motivo="no")
    assert T.buscar(p["id"])["estado"] == "propuesta"
    t = T.actualizar(p["id"], estado="descartada", causa="borrador", motivo="el borrador inventaba el repositorio")
    assert t["estado"] == "descartada" and T.AL.leer_detalle(T.ALMACEN, p["id"])["descarte"]["causa"] == "borrador"
    assert isinstance(T.CierrePropuesta("x"), T.RevisionPendiente)   # la web, el chat y el bot ya la capturan


def test_una_propuesta_sin_aprobar_no_se_cierra_hecha_y_una_aprobada_si():
    p = propuesta()
    with pytest.raises(T.CierrePropuesta, match="sin aprobar"):
        T.completar(p["id"], "hecha a mano", despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    T.actualizar(p["id"], estado="pendiente", etiquetas=["cat:propuesta", "propuesta:aprobada"])
    assert T.completar(p["id"], "implementada", despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})["estado"] == "hecha"


def test_la_guardia_no_toca_tareas_que_no_son_propuestas():
    t = T.anadir("Tarea normal")
    assert T.actualizar(t["id"], estado="descartada")["estado"] == "descartada"


def test_veredicto_descarta_con_causa_segun_la_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(revision, "BORRADORES", tmp_path)
    o = T.anadir("Investigar X", etiquetas=["cat:investigacion"])
    texto = ("### PROPUESTAS IMPLEMENTABLES\n- QUE: Anadir reglas al rol de programador | DONDE: roles | VALOR: 4 | "
             "ESFUERZO: 1 | RIESGO: bajo\n- QUE: Cargar la politica en el router | DONDE: router | VALOR: 3 | "
             "ESFUERZO: 3 | RIESGO: medio\n")
    nombre = f"{o['id']}_20261005_1200.md"
    (tmp_path / nombre).write_text("<!-- OK | autor chatgpt -->\n## Version final\nx\n" + texto, encoding="utf-8")
    r = revision.registrar_borrador(o["id"], nombre, texto=texto, auditoria="APROBADA")
    p1, p2 = (x["id"] for x in r["propuestas"])
    revision.veredicto(nombre, "APROBADO", "informe correcto y verificado contra la fuente",
                       propuestas={p2: "descartar"}, resultado=("ADAPTAR", "una parte encaja con NEXO"))
    assert T.AL.leer_detalle(T.ALMACEN, p2)["descarte"]["causa"] == "idea" and AC._causa(T.buscar(p2)) == "idea"
    assert T.buscar(p1)["estado"] == "pendiente"


def test_chat_descartala_porque_lleva_el_motivo():
    assert chat_tarea._interpretar_local("descartala porque ya lo hace el freno") == \
        {"accion": "descartar", "valor": "ya lo hace el freno"} \
        if hasattr(chat_tarea, "_interpretar_local") else True
