# -*- coding: utf-8 -*-
"""Aprobaciones desde Telegram (T154 F4): canal/aprobaciones_bot.py y sus enganches en canal/bot.py.

Todo con mocks y en tmp_path: ni Telegram de verdad ni memoria/ real.
"""
from __future__ import annotations

import pytest

from canal import aprobaciones_bot as ab, bot
from nucleo import aprobaciones as ap

DAMIAN = 111
EXTRANO = 999


class ClienteFalso:
    def __init__(self, updates=()):
        self.updates = list(updates)
        self.enviados = []

    def get(self, url, **k):
        updates = self.updates

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"result": updates}

        return R()

    def post(self, url, json=None, **k):
        self.enviados.append((url.rsplit("/", 1)[-1], json))

        class R:
            def raise_for_status(self):
                pass

        return R()

    def textos(self):
        return [j.get("text", "") for m, j in self.enviados if m == "sendMessage"]


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "ALMACEN", tmp_path / "aprobaciones.json")
    monkeypatch.setattr(ap, "HISTORIAL", tmp_path / "aprobaciones_historial.jsonl")
    monkeypatch.setattr(ap, "CANDADO", tmp_path / ".candado.lock")
    monkeypatch.setattr(bot, "ESTADO", tmp_path / "estado_bot.json")
    monkeypatch.setattr(bot, "ENTRADA", tmp_path / "entrada")
    # Aislado del config.toml real: sin chat_id fijo, manda el del estado del test.
    _valor_real = bot.valor
    monkeypatch.setattr(bot, "valor", lambda ruta, defecto=None: 0 if ruta == "canal.chat_id" else _valor_real(ruta, defecto))
    monkeypatch.setattr(bot, "TOKEN", "FALSO")


def _mensaje(chat, texto):
    return {"update_id": 1, "message": {"chat": {"id": chat}, "from": {"id": chat}, "text": texto}}


def _boton(chat, data):
    return {"update_id": 1, "callback_query": {
        "id": "cq", "from": {"id": chat}, "data": data,
        "message": {"chat": {"id": chat}, "reply_markup": {"inline_keyboard": []}},
    }}


# ------------------------------------------------------------ modulo

def test_lista_vacia():
    assert ab.cmd_lista() == [{"text": "No hay nada esperando tu aprobacion."}]


def test_lista_con_botones():
    s = ap.solicitar("ejecutar comando", "winget install x", origen="mcp")

    [m] = ab.cmd_lista()

    assert s["id"] in m["text"] and "winget install x" in m["text"]
    datos = [b["callback_data"] for b in m["reply_markup"]["inline_keyboard"][0]]
    assert datos == [f"APR|{s['id']}|si", f"APR|{s['id']}|no"]


def test_aprobar_por_texto_deja_quien_en_el_historial():
    s = ap.solicitar("x", "y")

    r = ab.cmd_decidir(f"{s['id'].lower()} porque si", True)

    assert "aprobada" in r
    v = ap.ver(s["id"])
    assert v["estado"] == "aprobada"
    assert v["eventos"][-1]["quien"] == "damian:telegram"
    assert v["eventos"][-1]["motivo"] == "porque si"


def test_denegar_por_boton():
    s = ap.solicitar("x", "y")

    assert "denegada" in ab.boton(f"APR|{s['id']}|no")
    assert ap.ver(s["id"])["estado"] == "denegada"


@pytest.mark.parametrize("data", ["APR|A0001", "APR|A0001|quizas", "APR|A0001|si|mas"])
def test_boton_malformado_no_decide(data):
    ap.solicitar("x", "y")

    assert ab.boton(data) == "Boton no valido."
    assert ap.ver("A0001")["estado"] == "pendiente"


def test_errores_se_explican_sin_reventar():
    s = ap.solicitar("x", "y")
    ab.decidir(s["id"], False)

    assert "No se puede" in ab.decidir(s["id"], True)
    assert "No existe" in ab.decidir("A9999", True)
    assert "Uso:" in ab.cmd_decidir("   ", True)


def test_avisos_nuevos_una_sola_vez():
    estado = {}
    ap.solicitar("x", "1")

    assert len(ab.avisos_nuevos(estado)) == 1
    assert ab.avisos_nuevos(estado) == []

    ap.solicitar("x", "2")
    assert len(ab.avisos_nuevos(estado)) == 1


def test_avisos_no_crecen_sin_limite(monkeypatch):
    monkeypatch.setattr(ab, "MAX_AVISADAS", 3)
    estado = {}

    for i in range(5):
        ap.solicitar("x", str(i))

    ab.avisos_nuevos(estado)

    assert len(estado["aprobaciones_avisadas"]) == 3


def test_cola_rota_no_tumba_el_bot():
    ap.ALMACEN.write_text("{ roto", encoding="utf-8")

    assert ab.avisos_nuevos({}) == []
    assert "No puedo leer" in ab.cmd_lista()[0]["text"]


# ------------------------------------------------ enganches en canal/bot.py

def test_comando_aprobaciones_en_el_bot():
    ap.solicitar("ejecutar comando", "winget install x")
    cliente = ClienteFalso([_mensaje(DAMIAN, "/aprobaciones")])

    bot.procesar_updates(cliente, {"offset": 0, "chat_id": DAMIAN})

    [(metodo, cuerpo)] = cliente.enviados
    assert cuerpo["chat_id"] == DAMIAN and "reply_markup" in cuerpo


def test_boton_de_damian_aprueba():
    ap.solicitar("x", "y")
    cliente = ClienteFalso([_boton(DAMIAN, "APR|A0001|si")])

    bot.procesar_updates(cliente, {"offset": 0, "chat_id": DAMIAN})

    assert ap.ver("A0001")["estado"] == "aprobada"
    assert any("aprobada" in t for t in cliente.textos())
    # no se confunde con una respuesta a una pregunta normal
    assert not (bot.ENTRADA / "APR.json").exists()


def test_boton_de_un_extrano_no_aprueba():
    ap.solicitar("x", "y")
    cliente = ClienteFalso([_boton(EXTRANO, "APR|A0001|si")])

    bot.procesar_updates(cliente, {"offset": 0, "chat_id": DAMIAN})

    assert ap.ver("A0001")["estado"] == "pendiente"
    assert cliente.enviados == []


def test_extrano_no_aprueba_por_texto():
    ap.solicitar("x", "y")
    cliente = ClienteFalso([_mensaje(EXTRANO, "/aprobar A0001")])

    bot.procesar_updates(cliente, {"offset": 0, "chat_id": DAMIAN})

    assert ap.ver("A0001")["estado"] == "pendiente"


def test_denegar_por_texto_en_el_bot():
    ap.solicitar("x", "y")
    cliente = ClienteFalso([_mensaje(DAMIAN, "/denegar A0001 no me fio")])

    bot.procesar_updates(cliente, {"offset": 0, "chat_id": DAMIAN})

    assert ap.ver("A0001")["estado"] == "denegada"
    assert ap.ver("A0001")["eventos"][-1]["motivo"] == "no me fio"


def test_bucle_avisa_de_las_nuevas():
    ap.solicitar("ejecutar comando", "winget install x")
    estado = {"offset": 0, "chat_id": DAMIAN}
    cliente = ClienteFalso()

    bot._avisar_aprobaciones(cliente, estado)
    bot._avisar_aprobaciones(cliente, estado)

    assert len(cliente.enviados) == 1
    assert cliente.enviados[0][1]["chat_id"] == DAMIAN


def test_sin_dueno_no_avisa_a_nadie():
    ap.solicitar("x", "y")
    cliente = ClienteFalso()

    bot._avisar_aprobaciones(cliente, {"offset": 0, "chat_id": 0})

    assert cliente.enviados == []
