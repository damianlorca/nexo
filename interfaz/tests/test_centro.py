# -*- coding: utf-8 -*-
"""Incremento 4: Command Center (estado global, proveedores, tareas por estado, ultimas acciones)."""
from __future__ import annotations

import json
import time

import proveedores
from interfaz import lecturas
from nucleo import enfriamiento, parada, registro, tareas


def _clase(nombre, respuesta, espera=0.0):
    def estado(self):
        time.sleep(espera)
        if isinstance(respuesta, Exception):
            raise respuesta
        return dict(respuesta)
    return type(nombre, (), {"nombre": nombre.lower(), "estado": estado})


def _proveedores(monkeypatch, *clases):
    for c in clases:
        monkeypatch.setattr(proveedores, c.__name__, c, raising=False)
    monkeypatch.setattr(lecturas, "CLASES_PROVEEDORES", tuple(c.__name__ for c in clases))


# ------------------------------------------------------------------ pagina
def test_centro_pinta_los_paneles_con_esqueleto_y_sus_disparadores(cliente, csrf):
    r = cliente.get("/tecnico")
    assert r.status_code == 200
    for url in ("/centro/resumen", "/centro/ias", "/centro/estado", "/centro/tareas", "/centro/proveedores",
                "/centro/auditoria", "/centro/revision", "/centro/acciones/tareas", "/centro/acciones/trazas",
                "/centro/turnos", "/centro/freno", "/centro/tribunal", "/centro/riesgo",
                "/centro/descartadas"):
        assert f'hx-get="{url}"' in r.text
    # T189: + auditoria; T192: + cola de revision; T230: + resumen humano e IAs (los 7 de antes, en "Detalle tecnico");
    # T231: + bloque Turnos; T666: + cola de propuestas (freno F0); T667: + tribunal; T668: + matriz de riesgo;
    # T688: + descartadas
    assert r.text.count('class="esqueleto"') == 14
    assert "nexo:parada from:body" in r.text and "nexo:tareas from:body" in r.text
    assert "nexo:log from:body throttle:3s" in r.text and "nexo:reconciliar from:body" in r.text


def test_paneles_requieren_sesion(cliente):
    for url in ("/centro/estado", "/centro/tareas", "/centro/proveedores",
                "/centro/acciones/tareas", "/centro/acciones/trazas"):
        assert cliente.get(url).status_code == 401


# ------------------------------------------------------------------ estado
def test_estado_activo_y_parado_desde_la_bandera_real(cliente, csrf):
    assert "ACTIVO" in cliente.get("/centro/estado").text
    parada.activar("revision", "damian")
    r = cliente.get("/centro/estado").text
    assert "PARADO" in r and "revision" in r and "Las órdenes están bloqueadas" in r


def test_estado_muestra_cierre_de_turno_pedido(cliente, csrf):
    parada.pedir_cierre("prueba")
    assert "Cierre de turno pedido" in cliente.get("/centro/estado").text


# ------------------------------------------------------------------ tareas
def test_tareas_vacio(cliente, csrf):
    assert "Todavía no hay tareas" in cliente.get("/centro/tareas").text


def test_tareas_cuenta_por_estado_real_y_dependencia(cliente, csrf):
    a = tareas.anadir("una")
    tareas.anadir("dos", depende="damian", etiquetas=["suyo:presencia"])   # guardia de responsables: suya de verdad
    c = tareas.anadir("tres")
    tareas.completar(a["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    tareas.completar(c["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    tareas.verificar(c["id"], "pytest -q -> 3 passed")  # T160: un tick ya no vale
    r = cliente.get("/centro/tareas").text
    assert "PLANIFICADO" in r and "HECHO SIN TESTEAR" in r and "HECHO Y TESTEADO" in r
    assert "tú <strong>1</strong>" in r and "Total: 3." in r


def test_tareas_json_roto_da_panel_de_error_con_reintento(cliente, csrf):
    tareas.ALMACEN.write_text("{roto", encoding="utf-8")
    r = cliente.get("/centro/tareas")
    assert r.status_code == 200
    assert 'role="alert"' in r.text and "Reintentar" in r.text and 'hx-get="/centro/tareas"' in r.text
    assert "roto" not in r.text  # ni el contenido ni la traza


# ------------------------------------------------------------- proveedores
def test_proveedores_salud_disponible_enfriamiento_y_error(cliente, csrf, monkeypatch):
    _proveedores(monkeypatch,
                 _clase("Bueno", {"disponible": True, "motivo": ""}),
                 _clase("Frio", {"disponible": False, "motivo": "En enfriamiento (cuota)"}),
                 _clase("Caido", {"disponible": False, "motivo": "Ollama no responde"}),
                 _clase("Roto", RuntimeError("clave=SECRETA")))
    monkeypatch.setattr(enfriamiento, "enfriado", lambda n: "cuota hasta 12:00: 429" if n == "frio" else None)
    r = cliente.get("/centro/proveedores").text
    assert "bueno" in r and "Disponible" in r
    assert "En enfriamiento" in r and "cuota hasta 12:00" in r
    assert "No disponible" in r and "Ollama no responde" in r
    assert "Error al comprobar" in r and "RuntimeError" in r and "SECRETA" not in r


def test_proveedores_se_comprueban_en_paralelo(cliente, csrf, monkeypatch):
    _proveedores(monkeypatch, *[_clase(f"Lento{i}", {"disponible": True}, espera=0.3) for i in range(6)])
    t0 = time.monotonic()
    assert cliente.get("/centro/proveedores").status_code == 200
    assert time.monotonic() - t0 < 1.2  # en serie serian 1,8 s


def test_proveedores_cacheados_no_se_sondean_en_cada_refresco(cliente, csrf, proveedores_falsos):
    cliente.get("/centro/proveedores")
    cliente.get("/centro/proveedores")
    assert proveedores_falsos.llamadas == 1


# ---------------------------------------------------------------- acciones
def test_acciones_vacias(cliente, csrf):
    assert "Ninguna tarea todavía" in cliente.get("/centro/acciones/tareas").text
    assert "Sin trazas registradas" in cliente.get("/centro/acciones/trazas").text


def test_trazas_solo_con_log_y_tareas_solo_con_tareas(cliente, csrf):
    r = cliente.get("/tecnico").text
    tareas_div = r[r.index('hx-get="/centro/acciones/tareas"'):][:200]
    trazas_div = r[r.index('hx-get="/centro/acciones/trazas"'):][:200]
    assert "nexo:tareas" in tareas_div and "nexo:log" not in tareas_div
    assert "nexo:log" in trazas_div and "nexo:tareas" not in trazas_div


def test_acciones_tareas_y_trazas_mas_recientes_primero(cliente, csrf):
    tareas.anadir("vieja")
    with (registro.CARPETA / "trazas.jsonl").open("w", encoding="utf-8") as f:
        for i in range(15):
            f.write(json.dumps({"t": f"2026-09-24 10:00:{i:02d}", "evento": f"ev{i}", "comando": f"cmd{i}"}) + "\n")
    assert "vieja" in cliente.get("/centro/acciones/tareas").text
    r = cliente.get("/centro/acciones/trazas").text
    assert r.index("ev14") < r.index("ev13") and "ev4" not in r  # solo las 10 ultimas


def test_ultimas_trazas_lee_solo_la_cola_de_un_fichero_grande():
    with (registro.CARPETA / "trazas.jsonl").open("w", encoding="utf-8") as f:
        for i in range(3000):
            f.write(json.dumps({"t": "x", "evento": f"ev{i}", "comando": "y" * 40}) + "\n")
    assert [x["evento"] for x in lecturas.ultimas_trazas(3)] == ["ev2999", "ev2998", "ev2997"]


def test_t667_claude_web_sale_en_la_lista_de_ias_con_su_color(cliente, csrf, monkeypatch):
    import inspect
    import re
    assert re.search(r'CLASES_PROVEEDORES = \([^)]*"ClaudeWebProvider"', inspect.getsource(lecturas))
    _proveedores(monkeypatch, _clase("claude_web", {"disponible": True, "motivo": ""}))
    r = cliente.get("/centro/ias").text
    assert 'data-ia="claude_web"' in r and "bc-marca-claude_web" in r and "Claude web" in r
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "estatico" / "humano.css").read_text(encoding="utf-8")
    assert ".bc-marca-claude_web" in css
