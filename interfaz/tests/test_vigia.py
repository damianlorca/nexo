# -*- coding: utf-8 -*-
"""Incremento 9: vigia de la interfaz (relanza si cae, respeta la parada a proposito, no pisa otro programa)."""
from __future__ import annotations

import pytest

from interfaz import vigia
from interfaz.vigia import AJENA, CAIDA, SANA, Vigia


class Falso:
    """Web de pega: `estados` es lo que devolveran los sondeos, en orden (el ultimo se repite)."""

    def __init__(self, *estados, detenida=False):
        self.estados = list(estados)
        self.detenida = detenida
        self.lanzadas = self.matadas = 0
        self.log: list[tuple[str, str]] = []

    def sondear(self, puerto):
        return self.estados.pop(0) if len(self.estados) > 1 else self.estados[0]

    def lanzar(self, puerto):
        self.lanzadas += 1
        return 4321

    def matar(self):
        self.matadas += 1
        return True

    def vigia(self) -> Vigia:
        return Vigia(8799, sondear=self.sondear, lanzar=self.lanzar, matar=self.matar,
                     detenida=lambda: self.detenida, dormir=lambda s: None,
                     log=lambda nivel, msg: self.log.append((nivel, msg)), serve=self.serve)

    serve_aviso = None

    def serve(self, puerto):
        return self.serve_aviso


def test_al_iniciar_sesion_la_lanza_al_primer_fallo():
    f = Falso(CAIDA, SANA)
    assert f.vigia().paso() == "relanzada"
    assert f.lanzadas == 1 and f.matadas == 1


def test_sana_no_hace_nada_y_el_log_solo_recoge_cambios():
    f = Falso(SANA)
    v = f.vigia()
    assert [v.paso() for _ in range(5)] == ["sana"] * 5
    assert f.lanzadas == 0 and len(f.log) == 1


def test_un_fallo_suelto_no_la_reinicia_dos_seguidos_si():
    f = Falso(SANA, CAIDA, SANA, CAIDA, CAIDA, SANA)
    v = f.vigia()
    assert [v.paso() for _ in range(4)] == ["sana", "fallo", "sana", "fallo"]
    assert f.lanzadas == 0
    assert v.paso() == "relanzada" and f.lanzadas == 1


def test_parada_a_proposito_no_se_relanza():
    f = Falso(CAIDA, detenida=True)
    v = f.vigia()
    assert [v.paso() for _ in range(3)] == ["detenida"] * 3
    assert f.lanzadas == 0 and f.matadas == 0
    f.detenida = False  # seguir_interfaz.bat quita la marca
    f.estados = [CAIDA, CAIDA, SANA]
    assert v.paso() == "fallo"  # tras una parada vuelve a exigir dos fallos seguidos
    assert v.paso() == "relanzada" and f.lanzadas == 1


def test_la_parada_de_nexo_no_impide_relanzar_la_web(bandera):
    # Decision de Damian (25/09): la web es donde se pulsa "Seguir"; la PARADA ya bloquea las ordenes.
    from nucleo import parada
    parada.activar("prueba", "damian")
    f = Falso(CAIDA, SANA)
    assert f.vigia().paso() == "relanzada"


def test_puerto_ocupado_por_otro_programa_no_lanza():
    f = Falso(AJENA)
    v = f.vigia()
    assert [v.paso() for _ in range(3)] == ["ajena"] * 3
    assert f.lanzadas == 0 and f.matadas == 0
    assert f.log[0][0] == "warning" and "otro programa" in f.log[0][1]


def test_si_no_levanta_espera_cada_vez_mas_hasta_el_techo():
    f = Falso(CAIDA)
    v = f.vigia()
    esperas = []
    for _ in range(8):
        assert v.paso() == "sin_respuesta"
        esperas.append(v.espera)
    assert esperas[:3] == [60, 120, 240] and esperas[-1] == vigia.ESPERA_MAX
    assert f.lanzadas == 8 and all(n == "error" for n, _ in f.log)


def test_correr_sobrevive_a_una_pasada_que_revienta(monkeypatch):
    f = Falso(SANA)
    v = f.vigia()
    llamadas = {"n": 0}

    def paso():
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise RuntimeError("uy")
        raise KeyboardInterrupt  # para salir del bucle en el test

    monkeypatch.setattr(v, "paso", paso)
    with pytest.raises(KeyboardInterrupt):
        v.correr()
    assert llamadas["n"] == 2 and f.log == [("error", "pasada fallida: RuntimeError")]


# ------------------------------------------------------------------ rotacion del log
def test_rotar_log(tmp_path):
    log = tmp_path / "interfaz.log"
    log.write_bytes(b"x" * 10)
    vigia.rotar(log, max_bytes=100)
    assert log.exists() and not (tmp_path / "interfaz.log.1").exists()  # pequeño: no rota
    for i in range(4):
        log.write_bytes(bytes([65 + i]) * 200)
        vigia.rotar(log, max_bytes=100, copias=3)
    assert not log.exists()
    assert [(tmp_path / f"interfaz.log.{i}").read_bytes()[:1] for i in (1, 2, 3)] == [b"D", b"C", b"B"]
    assert not (tmp_path / "interfaz.log.4").exists()


# ------------------------------------------------------------------ sondeo real contra la app
def test_salud_se_identifica(cliente):
    r = cliente.get("/salud")
    assert r.json() == {"ok": True, "app": "nexo-interfaz"}


def test_sondear_puerto_sin_nada_es_caida():
    assert vigia.sondear(1, timeout=0.5) == CAIDA


def test_parar_y_seguir_marcan_y_desmarcan(tmp_path, monkeypatch):
    monkeypatch.setattr(vigia, "DETENIDA", tmp_path / "INTERFAZ_DETENIDA")
    monkeypatch.setattr(vigia, "matar_anotada", lambda: False)
    monkeypatch.setattr(vigia, "sondear", lambda p: SANA)
    assert "Marcada como detenida" in vigia.parar() and vigia.DETENIDA.exists()
    assert vigia.seguir() == "La web ya estaba en marcha." and not vigia.DETENIDA.exists()


# ------------------------------------------------------------------ code-review bloque 7-9
@pytest.fixture
def anotado(tmp_path, monkeypatch):
    """memoria/interfaz.pid de prueba y taskkill falso: ningun test mata nada de verdad."""
    import json
    fichero = tmp_path / "interfaz.pid"
    monkeypatch.setattr(vigia, "FICHERO_PID", fichero)
    matados = []
    monkeypatch.setattr(vigia, "_terminar", matados.append)

    def anotar(pid=4321, puerto=8765, linea=None):
        fichero.write_text(json.dumps({"pid": pid, "puerto": puerto,
                                       "linea": vigia.linea_web(puerto) if linea is None else linea}))
    return anotar, matados


def test_mata_solo_si_la_linea_de_comando_es_exactamente_la_de_la_web(anotado, monkeypatch):
    anotar, matados = anotado
    anotar()
    monkeypatch.setattr(vigia, "linea_de_comando", lambda pid: vigia.linea_web(8765))
    assert vigia.matar_anotada() is True and matados == [4321]


@pytest.mark.parametrize("real", [
    None,                                                                      # ya no existe
    r'"C:\...\pythonw.exe" C:\Users\damia\Desktop\AI\agente\canal\bot.py',     # PID reutilizado: el bot
    "LINEA_WEB --reload",                                                      # parecida, no exacta
])
def test_pid_reutilizado_o_muerto_no_se_mata(anotado, monkeypatch, real):
    anotar, matados = anotado
    anotar()
    real = vigia.linea_web(8765) + " --reload" if real == "LINEA_WEB --reload" else real
    monkeypatch.setattr(vigia, "linea_de_comando", lambda pid: real)
    assert vigia.matar_anotada() is False and matados == []


def test_fichero_viejo_o_manipulado_no_mata(anotado, monkeypatch, tmp_path):
    anotar, matados = anotado
    monkeypatch.setattr(vigia, "linea_de_comando", lambda pid: "cualquier cosa")
    vigia.FICHERO_PID.write_text("32020")  # formato del incremento 9 (solo el numero)
    assert vigia.matar_anotada() is False
    anotar(linea="cualquier cosa")  # la linea anotada no es la de la web: no se fia
    assert vigia.matar_anotada() is False and matados == []


def test_linea_de_comando_lee_win32_process_y_falla_cerrado(monkeypatch):
    """Bloque 23 (K0034): antes lanzaba un proceso real y preguntaba a PowerShell; con la suite cargando el PC (worktree
    del implementador) PowerShell tardaba y el test tumbo la puerta de T559 y T844. Ahora con un doble de
    subprocess.run: la consulta es la de Win32_Process por ESE pid, se lee en UTF-8 y todo fallo es None (nunca se mata
    un proceso cuya linea no se pudo leer)."""
    import subprocess
    llamadas = []
    SALIDA, VACIA = 'python.exe -c "ñ"' + chr(13) + chr(10), bytes([13, 10])

    def run(cmd, **k):
        llamadas.append((cmd, k))
        return subprocess.CompletedProcess(cmd, 0, stdout=SALIDA.encode("utf-8"), stderr=b"")
    monkeypatch.setattr(vigia.subprocess, "run", run)
    assert vigia.linea_de_comando(4321) == 'python.exe -c "ñ"'
    cmd, k = llamadas[0]
    assert cmd[0] == "powershell.exe" and "Win32_Process -Filter 'ProcessId=4321'" in cmd[-1] and k["timeout"]
    monkeypatch.setattr(vigia.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, VACIA, b""))
    assert vigia.linea_de_comando(4321) is None                       # el proceso ya no existe
    for error in (subprocess.TimeoutExpired("powershell.exe", 20), OSError("sin powershell")):
        def falla(cmd, error=error, **k):
            raise error
        monkeypatch.setattr(vigia.subprocess, "run", falla)
        assert vigia.linea_de_comando(4321) is None


def test_rotar_no_revienta_si_el_log_esta_bloqueado(tmp_path, monkeypatch):
    log = tmp_path / "interfaz.log"
    log.write_bytes(b"x" * 200)

    def bloqueado(*a):
        raise PermissionError("en uso por otro proceso")
    monkeypatch.setattr(vigia.os, "replace", bloqueado)
    vigia.rotar(log, max_bytes=100)  # no lanza: relanzar la web importa mas que rotar
    assert log.read_bytes() == b"x" * 200


def test_el_vigia_no_carga_la_web():
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-c", "import sys, interfaz.vigia; "
                        "print(sorted(m for m in ('proveedores', 'fastapi', 'interfaz.app', 'interfaz.lecturas') if m in sys.modules))"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "[]"


# ------------------------------------------------------------------ T196: matar con /T
def test_terminar_mata_el_arbol_del_pid_exacto(monkeypatch):
    llamadas = []
    monkeypatch.setattr(vigia.subprocess, "run", lambda orden, **kw: llamadas.append(orden))
    vigia._terminar(4321)
    assert llamadas == [["taskkill", "/PID", "4321", "/T", "/F"]]


def test_terminar_no_deja_vivo_al_hijo_real():
    """El pythonw del venv es un lanzador: el uvicorn de verdad es su HIJO. Sin /T el hijo sobrevivia
    con el puerto ocupado. Aqui: cmd (el PID anotado) con un ping hijo; los dos los lanza el test."""
    import subprocess
    import time
    p = subprocess.Popen(["cmd", "/c", "ping -n 30 127.0.0.1 >NUL"], creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        hijo = None
        for _ in range(20):
            r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                                f"(Get-CimInstance Win32_Process -Filter \"ParentProcessId={p.pid} AND Name='PING.EXE'\").ProcessId"],
                               capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
            salida = r.stdout.decode().split()
            if salida:
                hijo = int(salida[0])
                break
            time.sleep(0.2)
        assert hijo, "el cmd de prueba no llego a lanzar su ping"
        linea_hijo = vigia.linea_de_comando(hijo)
        assert linea_hijo and "ping" in linea_hijo.lower()
        vigia._terminar(p.pid)
        p.wait(timeout=10)
        time.sleep(0.5)
        assert vigia.linea_de_comando(hijo) is None, "el hijo sigue vivo tras matar al padre"
    finally:
        if p.poll() is None and vigia.linea_de_comando(p.pid) == subprocess.list2cmdline(p.args):
            vigia._terminar(p.pid)


# ------------------------------------------------------------ T868: la web se reinicia sola si cambia interfaz/

def _con_codigo(f, cambios, desde=100.0, reloj=None):
    """Vigia con reinicio por codigo: `cambios` = lo que devolvera cambio() en cada pasada (ruta o None)."""
    pedidos = []
    it = iter(cambios)

    def cambio(desde_, ahora):
        pedidos.append(desde_)
        return next(it, None)
    v = Vigia(8799, sondear=f.sondear, lanzar=f.lanzar, matar=f.matar, detenida=lambda: f.detenida,
              dormir=lambda s: None, log=lambda nivel, msg: f.log.append((nivel, msg)), serve=f.serve,
              cambio=cambio, desde=lambda: desde, reloj=reloj or (lambda: 1000.0))
    return v, pedidos


def test_cambio_en_interfaz_reinicia_la_web_sana_por_su_pid():
    f = Falso(SANA)
    v, pedidos = _con_codigo(f, [None, "rutas/centro.py"])
    assert v.paso() == "sana" and f.lanzadas == 0
    assert v.paso() == "reiniciada_por_codigo"
    assert f.matadas == 1 and f.lanzadas == 1 and pedidos == [100.0, 100.0]
    assert any("interfaz/rutas/centro.py" in m for _, m in f.log)


def test_sin_cambio_o_con_el_reinicio_desactivado_no_toca_nada():
    f = Falso(SANA)
    v, _ = _con_codigo(f, [])
    assert [v.paso() for _ in range(3)] == ["sana"] * 3 and f.matadas == f.lanzadas == 0
    v2 = f.vigia()                              # por defecto (tests, sin main()): sin reinicio por codigo
    assert v2.paso() == "sana" and f.lanzadas == 0


def test_no_reinicia_dos_veces_seguidas_ni_en_bucle():
    f = Falso(SANA)
    t = [1000.0]
    v, pedidos = _con_codigo(f, ["a.py", "b.py", "c.py"], reloj=lambda: t[0])
    assert v.paso() == "reiniciada_por_codigo"
    t[0] += 30                                   # menos de REINICIO_MIN: se espera
    assert v.paso() == "sana" and f.lanzadas == 1
    t[0] += vigia.REINICIO_MIN
    assert v.paso() == "reiniciada_por_codigo" and f.lanzadas == 2
    assert pedidos[-1] >= 1000.0                 # tras reiniciar, solo cuentan cambios posteriores


def test_si_la_web_no_la_lanzo_el_vigia_avisa_una_vez_y_no_lanza_otra():
    f = Falso(SANA)
    f.matar = lambda: False
    v, _ = _con_codigo(f, ["a.py", "a.py", "a.py"])
    assert [v.paso() for _ in range(3)] == ["sana"] * 3 and f.lanzadas == 0
    assert [m for n, m in f.log if "reiniciala a mano" in m].__len__() == 1


def test_web_nueva_que_no_responde_cae_en_el_backoff():
    f = Falso(SANA, CAIDA)                       # tras reiniciar, nunca vuelve a responder bien
    v, _ = _con_codigo(f, ["a.py"])
    assert v.paso() == "sin_respuesta" and v.espera == vigia.INTERVALO * 2


def test_cambio_de_codigo_mira_solo_codigo_de_la_web_y_espera_a_que_este_quieto(tmp_path):
    import os
    (tmp_path / "rutas").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "__pycache__").mkdir()
    viejo, nuevo, test, cache, nota = (tmp_path / "app.py", tmp_path / "rutas" / "centro.py",
                                       tmp_path / "tests" / "test_x.py", tmp_path / "__pycache__" / "a.py",
                                       tmp_path / "CLAUDE.md")
    for p, t in ((viejo, 50), (nuevo, 500), (test, 900), (cache, 900), (nota, 900)):
        p.write_text("x", encoding="utf-8")
        os.utime(p, (t, t))
    assert vigia.cambio_de_codigo(100, ahora=2000, raiz=tmp_path) == "rutas/centro.py"   # tests, cache y .md no cuentan
    assert vigia.cambio_de_codigo(100, ahora=510, raiz=tmp_path) is None                  # aun se esta tocando
    assert vigia.cambio_de_codigo(600, ahora=2000, raiz=tmp_path) is None                 # nada posterior a `desde`


def test_lanzada_desde_es_el_momento_en_que_se_anoto_el_pid(tmp_path, monkeypatch):
    import os
    pid = tmp_path / "interfaz.pid"
    monkeypatch.setattr(vigia, "FICHERO_PID", pid)
    assert vigia.lanzada_desde(7.0) == 7.0                 # sin fichero: desde que arranco el vigia
    pid.write_text("{}", encoding="utf-8")
    os.utime(pid, (321, 321))
    assert vigia.lanzada_desde(7.0) == 321.0


def test_con_un_turno_en_marcha_el_reinicio_por_codigo_espera_y_luego_se_hace():
    f = Falso(SANA)
    v, _ = _con_codigo(f, ["a.py", "a.py", "a.py"])
    ocupado = [True, True, False]
    v._ocupado = lambda: ocupado.pop(0)
    assert [v.paso(), v.paso()] == ["sana", "sana"] and f.matadas == f.lanzadas == 0
    assert [m for _, m in f.log if "pospuesto" in m].__len__() == 1       # avisa una vez, no en cada pasada
    assert v.paso() == "reiniciada_por_codigo" and f.matadas == 1 and f.lanzadas == 1


def test_turno_en_marcha_lee_el_fichero_del_planificador(tmp_path, monkeypatch):
    import json
    import os
    fichero = tmp_path / "turno_en_marcha.json"
    assert vigia.turno_en_marcha(fichero) is False                        # sin fichero: nada en marcha
    fichero.write_text(json.dumps({"turno": "noche"}), encoding="utf-8")
    assert vigia.turno_en_marcha(fichero) is False                        # sin pid_turno: aun no arranco
    fichero.write_text(json.dumps({"pid_turno": os.getpid()}), encoding="utf-8")
    assert vigia.turno_en_marcha(fichero) is True                         # este proceso esta vivo
    fichero.write_text(json.dumps({"pid_turno": 2 ** 30}), encoding="utf-8")
    assert vigia.turno_en_marcha(fichero) is False                        # ese pid no existe
    fichero.write_text("{roto", encoding="utf-8")
    assert vigia.turno_en_marcha(fichero) is True                         # ante la duda, esperar


# ---------------------------------------------------------------- T1028: una sola instancia y disparadores
def test_t1028_si_otro_vigia_tiene_el_candado_main_se_retira_sin_vigilar(monkeypatch):
    import nucleo.instancia as instancia
    pedidos = []
    monkeypatch.setattr(instancia, "unico", lambda nombre: pedidos.append(nombre) or False)
    monkeypatch.setattr(vigia.Vigia, "correr", lambda self: pytest.fail("con otro vigia vivo no se vigila"))
    assert vigia.main([]) == 0
    assert pedidos == ["nexo_interfaz_vigia"]


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="mutex de Windows")
def test_t1028_el_candado_del_vigia_no_se_coge_dos_veces(tmp_path, monkeypatch):
    """El candado real (mutex con nombre): la segunda toma falla mientras la primera siga viva."""
    import uuid

    import nucleo.instancia as instancia
    from nucleo.instancia import unico
    monkeypatch.setattr(instancia, "PIDS", tmp_path)
    nombre = f"nexo_test_vigia_{uuid.uuid4().hex}"
    assert unico(nombre) is True
    assert unico(nombre) is False


def test_t1028_la_tarea_programada_salta_al_desbloquear_y_cada_10_min_con_una_instancia():
    script = (vigia.RAIZ / "interfaz" / "scripts" / "registrar_autoarranque.ps1").read_text(encoding="utf-8")
    assert "-AtLogOn" in script
    assert "MSFT_TaskSessionStateChangeTrigger" in script and "StateChange = 8" in script   # desbloquear
    assert "-RepetitionInterval (New-TimeSpan -Minutes 10)" in script
    assert "-MultipleInstances IgnoreNew" in script
    assert "-Trigger $disparadores" in script
