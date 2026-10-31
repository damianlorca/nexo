# -*- coding: utf-8 -*-
"""T674: una investigacion solo se cierra con RESULTADO (ADOPTAR/ADAPTAR/DESCARTAR + motivo); ADOPTAR/ADAPTAR
crea su integracion y la investigacion espera a que se verifique; un borrador malo no la cierra.
Tareas a tmp_path por el conftest de la raiz (turnos_aislados)."""
from __future__ import annotations

import pytest

from nucleo import evidencias, investigacion, revision, trabajo
from nucleo import tareas as T

DOS = ("### PROPUESTAS IMPLEMENTABLES\n"
       "- QUE: Anadir las reglas al rol de programador | DONDE: roles y prompts | VALOR: 4 | ESFUERZO: 1 | "
       "RIESGO: bajo: solo texto\n"
       "- QUE: Cargar la politica solo en tareas de codigo | DONDE: router | VALOR: 3 | ESFUERZO: 3 | "
       "RIESGO: medio: puede no activarse\n")
MOTIVO = "encaja con el router local y no tiene dependencias nuevas"


@pytest.fixture
def inv():
    return T.anadir("Investigar la herramienta X", etiquetas=["cat:investigacion"], importancia=4, urgencia=3)


def _t(tid):
    return T.buscar(tid)


def _borrador(t, nombre):
    return revision.registrar_borrador(t["id"], nombre, texto=DOS, auditoria="APROBADA")


# ------------------------------------------------------------------ la guardia, por todas las vias
def test_sin_resultado_no_se_cierra_por_ninguna_via(inv):
    for intento in (lambda: T.completar(inv["id"], "ya esta", despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"}),
                    lambda: T.actualizar(inv["id"], estado="hecha"),
                    lambda: T.actualizar(inv["id"], estado="descartada"),
                    lambda: evidencias.cerrar(inv["id"], "hecho", evidencia="pytest: 3 passed en tests/x.py")):
        with pytest.raises(T.ResultadoPendiente) as e:
            intento()
        assert "RESULTADO" in str(e.value)
    assert _t(inv["id"])["estado"] == "pendiente"
    assert isinstance(T.ResultadoPendiente("x"), T.RevisionPendiente)   # la web, el chat y el bot ya la capturan


def test_no_afecta_a_lotes_de_turno_ni_a_otras_tareas():
    lote = T.anadir("Revision de codigo (turno)", etiquetas=["cat:investigacion", "turno:lote"])
    otra = T.anadir("Arreglar un bug", etiquetas=["cat:codigo"])
    assert T.completar(lote["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})["estado"] == "hecha"
    assert T.actualizar(otra["id"], estado="descartada")["estado"] == "descartada"


def test_descartar_cierra_como_hecha_y_descartada_exige_descartar(inv):
    with pytest.raises(ValueError):
        investigacion.decidir(inv["id"], "QUIZAS", MOTIVO)
    with pytest.raises(ValueError):
        investigacion.decidir(inv["id"], "DESCARTAR", "corto")
    r = investigacion.decidir(inv["id"], "DESCARTAR", "no aporta frente a lo que ya tiene NEXO")
    t = r["investigacion"]
    assert t["estado"] == "hecha" and t["resultado"]["decision"] == "DESCARTAR" and r["hija"] is None
    otra = T.anadir("Investigar Y", etiquetas=["cat:investigacion"])
    investigacion.fijar_resultado(otra["id"], "ADOPTAR", MOTIVO)
    with pytest.raises(T.ResultadoPendiente):
        T.actualizar(otra["id"], estado="descartada")
    investigacion.fijar_resultado(otra["id"], "DESCARTAR", "ya no interesa: Damian lo retiro")
    assert T.actualizar(otra["id"], estado="descartada")["estado"] == "descartada"


# ------------------------------------------------------------------ ADOPTAR / ADAPTAR -> integracion
def test_adoptar_crea_hija_y_la_investigacion_espera_hasta_verificarla(inv):
    r = investigacion.decidir(inv["id"], "ADOPTAR", MOTIVO, informe="memoria/borradores/T001_x.md")
    h, t = r["hija"], r["investigacion"]
    assert t["estado"] == "esperando" and f"integracion:{h['id']}" in t["etiquetas"]
    assert h["estado"] == "pendiente" and h["importancia"] == 4 and f"integra:{inv['id']}" in h["etiquetas"]
    assert "cat:integracion" in h["etiquetas"] and "memoria/borradores/T001_x.md" in h["detalle"]
    assert "cola de aprobaciones (N04" in h["detalle"] and "no da permiso" in h["detalle"]
    for paso in ("1. Instalar", "2. Documentar", "3. Tests", "4. Verificar"):
        assert paso in h["detalle"]
    with pytest.raises(T.ResultadoPendiente) as e:
        T.completar(inv["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    assert h["id"] in str(e.value)
    T.completar(h["id"], "integrada", despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    assert _t(inv["id"])["estado"] == "esperando"          # hecha pero SIN verificar: no basta
    T.verificar(h["id"], "pytest tests -q: 12 passed; el router usa X en la prueba real")
    t = _t(inv["id"])
    assert t["estado"] == "hecha" and t["testeado"] and T.estado_real(t) == "HECHO Y TESTEADO"
    assert h["id"] in t["notas"][-1]["texto"]


def test_hija_descartada_devuelve_la_investigacion_a_pendiente(inv):
    h = investigacion.decidir(inv["id"], "ADAPTAR", MOTIVO)["hija"]
    T.actualizar(h["id"], estado="descartada")
    t = _t(inv["id"])
    assert t["estado"] == "pendiente" and "resultado" not in t
    assert not any(e.startswith("integracion:") for e in t["etiquetas"])
    assert "se descarto" in t["notas"][-1]["texto"]


def test_hija_verificada_por_evidencias_cerrar_tambien_cierra(inv):
    h = investigacion.decidir(inv["id"], "ADOPTAR", MOTIVO)["hija"]
    evidencias.cerrar(h["id"], "integrada", evidencia="pytest tests -q: 12 passed; salida real del router con X")
    assert T.estado_real(_t(inv["id"])) == "HECHO Y TESTEADO"


# ------------------------------------------------------------------ veredicto: borrador malo != contenido
def test_aprobado_de_investigacion_exige_resultado_y_no_toca_nada_sin_el(inv):
    r = _borrador(inv, "T001_20261003_1000.md")
    with pytest.raises(ValueError, match="--resultado"):
        revision.veredicto("T001_20261003_1000.md", "APROBADO", "informe correcto y verificado")
    assert all(_t(p["id"])["estado"] == "propuesta" for p in r["propuestas"])
    assert _t(r["revision"]["id"])["estado"] == "pendiente"
    revision.veredicto("T001_20261003_1000.md", "APROBADO", "informe correcto y verificado",
                       resultado=("ADAPTAR", MOTIVO))
    t = _t(inv["id"])
    hija = _t(investigacion._et(t, "integracion:"))
    assert t["estado"] == "esperando" and "revisado:aprobado" in t["etiquetas"]
    assert "memoria/borradores/T001_20261003_1000.md" in hija["detalle"]


def test_dos_borradores_malos_seguidos_pasan_a_esperar_a_claude(inv):
    _borrador(inv, "T001_20261003_1000.md")
    revision.veredicto("T001_20261003_1000.md", "DESCARTADO", "el borrador no cita fuentes primarias")
    assert (_t(inv["id"])["estado"], _t(inv["id"])["depende"]) == ("pendiente", "ia")
    _borrador(inv, "T001_20261003_1100.md")
    revision.veredicto("T001_20261003_1100.md", "REHACER", "sigue sin fuentes primarias del repo",
                       instrucciones="cita el README y el LICENSE con su URL")
    t = _t(inv["id"])
    assert (t["estado"], t["depende"], t["borradores_malos"]) == ("esperando", "claude", 2)
    assert "espera a Claude" in t["notas"][-1]["texto"]
    assert inv["id"] not in [x["id"] for x in trabajo.candidatas()]


def test_un_borrador_aprobado_corta_la_racha(inv):
    _borrador(inv, "T001_20261003_1000.md")
    revision.veredicto("T001_20261003_1000.md", "DESCARTADO", "el borrador no cita fuentes primarias")
    _borrador(inv, "T001_20261003_1100.md")
    revision.veredicto("T001_20261003_1100.md", "APROBADO", "ahora si, con fuentes verificadas",
                       resultado=("DESCARTAR", "no aporta frente a lo que ya hay"))
    t = _t(inv["id"])
    assert "borradores_malos" not in t and t["estado"] == "hecha"


# ------------------------------------------------------------------ turnos: no es un fallo del proveedor
def test_resultado_pendiente_en_el_turno_no_cuenta_como_fallo(inv, monkeypatch):
    def delegar(t, cat, limite):
        raise T.ResultadoPendiente(f"{t['id']} es una investigacion: solo se cierra con RESULTADO")
    monkeypatch.setattr(trabajo, "delegar", delegar)
    [fila] = trabajo.ciclo(max_tareas=1, lista=[_t(inv["id"])])
    t = _t(inv["id"])
    assert "RESULTADO" in fila["resultado_pendiente"] and "fallos_seguidos" not in fila
    assert "fallos_turno" not in t and t["estado"] == "pendiente"
    assert "no se cierra sin RESULTADO" in t["notas"][-1]["texto"]


# ------------------------------------------------------------------ depende=claude y auditoria
def test_depende_claude_es_valido_y_sale_en_la_vista():
    t = T.anadir("Partir el encargo", depende="claude")
    assert t["depende"] == "claude" and T.sugerencia_claude(t) is not None
    assert "Necesita a Claude" in T.render_md() and t["id"] in T.render_md()


def test_auditoria_solo_informa(inv, tmp_path, monkeypatch):
    monkeypatch.setattr(investigacion, "INFORMES", tmp_path / "inv")
    vieja = T.anadir("Investigar Z", etiquetas=["cat:investigacion", "revisado:descartado"])
    sup = T.anadir("Investigar W", etiquetas=["cat:investigacion", "revisado:superado"])
    apr = T.anadir("Investigar V", etiquetas=["cat:investigacion", "revisado:aprobado"])
    T.anadir("[Propuesta] usar V", estado="pendiente",
             etiquetas=["cat:propuesta", f"tarea_origen:{apr['id']}", "propuesta:aprobada"])
    datos = T.cargar()      # cerradas "a la antigua", sin pasar por la guardia
    for x in datos["tareas"]:
        if x["id"] in (vieja["id"], sup["id"], apr["id"]):
            x["estado"] = "descartada" if x["id"] == vieja["id"] else "hecha"
    T.guardar(datos)
    antes = T.ALMACEN.read_text("utf-8")
    r = investigacion.auditar()
    assert T.ALMACEN.read_text("utf-8") == antes
    prop = {f["id"]: f["propuesta"] for f in r["filas"]}
    assert prop == {vieja["id"]: "reabrir", sup["id"]: "descarte valido", apr["id"]: "crear integracion"}
    assert "SOLO INFORME" in open(r["informe"], encoding="utf-8").read()
