# -*- coding: utf-8 -*-
"""canal/bot.py: la parte que HABLA con Telegram (enviar, teclado, estado, anotar, ocultar token).

Los prueba_*_bot.py cubren los comandos y procesar_updates; esto no tenia prueba.
Telegram se sustituye por httpx.MockTransport: ninguna peticion sale de la maquina.
"""
from __future__ import annotations

import json

import httpx
import pytest

from canal import bot

TOKEN_FALSO = "123456:TOKEN_DE_PRUEBA_NO_REAL"


@pytest.fixture
def rutas(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "ENTRADA", tmp_path / "entrada")
    monkeypatch.setattr(bot, "ESTADO", tmp_path / "estado_bot.json")
    monkeypatch.setattr(bot, "TOKEN", TOKEN_FALSO)
    monkeypatch.setattr(bot, "traza", lambda *a, **k: None)
    return tmp_path


def _cliente(responder):
    peticiones = []

    def manejador(req: httpx.Request):
        peticiones.append(req)
        return responder(req)

    return httpx.Client(transport=httpx.MockTransport(manejador)), peticiones


def test_teclado_filas_de_dos_y_de_una_si_el_texto_es_largo():
    t = bot.teclado(["si", "no", "una opcion bastante larga", "x"], "P1")
    filas = t["inline_keyboard"]
    assert [[b["text"] for b in f] for f in filas] == [["si", "no"], ["una opcion bastante larga"], ["x"]]
    assert filas[0][1]["callback_data"] == "P1|1"


def test_teclado_como_mucho_ocho_botones_y_texto_recortado():
    t = bot.teclado([f"o{i}" * 40 for i in range(12)], "P")
    botones = [b for f in t["inline_keyboard"] for b in f]
    assert len(botones) == 8
    assert all(len(b["text"]) <= 60 for b in botones)


def test_sin_chat_id_no_envia(rutas):
    cli, peticiones = _cliente(lambda r: httpx.Response(200, json={"ok": True}))
    assert bot.enviar(cli, {"chat_id": 0}, {"texto": "hola"}) is False
    assert peticiones == []


def test_aviso_normal_silencioso_y_urgente(rutas):
    cli, peticiones = _cliente(lambda r: httpx.Response(200, json={"ok": True}))
    assert bot.enviar(cli, {"chat_id": 9}, {"texto": "hola", "silencioso": True}) is True
    assert bot.enviar(cli, {"chat_id": 9}, {"texto": "fuego", "urgente": True}) is True
    c1, c2 = (json.loads(p.content) for p in peticiones)
    assert peticiones[0].url.path.endswith("/sendMessage")
    assert c1 == {"chat_id": 9, "text": "hola", "disable_notification": True}
    assert c2["text"].startswith("🔴 ") and c2["disable_notification"] is False


def test_aviso_se_recorta_a_4000(rutas):
    cli, peticiones = _cliente(lambda r: httpx.Response(200, json={"ok": True}))
    bot.enviar(cli, {"chat_id": 9}, {"texto": "a" * 5000})
    assert len(json.loads(peticiones[0].content)["text"]) == 4000


def test_pregunta_lleva_botones(rutas):
    cli, peticiones = _cliente(lambda r: httpx.Response(200, json={"ok": True}))
    bot.enviar(cli, {"chat_id": 9}, {"tipo": "pregunta", "id": "Q7", "texto": "¿Sigo?", "opciones": ["si", "no"]})
    cuerpo = json.loads(peticiones[0].content)
    assert cuerpo["text"] == "❓ ¿Sigo?"
    assert cuerpo["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "Q7|0"


def test_foto_que_no_existe_no_llama_a_telegram(rutas):
    cli, peticiones = _cliente(lambda r: httpx.Response(200, json={"ok": True}))
    assert bot.enviar(cli, {"chat_id": 9}, {"tipo": "foto", "ruta": str(rutas / "no.png")}) is False
    assert peticiones == []


def test_foto_y_archivo_van_como_multipart(rutas):
    img = rutas / "a.png"
    img.write_bytes(b"\x89PNG....")
    cli, peticiones = _cliente(lambda r: httpx.Response(200, json={"ok": True}))
    assert bot.enviar(cli, {"chat_id": 9}, {"tipo": "foto", "ruta": str(img), "texto": "pie"}) is True
    assert bot.enviar(cli, {"chat_id": 9}, {"tipo": "archivo", "ruta": str(img)}) is True
    assert peticiones[0].url.path.endswith("/sendPhoto")
    assert peticiones[1].url.path.endswith("/sendDocument")
    assert b'name="photo"' in peticiones[0].content and b"pie" in peticiones[0].content


def test_error_http_no_deja_el_token_en_el_log(rutas, caplog):
    cli, _ = _cliente(lambda r: httpx.Response(401, json={"ok": False}))
    with caplog.at_level("ERROR", logger="canal.bot"):
        assert bot.enviar(cli, {"chat_id": 9}, {"texto": "hola"}) is False
    assert caplog.records, "deberia registrar el fallo"
    assert TOKEN_FALSO not in caplog.text
    assert "<token_telegram>" in caplog.text


def test_sin_token_tambien_oculta_el_de_la_rutina(rutas, monkeypatch):
    monkeypatch.setattr(bot, "valor", lambda ruta, defecto=None: "rutina_secreta_xyz" if ruta == "rutina.token_api" else defecto)
    limpio = bot._sin_token(f"fallo en https://api.telegram.org/bot{TOKEN_FALSO}/x con rutina_secreta_xyz")
    assert TOKEN_FALSO not in limpio and "rutina_secreta_xyz" not in limpio


def test_cargar_estado_sin_archivo_o_roto_usa_el_de_config(rutas, monkeypatch):
    monkeypatch.setattr(bot, "valor", lambda ruta, defecto=None: 555 if ruta == "canal.chat_id" else defecto)
    assert bot.cargar_estado() == {"offset": 0, "chat_id": 555}
    bot.ESTADO.write_text("{roto", encoding="utf-8")
    assert bot.cargar_estado() == {"offset": 0, "chat_id": 555}


def test_guardar_y_cargar_estado_ida_y_vuelta(rutas):
    bot.guardar_estado({"offset": 42, "chat_id": 9, "nota": "ñ"})
    assert bot.cargar_estado() == {"offset": 42, "chat_id": 9, "nota": "ñ"}


def test_anotar_respuesta_escribe_en_entrada(rutas):
    bot.anotar_respuesta("Q1", "si", "boton")
    datos = json.loads((bot.ENTRADA / "Q1.json").read_text(encoding="utf-8"))
    assert datos["respuesta"] == "si" and datos["origen"] == "boton"


def test_anotar_libre_devuelve_la_forma_de_mensaje(rutas):
    m = bot.anotar_libre("compra pan")
    assert m["texto"] == "compra pan" and m["archivo"].startswith("libre_")
    assert json.loads((bot.ENTRADA / m["archivo"]).read_text(encoding="utf-8"))["texto"] == "compra pan"


# B3 de N02 (arreglado): antes el nombre era libre_HHMMSS.json y dos mensajes se pisaban.
def test_dos_mensajes_sueltos_en_el_mismo_segundo_no_se_pisan(rutas, monkeypatch):
    import time as _t
    original = _t.strftime  # bot.time es el modulo time global: guardar el original antes
    fijo = _t.struct_time((2026, 9, 25, 12, 0, 0, 3, 268, -1))
    monkeypatch.setattr(bot.time, "strftime", lambda fmt, *a: original(fmt, fijo))
    a = bot.anotar_libre("primero")
    b = bot.anotar_libre("segundo")
    textos = sorted(json.loads(p.read_text(encoding="utf-8"))["texto"] for p in bot.ENTRADA.glob("libre_*.json"))
    assert a["archivo"] != b["archivo"]
    assert textos == ["primero", "segundo"]
    assert a["archivo"].startswith("libre_20260925_120000_")


def test_nombres_de_libres_ordenan_cronologicamente(rutas, monkeypatch):
    import time as _t
    horas = iter([(2026, 9, 25, 23, 59, 59), (2026, 9, 26, 0, 0, 1)])

    original = _t.strftime

    def strftime(fmt, *a):
        return original(fmt, _t.struct_time((*actual[0], 0, 1, -1)))

    actual = [None]
    monkeypatch.setattr(bot.time, "strftime", strftime)
    nombres = []
    for h in horas:
        actual[0] = h
        nombres.append(bot.anotar_libre("x")["archivo"])
    assert sorted(nombres) == nombres


def test_guardar_estado_es_atomico(rutas, monkeypatch):
    """Si la escritura falla a mitad, el estado anterior sigue entero (antes quedaba roto)."""
    bot.guardar_estado({"offset": 7, "chat_id": 9})
    import nucleo.escritura as esc

    def reventar(*a, **k):
        raise OSError("disco lleno")

    monkeypatch.setattr(esc.os, "replace", reventar)
    with pytest.raises(OSError):
        bot.guardar_estado({"offset": 8, "chat_id": 9})
    assert bot.cargar_estado() == {"offset": 7, "chat_id": 9}
