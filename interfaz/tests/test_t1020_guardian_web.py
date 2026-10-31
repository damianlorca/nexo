# -*- coding: utf-8 -*-
"""T1020: el guardian en la web. Fichas en Te toca y Bandejas (sin «sin clasificar»), la ficha de cada solicitud,
el grupo «Permisos que ha resuelto NEXO» y el interruptor de Ajustes."""
from __future__ import annotations

import pytest

from nucleo import aprobaciones as ap
from nucleo import guardian as G

RAIZ = G.RAIZ


def _post(cliente, csrf, url, **datos):
    return cliente.post(url, data=datos, headers={"X-CSRF-Token": csrf})


@pytest.fixture
def con_gancho(monkeypatch):
    monkeypatch.setattr(G, "GANCHO", True)


def test_tarjeta_de_te_toca_con_la_ficha_del_guardian(cliente, csrf, con_gancho):
    a = ap.solicitar("ejecutar comando", "Remove-Item documentacion\\notas_viejas.md", origen="mcp",
                     extra={"motivo": "limpiar notas viejas"})
    r = cliente.get("/centro/te_toca").text
    assert "Borrar notas_viejas.md." in r and "Borra de verdad" in r and "limpiar notas viejas" in r
    assert "Recomendación:" in r and "sin clasificar" not in r.lower()
    assert f'href="/aprobacion/{a["id"]}#chat-aprobacion">Preguntar</a>' in r


def test_lo_que_mira_el_tribunal_no_sale_en_te_toca_pero_si_en_bandejas(cliente, csrf, con_gancho):
    a = ap.solicitar("archivar", str(RAIZ / "herramientas_nube" / "_viejo.py"), origen="mcp")
    assert a["tribunal"]["estado"] == "pendiente"
    assert "Nada te espera" in cliente.get("/centro/te_toca").text
    r = cliente.get("/centro/ambar").text
    assert a["id"] in r and "El tribunal de 3 IAs lo está mirando" in r and "Mover _viejo.py a _archivo/" in r


def test_bandejas_ficha_completa(cliente, csrf, con_gancho):
    ap.solicitar("ejecutar comando", "git apply documentacion/diffs/guardia_T830_T832_T841.patch", origen="mcp")
    r = cliente.get("/centro/ambar").text
    for campo in ("Qué hace", "Sobre qué", "Tipo", "¿Se puede deshacer?", "Quién lo pide y para qué", "Recomendación",
                  "No lo ha dicho."):
        assert campo in r, campo
    assert "nucleo/permisos.py" in r and "sin clasificar" not in r.lower()


def test_ficha_de_una_solicitud_y_decidir_desde_ella(cliente, csrf, con_gancho):
    a = ap.solicitar("ejecutar comando", "Remove-Item documentacion\\x.md", origen="mcp")
    r = cliente.get(f"/aprobacion/{a['id']}")
    assert r.status_code == 200 and "Espera una decisión" in r.text and "Qué ha pasado" in r.text
    assert 'name="desde" value="ficha"' in r.text
    d = _post(cliente, csrf, "/ambar/decidir", id=a["id"], accion="denegar", desde="ficha")
    assert d.status_code == 204 and d.headers["HX-Redirect"] == f"/aprobacion/{a['id']}"
    assert "Denegada: no se hizo" in cliente.get(f"/aprobacion/{a['id']}").text
    otra = _post(cliente, csrf, "/ambar/decidir", id=a["id"], accion="denegar", desde="ficha")
    assert 'role="alert"' in otra.text
    assert cliente.get("/aprobacion/A9999").status_code == 404


def test_hecho_desde_tu_visita_permisos_que_ha_resuelto_nexo(cliente, csrf, con_gancho):
    a = ap.solicitar("ejecutar comando", "git log --oneline -3; Get-Content nucleo\\guardian.py | Select-Object -First 3",
                     origen="mcp")
    assert ap.ver(a["id"])["decidida_por"] == "guardian"
    r = cliente.get("/centro/hecho").text
    assert "Permisos que ha resuelto NEXO · 1 (1 sí, 0 no)" in r
    assert f'href="/aprobacion/{a["id"]}"' in r and "Aprobado por NEXO solo" in r


def test_interruptor_en_ajustes(cliente, csrf, con_gancho):
    assert "Permisos que resuelve NEXO (guardián)" in cliente.get("/ajustes").text
    r = _post(cliente, csrf, "/ajustes/guardian", accion="apagar")
    assert "Apagado." in r.text and G.activo() is False
    a = ap.solicitar("ejecutar comando", "Get-Content nucleo\\guardian.py | Select-Object -First 3", origen="mcp")
    assert a["estado"] == "pendiente"                                  # apagado: a Damian, con ficha
    assert "Solo lee (no cambia nada)" in cliente.get("/centro/te_toca").text
    r = _post(cliente, csrf, "/ajustes/guardian", accion="encender")
    assert "Encendido." in r.text and G.activo() is True
    assert _post(cliente, csrf, "/ajustes/guardian", accion="otra").text.count("Acción desconocida") == 1


def test_minichat_en_la_ficha(cliente, csrf, con_gancho, monkeypatch):
    from types import SimpleNamespace
    from nucleo import chat_aprobacion as CA

    class Nv:
        nombre = "nvidia"

        def disponible(self):
            return True

        def enviar(self, prompt):
            return SimpleNamespace(ok=True, texto="Borra una nota sin copia.", estado="ok", meta={})
    monkeypatch.setattr(CA, "proveedores", lambda: [Nv()])
    a = ap.solicitar("ejecutar comando", "Remove-Item documentacion\\x.md", origen="mcp")
    r = cliente.get(f"/aprobacion/{a['id']}").text
    assert 'id="chat-aprobacion"' in r and "Preguntar sobre este permiso" in r
    r = _post(cliente, csrf, f"/aprobacion/{a['id']}/chat", mensaje="¿Qué hace?").text
    assert "¿Qué hace?" in r and "Borra una nota sin copia." in r and "NVIDIA" in r
    r = _post(cliente, csrf, f"/aprobacion/{a['id']}/chat", mensaje="¿Seguro?", escalar="1").text
    assert "Guardada para Claude" in r and "para Claude" in r
    assert "Escribe la pregunta" in _post(cliente, csrf, f"/aprobacion/{a['id']}/chat", mensaje=" ").text
