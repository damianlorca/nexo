# -*- coding: utf-8 -*-
"""Incremento 3: vigilancia de ficheros del core -> eventos (parada, tareas, logs, borradores)."""
from __future__ import annotations

import json
import os

from interfaz.eventos import Bus
from interfaz.vigilancia import Vigilante
from nucleo import parada, registro, tareas, trabajo


def _vig():
    v = Vigilante(Bus())
    assert v.revisar() == []  # foto inicial: nunca emite
    return v


def _anadir_lineas(ruta, *lineas):
    with ruta.open("a", encoding="utf-8") as f:
        for linea in lineas:
            f.write(linea + "\n")


def test_parada_desde_fuera_emite_evento_on_y_off():
    v = _vig()
    parada.activar("desde telegram", "telegram")
    assert v.revisar() == [("parada", {"activa": True, "motivo": "desde telegram"})]
    assert v.revisar() == []  # sin cambios, nada
    parada.desactivar()
    assert v.revisar() == [("parada", {"activa": False, "motivo": ""})]


def test_tareas_por_mtime():
    tareas.anadir("previa")
    v = _vig()
    tareas.anadir("nueva")
    st = tareas.ALMACEN.stat()
    os.utime(tareas.ALMACEN, (st.st_atime, st.st_mtime + 5))  # por si el reloj no avanza entre escrituras
    assert ("tareas", {}) in v.revisar()


def test_logs_solo_lineas_nuevas_y_completas():
    trazas = registro.CARPETA / "trazas.jsonl"
    _anadir_lineas(trazas, json.dumps({"evento": "viejo"}))
    v = _vig()
    _anadir_lineas(trazas, json.dumps({"evento": "nuevo"}), "texto no json")
    with trazas.open("a", encoding="utf-8") as f:
        f.write('{"evento": "a medias"')  # sin salto: aun no se emite
    eventos = v.revisar()
    assert eventos == [("log", {"fuente": "trazas", "linea": {"evento": "nuevo"}}),
                       ("log", {"fuente": "trazas", "linea": {"texto": "texto no json"}})]
    with trazas.open("a", encoding="utf-8") as f:
        f.write("}\n")
    assert v.revisar() == [("log", {"fuente": "trazas", "linea": {"evento": "a medias"}})]


def test_log_que_aparece_despues_se_lee_desde_el_principio():
    v = _vig()
    _anadir_lineas(registro.CARPETA / "evidencia.jsonl", json.dumps({"fase": "tool"}))
    assert v.revisar() == [("log", {"fuente": "evidencia", "linea": {"fase": "tool"}})]


def test_log_truncado_vuelve_a_empezar():
    uso = registro.CARPETA / "uso_proveedores.jsonl"
    _anadir_lineas(uso, json.dumps({"proveedor": "qwen"}) * 3)
    v = _vig()
    uso.write_text(json.dumps({"proveedor": "groq"}) + "\n", encoding="utf-8")
    assert v.revisar() == [("log", {"fuente": "uso_proveedores", "linea": {"proveedor": "groq"}})]


def test_linea_enorme_se_recorta():
    v = _vig()
    _anadir_lineas(registro.CARPETA / "trazas.jsonl", "x" * 20000)
    (_, datos), = v.revisar()
    assert datos["linea"]["recortada"] is True and len(datos["linea"]["texto"]) <= 8001


def test_borrador_nuevo():
    (trabajo.BORRADORES / "T001_viejo.md").write_text("a", encoding="utf-8")
    v = _vig()
    (trabajo.BORRADORES / "T002_nuevo.md").write_text("b", encoding="utf-8")
    assert v.revisar() == [("borrador", {"nombre": "T002_nuevo.md"})]


def test_fallo_en_una_comprobacion_no_pierde_los_eventos_de_las_demas(monkeypatch):
    v = _vig()
    parada.activar("telegram", "telegram")

    def rompe():
        raise PermissionError("bloqueado")
    monkeypatch.setattr(v, "_revisar_logs", rompe)
    assert ("parada", {"activa": True, "motivo": "telegram"}) in v.revisar()


def test_linea_mayor_que_la_pasada_no_atasca_el_log(monkeypatch):
    import interfaz.vigilancia as vig
    monkeypatch.setattr(vig, "MAX_BYTES_PASADA", 100)
    v = _vig()
    trazas = registro.CARPETA / "trazas.jsonl"
    _anadir_lineas(trazas, "y" * 250, json.dumps({"evento": "despues"}))
    eventos = []
    for _ in range(6):
        eventos += v.revisar()
    assert eventos[0][1]["linea"].get("texto", "").startswith("yyy")
    assert eventos[-1] == ("log", {"fuente": "trazas", "linea": {"evento": "despues"}})
    assert len(eventos) == 2
