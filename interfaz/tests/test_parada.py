# -*- coding: utf-8 -*-
"""Incremento 2: PARADA de emergencia (POST, doble confirmacion, estado real, web viva con PARADA)."""
from __future__ import annotations

import json

from nucleo import parada


def _parar(cliente, csrf, motivo="prueba", confirmacion="si"):
    return cliente.post("/parada", data={"confirmacion": confirmacion, "motivo": motivo},
                        headers={"X-CSRF-Token": csrf})


def _seguir(cliente, csrf, confirmacion="si"):
    return cliente.post("/seguir", data={"confirmacion": confirmacion}, headers={"X-CSRF-Token": csrf})


def test_boton_parada_visible_en_todas_las_pantallas(cliente, csrf):
    for ruta in ("/", "/no-existe"):
        r = cliente.get(ruta)
        assert 'id="parada"' in r.text and "PARADA" in r.text and "Activo" in r.text


def test_parar_activa_la_bandera_real_con_quien_damian(cliente, csrf, bandera):
    r = _parar(cliente, csrf, motivo="me voy a dormir")
    assert r.status_code == 200
    datos = json.loads(bandera.read_text(encoding="utf-8"))
    assert datos["motivo"] == "me voy a dormir" and datos["quien"] == "damian"
    # La respuesta sale de la bandera releida: boton Seguir, banner OOB y aviso accesible.
    assert "Seguir" in r.text and "PARADO" in r.text
    assert 'id="banner-parada" hx-swap-oob="true"' in r.text and "me voy a dormir" in r.text
    assert 'hx-swap-oob="innerHTML:#avisos"' in r.text and "NEXO parado." in r.text


def test_parar_sin_confirmacion_no_hace_nada(cliente, csrf, bandera):
    assert _parar(cliente, csrf, confirmacion="").status_code == 400
    assert _parar(cliente, csrf, confirmacion="no").status_code == 400
    assert not bandera.exists()


def test_parar_sin_csrf_no_hace_nada(cliente, csrf, bandera):
    r = cliente.post("/parada", data={"confirmacion": "si", "motivo": "x"})
    assert r.status_code == 403
    assert not bandera.exists()


def test_seguir_sin_csrf_ni_confirmacion_no_hace_nada(cliente, csrf, bandera):
    parada.activar("externa", "telegram")
    assert cliente.post("/seguir", data={"confirmacion": "si"}).status_code == 403
    assert _seguir(cliente, csrf, confirmacion="").status_code == 400
    assert bandera.exists()


def test_con_parada_la_web_sigue_viva_y_navegable(cliente, csrf):
    _parar(cliente, csrf, motivo="prueba web viva")
    r = cliente.get("/")
    assert r.status_code == 200
    assert "NEXO está PARADO" in r.text and "prueba web viva" in r.text
    assert cliente.get("/no-existe").status_code == 404
    assert cliente.get("/parada/estado").status_code == 200
    assert cliente.get("/salud").status_code == 200


def test_seguir_quita_la_bandera(cliente, csrf, bandera):
    _parar(cliente, csrf)
    r = _seguir(cliente, csrf)
    assert r.status_code == 200 and not bandera.exists()
    assert "Activo" in r.text and "NEXO reanudado." in r.text
    assert "NEXO está PARADO" not in r.text


def test_seguir_funciona_con_parada_puesta_desde_fuera(cliente, csrf, bandera):
    # Parada creada por Telegram / a mano, no por la web.
    parada.activar("desde telegram", "telegram")
    r = _seguir(cliente, csrf)
    assert r.status_code == 200 and not bandera.exists()


def test_seguir_sin_parada_activa_lo_dice(cliente, csrf):
    r = _seguir(cliente, csrf)
    assert r.status_code == 200 and "No había PARADA activa." in r.text


def test_estado_refleja_la_bandera_real_sin_cache(cliente, csrf, bandera):
    assert "Activo" in cliente.get("/parada/estado").text
    bandera.write_text(json.dumps({"motivo": "puesta a mano", "quien": "damian", "cuando": "hoy"}), encoding="utf-8")
    assert "PARADO" in cliente.get("/parada/estado").text
    assert "puesta a mano" in cliente.get("/").text
    bandera.unlink()
    assert "Activo" in cliente.get("/parada/estado").text


def test_bandera_ilegible_cuenta_como_parada(cliente, csrf, bandera):
    bandera.write_text("{roto", encoding="utf-8")
    r = cliente.get("/")
    assert "NEXO está PARADO" in r.text and "bandera ilegible" in r.text


def test_motivo_se_escapa_y_se_recorta(cliente, csrf, bandera):
    r = _parar(cliente, csrf, motivo="<script>alert(1)</script>" + "x" * 500)
    assert "<script>alert(1)" not in r.text and "&lt;script&gt;" in r.text
    assert len(json.loads(bandera.read_text(encoding="utf-8"))["motivo"]) == 300


def test_fallo_del_core_se_muestra_y_pinta_estado_real(cliente, csrf, bandera, monkeypatch):
    def rompe(*a, **k):
        raise OSError("disco lleno")
    monkeypatch.setattr(parada, "activar", rompe)
    r = _parar(cliente, csrf)
    assert r.status_code == 200
    assert "No se pudo activar la PARADA: disco lleno" in r.text and 'role="alert"' in r.text
    # Nada de optimistic update: sigue pintando "Activo" porque la bandera no existe.
    assert "Activo" in r.text and not bandera.exists()


def test_parar_con_parada_ya_activa_no_pisa_la_original(cliente, csrf, bandera):
    parada.activar("fallo Gemini", "telegram")
    original = bandera.read_text(encoding="utf-8")
    r = _parar(cliente, csrf, motivo="otra")
    assert r.status_code == 200 and "ya estaba parado (fallo Gemini)" in r.text
    assert bandera.read_text(encoding="utf-8") == original


def test_get_a_una_accion_da_405_explicado(cliente, csrf):
    r = cliente.get("/parada")
    assert r.status_code == 405 and "es una acción" in r.text and "ha fallado en el servidor" not in r.text


# ------------------------------------------------ movil (28/09: la PARADA no se podia confirmar)
MOVIL_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/129.0 Mobile Safari/537.36"


def test_motivo_vacio_desde_el_movil(cliente, csrf, bandera):
    r = cliente.post("/parada", data={"confirmacion": "si", "motivo": "  "},
                     headers={"X-CSRF-Token": csrf, "User-Agent": MOVIL_UA})
    assert r.status_code == 200
    assert json.loads(bandera.read_text(encoding="utf-8"))["motivo"] == "desde el móvil"


def test_motivo_vacio_desde_el_pc(cliente, csrf, bandera):
    _parar(cliente, csrf, motivo="")
    assert json.loads(bandera.read_text(encoding="utf-8"))["motivo"] == "desde la web"


def test_confirmar_va_antes_que_el_motivo_y_se_enfoca(cliente, csrf):
    html = cliente.get("/").text
    form = html[html.index('id="confirmar-parada"'):]
    form = form[:form.index("</form>")]
    assert form.index("Sí, parar NEXO") < form.index('id="motivo-parada"')
    boton = form[:form.index("Sí, parar NEXO")]
    assert 'x-ref="primero"' in boton[boton.rindex("<button"):]        # el foco va al boton, no al campo
    assert "required" not in form[form.index('id="motivo-parada"'):]


def test_css_movil_el_panel_es_una_hoja_fija_en_pantalla():
    from pathlib import Path
    import re
    css = (Path(__file__).resolve().parents[1] / "estatico" / "nexo.css").read_text(encoding="utf-8")
    bloque = re.search(r"@media \(max-width: 640px\) \{\s*\.confirmar, \.error-parada \{(.*?)\}", css, re.S)
    assert bloque, "falta la regla movil del panel de PARADA"
    reglas = bloque.group(1)
    for r in ("position: fixed", "left: 12px", "right: 12px", "width: auto", "overflow-y: auto"):
        assert r in reglas
    # sin zoom de iOS; con la misma especificidad que ".confirmar input:not([type]) { font: inherit }"
    assert re.search(r"\.confirmar input:not\(\[type\]\), .*?\{ font-size: 16px; \}", css)


def test_version_de_cache_nueva():
    from pathlib import Path
    sw = (Path(__file__).resolve().parents[1] / "estatico" / "sw.js").read_text(encoding="utf-8")
    assert 'var VERSION = "nexo-v8";' in sw   # v8: T691 escritorio (nexo.css)


def test_css_movil_tactil_y_sin_zoom_en_toda_la_web():
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "estatico" / "humano.css").read_text(encoding="utf-8")
    bloque = css[css.rindex("@media (max-width: 640px)"):]
    assert "min-height: 44px !important" in bloque and "font-size: 16px !important" in bloque
