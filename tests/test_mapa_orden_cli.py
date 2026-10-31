# -*- coding: utf-8 -*-
"""nucleo/mapa.py y nucleo/orden_cli.py: sin ninguna prueba hasta ahora.

mapa: CLAUDE.md manda consultarlo antes de trabajar un tema, asi que sus IDs tienen que
existir de verdad. Se comprueba LEYENDO memoria/tareas.json y memoria/catalogo.json (solo
lectura) y el resto con dobles en tmp_path.
orden_cli: el script que lanzan /orden del bot y la web; se ejecuta con runpy y dobles.
"""
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

from nucleo import mapa

RAIZ = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ mapa

def test_ver_tambien_apunta_a_temas_que_existen():
    for nombre, info in mapa.TEMAS.items():
        for otro in info["ver_tambien"]:
            assert otro in mapa.TEMAS, f"{nombre} -> {otro}"
            assert otro != nombre


def _tareas_reales() -> list[dict]:
    """Las tareas REALES (vivas de tareas.json y, desde T1010, cerradas del historial), leidas sin pasar por la
    API (el fixture autouse redirige el almacen de la API a tmp_path)."""
    from nucleo import tarea_v2, tareas_almacen
    real = RAIZ / "memoria" / "tareas.json"
    vivas = json.loads(real.read_text(encoding="utf-8"))["tareas"]
    return [tarea_v2.de_disco(r) for r in vivas + tareas_almacen.leer_historial(real)[1]]


def test_ids_de_tareas_del_mapa_existen_en_tareas_json():
    ids = {t["id"] for t in _tareas_reales()}
    faltan = {n: [i for i in info["tareas"].split() if i not in ids] for n, info in mapa.TEMAS.items()}
    assert not {n: f for n, f in faltan.items() if f}


def test_ids_del_catalogo_del_mapa_existen_en_catalogo_json():
    ids = {x["id"] for x in json.loads((RAIZ / "memoria" / "catalogo.json").read_text(encoding="utf-8"))["items"]}
    faltan = {n: [i for i in info["catalogo"].split() if i not in ids] for n, info in mapa.TEMAS.items()}
    assert not {n: f for n, f in faltan.items() if f}


@pytest.fixture
def almacenes(tmp_path, monkeypatch):
    """tareas.json y catalogo.json de juguete en tmp_path (nunca los de memoria/)."""
    from nucleo import catalogo, tareas
    tj = tmp_path / "tareas.json"
    cj = tmp_path / "catalogo.json"
    # Copia de dos tareas REALES (esquema completo), con etiquetas controladas.
    reales = {t["id"]: t for t in _tareas_reales()}
    t134 = dict(reales["T134"], etiquetas=[])
    t079 = dict(reales["T079"], etiquetas=["tema:orquestacion"])
    tj.write_text(json.dumps({"version": 1, "siguiente_id": 999, "tareas": [t134, t079]}), encoding="utf-8")
    cj.write_text(json.dumps({"version": 1, "actualizado": "", "items": [
        {"id": "H041", "nombre": "Herramienta", "veredicto": "adoptar", "auditado": "no"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(tareas, "ALMACEN", tj)
    monkeypatch.setattr(tareas, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(tareas, "VISTA_VAULT", tmp_path / "vault.md")
    monkeypatch.setattr(tareas, "CANDADO", tmp_path / ".candado_tareas.lock")
    monkeypatch.setattr(catalogo, "ALMACEN", cj)
    monkeypatch.setattr(catalogo, "CANDADO", tmp_path / ".candado_catalogo.lock")
    monkeypatch.setattr(catalogo, "VISTA", tmp_path / "catalogo.md")
    # buscar() de tareas cae a buscar por titulo si no encuentra el ID: aqui no hay titulos con IDs.
    return tj, cj


def test_tema_lista_tareas_y_catalogo_con_su_estado(almacenes):
    texto = mapa.tema("modelos_proveedores_roles")
    assert "T134 [" in texto
    assert "H041 [adoptar/no] Herramienta" in texto
    assert "Ver tambien: orquestacion, ahorro_claude_dev" in texto


def test_tema_inexistente_lanza_keyerror():
    with pytest.raises(KeyError):
        mapa.tema("no_existe")


def test_aplicar_etiqueta_sin_duplicar(almacenes):
    tj, cj = almacenes
    nt, nc = mapa.aplicar()
    datos = json.loads(tj.read_text(encoding="utf-8"))
    t134 = next(t for t in datos["tareas"] if t["id"] == "T134")
    t079 = next(t for t in datos["tareas"] if t["id"] == "T079")
    assert "tema:modelos_proveedores_roles" in t134["etiquetas"]
    assert t079["etiquetas"].count("tema:orquestacion") == 1
    assert json.loads(cj.read_text(encoding="utf-8"))["items"][0]["categoria"] == "modelos_proveedores_roles"
    assert nt == 1
    nt2, _ = mapa.aplicar()
    assert nt2 == 0


# ------------------------------------------------------------- orden_cli

@pytest.fixture
def orden_cli(monkeypatch):
    from canal import buzon
    from nucleo import ordenes
    llamadas = {"procesar": [], "avisar": []}

    def procesar(texto, canal="telegram"):
        llamadas["procesar"].append((texto, canal))
        return {"respuesta": f"ok: {texto}"} if texto else {"estado": "VACIA"}

    monkeypatch.setattr(ordenes, "procesar", procesar)
    monkeypatch.setattr(buzon, "avisar", lambda texto, **k: llamadas["avisar"].append((texto, k)))

    def correr(*args):
        monkeypatch.setattr(sys, "argv", ["orden_cli.py", *args])
        runpy.run_module("nucleo.orden_cli", run_name="__main__")
        return llamadas

    return correr


def test_orden_cli_por_defecto_telegram_y_silencioso(orden_cli):
    ll = orden_cli("resume", "esto")
    assert ll["procesar"] == [("resume esto", "telegram")]
    assert ll["avisar"] == [("[telegram] ok: resume esto", {"silencioso": True})]


def test_orden_cli_con_canal_web(orden_cli):
    ll = orden_cli("--canal=web", "haz", "algo")
    assert ll["procesar"] == [("haz algo", "web")]
    assert ll["avisar"][0][0].startswith("[web] ok: haz algo")


def test_orden_cli_sin_respuesta_avisa_con_el_dict(orden_cli):
    ll = orden_cli()
    assert ll["avisar"][0][0] == "[telegram] {'estado': 'VACIA'}"
