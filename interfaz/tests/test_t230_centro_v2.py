# -*- coding: utf-8 -*-
"""T230, Centro v2 (aprobado por Damian el 18/10; documentacion/diseno/CENTRO_V2.md). Todo en tmp_path y con dobles:
ni Ollama, ni memoria/ real. Una clase de tests por pieza."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytest

from interfaz import hecho_llano, presentar
from nucleo import aprobaciones as ap
from nucleo import avisos
from nucleo import tareas as T

AHORA = datetime(2026, 10, 18, 12, 0, 0)


@pytest.fixture
def sin_turnos(monkeypatch):
    from nucleo import planificador
    monkeypatch.setattr(planificador, "resumen_centro", lambda: {"marcha": None, "cola": [], "proximo": None,
                                                                 "desactivados": 0})


def _post(cliente, csrf, url, **datos):
    return cliente.post(url, data=datos, headers={"X-CSRF-Token": csrf})


def _suya(titulo, **kw):
    return T.anadir(titulo, depende="damian", etiquetas=["suyo:gustos"], **kw)   # suya de verdad (guardia 05/10)


def _cerrar(tid, cuando, evidencia="", testeado=True, **extra):
    """Cierra una tarea como hecha en `cuando` (sin pasar por completar: aqui solo importa lo que se ve)."""
    datos = T.cargar()
    for x in datos["tareas"]:
        if x["id"] == tid:
            x.update(estado="hecha", cerrada=cuando, testeado=testeado,
                     cierre={"estado_real": "HECHO Y TESTEADO" if testeado else "HECHO SIN TESTEAR",
                             "evidencia": evidencia or "se hizo y se comprobó con pruebas automáticas", **extra.pop("cierre", {})},
                     **extra)
    T.guardar(datos)


# ------------------------------------------------------------------ Pieza 1: Te toca
def test_llano_quita_para_damian_y_el_contador_final():
    assert presentar.llano("Para Damian: pasarme la información del proyecto (5)") == "Pasarme la información del proyecto"
    assert presentar.llano("T123 · Para Damián - decidir qué hago con WAVER (12)") == "Decidir qué hago con WAVER"
    assert presentar.llano("para damian: x") == "X"
    assert presentar.llano("Revisar (los 3 reels) pendientes") == "Revisar (los 3 reels) pendientes"   # no es un contador final


def test_cuando_llano_y_plazo_en_palabras():
    assert presentar.cuando_llano("2026-10-18 20:00:00", AHORA) == "hoy a las 20:00"
    assert presentar.cuando_llano("2026-10-19 12:22:00", AHORA) == "mañana a las 12:22"
    assert presentar.cuando_llano("2026-10-25 09:05:00", AHORA) == "el 25/10 a las 09:05"
    assert presentar.cuando_llano("basura", AHORA) == ""
    assert presentar.plazo_llano({"tipo": "ambar", "vence": "2026-10-19 12:22:00"}, AHORA) == \
        "Si no dices nada, caduca mañana a las 12:22"
    assert presentar.plazo_llano({"tipo": "r1", "vence": "2026-10-18 20:00:00"}, AHORA) == \
        "Si no dices nada, se hará hoy a las 20:00"
    assert presentar.plazo_llano({"tipo": "r2", "vence": "2026-10-25 09:05:00"}, AHORA) == \
        "Si no dices nada, se descarta el 25/10 a las 09:05"
    assert presentar.plazo_llano({"tipo": "chat"}, AHORA) == "Si no dices nada, caduca en 24 horas"
    assert presentar.plazo_llano({"tipo": "tarea"}, AHORA) == ""


def test_la_tarjeta_de_permiso_trae_plazo_titulo_real_quien_lo_pide_y_los_botones(cliente, csrf):
    a = ap.solicitar("ejecutar comando", "git add nucleo/permisos.py; git commit -m 'guardia de comandos'", origen="mcp",
                     extra={"para_que": "El cambio ya está aplicado y probado; solo falta registrarlo."})
    r = cliente.get("/centro/te_toca").text
    assert "Pide permiso" in r and "Si no dices nada, caduca " in r
    assert "Guardar en el historial (git) un cambio" in r and "Aplicar un parche" not in r      # el titulo dice QUE se hace
    assert "Lo pide Claude." in r and "solo falta registrarlo" in r
    assert a["id"] not in r.replace(f'value="{a["id"]}"', "").replace(f'/aprobacion/{a["id"]}', "")  # ni IDs a la vista
                                                                                   # (T1020: el enlace a la ficha si)
    assert 'hx-post="/ambar/decidir"' in r and 'name="desde" value="centro"' in r
    assert re.findall(r'<button type="submit" name="accion" value="(\w+)">([^<]+)</button>', r) == \
        [("aprobar", "Aprobar"), ("denegar", "Denegar")]
    assert "Ver el cambio" in r


def test_aprobar_desde_la_tarjeta_usa_el_mismo_endpoint_y_repinta_te_toca(cliente, csrf):
    a = ap.solicitar("ejecutar comando", "pip install algo", origen="mcp")
    r = _post(cliente, csrf, "/ambar/decidir", id=a["id"], accion="aprobar", desde="centro", todas="0")
    assert r.status_code == 200 and "Aprobada" in r.text and "tt-tarjetas" not in r.text      # ya no hay tarjeta
    assert ap.ver(a["id"])["estado"] == "aprobada"
    b = ap.solicitar("ejecutar comando", "pip install otro", origen="mcp")
    r = _post(cliente, csrf, "/ambar/decidir", id=b["id"], accion="denegar")              # sin desde: panel de Bandejas
    assert "Denegada" in r.text and ap.ver(b["id"])["estado"] == "denegada"


def test_r1_se_acepta_o_se_veta_desde_la_tarjeta(cliente, csrf):
    from nucleo import riesgo
    t = T.anadir("Test de la cola", detalle="QUE: x\nDONDE: tests/test_cola.py")
    s = ap.ver(riesgo.autorizacion(T.buscar(t["id"]))["solicitud"])
    r = cliente.get("/centro/te_toca").text
    assert "Se hará si no dices nada" in r and "Si no dices nada, se hará " in r
    assert re.findall(r'name="accion" value="(\w+)">([^<]+)<', r)[:2] == [("aceptar", "Aceptar"), ("denegar", "Vetar")]
    r = _post(cliente, csrf, "/riesgo/decidir", id=s["id"], accion="aceptar", desde="centro")
    assert "Aceptada" in r.text and ap.ver(s["id"])["estado"] == "aprobada"


def test_tus_tareas_filas_de_una_linea_y_la_de_fecha_limite_primero(cliente, csrf, sin_turnos):
    _suya("Para Damian: sin prisa alguna (3)")
    limite = datetime.now().date() + timedelta(days=10)       # 20/10: fija en 2026-10-20 fallaba ese dia ("vence hoy")
    con = _suya("Mandar los papeles de la beca", limite=limite.isoformat())
    r = cliente.get("/centro/te_toca").text
    assert r.index("Mandar los papeles de la beca") < r.index("Sin prisa alguna")
    assert "Sin prisa alguna" in r and "Para Damian" not in r and "(3)" not in r
    assert f"vence el {limite:%d/%m}" in r and "<ul class=\"tt-filas\">" in r and r.count(">Abrir</a>") == 2
    assert f'href="/tareas/{con["id"]}"' in r
    frase = cliente.get("/centro/frase").text
    assert "Tienes 2 tareas tuyas, 1 con fecha límite." in frase
    assert presentar.te_toca_llano(None)["con_fecha"] == 1


def test_la_frase_dice_ninguna_con_prisa_y_cuenta_las_decisiones(cliente, csrf, sin_turnos):
    for i in range(3):
        _suya(f"Tarea mía {i}")
    ap.solicitar("ejecutar comando", "pip install x", origen="mcp")
    assert "1 cosa necesita tu decisión y tienes 3 tareas tuyas, ninguna con prisa." in cliente.get("/centro/frase").text


# ------------------------------------------------------------------ Pieza 1: revisor.explicar
def test_explicar_un_commit_no_es_aplicar_un_parche():
    from nucleo import revisor
    s = {"accion": "ejecutar comando", "origen": "mcp",
         "detalle": "git add nucleo/permisos.py; git commit -m 'aplica el parche de la guardia (.patch)'"}
    e = revisor.explicar(s)
    assert e["que"] == "Guardar en el historial (git) un cambio." and e["quien_corto"] == "Claude"
    assert e["frase"].startswith("Guardar en el historial (git) un cambio. Lo pide Claude. Riesgo:")
    assert revisor.explicar({**s, "detalle": "git apply guardia.patch"})["que"].startswith("Aplicar un parche")


# ------------------------------------------------------------------ Pieza 2: ultima visita
def test_un_refresco_a_menos_de_30_min_no_mueve_la_ultima_visita():
    assert presentar.ultima_visita() is None
    presentar.registrar_visita(AHORA)                                              # primera carga: sin visita anterior
    assert presentar.ultima_visita() is None
    presentar.registrar_visita(AHORA + timedelta(minutes=25))                      # refresco: misma visita
    presentar.registrar_visita(AHORA + timedelta(minutes=50))                      # otro refresco (25 min desde el anterior)
    assert presentar.ultima_visita() is None
    vuelve = AHORA + timedelta(hours=5)
    presentar.registrar_visita(vuelve)                                             # hueco >30 min: visita nueva
    assert presentar.ultima_visita() == AHORA + timedelta(minutes=50)              # la ultima carga de la visita anterior
    presentar.registrar_visita(vuelve + timedelta(minutes=29))
    assert presentar.ultima_visita() == AHORA + timedelta(minutes=50)              # y recargar no la mueve
    assert presentar.visita_llana(vuelve) == "hoy a las 12:50"


def test_cargar_el_centro_registra_la_visita_y_la_enseña(cliente, csrf):
    assert "Primera visita" in cliente.get("/").text
    presentar.VISITA.write_text('{"anterior": "2026-10-18 00:25:00", "actual": "2026-10-18 00:25:00"}', encoding="utf-8")
    assert "Tu última visita: " in cliente.get("/").text


# ------------------------------------------------------------------ Pieza 2: Hecho desde tu ultima visita
def _visita_anterior(cuando="2026-10-18 00:25:00"):
    presentar.VISITA.write_text(f'{{"anterior": "{cuando}", "actual": "{cuando}"}}', encoding="utf-8")


def test_hecho_agrupa_por_commit_y_por_epica_y_solo_cuenta_lo_posterior_a_la_visita():
    _visita_anterior()
    a, b, c = (T.anadir(f"Arreglo de imágenes número {i}") for i in range(3))
    d = T.anadir("Cambio suelto de tema X", etiquetas=["tema:voz"])
    e = T.anadir("Otro cambio de tema X", etiquetas=["tema:voz"])
    f = T.anadir("Tarea aislada")
    viejo = T.anadir("Cerrada antes de la visita")
    _cerrar(a["id"], "2026-10-18 09:00:00", "commit 1a2b3c4 y tests 12 passed")
    _cerrar(b["id"], "2026-10-18 09:10:00", "commit 1a2b3c4d: fusionado")        # mismo commit (prefijo de 7)
    _cerrar(c["id"], "2026-10-18 09:20:00", "commit 1a2b3c4 tambien")
    _cerrar(d["id"], "2026-10-18 10:00:00", "se hizo y se comprobó con pruebas")
    _cerrar(e["id"], "2026-10-18 10:30:00", "se hizo y se comprobó con pruebas")
    _cerrar(f["id"], "2026-10-18 11:00:00", "se hizo y se comprobó con pruebas")
    _cerrar(viejo["id"], "2026-10-17 23:00:00", "se hizo y se comprobó con pruebas")
    h = presentar.hecho_desde_visita(AHORA)
    assert h["total"] == 6 and h["n_grupos"] == 3
    ns = sorted(g["n"] for g in h["grupos"])
    assert ns == [1, 2, 3]                                                         # commit (3), tema (2), suelta (1)
    assert [g["frase"] for g in h["grupos"]][0] == "Tarea aislada"                 # el grupo mas reciente, primero
    assert any(g["frase"].endswith("· 3 cambios") for g in h["grupos"])
    assert all("Cerrada antes" not in g["frase"] for g in h["grupos"])


def test_hecho_maximo_6_grupos_y_ver_las_n(cliente, csrf):
    _visita_anterior("2026-10-01 00:00:00")
    hoy = datetime.now().strftime("%Y-%m-%d")
    for i in range(9):
        t = T.anadir(f"Cosa hecha número {i}")
        _cerrar(t["id"], f"{hoy} 10:{i:02d}:00", "se hizo y se comprobó con pruebas")
    r = cliente.get("/centro/hecho").text
    assert r.count('class="hh-grupo"') == 6 and "Ver las 9" in r


def test_hecho_probado_nuevo_para_ti_y_frase_de_quien_cierra(cliente, csrf):
    _visita_anterior()
    hoy = datetime.now().strftime("%Y-%m-%d")
    a = T.anadir("Cerrar una tarea a mano")
    b = T.anadir("Cosa sin pruebas")
    _cerrar(a["id"], f"{hoy} 09:00:00", cierre={"para_damian": "Cerrar una tarea a mano es un solo clic",
                                                   "novedad": True})
    _cerrar(b["id"], f"{hoy} 09:30:00", testeado=False)
    r = cliente.get("/centro/hecho").text
    assert "Cerrar una tarea a mano es un solo clic" in r and "Nuevo para ti" in r
    assert r.count("✓") == 1 and "Probado" in r                                    # solo la probada lleva el ✓


def test_los_extras_del_cierre_sobreviven_a_completar_y_verificar():
    t = T.anadir("Poner la hora de Madrid")
    T.completar(t["id"], despues="nada: no queda nada pendiente de esto",
                cierre={"estado_real": "HECHO Y TESTEADO", "evidencia": "tests/test_hora.py 4 passed en local",
                        "para_damian": "Las IAs saben la fecha y la hora reales", "novedad": True, "otra": "x"})
    c = T.buscar(t["id"])["cierre"]
    assert c["para_damian"] == "Las IAs saben la fecha y la hora reales" and c["novedad"] is True
    assert "otra" not in c and c["estado_real"] in ("HECHO Y TESTEADO", "HECHO SIN TESTEAR")
    # llamadas viejas, sin los campos nuevos, siguen funcionando
    u = T.anadir("Otra sin extras")
    T.completar(u["id"], despues="nada: no queda nada pendiente de esto",
                cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "se hizo a mano y se vio funcionando"})
    assert "para_damian" not in T.buscar(u["id"])["cierre"]


def test_sin_frase_qwen_la_genera_y_se_guarda_sin_pisar_el_detalle(monkeypatch):
    from nucleo import tareas_almacen as AL
    llamadas = []
    monkeypatch.setattr(hecho_llano, "_qwen", lambda p: llamadas.append(p) or "Ahora el cierre de una tarea es un solo clic.")
    t = T.anadir("Cerrar tareas a mano")
    _cerrar(t["id"], "2026-10-18 09:00:00")
    AL.fusionar_detalle(T.ALMACEN, t["id"], conversaciones={"x": 1})
    tarea = T.buscar(t["id"])
    f1 = hecho_llano.frase(tarea)
    assert f1[0] == "Ahora el cierre de una tarea es un solo clic." and f1[2] is True and "Cerrar tareas a mano" in llamadas[0]
    det = AL.leer_detalle(T.ALMACEN, t["id"])
    assert det["frase_damian"] == f1[0] and det["conversaciones"] == {"x": 1}      # guardada, y lo anterior intacto
    f2 = hecho_llano.frase(tarea)
    assert f2[0] == f1[0] and f2[2] is False and len(llamadas) == 1                # la segunda vez, del detalle


def test_sin_qwen_el_titulo_en_llano_cortado_por_palabra(monkeypatch):
    monkeypatch.setattr(hecho_llano, "_qwen", lambda p: "")
    largo = "Para Damian: " + " ".join(["arreglar"] * 3 + ["la sincronización"] * 12) + " (4)"
    t = T.anadir(largo)
    _cerrar(t["id"], "2026-10-18 09:00:00")
    f, _, generada = hecho_llano.frase(T.buscar(t["id"]))
    assert generada is False and len(f) <= hecho_llano.MAX_FRASE and f.endswith("…")
    assert not f.startswith("Para") and f[:-1].split(" ")[-1] in ("arreglar", "la", "sincronización")   # palabra entera
    assert hecho_llano.cortar("una frase corta", 50) == "una frase corta"
    assert hecho_llano.cortar("abcdefghij klmnopqrst", 12) == "abcdefghij…"


def test_qwen_solo_con_el_modelo_pequeno_y_el_contexto_acotado():
    assert hecho_llano.MODELO == "qwen2.5:7b" and hecho_llano.NUM_CTX == 4096 and hecho_llano.NUM_PREDICT == 80


# ------------------------------------------------------------------ Pieza 3: En marcha
def test_los_nombres_de_turno_en_llano_cubren_las_plantillas():
    from nucleo import turnos
    for p in turnos.PLANTILLAS.values():
        assert p["nombre"] in presentar.TURNOS_LLANO, p["nombre"]
    assert presentar.turno_llano("Mi turno raro propio") == "Mi turno raro propio"


# ------------------------------------------------------------------ Pieza 4: Avisos
def test_avisos_solo_los_que_piden_respuesta_agrupados(cliente, csrf):
    assert "Ninguno te pide nada ahora." in cliente.get("/centro/avisos").text
    avisos.emitir("espejo", "Espejo fallido", "x")                                  # informativo: no sale
    avisos.emitir("auditoria", "Delegacion bloqueada", "x")
    assert "Ninguno te pide nada ahora." in cliente.get("/centro/avisos").text
    avisos.emitir("terminos", "OpenAI cambió sus condiciones", "x", ruta="/ajustes", clave="t1")
    avisos.emitir("terminos", "Groq cambió sus condiciones", "x", ruta="/ajustes", clave="t2")
    avisos.emitir("disco_bajo", "Poco espacio libre en disco", "x")
    r = cliente.get("/centro/avisos").text
    assert "Condiciones de un servicio que han cambiado" in r and "· 2" in r and "OpenAI cambió" in r
    assert "Poco espacio en el disco" in r
    assert "Espejo fallido" not in r and "Delegacion bloqueada" not in r and "Ninguno te pide" not in r


def test_un_aviso_viejo_deja_de_salir_y_el_resuelto_no_sale():
    avisos.emitir("terminos", "Condiciones viejas", "x", clave="v1", ahora=(AHORA - timedelta(days=5)).timestamp())
    avisos.emitir("terminos", "Condiciones de hoy", "x", clave="v2", ahora=AHORA.timestamp())
    g = presentar.avisos_pendientes(AHORA)["grupos"]
    assert [a["titulo"] for x in g for a in x["avisos"]] == ["Condiciones de hoy"]


# ------------------------------------------------------------------ Movil
def test_movil_una_columna_y_botones_de_48px(cliente, csrf):
    css = cliente.get("/estatico/nexo.css").text
    assert "@media (max-width: 860px)" in css and "min-height: 48px !important" in css
    assert "@media (min-width: 861px)" in css and "minmax(0, 3fr) minmax(0, 2fr)" in css
    r = cliente.get("/").text
    # el orden del HTML (el de la columna unica del movil): Te toca, Hecho, En marcha, Avisos
    orden = [r.index(x) for x in ('id="col-te-toca"', 'id="col-hecho"', 'id="col-en-marcha"', 'id="col-avisos"')]
    assert orden == sorted(orden)
