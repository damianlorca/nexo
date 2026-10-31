# -*- coding: utf-8 -*-
"""Incremento 6: tareas (lista filtrable, ficha, crear/editar/anotar/completar/verificar)."""
from __future__ import annotations

import json

import pytest

from nucleo import tareas as T


def _post(cliente, csrf, url, **datos):
    return cliente.post(url, data=datos, headers={"X-CSRF-Token": csrf})


def _version_de(id_):
    from interfaz.rutas import tareas as rutas
    return rutas._version(next(t for t in T.cargar()["tareas"] if t["id"] == id_))


CAMPOS = {"titulo": "Tarea nueva", "detalle": "detalle", "importancia": "4", "urgencia": "2",
          "dificultad": "3", "coste": "1", "depende": "damian", "limite": "2026-10-01", "etiquetas": "a, b, a"}


# -------------------------------------------------------------------- lista
def test_lista_vacia(cliente, csrf):
    r = cliente.get("/tareas")
    assert r.status_code == 200 and "Ninguna tarea con estos filtros" in r.text


def test_lista_por_puntuacion_con_estado_real(cliente, csrf):
    T.anadir("baja", importancia=1, urgencia=1)
    alta = T.anadir("alta", importancia=5, urgencia=5)
    r = cliente.get("/tareas").text
    assert r.index("alta") < r.index("baja") and "PLANIFICADO" in r
    assert f'href="/tareas/{alta["id"]}"' in r


def test_filtros_estado_depende_etiqueta_y_texto(cliente, csrf):
    a = T.anadir("Revisar becas", depende="damian", etiquetas=["cat:personal"])
    b = T.anadir("Resumir informe", etiquetas=["cat:resumen"])
    T.completar(b["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    assert "Revisar becas" in cliente.get("/tareas/lista", params={"depende": "damian"}).text
    assert "Resumir informe" not in cliente.get("/tareas/lista").text            # vivas por defecto
    assert "Resumir informe" in cliente.get("/tareas/lista", params={"estado": "hecha"}).text
    assert "Resumir informe" in cliente.get("/tareas/lista", params={"estado": "todas"}).text
    r = cliente.get("/tareas/lista", params={"estado": "todas", "etiqueta": "cat:res"}).text
    assert "Resumir informe" in r and "Revisar becas" not in r
    r = cliente.get("/tareas/lista", params={"q": a["id"].lower()}).text
    assert "Revisar becas" in r and "Resumir" not in r


def test_lista_refleja_el_filtro_en_la_url_y_se_refresca_por_sse(cliente, csrf):
    r = cliente.get("/tareas/lista", params={"estado": "hecha", "depende": "ia"})
    assert r.headers["hx-replace-url"] == "/tareas?estado=hecha&depende=ia"
    pagina = cliente.get("/tareas").text
    assert 'hx-include="#filtros-tareas"' in pagina and "nexo:tareas from:body" in pagina


def test_filtros_basura_caen_a_valores_seguros(cliente, csrf):
    r = cliente.get("/tareas/lista", params={"estado": "<script>", "depende": "nadie"})
    assert r.status_code == 200 and "<script>" not in r.text


def test_lista_con_tareas_json_roto_da_error_con_reintento(cliente, csrf):
    T.ALMACEN.write_text("{roto", encoding="utf-8")
    r = cliente.get("/tareas")
    assert r.status_code == 200 and "No se ha podido cargar" in r.text and "Reintentar" in r.text


# -------------------------------------------------------------------- crear
def test_crear_llama_al_core_y_redirige_a_la_ficha(cliente, csrf):
    r = _post(cliente, csrf, "/tareas", **CAMPOS)
    assert r.status_code == 204
    t = T.cargar()["tareas"][0]
    assert r.headers["hx-redirect"] == f"/tareas/{t['id']}"
    assert (t["titulo"], t["importancia"], t["depende"], t["limite"], t["etiquetas"]) == \
           ("Tarea nueva", 4, "damian", "2026-10-01", ["a", "b", "suyo:gustos"])   # se la asigna el: decision suya


@pytest.mark.parametrize("cambio,mensaje", [
    ({"titulo": "  "}, "El título no puede estar vacío"),
    ({"importancia": "9"}, "Importancia"),
    ({"coste": "x"}, "Coste"),
    ({"depende": "otro"}, "Depende de"),
    ({"limite": "mañana"}, "AAAA-MM-DD"),
    ({"etiquetas": "x" * 61}, "Etiqueta demasiado larga"),
])
def test_crear_invalido_no_toca_el_core(cliente, csrf, cambio, mensaje):
    r = _post(cliente, csrf, "/tareas", **{**CAMPOS, **cambio})
    assert r.headers["hx-retarget"] == "#error-nueva" and mensaje in r.text
    assert T.cargar()["tareas"] == []


def test_crear_sin_csrf_da_403(cliente, csrf):
    assert cliente.post("/tareas", data=CAMPOS).status_code == 403
    assert T.cargar()["tareas"] == []


# -------------------------------------------------------------------- ficha
def test_ficha_con_estado_real_notas_y_evidencia(cliente, csrf):
    t = T.anadir("Con notas", detalle="<b>no html</b>")
    T.anotar(t["id"], "primera")
    T.completar(t["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    T.verificar(t["id"], "pytest 97 passed")
    r = cliente.get(f"/tareas/{t['id']}").text
    assert "HECHO Y TESTEADO" in r and "testeada" in r
    assert 'class="nota-evidencia"' in r and "<strong>Evidencia:</strong>" in r and "pytest 97 passed" in r
    assert "&lt;b&gt;no html" in r and "<b>no html" not in r
    assert "Marcar hecha" not in r and "Verificar con evidencia" not in r  # ya hecha y testeada


def test_ficha_inexistente_da_404(cliente, csrf):
    assert cliente.get("/tareas/T999").status_code == 404


def test_sse_solo_repinta_la_ficha_no_los_formularios(cliente, csrf):
    t = T.anadir("x")
    pagina = cliente.get(f"/tareas/{t['id']}").text
    assert f'hx-get="/tareas/{t["id"]}/ficha"' in pagina
    ficha = cliente.get(f"/tareas/{t['id']}/ficha").text
    assert "<form" not in ficha and "Ficha" in ficha


# ------------------------------------------------------------------ acciones
def test_anotar(cliente, csrf):
    t = T.anadir("x")
    r = _post(cliente, csrf, f"/tareas/{t['id']}/nota", nota="nota desde la web")
    assert "nota desde la web" in r.text and "Nota añadida." in r.text
    assert T.cargar()["tareas"][0]["notas"][-1]["texto"] == "nota desde la web"
    assert _post(cliente, csrf, f"/tareas/{t['id']}/nota", nota="  ").headers["hx-retarget"] == "#error-nota"


def test_completar_deja_hecho_sin_testear(cliente, csrf):
    t = T.anadir("x")
    r = _post(cliente, csrf, f"/tareas/{t['id']}/completar", nota="quedó así",
              despues="nada: sin continuación", evidencia="revisado a mano en la ficha")
    assert "HECHO SIN TESTEAR" in r.text and "falta verificarla" in r.text
    guardada = T.cargar()["tareas"][0]
    assert guardada["estado"] == "hecha" and guardada["testeado"] is False
    assert guardada["despues"] == "nada: sin continuación" and guardada["cierre"]["estado_real"] == "HECHO SIN TESTEAR"


def test_cerrar_a_mano_viene_rellenado_y_se_cierra_con_un_clic(cliente, csrf):
    """Cerrar desde la ficha: «después» y evidencia ya vienen puestos (editables) y el formulario tal cual cierra."""
    t = T.anadir("x")
    html = cliente.get(f"/tareas/{t['id']}").text
    assert 'value="nada: cerrada por Damián"' in html
    assert ">cerrada a mano por Damián desde la web</textarea>" in html
    r = _post(cliente, csrf, f"/tareas/{t['id']}/completar", despues="nada: cerrada por Damián",
              evidencia="cerrada a mano por Damián desde la web", estado_real="HECHO SIN TESTEAR")
    assert "HECHO SIN TESTEAR" in r.text
    assert T.cargar()["tareas"][0]["estado"] == "hecha"


def test_completar_sin_despues_ni_evidencia_se_rechaza_y_no_cierra(cliente, csrf):
    t = T.anadir("x")
    r = _post(cliente, csrf, f"/tareas/{t['id']}/completar", nota="quedó así")
    assert r.headers["hx-retarget"] == "#error-completar" and "No se cierra" in r.text
    assert T.cargar()["tareas"][0]["estado"] == "pendiente"
    r = _post(cliente, csrf, f"/tareas/{t['id']}/completar", despues="nada: sin continuación",
              evidencia="pytest interfaz/tests: 12 passed", estado_real="HECHO Y TESTEADO")
    assert "HECHO Y TESTEADO" in r.text and T.cargar()["tareas"][0]["testeado"] is True


def test_crear_y_editar_con_los_campos_v2_y_la_ficha_los_ensena(cliente, csrf):
    r = _post(cliente, csrf, "/tareas", **{**CAMPOS, "depende": "claude", "objetivo": "Que el router sea uno solo",
                                          "hecho_cuando": "test verde" + chr(10) + "sin avisos", "donde": "nucleo/router.py",
                                          "tipo": "codigo", "coste_eur": "0",
                                          "instrucciones_damian": "Hazlo sin tocar permisos.py"})
    assert r.status_code == 204
    g = T.cargar()["tareas"][0]
    assert (g["objetivo"], g["hecho_cuando"], g["donde"], g["tipo"], g["coste_eur"]) ==         ("Que el router sea uno solo", ["test verde", "sin avisos"], "nucleo/router.py", "codigo", 0.0)
    ficha = cliente.get(f"/tareas/{g['id']}").text
    assert "Que el router sea uno solo" in ficha and "sin avisos" in ficha and "Hazlo sin tocar permisos.py" in ficha
    assert "Avisos de formato" not in ficha
    # editar: el objetivo se puede vaciar y el limite de 300 se exige en la web
    base = {**CAMPOS, "visto": _version_de(g["id"]), "estado": "pendiente", "depende": "claude"}
    r = _post(cliente, csrf, f"/tareas/{g['id']}/editar", **{**base, "objetivo": "x" * 301})
    assert r.headers["hx-retarget"] == "#error-editar" and "300" in r.text
    r = _post(cliente, csrf, f"/tareas/{g['id']}/editar", **{**base, "objetivo": "Nuevo objetivo", "tipo": "decision"})
    assert "Cambios guardados" in r.text and T.cargar()["tareas"][0]["tipo"] == "decision"


def test_las_tareas_viejas_se_ven_sin_los_campos_v2(cliente, csrf):
    t = T.anadir("Vieja sin nada", importancia=2)
    ficha = cliente.get(f"/tareas/{t['id']}")
    assert ficha.status_code == 200 and "Vieja sin nada" in ficha.text and "Avisos de formato" not in ficha.text
    assert "Hecho cuando" not in cliente.get(f"/tareas/{t['id']}/ficha").text


def test_verificar_exige_evidencia(cliente, csrf):
    t = T.anadir("x")
    T.completar(t["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    r = _post(cliente, csrf, f"/tareas/{t['id']}/verificar", evidencia="ok")
    assert r.headers["hx-retarget"] == "#error-verificar" and "evidencia" in r.text.lower()
    assert T.cargar()["tareas"][0]["testeado"] is False
    r = _post(cliente, csrf, f"/tareas/{t['id']}/verificar", evidencia="pytest interfaz/ 102 passed")
    assert "HECHO Y TESTEADO" in r.text
    assert T.cargar()["tareas"][0]["notas"][-1]["texto"] == "[verificado] pytest interfaz/ 102 passed"


def test_acciones_sobre_tarea_inexistente(cliente, csrf):
    for url, datos in (("nota", {"nota": "x"}), ("completar", {}), ("verificar", {"evidencia": "evidencia larga"})):
        r = _post(cliente, csrf, f"/tareas/T999/{url}", **datos)
        assert "no existe" in r.text and "hx-retarget" in r.headers


# --------------------------------------------------------------------- editar
def _editar(cliente, csrf, t, **cambios):
    from interfaz.rutas.tareas import _version
    datos = {**CAMPOS, "visto": _version(t), "estado": t["estado"], "bloqueada_por": "", **cambios}
    return _post(cliente, csrf, f"/tareas/{t['id']}/editar", **datos)


def test_editar_guarda_por_el_core(cliente, csrf):
    t = T.anadir("original")
    r = _editar(cliente, csrf, t, titulo="cambiada", estado="bloqueada", bloqueada_por="T001")
    assert "Cambios guardados." in r.text and "BLOQUEADO" in r.text
    g = T.cargar()["tareas"][0]
    assert (g["titulo"], g["estado"], g["bloqueada_por"], g["importancia"]) == ("cambiada", "bloqueada", "T001", 4)


def test_editar_rechaza_si_la_tarea_cambio_mientras_tanto(cliente, csrf):
    t = T.anadir("original")
    visto = dict(t)
    datos = T.cargar()
    datos["tareas"][0]["estado"] = "en_curso"  # otro proceso la toco en el MISMO segundo:
    T.guardar(datos)                           # 'actualizada' no cambia, la huella si
    r = _editar(cliente, csrf, visto, titulo="pisaria")
    assert r.headers["hx-retarget"] == "#error-editar" and "cambió mientras la editabas" in r.text
    assert T.cargar()["tareas"][0]["titulo"] == "original"


def test_reabrir_una_tarea_hecha_le_quita_el_testeado(cliente, csrf):
    t = T.anadir("x")
    T.completar(t["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    t = T.verificar(t["id"], "probada a mano: abre y guarda")  # T160: un tick ya no vale
    _editar(cliente, csrf, t, estado="pendiente")
    g = T.cargar()["tareas"][0]
    assert g["estado"] == "pendiente" and g["testeado"] is False
    # Y al volver a cerrarla queda SIN TESTEAR, no hereda la comprobacion vieja.
    T.completar(t["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    assert T.estado_real(T.cargar()["tareas"][0]) == "HECHO SIN TESTEAR"


def test_editar_estado_invalido(cliente, csrf):
    t = T.anadir("x")
    r = _editar(cliente, csrf, t, estado="inventado")
    assert r.headers["hx-retarget"] == "#error-editar"
    assert T.cargar()["tareas"][0]["estado"] == "pendiente"


def test_editar_sin_csrf_da_403(cliente, csrf):
    t = T.anadir("x")
    datos = {**CAMPOS, "visto": "x", "estado": "hecha"}
    assert cliente.post(f"/tareas/{t['id']}/editar", data=datos).status_code == 403
    assert T.cargar()["tareas"][0]["estado"] == "pendiente"


def test_verificar_una_tarea_sin_cerrar_se_rechaza(cliente, csrf):
    t = T.anadir("pendiente")
    r = _post(cliente, csrf, f"/tareas/{t['id']}/verificar", evidencia="evidencia de antes de hacerla")
    assert r.headers["hx-retarget"] == "#error-verificar" and "ciérrala primero" in r.text
    assert T.cargar()["tareas"][0]["testeado"] is False
    assert "Verificar con evidencia" not in cliente.get(f"/tareas/{t['id']}").text


# -------------------------------------------------------------------- T005: modelo y esfuerzo para Code
@pytest.mark.parametrize("dificultad,importancia,esperado", [
    (1, 2, ("Sonnet", "medium")), (3, 3, ("Sonnet", "high")), (5, 5, ("Opus", "high")),
    (2, 5, ("Sonnet", "high")),   # importante pero facil: no pide Opus
])
def test_sugerencia_claude_por_dificultad_e_importancia(dificultad, importancia, esperado):
    s = T.sugerencia_claude({"dificultad": dificultad, "importancia": importancia, "depende": "ia"})
    assert (s["modelo"], s["esfuerzo"]) == esperado and s["texto"] == f"{esperado[0]} · {esperado[1]}"


def test_sugerencia_claude_solo_para_tareas_de_la_ia():
    assert T.sugerencia_claude({"dificultad": 5, "importancia": 5, "depende": "damian"}) is None
    assert T.sugerencia_claude({"dificultad": 5, "importancia": 5, "depende": "externo"}) is None


def test_lista_y_ficha_muestran_modelo_y_esfuerzo(cliente, csrf):
    dura = T.anadir("dura", dificultad=5, importancia=5)
    T.anadir("de damian", depende="damian")
    lista = cliente.get("/tareas").text
    assert "Claude: Opus · high" in lista   # T230: tarjetas en vez de tabla; el dato sigue en cada una
    ficha = cliente.get(f"/tareas/{dura['id']}").text
    assert "<strong>Opus</strong>, esfuerzo <strong>high</strong>" in ficha


def test_cli_siguiente_dice_con_que_abrir_la_sesion(capsys):
    T.anadir("facil", dificultad=1, importancia=2, urgencia=5)
    T._cli(["siguiente"])
    assert "[abrir con Sonnet, esfuerzo medium]" in capsys.readouterr().out


# -------------------------------------------------------------------- T674: investigaciones con RESULTADO
def test_ficha_de_investigacion_pide_resultado_y_motivo(cliente, csrf):
    t = T.anadir("Investigar X", etiquetas=["cat:investigacion"])
    html = cliente.get(f"/tareas/{t['id']}").text
    assert 'name="decision"' in html and "ADOPTAR" in html and "DESCARTAR" in html and 'name="motivo"' in html
    otra = T.anadir("Arreglar algo")
    assert 'name="decision"' not in cliente.get(f"/tareas/{otra['id']}").text


def test_completar_investigacion_sin_resultado_no_cierra(cliente, csrf):
    t = T.anadir("Investigar X", etiquetas=["cat:investigacion"])
    r = _post(cliente, csrf, f"/tareas/{t['id']}/completar", nota="ya esta")
    assert r.headers["hx-retarget"] == "#error-completar" and "No se cierra" in r.text
    assert T.buscar(t["id"])["estado"] == "pendiente"


def test_completar_investigacion_con_adoptar_crea_la_integracion(cliente, csrf):
    t = T.anadir("Investigar X", etiquetas=["cat:investigacion"])
    r = _post(cliente, csrf, f"/tareas/{t['id']}/completar", decision="ADOPTAR",
              motivo="encaja con el router y no trae dependencias nuevas")
    g = T.buscar(t["id"])
    assert g["estado"] == "esperando" and g["resultado"]["quien"] == "damian"
    hija = next(e.split(":", 1)[1] for e in g["etiquetas"] if e.startswith("integracion:"))
    assert f"creada la integración {hija}" in r.text and T.buscar(hija)["estado"] == "pendiente"


def test_completar_investigacion_con_descartar_la_cierra(cliente, csrf):
    t = T.anadir("Investigar X", etiquetas=["cat:investigacion"])
    r = _post(cliente, csrf, f"/tareas/{t['id']}/completar", decision="DESCARTAR",
              motivo="no aporta frente a lo que ya tiene NEXO")
    assert "resultado DESCARTAR" in r.text and T.buscar(t["id"])["estado"] == "hecha"


def test_editar_investigacion_a_hecha_sin_resultado_se_rechaza(cliente, csrf):
    t = T.anadir("Investigar X", etiquetas=["cat:investigacion"])
    r = _editar(cliente, csrf, t, titulo="Investigar X", estado="hecha", etiquetas="cat:investigacion")
    assert r.headers["hx-retarget"] == "#error-editar" and "RESULTADO" in r.text
    assert T.buscar(t["id"])["estado"] == "pendiente"
