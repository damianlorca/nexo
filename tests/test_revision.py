# -*- coding: utf-8 -*-
"""T192: circuito cerrado borrador de NEXO -> revision de Claude -> propuestas. Sin red ni Chrome."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from nucleo import auditor, avisos, evidencias, revision, trabajo
from nucleo import tareas as T
from tests.test_ok_absoluto import CIERRE_OK, MODO_OK, REV_OK, Api, Web  # noqa: F401

DOS = ("### PROPUESTAS IMPLEMENTABLES\n"
       "- QUE: Anadir las 4 reglas de coding al rol de programador | DONDE: roles y prompts | VALOR: 4 | "
       "ESFUERZO: 1 | RIESGO: bajo: solo texto\n"
       "- **QUE:** Cargar la politica solo en tareas de codigo | **DONDE:** router de modelos | **VALOR:** 3 | "
       "**ESFUERZO:** 3 | **RIESGO:** medio: puede no activarse cuando toca\n")
INFORME = "ENTENDIMIENTO:\nSe pide X.\n### INFORME\n" + "1) Que es: X es un repositorio de reglas. " * 20


@pytest.fixture
def cola(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "x.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado")
    monkeypatch.setattr(trabajo, "BORRADORES", tmp_path / "borradores")
    monkeypatch.setattr(revision, "BORRADORES", tmp_path / "borradores")
    monkeypatch.setattr(trabajo, "_web", lambda: True)
    return T.anadir("Investigar las skills de X", depende="ia", etiquetas=["cat:investigacion"], detalle="Evaluar X.")


def _delegar(monkeypatch, final: str):
    autor = Web("chatgpt", INFORME + "\n" + final, "### AUTOAUDITORIA\n" + CIERRE_OK.split("### AUTOAUDITORIA\n")[1])
    rev = Api("gemini_api", REV_OK, REV_OK)
    monkeypatch.setattr(trabajo, "_generadores", lambda cat: [autor])
    monkeypatch.setattr(trabajo, "_revisores", lambda nombre: [rev])
    [fila] = trabajo.ciclo(max_tareas=1)
    return fila


def _t(tid):
    return next(t for t in T.cargar()["tareas"] if t["id"] == tid)


# ------------------------------------------------------------------ 5) el test de Damian
def test_borrador_con_dos_propuestas_crea_revision_y_dos_propuestas_enlazadas(cola, monkeypatch):
    fila = _delegar(monkeypatch, DOS)
    assert fila["auditoria"] == "APROBADA", fila
    nombre = fila["archivo"].rsplit("/", 1)[-1]
    rev = _t(fila["revision_claude"])
    assert revision.ET_REVISION in rev["etiquetas"] and "prov:claude" in rev["etiquetas"]
    assert f"tarea_origen:{cola['id']}" in rev["etiquetas"] and f"de_borrador:{nombre}" in rev["etiquetas"]
    assert len(fila["propuestas"]) == 2
    props = [_t(i) for i in fila["propuestas"]]
    for p in props:
        assert p["estado"] == "propuesta" and p["bloqueada_por"] == rev["id"]
        assert f"tarea_origen:{cola['id']}" in p["etiquetas"] and f"de_borrador:{nombre}" in p["etiquetas"]
    assert (props[0]["importancia"], props[0]["dificultad"]) == (4, 1)
    assert (props[1]["importancia"], props[1]["dificultad"]) == (3, 3)
    assert "RIESGO: medio" in props[1]["detalle"]
    # la origen espera el veredicto, y NEXO no la vuelve a coger
    origen = _t(cola["id"])
    assert f"revision_claude:{rev['id']}" in origen["etiquetas"]
    assert cola["id"] not in [t["id"] for t in trabajo.candidatas()]
    # las propuestas no las trabaja nadie
    assert T.siguiente()["id"] == rev["id"]
    # aparece en la cola con sus dos propuestas
    c = revision.cola()
    assert [r["id"] for r in c["revisiones"]] == [rev["id"]] and c["revisiones"][0]["propuestas"] == 2
    assert {p["id"] for p in c["propuestas"]} == set(fila["propuestas"])
    # el borrador lo enlaza y el handoff tambien
    texto = (trabajo.BORRADORES / nombre).read_text(encoding="utf-8")
    assert f"Revision de Claude: {rev['id']}" in texto and fila["propuestas"][1] in texto
    assert "## Propuestas de NEXO" in T.render_md() and "[p]" in T.render_md()


def test_la_origen_no_se_cierra_sin_veredicto(cola, monkeypatch):
    fila = _delegar(monkeypatch, DOS)
    with pytest.raises(T.RevisionPendiente):
        T.completar(cola["id"], "cerrar a mano", despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    with pytest.raises(ValueError):
        evidencias.cerrar(cola["id"], "tampoco por aqui", evidencia="test ejecutado y salio bien")
    assert _t(cola["id"])["estado"] == "pendiente"
    assert T._cli(["hecha", cola["id"]]) == 2
    assert _t(fila["revision_claude"])["estado"] == "pendiente"


# ------------------------------------------------------------------ 4) veredictos
def test_aprobado_pasa_propuestas_a_pendiente_y_cierra_con_evidencia(cola, monkeypatch):
    fila = _delegar(monkeypatch, DOS)
    p1, p2 = fila["propuestas"]
    r = revision.veredicto(fila["archivo"], "APROBADO", "informe correcto y verificado contra el repo",
                           propuestas={p1: 4, p2: "descartar"}, resultado=("DESCARTAR", "no se adopta: NEXO ya tiene reglas equivalentes"))
    assert r["aprobadas"] == [p1] and r["descartadas"] == [p2]
    assert _t(p1)["estado"] == "pendiente" and _t(p1)["urgencia"] == 4 and not _t(p1)["bloqueada_por"]
    assert _t(p2)["estado"] == "descartada"
    origen, rev = _t(cola["id"]), _t(fila["revision_claude"])
    assert origen["estado"] == "hecha" and origen["testeado"] and "revisado:aprobado" in origen["etiquetas"]
    assert not revision.revision_pendiente(origen)
    assert rev["estado"] == "hecha" and rev["testeado"]
    ev = [json.loads(x) for x in evidencias.almacen().read_text(encoding="utf-8").splitlines()]
    assert {e["tarea"] for e in ev if e["tipo"] == "revision"} == {cola["id"], rev["id"]}
    assert revision.cola()["pendientes"] == 0


def test_aprobado_sin_prioridad_la_saca_del_valor(cola, monkeypatch):
    fila = _delegar(monkeypatch, DOS)
    revision.veredicto(fila["archivo"], "APROBADO", "informe correcto y verificado contra el repo", resultado=("DESCARTAR", "no se adopta: NEXO ya tiene reglas equivalentes"))
    p1, p2 = fila["propuestas"]
    assert (_t(p1)["estado"], _t(p1)["urgencia"]) == ("pendiente", 3)   # valor 4
    assert (_t(p2)["estado"], _t(p2)["urgencia"]) == ("pendiente", 2)   # valor 3


def test_descartado_de_un_lote_cierra_origen_y_propuestas_con_motivo(cola, monkeypatch):
    # un lote de turno (turno:lote) no es una investigacion (T674): DESCARTADO sigue cerrando su origen
    T.actualizar(cola["id"], etiquetas=cola["etiquetas"] + ["turno:lote"])
    fila = _delegar(monkeypatch, DOS)
    revision.veredicto(fila["archivo"], "DESCARTADO", "no aporta nada a NEXO frente a lo que ya hay")
    assert _t(cola["id"])["estado"] == "descartada"
    assert all(_t(p)["estado"] == "descartada" for p in fila["propuestas"])
    assert "no aporta nada" in _t(cola["id"])["notas"][-1]["texto"]


def test_descartado_de_una_investigacion_es_borrador_malo_y_no_la_cierra(cola, monkeypatch):
    """T674: DESCARTADO juzga el borrador; la investigacion sigue viva y NEXO la vuelve a coger."""
    fila = _delegar(monkeypatch, DOS)
    revision.veredicto(fila["archivo"], "DESCARTADO", "el borrador no cita ninguna fuente primaria")
    origen = _t(cola["id"])
    assert origen["estado"] == "pendiente" and origen["cerrada"] is None and origen["borradores_malos"] == 1
    assert all(_t(p)["estado"] == "descartada" for p in fila["propuestas"])
    assert any("no cita ninguna fuente" in n["texto"] for n in origen["notas"])
    assert cola["id"] in [t["id"] for t in trabajo.candidatas()]


def test_rehacer_devuelve_la_tarea_a_nexo_con_instrucciones(cola, monkeypatch):
    fila = _delegar(monkeypatch, DOS)
    with pytest.raises(ValueError):
        revision.veredicto(fila["archivo"], "REHACER", "faltan fuentes primarias del repositorio")
    revision.veredicto(fila["archivo"], "REHACER", "faltan fuentes primarias del repositorio",
                       instrucciones="cita el fichero LICENSE y el SKILL.md con su URL")
    origen = _t(cola["id"])
    assert origen["estado"] == "pendiente" and trabajo.HECHO not in origen["etiquetas"]
    assert "CORRECCIONES PEDIDAS EN LA REVISION: cita el fichero LICENSE" in origen["detalle"]
    assert cola["id"] in [t["id"] for t in trabajo.candidatas()]
    assert "CORRECCIONES PEDIDAS" in trabajo._prompt_gen(origen, "investigacion")
    assert all(_t(p)["estado"] == "descartada" for p in fila["propuestas"])


def test_veredicto_invalido_no_toca_nada(cola, monkeypatch):
    fila = _delegar(monkeypatch, DOS)
    for args in (("OK", "motivo suficientemente largo"), ("APROBADO", "bien")):
        with pytest.raises(ValueError):
            revision.veredicto(fila["archivo"], *args)
    with pytest.raises(ValueError):
        revision.veredicto(fila["archivo"], "APROBADO", "motivo suficientemente largo", propuestas={"T999": 3})
    with pytest.raises(ValueError):
        revision.veredicto("no_existe.md", "APROBADO", "motivo suficientemente largo")
    assert all(_t(p)["estado"] == "propuesta" for p in fila["propuestas"])
    assert _t(fila["revision_claude"])["estado"] == "pendiente"


# ------------------------------------------------------------------ 1) plantilla + auditor (h)
def test_la_plantilla_de_investigacion_pide_las_propuestas():
    assert "PROPUESTAS IMPLEMENTABLES" in trabajo.INSTRUCCION["investigacion"]
    assert "NINGUNA: <por que>" in trabajo.INSTRUCCION["investigacion"]
    prompt = trabajo._prompt_gen({"titulo": "Investigar X", "detalle": ""}, "investigacion")
    assert auditor.revisar_prompt(prompt, "generar") == []


def test_sin_seccion_de_propuestas_la_auditoria_bloquea(cola, monkeypatch):
    fila = _delegar(monkeypatch, "")
    assert fila["auditoria"] == "BLOQUEADA" and "h_propuestas" in fila["fallos_auditoria"]
    # aun asi entra en la cola de Claude, sin propuestas y diciendo por que
    rev = _t(fila["revision_claude"])
    assert fila["propuestas"] == [] and "SIN propuestas legibles" in rev["detalle"]


def test_ninguna_justificada_vale_y_sin_justificar_no(cola, monkeypatch):
    ok = _delegar(monkeypatch, "### PROPUESTAS IMPLEMENTABLES\nNINGUNA: NEXO ya tiene reglas equivalentes en CLAUDE.md\n")
    assert ok["auditoria"] == "APROBADA" and ok["propuestas"] == []
    assert revision.comprobar_seccion("### PROPUESTAS IMPLEMENTABLES\nNINGUNA\n")[0] is False


def test_el_punto_h_no_se_aplica_a_redaccion():
    exp = {"cat": "redaccion", "estado": "OK_ABSOLUTO", "final": "texto sin propuestas", "llamadas": []}
    assert "h_propuestas" not in auditor.auditar(exp)["puntos"]


@pytest.mark.parametrize("texto,n,problemas", [
    (DOS, 2, []),
    ("### PROPUESTAS IMPLEMENTABLES\n1. QUE: a\n   DONDE: b\n   VALOR: 5\n   ESFUERZO: 2\n   RIESGO: alto\n"
     "2) QUE: c | DONDE: d | VALOR: 2 | ESFUERZO: 4 | RIESGO: bajo\n\nAUTOAUDITORIA\nCIERRE: OK ABSOLUTO\n", 2, []),
    ("### PROPUESTAS IMPLEMENTABLES\n- QUE: a | DONDE: b | VALOR: alto | ESFUERZO: 2 | RIESGO: bajo\n", 1,
     ["propuesta 1 sin valor"]),
    ("informe sin la seccion", 0, ["falta la seccion PROPUESTAS IMPLEMENTABLES"]),
])
def test_extraer_propuestas(texto, n, problemas):
    r = revision.extraer_propuestas(texto)
    assert len(r["propuestas"]) == n and r["problemas"] == problemas


def test_version_final_del_md():
    md = "# T1\n## Auditoria: X\n- a\n## Version final\nel informe\n### PROPUESTAS IMPLEMENTABLES\n- QUE: a\n## Ronda 1\nrev\n"
    v = revision.version_final(md)
    assert "el informe" in v and "PROPUESTAS" in v and "rev" not in v


# ------------------------------------------------------------------ registro: idempotente y sustitucion
def test_registrar_es_idempotente_y_el_borrador_nuevo_sustituye_al_viejo(cola, tmp_path):
    carpeta = tmp_path / "borradores"
    carpeta.mkdir()
    (carpeta / "T001_20260920_1000.md").write_text("## Version final\n" + DOS, encoding="utf-8")
    a = revision.registrar_borrador(cola["id"], "T001_20260920_1000.md")
    b = revision.registrar_borrador(cola["id"], "T001_20260920_1000.md")
    assert a["nueva"] and not b["nueva"] and a["revision"]["id"] == b["revision"]["id"] and len(a["propuestas"]) == 2
    c = revision.registrar_borrador(cola["id"], "memoria/borradores/T001_20260921_1000.md", texto=DOS)
    assert c["sustituida"] == a["revision"]["id"]
    assert _t(a["revision"]["id"])["estado"] == "descartada"
    assert all(_t(p["id"])["estado"] == "descartada" for p in a["propuestas"])
    assert f"revision_claude:{c['revision']['id']}" in _t(cola["id"])["etiquetas"]
    assert [r["id"] for r in revision.cola()["revisiones"]] == [c["revision"]["id"]]


# ------------------------------------------------------------------ 3) cola y aviso push
TEMAS = ("graficos de uso", "cifrado de copias", "avisos de bateria", "lectura de correo", "voz del asistente")


def _dos_distintas(n):
    """T1007: el filtro de repetidas no deja crear la misma propuesta en cada borrador; cada uno trae las suyas."""
    return ("### PROPUESTAS IMPLEMENTABLES\n"
            f"- QUE: Mejorar el modulo de {TEMAS[n]} | DONDE: router de modelos | VALOR: 4 | ESFUERZO: 1 | RIESGO: bajo\n"
            f"- QUE: Medir el consumo de {TEMAS[(n + 1) % 5]} cada semana | DONDE: interfaz web | VALOR: 3 | "
            "ESFUERZO: 3 | RIESGO: medio\n")


def test_cola_avisa_con_cinco_borradores_una_vez_al_dia(cola):
    for i in range(4):
        revision.registrar_borrador(cola["id"] if i == 0 else T.anadir(f"inv {i}")["id"],
                                    f"T00{i}_20260927_100{i}.md", texto=_dos_distintas(i))
    ahora = datetime(2026, 9, 27, 18, 0)
    assert not revision.cola(ahora)["alerta"] and revision.comprobar_cola(ahora) is None
    revision.registrar_borrador(T.anadir("inv 5")["id"], "T009_20260927_1009.md", texto=_dos_distintas(4))
    c = revision.cola(ahora)
    assert c["alerta"] and c["pendientes"] == 5 and len(c["propuestas"]) == 10
    f = revision.comprobar_cola(ahora)
    aviso = json.loads(f.read_text(encoding="utf-8"))
    assert aviso["tipo"] == "revision" and "5 borrador" in aviso["titulo"]
    assert revision.comprobar_cola(ahora + timedelta(hours=3)) is None           # mismo dia: no repite
    assert revision.comprobar_cola(ahora + timedelta(days=1)) is not None        # al dia siguiente, otra vez


def test_cola_avisa_si_alguno_pasa_de_siete_dias(cola):
    revision.registrar_borrador(cola["id"], "T001_20260919_1000.md", texto=DOS)
    c = revision.cola(datetime(2026, 9, 27, 12, 0))
    assert c["pendientes"] == 1 and c["mas_antigua"] > 7 and c["alerta"]
    assert any("dias" in m for m in c["motivos"])
    assert revision.comprobar_cola(datetime(2026, 9, 27, 12, 0)) is not None
    assert len(avisos.recientes()) == 1


# ------------------------------------------------------------------ T224: veredicto SUPERADO
def test_superado_sin_resultado_deja_la_investigacion_esperando_a_claude(cola, monkeypatch):
    """T860: antes la investigacion volvia a 'pendiente' y el turno la rehacia como si el borrador fuera malo."""
    fila = _delegar(monkeypatch, DOS)
    revision.veredicto(fila["archivo"], "SUPERADO", "el trabajo real esta en auditorias/x-v2.md (T199)")
    origen = _t(cola["id"])
    assert origen["estado"] == "esperando" and origen["depende"] == "claude"
    assert "revisado:superado" in origen["etiquetas"]
    assert not any(e.startswith(revision.PRE_PENDIENTE) for e in origen["etiquetas"])
    assert "auditorias/x-v2.md" in origen["notas"][-2]["texto"] and "T860" in origen["notas"][-1]["texto"]
    assert _t(fila["revision_claude"])["estado"] == "hecha"
    assert all(_t(p)["estado"] == "descartada" for p in fila["propuestas"])
    assert cola["id"] not in [t["id"] for t in trabajo.candidatas()]   # NEXO no lo vuelve a redactar
    with pytest.raises(T.ResultadoPendiente):                          # T674: ya no espera revision, pero
        T.completar(cola["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})                                        # una investigacion pide RESULTADO
    from nucleo import investigacion
    investigacion.decidir(cola["id"], "DESCARTAR", "el trabajo real vive en auditorias/x-v2.md")
    assert _t(cola["id"])["estado"] == "hecha"


def test_superado_con_resultado_cierra_la_investigacion(cola, monkeypatch):
    fila = _delegar(monkeypatch, DOS)
    revision.veredicto(fila["archivo"], "SUPERADO", "el trabajo real esta en auditorias/x-v2.md (T199)",
                       resultado=("DESCARTAR", "ya lo cubre auditorias/x-v2.md"))
    origen = _t(cola["id"])
    assert origen["estado"] == "hecha" and origen["resultado"]["decision"] == "DESCARTAR"


def test_reclasificar_superada_una_origen_descartada_por_error(cola, monkeypatch):
    T.actualizar(cola["id"], etiquetas=cola["etiquetas"] + ["turno:lote"])   # T674: solo un lote se descarta asi
    fila = _delegar(monkeypatch, DOS)
    revision.veredicto(fila["archivo"], "DESCARTADO", "no aporta nada a NEXO frente a lo que ya hay")
    revision.reclasificar_superada(cola["id"], "el trabajo se hizo por otra via: auditorias/x-v2.md")
    origen = _t(cola["id"])
    assert origen["estado"] == "pendiente" and origen["cerrada"] is None
    assert "revisado:superado" in origen["etiquetas"] and "revisado:descartado" not in origen["etiquetas"]
    assert "borrador:rechazado" not in origen["etiquetas"]
    assert "auditorias/x-v2.md" in origen["notas"][-1]["texto"]


def test_reclasificar_solo_vale_para_descartadas_por_veredicto(cola):
    with pytest.raises(ValueError):
        revision.reclasificar_superada(cola["id"], "motivo suficientemente largo")


def test_t265_subcabecera_dentro_de_la_seccion_no_la_corta():
    texto = ("### PROPUESTAS IMPLEMENTABLES\n#### Propuesta 1\n"
             "- QUE: a | DONDE: b | VALOR: 3 | ESFUERZO: 2 | RIESGO: bajo\n"
             "### Otra seccion\n- QUE: no cuenta | DONDE: x | VALOR: 1 | ESFUERZO: 1 | RIESGO: no\n")
    r = revision.extraer_propuestas(texto)
    assert [p["que"] for p in r["propuestas"]] == ["a"]
    assert not r["problemas"]


def test_t265_autoauditoria_con_almohadillas_cierra_la_seccion():
    texto = DOS + "### AUTOAUDITORIA\n- QUE: no es propuesta | DONDE: x | VALOR: 1 | ESFUERZO: 1 | RIESGO: no\n"
    assert len(revision.extraer_propuestas(texto)["propuestas"]) == 2


def test_el_veredicto_resuelve_los_bloqueos_del_auditor_de_ese_borrador(cola, monkeypatch):
    fila = _delegar(monkeypatch, DOS)
    exp = {"tarea": cola["id"], "titulo": "x", "archivo": fila["archivo"], "llamadas": []}
    f = auditor.registrar(exp, {"resultado": "BLOQUEADA", "fallos": ["e_ok_absoluto"],
                                "puntos": {"e_ok_absoluto": {"ok": False, "detalle": "sin OK"}}})
    r = revision.veredicto(fila["archivo"], "APROBADO", "informe correcto y verificado contra el repo", resultado=("DESCARTAR", "no se adopta: NEXO ya tiene reglas equivalentes"))
    assert r["auditorias_resueltas"] == [f.name]
    assert not auditor.pendientes_de_revisar(auditor.recientes())
