# -*- coding: utf-8 -*-
"""Aislamiento de registros/ para TODA la suite (tests/ e interfaz/tests/).

Por que en la raiz: pytest.ini esta aqui, asi que pytest carga este conftest siempre, y lo
importa ANTES que los modulos de test. Eso importa porque varios modulos llaman a
registro.logger() al importarse, y eso creaba registros/agente_<fecha>.log real.

Incidente 27/09/2026 15:41: la suite escribio en registros/ REALES (trazas.jsonl con
"respuesta_movil" P2 de test_bot_remitente y turno_nexo_20260927_154135.json de test_turnos),
contaminando los registros que se usan para auditar y confundiendo un diagnostico.

Dos piezas:
- Redireccion: al importar, registro.* apunta a una carpeta temporal de la sesion; en cada test,
  un fixture autouse lleva todas las rutas conocidas de registros/ a tmp_path/registros.
- Guardian: un audit hook ve cada open/mkdir/rename/remove de ESTE proceso bajo registros/ reales
  (y bajo memoria/auditoria y memoria/avisos reales, ver mas abajo).
  Lo bloquea (PermissionError) y lo apunta; al final de la sesion, si hubo alguno, la suite falla.
  No compara mtimes a proposito: en el PC el bot y la web de NEXO escriben en registros/ mientras
  corre la suite, y eso daria falsos positivos. Lo que lance un subproceso no lo ve.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

REGISTROS_REALES = os.path.normcase(os.path.abspath(RAIZ / "registros"))
# Incidente 28/09/2026 08:32: aparecio en memoria/ real una auditoria BLOQUEADA de "T001 Investigar la
# libreria X" (dato de tests/test_ok_absoluto.py) y su aviso con push. No fue la suite (tests/conftest.py
# ya redirige auditor.CARPETA y avisos.CARPETA, T189) sino un script de depuracion suelto que reusaba
# esos dobles fuera de pytest. El guardian cubre tambien estas carpetas: si un fixture deja de
# redirigirlas, la suite falla en vez de ensuciar lo que lee la web.
PROTEGIDAS = (REGISTROS_REALES,
              os.path.normcase(os.path.abspath(RAIZ / "memoria" / "auditoria")),
              os.path.normcase(os.path.abspath(RAIZ / "memoria" / "avisos")),
              # T290: el chat de cada tarea y la cola de aprobaciones (lo que se aprueba desde el chat)
              os.path.normcase(os.path.abspath(RAIZ / "memoria" / "chats_tareas")),
              os.path.normcase(os.path.abspath(RAIZ / "memoria" / "aprobaciones.json")),
              os.path.normcase(os.path.abspath(RAIZ / "memoria" / "aprobaciones_historial.jsonl")),
              # T231 (28/09): un turno de test dejo un handoff falso en el vault real
              os.path.normcase(os.path.abspath(RAIZ.parent / "contexto" / "proyectos" / "nexo" / "handoffs-turno")),
              os.path.normcase(os.path.abspath(RAIZ / "memoria" / "turnos_config.json")),
              os.path.normcase(os.path.abspath(RAIZ / "memoria" / "planificador.json")),
              os.path.normcase(os.path.abspath(RAIZ / "memoria" / "turno_en_marcha.json")),
              os.path.normcase(os.path.abspath(RAIZ / "memoria" / "vigia")))
ESCRITURAS_PROHIBIDAS: list[str] = []
_EVENTOS = {"open", "os.mkdir", "os.rename", "os.replace", "os.remove", "os.rmdir",
            "os.truncate", "shutil.copyfile", "shutil.move", "shutil.rmtree"}


def _bajo_registros(ruta) -> bool:
    if isinstance(ruta, int):  # descriptor ya abierto
        return False
    try:
        ruta = os.fsdecode(os.fspath(ruta))
    except TypeError:
        return False
    ruta = os.path.normcase(os.path.abspath(ruta))
    return any(ruta == c or ruta.startswith(c + os.sep) for c in PROTEGIDAS)


def _es_escritura(evento: str, args) -> bool:
    if evento != "open":
        return True
    modo, flags = args[1], args[2]
    if isinstance(modo, str):
        return any(c in modo for c in "wax+")
    return bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC))


def _guardian(evento, args):
    if evento not in _EVENTOS or not args:
        return
    if evento == "shutil.copyfile":
        rutas = args[1:2]  # copiar DESDE registros/ es leer
    elif evento in ("os.rename", "os.replace", "shutil.move"):
        rutas = args[:2]
    else:
        rutas = args[:1]
    if not any(_bajo_registros(r) for r in rutas) or not _es_escritura(evento, args):
        return
    ESCRITURAS_PROHIBIDAS.append(f"{evento} {args[:2]!r}")
    raise PermissionError(f"test escribiendo en carpeta real protegida: {evento} {args[:2]!r}")


sys.addaudithook(_guardian)

# Antes de que ningun modulo de test se importe: lo que escriba registro al importar (logger())
# va a una carpeta temporal de la sesion, no a registros/.
from nucleo import registro  # noqa: E402

_SESION = Path(tempfile.mkdtemp(prefix="nexo_tests_registros_"))
registro.CARPETA = _SESION
registro.EVIDENCIA = _SESION / "evidencia.jsonl"
registro.CANDADO_EVIDENCIA = _SESION / ".candado_evidencia.lock"


@pytest.fixture(autouse=True)
def registros_aislados(tmp_path, monkeypatch):
    """Todas las rutas conocidas de registros/ a tmp_path/registros (la carpeta la crea quien escriba)."""
    import turno_nexo
    from extremidades import imagen
    from manos import shell
    from nucleo import instancia, uso_proveedores
    carpeta = tmp_path / "registros"
    monkeypatch.setattr(registro, "CARPETA", carpeta)
    monkeypatch.setattr(registro, "EVIDENCIA", carpeta / "evidencia.jsonl")
    monkeypatch.setattr(registro, "CANDADO_EVIDENCIA", carpeta / ".candado_evidencia.lock")
    monkeypatch.setattr(uso_proveedores, "REGISTRO", carpeta / "uso_proveedores.jsonl")
    monkeypatch.setattr(turno_nexo, "REGISTROS", carpeta)
    monkeypatch.setattr(instancia, "PIDS", carpeta)
    monkeypatch.setattr(shell, "LOGS", carpeta)
    monkeypatch.setattr(imagen, "ANOTADO", carpeta / "comfyui_pid.json")
    return carpeta


# Bloque 21 (25/10): una sola suite de NEXO a la vez (nucleo/cerrojo_suite.py). Una sesion lanzada a mano espera a la
# que este en marcha (implementador, puerta, otra de Claude) hasta ESPERA_CERROJO s; el pytest que lanza el propio
# implementador ya lo hereda y no espera.
ESPERA_CERROJO = 3600
_CERROJO = []


@pytest.hookimpl(tryfirst=True)       # antes de que pytest-xdist arranque sus workers
def pytest_sessionstart(session):
    from nucleo import cerrojo_suite
    if cerrojo_suite.heredado() or hasattr(session.config, "workerinput"):   # un worker: lo tiene su controlador
        return
    otro = cerrojo_suite.quien()
    if otro:
        sys.stderr.write(f"\n[NEXO] Hay otra suite de NEXO en marcha ({otro}): se espera a que acabe.\n")
        sys.stderr.flush()
    cm = cerrojo_suite.tomar(ESPERA_CERROJO, motivo=f"pytest en {RAIZ.name}")
    cm.__enter__()
    _CERROJO.append(cm)
    os.environ.update(cerrojo_suite.env_hijo())   # lo que lancen los tests (y los workers de xdist) ya lo tiene


def pytest_sessionfinish(session, exitstatus):
    while _CERROJO:
        _CERROJO.pop().__exit__(None, None, None)


@pytest.fixture(scope="session", autouse=True)
def registros_reales_intactos():
    """Falla la sesion si algun test intento escribir en registros/ reales (aunque se tragara el error)."""
    yield
    assert not ESCRITURAS_PROHIBIDAS, (
        "la suite intento escribir en registros/ o memoria/auditoria|avisos reales:\n  " + "\n  ".join(ESCRITURAS_PROHIBIDAS))


@pytest.fixture(autouse=True)
def sin_fsync(monkeypatch):
    """Bloque 21 (25/10): escribir_atomico hace fsync en cada escritura (~10 ms en este PC, y la suite escribe decenas
    de miles de veces en tmp_path). Que el contenido llegue al disco ante un apagon no lo comprueba ningun test; el
    resto (temporal en la misma carpeta, os.replace atomico) se sigue ejecutando igual."""
    monkeypatch.setattr(os, "fsync", lambda fd: None)


@pytest.fixture(autouse=True)
def perfil_privado_aislado(tmp_path, monkeypatch):
    """Bloque 21 (25/10): el auditor (T750) recorria memoria/perfil_privado REAL en cada llamada (17.000 archivos de
    reels: ~2 s cada vez, y la suite lo llama en cada ciclo de trabajo) y el resultado dependia de los datos privados de
    Damian, que no existen en los worktrees del implementador. Los tests de T750 ponen sus propias rutas encima."""
    from nucleo import auditor
    monkeypatch.setattr(auditor, "RUTAS_PERFIL", [tmp_path / "perfil_privado_vacio"])
    auditor._cache_perfil.clear()


@pytest.fixture(autouse=True)
def turnos_aislados(tmp_path, monkeypatch):
    """T231: tabla de turnos, planificador (cola y turno en marcha), cursor de lotes y vigia a tmp_path; y NUNCA
    un proceso de turno real ni red. Un test que necesite lanzar pasa su propio doble de `lanzar`."""
    from nucleo import planificador, plantillas_turno, trabajo, turnos, vigia
    carpeta = tmp_path / "memoria_turnos"
    monkeypatch.setattr(trabajo, "HANDOFFS", tmp_path / "handoffs-turno")   # el vault real no se toca
    monkeypatch.setattr(turnos, "BANDERA", carpeta / "TURNOS_DESACTIVADOS")
    monkeypatch.setattr(turnos, "CONFIG", carpeta / "turnos_config.json")
    monkeypatch.setattr(plantillas_turno, "ESTADO", carpeta / "turnos_estado.json")
    monkeypatch.setattr(planificador, "ESTADO", carpeta / "planificador.json")
    monkeypatch.setattr(planificador, "EN_MARCHA", carpeta / "turno_en_marcha.json")
    monkeypatch.setattr(planificador, "CANDADO", carpeta / ".candado_planificador.lock")
    monkeypatch.setattr(planificador, "SALIDAS", tmp_path / "registros")
    monkeypatch.setattr(vigia, "CARPETA", carpeta / "vigia")
    import turno_nexo           # 28/09: con un turno REAL en marcha, los tests veian su candado y abortaban
    monkeypatch.setattr(turno_nexo, "CANDADO", carpeta / ".candado_turno_nexo.lock")
    from nucleo import parada   # "Parar" un turno usa el cierre suave: ni la PARADA ni el cierre reales
    monkeypatch.setattr(parada, "BANDERA", carpeta / "PARADA_NEXO")
    monkeypatch.setattr(parada, "CIERRE", carpeta / "CIERRE_TURNO")
    # T666: el planificador consulta el freno, que lee la cola de tareas; sin esto un tick de prueba dependeria
    # de cuantas propuestas haya de verdad en memoria/. Archivo e informes del filtro, tambien fuera.
    from nucleo import freno
    from nucleo import tareas as T
    monkeypatch.setattr(T, "ALMACEN", carpeta / "tareas.json")
    monkeypatch.setattr(T, "VISTA", carpeta / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", carpeta / "vault" / "tareas-por-prioridad.md")
    monkeypatch.setattr(T, "CANDADO", carpeta / ".candado_tareas.lock")
    monkeypatch.setattr(freno, "REGISTRO", carpeta / "freno_archivo.jsonl")
    monkeypatch.setattr(freno, "INFORMES", carpeta / "freno")
    monkeypatch.setattr(freno, "BORRADORES", carpeta / "borradores")
    from nucleo import auditoria_cierres   # E1/T686: el tribunal lee de aqui los lotes a reconsiderar
    monkeypatch.setattr(auditoria_cierres, "INFORMES", carpeta / "investigacion")
    from nucleo import kuzushi             # T1011: su registro de hallazgos nunca es el de memoria/
    monkeypatch.setattr(kuzushi, "CARPETA", carpeta / "kuzushi")

    def sin_proceso(*a, **k):
        raise RuntimeError("test sin doble de lanzar: no se arranca un turno real")
    monkeypatch.setattr(planificador, "_popen", sin_proceso)

    def sin_matar(*a, **k):   # T1024: un test sin doble nunca lee procesos reales ni lanza un taskkill de verdad
        raise RuntimeError("test sin doble de procesos: no se lee ni se cierra nada real")
    monkeypatch.setattr(planificador, "_procesos", lambda: [])
    monkeypatch.setattr(planificador, "_linea_de_comando", sin_matar)
    monkeypatch.setattr(planificador, "_matar", sin_matar)
    from nucleo import linea_base   # T1027: ningun test crea el worktree de la linea base ni pasa la suite real alli
    monkeypatch.setattr(linea_base, "_medir", sin_matar)   # sin doble: la linea base "no disponible" = el rojo cuenta

    def sin_red(*a, **k):
        raise RuntimeError("test sin doble de red: el vigia no sale a internet en la suite")
    monkeypatch.setattr(vigia, "_get", sin_red)
    return carpeta
