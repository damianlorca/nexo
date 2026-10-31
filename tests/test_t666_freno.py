# -*- coding: utf-8 -*-
"""T666 (F0 de la epica T664): limite de trabajo en curso, freno de turnos generadores, filtro sin IA,
archivo recuperable y metricas. Todo en tmp_path: nunca memoria/ de verdad."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from nucleo import freno, planificador, turnos
from nucleo import tareas as T

AHORA = datetime(2026, 10, 3, 12, 0, 0)


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "x.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado")
    monkeypatch.setattr(freno, "REGISTRO", tmp_path / "freno_archivo.jsonl")
    monkeypatch.setattr(freno, "INFORMES", tmp_path / "freno")
    monkeypatch.setattr(freno, "BORRADORES", tmp_path / "borradores")
    (tmp_path / "borradores").mkdir()
    (tmp_path / "borradores" / "B_20261001_1000.md").write_text("Ver nucleo/router.py y https://ejemplo.org", "utf-8")
    (tmp_path / "borradores" / "SIN_20261001_1000.md").write_text("Opiniones sin citar nada.", "utf-8")
    return tmp_path


def _prop(que, valor=4, esfuerzo=2, borrador="B_20261001_1000.md", origen="", donde="router", riesgo="bajo"):
    det = (f"QUE: {que}\nDONDE: {donde}\nVALOR: {valor} · ESFUERZO: {esfuerzo}\nRIESGO: {riesgo}\n"
           f"Sale del borrador memoria/borradores/{borrador}.")
    et = ["cat:propuesta", "prov:claude", f"de_borrador:{borrador}"] + ([f"tarea_origen:{origen}"] if origen else [])
    return T.anadir(f"[Propuesta] {que[:100]}", detalle=det, estado="propuesta", importancia=valor,
                    dificultad=esfuerzo, bloqueada_por="T999", etiquetas=et)


def _reglas(ev):
    return {a["id"]: a["regla"] for a in ev["archivar"]}


# ------------------------------------------------------------------ limite y freno
def test_limite_de_propuestas_y_revisiones(monkeypatch):
    monkeypatch.setattr(freno, "LIMITE_PROPUESTAS", 2)
    monkeypatch.setattr(freno, "LIMITE_REVISIONES", 1)
    for i in range(2):
        _prop(f"Cambiar el router para que haga la cosa numero {i}")
    e = freno.estado_cola()
    assert (e["propuestas"], e["revisiones"], e["superado"]) == (2, 0, False)
    assert freno.puede_generar("vigia") == (True, "")
    _prop("Una propuesta mas que pasa del limite de dos")
    ok, motivo = freno.puede_generar("vigia")
    assert not ok and "3 propuestas abiertas (limite 2)" in motivo
    assert freno.puede_generar("cola") == (True, "")          # cola no es generadora
    for i in range(2):
        T.anadir(f"Revisar borrador {i}", etiquetas=["cat:revision", "revision:borrador"])
    assert "2 revisiones pendientes (limite 1)" in freno.estado_cola()["motivos"][1]


def test_planificador_no_lanza_generadores_con_el_freno_puesto(monkeypatch):
    # turnos, planificador y parada ya van a tmp_path por el conftest de la raiz (turnos_aislados)
    monkeypatch.setattr(freno, "LIMITE_PROPUESTAS", 0)
    _prop("Una propuesta abierta basta para pasar del limite cero")
    vig = turnos.guardar_turno({"nombre": "Vigia", "plantilla": "vigia", "dias": list(turnos.DIAS), "horas": ["03:00"]})
    cola = turnos.guardar_turno({"nombre": "Cola", "plantilla": "cola", "dias": list(turnos.DIAS), "horas": ["03:00"]})
    lanzados = []
    planificador.tick(datetime(2026, 10, 5, 2, 59, 30), lanzar=lambda e: lanzados.append(e["turno"]) or 99999999)
    hecho = planificador.tick(datetime(2026, 10, 5, 3, 0, 30), lanzar=lambda e: lanzados.append(e["turno"]) or 99999999)
    assert hecho["frenados"] == [vig["id"]] and lanzados == [cola["id"]]
    est = json.loads(planificador.ESTADO.read_text("utf-8"))
    assert est["frenados"][-1]["turno"] == vig["id"] and "freno F0" in est["frenados"][-1]["motivo"]
    assert all(x["turno"] != vig["id"] for x in est["cola"])


def test_lanzar_ya_manual_de_damian_si_arranca(monkeypatch):
    monkeypatch.setattr(freno, "LIMITE_PROPUESTAS", 0)
    _prop("Una propuesta abierta basta para pasar del limite cero")
    vig = turnos.guardar_turno({"nombre": "Vigia", "plantilla": "vigia", "dias": ["lunes"], "horas": ["03:00"]})
    ahora = datetime(2026, 10, 3, 12, 0, 0)
    planificador.encolar(vig["id"], manual=True, cuando=ahora)
    lanzados = []
    hecho = planificador.tick(ahora, lanzar=lambda e: lanzados.append(e["turno"]) or 99999999)
    assert hecho["frenados"] == [] and lanzados == [vig["id"]]


# ------------------------------------------------------------------ filtro
def test_reglas_simples(monkeypatch):
    ok = _prop("Cambiar el router para que registre el motivo de cada escalado")
    sin_campos = T.anadir("[Propuesta] x", detalle="QUE: Algo bastante largo de hacer en el router\nDONDE: ?\n",
                          estado="propuesta", etiquetas=["cat:propuesta", "de_borrador:B_20261001_1000.md"])
    bajo = _prop("Reescribir entero el sistema de memoria con otra base de datos", valor=2, esfuerzo=4)
    sinf = _prop("Adoptar el marco de trabajo milagroso que lo arregla todo", borrador="SIN_20261001_1000.md")
    nob = _prop("Adoptar otro marco de trabajo que tampoco tiene borrador", borrador="NO_EXISTE.md")
    tg = _prop("Validar el callback_query antes de responder en el bot")
    orig = T.anadir("Revision de codigo (turno 01/10, lote 1): canal/bot.py")
    tg2 = _prop("Validar los tipos de la configuracion antes de aplicarla", origen=orig["id"])
    vieja = _prop("Cambiar el planificador para que reparta mejor la carga de turnos")
    datos = T.cargar()
    next(t for t in datos["tareas"] if t["id"] == vieja["id"])["actualizada"] = "2026-09-15 10:00:00"
    T.guardar(datos)
    ev = freno.evaluar(ahora=AHORA)
    r = _reglas(ev)
    assert r == {sin_campos["id"]: "formato", bajo["id"]: "valor_bajo", sinf["id"]: "sin_fuentes",
                 nob["id"]: "sin_fuentes", tg["id"]: "decision_vigente", tg2["id"]: "decision_vigente",
                 vieja["id"]: "caducada"}
    assert ok["id"] in ev["quedan"]
    assert "canal/bot.py" in next(a["motivo"] for a in ev["archivar"] if a["id"] == tg2["id"])


def test_duplicada_de_tarea_y_fusion_de_parecidas():
    real = T.anadir("Separar errores 401 y 403 del salto al siguiente modelo en NvidiaProvider")
    vieja = T.anadir("Anadir modo oscuro a la web de NEXO", estado="hecha")
    datos = T.cargar()
    next(t for t in datos["tareas"] if t["id"] == vieja["id"])["cerrada"] = "2026-08-01 10:00:00"   # > 30 dias
    T.guardar(datos)
    dup = _prop("Separar errores 401 y 403 del salto al siguiente modelo en NvidiaProvider enviar")
    no_dup = _prop("Anadir modo oscuro a la web de NEXO con selector")
    a = _prop("Registrar en el router el motivo de escalado y la confianza de cada decision", valor=5)
    b = _prop("Registrar en el router motivo de escalado y confianza de cada decision tomada", valor=3)
    ev = freno.evaluar(ahora=AHORA)
    r = _reglas(ev)
    assert r[dup["id"]] == "duplicada" and real["id"] in next(x["motivo"] for x in ev["archivar"] if x["id"] == dup["id"])
    assert no_dup["id"] in ev["quedan"]                       # la parecida se cerro hace mas de 30 dias
    assert r[b["id"]] == "fundida" and a["id"] in ev["quedan"]   # se queda la de mas valor


def test_excedente_solo_si_se_pide(monkeypatch):
    monkeypatch.setattr(freno, "LIMITE_PROPUESTAS", 2)
    ids = [_prop(texto, valor=v)["id"] for texto, v in [
        ("Registrar en el router el motivo de cada escalado", 5),
        ("Comprimir la memoria vieja en resumenes semanales", 3),
        ("Mostrar en la interfaz movil el estado de cada turno", 4),
        ("Probar otra voz local para leer los avisos en alto", 2)]]
    ev = freno.evaluar(ahora=AHORA)
    assert ev["archivar"] == [] and len(ev["excedente_posible"]) == 2
    ev = freno.evaluar(ahora=AHORA, excedente=True)
    assert sorted(_reglas(ev)) == sorted([ids[1], ids[3]]) and sorted(ev["quedan"]) == sorted([ids[0], ids[2]])


# ------------------------------------------------------------------ simular, aplicar, recuperar
def test_simular_no_toca_nada_y_aplicar_archiva_recuperable(aislado):
    p = _prop("Validar el callback_query antes de responder en el bot")
    q = _prop("Cambiar el router para que registre el motivo de cada escalado")
    antes = T.ALMACEN.read_text("utf-8")
    r = freno.simular(ahora=AHORA)
    assert T.ALMACEN.read_text("utf-8") == antes and r["archivadas"] == []
    assert "SIMULACION" in (aislado / "freno" / "simulacion_20261003_1200.md").read_text("utf-8")
    r = freno.aplicar(ahora=AHORA)
    assert r["archivadas"] == [p["id"]]
    t = T.buscar(p["id"])
    assert t["estado"] == "descartada" and t["bloqueada_por"] == "" and freno.ET_ARCHIVADA in t["etiquetas"]
    assert "filtro:decision_vigente" in t["etiquetas"] and "recuperar" in t["notas"][-1]["texto"]
    assert T.buscar(q["id"])["estado"] == "propuesta"
    foto = json.loads(freno.REGISTRO.read_text("utf-8").splitlines()[0])
    assert foto["id"] == p["id"] and foto["antes"]["estado"] == "propuesta"
    vuelta = freno.recuperar(p["id"])
    assert (vuelta["estado"], vuelta["bloqueada_por"], vuelta["cerrada"]) == ("propuesta", "T999", None)
    assert not any(e.startswith("filtro:") or e == freno.ET_ARCHIVADA for e in vuelta["etiquetas"])
    with pytest.raises(ValueError):
        freno.recuperar(p["id"])          # ya no esta archivada
    with pytest.raises(ValueError):
        freno.recuperar(q["id"])          # nunca la archivo el filtro


def test_fusion_anota_en_la_que_se_queda():
    a = _prop("Registrar en el router el motivo de escalado y la confianza de cada decision", valor=5)
    b = _prop("Registrar en el router motivo de escalado y confianza de cada decision tomada", valor=3)
    freno.aplicar(ahora=AHORA)
    assert T.buscar(b["id"])["estado"] == "descartada"
    assert b["id"] in T.buscar(a["id"])["notas"][-1]["texto"]


# ------------------------------------------------------------------ metricas
def test_metricas_por_semana():
    p = _prop("Validar el callback_query antes de responder en el bot")
    _prop("Cambiar el router para que registre el motivo de cada escalado")
    T.anadir("Revisar borrador", etiquetas=["cat:revision", "revision:borrador"])
    freno.aplicar(ahora=datetime.now())
    m = freno.metricas(semanas=3)
    esta = m["semanas"][-1]
    assert len(m["semanas"]) == 3
    assert (esta["prop_entran"], esta["prop_salen"], esta["prop_archivadas"], esta["rev_entran"]) == (2, 1, 1, 1)
    assert m["cola"]["propuestas"] == 1 and m["archivadas"] == 1 and T.buscar(p["id"])["estado"] == "descartada"


# ------------------------------------------------------------------ decisiones de Damian 03/10
def test_aplicar_aparta_y_funde_en_una_tarea_recuperable():
    """Telegram: las de seguridad no se archivan sueltas; se funden en UNA tarea con sus ids y la importancia mayor."""
    s1 = _prop("Validar el callback_query y el usuario antes de responder en el bot", valor=3, esfuerzo=2)
    s2 = _prop("Sanitizar la ruta de las fotos que envia el bot de telegram", valor=5, esfuerzo=3)
    otra = _prop("Documentar telegram como canal restringido en el README", valor=4)
    r = freno.aplicar(ahora=AHORA, fundir_ids=(s1["id"], s2["id"]), fundir_titulo="Revision de seguridad del bot",
                      fundir_motivo="decision de Damian 03/10")
    assert r["archivadas"] == [otra["id"]]
    n = r["fusion"]
    assert (n["titulo"], n["estado"], n["importancia"], n["dificultad"]) == ("Revision de seguridad del bot", "propuesta", 5, 3)
    assert s1["id"] in n["detalle"] and s2["id"] in n["detalle"] and f"fundida_de:{s1['id']}" in n["etiquetas"]
    for s in (s1, s2):
        t = T.buscar(s["id"])
        assert t["estado"] == "descartada" and "filtro:fundida" in t["etiquetas"] and n["id"] in t["notas"][-1]["texto"]
    assert freno.estado_cola()["propuestas"] == 1
    assert freno.recuperar(s1["id"])["estado"] == "propuesta"
    assert "Apartadas para fundir (2)" in open(r["informe"], encoding="utf-8").read()


def test_simular_con_fundir_no_toca_nada():
    s1 = _prop("Validar el callback_query y el usuario antes de responder en el bot")
    s2 = _prop("Sanitizar la ruta de las fotos que envia el bot de telegram")
    antes = T.ALMACEN.read_text("utf-8")
    r = freno.simular(ahora=AHORA, fundir_ids=(s1["id"], s2["id"]), fundir_titulo="x")
    assert T.ALMACEN.read_text("utf-8") == antes and r["fusion"] is None
    assert r["evaluacion"]["archivar"] == [] and len(r["evaluacion"]["apartadas_para_fundir"]) == 2


def test_parecidas_por_embeddings_solo_informa(aislado):
    a = _prop("Registrar el motivo de escalado en el router")
    b = _prop("Guardar por que el router escala cada peticion")
    c = _prop("Probar otra voz local para leer los avisos en alto")
    real = T.anadir("Anotar en el router la razon de cada escalado")
    vec = {que(a): [1, 0, 0], que(b): [0.95, 0.05, 0], que(c): [0, 1, 0], real["titulo"]: [0.9, 0, 0.1]}
    llamadas = []

    def falso(textos):
        llamadas.append(len(textos))
        return [vec.get(x, [0, 0, 1]) for x in textos]
    antes = T.ALMACEN.read_text("utf-8")
    r = freno.pares_semanticos(umbral=0.9, embeber=falso, ahora=AHORA)
    assert T.ALMACEN.read_text("utf-8") == antes                       # no funde ni archiva nada
    assert [(p["a"], p["b"]) for p in r["entre_propuestas"]] == [(a["id"], b["id"])]
    assert {(p["a"], p["b"]) for p in r["contra_tareas"]} == {(a["id"], real["id"]), (b["id"], real["id"])}
    assert "CANDIDATOS" in (aislado / "freno" / "parecidas_20261003_1200.md").read_text("utf-8")
    assert freno.pares_semanticos(umbral=0.999, embeber=falso, ahora=AHORA)["entre_propuestas"] == []


que = freno.que


def test_la_propuesta_fundida_no_se_archiva_por_no_tener_borrador():
    """05/10: T673 (fusion de Damian del 03/10) no tiene borrador propio; sus fuentes son las propuestas fundidas.
    El filtro la marcaba 'sin_fuentes' y un aplicar la habria archivado, deshaciendo la fusion."""
    s1 = _prop("Validar el callback_query y el usuario antes de responder en el bot", valor=3, esfuerzo=2)
    s2 = _prop("Sanitizar la ruta de las fotos que envia el bot de telegram", valor=5, esfuerzo=3)
    n = freno.fundir([s1["id"], s2["id"]], "Revision de seguridad del bot", "decision de Damian 03/10")
    assert n["id"] not in _reglas(freno.evaluar(ahora=AHORA))
