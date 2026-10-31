# -*- coding: utf-8 -*-
"""Hito movil, incremento 5: pantalla Ajustes y push en el service worker."""
from __future__ import annotations

from interfaz.vistas import DIR

SW = (DIR / "estatico" / "sw.js").read_text(encoding="utf-8")
JS = (DIR / "estatico" / "nexo.js").read_text(encoding="utf-8")
SUB = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "BP", "auth": "au"}}


def test_ajustes_necesita_sesion(cliente):
    assert cliente.get("/ajustes").status_code == 401


def test_ajustes_en_el_menu_y_con_el_componente(cliente, csrf):
    r = cliente.get("/ajustes")
    assert r.status_code == 200
    assert 'href="/ajustes"' in r.text and 'aria-current="page"' in r.text
    assert 'x-data="notificaciones"' in r.text
    assert "Dispositivos suscritos: 0" in r.text
    assert "Inicio automático" in r.text and "Sin restricciones" in r.text


def test_ajustes_cuenta_suscripciones(cliente, csrf):
    cliente.post("/push/suscribir", json=SUB, headers={"X-CSRF-Token": csrf})
    assert "Dispositivos suscritos: 1" in cliente.get("/ajustes").text


def test_ajustes_sin_tailnet_lo_dice(cliente, csrf):
    assert "Tailscale no está en marcha" in cliente.get("/ajustes").text


def test_sw_muestra_la_notificacion_y_abre_solo_rutas_internas():
    assert 'addEventListener("push"' in SW and "showNotification" in SW
    assert 'addEventListener("notificationclick"' in SW
    assert "rutaSegura(d.ruta)" in SW and "rutaSegura(e.notification.data" in SW
    assert "openWindow(destino)" in SW


def test_js_manda_csrf_en_los_post_de_push():
    assert '"X-CSRF-Token": csrfToken()' in JS
    assert "userVisibleOnly: true" in JS
