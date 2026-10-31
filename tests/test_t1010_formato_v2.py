"""T1010 paso 2, punto 1: formato de tarea v2 en nucleo/tareas.py (campos, validador, completar).

Todo con dobles: el almacen de tareas va a tmp_path (fixture autouse `turnos_aislados` de conftest.py).
"""
import json

import pytest

from nucleo import tarea_v2 as V
from nucleo import tareas as T


def _disco(tid):
    """El registro tal como esta en disco (tareas.json o historial)."""
    datos = json.loads(T.ALMACEN.read_text(encoding="utf-8"))
    for r in datos["tareas"]:
        if r["id"] == tid:
            return r
    _, regs = T.AL.leer_historial(T.ALMACEN)
    return next(r for r in regs if r["id"] == tid)


# ------------------------------------------------------------------ campos v2 <-> viejos

def test_anadir_con_nombres_v2_rellena_tambien_los_viejos():
    t = T.anadir("Mover el router", objetivo="Que el router vaya a una sola funcion", hecho_cuando=["test verde", "doc"],
                 donde="nucleo/router.py", quien="claude", tipo="codigo", prioridad=4, esfuerzo=2, coste_eur=0,
                 fecha_limite="2030-01-31", depende_de=["T001", "T002"])
    assert (t["depende"], t["importancia"], t["urgencia"], t["dificultad"]) == ("claude", 4, 4, 2)
    assert t["limite"] == "2030-01-31" and t["bloqueada_por"] == "T001, T002"
    assert "cat:codigo" in t["etiquetas"]
    # y las vistas v2 cuadran
    assert (t["quien"], t["tipo"], t["prioridad"], t["esfuerzo"]) == ("claude", "codigo", 4, 2)
    assert t["fecha_limite"] == "2030-01-31" and t["depende_de"] == ["T001", "T002"]
    assert t["hecho_cuando"] == ["test verde", "doc"] and t["coste_eur"] == 0


def test_anadir_con_nombres_viejos_rellena_las_vistas_v2():
    t = T.anadir("Cosa vieja", importancia=5, urgencia=1, dificultad=2, depende="claude", limite="2031-02-02",
                 bloqueada_por="esperando a T010 y T011", etiquetas="cat:investigacion, tema:foco")
    assert (t["prioridad"], t["esfuerzo"], t["quien"], t["tipo"]) == (3, 2, "claude", "investigacion")
    assert t["fecha_limite"] == "2031-02-02" and t["depende_de"] == ["T010", "T011"]
    assert t["importancia"] == 5 and t["urgencia"] == 1          # los viejos mandan en memoria


def test_hecho_cuando_y_coste_llegan_como_texto_de_la_cli():
    t = T.anadir("Por CLI", hecho_cuando="primero | segundo", coste_eur="1,5")
    assert t["hecho_cuando"] == ["primero", "segundo"] and t["coste_eur"] == 1.5


def test_actualizar_acepta_v2_y_mantiene_coherencia():
    t = T.anadir("A cambiar", depende="claude")
    t = T.actualizar(t["id"], quien="implementador", prioridad=5, esfuerzo=1, fecha_limite="2032-03-03")
    assert t["depende"] == "ia" and t["quien"] == "implementador"        # el implementador es una "ia" para el resto
    assert (t["importancia"], t["urgencia"], t["dificultad"], t["limite"]) == (5, 5, 1, "2032-03-03")
    t = T.actualizar(t["id"], depende="claude")                          # y un cambio con el nombre viejo manda
    assert t["quien"] == "claude"


def test_quien_damian_con_motivo_pasa_la_guardia_de_responsables():
    t = T.anadir("Elegir fecha", quien="damian", motivo_quien="gustos: decide cuando le viene bien")
    assert t["depende"] == "damian" and t["quien"] == "damian"
    sin = T.anadir("Revisar un modulo", quien="damian", motivo_quien="porque si")
    assert sin["depende"] == "claude" and sin["quien"] == "claude"       # sin razon de verdad, la guardia la pasa a Claude


def test_externo_es_damian_con_motivo_externo_y_vuelve_igual():
    t = T.anadir("Esperar al servidor", depende="externo")
    assert t["quien"] == "damian" and t["motivo_quien"].startswith("externo")
    assert T.cargar()["tareas"][0]["depende"] == "externo"
    t = T.actualizar(t["id"], depende="claude")
    assert t["quien"] == "claude" and t["motivo_quien"] == ""


def test_etiquetas_de_rastreo_viajan_en_origen_y_se_reconstruyen():
    et = ["prov:claude", "tarea_origen:T5", "de_borrador:T5_1.md", "tema:foco", "cat:revision", "origen:orden_web"]
    t = T.anadir("Revisar borrador", etiquetas=et)
    assert t["origen"] == {"prov": "claude", "tarea_origen": "T5", "de_borrador": "T5_1.md", "via": "orden_web",
                           "cat": "revision"}
    assert t["tipo"] == "investigacion"
    r = _disco(t["id"])
    assert r["etiquetas"] == ["tema:foco"]                               # en disco solo lo que no es rastreo ni cat
    assert r["origen"]["prov"] == "claude" and r["tipo"] == "investigacion"
    de_nuevo = T.cargar()["tareas"][0]
    assert sorted(de_nuevo["etiquetas"]) == sorted(et)                   # y al cargar vuelven todas


def test_origen_v2_se_convierte_en_etiquetas_que_el_resto_del_codigo_lee():
    t = T.anadir("Con origen", origen={"prov": "nexo", "tarea_origen": "T9", "cuando": "2026-10-17"})
    assert "prov:nexo" in t["etiquetas"] and "tarea_origen:T9" in t["etiquetas"]
    assert t["origen"]["cuando"] == "2026-10-17" and T.cargar()["tareas"][0]["origen"]["cuando"] == "2026-10-17"


def test_importancia_y_urgencia_distintas_sobreviven_al_disco():
    t = T.anadir("Dos medidas", importancia=5, urgencia=1, coste=4)
    g = T.cargar()["tareas"][0]
    assert (g["importancia"], g["urgencia"], g["coste"]) == (5, 1, 4)
    assert T.puntuacion(g) == T.puntuacion(t)


# ------------------------------------------------------------------ instrucciones privadas

def test_instrucciones_de_damian_literales_y_privadas_a_su_archivo():
    t = T.anadir("Pedido suyo", instrucciones_damian="Hazlo asi, sin tocar el router.")
    assert t["instrucciones_damian"] == "Hazlo asi, sin tocar el router." and T.instrucciones(t).startswith("Hazlo asi")
    p = T.anadir("Dato personal", tipo="personal", instrucciones_damian="Mi DNI es 000 y mi IBAN es 111")
    assert p["instrucciones_damian"] == V.PRIVADO_REF.format(id=p["id"])
    archivo = T.ALMACEN.parent / "perfil_privado" / "tareas" / f"{p['id']}.md"
    assert "IBAN" in archivo.read_text(encoding="utf-8") and "IBAN" in T.instrucciones(p)
    assert "IBAN" not in T.ALMACEN.read_text(encoding="utf-8")           # el texto privado nunca esta en tareas.json


def test_actualizar_instrucciones_privado_true():
    t = T.anadir("Otra")
    t = T.actualizar(t["id"], instrucciones_damian="secreto de Damian", privado=True)
    assert t["instrucciones_damian"].startswith("memoria/perfil_privado/tareas/")
    assert "secreto" not in T.ALMACEN.read_text(encoding="utf-8")


# ------------------------------------------------------------------ validador

def _bueno(**extra):
    base = dict(objetivo="Dejarlo funcionando", hecho_cuando=["el test pasa"], donde="nucleo/x.py", quien="ia",
                tipo="codigo", prioridad=3, esfuerzo=2, coste_eur=0)
    base.update(extra)
    return T.anadir("Una tarea bien hecha", **base)


def test_tarea_correcta_no_da_avisos():
    assert V.validar(_bueno()) == []


@pytest.mark.parametrize("campos, texto", [
    ({"objetivo": "x" * 301}, "objetivo de 301"),
    ({"hecho_cuando": []}, "hecho_cuando"),
    ({"hecho_cuando": ["a", "b", "c", "d"]}, "hecho_cuando"),
    ({"donde": ""}, "falta donde"),
    ({"tipo": "cosas"}, "tipo debe ser"),
    ({"coste_eur": -1}, "coste_eur"),
    ({"fecha_limite": "pasado manana"}, "fecha_limite"),
])
def test_validador_avisa_de_cada_limite(campos, texto):
    t = _bueno()
    t.update(campos)
    assert any(texto in p for p in V.validar(t)), V.validar(t)


def test_validador_titulo_largo_notas_y_damian_sin_motivo():
    t = _bueno()
    t["titulo"] = "t" * 81
    t["notas"] = [{"cuando": "x", "texto": str(i)} for i in range(6)]
    t["quien"], t["motivo_quien"] = "damian", ""
    p = V.validar(t)
    assert any("titulo de 81" in x for x in p) and any("notas" in x for x in p) and any("motivo_quien" in x for x in p)


def test_las_tareas_viejas_no_dan_avisos_ni_se_bloquean(monkeypatch):
    emitidos = []
    from nucleo import avisos
    monkeypatch.setattr(avisos, "emitir", lambda *a, **k: emitidos.append((a, k)))
    t = T.anadir("T" * 200, importancia=2)                                # titulo larguisimo, sin nada v2
    assert t["id"] == "T001" and emitidos == [] and T.avisos_formato() == []


def test_aviso_de_formato_va_al_centro_y_no_bloquea(monkeypatch):
    emitidos = []
    from nucleo import avisos
    monkeypatch.setattr(avisos, "emitir", lambda *a, **k: emitidos.append((a, k)))
    t = T.anadir("Mal hecha", objetivo="o" * 400, hecho_cuando=["ok"], donde="aqui")    # objetivo pasado de largo
    assert t["id"] == "T001"                                                             # se creo igualmente
    assert len(emitidos) == 1 and emitidos[0][0][0] == "formato" and "T001" in emitidos[0][0][1]
    assert emitidos[0][1]["clave"] == "formato:T001"
    assert [i for i, _ in T.avisos_formato()] == ["T001"]


def test_un_fallo_al_avisar_no_rompe_el_alta(monkeypatch):
    from nucleo import avisos
    monkeypatch.setattr(avisos, "emitir", lambda *a, **k: (_ for _ in ()).throw(OSError("disco lleno")))
    assert T.anadir("Mal", objetivo="o" * 400, hecho_cuando=["ok"], donde="x")["id"] == "T001"


# ------------------------------------------------------------------ completar exige despues y cierre

CIERRE = {"estado_real": "HECHO SIN TESTEAR", "evidencia": "hecho a mano, sin prueba automatica"}


def test_completar_sin_despues_o_sin_cierre_no_cierra():
    t = T.anadir("Cerrar mal")
    for despues, cierre in [(None, CIERRE), ("nada: ya no hace falta", None), ("", CIERRE),
                            ("nada:", CIERRE), ("ya veremos", CIERRE),
                            ("nada: ya no hace falta", {"estado_real": "HECHO SIN TESTEAR", "evidencia": ""}),
                            ("nada: ya no hace falta", {"estado_real": "casi", "evidencia": "algo de evidencia"})]:
        with pytest.raises(T.CierreIncompleto):
            T.completar(t["id"], despues=despues, cierre=cierre)
    assert T.buscar(t["id"])["estado"] == "pendiente"
    assert issubclass(T.CierreIncompleto, T.RevisionPendiente)           # la web, el chat y el bot ya la capturan


def test_completar_bien_deja_despues_y_cierre_y_sigue_sin_testear():
    t = T.anadir("Cerrar bien")
    c = T.completar(t["id"], "nota", despues="nada: no tiene continuacion", cierre=CIERRE)
    assert c["estado"] == "hecha" and c["despues"] == "nada: no tiene continuacion"
    assert c["cierre"] == CIERRE and T.estado_real(c) == "HECHO SIN TESTEAR"
    assert c["cerrada"] and c["notas"][-1]["texto"] == "nota"


def test_completar_con_una_tarea_siguiente_existente():
    a, b = T.anadir("Primera"), T.anadir("Segunda")
    assert T.completar(a["id"], despues=b["id"], cierre=CIERRE)["despues"] == b["id"]


def test_completar_con_siguiente_nueva_la_crea_con_contenido():
    t = T.anadir("Origen")
    c = T.completar(t["id"], despues={"titulo": "Seguir con la parte 2", "objetivo": "Hacer la parte 2", "quien": "claude"},
                    cierre=CIERRE)
    nueva = T.buscar(c["despues"])
    assert nueva["titulo"] == "Seguir con la parte 2" and nueva["quien"] == "claude" and nueva["estado"] == "pendiente"
    assert nueva["origen"]["tarea_origen"] == t["id"]


def test_completar_hecho_y_testeado_verifica_con_la_evidencia():
    t = T.anadir("Con prueba")
    c = T.completar(t["id"], despues="nada: nada mas que hacer",
                    cierre={"estado_real": "HECHO Y TESTEADO", "evidencia": "pytest tests/test_x.py: 4 passed"})
    assert c["testeado"] is True and T.estado_real(c) == "HECHO Y TESTEADO"
    assert c["cierre"]["estado_real"] == "HECHO Y TESTEADO" and "4 passed" in c["cierre"]["evidencia"]


def test_completar_inexistente_o_con_revision_pendiente():
    assert T.completar("T999", despues="nada: no existe", cierre=CIERRE) is None
    t = T.anadir("Espera revision", etiquetas=["revision_claude:T5_1.md"])
    with pytest.raises(T.RevisionPendiente):
        T.completar(t["id"], despues="nada: espera veredicto", cierre=CIERRE)


def test_el_validador_pide_cierre_y_despues_a_las_cerradas():
    t = _bueno()
    t["estado"] = "hecha"
    assert any("cierre" in p for p in V.validar(t)) and any("despues" in p for p in V.validar(t))
    t["cierre"], t["despues"] = dict(CIERRE), "nada: nada mas que hacer"
    assert not [p for p in V.validar(t) if "cierre" in p or "despues" in p]


def test_cli_hecha_pide_despues_y_evidencia(capsys):
    t = T.anadir("Por CLI")
    assert T._cli(["hecha", t["id"], "nota"]) == 2
    assert "NO cerrada" in capsys.readouterr().out and T.buscar(t["id"])["estado"] == "pendiente"
    assert T._cli(["hecha", t["id"], "nota", "--despues", "nada: sin continuacion",
                   "--evidencia", "lo he comprobado a mano"]) == 0
    c = T.buscar(t["id"])
    assert c["estado"] == "hecha" and c["despues"] == "nada: sin continuacion" and not c["testeado"]
    assert T._cli(["hecha"]) == 2


def test_cli_anadir_acepta_los_nombres_v2():
    assert T._cli(["anadir", "Con v2", "--quien", "claude", "--prioridad", "5", "--objetivo", "Hacer algo",
                   "--hecho_cuando", "uno | dos", "--tipo", "codigo"]) == 0
    t = T.cargar()["tareas"][0]
    assert (t["depende"], t["prioridad"], t["objetivo"], t["hecho_cuando"], t["tipo"]) == \
        ("claude", 5, "Hacer algo", ["uno", "dos"], "codigo")


def test_cerrar_una_tarea_vieja_no_genera_avisos_de_formato(monkeypatch):
    emitidos = []
    from nucleo import avisos
    monkeypatch.setattr(avisos, "emitir", lambda *a, **k: emitidos.append(a))
    t = T.anadir("Vieja")
    T.completar(t["id"], despues="nada: sin continuacion", cierre=CIERRE)
    assert emitidos == [] and T.avisos_formato() == []
