# -*- coding: utf-8 -*-
"""T189: la delegacion bloqueada por el auditor y el aviso de modo se ven en la web y llegan por push."""
from __future__ import annotations

import json

from interfaz.eventos import Bus
from interfaz.vigilancia import Vigilante
from nucleo import auditor, avisos, trabajo

PUNTOS_MAL = {"a_modo": {"ok": True, "detalle": "2 llamadas web con el modo comprobado"},
              "d_revision": {"ok": False, "detalle": "ninguna revision valida de otra familia"}}


def _auditoria(resultado="BLOQUEADA", tarea="T901", borrador="T901_20260927_1500.md"):
    exp = {"tarea": tarea, "titulo": "Investigar X", "archivo": f"memoria/borradores/{borrador}", "llamadas": []}
    fallos = [k for k, v in PUNTOS_MAL.items() if not v["ok"]] if resultado == "BLOQUEADA" else []
    return auditor.registrar(exp, {"resultado": resultado, "fallos": fallos, "puntos": PUNTOS_MAL})


def test_el_centro_tiene_el_panel_de_auditoria(cliente, csrf):
    r = cliente.get("/tecnico")
    assert 'hx-get="/centro/auditoria"' in r.text and "nexo:aviso from:body" in r.text


def test_panel_muestra_la_bloqueada_primero_con_su_fallo(cliente, csrf):
    _auditoria("BLOQUEADA", "T901")
    _auditoria("APROBADA", "T902", "T902_20260927_1501.md")
    r = cliente.get("/centro/auditoria")
    assert r.status_code == 200
    assert "1 delegación BLOQUEADA" in r.text
    assert r.text.index("T901") < r.text.index("T902")
    assert "falla d_revision: ninguna revision valida de otra familia" in r.text
    assert "/borrador?f=T901_20260927_1500.md" in r.text


def test_panel_vacio(cliente, csrf):
    r = cliente.get("/centro/auditoria")
    assert "Todavía no hay delegaciones auditadas." in r.text


def test_la_bloqueada_deja_un_aviso_que_sale_en_el_panel(cliente, csrf):
    _auditoria("BLOQUEADA", "T901")
    [aviso] = avisos.recientes()
    assert aviso["tipo"] == "auditoria" and aviso["ruta"] == "/borrador?f=T901_20260927_1500.md"
    assert "delegación BLOQUEADA" in cliente.get("/centro/auditoria").text


def test_la_aprobada_no_avisa():
    _auditoria("APROBADA")
    assert avisos.recientes() == []


def test_el_borrador_ensena_su_auditoria(cliente, csrf):
    (trabajo.BORRADORES / "T901_20260927_1500.md").write_text("# T901\ntexto", encoding="utf-8")
    _auditoria("BLOQUEADA", "T901")
    r = cliente.get("/borrador?f=T901_20260927_1500.md")
    assert r.status_code == 200
    assert "Auditoría:" in r.text and "BLOQUEADA" in r.text and "FALLA" in r.text


def test_vigilancia_convierte_un_aviso_nuevo_en_evento():
    v = Vigilante(Bus())
    assert v.revisar() == []   # foto inicial
    avisos.emitir("modo", "Ningún proveedor consigue el modo Pensar/Pro", "detalle", ruta="/logs", clave="modo:todos")
    eventos = [e for e in v.revisar() if e[0] == "aviso"]
    assert len(eventos) == 1 and eventos[0][1]["tipo"] == "modo" and eventos[0][1]["ruta"] == "/logs"
    assert [e for e in v.revisar() if e[0] == "aviso"] == []   # no se repite


def test_los_avisos_de_antes_de_arrancar_no_se_reenvian():
    avisos.emitir("modo", "viejo", "x", clave="k1")
    v = Vigilante(Bus())
    v.revisar()
    assert [e for e in v.revisar() if e[0] == "aviso"] == []


def test_push_traduce_el_aviso_con_urgencia_alta():
    from interfaz.push import Almacen, Notificador
    n = Notificador(Almacen.__new__(Almacen), enviar=lambda *a: 201)
    datos = {"tipo": "auditoria", "titulo": "T901: delegación BLOQUEADA por el auditor", "cuerpo": "d_revision: x",
             "ruta": "/borrador?f=T901_x.md", "clave": "auditoria:T901_x.json", "nombre": "aviso_1.json"}
    aviso = n.aviso_de("aviso", datos)
    assert aviso["urgencia"] == "high" and aviso["ruta"] == "/borrador?f=T901_x.md" and "BLOQUEADA" in aviso["titulo"]
    assert n.aviso_de("aviso", datos) is None                                  # una sola vez
    raro = n.aviso_de("aviso", dict(datos, nombre="aviso_2.json", ruta="https://fuera.example"))
    assert raro["ruta"] == "/"                                                   # nunca un enlace externo
    n._ejecutor.shutdown(wait=False)


def test_la_bloqueada_revisada_por_claude_deja_de_avisar(cliente, csrf):
    ruta = _auditoria("BLOQUEADA", "T901")
    _auditoria("BLOQUEADA", "T903", "T903_20260927_1502.md")
    assert "2 delegaciones BLOQUEADAS" in cliente.get("/centro/auditoria").text
    auditor.resolver(ruta.name, "APROBADO", "el ESCALAR era un falso positivo del revisor")
    r = cliente.get("/centro/auditoria").text
    assert "1 delegación BLOQUEADA" in r
    assert "revisada por Claude: <strong>APROBADO</strong>" in r
    assert "T903: delegación BLOQUEADA" in r and "T901: delegación BLOQUEADA" not in r   # su aviso ya no sale
    assert r.index("T903") < r.index("T901")                                            # la revisada, al final


def test_resolver_exige_motivo_y_no_toca_las_aprobadas():
    import pytest
    ruta = _auditoria("APROBADA", "T902", "T902_20260927_1501.md")
    with pytest.raises(ValueError):
        auditor.resolver(ruta.name, "APROBADO", "motivo suficiente de verdad")
    ruta = _auditoria("BLOQUEADA", "T901")
    with pytest.raises(ValueError):
        auditor.resolver(ruta.name, "APROBADO", "corto")
    assert json.loads(ruta.read_text(encoding="utf-8"))["resultado"] == "BLOQUEADA"   # la evidencia no cambia
