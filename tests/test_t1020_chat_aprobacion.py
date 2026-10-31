# -*- coding: utf-8 -*-
"""T1020 pieza 3: minichat de una solicitud de la cola (nucleo/chat_aprobacion.py). Sin red: proveedores de pega."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo import aprobaciones as ap
from nucleo import chat_aprobacion as CA
from nucleo import guardian as G


class Falso:
    def __init__(self, nombre, texto="", ok=True, disponible=True):
        self.nombre, self._texto, self._ok, self._disp = nombre, texto, ok, disponible
        self.prompts = []

    def disponible(self):
        return self._disp

    def enviar(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(ok=self._ok, texto=self._texto, estado="ok" if self._ok else "error", meta={})


@pytest.fixture
def cola(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "ALMACEN", tmp_path / "aprobaciones.json")
    monkeypatch.setattr(ap, "HISTORIAL", tmp_path / "aprobaciones_historial.jsonl")
    monkeypatch.setattr(ap, "CANDADO", tmp_path / ".candado_aprobaciones.lock")
    monkeypatch.setattr(CA, "CARPETA", tmp_path / "chats_aprobaciones")
    monkeypatch.setattr(G, "GANCHO", True)
    from nucleo import parada
    monkeypatch.setattr(parada, "BANDERA", tmp_path / "PARADA_NEXO")
    return tmp_path


def _provs(monkeypatch, *provs, qwen=None):
    monkeypatch.setattr(CA, "proveedores", lambda: list(provs))
    q = qwen or Falso("qwen", "respuesta local")
    monkeypatch.setattr(CA, "_qwen", lambda: q)
    return q


def test_contesta_nvidia_con_solo_esa_solicitud_y_su_ficha(cola, monkeypatch):
    otra = ap.solicitar("ejecutar comando", "Remove-Item documentacion\\otra_cosa.md", origen="mcp")
    s = ap.solicitar("ejecutar comando", "Remove-Item " + str(G.RAIZ / "documentacion" / "notas.md"), origen="mcp",
                     extra={"motivo": "limpiar"})
    nv = Falso("nvidia", "Quiere borrar una nota; no hay copia.")
    _provs(monkeypatch, nv, Falso("groq", "x"))
    nuevas = CA.preguntar(s["id"], "¿Se puede recuperar?")
    assert [x["tipo"] for x in nuevas] == ["mensaje", "respuesta"] and nuevas[1]["quien"] == "nvidia"
    p = nv.prompts[0]
    assert "¿Se puede recuperar?" in p and "SE PUEDE DESHACER: No" in p and "PARA QUE: limpiar" in p
    assert "otra_cosa" not in p and otra["id"] not in p                     # solo ESA solicitud
    assert "users" not in p.lower()                                          # auditor.tapar
    assert "no decides ni haces nada" in p.lower().replace("tu ", "")
    assert [x["n"] for x in CA.historial(s["id"])] == [1, 2]
    CA.preguntar(s["id"], "¿Y si digo que no?")
    assert "Quiere borrar una nota" in nv.prompts[1]                         # recuerda la conversacion


def test_reserva_groq_y_al_final_qwen(cola, monkeypatch):
    s = ap.solicitar("ejecutar comando", "Remove-Item documentacion\\x.md", origen="mcp")
    _provs(monkeypatch, Falso("nvidia", ok=False), Falso("groq", "desde groq"))
    assert CA.preguntar(s["id"], "hola")[1]["quien"] == "groq"
    _provs(monkeypatch, Falso("nvidia", ok=False), Falso("groq", disponible=False), Falso("gemini_api", ok=False))
    assert CA.preguntar(s["id"], "hola")[1]["quien"] == "qwen"
    _provs(monkeypatch, qwen=Falso("qwen", ok=False))
    r = CA.preguntar(s["id"], "hola")[1]
    assert r["error"] and "Escalar" in r["texto"]


def test_escalar_no_llama_a_nadie_y_claude_contesta(cola, monkeypatch):
    s = ap.solicitar("ejecutar comando", "Remove-Item documentacion\\x.md", origen="mcp")
    monkeypatch.setattr(CA, "proveedores", lambda: pytest.fail("no debe llamar a ninguna IA"))
    nuevas = CA.preguntar(s["id"], "¿Esto lo pidió Claude?", escalar=True)
    assert nuevas[1]["tipo"] == "escalado"
    assert CA.escalados() == [{"solicitud": s["id"], "n": 1, "cuando": nuevas[1]["cuando"],
                               "pregunta": "¿Esto lo pidió Claude?"}]
    CA.responder_claude(s["id"], 1, "Sí, para limpiar notas.")
    assert CA.escalados() == []
    with pytest.raises(CA.ChatRechazado):
        CA.responder_claude(s["id"], 7, "x")


def test_parada_y_peticiones_invalidas(cola, monkeypatch):
    s = ap.solicitar("ejecutar comando", "Remove-Item documentacion\\x.md", origen="mcp")
    (cola / "PARADA_NEXO").write_text("x", encoding="utf-8")
    monkeypatch.setattr(CA, "proveedores", lambda: pytest.fail("con PARADA no se pregunta a nadie"))
    assert "PARADA" in CA.preguntar(s["id"], "hola")[1]["texto"]
    for id_, texto in ((s["id"], "  "), ("../x", "hola"), ("A9999", "hola"), (s["id"], "x" * 3000)):
        with pytest.raises(CA.ChatRechazado):
            CA.preguntar(id_, texto)


def test_si_lleva_algo_privado_solo_contesta_qwen_local(cola, monkeypatch):
    s = ap.solicitar("ejecutar comando", "Get-Content memoria\\perfil_privado\\perfil.md", origen="mcp")
    q = _provs(monkeypatch, Falso("nvidia", "no deberia"))
    monkeypatch.setattr("nucleo.auditor.motivos_privados", lambda t: ["perfil privado"])
    r = CA.preguntar(s["id"], "¿qué lee?")[1]
    assert r["quien"] == "qwen" and r["solo_local"] == "perfil privado" and q.prompts
