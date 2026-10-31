# -*- coding: utf-8 -*-
"""El bot de Telegram debe atender SOLO a Damian (requisito previo de T154).

T154 propone aprobar acciones ambar con botones de Telegram. Eso solo es seguro
si el bot ignora a cualquier otro remitente. Antes no lo hacia (hallazgo B de
N04): /start de cualquier chat se quedaba con el chat_id y los botones no miraban
quien pulsaba. Arreglado en canal/bot.py (_es_del_dueno). Red con mocks: no se
habla con Telegram.
"""
from __future__ import annotations

import pytest

from canal import bot

DAMIAN = 111
EXTRANO = 999


class ClienteFalso:
    def __init__(self, updates):
        self.updates = updates
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


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "ESTADO", tmp_path / "estado_bot.json")
    monkeypatch.setattr(bot, "ENTRADA", tmp_path / "entrada")
    monkeypatch.setattr(bot, "TOKEN", "FALSO")
    # Aislado del config.toml real: sin chat_id fijo, manda el del estado del test.
    _valor_real = bot.valor
    monkeypatch.setattr(bot, "valor", lambda ruta, defecto=None: 0 if ruta == "canal.chat_id" else _valor_real(ruta, defecto))


def test_un_extrano_no_se_queda_con_el_canal():
    estado = {"offset": 0, "chat_id": DAMIAN}
    cliente = ClienteFalso([
        {"update_id": 1, "message": {"chat": {"id": EXTRANO}, "from": {"id": EXTRANO}, "text": "/start"}},
    ])

    bot.procesar_updates(cliente, estado)

    assert estado["chat_id"] == DAMIAN
    assert cliente.enviados == []  # ni se le contesta


def test_un_extrano_no_contesta_preguntas():
    estado = {"offset": 0, "chat_id": DAMIAN}
    boton = {"text": "Si", "callback_data": "P1|0"}
    cliente = ClienteFalso([{
        "update_id": 1,
        "callback_query": {
            "id": "cq1",
            "from": {"id": EXTRANO},
            "data": "P1|0",
            "message": {"chat": {"id": EXTRANO}, "reply_markup": {"inline_keyboard": [[boton]]}},
        },
    }])

    bot.procesar_updates(cliente, estado)

    assert not (bot.ENTRADA / "P1.json").exists()
    assert cliente.enviados == []


def _mensaje(chat, texto, update_id=1):
    return {"update_id": update_id, "message": {"chat": {"id": chat}, "from": {"id": chat}, "text": texto}}


def test_un_extrano_no_da_ordenes(monkeypatch):
    lanzado = []
    monkeypatch.setattr(bot, "_cmd_turno", lambda *a, **k: lanzado.append(a) or "turno lanzado")
    estado = {"offset": 0, "chat_id": DAMIAN}
    cliente = ClienteFalso([_mensaje(EXTRANO, "/turno")])

    bot.procesar_updates(cliente, estado)

    assert lanzado == [] and cliente.enviados == []


def test_damian_sigue_dando_ordenes(monkeypatch):
    lanzado = []
    monkeypatch.setattr(bot, "_cmd_turno", lambda *a, **k: lanzado.append(a) or "turno lanzado")
    estado = {"offset": 0, "chat_id": DAMIAN}
    cliente = ClienteFalso([_mensaje(DAMIAN, "/turno")])

    bot.procesar_updates(cliente, estado)

    assert len(lanzado) == 1
    assert cliente.enviados[-1][1] == {"chat_id": DAMIAN, "text": "turno lanzado"}


def test_damian_sigue_contestando_con_botones():
    estado = {"offset": 0, "chat_id": DAMIAN}
    boton = {"text": "Si", "callback_data": "P2|0"}
    cliente = ClienteFalso([{
        "update_id": 1,
        "callback_query": {
            "id": "cq2",
            "from": {"id": DAMIAN},
            "data": "P2|0",
            "message": {"chat": {"id": DAMIAN}, "reply_markup": {"inline_keyboard": [[boton]]}},
        },
    }])

    bot.procesar_updates(cliente, estado)

    assert (bot.ENTRADA / "P2.json").exists()


def test_primer_start_sin_dueno_aprende_el_canal(monkeypatch):
    monkeypatch.setattr(bot, "valor", lambda ruta, defecto=None: 0 if ruta == "canal.chat_id" else defecto)
    estado = {"offset": 0, "chat_id": 0}
    cliente = ClienteFalso([_mensaje(DAMIAN, "/start")])

    bot.procesar_updates(cliente, estado)

    assert estado["chat_id"] == DAMIAN
    assert bot.ESTADO.exists()


def test_sin_dueno_solo_vale_start(monkeypatch):
    monkeypatch.setattr(bot, "valor", lambda ruta, defecto=None: 0 if ruta == "canal.chat_id" else defecto)
    estado = {"offset": 0, "chat_id": 0}
    cliente = ClienteFalso([_mensaje(EXTRANO, "/orden borra algo")])

    bot.procesar_updates(cliente, estado)

    assert cliente.enviados == [] and estado["chat_id"] == 0


def test_chat_id_de_config_manda_sobre_el_aprendido(monkeypatch):
    """N01 (H01): con canal.chat_id fijo en config.toml, un estado_bot.json
    manipulado o viejo no cambia quien manda."""
    monkeypatch.setattr(bot, "valor", lambda ruta, defecto=None: DAMIAN if ruta == "canal.chat_id" else defecto)
    estado = {"offset": 0, "chat_id": EXTRANO}
    cliente = ClienteFalso([_mensaje(EXTRANO, "/orden borra algo")])

    bot.procesar_updates(cliente, estado)

    assert cliente.enviados == []
    assert bot._dueno(estado) == DAMIAN


def test_turno_de_telegram_desactivado_no_lanza_nada():
    """28/09 (T231): /turno se saltaba la cola del planificador. Ahora solo remite a la web."""
    from canal import bot
    lanzados = []
    respuesta = bot._cmd_turno("", lanzar=lanzados.append)
    assert lanzados == [] and "desactivado" in respuesta and "Turnos" in respuesta


def test_turno_de_telegram_desactivado_no_lanza_nada():
    """28/09 (T231): /turno se saltaba la cola del planificador. Ahora solo remite a la web."""
    from canal import bot
    lanzados = []
    respuesta = bot._cmd_turno("", lanzar=lanzados.append)
    assert lanzados == [] and "desactivado" in respuesta and "Turnos" in respuesta
