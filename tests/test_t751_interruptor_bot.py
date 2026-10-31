# -*- coding: utf-8 -*-
"""T751: interruptor canal.bot_activo (config.toml). Apagado: el vigilante no relanza y el bot no arranca."""
from __future__ import annotations

import pytest

from canal import interruptor


def test_lee_config_en_fresco(tmp_path):
    cfg = tmp_path / "config.toml"
    assert interruptor.bot_activo(cfg) is False                     # ilegible/ausente: apagado
    cfg.write_text("[canal]\nchat_id = 1\n", encoding="utf-8")
    assert interruptor.bot_activo(cfg) is True                      # sin la clave: como siempre
    cfg.write_text("[canal]\nbot_activo = false\n", encoding="utf-8")
    assert interruptor.bot_activo(cfg) is False
    cfg.write_text("[canal]\nbot_activo = true\n", encoding="utf-8")
    assert interruptor.bot_activo(cfg) is True
    cfg.write_text("[canal\nroto", encoding="utf-8")
    assert interruptor.bot_activo(cfg) is False


def test_vigilante_no_relanza_con_el_bot_apagado(monkeypatch):
    from canal import vigilante
    arrancados, vueltas = [], []

    class Fin(Exception):
        pass

    def dormir(s):
        vueltas.append(s)
        if len(vueltas) >= 3:
            raise Fin
    monkeypatch.setattr(vigilante, "unico", lambda nombre: True)
    monkeypatch.setattr(vigilante, "bot_activo", lambda: False)
    monkeypatch.setattr(vigilante, "pid_anotado", lambda n: 0)
    monkeypatch.setattr(vigilante, "_arrancar", lambda: arrancados.append(1))
    monkeypatch.setattr(vigilante.time, "sleep", dormir)
    with pytest.raises(Fin):
        vigilante.main()
    assert arrancados == []


def test_bot_no_arranca_con_el_interruptor_apagado(monkeypatch):
    from canal import bot
    monkeypatch.setattr(bot, "TOKEN", "falso")
    monkeypatch.setattr(bot, "bot_activo", lambda: False)
    monkeypatch.setattr(bot, "unico", lambda n: pytest.fail("no debe ni coger el candado"))
    assert bot.main() is None
