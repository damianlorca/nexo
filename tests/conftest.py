# -*- coding: utf-8 -*-
"""Fixtures comunes de la red de tests N02 (nucleo/, extremidades/, canal/).

Nada de lo que se prueba aqui toca red, Ollama, ComfyUI, Chrome ni Telegram:
todo va con dobles. Lo que escribe va a tmp_path, nunca a memoria/ ni canal/ reales.
"""
from __future__ import annotations

import time as _time
import sys
from pathlib import Path

import pytest

# Raiz del repo en sys.path para que `import nucleo` funcione desde tests/ (N05).
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


class TiempoFalso:
    """Sustituto del modulo `time` dentro de UN modulo bajo prueba.

    sleep() no espera: apunta la pausa y adelanta el reloj que devuelve time(),
    asi los bucles "hasta que pase X segundos" terminan al instante y de forma
    determinista. El resto de atributos (strftime...) son los de verdad.
    """

    def __init__(self):
        self.esperas: list[float] = []
        self._extra = 0.0

    def sleep(self, s):
        self.esperas.append(float(s))
        self._extra += float(s)

    def time(self):
        return _time.time() + self._extra

    def __getattr__(self, nombre):
        return getattr(_time, nombre)


@pytest.fixture
def reloj_falso(monkeypatch):
    """reloj_falso(modulo) -> TiempoFalso instalado en modulo.time."""

    def instalar(modulo):
        falso = TiempoFalso()
        monkeypatch.setattr(modulo, "time", falso)
        return falso

    return instalar


@pytest.fixture(autouse=True)
def avisos_aislados(tmp_path, tmp_path_factory, monkeypatch):
    """T189: ningun test deja avisos ni auditorias en memoria/ de verdad (los lee la web y hace push)."""
    from nucleo import auditor, avisos
    monkeypatch.setattr(avisos, "CARPETA", tmp_path / "avisos")
    monkeypatch.setattr(auditor, "CARPETA", tmp_path / "auditoria")
    from nucleo import enfriamiento   # T549: el interruptor manual de verdad no apaga proveedores en los tests
    monkeypatch.setattr(enfriamiento, "APAGADOS", tmp_path / "proveedores_apagados.json")
    # T157: el failover enfria el proveedor con una clave mala (401): nunca en memoria/enfriamiento.json real
    monkeypatch.setattr(enfriamiento, "ALMACEN", tmp_path / "enfriamiento.json")
    from nucleo import orden_proveedores   # T195: el orden de Ajustes nunca en memoria/ real
    monkeypatch.setattr(orden_proveedores, "ARCHIVO", tmp_path / "orden_proveedores.json")
    from nucleo import cuota   # T684: la cuota leida de las cabeceras, nunca en memoria/cuota.json real
    monkeypatch.setattr(cuota, "ALMACEN", tmp_path / "cuota.json")
    monkeypatch.setattr(cuota, "PRESUPUESTO", tmp_path / "cuota_presupuesto.json")
    monkeypatch.setattr(cuota, "CANDADO_PRESUPUESTO", tmp_path / ".candado_presupuesto.lock")
    monkeypatch.setattr(cuota, "CANDADO", tmp_path / ".candado_cuota.lock")
    from canal import interruptor   # T751: los tests no dependen de canal.bot_activo del config.toml real
    cfg = tmp_path_factory.mktemp("interruptor") / "config.toml"   # fuera de tmp_path: hay tests que lo listan
    cfg.write_text("[canal]\nbot_activo = true\n", encoding="utf-8")
    monkeypatch.setattr(interruptor, "ARCHIVO", cfg)
    from nucleo import vigia   # T550: el vigia de los tests nunca lee terminos de verdad (red)
    monkeypatch.setattr(vigia, "_terminos", lambda ahora: {})
    from nucleo import responsables   # 05/10: el repaso de responsables nunca escribe en memoria/ real
    monkeypatch.setattr(responsables, "REPASO", tmp_path / "responsables_repaso.json")
    from nucleo import radar   # T693: los radares de los tests nunca escriben en memoria/radares real
    monkeypatch.setattr(radar, "CARPETA", tmp_path / "radares")
    from nucleo import cierre_auto   # 11/10: el cierre automatico de los ticks de prueba no lanza procesos reales
    monkeypatch.setattr(cierre_auto, "CARPETA", tmp_path / "cierre_auto")
    monkeypatch.setattr(cierre_auto, "LANZADOR", lambda: 0)
    from nucleo import banco_modelos   # T890: el orden de los revisores no depende de roles.json real (cambia cada dia)
    monkeypatch.setattr(banco_modelos, "ROLES", tmp_path / "modelos" / "roles.json")
    from nucleo import espejo   # T890: ni un tick de prueba publica el espejo de verdad
    monkeypatch.setattr(espejo, "CARPETA", tmp_path / "espejo")
    monkeypatch.setattr(espejo, "LANZADOR", lambda: (0, ""))
    return tmp_path


@pytest.fixture(autouse=True)
def guardian_aislado(tmp_path_factory, monkeypatch):
    """T1020: el guardian de aprobaciones nunca lee ni escribe memoria/ real (ni la cola de aprobaciones de verdad, que
    un tick del planificador barreria) y nunca lanza su proceso de fondo. El gancho de aprobaciones.solicitar va
    apagado: los tests de siempre ven la cola como antes; los del guardian lo encienden."""
    d = tmp_path_factory.mktemp("guardian")   # fuera de tmp_path: hay tests que lo listan
    from nucleo import aprobaciones, guardian
    monkeypatch.setattr(aprobaciones, "ALMACEN", d / "aprobaciones.json")
    monkeypatch.setattr(aprobaciones, "HISTORIAL", d / "aprobaciones_historial.jsonl")
    monkeypatch.setattr(aprobaciones, "CANDADO", d / ".candado_aprobaciones.lock")
    monkeypatch.setattr(guardian, "ESTADO", d / "guardian.json")
    monkeypatch.setattr(guardian, "REGISTRO", d / "guardian_decisiones.jsonl")
    monkeypatch.setattr(guardian, "CANDADO", d / ".candado_guardian.lock")
    monkeypatch.setattr(guardian, "LANZADOR", lambda: 0)
    monkeypatch.setattr(guardian, "GANCHO", False)
    monkeypatch.setattr(guardian, "_qwen", lambda prompt: "")
    try:
        from nucleo import chat_aprobacion
        monkeypatch.setattr(chat_aprobacion, "CARPETA", d / "chats_aprobaciones")
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def sin_embeddings_reales(monkeypatch):
    """T1007: el filtro de propuestas repetidas (nucleo.freno) usa bge-m3 en Ollama; en tests nunca: cae a lo lexico."""
    def _no(*a, **k):
        raise ConnectionError("embeddings desactivados en tests")
    monkeypatch.setattr("nucleo.freno._embeber", _no)


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
def reparto_aislado(tmp_path_factory, monkeypatch):
    """T1069: el reparto de reels hace su propio commit; en la suite nunca en el repo real (REPO a una carpeta vacia,
    fuera de tmp_path) ni mirando el candado real del almacen (la puerta pregunta si hay un reparto en marcha)."""
    from nucleo import reels_destino
    d = tmp_path_factory.mktemp("reparto")
    monkeypatch.setattr(reels_destino, "REPO", d / "sin_repo")
    monkeypatch.setattr(reels_destino, "ALMACEN", d / "destinos.json")


@pytest.fixture(autouse=True)
def handoff_aislado(tmp_path, monkeypatch):
    """T140 pieza E: ningun test escribe el handoff a Claude de verdad (memoria/handoff_claude.jsonl)."""
    try:
        from nucleo import handoff
    except ImportError:          # hasta que el implementador cree nucleo/handoff.py
        return
    monkeypatch.setattr(handoff, "RUTA", tmp_path / "handoff_claude.jsonl")
