# -*- coding: utf-8 -*-
"""extremidades/imagen.py: ComfyUI local, sin ComfyUI.

Solo tenia prueba_imagen_viva.py (necesita la GPU del PC). Aqui la API HTTP de ComfyUI
se simula y el reinicio se sustituye: se prueba el flujo de encargo, la deteccion del
cuadro negro, el reintento con ComfyUI recien arrancado y la regla de matar procesos.
"""
from __future__ import annotations

import httpx
import pytest

from extremidades import imagen

PNG_BUENO = b"\x89PNG" + b"x" * (imagen.MINIMO_CREIBLE + 10)


class ComfyFalso:
    """Simula /prompt, /history/<id> y /view. `historiales` es lo que devuelve cada sondeo."""

    def __init__(self, historiales, imagen_bytes=PNG_BUENO):
        self.historiales = list(historiales)
        self.imagen = imagen_bytes
        self.encargos = []

    def post(self, url, json=None, timeout=None):
        self.encargos.append(json)
        return httpx.Response(200, json={"prompt_id": "P1"}, request=httpx.Request("POST", url))

    def get(self, url, params=None, timeout=None):
        req = httpx.Request("GET", url)
        if "/history/" in url:
            h = self.historiales.pop(0) if len(self.historiales) > 1 else self.historiales[0]
            return httpx.Response(200, json=h, request=req)
        if url.endswith("/view"):
            return httpx.Response(200, content=self.imagen, request=req)
        return httpx.Response(200, json={}, request=req)


LISTO = {"P1": {"outputs": {"9": {"images": [{"filename": "a.png", "subfolder": "", "type": "output"}]}},
                "status": {"completed": True, "status_str": "success"}}}
ROTO = {"P1": {"outputs": {}, "status": {"completed": False, "status_str": "error"}}}


@pytest.fixture
def comfy(monkeypatch, tmp_path, reloj_falso):
    reloj_falso(imagen)
    monkeypatch.setattr(imagen, "salidas", lambda: tmp_path)
    monkeypatch.setattr(imagen, "valor", lambda ruta, defecto=None: defecto)

    def instalar(historiales, imagen_bytes=PNG_BUENO):
        falso = ComfyFalso(historiales, imagen_bytes)
        monkeypatch.setattr(imagen.httpx, "post", falso.post)
        monkeypatch.setattr(imagen.httpx, "get", falso.get)
        return falso

    return instalar


def test_flujo_lleva_prompt_negativo_y_semilla():
    f = imagen._flujo("un gato", "borroso", 42)
    assert f["6"]["inputs"]["text"] == "un gato" and f["7"]["inputs"]["text"] == "borroso"
    assert f["3"]["inputs"]["seed"] == 42 and f["9"]["class_type"] == "SaveImage"


def test_un_intento_espera_y_guarda_la_imagen(comfy, tmp_path):
    falso = comfy([{}, {}, LISTO])
    ruta = imagen._un_intento("gato", "", 1, espera_max=60)
    assert ruta.parent == tmp_path and ruta.read_bytes() == PNG_BUENO
    assert falso.encargos[0]["prompt"]["6"]["inputs"]["text"] == "gato"


def test_un_intento_detecta_el_cuadro_negro(comfy, tmp_path):
    comfy([LISTO], imagen_bytes=b"\x89PNG" + b"0" * 100)
    with pytest.raises(RuntimeError, match="vacia"):
        imagen._un_intento("gato", "", 1, espera_max=60)
    assert list(tmp_path.iterdir()) == []


def test_un_intento_falla_rapido_si_comfy_termina_sin_imagen(comfy):
    comfy([ROTO])
    with pytest.raises(RuntimeError, match="sin devolver imagen"):
        imagen._un_intento("gato", "", 1, espera_max=60)


def test_un_intento_timeout(comfy):
    comfy([{}])
    with pytest.raises(TimeoutError):
        imagen._un_intento("gato", "", 1, espera_max=10)


@pytest.fixture
def generar_aislado(monkeypatch):
    """generar() sin reiniciar nada de verdad. Devuelve el contador de reinicios."""
    estado = {"reinicios": 0, "reinicio_ok": True, "intentos": []}

    def reiniciar():
        estado["reinicios"] += 1
        if estado["reinicio_ok"]:
            imagen._encargos_hechos = 0
        return estado["reinicio_ok"]

    monkeypatch.setattr(imagen, "reiniciar_comfyui", reiniciar)
    monkeypatch.setattr(imagen, "disponible", lambda: True)
    monkeypatch.setattr(imagen, "_encargos_hechos", 0)
    return estado


def test_generar_con_comfy_limpio_no_reinicia(generar_aislado, monkeypatch, tmp_path):
    monkeypatch.setattr(imagen, "_un_intento", lambda *a: tmp_path / "ok.png")
    assert imagen.generar("gato", semilla=1) == tmp_path / "ok.png"
    assert generar_aislado["reinicios"] == 0 and imagen._encargos_hechos == 1


def test_generar_reinicia_antes_si_comfy_ya_se_uso(generar_aislado, monkeypatch, tmp_path):
    monkeypatch.setattr(imagen, "_encargos_hechos", 1)
    monkeypatch.setattr(imagen, "_un_intento", lambda *a: tmp_path / "ok.png")
    imagen.generar("gato", semilla=1)
    assert generar_aislado["reinicios"] == 1


def test_generar_reintenta_una_vez_tras_reiniciar(generar_aislado, monkeypatch, tmp_path):
    intentos = []

    def intento(*a):
        intentos.append(a)
        if len(intentos) == 1:
            raise TimeoutError("atascado en el paso 0")
        return tmp_path / "ok.png"

    monkeypatch.setattr(imagen, "_un_intento", intento)
    assert imagen.generar("gato", semilla=7) == tmp_path / "ok.png"
    assert len(intentos) == 2 and generar_aislado["reinicios"] == 1
    assert intentos[0][2] == intentos[1][2] == 7  # misma semilla


def test_generar_dos_fallos_da_un_error_con_diagnostico(generar_aislado, monkeypatch):
    def intento(*a):
        raise RuntimeError("vacia")

    monkeypatch.setattr(imagen, "_un_intento", intento)
    with pytest.raises(RuntimeError, match="dos veces"):
        imagen.generar("gato", semilla=1)


def test_generar_sin_comfy_y_sin_poder_levantarlo(generar_aislado, monkeypatch):
    monkeypatch.setattr(imagen, "disponible", lambda: False)
    generar_aislado["reinicio_ok"] = False
    with pytest.raises(RuntimeError, match="no responde"):
        imagen.generar("gato")


# B5 de N02 (arreglado): antes generar() ignoraba que el reinicio previo fallara.
def test_generar_no_encarga_si_el_reinicio_previo_fallo_y_comfy_no_responde(generar_aislado, monkeypatch, tmp_path):
    monkeypatch.setattr(imagen, "_encargos_hechos", 1)
    generar_aislado["reinicio_ok"] = False
    respuestas = iter([True, False])  # responde al principio; tras el reinicio fallido, ya no
    monkeypatch.setattr(imagen, "disponible", lambda: next(respuestas))
    encargos = []
    monkeypatch.setattr(imagen, "_un_intento", lambda *a: encargos.append(a) or tmp_path / "x.png")
    with pytest.raises(RuntimeError, match="No he podido reiniciar"):
        imagen.generar("gato", semilla=1)
    assert encargos == []


def test_generar_usa_el_comfy_ajeno_si_no_puede_reiniciarlo(generar_aislado, monkeypatch, tmp_path):
    """Un ComfyUI arrancado a mano no se mata: se usa tal cual."""
    monkeypatch.setattr(imagen, "_encargos_hechos", 1)
    generar_aislado["reinicio_ok"] = False
    monkeypatch.setattr(imagen, "_un_intento", lambda *a: tmp_path / "ok.png")
    assert imagen.generar("gato", semilla=1) == tmp_path / "ok.png"


# ------------------------------------------- B1 de N02: matar solo lo nuestro

class Shell:
    """Doble de manos.shell.ejecutar: apunta los comandos y contesta la linea de comando del PID."""

    def __init__(self, lineas=None, ok=True):
        self.comandos = []
        self.lineas = lineas or {}
        self.ok = ok

    def __call__(self, cmd, **k):
        self.comandos.append(cmd)
        salida = ""
        if "Get-CimInstance" in cmd:
            pid = int(cmd.split("ProcessId=")[1].split("'")[0])
            salida = self.lineas.get(pid, "")
        return type("R", (), {"ok": self.ok, "salida": salida, "codigo": 0 if self.ok else 1, "error": ""})()


@pytest.fixture
def anotado(tmp_path, monkeypatch):
    monkeypatch.setattr(imagen, "ANOTADO", tmp_path / "registros" / "comfyui_pid.json")
    # T1027: _anotar() consulta la identidad del PID; sin doble preguntaba a un proceso REAL con manos.shell y, en el
    # worktree del implementador (cwd fuera de la zona verde), fallaba con NecesitaAprobacion. Cada test pone su Shell.
    monkeypatch.setattr(imagen, "ejecutar", Shell())
    return imagen.ANOTADO


def _prohibido(cmd):
    return "-like" in cmd or "Name=" in cmd or "/IM" in cmd.upper() or "Stop-Process -Name" in cmd


def test_matar_sin_nada_anotado_no_toca_nada(anotado, monkeypatch):
    sh = Shell()
    monkeypatch.setattr(imagen, "ejecutar", sh)
    assert imagen._matar_comfyui() is False
    assert sh.comandos == []


def test_matar_solo_el_pid_anotado_tras_comprobar_su_linea(anotado, monkeypatch):
    imagen._anotar(4242)
    sh = Shell(lineas={4242: imagen._linea_arranque()})
    monkeypatch.setattr(imagen, "ejecutar", sh)
    assert imagen._matar_comfyui() is True
    assert "ProcessId=4242" in sh.comandos[0]
    assert sh.comandos[1] == "taskkill /PID 4242 /T /F"
    assert not any(_prohibido(c) for c in sh.comandos)


def test_matar_no_toca_un_pid_reutilizado_por_otro_proceso(anotado, monkeypatch):
    imagen._anotar(4242)
    sh = Shell(lineas={4242: r'"C:\Windows\notepad.exe"'})
    monkeypatch.setattr(imagen, "ejecutar", sh)
    assert imagen._matar_comfyui() is False
    assert not any("taskkill" in c for c in sh.comandos)


def test_matar_no_toca_si_el_pid_ya_no_existe(anotado, monkeypatch):
    imagen._anotar(4242)
    sh = Shell(lineas={})
    monkeypatch.setattr(imagen, "ejecutar", sh)
    assert imagen._matar_comfyui() is False
    assert not any("taskkill" in c for c in sh.comandos)


def test_matar_ignora_anotaciones_de_otra_orden_o_rotas(anotado, monkeypatch):
    sh = Shell(lineas={1: "x"})
    monkeypatch.setattr(imagen, "ejecutar", sh)
    anotado.parent.mkdir(parents=True, exist_ok=True)
    anotado.write_text('{"pid": 1, "linea": "otra cosa"}', encoding="utf-8")
    assert imagen._matar_comfyui() is False
    anotado.write_text("{roto", encoding="utf-8")
    assert imagen._matar_comfyui() is False
    assert sh.comandos == []


def test_reiniciar_no_lanza_otro_si_sigue_uno_ajeno(anotado, monkeypatch, reloj_falso):
    reloj_falso(imagen)
    monkeypatch.setattr(imagen, "_matar_comfyui", lambda: False)
    monkeypatch.setattr(imagen, "disponible", lambda: True)
    monkeypatch.setattr(imagen.subprocess, "Popen", lambda *a, **k: pytest.fail("no deberia lanzar"))
    assert imagen.reiniciar_comfyui() is False


def test_reiniciar_lanza_y_anota_su_pid(anotado, monkeypatch, reloj_falso):
    reloj_falso(imagen)
    monkeypatch.setattr(imagen, "_encargos_hechos", 1)  # se restaura al acabar
    monkeypatch.setattr(imagen, "_matar_comfyui", lambda: True)
    estados = iter([False, False, True])
    monkeypatch.setattr(imagen, "disponible", lambda: next(estados))
    lanzados = []

    class PopenFalso:
        pid = 9876

        def __init__(self, args, **kw):
            lanzados.append(args)

    monkeypatch.setattr(imagen.subprocess, "Popen", PopenFalso)
    monkeypatch.setattr(imagen, "ejecutar", Shell(lineas={9876: imagen._linea_arranque()}))
    assert imagen.reiniciar_comfyui(espera_max=30) is True
    assert lanzados == [imagen.ARRANQUE]
    assert imagen._anotado() == {"pid": 9876, "linea": imagen._linea_arranque()}
    assert imagen._encargos_hechos == 0


def test_no_queda_ningun_patron_de_matar_en_el_modulo():
    """Red de seguridad textual: la regla del 25/09 prohibe matar por patron o por nombre."""
    import inspect
    fuente = inspect.getsource(imagen)
    assert "Stop-Process" not in fuente
    assert "-like '*ComfyUI*'" not in fuente


# ------------------------------------------------------------------ T928, T929, T931, T048
class ShellCreacion(Shell):
    """Como Shell, pero la consulta de identidad devuelve tambien la hora de creacion (segunda linea)."""

    def __init__(self, lineas=None, creados=None, ok=True):
        super().__init__(lineas, ok)
        self.creados = creados or {}

    def __call__(self, cmd, **k):
        r = super().__call__(cmd, **k)
        if "Get-CimInstance" in cmd:
            pid = int(cmd.split("ProcessId=")[1].split("'")[0])
            if pid in self.creados:
                r.salida = f"{r.salida}\n{self.creados[pid]}"
        return r


def test_anotar_guarda_la_hora_de_creacion_del_proceso(anotado, monkeypatch):
    monkeypatch.setattr(imagen, "ejecutar", ShellCreacion(lineas={7: imagen._linea_arranque()},
                                                          creados={7: "2026-10-18T10:00:00.0000000Z"}))
    imagen._anotar(7)
    assert imagen._anotado()["creado"] == "2026-10-18T10:00:00.0000000Z"


def test_matar_exige_la_misma_hora_de_creacion_si_estaba_anotada(anotado, monkeypatch):
    """T929: otro proceso con el mismo PID y la MISMA linea (p. ej. un ComfyUI a mano) no se toca."""
    monkeypatch.setattr(imagen, "ejecutar", ShellCreacion(lineas={7: imagen._linea_arranque()},
                                                          creados={7: "2026-10-18T10:00:00.0000000Z"}))
    imagen._anotar(7)
    ajeno = ShellCreacion(lineas={7: imagen._linea_arranque()}, creados={7: "2026-10-18T11:30:00.0000000Z"})
    monkeypatch.setattr(imagen, "ejecutar", ajeno)
    assert imagen._matar_comfyui() is False
    assert not any("taskkill" in c for c in ajeno.comandos) and anotado.exists()
    propio = ShellCreacion(lineas={7: imagen._linea_arranque()}, creados={7: "2026-10-18T10:00:00.0000000Z"})
    monkeypatch.setattr(imagen, "ejecutar", propio)
    assert imagen._matar_comfyui() is True and "taskkill /PID 7 /T /F" in propio.comandos


def test_matar_borra_el_registro_para_que_no_apunte_a_un_pid_ajeno(anotado, monkeypatch):
    imagen._anotar(4242)
    monkeypatch.setattr(imagen, "ejecutar", Shell(lineas={4242: imagen._linea_arranque()}))
    assert imagen._matar_comfyui() is True
    assert not anotado.exists() and imagen._anotado() is None


def test_si_falla_anotar_tras_arrancar_se_termina_el_arbol_y_no_se_da_por_levantado(anotado, monkeypatch, reloj_falso):
    """T928."""
    reloj_falso(imagen)
    monkeypatch.setattr(imagen, "_matar_comfyui", lambda: True)
    monkeypatch.setattr(imagen, "disponible", lambda: False)

    class PopenFalso:
        pid = 5555

        def __init__(self, args, **kw):
            pass

        def kill(self):
            raise AssertionError("taskkill funciono: no hace falta kill")

    sh = Shell()
    monkeypatch.setattr(imagen.subprocess, "Popen", PopenFalso)
    monkeypatch.setattr(imagen, "ejecutar", sh)

    def anotar_roto(pid):
        raise OSError("disco lleno")
    monkeypatch.setattr(imagen, "_anotar", anotar_roto)
    assert imagen.reiniciar_comfyui(espera_max=30) is False
    assert sh.comandos == ["taskkill /PID 5555 /T /F"]


def test_si_falla_anotar_y_taskkill_tambien_se_mata_el_popen(anotado, monkeypatch, reloj_falso):
    reloj_falso(imagen)
    monkeypatch.setattr(imagen, "_matar_comfyui", lambda: True)
    monkeypatch.setattr(imagen, "disponible", lambda: False)
    muertos = []

    class PopenFalso:
        pid = 5556

        def __init__(self, args, **kw):
            pass

        def kill(self):
            muertos.append(self.pid)

    monkeypatch.setattr(imagen.subprocess, "Popen", PopenFalso)
    monkeypatch.setattr(imagen, "ejecutar", Shell(ok=False))
    monkeypatch.setattr(imagen, "_anotar", lambda pid: (_ for _ in ()).throw(OSError("x")))
    assert imagen.reiniciar_comfyui(espera_max=30) is False and muertos == [5556]


def test_un_http_de_error_al_consultar_no_se_disfraza_de_timeout(comfy):
    """T931: antes un 500 con cuerpo no-JSON acababa como TimeoutError tras agotar la espera."""
    class Roto(ComfyFalso):
        def get(self, url, params=None, timeout=None):
            if "/history/" in url:
                return httpx.Response(500, text="Internal Server Error", request=httpx.Request("GET", url))
            return super().get(url, params, timeout)
    falso = Roto([{}])
    imagen.httpx.post, imagen.httpx.get = falso.post, falso.get
    with pytest.raises(RuntimeError, match="HTTP 500"):
        imagen._un_intento("gato", "", 1, espera_max=600)


def test_un_error_de_red_o_un_json_a_medias_siguen_reintentandose(comfy, monkeypatch):
    falso = comfy([LISTO])
    llamadas = {"n": 0}
    real = falso.get

    def get(url, params=None, timeout=None):
        if "/history/" in url:
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                raise httpx.ConnectError("aun no")
            if llamadas["n"] == 2:
                return httpx.Response(200, text="{medio", request=httpx.Request("GET", url))
        return real(url, params, timeout)
    monkeypatch.setattr(imagen.httpx, "get", get)
    assert imagen._un_intento("gato", "", 1, espera_max=60).read_bytes() == PNG_BUENO and llamadas["n"] == 3


def test_arrancar_comfyui_pasa_por_permisos(anotado, monkeypatch, reloj_falso):
    """T048: en ambar o rojo no se lanza nada; en verde, si."""
    from nucleo import permisos
    reloj_falso(imagen)
    monkeypatch.setattr(imagen, "_matar_comfyui", lambda: False)
    monkeypatch.setattr(imagen, "disponible", lambda: False)
    monkeypatch.setattr(imagen.subprocess, "Popen", lambda *a, **k: pytest.fail("no deberia lanzar"))
    for nivel in (permisos.Nivel.AMBAR, permisos.Nivel.ROJO):
        monkeypatch.setattr(imagen.permisos, "nivel_de_comando", lambda c, n=nivel: n)
        assert imagen.reiniciar_comfyui(espera_max=5) is False
    monkeypatch.setattr(imagen.permisos, "nivel_de_comando", lambda c: permisos.Nivel.VERDE)
    monkeypatch.setattr(imagen.permisos, "nivel_de_ruta", lambda r, escritura=True: permisos.Nivel.AMBAR)
    assert imagen.reiniciar_comfyui(espera_max=5) is False        # la carpeta tampoco es zona verde


def test_el_arranque_real_de_comfyui_es_verde_para_permisos():
    from nucleo import permisos
    assert permisos.nivel_de_comando(imagen._linea_arranque()) is permisos.Nivel.VERDE
