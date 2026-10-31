# -*- coding: utf-8 -*-
"""Fixtures comunes. Todo lo que escribe va a tmp_path: nunca a memoria/ de verdad."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from interfaz.app import crear_app
from interfaz.config import Ajustes
from interfaz.seguridad import COOKIE

BASE = "http://127.0.0.1:8765"


@pytest.fixture(autouse=True)
def bandera(tmp_path, monkeypatch):
    """PARADA_NEXO de prueba en tmp_path y sin tocar Ollama. Autouse: ningun test ve la bandera real."""
    from nucleo import parada
    ruta = tmp_path / "PARADA_NEXO"
    monkeypatch.setattr(parada, "BANDERA", ruta)
    monkeypatch.setattr(parada, "CIERRE", tmp_path / "CIERRE_TURNO")
    monkeypatch.setattr(parada, "_descargar_ollama", lambda: [])
    from nucleo import cierre_auto   # 11/10: si la web de prueba hace un tick, el cierre automatico no lanza nada
    monkeypatch.setattr(cierre_auto, "CARPETA", tmp_path / "cierre_auto")
    monkeypatch.setattr(cierre_auto, "LANZADOR", lambda: 0)
    from nucleo import espejo   # T890: ni la web de prueba publica el espejo de verdad
    monkeypatch.setattr(espejo, "CARPETA", tmp_path / "espejo")
    monkeypatch.setattr(espejo, "LANZADOR", lambda: (0, ""))
    return ruta


@pytest.fixture(autouse=True)
def modelos_estado_aislado(tmp_path, monkeypatch):
    """T669 (04/10): los dobles de Groq/NVIDIA anotaban en memoria/modelos_estado.json REAL (T320) y lo marcaban
    "vivo" con datos falsos; ademas el implementador veia ese archivo como cambio suyo. Siempre en tmp_path."""
    from nucleo import modelos_estado
    monkeypatch.setattr(modelos_estado, "ESTADO", tmp_path / "modelos_estado.json")
    monkeypatch.setattr(modelos_estado, "CANDADO", tmp_path / ".candado_modelos_estado.lock")
    from nucleo import implementador     # T669: el piloto y los informes del implementador, nunca los reales
    monkeypatch.setattr(implementador, "INFORMES", tmp_path / "implementador")
    monkeypatch.setattr(implementador, "PILOTO", tmp_path / "implementador" / "piloto.json")


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    """Rutas del core que la web lee o vigila, todas a tmp_path (nunca memoria/ ni registros/ reales)."""
    from nucleo import registro, tareas, trabajo
    memoria = tmp_path / "memoria"
    registros = tmp_path / "registros"
    memoria.mkdir()
    registros.mkdir()
    (memoria / "borradores").mkdir()
    monkeypatch.setattr(tareas, "ALMACEN", memoria / "tareas.json")
    from nucleo import responsables
    monkeypatch.setattr(responsables, "REPASO", memoria / "responsables_repaso.json")
    from nucleo import radar
    monkeypatch.setattr(radar, "CARPETA", memoria / "radares")
    monkeypatch.setattr(tareas, "VISTA", memoria / "tareas.md")
    monkeypatch.setattr(tareas, "VISTA_VAULT", tmp_path / "vault" / "tareas-por-prioridad.md")
    monkeypatch.setattr(tareas, "CANDADO", memoria / ".candado_tareas.lock")
    monkeypatch.setattr(registro, "CARPETA", registros)
    monkeypatch.setattr(trabajo, "BORRADORES", memoria / "borradores")
    from nucleo import revision
    monkeypatch.setattr(revision, "BORRADORES", memoria / "borradores")
    from nucleo import auditor, avisos
    monkeypatch.setattr(avisos, "CARPETA", memoria / "avisos")
    monkeypatch.setattr(auditor, "CARPETA", memoria / "auditoria")
    from nucleo import aprobaciones, chat_tarea
    monkeypatch.setattr(chat_tarea, "CARPETA", memoria / "chats_tareas")
    monkeypatch.setattr(chat_tarea, "CANDADO", memoria / "chats_tareas" / ".candado_chats.lock")
    monkeypatch.setattr(aprobaciones, "ALMACEN", memoria / "aprobaciones.json")
    monkeypatch.setattr(aprobaciones, "HISTORIAL", memoria / "aprobaciones_historial.jsonl")
    monkeypatch.setattr(aprobaciones, "CANDADO", memoria / ".candado_aprobaciones.lock")
    from nucleo import enfriamiento   # T549
    monkeypatch.setattr(enfriamiento, "APAGADOS", memoria / "proveedores_apagados.json")
    from nucleo import guardian   # T1020: ni el estado real del guardian ni su proceso de fondo; gancho apagado
    monkeypatch.setattr(guardian, "ESTADO", memoria / "guardian.json")
    monkeypatch.setattr(guardian, "REGISTRO", memoria / "guardian_decisiones.jsonl")
    monkeypatch.setattr(guardian, "CANDADO", memoria / ".candado_guardian.lock")
    monkeypatch.setattr(guardian, "LANZADOR", lambda: 0)
    monkeypatch.setattr(guardian, "GANCHO", False)
    monkeypatch.setattr(guardian, "_qwen", lambda prompt: "")
    try:
        from nucleo import chat_aprobacion
        monkeypatch.setattr(chat_aprobacion, "CARPETA", memoria / "chats_aprobaciones")
    except ImportError:
        pass
    from interfaz import hecho_llano, presentar   # T230 v2: ni la ultima visita real ni Qwen/Ollama de verdad
    monkeypatch.setattr(presentar, "VISITA", memoria / "interfaz_visita.json")
    monkeypatch.setattr(hecho_llano, "_qwen", lambda prompt: "")
    monkeypatch.setattr(hecho_llano, "_fallo_hasta", 0.0)
    return tmp_path


class ProveedorFalso:
    """Proveedor de pega: nunca sondea Ollama, Chrome ni APIs de verdad."""
    nombre = "falso"
    respuesta = {"disponible": True, "motivo": ""}
    llamadas = 0

    def estado(self):
        type(self).llamadas += 1
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return dict(self.respuesta)


@pytest.fixture(autouse=True)
def proveedores_falsos(monkeypatch):
    """Por defecto un unico proveedor falso disponible y la cache vacia. Los tests lo cambian."""
    import proveedores
    from interfaz import lecturas
    monkeypatch.setattr(proveedores, "ProveedorFalso", ProveedorFalso, raising=False)
    monkeypatch.setattr(lecturas, "CLASES_PROVEEDORES", ("ProveedorFalso",))
    monkeypatch.setattr(ProveedorFalso, "llamadas", 0)
    lecturas._cache_proveedores.update(cuando=0.0, lista=None)
    yield ProveedorFalso
    lecturas._cache_proveedores.update(cuando=0.0, lista=None)


@pytest.fixture
def ajustes(tmp_path):
    # Sin vigilancia en segundo plano: los tests que la necesitan la activan o llaman a revisar().
    return Ajustes(token_fichero=tmp_path / "interfaz_token.txt", vigilar=False, push_carpeta=tmp_path / "push")


@pytest.fixture
def app(ajustes):
    return crear_app(ajustes)


@pytest.fixture
def cliente(app):
    with TestClient(app, base_url=BASE) as c:
        yield c


@pytest.fixture
def csrf(cliente, app):
    """Inicia sesion con el token de arranque y devuelve el token CSRF de esa sesion."""
    r = cliente.get("/entrar", params={"t": app.state.seguridad.token})
    assert r.status_code == 200
    return app.state.seguridad.sesion(cliente.cookies.get(COOKIE))["csrf"]


@pytest.fixture(autouse=True)
def handoff_aislado(tmp_path, monkeypatch):
    """T140 pieza E: ningun test escribe el handoff a Claude de verdad (memoria/handoff_claude.jsonl)."""
    try:
        from nucleo import handoff
    except ImportError:          # hasta que el implementador cree nucleo/handoff.py
        return
    monkeypatch.setattr(handoff, "RUTA", tmp_path / "handoff_claude.jsonl")
