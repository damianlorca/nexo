# -*- coding: utf-8 -*-
"""T1007 (Bloque 11): menos propuestas de relleno en las investigaciones. Sin red ni Ollama (dobles)."""
from __future__ import annotations

import pytest

from nucleo import auditor, freno, plantillas_turno, revision, trabajo
from nucleo import tareas as T


@pytest.fixture
def almacen(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "x.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado")
    return tmp_path


def _linea(que, donde, v=3):
    return f"- QUE: {que} | DONDE: {donde} | VALOR: {v} | ESFUERZO: 2 | RIESGO: bajo: texto\n"


def _informe(*lineas):
    return "Informe.\n### PROPUESTAS IMPLEMENTABLES\n" + "".join(lineas)


def _inv():
    return T.anadir("Investigar la herramienta X", depende="ia", etiquetas=["cat:investigacion"], detalle="Evaluar X.")


def _prop(que, estado="propuesta", donde="router"):
    return T.anadir(f"[Propuesta de T1] {que}", detalle=f"QUE: {que}\nDONDE: {donde}\nVALOR: 3", estado=estado,
                    importancia=3, bloqueada_por="T999", etiquetas=["cat:propuesta", "prov:claude"])


# ------------------------------------------------------------------ 1) plantilla, tope y DONDE real
def test_la_plantilla_de_investigacion_pide_ninguna_como_normal_y_dos_como_mucho():
    for clave in ("investigacion", "investigacion_interna"):
        txt = trabajo.INSTRUCCION[clave]
        assert "como MUCHO 2" in txt and "NINGUNA: <por que>" in txt and "LO NORMAL" in txt
        assert "maximo 5" not in txt
    # los turnos de lotes (vigia, etc.) siguen con su formato de siempre
    assert "maximo 5" in trabajo.PROPUESTAS_FORMATO


def test_extraer_con_tope_y_donde_real():
    t = _informe(_linea("Proteger el router con un limite", "nucleo/router.py"),
                 _linea("Registrar URL y fecha de cada fuente", "proceso de investigacion"),
                 _linea("Ajustar el rol del programador", "roles/programador.md"),
                 _linea("Cambiar la bandeja", "interfaz"))
    r = revision.extraer_propuestas(t, tope=2, donde_real=True)
    assert [p["que"][:10] for p in r["propuestas"]] == ["Proteger e", "Ajustar el"]
    assert r["sobran"] == 1 and len(r["sin_evidencia"]) == 1 and "Registrar URL" in r["sin_evidencia"][0]
    # sin los parametros nuevos, comportamiento de siempre
    assert len(revision.extraer_propuestas(t)["propuestas"]) == 4


def test_ninguna_justificada_no_cuenta_como_fallo_del_auditor():
    ok, detalle = revision.comprobar_seccion("### PROPUESTAS IMPLEMENTABLES\nNINGUNA: NEXO ya cubre esto con sus reglas actuales\n")
    assert ok and "ninguna propuesta" in detalle
    exp = {"cat": "investigacion", "estado": "OK_ABSOLUTO", "llamadas": [],
           "final": "Informe\n### PROPUESTAS IMPLEMENTABLES\nNINGUNA: NEXO ya cubre esto con sus reglas actuales\n"}
    assert auditor.auditar(exp)["puntos"]["h_propuestas"]["ok"]


def test_una_investigacion_crea_como_mucho_dos_y_solo_con_donde_real(almacen):
    o = _inv()
    t = _informe(_linea("Limitar el reintento del router", "nucleo/router.py:40"),
                 _linea("Anotar la licencia de cada fuente", "proceso general"),
                 _linea("Cachear el catalogo de modelos", "nucleo/catalogo.py"),
                 _linea("Aislar paginas externas en el navegador", "extremidades/navegador.py"))
    res = revision.registrar_borrador(o["id"], "I_20261017_1000.md", texto=t)
    ques = [T.buscar(p["id"])["titulo"] for p in res["propuestas"]]
    assert len(ques) == 2 and "router" in ques[0] and "catalogo" in ques[1]
    nota = T.buscar(o["id"])["notas"][-1]["texto"]
    assert "sin evidencia" in nota.lower() or "Sin evidencia" in nota
    assert "tope" in nota


def test_los_lotes_de_turno_no_llevan_el_tope_de_investigacion(almacen):
    o = T.anadir("Lote del vigia", depende="ia", etiquetas=["cat:investigacion", "turno:lote", "plantilla:vigia"])
    temas = ("graficos de uso", "cifrado de copias", "avisos de bateria", "lectura de correo")
    t = _informe(*[_linea(f"Mejorar el modulo de {x}", "nucleo/router.py") for x in temas])
    res = revision.registrar_borrador(o["id"], "V_20261017_1000.md", texto=t)
    assert len(res["propuestas"]) == 4


# ------------------------------------------------------------------ 2) filtro de repetidas
def test_repetida_de_una_abierta_se_anota_en_ella_y_no_se_crea(almacen):
    vieja = _prop("Registrar la URL y la fecha de cada fuente consultada")
    o = _inv()
    t = _informe(_linea("Registrar la URL y la fecha de cada fuente consultada", "nucleo/investigacion.py"),
                 _linea("Cachear el catalogo de modelos de Ollama", "nucleo/catalogo.py"))
    res = revision.registrar_borrador(o["id"], "I_20261017_1100.md", texto=t)
    assert len(res["propuestas"]) == 1 and "catalogo" in res["propuestas"][0]["titulo"].lower()
    assert any("T1007" in n["texto"] and o["id"] in n["texto"] for n in T.buscar(vieja["id"])["notas"])
    assert "ya existian parecidas" not in res["revision"]["detalle"]   # hay una propuesta nueva: resumen normal
    assert "Parecidas a otras" in T.buscar(o["id"])["notas"][-1]["texto"]


def test_repetida_de_una_descartada_tampoco_se_crea(almacen):
    d = _prop("Aislar las paginas externas en un perfil de navegador aparte", estado="descartada")
    o = _inv()
    t = _informe(_linea("Aislar las paginas externas en un perfil de navegador aparte", "extremidades/navegador.py"))
    res = revision.registrar_borrador(o["id"], "I_20261017_1200.md", texto=t)
    assert res["propuestas"] == []
    assert "ya existian parecidas" in res["revision"]["detalle"]
    assert any("T1007" in n["texto"] for n in T.buscar(d["id"])["notas"])


def test_dos_iguales_en_el_mismo_informe_se_quedan_en_una(almacen):
    o = _inv()
    t = _informe(_linea("Guardar el hash de cada borrador generado", "nucleo/trabajo.py"),
                 _linea("Guardar el hash de cada borrador generado en disco", "nucleo/trabajo.py"))
    assert len(revision.registrar_borrador(o["id"], "I_20261017_1300.md", texto=t)["propuestas"]) == 1


def test_con_embeddings_manda_el_coseno_y_si_fallan_cae_a_lo_lexico(almacen):
    _prop("Poner un tope a los reintentos del router")
    tareas = T.cargar()["tareas"]
    nuevos = ["Limitar cuantas veces reintenta el enrutador", "Cachear el catalogo"]

    def emb(textos):   # vectores de juguete: los dos primeros textos apuntan al mismo sitio
        return [[1.0, 0.0] if ("reintent" in x.lower()) else [0.0, 1.0] for x in textos]

    r = freno.parecidas_a_existentes(nuevos, tareas=tareas, embeber=emb)
    assert r[0]["metodo"] == "embeddings" and r[0]["parecido"] >= 0.99 and r[0]["tipo"] == "abierta" and r[1] is None

    def roto(textos):
        raise ConnectionError("sin Ollama")

    # lexico: sin palabras en comun no hay parecido; con el mismo texto si
    r2 = freno.parecidas_a_existentes(["Poner un tope a los reintentos del router", "Cachear el catalogo"],
                                      tareas=tareas, embeber=roto)
    assert r2[0]["metodo"] == "lexico" and r2[1] is None


def test_si_el_filtro_falla_se_crean_todas(almacen, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("fallo")
    monkeypatch.setattr(freno, "parecidas_a_existentes", boom)
    o = _inv()
    t = _informe(_linea("Cambio uno del router", "nucleo/router.py"), _linea("Cambio dos del catalogo", "nucleo/catalogo.py"))
    assert len(revision.registrar_borrador(o["id"], "I_20261017_1400.md", texto=t)["propuestas"]) == 2


# ------------------------------------------------------------------ 3) freno F0 y el turno cola
def _llenar_propuestas(monkeypatch, n=3):
    monkeypatch.setattr(freno, "LIMITE_PROPUESTAS", 2)
    for i in range(n):
        _prop(f"Cambiar el router de forma distinta numero {i} con detalle")


def test_con_el_freno_puesto_la_cola_no_coge_investigaciones_pero_si_el_resto(almacen, monkeypatch):
    inv = _inv()
    red = T.anadir("Redactar el resumen semanal", depende="ia", etiquetas=["cat:redaccion"], detalle="x")
    ctx = {"plantilla": "cola", "texto": "", "tareas": [], "manual": False, "max_tareas": 5}
    assert {t["id"] for t in plantillas_turno._de_cola(ctx)} == {inv["id"], red["id"]}   # sin freno, como siempre
    _llenar_propuestas(monkeypatch)
    assert {t["id"] for t in plantillas_turno._de_cola(ctx)} == {red["id"]}
    assert plantillas_turno.candidatas(ctx) == 1
    # "Lanzar ya" (manual) no se frena
    assert {t["id"] for t in plantillas_turno._de_cola(dict(ctx, manual=True))} == {inv["id"], red["id"]}


def test_con_el_freno_y_solo_investigaciones_la_cola_dice_por_que_no_tiene_trabajo(almacen, monkeypatch):
    _inv()
    _llenar_propuestas(monkeypatch)
    ctx = {"plantilla": "cola", "texto": "", "tareas": [], "manual": False, "max_tareas": 5}
    assert plantillas_turno.candidatas(ctx) == 0
    assert "freno F0" in plantillas_turno.por_que_nada(ctx)


def test_la_regla_solo_afecta_a_la_plantilla_cola(almacen, monkeypatch):
    _llenar_propuestas(monkeypatch)
    assert freno.cola_sin_investigaciones("cola")[0]
    assert not freno.cola_sin_investigaciones("correcciones")[0]
    assert not freno.cola_sin_investigaciones("cola", manual=True)[0]
