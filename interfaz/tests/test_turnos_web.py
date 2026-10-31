# -*- coding: utf-8 -*-
"""T231 (rediseno 28/09): pagina /turnos como TABLA, bloque Turnos del Centro. Sin procesos reales."""
from __future__ import annotations

import json
import re

import pytest

from nucleo import parada, planificador, registro, turnos


def _post(cliente, csrf, ruta, **datos):
    return cliente.post(ruta, data=datos, headers={"X-CSRF-Token": csrf})


def _turno(**campos):
    base = {"nombre": "Noche 03:30", "plantilla": "cola", "dias": list(turnos.DIAS), "horas": ["03:30"]}
    return turnos.guardar_turno(dict(base, **campos))


@pytest.fixture
def lanzados(monkeypatch):
    from nucleo import plantillas_turno
    monkeypatch.setattr(plantillas_turno, "candidatas", lambda ctx: 1)   # hay trabajo (aqui se prueba la cola)
    vistos = []

    class Proc:
        pid = 99999999
    monkeypatch.setattr(planificador, "_popen", lambda args, **k: vistos.append(args) or Proc())
    return vistos


def test_pagina_y_menu(cliente, csrf):
    r = cliente.get("/turnos")
    assert r.status_code == 200 and 'href="/turnos"' in r.text and "Añadir turno" in r.text
    assert "nunca escribe código" in r.text and 'hx-get="/turnos/tabla"' in r.text


def test_tabla_con_proxima_y_ultimo_resultado(cliente, csrf):
    t = _turno()
    registro.CARPETA.mkdir(parents=True, exist_ok=True)
    (registro.CARPETA / "turno_nexo_20260928_033000.json").write_text(json.dumps({
        "inicio": "2026-09-28T03:30:00", "turno_id": t["id"], "nombre_turno": t["nombre"],
        "pasos": {"trabajo": {"filas": [{"tarea": "T1", "propuestas": ["T2", "T3"]}]}}}), encoding="utf-8")
    r = cliente.get("/turnos/tabla")
    assert "Noche 03:30" in r.text and "todos los días · 03:30" in r.text and "Tareas de la cola por orden" in r.text
    assert "28/09 03:30: 1 tarea(s), 2 propuesta(s)" in r.text
    assert re.search(r"(lun|mar|mié|jue|vie|sáb|dom) \d\d/\d\d 03:30", r.text)       # proxima ejecucion
    for boton in ("Editar", "Duplicar", "Borrar", "Lanzar ya", "Activo"):
        assert boton in r.text


def test_alta_por_formulario(cliente, csrf):
    assert "Nuevo turno" in cliente.get("/turnos/nuevo").text
    r = cliente.post("/turnos/guardar", headers={"X-CSRF-Token": csrf}, data={
        "nombre": "Vigía diario", "plantilla": "vigia", "instrucciones": "", "tareas": "", "dias": ["lunes", "viernes"],
        "horas": "09:15", "max_tareas": "1", "max_minutos": "30", "avisar": "si", "activo": "si"})
    assert "Turno «Vigía diario» guardado" in r.text and "L V · 09:15" in r.text and "1 tarea(s) · 30 min" in r.text
    assert 'id="turno-form" hx-swap-oob="innerHTML"' in r.text          # cierra el formulario
    [t] = turnos.cargar()["turnos"]
    assert (t["plantilla"], t["avisar"], t["activo"]) == ("vigia", True, True)


def test_alta_con_error_vuelve_al_formulario(cliente, csrf):
    r = cliente.post("/turnos/guardar", headers={"X-CSRF-Token": csrf}, data={
        "nombre": "Malo", "plantilla": "cola", "dias": ["lunes"], "horas": "3:30", "max_minutos": "55"})
    assert r.headers["HX-Retarget"] == "#turno-form" and "hora no valida" in r.text and 'value="Malo"' in r.text
    assert turnos.cargar()["turnos"] == []


def test_editar_duplicar_activo_y_borrar(cliente, csrf):
    t = _turno(instrucciones="Solo seguridad.")
    r = cliente.get(f"/turnos/{t['id']}/editar")
    assert "Editar «Noche 03:30»" in r.text and "Solo seguridad." in r.text
    r = _post(cliente, csrf, f"/turnos/{t['id']}/duplicar")
    assert "nace INACTIVO" in r.text and "Noche 03:30 (copia)" in r.text
    r = _post(cliente, csrf, f"/turnos/{t['id']}/activo", valor="no")
    assert "INACTIVO" in r.text and not turnos.buscar(t["id"])["activo"]
    r = _post(cliente, csrf, f"/turnos/{t['id']}/borrar")
    assert "queda archivado" in r.text and turnos.buscar(t["id"]) is None


def test_post_sin_csrf_no_hace_nada(cliente, csrf):
    t = _turno()
    assert cliente.post(f"/turnos/{t['id']}/borrar").status_code == 403
    assert cliente.post(f"/turnos/{t['id']}/lanzar").status_code == 403
    assert turnos.buscar(t["id"])


def test_choque_de_horas_se_avisa_en_la_tabla(cliente, csrf):
    _turno(nombre="A", horas=["03:30"])
    _turno(nombre="B", horas=["04:00"])
    r = cliente.get("/turnos/tabla")
    assert "Coincide con B: el segundo esperará en cola" in r.text and "Coincide con A" in r.text


def test_lanzar_ya_arranca_y_el_segundo_queda_en_cola(cliente, csrf, lanzados):
    a, b = _turno(nombre="Revisar codigo", plantilla="revisar_codigo"), _turno(nombre="Vigia", plantilla="vigia")
    r = _post(cliente, csrf, f"/turnos/{a['id']}/lanzar")
    assert "«Revisar codigo» arrancado" in r.text and f"--turno={a['id']}" in lanzados[0] and "--manual" in lanzados[0]
    r = _post(cliente, csrf, f"/turnos/{b['id']}/lanzar")
    assert "«Vigia» en cola" in r.text and "en cola (1º)" in r.text and "en marcha" in r.text and len(lanzados) == 1


def test_lanzar_ya_respeta_parada_e_interruptor(cliente, csrf, lanzados):
    t = _turno()
    parada.activar("prueba", "damian")
    assert "PARADA" in _post(cliente, csrf, f"/turnos/{t['id']}/lanzar").text
    parada.desactivar()
    r = _post(cliente, csrf, "/turnos/interruptor", accion="off", motivo="de viaje")
    assert "TODOS los turnos en pausa" in r.text and "de viaje" in r.text and "Reanudar todos los turnos" in r.text
    assert "desactivados" in _post(cliente, csrf, f"/turnos/{t['id']}/lanzar").text
    assert lanzados == [] and planificador.cola() == []


def test_textos_de_plantilla(cliente, csrf):
    r = _post(cliente, csrf, "/turnos/texto", plantilla="revisar_codigo", texto="Mira solo la seguridad.")
    assert "Texto guardado" in r.text and "Mira solo la seguridad." in r.text
    _post(cliente, csrf, "/turnos/texto", plantilla="revisar_codigo", texto="x", restablecer="1")
    assert turnos.texto_plantilla("revisar_codigo") == turnos.PLANTILLAS["revisar_codigo"]["texto"]


def test_formulario_sin_casillas_con_estilo_de_campo_de_texto(cliente, csrf):
    """Punto 3 del 28/09: las casillas dentro de .campos heredaban padding/min-height y se montaban."""
    for html in (cliente.get("/turnos/nuevo").text, cliente.get("/turnos").text):
        for bloque in re.findall(r'<div class="campos">(.*?)</div>', html, re.S):
            assert 'type="checkbox"' not in bloque
    css = cliente.get("/estatico/nexo.css").text
    assert '.campos input[type="checkbox"], .campos input[type="radio"] { min-height: 0; padding: 0; width: auto; }' in css


def test_bloque_turnos_del_centro(cliente, csrf):
    t = _turno(nombre="Tarde", horas=["17:00"])
    import os
    import time
    planificador.progreso(pid_turno=os.getpid(), turno=t["id"], nombre="Tarde", paso="trabajo",
                          tarea="T001 Investigar X", lanzado=time.time() - 65)
    r = cliente.get("/centro/turnos")
    assert "Tarde" in r.text and "trabajo" in r.text and "1 min" in r.text and "Trabajando en T001 Investigar X" in r.text
    assert "Próximo" in r.text and "Último" in r.text
    assert 'hx-get="/centro/turnos"' in cliente.get("/").text


def test_resumen_de_turnos(cliente, csrf):
    registro.CARPETA.mkdir(parents=True, exist_ok=True)
    (registro.CARPETA / "turno_nexo_20260928_033000.json").write_text(json.dumps({
        "inicio": "2026-09-28T03:30:00", "nombre_turno": "Noche 03:30", "solo_lectura": {"ok": True, "cambiados": []},
        "pasos": {"trabajo": {"filas": [{"tarea": "T300", "titulo": "Lote 1", "veredicto": "OK_ABSOLUTO",
                                          "auditoria": "APROBADA", "revision_claude": "T301", "propuestas": ["T302"]}]}}}),
        encoding="utf-8")
    r = cliente.get("/turnos/resumen")
    assert "Noche 03:30" in r.text and 'href="/tareas/T302"' in r.text and "el turno no escribió nada en el proyecto" in r.text


# ------------------------------------------------------------------ control individual (28/09)
def test_lista_en_marcha_y_en_cola_con_sus_botones(cliente, csrf, lanzados):
    a, b = _turno(nombre="Revisar codigo"), _turno(nombre="Vigia")
    _post(cliente, csrf, f"/turnos/{a['id']}/lanzar")
    _post(cliente, csrf, f"/turnos/{b['id']}/lanzar")
    for ruta in ("/turnos/en-curso", "/centro/turnos"):
        r = cliente.get(ruta)
        assert "Revisar codigo" in r.text and "Parar este turno" in r.text
        assert "1º <strong>Vigia</strong>" in r.text and "Quitar de la cola" in r.text
        assert "Mañana a la misma hora" in r.text and 'type="time" name="hora"' in r.text
    assert 'id="msg-turnos"' in cliente.get("/turnos").text and 'id="msg-turnos"' in cliente.get("/").text


def test_parar_quitar_y_posponer_desde_la_web(cliente, csrf, lanzados):
    a, b = _turno(nombre="A"), _turno(nombre="B")
    _post(cliente, csrf, f"/turnos/{a['id']}/lanzar")
    _post(cliente, csrf, f"/turnos/{b['id']}/lanzar")
    r = _post(cliente, csrf, f"/turnos/{b['id']}/posponer", opcion="hora", hora="23:45")
    assert "pospuesto hasta" in r.text and "23:45" in r.text and r.headers["HX-Trigger"] == "nexo:turno_estado"
    assert "pospuesto hasta" in cliente.get("/turnos/en-curso").text
    r = _post(cliente, csrf, f"/turnos/cola/{b['id']}/quitar")
    assert "quitado de la cola" in r.text and planificador.cola() == []
    r = _post(cliente, csrf, "/turnos/marcha/parar")
    assert "Parando «A»" in r.text and "PARADA general no se toca" in r.text
    assert parada.cierre_pedido() and not parada.activa() and "parando" in cliente.get("/turnos/en-curso").text
    r = _post(cliente, csrf, f"/turnos/{a['id']}/posponer", opcion="siglo")
    assert 'class="nota nota-bloqueo"' in r.text


def test_tabla_desactivar_saltar_y_borrar_por_turno(cliente, csrf):
    t = _turno(nombre="Tarde", horas=["17:00"])
    r = cliente.get("/turnos/tabla")
    for boton in ("Desactivar este", "Saltar la próxima", "Borrar", "Pausar TODOS los turnos"):
        assert boton in r.text
    assert "Sale de la tabla y queda archivado" in r.text          # la confirmacion del borrado
    r = _post(cliente, csrf, f"/turnos/{t['id']}/saltar")
    assert "Se saltará solo la del" in r.text and "(se salta la del" in r.text and "No saltar" in r.text
    r = _post(cliente, csrf, f"/turnos/{t['id']}/saltar", deshacer="1")
    assert "Ya no se salta" in r.text and "Saltar la próxima" in r.text
    r = _post(cliente, csrf, f"/turnos/{t['id']}/activo", valor="no")
    assert "Activar este" in r.text and "Saltar la próxima" not in r.text
    assert turnos.buscar(t["id"])["activo"] is False and len(turnos.cargar()["turnos"]) == 1


# ------------------------------------------------------------------ reanudar, reordenar y tabla (2a ronda)
def test_reordenar_y_reanudar_desde_la_web(cliente, csrf, lanzados):
    a, b, c = _turno(nombre="A"), _turno(nombre="B"), _turno(nombre="C")
    for t in (a, b, c):
        _post(cliente, csrf, f"/turnos/{t['id']}/lanzar")          # A arranca; B y C en cola
    html = cliente.get("/turnos/en-curso").text
    assert "Pasar C el primero" in html and "Bajar B" in html and "Pasar B el primero" not in html
    r = _post(cliente, csrf, f"/turnos/cola/{c['id']}/mover", hacia="primero")
    assert "pasa el primero" in r.text and [x["turno"] for x in planificador.cola()] == [c["id"], b["id"]]
    _post(cliente, csrf, f"/turnos/{b['id']}/posponer", opcion="1h")
    assert "Reanudar ahora" in cliente.get("/turnos/en-curso").text
    r = _post(cliente, csrf, f"/turnos/{b['id']}/reanudar")
    assert "reanudado" in r.text and planificador.cola()[0]["turno"] == b["id"]
    r = _post(cliente, csrf, "/turnos/marcha/parar")
    planificador.terminar()
    html = cliente.get("/turnos/en-curso").text
    assert "Parados hace poco" in html and f'/turnos/{a["id"]}/reanudar' in html


def test_reanudar_todos_se_ve_en_turnos_y_en_el_centro(cliente, csrf):
    turnos.desactivar("de viaje")
    for ruta in ("/turnos/en-curso", "/centro/turnos"):
        html = cliente.get(ruta).text
        assert "TODOS los turnos están en pausa" in html and 'class="boton-grande" hx-post="/turnos/reanudar-todos"' in html
    assert 'class="boton-grande">Reanudar todos los turnos' in cliente.get("/turnos/tabla").text
    r = _post(cliente, csrf, "/turnos/reanudar-todos")
    assert "Turnos reanudados" in r.text and turnos.desactivados() is None


def test_columna_estado_no_se_parte(cliente, csrf):
    _turno(nombre="Tarde")
    html = cliente.get("/turnos/tabla").text
    assert '<th scope="col">Turno</th><th scope="col">Estado</th>' in html
    assert 'data-etiqueta="Estado"><span class="estado-turno estado-turno-on">● Activo</span>' in html
    assert 'data-etiqueta="Activo"' not in html
    assert ".estado-turno { display: inline-block; white-space: nowrap;" in cliente.get("/estatico/nexo.css").text


# ------------------------------------------------------------------ d) por que un turno no hizo nada (28/09)
def test_lanzar_ya_avisa_antes_si_no_haria_nada(cliente, csrf, monkeypatch):
    lanzados = []
    monkeypatch.setattr(planificador, "_popen", lambda args, **k: lanzados.append(args))
    t = _turno(nombre="Correcciones", plantilla="correcciones")
    r = _post(cliente, csrf, f"/turnos/{t['id']}/lanzar")
    assert "«Correcciones» no haría nada ahora: no había errores de código pendientes" in r.text
    assert "No se ha lanzado" in r.text and lanzados == [] and planificador.cola() == []


def test_la_web_explica_por_que_no_hizo_nada(cliente, csrf):
    t = _turno(nombre="Vigía")
    registro.CARPETA.mkdir(parents=True, exist_ok=True)
    (registro.CARPETA / "turno_nexo_20260928_181035.json").write_text(json.dumps({
        "inicio": "2026-09-28T18:10:34", "turno_id": t["id"], "nombre_turno": "Vigía",
        "abortado": "sin candidatas para esta plantilla: no se despierta a nadie",
        "explicacion": "el vigía de novedades ya pasó hoy (va una vez al día) y su lote de hoy ya está trabajado; "
                       "vuelve mañana", "pasos": {}}), encoding="utf-8")
    assert "Por qué no hizo nada:</strong> el vigía de novedades ya pasó hoy" in cliente.get("/turnos/resumen").text
    assert "no hizo nada: el vigía de novedades ya pasó hoy" in cliente.get("/turnos/tabla").text
    assert "no hizo nada: el vigía de novedades ya pasó hoy" in cliente.get("/centro/turnos").text


def test_trabajar_ahora_encola_y_enseña_por_que_no_el_resto(cliente, csrf, lanzados, monkeypatch):
    from nucleo import plantillas_turno
    cola = _turno(nombre="Cola noche", plantilla="cola")
    vig = _turno(nombre="Vigía", plantilla="vigia")
    monkeypatch.setattr(plantillas_turno, "candidatas", lambda ctx: 1 if ctx["plantilla"] == "cola" else 0)
    monkeypatch.setattr(plantillas_turno, "por_que_nada", lambda ctx: "ya hecho hoy")
    r = _post(cliente, csrf, "/turnos/trabajar", horas="2")
    assert r.status_code == 200 and "encolado" in r.text and "Modo trabajo" in r.text
    assert "Dejar de trabajar" in r.text and "Vigía: sin trabajo: ya hecho hoy" in r.text
    assert planificador.modo_trabajo()
    r = _post(cliente, csrf, "/turnos/trabajar/parar")
    assert "Modo trabajo quitado" in r.text and not planificador.modo_trabajo()
    assert cola["id"] and vig["id"]


def test_trabajar_ahora_con_parada_no_encola(cliente, csrf, lanzados):
    parada.activar("prueba")
    r = _post(cliente, csrf, "/turnos/trabajar", horas="0")
    assert "PARADA" in r.text and planificador.cola() == []
