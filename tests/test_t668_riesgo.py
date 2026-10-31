# -*- coding: utf-8 -*-
"""T668 (F2 de la epica T664): matriz de riesgo fija y su enlace con la cola de aprobaciones N04.

El nivel lo calcula codigo fijo (rutas, diff, etiquetas); ninguna etiqueta lo baja. R1 = veto de Damian 8 h ANTES
de implementar (silencio = si); R2 = OK de Damian DESPUES de implementar, atado al diff real (7 dias, silencio = no,
como mucho 10 abiertas); R3 = nunca el implementador. Todo en tmp_path: nunca memoria/ real."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from nucleo import aprobaciones as ap
from nucleo import avisos, riesgo

T0 = datetime(2026, 10, 4, 10, 0, 0)


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "ALMACEN", tmp_path / "aprobaciones.json")
    monkeypatch.setattr(riesgo, "TRIBUNAL_R1", False)   # T967: estas pruebas son del veto sin tribunal
    monkeypatch.setattr(ap, "HISTORIAL", tmp_path / "aprobaciones_historial.jsonl")
    monkeypatch.setattr(ap, "CANDADO", tmp_path / ".candado.lock")
    monkeypatch.setattr(avisos, "CARPETA", tmp_path / "avisos")
    return tmp_path


def tarea(id_="T900", titulo="Aclarar el README", donde="documentacion", etiquetas=()):
    return {"id": id_, "titulo": titulo, "detalle": f"QUE: {titulo}\nDONDE: {donde}\nVALOR: 3 · ESFUERZO: 1",
            "etiquetas": list(etiquetas)}


def diff_de(ruta, lineas=("+hola",), nuevo=False, borrado=False):
    cab = [f"diff --git a/{ruta} b/{ruta}"]
    if nuevo:
        cab.append("new file mode 100644")
    if borrado:
        cab.append("deleted file mode 100644")
    cab += [f"--- a/{ruta}", f"+++ b/{ruta}", "@@ -1,1 +1,2 @@"]
    return "\n".join(cab + list(lineas)) + "\n"


# ------------------------------------------------------------ rutas

@pytest.mark.parametrize("ruta,nivel", [
    ("documentacion/PLAN.md", "R0"),
    ("README.md", "R0"),
    ("interfaz/HITO_MOVIL.md", "R0"),
    ("tests/test_x.py", "R1"),
    ("interfaz/tests/test_y.py", "R1"),
    ("interfaz/plantillas/centro.html", "R1"),
    ("interfaz/estatico/estilo.css", "R1"),
    ("roles/programador.md", "R1"),
    ("roles/programador.txt", "R1"),
    ("documentacion/prompts/CLAUDE_BANDEJA.md", "R3"),   # 11/10: orden de Claude = control
    ("herramientas_nube/_algo.py", "R1"),
    ("nucleo/tareas.py", "R2"),
    ("proveedores.py", "R2"),
    ("router.py", "R2"),
    ("canal/bot.py", "R2"),
    ("memoria/tareas.json", "R2"),
    ("interfaz/rutas/centro.py", "R2"),
    ("algo/desconocido.py", "R2"),
    ("requirements.txt", "R2"),
    ("interfaz/estatico/vendor/htmx.min.js", "R2"),
    ("nucleo/permisos.py", "R3"),
    ("nucleo/instancia.py", "R3"),
    ("nucleo/config.py", "R3"),
    ("manos/shell.py", "R3"),
    ("secretos.toml", "R3"),
    ("canal/secretos.toml", "R3"),
    (".env", "R3"),
    (".claude/settings.json", "R3"),
    ("CLAUDE.md", "R3"),
])
def test_nivel_por_ruta(ruta, nivel):
    assert riesgo.calcular(rutas=[ruta])["nivel"] == nivel


def test_manda_la_ruta_mas_alta_y_dice_por_que():
    r = riesgo.calcular(rutas=["documentacion/a.md", "tests/test_a.py", "nucleo/tareas.py"])
    assert r["nivel"] == "R2"
    assert any("nucleo/tareas.py" in m for m in r["motivos"])


def test_sin_rutas_ni_diff_es_r2():
    assert riesgo.calcular()["nivel"] == "R2"


# ------------------------------------------------------------ diff

def test_dependencia_nueva_es_r2_como_minimo():
    r = riesgo.calcular(diff=diff_de("requirements.txt", ["+httpx==0.28.1"]))
    assert r["nivel"] == "R2" and any("dependencia" in m for m in r["motivos"])
    assert riesgo.calcular(diff=diff_de("package.json", ['+  "x": "1.0"']))["nivel"] == "R2"
    assert riesgo.calcular(diff=diff_de("interfaz/estatico/vendor/x.js", nuevo=True))["nivel"] == "R2"


def test_import_de_terceros_nuevo_es_dependencia(monkeypatch):
    monkeypatch.setattr(riesgo, "_requisitos", lambda: {"httpx", "pytest"})
    assert riesgo.calcular(diff=diff_de("tests/test_a.py", ["+import requests"]))["nivel"] == "R2"
    assert riesgo.calcular(diff=diff_de("tests/test_a.py", ["+from yaml import safe_load"]))["nivel"] == "R2"
    # biblioteca estandar, paquetes del repo y lo que ya esta en requirements: nada nuevo
    for linea in ("+import json", "+from pathlib import Path", "+from nucleo import tareas", "+import httpx",
                  "+    from interfaz import push", "+import pytest"):
        assert riesgo.calcular(diff=diff_de("tests/test_a.py", [linea]))["nivel"] == "R1", linea


def test_borrar_un_archivo_es_r3_y_archivar_no():
    assert riesgo.calcular(diff=diff_de("documentacion/viejo.md", ["-x"], borrado=True))["nivel"] == "R3"
    archivar = ("diff --git a/documentacion/viejo.md b/_archivo/20261004/viejo.md\n"
                "similarity index 100%\nrename from documentacion/viejo.md\nrename to _archivo/20261004/viejo.md\n")
    r = riesgo.calcular(diff=archivar)
    assert r["nivel"] == "R0", r


@pytest.mark.parametrize("linea", [
    '+API_KEY = "nvapi-AbCdEf0123456789AbCdEf0123456789"',
    '+token = "ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"',
    '+clave = "sk-FALSOXXXXXXXXXXXXXXXXXXXX"',
    '+    "-----BEGIN ' + 'PRIVATE KEY-----"',   # partido: publicar_nube.py aborta si ve la cabecera entera
    '+lee(RAIZ / "secretos.toml")',
])
def test_secretos_en_el_diff_son_r3(linea):
    r = riesgo.calcular(diff=diff_de("tests/test_a.py", [linea]))
    assert r["nivel"] == "R3" and any("secreto" in m for m in r["motivos"])


def test_red_nueva_en_codigo_es_r3_y_en_documentacion_no():
    r = riesgo.calcular(diff=diff_de("herramientas_nube/x.py", ['+URL = "https://evil.example.com/api"']))
    assert r["nivel"] == "R3" and any("red" in m for m in r["motivos"])
    # host de la lista blanca: no es red nueva
    ok = diff_de("herramientas_nube/x.py", ['+URL = "https://api.groq.com/openai/v1"'])
    assert riesgo.calcular(diff=ok)["nivel"] == "R1"
    # un enlace en un .md es documentacion, no una conexion
    assert riesgo.calcular(diff=diff_de("documentacion/a.md", ["+Ver https://evil.example.com"]))["nivel"] == "R0"


def test_dinero_en_codigo_es_r3():
    r = riesgo.calcular(diff=diff_de("herramientas_nube/x.py", ["+stripe.Charge.create(amount=500)"]))
    assert r["nivel"] == "R3"


def test_r0_r1_de_mas_de_300_lineas_sube_a_r2():
    grande = diff_de("documentacion/a.md", [f"+linea {i}" for i in range(301)])
    r = riesgo.calcular(diff=grande)
    assert r["nivel"] == "R2" and any("300" in m for m in r["motivos"])
    assert riesgo.calcular(diff=diff_de("documentacion/a.md", [f"+l{i}" for i in range(300)]))["nivel"] == "R0"


def test_el_diff_se_lee_con_sus_rutas():
    d = diff_de("documentacion/a.md") + diff_de("nucleo/permisos.py", ["+x = 1"])
    assert riesgo.rutas_de_diff(d) == ["documentacion/a.md", "nucleo/permisos.py"]
    assert riesgo.calcular(diff=d)["nivel"] == "R3"


# ------------------------------------------------------------ etiquetas

def test_etiqueta_sube_nunca_baja():
    assert riesgo.calcular(rutas=["documentacion/a.md"], etiquetas=["riesgo:R3"])["nivel"] == "R3"
    assert riesgo.calcular(rutas=["documentacion/a.md"], etiquetas=["riesgo:R1"])["nivel"] == "R1"
    assert riesgo.calcular(rutas=["nucleo/tareas.py"], etiquetas=["riesgo:R0"])["nivel"] == "R2"
    assert riesgo.calcular(rutas=["manos/x.py"], etiquetas=["riesgo:R1"])["nivel"] == "R3"


# ------------------------------------------------------------ nivel previsto (antes de implementar)

@pytest.mark.parametrize("t,nivel", [
    (tarea(donde="documentacion"), "R0"),
    (tarea(donde="documentación"), "R0"),
    (tarea(titulo="Incorporar al modelo de permisos del README la excepcion", donde="seguridad y permisos"), "R0"),
    (tarea(titulo="Fijar modelos gratuitos", donde="router de modelos"), "R2"),
    (tarea(titulo="Validar claves", donde="memoria y cola de tareas"), "R2"),
    (tarea(titulo="Algo", donde="NvidiaProvider.enviar()"), "R2"),
    (tarea(titulo="Algo", donde="nucleo/tareas.py"), "R2"),
    (tarea(titulo="Arreglar", donde="manos/shell.py"), "R3"),
    (tarea(titulo="Tests de la cola", donde="tests/test_cola.py"), "R1"),
    (tarea(titulo="Algo raro", donde="por ahi"), "R2"),
    (tarea(donde="documentacion", etiquetas=["riesgo:R3"]), "R3"),
])
def test_nivel_previsto_de_una_tarea(t, nivel):
    assert riesgo.previsto(t)["nivel"] == nivel


# ------------------------------------------------------------ autorizacion antes de implementar

def test_r0_se_implementa_sin_preguntar():
    a = riesgo.autorizacion(tarea(), ahora=T0)
    assert a["puede"] and a["nivel"] == "R0"
    assert ap.cargar()["solicitudes"] == []


def test_r1_pide_veto_con_push_y_espera_8_horas():
    t = tarea(titulo="Test de la cola", donde="tests/test_cola.py")
    a = riesgo.autorizacion(t, ahora=T0)
    assert not a["puede"] and a["nivel"] == "R1" and "veto" in a["motivo"]
    s = ap.ver(a["solicitud"])
    assert s["nivel"] == "R1" and s["tipo"] == "veto" and s["vence"] == "2026-10-04 18:00:00"
    aviso = avisos.recientes(5)[0]
    assert "Se implementará T900 en 8 h salvo que digas NO" in aviso["titulo"]
    # pedir otra vez no duplica ni re-avisa
    b = riesgo.autorizacion(t, ahora=T0 + timedelta(hours=1))
    assert b["solicitud"] == a["solicitud"] and not b["puede"]
    assert len(ap.cargar()["solicitudes"]) == 1


def test_r1_silencio_8_horas_es_si():
    t = tarea(titulo="Test de la cola", donde="tests/test_cola.py")
    a = riesgo.autorizacion(t, ahora=T0)
    b = riesgo.autorizacion(t, ahora=T0 + timedelta(hours=8, seconds=1))
    assert b["puede"] and b["solicitud"] == a["solicitud"]
    s = ap.ver(a["solicitud"])
    assert s["estado"] == "aprobada"
    assert [e["tipo"] for e in s["eventos"]] == ["alta", "aprobada_por_silencio"]
    ok, _ = ap.verificar_historial()
    assert ok


def test_r1_vetado_no_se_implementa():
    t = tarea(titulo="Test de la cola", donde="tests/test_cola.py")
    a = riesgo.autorizacion(t, ahora=T0)
    ap.denegar(a["solicitud"], quien="damian", motivo="NO", ahora=T0 + timedelta(hours=2))
    b = riesgo.autorizacion(t, ahora=T0 + timedelta(hours=30))
    assert not b["puede"] and "vetad" in b["motivo"]


def test_r2_se_implementa_y_el_ok_se_pide_despues():
    t = tarea(titulo="Validar claves", donde="nucleo/tareas.py")
    a = riesgo.autorizacion(t, ahora=T0)
    assert a["puede"] and a["nivel"] == "R2" and "despues" in a["motivo"]
    assert ap.cargar()["solicitudes"] == []


def test_r3_nunca_lo_implementa_el_implementador():
    a = riesgo.autorizacion(tarea(donde="manos/shell.py"), ahora=T0)
    assert not a["puede"] and a["nivel"] == "R3" and a["destino"] == "claude"


# ------------------------------------------------------------ fusion (despues, sobre el diff real)

def test_r0_real_fusiona_sin_preguntar():
    f = riesgo.fusion(tarea(), diff_de("documentacion/a.md"), "R0", ahora=T0)
    assert f["puede"] and f["nivel_real"] == "R0"


def test_r2_pide_ok_atado_al_diff_y_caduca_a_los_7_dias():
    t = tarea(titulo="Validar claves", donde="nucleo/tareas.py")
    d = diff_de("nucleo/tareas.py", ["+x = 1"])
    f = riesgo.fusion(t, d, "R2", resumen="Valida las claves antes de etiquetar.", ahora=T0)
    assert not f["puede"] and f["nivel_real"] == "R2"
    s = ap.ver(f["solicitud"])
    assert s["nivel"] == "R2" and s["vence"] == "2026-10-11 10:00:00"
    assert s["extra"]["resumen"] == "Valida las claves antes de etiquetar."
    assert "nucleo/tareas.py" in s["extra"]["diff_resumido"]
    # Damian dice que si: ahora se puede, y la aprobacion vale solo para ESTE diff
    ap.aprobar(f["solicitud"], ahora=T0 + timedelta(hours=1))
    g = riesgo.fusion(t, d, "R2", ahora=T0 + timedelta(hours=5))
    assert g["puede"] and g["solicitud"] == f["solicitud"]
    otro = riesgo.fusion(t, diff_de("nucleo/tareas.py", ["+x = 2"]), "R2", ahora=T0 + timedelta(hours=5))
    assert not otro["puede"] and otro["solicitud"] != f["solicitud"]
    with pytest.raises(ap.NoCoincide):
        ap.consumir(f["solicitud"], s["accion"], s["detalle"] + "x", ahora=T0 + timedelta(hours=6))


def test_r2_sin_respuesta_en_7_dias_es_no():
    t = tarea(titulo="Validar claves", donde="nucleo/tareas.py")
    d = diff_de("nucleo/tareas.py", ["+x = 1"])
    f = riesgo.fusion(t, d, "R2", ahora=T0)
    g = riesgo.fusion(t, d, "R2", ahora=T0 + timedelta(days=7, seconds=1))
    assert not g["puede"] and "caduc" in g["motivo"]
    assert ap.ver(f["solicitud"])["estado"] == "caducada"


def test_si_el_diff_real_sube_de_nivel_se_pide_ok():
    # aprobada como R0 (documentacion) pero el diff toca el nucleo: no fusiona sin OK
    f = riesgo.fusion(tarea(), diff_de("nucleo/tareas.py", ["+x = 1"]), "R0", ahora=T0)
    assert not f["puede"] and f["nivel_real"] == "R2" and f["solicitud"]
    # R1 aprobado y diff R1: fusiona
    assert riesgo.fusion(tarea(), diff_de("tests/test_a.py"), "R1", ahora=T0)["puede"]
    # R0 aprobado y diff R1 (no hubo veto previo): tambien pide OK
    g = riesgo.fusion(tarea(), diff_de("tests/test_a.py"), "R0", ahora=T0)
    assert not g["puede"] and g["solicitud"]


def test_diff_r3_no_se_fusiona_nunca():
    f = riesgo.fusion(tarea(), diff_de("manos/shell.py", ["+x = 1"]), "R2", ahora=T0)
    assert not f["puede"] and f["nivel_real"] == "R3" and f["destino"] == "claude"
    assert ap.cargar()["solicitudes"] == []


def test_como_mucho_10_r2_pendientes():
    for i in range(10):
        f = riesgo.fusion(tarea(id_=f"T{900 + i}"), diff_de("nucleo/tareas.py", [f"+x = {i}"]), "R2", ahora=T0)
        assert f["solicitud"]
    assert riesgo.r2_pendientes(ahora=T0) == 10 and riesgo.cupo_r2_lleno(ahora=T0)
    # la 11: ni se pide ni se implementa otra R2
    f = riesgo.fusion(tarea(id_="T950"), diff_de("nucleo/tareas.py", ["+y = 1"]), "R2", ahora=T0)
    assert not f["puede"] and not f["solicitud"] and "10" in f["motivo"]
    a = riesgo.autorizacion(tarea(id_="T951", donde="nucleo/tareas.py"), ahora=T0)
    assert not a["puede"] and "10" in a["motivo"]
    # una R0 sigue su camino
    assert riesgo.autorizacion(tarea(id_="T952"), ahora=T0)["puede"]
    # al decidir una, vuelve a haber hueco
    ap.denegar(ap.pendientes(ahora=T0, incluir_matriz=True)[0]["id"], ahora=T0)
    assert not riesgo.cupo_r2_lleno(ahora=T0)


# ------------------------------------------------------------ la cola N04 de siempre no cambia

def test_el_bot_no_ve_r1_ni_r2_y_lo_ambar_sigue_igual():
    riesgo.autorizacion(tarea(titulo="Test", donde="tests/test_a.py"), ahora=T0)
    riesgo.fusion(tarea(id_="T901"), diff_de("nucleo/tareas.py"), "R2", ahora=T0)
    s = ap.solicitar("ejecutar comando", "winget --version", origen="mcp", ahora=T0)
    assert [x["id"] for x in ap.pendientes(ahora=T0)] == [s["id"]]
    assert len(ap.pendientes(ahora=T0, incluir_matriz=True)) == 3
    # lo ambar: el silencio sigue siendo NO
    ap.caducar(ahora=T0 + timedelta(hours=25))
    assert ap.ver(s["id"])["estado"] == "caducada"


def test_resumen_para_el_centro():
    riesgo.autorizacion(tarea(titulo="Test", donde="tests/test_a.py"), ahora=T0)
    riesgo.fusion(tarea(id_="T901"), diff_de("nucleo/tareas.py"), "R2", resumen="Hace X.", ahora=T0)
    m = riesgo.bandeja(ahora=T0)
    assert [x["tarea"] for x in m["r1"]] == ["T900"] and [x["tarea"] for x in m["r2"]] == ["T901"]
    assert m["r2_max"] == 10 and m["r2_lleno"] is False
    assert m["r1"][0]["vence"] == "2026-10-04 18:00:00"


@pytest.mark.parametrize("ruta", ["nucleo/riesgo.py", "nucleo/puerta.py", "nucleo/implementador.py",
                                  "nucleo/piloto_serie.py", "nucleo/aprobaciones.py", "nucleo/parada.py",
                                  "tests_dados/test_t746_x.py", "documentacion/prompts/CLAUDE_BANDEJA.md",
                                  "./nucleo/puerta.py"])
def test_controles_del_implementador_son_r3(ruta):
    """11/10: el implementador nunca toca lo que lo controla (antes era R2 y un OK de Damian podia fusionarlo)."""
    nivel, motivo = riesgo.nivel_ruta(ruta)
    assert nivel == "R3" and "control del implementador" in motivo


def test_el_resto_del_nucleo_sigue_r2():
    assert riesgo.nivel_ruta("nucleo/freno.py")[0] == "R2"
    assert riesgo.nivel_ruta("tests/test_t746_x.py")[0] == "R1"


# ------------------------------------------------------------ R2 sin cuello de botella (Damian 13/10)
def _pieza(etiquetas=("tests:dados",)):
    return tarea(titulo="Detector de acciones", donde="nucleo/orden_accion.py", etiquetas=etiquetas)


def test_pieza_con_tests_dados_y_puerta_verde_va_por_veto_r1_y_se_fusiona_sola_a_las_8h():
    d = diff_de("nucleo/orden_accion.py", ["+def detectar(t):", "+    return None"], nuevo=True)
    f = riesgo.fusion(_pieza(), d, "R2", resumen="Detecta acciones.", ahora=T0, puerta_ok=True)
    assert not f["puede"] and f["nivel_real"] == "R1" and "salvo veto" in f["motivo"]
    s = ap.ver(f["solicitud"])
    assert s["nivel"] == "R1" and s["tipo"] == "veto" and s["extra"]["fusion"] is True
    assert riesgo.bandeja(ahora=T0)["r1"][0]["fusion"] is True and riesgo.bandeja(ahora=T0)["r2"] == []
    assert not riesgo.fusion(_pieza(), d, "R2", ahora=T0 + timedelta(hours=7), puerta_ok=True)["puede"]
    g = riesgo.fusion(_pieza(), d, "R2", ahora=T0 + timedelta(hours=8, seconds=1), puerta_ok=True)
    assert g["puede"] and g["solicitud"] == f["solicitud"]


def test_un_ok_r2_ya_dado_a_ese_diff_vale_sin_esperar_el_veto():
    """12/10: A0034/A0035 (OK R2 de Damian) quedaron debajo de un veto R1 nuevo de 8 h al llegar la via R1."""
    d = diff_de("nucleo/orden_accion.py", ["+def detectar(t):", "+    return None"], nuevo=True)
    f = riesgo.fusion(_pieza(), d, "R2", ahora=T0)                      # antes: sin puerta_ok -> pide OK R2
    ap.aprobar(f["solicitud"], ahora=T0 + timedelta(hours=1))
    g = riesgo.fusion(_pieza(), d, "R2", ahora=T0 + timedelta(hours=2), puerta_ok=True)
    assert g["puede"] and g["solicitud"] == f["solicitud"] and g["motivo"] == "OK de Damian para este diff"
    assert riesgo.bandeja(ahora=T0 + timedelta(hours=2))["r1"] == []    # no se abre veto encima
    otro = diff_de("nucleo/orden_accion.py", ["+def detectar(t):", "+    return 1"], nuevo=True)
    h = riesgo.fusion(_pieza(), otro, "R2", ahora=T0 + timedelta(hours=2), puerta_ok=True)
    assert not h["puede"] and "salvo veto" in h["motivo"]                # otro diff: su propio veto


def test_el_veto_de_damian_la_para():
    d = diff_de("nucleo/orden_accion.py", ["+x = 1"])
    f = riesgo.fusion(_pieza(), d, "R2", ahora=T0, puerta_ok=True)
    ap.denegar(f["solicitud"], ahora=T0 + timedelta(hours=1))
    g = riesgo.fusion(_pieza(), d, "R2", ahora=T0 + timedelta(days=2), puerta_ok=True)
    assert not g["puede"] and "vetada" in g["motivo"]


@pytest.mark.parametrize("pieza,d,motivo", [
    (_pieza(()), diff_de("nucleo/orden_accion.py", ["+x = 1"]), "sin tests dados"),
    (_pieza(), diff_de("nucleo/permisos_canal.py", ["+x = 1"]), "sensibles"),
    (_pieza(), diff_de("nucleo/guardia_disco.py", ["+x = 1"]), "sensibles"),
    (_pieza(), diff_de("interfaz/sesion_web.py", ["+x = 1"]), "sensibles"),
    (_pieza(), diff_de("nucleo/orden_accion.py", ["+import paquete_raro_xyz"]), "dependencia"),
    (_pieza(), diff_de("memoria/x.json", ["+{}"]), "memoria"),
    (_pieza(), diff_de("nucleo/orden_accion.py", ["+x = 1"] * 301), "lineas"),
])
def test_sigue_en_r2_si_no_es_una_pieza_limpia(pieza, d, motivo):
    assert motivo in riesgo.r1_por_tests_dados(pieza, d)
    f = riesgo.fusion(pieza, d, "R2", ahora=T0, puerta_ok=True)
    assert f["nivel_real"] == "R2" and ap.ver(f["solicitud"])["nivel"] == "R2"


def test_sin_la_puerta_no_hay_veto():
    f = riesgo.fusion(_pieza(), diff_de("nucleo/orden_accion.py", ["+x = 1"]), "R2", ahora=T0)
    assert f["nivel_real"] == "R2" and ap.ver(f["solicitud"])["nivel"] == "R2"


@pytest.mark.parametrize("ruta", ["nucleo/permisos.py", "manos/shell.py", ".claude/settings.json",
                                  "nucleo/puerta.py", "secretos.toml"])
def test_lo_r3_nunca_baja(ruta):
    f = riesgo.fusion(_pieza(), diff_de(ruta, ["+x = 1"]), "R2", ahora=T0, puerta_ok=True)
    assert f["nivel_real"] == "R3" and f["destino"] == "claude"
