# -*- coding: utf-8 -*-
"""T078: uso de Claude por sesion de Code y por tarea, leido de transcripts sinteticos."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from nucleo import uso_claude as U


def _usage(entrada=10, c5=0, c1=100, lectura=1000, salida=50):
    return {"input_tokens": entrada, "cache_creation_input_tokens": c5 + c1, "cache_read_input_tokens": lectura,
            "output_tokens": salida,
            "cache_creation": {"ephemeral_5m_input_tokens": c5, "ephemeral_1h_input_tokens": c1}}


def _asistente(req, cuando, usage, modelo="claude-opus-5-5", esfuerzo="medium", comando=None):
    contenido = [{"type": "text", "text": "hola"}]
    if comando:
        contenido = [{"type": "tool_use", "name": "Bash", "input": {"command": comando}}]
    return {"type": "assistant", "requestId": req, "timestamp": cuando, "effort": esfuerzo,
            "message": {"id": "m" + req, "model": modelo, "usage": usage, "content": contenido}}


def _escribir(ruta: Path, lineas: list[dict]) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(json.dumps(x) for x in lineas) + "\n{roto\n", encoding="utf-8")
    return ruta


def test_una_peticion_repetida_por_bloques_cuenta_una_vez(tmp_path):
    u = _usage()
    ruta = _escribir(tmp_path / "s1.jsonl", [
        {"type": "custom-title", "customTitle": "Mi sesion"},
        _asistente("r1", "2026-09-27T10:00:00Z", u),
        _asistente("r1", "2026-09-27T10:00:01Z", u),   # mismo requestId, otro bloque
        _asistente("r2", "2026-09-27T11:00:00Z", u, esfuerzo="high"),
        {"type": "assistant", "requestId": "r3", "message": {"model": "<synthetic>", "usage": u}},
    ])
    s = U.leer_sesion(ruta)
    m = s["modelos"]["claude-opus-5-5"]
    assert (m["peticiones"], m["entrada"], m["cache_1h"], m["cache_lectura"], m["salida"]) == (2, 20, 200, 2000, 100)
    assert s["titulo"] == "Mi sesion" and s["esfuerzos"] == {"medium": 1, "high": 1}
    assert s["sesion"] == "s1" and s["inicio"] < s["fin"]


def test_ponderado_usa_los_multiplicadores_de_precio():
    u = {"entrada": 100, "cache_5m": 100, "cache_1h": 100, "cache_lectura": 1000, "salida": 100}
    assert U.ponderado(u) == 100 + 125 + 200 + 100 + 500


def test_tareas_salen_de_commits_y_del_cli_de_tareas(tmp_path):
    ruta = _escribir(tmp_path / "s2.jsonl", [
        _asistente("r1", "2026-09-27T10:00:00Z", _usage(),
                   comando='git add x && git commit -q -m "T005: algo\n\nmenciona T999 en el cuerpo"'),
        _asistente("r2", "2026-09-27T10:05:00Z", _usage(), comando=".venv/Scripts/python.exe -m nucleo.tareas hecha T078 'x'"),
        _asistente("r3", "2026-09-27T10:06:00Z", _usage(), comando="git log --oneline -1  # T123 no cuenta"),
    ])
    assert U.leer_sesion(ruta)["tareas"] == ["T005", "T078"]


def test_subagentes_suman_a_su_sesion(tmp_path):
    ruta = _escribir(tmp_path / "s3.jsonl", [_asistente("r1", "2026-09-27T10:00:00Z", _usage())])
    _escribir(tmp_path / "s3" / "subagents" / "a.jsonl",
              [_asistente("r9", "2026-09-27T10:01:00Z", _usage(), modelo="claude-sonnet-5")])
    s = U.leer_sesion(ruta)
    assert set(s["modelos"]) == {"claude-opus-5-5", "claude-sonnet-5"}


def test_sesion_sin_peticiones_no_cuenta(tmp_path):
    assert U.leer_sesion(_escribir(tmp_path / "vacia.jsonl", [{"type": "user"}])) is None


def test_actualizar_conserva_sesiones_cuyo_transcript_ya_no_existe(tmp_path):
    reg = tmp_path / "uso_claude.jsonl"
    a = _escribir(tmp_path / "a.jsonl", [_asistente("r1", "2026-09-20T10:00:00Z", _usage())])
    assert U.actualizar(reg, [a]) == 1
    a.unlink()
    b = _escribir(tmp_path / "b.jsonl", [_asistente("r2", "2026-09-27T10:00:00Z", _usage())])
    assert U.actualizar(reg, [b]) == 2
    assert set(U.cargar(reg)) == {"a", "b"}
    assert U.actualizar(reg, [b]) == 2   # releer no duplica


def test_por_tarea_reparte_la_sesion_entre_sus_tareas():
    s = {"sesion": "x", "inicio": "2026-09-27T10:00:00", "tareas": ["T001", "T002"],
         "modelos": {"opus": {"entrada": 1000, "cache_5m": 0, "cache_1h": 0, "cache_lectura": 0, "salida": 0,
                              "peticiones": 1}}}
    r = U.por_tarea([s])
    assert r["T001"] == {"sesiones": 1, "ponderado": {"opus": 500}} and r["T002"]["ponderado"]["opus"] == 500


def test_comparar_antes_y_despues():
    def ses(dia, n):
        return {"sesion": dia, "inicio": f"{dia}T10:00:00", "tareas": [],
                "modelos": {"opus": {"entrada": n, "cache_5m": 0, "cache_1h": 0, "cache_lectura": 0, "salida": 0,
                                     "peticiones": n}}}
    c = U.comparar(date(2026, 9, 28), 2, [ses("2026-09-26", 40), ses("2026-09-27", 60), ses("2026-09-28", 10),
                                          ses("2026-09-25", 999), ses("2026-09-30", 999)])
    assert c["antes"]["sesiones"] == 2 and c["antes"]["modelos"]["opus"]["peticiones_dia"] == 50
    assert c["despues"]["sesiones"] == 1 and c["despues"]["modelos"]["opus"]["ponderado_dia"] == 5


def test_carpeta_de_proyecto_y_worktrees(tmp_path):
    raiz = Path("C:/Users/x/agente")
    base = U.carpeta_proyecto(raiz)
    assert base == "C--Users-x-agente"
    for nombre in (base, base + "--claude-worktrees-w1", "C--Users-x-otro"):
        _escribir(tmp_path / nombre / "s.jsonl", [])
    encontrados = {p.parent.name for p in U.transcripts(raiz, tmp_path)}
    assert encontrados == {base, base + "--claude-worktrees-w1"}
