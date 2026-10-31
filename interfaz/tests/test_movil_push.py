# -*- coding: utf-8 -*-
"""Hito movil, incremento 4: push (suscripcion con CSRF, envio simulado, anti-spam, turnos)."""
from __future__ import annotations

import json
import subprocess

import pytest

from interfaz import push
from interfaz.config import RAIZ
from interfaz.eventos import Bus
from interfaz.push import Almacen, Notificador
from interfaz.vigilancia import Vigilante, fallos_turno

FCM = "https://fcm.googleapis.com/fcm/send/abc123"
SUB = {"endpoint": FCM, "keys": {"p256dh": "BPclave", "auth": "autor"}}


class Inmediato:
    """Ejecutor sincrono: lo encolado se ejecuta ya (los tests no esperan hilos)."""
    def submit(self, f, *a):
        f(*a)

    def shutdown(self, **k):
        pass


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class TimerFalso:
    creados: list = []

    def __init__(self, espera, funcion):
        self.espera, self.funcion, self.daemon = espera, funcion, False
        TimerFalso.creados.append(self)

    def start(self):
        pass

    def cancel(self):
        pass


@pytest.fixture
def almacen(tmp_path):
    return Almacen(tmp_path / "push")


@pytest.fixture
def envios():
    return []


@pytest.fixture
def notif(almacen, envios):
    TimerFalso.creados = []
    almacen.guardar(SUB)

    def enviar(sub, datos, clave, urgencia):
        envios.append((sub["endpoint"], json.loads(datos), urgencia))
        return 201
    ordenes = {"W7": {"texto": "Resúmeme el PDF de becas con la clave sk-" + "a" * 30,
                      "resultado": {"tarea": "T185"}}}
    return Notificador(almacen, buscar_orden=ordenes.get, enviar=enviar, ejecutor=Inmediato(),
                       reloj=Reloj(), temporizador=TimerFalso)


class Ev:
    def __init__(self, tipo, datos):
        self.tipo, self.datos = tipo, datos


# ------------------------------------------------------------ traduccion
def test_orden_terminada_tipo_id_y_frase_sin_secretos(notif, envios):
    notif.oir(Ev("orden", {"id": "W7", "estado": "en_curso"}))
    assert envios == []
    notif.oir(Ev("orden", {"id": "W7", "estado": "hecha"}))
    (_, datos, _), = envios
    assert datos["titulo"] == "Orden W7 · T185 terminada"
    assert datos["ruta"] == "/ordenes"
    assert "Resúmeme el PDF de becas" in datos["cuerpo"]
    assert "sk-aaaa" not in datos["cuerpo"]
    assert len(datos["cuerpo"]) <= push.LARGO_FRASE
    assert set(datos) == {"titulo", "cuerpo", "ruta", "etiqueta"}


def test_maximo_un_push_por_orden(notif, envios):
    for estado in ("hecha", "hecha", "error"):
        notif.oir(Ev("orden", {"id": "W7", "estado": estado}))
    assert len(envios) == 1


def test_orden_con_error(notif, envios):
    notif.oir(Ev("orden", {"id": "W9", "estado": "error"}))
    assert envios[0][1]["titulo"] == "Orden W9 con error"


def test_parada_con_motivo_y_urgente(notif, envios):
    notif.oir(Ev("parada", {"activa": True, "motivo": "se ha vuelto loco el router"}))
    notif.oir(Ev("parada", {"activa": False, "motivo": ""}))
    assert [e[1]["titulo"] for e in envios] == ["PARADA activada", "PARADA quitada"]
    assert envios[0][1]["cuerpo"] == "se ha vuelto loco el router"
    assert envios[0][2] == "high"


def test_turno_solo_con_fallos_y_una_vez(notif, envios):
    notif.oir(Ev("turno", {"nombre": "turno_nexo_1.json", "fallos": []}))
    notif.oir(Ev("turno", {"nombre": "turno_nexo_2.json", "fallos": ["router", "catalogo"]}))
    notif.oir(Ev("turno", {"nombre": "turno_nexo_2.json", "fallos": ["router", "catalogo"]}))
    assert len(envios) == 1
    assert envios[0][1]["titulo"] == "Turno nocturno: 2 fallos"
    assert envios[0][1]["cuerpo"] == "router, catalogo" and envios[0][1]["ruta"] == "/logs"


def test_otros_eventos_no_avisan(notif, envios):
    for tipo in ("log", "tareas", "borrador"):
        notif.oir(Ev(tipo, {}))
    assert envios == []


# ------------------------------------------------------------ anti-spam
def test_mas_de_5_por_minuto_se_agrupan(notif, envios):
    for i in range(8):
        notif.oir(Ev("orden", {"id": f"W{100 + i}", "estado": "hecha"}))
    assert len(envios) == 5
    timer, = TimerFalso.creados        # un solo temporizador para todo lo pendiente
    assert 0 < timer.espera <= push.VENTANA
    notif.oir(Ev("parada", {"activa": True, "motivo": "x"}))
    timer.funcion()
    assert len(envios) == 6
    agrupado = envios[-1][1]
    assert agrupado["titulo"] == "NEXO: 4 avisos"
    assert agrupado["cuerpo"].startswith("PARADA activada")   # la PARADA primero
    assert envios[-1][2] == "high"


def test_pasada_la_ventana_vuelve_a_enviar_directo(notif, envios):
    for i in range(5):
        notif.oir(Ev("orden", {"id": f"W{i}", "estado": "hecha"}))
    notif._reloj.t += push.VENTANA + 1
    notif.oir(Ev("orden", {"id": "W50", "estado": "hecha"}))
    assert len(envios) == 6 and TimerFalso.creados == []


# ------------------------------------------------------------ envio y caducadas
def test_suscripcion_caducada_410_se_borra(almacen):
    almacen.guardar(SUB)
    otra = {**SUB, "endpoint": FCM + "zz"}
    almacen.guardar(otra)
    n = Notificador(almacen, enviar=lambda s, *a: 410 if s["endpoint"] == FCM else 201, ejecutor=Inmediato())
    r = n._enviar_a_todos({"titulo": "t", "cuerpo": "c", "ruta": "/", "etiqueta": "e"})
    assert r == {"enviados": 1, "caducadas": 1, "fallos": 0}
    assert [s["endpoint"] for s in almacen.todas()] == [otra["endpoint"]]


def test_un_envio_que_revienta_no_para_los_demas(almacen):
    almacen.guardar(SUB)
    n = Notificador(almacen, enviar=lambda *a: 1 / 0, ejecutor=Inmediato())
    assert n._enviar_a_todos({"titulo": "t", "cuerpo": "c", "ruta": "/", "etiqueta": "e"})["fallos"] == 1


def test_claves_vapid_se_generan_una_vez(almacen):
    c1 = almacen.clave_publica()
    c2 = almacen.clave_publica()
    assert c1 == c2 and len(c1) == 87                # punto P-256 sin comprimir (65 bytes) en base64url
    assert almacen.clave_privada.read_text().startswith("-----BEGIN")


def test_gitignore_excluye_la_carpeta_push():
    r = subprocess.run(["git", "check-ignore", "-q", "memoria/push/vapid_privada.pem"], cwd=RAIZ)
    assert r.returncode == 0


def test_bus_llama_a_los_oyentes_y_uno_roto_no_molesta():
    bus, vistos = Bus(), []
    bus.oir(lambda ev: 1 / 0)
    bus.oir(lambda ev: vistos.append(ev.tipo))
    bus.publicar("parada", {"activa": True})
    assert vistos == ["parada"]


# ------------------------------------------------------------ endpoints
def test_suscribir_necesita_csrf(cliente, csrf):
    assert cliente.post("/push/suscribir", json=SUB).status_code == 403
    r = cliente.post("/push/suscribir", json=SUB, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["ok"]
    assert cliente.app.state.notificador.almacen.todas()[0]["endpoint"] == FCM


def test_suscribir_sin_sesion_da_401(cliente):
    assert cliente.post("/push/suscribir", json=SUB, headers={"X-CSRF-Token": "x"}).status_code == 401


@pytest.mark.parametrize("mala", [
    {**SUB, "endpoint": "https://evil.example/recoge"},          # servidor push desconocido
    {**SUB, "endpoint": "http://fcm.googleapis.com/x"},          # sin https
    {**SUB, "endpoint": "https://fcm.googleapis.com.evil.com/x"},
    {"endpoint": FCM},                                           # sin claves
    "no es un dict",
])
def test_suscripcion_mala_da_400(cliente, csrf, mala):
    r = cliente.post("/push/suscribir", json=mala, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 400
    assert cliente.app.state.notificador.almacen.todas() == []


def test_baja_y_clave(cliente, csrf):
    cliente.post("/push/suscribir", json=SUB, headers={"X-CSRF-Token": csrf})
    assert len(cliente.get("/push/clave").json()["clave"]) == 87
    r = cliente.post("/push/baja", json={"endpoint": FCM}, headers={"X-CSRF-Token": csrf})
    assert r.json() == {"ok": True, "quitada": True}
    assert cliente.app.state.notificador.almacen.todas() == []


def test_prueba_envia_a_las_suscripciones(cliente, csrf, monkeypatch):
    enviados = []
    monkeypatch.setattr(cliente.app.state.notificador, "_enviar", lambda s, d, c, u: enviados.append(d) or 201)
    cliente.post("/push/suscribir", json=SUB, headers={"X-CSRF-Token": csrf})
    r = cliente.post("/push/prueba", headers={"X-CSRF-Token": csrf})
    assert r.json()["ok"] and r.json()["enviados"] == 1
    assert json.loads(enviados[0])["titulo"] == "NEXO: prueba"


def test_orden_de_la_web_llega_al_push_por_el_bus(cliente, csrf, monkeypatch):
    avisos = []
    monkeypatch.setattr(cliente.app.state.notificador, "avisar", avisos.append)
    cliente.app.state.bus.publicar("orden", {"id": "W1", "estado": "hecha"})
    assert avisos and avisos[0]["titulo"].startswith("Orden W1")


# ------------------------------------------------------------ turnos en la vigilancia
def test_fallos_turno_ignora_saltados():
    datos = {"pasos": {"libres": {"pendientes": 3}, "router": {"error": "TimeoutError: x"},
                       "trabajo": {"error": "saltado: PARADA DE EMERGENCIA"},
                       "catalogo": {"error": "saltado: RAM libre 1.2 GB"}},
             "handoff_error": "telegram caido"}
    assert fallos_turno(datos) == ["router", "handoff"]
    assert fallos_turno({}) == [] and fallos_turno(None) == []


def test_vigilancia_emite_turno_nuevo_y_espera_si_esta_a_medias(entorno):
    registros = entorno / "registros"
    (registros / "turno_nexo_viejo.json").write_text('{"pasos": {"a": {"error": "x"}}}', encoding="utf-8")
    v = Vigilante(Bus())
    assert v.revisar() == []                               # foto inicial: el viejo no avisa
    nuevo = registros / "turno_nexo_nuevo.json"
    nuevo.write_text('{"pasos": {"router": {"err', encoding="utf-8")   # a medio escribir
    assert [e for e in v.revisar() if e[0] == "turno"] == []
    nuevo.write_text(json.dumps({"pasos": {"router": {"error": "boom"}}}), encoding="utf-8")
    turnos = [e for e in v.revisar() if e[0] == "turno"]
    assert turnos == [("turno", {"nombre": "turno_nexo_nuevo.json", "fallos": ["router"]})]
    assert [e for e in v.revisar() if e[0] == "turno"] == []   # una sola vez


# ------------------------------------------------------------ hallazgos 6 y 7 del code-review
def test_el_tope_de_ya_avisados_tira_las_mas_antiguas_no_la_recien_anadida(notif, envios, monkeypatch):
    monkeypatch.setattr(push, "MAX_YA_AVISADOS", 5)
    for i in range(20):
        assert notif._primera_vez(f"orden:W{i}")
    assert list(notif._ya_avisados) == [f"orden:W{i}" for i in range(15, 20)]
    assert not notif._primera_vez("orden:W19")      # la mas reciente sigue recordada: no repite push


def test_agrupado_tras_cerrar_no_revienta_ni_envia(notif, envios):
    for i in range(7):
        notif.oir(Ev("orden", {"id": f"W{i}", "estado": "hecha"}))
    timer, = TimerFalso.creados
    notif.cerrar()
    timer.funcion()                                  # el Timer ya habia saltado: no debe lanzar nada
    assert len(envios) == 5


def test_agrupado_con_ejecutor_ya_apagado_no_lanza(notif, envios):
    class Apagado:
        def submit(self, *a):
            raise RuntimeError("cannot schedule new futures after shutdown")
    for i in range(7):
        notif.oir(Ev("orden", {"id": f"W{i}", "estado": "hecha"}))
    notif._ejecutor = Apagado()
    TimerFalso.creados[0].funcion()                  # sin excepcion
