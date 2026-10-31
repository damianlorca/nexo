# -*- coding: utf-8 -*-
"""T1039 (25/10): tribunal, chat de tareas, chat de aprobaciones e implementador leen el primer modelo VIVO de config
nvidia.modelos (ultra el primero); ninguno lleva escrito a mano nemotron-3-super-120b (404 desde el 21/10)."""
from pathlib import Path

import proveedores as P
from nucleo import modelos_estado

RAIZ = Path(__file__).resolve().parent.parent
SUPER = "nemotron-3-super-120b"


def test_ningun_consumidor_lleva_el_modelo_retirado_a_mano():
    for r in ("nucleo/tribunal.py", "nucleo/chat_tarea.py", "nucleo/chat_aprobacion.py", "nucleo/implementador.py"):
        codigo = [l for l in (RAIZ / r).read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#")]
        assert not [l for l in codigo if SUPER in l or "nemotron-3-ultra" in l], r


def test_principal_es_el_primero_de_la_config_y_salta_los_muertos():
    lista = P.modelos_nvidia_config()
    assert lista[0] == "nvidia/nemotron-3-ultra-550b-a55b" and all(m in P.MODELOS_NVIDIA_GRATIS for m in lista)
    assert P.modelo_nvidia_principal() == lista[0]
    modelos_estado.anotar("nvidia", lista[0], 404)
    modelos_estado.anotar("nvidia", lista[0], 404)
    assert modelos_estado.fuera_de_uso("nvidia", lista[0])
    assert P.modelo_nvidia_principal() == lista[1]


def test_id_corto_conserva_el_id_de_siempre():
    assert P.id_corto_nvidia("nvidia/nemotron-3-ultra-550b-a55b") == "nvidia:nemotron-3-ultra"
    assert P.id_corto_nvidia("nvidia/nemotron-3.5-lightning-30b-a3b") == "nvidia:nemotron-3.5-lightning"
    assert P.id_corto_nvidia("minimaxai/minimax-m3.1-flash") == "nvidia:minimax-m3.1-flash"


def test_los_cuatro_consumidores_usan_el_principal(monkeypatch):
    from nucleo import chat_aprobacion, chat_tarea, implementador as I, tribunal
    lista = P.modelos_nvidia_config()
    assert tribunal._NVIDIA.modelo == lista[0] and tribunal._NVIDIA in tribunal.TRIBUNAL
    assert tribunal._NVIDIA_B.modelo == lista[1] and tribunal._NVIDIA_B in tribunal.APELACION
    assert [m for m in I.MODELOS if m.proveedor == "nvidia"] == [I._nvidia(lista[0])]
    monkeypatch.setattr(P, "modelo_nvidia_principal", lambda: "minimaxai/minimax-m3.1-flash")
    assert chat_tarea.proveedores_dudas()[0].modelos == ("minimaxai/minimax-m3.1-flash",)
    assert chat_aprobacion.proveedores()[0].modelos == ("minimaxai/minimax-m3.1-flash",)
    nv = [m for m in I.modelos_programar() if m.proveedor == "nvidia"]
    assert nv == [I.Modelo("nvidia:minimax-m3.1-flash", "nvidia", "openai/minimaxai/minimax-m3.1-flash", "nvidia")]


def test_asignar_no_elige_un_retirado():
    from nucleo import banco_modelos as B
    fila = {"calidad": 0.9, "exito": 1.0, "fiabilidad": 1.0, "mediana_s": 1.0, "casos": 1, "de": 1, "pasadas": 4,
            "puntos": 0.95, "verdes": 0}
    tabla = {"revisar": {"groq:a": dict(fila, puntos=0.99), f"nvidia:nvidia/{SUPER}-a12b": fila,
                         "nvidia:nvidia/otro": dict(fila, puntos=0.9)}}
    assert B.asignar(tabla)["revisar"]["reserva"] == f"nvidia:nvidia/{SUPER}-a12b"
    modelos_estado.anotar("nvidia", f"nvidia/{SUPER}-a12b", 410)
    modelos_estado.anotar("nvidia", f"nvidia/{SUPER}-a12b", 410)
    assert B.asignar(tabla)["revisar"]["reserva"] == "nvidia:nvidia/otro"
