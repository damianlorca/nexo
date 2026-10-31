# -*- coding: utf-8 -*-
"""T667: el tribunal en el Centro: bandeja de Damian (3 lineas + Aprobar / Rechazar / Mandar a Claude), bandeja de
Claude (pendientes + "Copiar orden") y calidad por revisor y por tipo. Todo a tmp_path (conftest de interfaz)."""
from __future__ import annotations

from nucleo import revision, tribunal
from nucleo import tareas as T

DOS = ("### PROPUESTAS IMPLEMENTABLES\n"
       "- QUE: Anadir las reglas al rol de programador | DONDE: roles y prompts | VALOR: 4 | ESFUERZO: 1 | "
       "RIESGO: bajo: solo texto\n"
       "- QUE: Cargar la politica solo en tareas de codigo | DONDE: router | VALOR: 3 | ESFUERZO: 3 | "
       "RIESGO: medio: puede no activarse\n")


def _post(cliente, csrf, url, **datos):
    return cliente.post(url, data=datos, headers={"X-CSRF-Token": csrf})


def _dict(cid, glob, props, res="ADAPTAR"):
    return {"id": cid, "familia": tribunal.CANDIDATOS[cid].familia, "global": glob, "motivo": f"motivo {glob}",
            "propuestas": [[v, "m"] for v in props], "resultado": [res, "encaja bien con NEXO"], "falsos": []}


def en_bandeja(entorno, titulo="Investigar X"):
    o = T.anadir(titulo, etiquetas=["cat:investigacion"])
    nombre = f"{o['id']}_20261003_1200.md"
    (entorno / "memoria" / "borradores" / nombre).write_text(f"<!-- autor groq -->\n## Version final\nInforme.\n{DOS}",
                                                            encoding="utf-8")
    revision.registrar_borrador(o["id"], nombre, auditoria="APROBADA")
    tribunal._sincronizar()
    e = tribunal.expedientes()[nombre]
    ids = [c.id for c in tribunal.TRIBUNAL]
    e["dictamenes"] = {"tribunal": [_dict(ids[0], "APROBAR", ("APROBAR", "RECHAZAR")),
                                    _dict(ids[1], "RECHAZAR", ("RECHAZAR", "RECHAZAR"), "DESCARTAR"),
                                    _dict(ids[2], "APROBAR", ("APROBAR", "RECHAZAR"))],
                       "apelacion": [_dict(ids[3], "DUDA", ("DUDA", "RECHAZAR")),
                                     _dict(ids[4], "APROBAR", ("APROBAR", "RECHAZAR")),
                                     _dict(ids[5], "APROBAR", ("APROBAR", "RECHAZAR"))]}
    e["fase"] = "damian"
    e["lineas"] = tribunal._lineas_damian(e)
    tribunal._guardar_exp(e)
    return o, nombre


def test_centro_carga_el_panel_del_tribunal(cliente, csrf):
    assert 'hx-get="/centro/tribunal"' in cliente.get("/tecnico").text


def test_panel_vacio(cliente, csrf):
    r = cliente.get("/centro/tribunal")
    assert r.status_code == 200 and "Nada esperando tu decisión" in r.text
    assert "Bandeja de Claude" in r.text and "0 / 20" in r.text


def test_bandeja_de_damian_con_tres_lineas_y_tres_botones(cliente, csrf, entorno):
    o, nombre = en_bandeja(entorno)
    r = cliente.get("/centro/tribunal").text
    for linea in tribunal.bandeja_damian()[0]["lineas"]:
        assert linea.split(" · ")[0] in r
    for boton in ("Aprobar", "Rechazar", "Mandar a Claude"):
        assert boton in r
    assert 'name="resultado"' in r and 'value="ADAPTAR" selected' in r      # investigacion: RESULTADO elegible


def test_damian_aprueba_desde_la_web(cliente, csrf, entorno):
    o, nombre = en_bandeja(entorno)
    r = _post(cliente, csrf, "/tribunal/decidir", nombre=nombre, accion="aprobar", resultado="ADOPTAR")
    assert r.status_code == 200 and "Aprobado" in r.text
    assert tribunal.expedientes()[nombre]["quien"] == "damian"
    assert T.buscar(o["id"])["resultado"]["decision"] == "ADOPTAR"


def test_mandar_a_claude_y_bandeja_llena(cliente, csrf, entorno, monkeypatch):
    monkeypatch.setattr(tribunal, "MAX_BANDEJA_CLAUDE", 1)
    o, nombre = en_bandeja(entorno)
    o2, n2 = en_bandeja(entorno, "Investigar Y")
    assert "a Claude" in _post(cliente, csrf, "/tribunal/decidir", nombre=nombre, accion="claude").text
    r = _post(cliente, csrf, "/tribunal/decidir", nombre=n2, accion="claude")
    assert "llena" in r.text and tribunal.expedientes()[n2]["fase"] == "damian"
    assert "1 / 1" in cliente.get("/centro/tribunal").text


def test_copiar_orden_lleva_el_texto_fijo(cliente, csrf):
    r = cliente.get("/centro/tribunal").text
    assert "Copiar orden" in r and "data-copiar" in r and "nucleo.tribunal bandeja_claude" in r


def test_decidir_sin_csrf_se_rechaza(cliente, csrf, entorno):
    o, nombre = en_bandeja(entorno)
    assert cliente.post("/tribunal/decidir", data={"nombre": nombre, "accion": "aprobar"}).status_code == 403
    assert tribunal.expedientes()[nombre]["fase"] == "damian"


# ------------------------------------------------------------------ indicador fijo de la bandeja de Claude (04/10)
def _con_pendientes(monkeypatch, n):
    monkeypatch.setattr(tribunal, "bandeja_claude", lambda: {"casos": [], "pendientes": n, "maximo": 20,
                                                              "llena": False, "en_espera": 0})


def test_indicador_encendido_con_el_numero_y_la_orden_para_copiar(cliente, csrf, monkeypatch):
    _con_pendientes(monkeypatch, 3)
    r = cliente.get("/centro/claude")
    assert r.status_code == 200
    t = r.text
    assert "claude-encendido" in t and 'class="claude-numero">3<' in t and ">Claude<" in t
    assert 'data-copiar="#orden-claude-rapida"' in t and 'data-copiado="Copiado"' in t and "data-copiar-estado" in t
    assert "3 casos en la bandeja" in t and "disabled" not in t.split("<textarea")[0]
    orden = t.split('id="orden-claude-rapida"')[1].split("</textarea>")[0]
    assert "nucleo.tribunal bandeja_claude" in orden            # la orden entera de CLAUDE_BANDEJA.md
    assert "claude-logo" not in t and "anthropic" not in t.lower()   # icono propio, sin el logo oficial


def test_indicador_apagado_y_gris_sin_trabajo(cliente, csrf, monkeypatch):
    _con_pendientes(monkeypatch, 0)
    t = cliente.get("/centro/claude").text
    assert "claude-apagado" in t and "claude-encendido" not in t and "claude-numero" not in t
    assert "disabled" in t and "bandeja vacía" in t


def test_indicador_singular_con_un_caso(cliente, csrf, monkeypatch):
    _con_pendientes(monkeypatch, 1)
    assert "1 caso en la bandeja" in cliente.get("/centro/claude").text


def test_el_centro_carga_el_indicador_y_se_refresca_solo(cliente, csrf):
    t = cliente.get("/tecnico").text
    assert 'hx-get="/centro/claude"' in t and "every 30s" in t


def test_el_indicador_cuenta_los_casos_reales_de_la_bandeja(cliente, csrf, entorno):
    o, nombre = en_bandeja(entorno)          # fase damian: aun no es de Claude
    assert "claude-apagado" in cliente.get("/centro/claude").text
    tribunal.decidir_damian(nombre, "claude")
    t = cliente.get("/centro/claude").text
    assert "claude-encendido" in t and 'class="claude-numero">1<' in t


def test_el_js_copia_con_su_propio_texto_y_el_css_tiene_los_dos_estados():
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent / "estatico"
    js, css = (raiz / "nexo.js").read_text(encoding="utf-8"), (raiz / "nexo.css").read_text(encoding="utf-8")
    assert 'data-copiado' in js and "navigator.clipboard" in js and "execCommand" in js   # y plan B sin portapapeles
    assert ".claude-encendido" in css and ".claude-apagado" in css and "env(safe-area-inset-bottom" in css
    assert "min-height: 48px" in css                                                      # tactil en el movil
