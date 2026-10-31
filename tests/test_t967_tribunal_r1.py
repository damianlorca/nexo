# -*- coding: utf-8 -*-
"""T967 (Damian 17/10): R1 con plazo de 8 h, boton Aceptar y tribunal previo. Todo con dobles, en tmp_path."""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from nucleo import aprobaciones as ap
from nucleo import avisos, riesgo, tribunal_r1
from nucleo import tareas as T

T0 = datetime(2026, 10, 17, 18, 0, 0)


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "ALMACEN", tmp_path / "aprobaciones.json")
    monkeypatch.setattr(ap, "HISTORIAL", tmp_path / "aprobaciones_historial.jsonl")
    monkeypatch.setattr(ap, "CANDADO", tmp_path / ".candado.lock")
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "tareas.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado_tareas.lock")
    monkeypatch.setattr(avisos, "CARPETA", tmp_path / "avisos")
    # T1016: juzgar()/ciclo() no aceptan `ahora`; con la hora real, pasadas 8 h de T0 el silencio decidia antes que el
    # tribunal. Reloj congelado en T0 (los tests que pasan `ahora=` explicito no cambian).
    monkeypatch.setattr(ap, "_ahora", lambda: T0)
    monkeypatch.setattr(riesgo, "_ahora", lambda: T0)
    return tmp_path


def _tarea(id_="T900"):
    return {"id": id_, "titulo": "Test de la cola", "detalle": "QUE: x\nDONDE: tests/test_cola.py", "etiquetas": []}


def _r1(id_="T900"):
    a = riesgo.autorizacion(_tarea(id_), ahora=T0)
    return ap.ver(a["solicitud"])


def _d(*votos):
    return [{"id": f"p{i}", "familia": f"f{i}", "voto": v, "motivo": f"m{i}"} for i, v in enumerate(votos)]


def _tarea_real():
    return T.anadir("tarea", detalle="QUE: x\nDONDE: tests/test_cola.py")["id"]


def test_el_plazo_de_una_r1_es_de_8_horas_y_con_tribunal_empieza_al_llegar_a_la_bandeja():
    assert ap.TTL_VETO == timedelta(hours=8) and riesgo.TTL_VETO == ap.TTL_VETO
    s = _r1()
    assert s["tribunal"]["estado"] == "pendiente"
    assert s["vence"] == (T0 + ap.TTL_VETO + ap.ESPERA_TRIBUNAL).strftime(ap.FORMATO)
    llega = T0 + timedelta(hours=1)
    r = ap.registrar_tribunal(s["id"], "bandeja", _d("APROBAR", "VETAR", "APROBAR"), "dividido", ahora=llega)
    assert r["estado"] == "pendiente" and r["vence"] == (llega + ap.TTL_VETO).strftime(ap.FORMATO)
    ap.caducar(ahora=llega + ap.TTL_VETO + timedelta(seconds=1))      # el silencio sigue valiendo como si
    r = ap.ver(s["id"])
    assert r["estado"] == "aprobada" and r["decidida_por"] == "silencio"


def test_tres_de_tres_aprobar_aprueba_sin_damian():
    s = _r1()
    r = ap.registrar_tribunal(s["id"], "aprobar", _d("APROBAR", "APROBAR", "APROBAR"), "3/3", ahora=T0)
    assert r["estado"] == "aprobada" and r["decidida_por"] == "tribunal"
    assert riesgo.autorizacion(_tarea(), ahora=T0)["puede"]
    assert ap.verificar_historial()[0] is True


def test_tres_de_tres_vetar_veta_y_se_puede_deshacer():
    id_ = _tarea_real()
    s = _r1(id_)
    r = ap.registrar_tribunal(s["id"], "vetar", _d("VETAR", "VETAR", "VETAR"), "3/3", ahora=T0)
    assert r["estado"] == "denegada" and r["decidida_por"] == "tribunal"
    d = ap.deshacer_veto(s["id"], ahora=T0 + timedelta(hours=1))
    assert d["estado"] == "pendiente" and d["vence"] == (T0 + timedelta(hours=9)).strftime(ap.FORMATO)
    assert d["tribunal"]["estado"] == "decidido"          # el tribunal no vuelve a juzgarla
    assert tribunal_r1.pendientes() == []


def test_damian_se_adelanta_al_tribunal():
    s = _r1()
    ap.aprobar(s["id"], quien="damian", ahora=T0)
    r = ap.ver(s["id"])
    assert r["decidida_por"] == "damian" and r["tribunal"]["estado"] == "superado"
    assert tribunal_r1.pendientes() == []
    with pytest.raises(ap.EstadoInvalido):
        ap.registrar_tribunal(s["id"], "vetar", _d("VETAR", "VETAR", "VETAR"), "tarde", ahora=T0)


def test_el_tribunal_nunca_juzga_r2_ni_r3():
    with pytest.raises(ValueError):
        ap.solicitar("fusionar T1", "R2 sha256:x", nivel="R2", espera_tribunal=ap.ESPERA_TRIBUNAL)
    with pytest.raises(ValueError):
        ap.solicitar("x", "y", nivel="R1", tipo="normal", espera_tribunal=ap.ESPERA_TRIBUNAL)
    diff = ("diff --git a/nucleo/tareas.py b/nucleo/tareas.py\n--- a/nucleo/tareas.py\n"
            "+++ b/nucleo/tareas.py\n@@ -1 +1,2 @@\n+X = 1\n")
    f = riesgo.fusion({"id": "T901", "titulo": "t", "detalle": "", "etiquetas": []}, diff, "R2", ahora=T0)
    assert "tribunal" not in ap.ver(f["solicitud"]) and tribunal_r1.pendientes() == []


def test_decidir_solo_unanimidad_decide():
    assert tribunal_r1.decidir(_d("APROBAR", "APROBAR", "APROBAR"))[0] == "aprobar"
    assert tribunal_r1.decidir(_d("VETAR", "VETAR", "VETAR"))[0] == "vetar"
    assert tribunal_r1.decidir(_d("APROBAR", "VETAR", "APROBAR"))[0] == "bandeja"
    r, motivo = tribunal_r1.decidir(_d("APROBAR", "APROBAR"))
    assert r == "bandeja" and "2/3" in motivo
    assert tribunal_r1.decidir([])[0] == "bandeja"


def test_parsear_el_dictamen():
    ok = tribunal_r1.parsear("VOTO: APROBAR\nMOTIVO: bien definida\nFIN_DICTAMEN")
    assert ok == {"voto": "APROBAR", "motivo": "bien definida", "error": ""}
    assert tribunal_r1.parsear("**VOTO:** vetar\nMOTIVO: x\nFIN_DICTAMEN")["voto"] == "VETAR"
    assert tribunal_r1.parsear("VOTO: APROBAR\nMOTIVO: x")["error"]                  # sin FIN: truncado
    assert tribunal_r1.parsear("VOTO: APROBAR\nVOTO: VETAR\nFIN_DICTAMEN")["error"]  # contradictorio
    assert tribunal_r1.parsear("sin formato FIN_DICTAMEN")["error"]


def test_el_prompt_lleva_la_tarea_el_donde_y_el_contrato(tmp_path, monkeypatch):
    (tmp_path / "tests_dados").mkdir()
    (tmp_path / "tests_dados" / "test_cola.py").write_text("def test_algo():\n    assert cola.vacia()\n",
                                                           encoding="utf-8")
    monkeypatch.setattr(tribunal_r1, "RAIZ", tmp_path)
    p = tribunal_r1.prompt(_tarea())
    assert "Test de la cola" in p and "DONDE: tests/test_cola.py" in p and "cola.vacia()" in p
    monkeypatch.setattr(tribunal_r1, "RAIZ", tmp_path / "otro")
    assert "no hay tests dados" in tribunal_r1.prompt(_tarea())


class _Prov:
    def __init__(self, texto=None, ok=True, excepcion=None):
        self.texto, self.ok, self.excepcion = texto, ok, excepcion

    def enviar(self, prompt):
        if self.excepcion:
            raise self.excepcion
        return SimpleNamespace(ok=self.ok, texto=self.texto, estado="error", detalle="caido")


def _preparar(monkeypatch, respuestas):
    """respuestas: {id_candidato: _Prov}; el resto no esta disponible."""
    from nucleo import banco_modelos
    from nucleo import tribunal as TR
    monkeypatch.setattr(banco_modelos, "ordenar", lambda rol, lista, clave: list(lista))
    monkeypatch.setattr(TR, "_disponible", lambda c: c.id in respuestas)
    monkeypatch.setattr(TR, "_esperar", lambda c, limite: True)
    monkeypatch.setattr(TR, "_marcar_uso", lambda c: None)
    monkeypatch.setattr(TR, "_proveedor", lambda c: respuestas[c.id])


def _ok(voto):
    return _Prov(f"VOTO: {voto}\nMOTIVO: razon\nFIN_DICTAMEN")


def test_reunir_toma_tres_familias_distintas_y_salta_los_fallos(monkeypatch):
    from nucleo import tribunal as TR
    ids = [c.id for c in TR.TRIBUNAL]
    resp = {ids[0]: _Prov(excepcion=RuntimeError("red")), ids[1]: _ok("APROBAR"), ids[2]: _ok("APROBAR"),
            ids[3]: _Prov("basura"), ids[4]: _ok("APROBAR"), ids[5]: _ok("VETAR")}
    _preparar(monkeypatch, resp)
    dicts, fallos = tribunal_r1._reunir(_tarea(), None)
    assert len(dicts) == 3 and len({d["familia"] for d in dicts}) == 3
    assert {f["id"] for f in fallos} == {ids[0], ids[3]}


def test_juzgar_tres_aprobar_aprueba(monkeypatch):
    s = _r1(_tarea_real())
    monkeypatch.setattr(tribunal_r1, "_reunir", lambda tarea, limite: (_d("APROBAR", "APROBAR", "APROBAR"), []))
    r = tribunal_r1.juzgar(s)
    assert r["estado"] == "aprobada" and r["decidida_por"] == "tribunal"


def test_juzgar_con_proveedores_caidos_cae_a_la_bandeja_de_damian(monkeypatch):
    s = _r1(_tarea_real())
    _preparar(monkeypatch, {})                       # nadie disponible: sin cupo
    r = tribunal_r1.juzgar(s)
    assert r["estado"] == "pendiente" and r["tribunal"]["estado"] == "bandeja"
    assert "sin quorum" in r["tribunal"]["motivo"]
    assert riesgo.bandeja()["r1"][0]["estado_tribunal"] == "bandeja"


def test_ciclo_juzga_las_pendientes_y_la_tarea_inexistente_va_a_bandeja(monkeypatch):
    s = _r1()                                         # T900 no existe en la cola de tareas
    monkeypatch.setattr(tribunal_r1, "_reunir", lambda *a: pytest.fail("no debe llamar a nadie"))
    assert tribunal_r1.ciclo() == {s["id"]: "bandeja"}
    assert tribunal_r1.ciclo() == {}


# ------------------------------------------------------------ Bloque 10: tambien las R1 de FUSION

def _diff_r1():
    return ("diff --git a/nucleo/colas.py b/nucleo/colas.py\n--- a/nucleo/colas.py\n+++ b/nucleo/colas.py\n"
            "@@ -1 +1,2 @@\n x = 1\n+y = 2\n")


def _fusion_r1(ahora=T0):
    """Pieza con tests dados y diff R2 de codigo normal que paso la puerta: va por veto R1 de fusion."""
    id_ = T.anadir("tarea", detalle="QUE: x\nDONDE: nucleo/colas.py")["id"]
    t = {**T.buscar(id_), "etiquetas": [riesgo.TESTS_DADOS]}
    return t, riesgo.fusion(t, _diff_r1(), "R1", resumen="Anade y.", ahora=ahora, puerta_ok=True)


def test_la_r1_de_fusion_tambien_espera_al_tribunal_y_su_prompt_lleva_el_diff(monkeypatch):
    t, f = _fusion_r1()
    id_ = t["id"]
    s = ap.ver(f["solicitud"])
    assert s["accion"] == f"fusionar {id_}" and s["nivel"] == "R1" and s["tribunal"]["estado"] == "pendiente"
    assert s["vence"] == (T0 + ap.TTL_VETO + ap.ESPERA_TRIBUNAL).strftime(ap.FORMATO)
    assert [x["id"] for x in tribunal_r1.pendientes()] == [s["id"]]
    vistos = []
    monkeypatch.setattr(tribunal_r1, "_reunir",
                        lambda tarea, limite, texto=None: (vistos.append(texto) or (_d("APROBAR", "APROBAR", "APROBAR"), [])))
    r = tribunal_r1.juzgar(s)
    assert r["estado"] == "aprobada" and r["decidida_por"] == "tribunal"
    assert "Anade y." in vistos[0] and "SE FUSIONA" not in vistos[0] and "fusiona" in vistos[0]
    assert riesgo.fusion(t, _diff_r1(), "R1", ahora=T0, puerta_ok=True)["puede"]


def test_r1_de_fusion_dividida_cae_a_la_bandeja_de_damian_con_8_h(monkeypatch):
    t, f = _fusion_r1()
    s = ap.ver(f["solicitud"])
    monkeypatch.setattr(tribunal_r1, "_reunir", lambda tarea, limite, texto=None: (_d("APROBAR", "VETAR", "APROBAR"), []))
    r = tribunal_r1.juzgar(s)
    assert r["estado"] == "pendiente" and r["tribunal"]["estado"] == "bandeja"
    assert riesgo.bandeja()["r1"][0]["fusion"] is True
