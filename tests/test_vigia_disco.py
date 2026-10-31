"""T708: aviso si un log de registros/ crece de forma anormal o el disco libre baja de un umbral."""

import json
from collections import namedtuple

from nucleo import avisos, vigia_disco

Uso = namedtuple("Uso", "total used free")
GB = 1024 ** 3


def _avisos(tmp_path):
    return [json.loads(p.read_text(encoding="utf-8")) for p in (tmp_path / "av").glob("*.json") if not p.name.startswith("_")]


def _preparar(tmp_path, monkeypatch):
    monkeypatch.setattr(avisos, "CARPETA", tmp_path / "av")
    reg = tmp_path / "registros"
    reg.mkdir()
    return reg


def test_log_por_encima_del_tope_avisa(tmp_path, monkeypatch):
    reg = _preparar(tmp_path, monkeypatch)
    (reg / "pequeno.log").write_text("x", encoding="utf-8")
    grande = reg / "guardia_vault.log"
    grande.write_text("x", encoding="utf-8")
    real = type(grande).stat

    def stat(self, *a, **k):
        r = real(self, *a, **k)
        if self.name == "guardia_vault.log":
            return type("S", (), {"st_size": 3 * GB, "st_mode": r.st_mode})()
        return r

    monkeypatch.setattr(type(grande), "stat", stat)
    monkeypatch.setattr(vigia_disco.shutil, "disk_usage", lambda p: Uso(900 * GB, 400 * GB, 500 * GB))
    r = vigia_disco.revisar(reg, tope_log=1 * GB, umbral_libre=20 * GB)

    assert [n for n, _ in r["logs_grandes"]] == ["guardia_vault.log"]
    assert r["disco_bajo"] is False
    av = _avisos(tmp_path)
    assert len(av) == 1 and "guardia_vault.log" in av[0]["titulo"] + av[0]["cuerpo"]


def test_disco_con_poco_espacio_avisa(tmp_path, monkeypatch):
    reg = _preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(vigia_disco.shutil, "disk_usage", lambda p: Uso(900 * GB, 890 * GB, 10 * GB))
    r = vigia_disco.revisar(reg, tope_log=1 * GB, umbral_libre=20 * GB)
    assert r["disco_bajo"] is True and r["libre"] == 10 * GB
    assert len(_avisos(tmp_path)) == 1


def test_todo_normal_no_avisa_y_no_repite_el_aviso(tmp_path, monkeypatch):
    reg = _preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(vigia_disco.shutil, "disk_usage", lambda p: Uso(900 * GB, 400 * GB, 500 * GB))
    assert vigia_disco.revisar(reg, tope_log=1 * GB, umbral_libre=20 * GB)["logs_grandes"] == []
    assert _avisos(tmp_path) == []
    monkeypatch.setattr(vigia_disco.shutil, "disk_usage", lambda p: Uso(900 * GB, 890 * GB, 10 * GB))
    vigia_disco.revisar(reg, tope_log=1 * GB, umbral_libre=20 * GB, ahora=1000.0)
    vigia_disco.revisar(reg, tope_log=1 * GB, umbral_libre=20 * GB, ahora=1060.0)
    assert len(_avisos(tmp_path)) == 1


def test_un_fallo_al_mirar_no_rompe_el_tick(tmp_path, monkeypatch):
    reg = _preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(vigia_disco.shutil, "disk_usage", lambda p: (_ for _ in ()).throw(OSError("x")))
    r = vigia_disco.revisar(reg / "no_existe", tope_log=1 * GB, umbral_libre=20 * GB)
    assert r["libre"] is None and r["logs_grandes"] == []
