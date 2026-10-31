# -*- coding: utf-8 -*-
"""T1024 (19/10): el turno "modelos" (tope 45 min) duro 70. El banco no miraba el tope ni el "Parar", y el
planificador, a tope + 15 min, borraba turno_en_marcha.json y dejaba el proceso suelto (sin registro y con la cola
libre). Ahora: el banco para antes de pasarse; el planificador nunca suelta un turno vivo, le pide que acabe a tope +
margen y, si no obedece, lo cierra por su PID EXACTO (linea comprobada, hijos listados antes del /T); si no puede,
avisa en el Centro. Sin procesos reales: dobles de _vivo, _linea_de_comando, _procesos y _matar."""
from __future__ import annotations

import json
import time
from datetime import datetime

import pytest

from nucleo import avisos, banco_modelos as B, parada, registro
from nucleo import planificador as P
from nucleo import turnos

PID = 4242
RAIZ = str(P.RAIZ)
LUNES = datetime(2026, 10, 19, 9, 10, 0)


def _turno(**campos):
    base = {"nombre": "Banco de modelos", "plantilla": "modelos", "dias": list(turnos.DIAS), "horas": ["03:30"],
            "max_minutos": 45}
    return turnos.guardar_turno(dict(base, **campos))


def _en_marcha(t, hace_s, **extra):
    P.progreso(pid_turno=PID, turno=t["id"], nombre=t["nombre"], max_minutos=t["max_minutos"],
               inicio="2026-10-19T08:09:52", lanzado=time.time() - hace_s, **extra)


def _linea(t):
    return f"C:\\agente\\.venv\\Scripts\\python.exe C:\\agente\\turno_nexo.py --turno={t['id']} --arrancar-chrome"


def _registros():
    return sorted(registro.CARPETA.glob("turno_nexo_*.json"))


def _avisos():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(avisos.CARPETA.glob("aviso_*.json"))]


@pytest.fixture(autouse=True)
def carpeta_parada():
    parada.CIERRE.parent.mkdir(parents=True, exist_ok=True)   # en el PC, memoria/ siempre existe


@pytest.fixture
def vivo(monkeypatch):
    """El turno sigue vivo hasta que _matar lo cierra (o para siempre, si `muere` es False)."""
    estado = {"muertos": [], "muere": True}

    def matar(pid):
        estado["muertos"].append(pid)
    monkeypatch.setattr(P, "_vivo", lambda pid: pid == PID and not (estado["muertos"] and estado["muere"]))
    monkeypatch.setattr(P, "_matar", matar)
    return estado


# ------------------------------------------------------------------ el planificador ya no suelta un turno vivo
def test_turno_vivo_pasado_su_tope_no_pierde_su_registro_y_se_le_pide_que_acabe(vivo):
    t = _turno()
    _en_marcha(t, (45 + 16) * 60)                                     # 09:10 del 19/10: tope + 16 min
    assert P.en_marcha()["turno"] == t["id"] and P.EN_MARCHA.exists()   # antes: None y fichero borrado
    hecho = P.tick(LUNES, lanzar=lambda e: pytest.fail("no se lanza otro turno con uno vivo"))
    assert "45 min" in hecho["tope"] and parada.cierre_pedido() and "tope" in parada.motivo_cierre()
    d = P._leer(P.EN_MARCHA, {})
    assert d["parar_pedido"] and "tope" in d["parar_motivo"] and vivo["muertos"] == []   # primero, cierre suave
    assert P.tick(LUNES, lanzar=lambda e: 0)["tope"] is None                             # se pide una sola vez


def test_dentro_de_su_tope_mas_el_margen_no_se_toca(vivo):
    t = _turno()
    _en_marcha(t, (45 + 14) * 60)
    assert P.tick(LUNES, lanzar=lambda e: 0)["tope"] is None and not parada.cierre_pedido()


def test_con_un_turno_vivo_pasado_de_tope_la_cola_espera(vivo):
    t, otro = _turno(), _turno(nombre="Cola", plantilla="cola")
    _en_marcha(t, (45 + 16) * 60)
    P.encolar(otro["id"], manual=True)
    hecho = P.tick(LUNES, lanzar=lambda e: pytest.fail("nunca dos turnos a la vez"))
    assert hecho["lanzado"] is None and "espera" in hecho["motivo"]


def test_si_no_obedece_se_cierra_por_pid_exacto_tras_listar_a_sus_hijos(vivo, monkeypatch):
    t = _turno()
    _en_marcha(t, (45 + 20) * 60, parar_pedido=time.time() - P.FORZAR_TRAS - 5, parar_motivo="paso su tope de 45 min")
    monkeypatch.setattr(P, "_linea_de_comando", lambda pid: _linea(t))
    listados = []

    def hijos(pid):
        listados.append(pid)
        return [{"pid": 501, "nombre": "python.exe", "linea": f"{RAIZ}\\.venv\\Scripts\\python.exe -m pytest",
                 "reconocido": True}]
    monkeypatch.setattr(P, "_hijos", hijos)
    hecho = P.tick(LUNES, lanzar=lambda e: 0)
    assert listados == [PID] and vivo["muertos"] == [PID] and "cerrado" in hecho["forzado"]
    assert not P.EN_MARCHA.exists()
    reg = json.loads(_registros()[-1].read_text(encoding="utf-8"))
    assert reg["turno_id"] == t["id"] and "tope" in reg["abortado"] and reg["hijos_cerrados"][0]["pid"] == 501


def test_con_un_hijo_desconocido_no_mata_nada_y_avisa_en_el_centro(vivo, monkeypatch):
    t = _turno()
    _en_marcha(t, (45 + 20) * 60, parar_pedido=time.time() - P.FORZAR_TRAS - 5, parar_motivo="paso su tope de 45 min")
    monkeypatch.setattr(P, "_linea_de_comando", lambda pid: _linea(t))
    monkeypatch.setattr(P, "_hijos", lambda pid: [{"pid": 777, "nombre": "notepad.exe", "linea": "notepad.exe x.txt",
                                                   "reconocido": False}])
    hecho = P.tick(LUNES, lanzar=lambda e: pytest.fail("la cola espera"))
    assert vivo["muertos"] == [] and "no reconozco" in hecho["forzado"] and P.EN_MARCHA.exists()
    (aviso,) = _avisos()
    assert "sin cerrar" in aviso["titulo"] and "notepad.exe" in aviso["cuerpo"] and "777" in aviso["cuerpo"]
    assert P.tick(LUNES, lanzar=lambda e: 0)["forzado"] is None                   # no lo reintenta cada 20 s
    assert len(_avisos()) == 1


def test_si_taskkill_no_lo_cierra_avisa_y_el_registro_sigue(vivo, monkeypatch):
    vivo["muere"] = False
    t = _turno()
    _en_marcha(t, (45 + 20) * 60, parar_pedido=time.time() - P.FORZAR_TRAS - 5)
    monkeypatch.setattr(P, "_linea_de_comando", lambda pid: _linea(t))
    monkeypatch.setattr(P, "_hijos", lambda pid: [])
    hecho = P.tick(LUNES, lanzar=lambda e: 0)
    assert vivo["muertos"] == [PID] and "taskkill" in hecho["forzado"] and P.EN_MARCHA.exists()
    assert "sin cerrar" in _avisos()[0]["titulo"]


def test_si_no_puede_leer_su_linea_de_comando_no_mata_y_avisa(vivo, monkeypatch):
    t = _turno()
    _en_marcha(t, (45 + 20) * 60, parar_pedido=time.time() - P.FORZAR_TRAS - 5)

    def falla(pid):
        raise OSError("powershell no responde")
    monkeypatch.setattr(P, "_linea_de_comando", falla)
    assert "linea de comando" in P.tick(LUNES, lanzar=lambda e: 0)["forzado"] and vivo["muertos"] == []
    assert P.EN_MARCHA.exists() and _avisos()


def test_pid_reutilizado_no_se_toca_pero_el_turno_queda_registrado(vivo, monkeypatch):
    t = _turno()
    _en_marcha(t, (45 + 20) * 60, parar_pedido=time.time() - P.FORZAR_TRAS - 5)
    monkeypatch.setattr(P, "_linea_de_comando", lambda pid: "C:/Windows/notepad.exe")
    assert "no se toca" in P.tick(LUNES, lanzar=lambda e: 0)["forzado"] and vivo["muertos"] == []
    assert not P.EN_MARCHA.exists() and "murio sin dejar registro" in json.loads(
        _registros()[-1].read_text(encoding="utf-8"))["abortado"]


# ------------------------------------------------------------------ hijos
def _p(pid, padre, nombre, linea, creado):
    return {"pid": pid, "padre": padre, "nombre": nombre, "linea": linea, "creado": creado}


def test_hijos_lista_el_arbol_y_marca_lo_que_no_reconoce():
    procesos = [
        _p(PID, 100, "python.exe", f"{RAIZ}\\.venv\\Scripts\\python.exe turno_nexo.py", "2026-10-19T08:09:50"),
        _p(10, PID, "conhost.exe", "\\??\\C:\\Windows\\system32\\conhost.exe 0x4", "2026-10-19T08:09:51"),
        _p(11, PID, "python.exe", f"{RAIZ.replace(chr(92), '/')}/.venv/Scripts/python.exe -m pytest", "2026-10-19T08:30:00"),
        _p(12, 11, "cmd.exe", "cmd /c algo", "2026-10-19T08:30:01"),             # cuelga de uno reconocido: suyo
        _p(13, PID, "chrome.exe", "chrome.exe --remote-debugging-port=9333 --user-data-dir=x", "2026-10-19T08:10:00"),
        _p(14, 13, "chrome.exe", "chrome.exe --type=renderer", "2026-10-19T08:10:01"),
        _p(15, PID, "notepad.exe", "notepad.exe", "2026-10-19T08:40:00"),        # desconocido
        _p(16, PID, "viejo.exe", "viejo.exe", "2026-10-18T22:00:00"),            # huerfano de un PID reutilizado
        _p(17, 999, "otro.exe", "otro.exe", "2026-10-19T08:41:00"),              # de otro arbol
    ]
    hijos = {h["pid"]: h["reconocido"] for h in P._hijos(PID, procesos)}
    assert hijos == {10: True, 11: True, 12: True, 13: True, 14: True, 15: False}


def test_chrome_cualquiera_no_es_el_de_nexo():
    assert not P._hijo_reconocido({"nombre": "chrome.exe", "linea": "chrome.exe --profile-directory=Default"})
    assert P._hijo_reconocido({"nombre": "git.exe", "linea": "git status"})


# ------------------------------------------------------------------ el banco para a tiempo
def test_correr_no_empieza_otra_llamada_cuando_hay_que_cortar(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "CARPETA", tmp_path)
    monkeypatch.setattr(B, "RESULTADOS", tmp_path / "banco.jsonl")
    llamadas, motivo = [], [""]

    def llamar(prov, modelo, prompt):
        llamadas.append(modelo)
        motivo[0] = "tope de tiempo del turno"            # tras la primera llamada se acaba el tiempo
        return {"texto": "", "segundos": 1.0, "error": "vacia", "codigo": "vacia"}
    filas = B.correr([("groq", "a"), ("groq", "b")], roles=("triaje",), llamar_fn=llamar, dormir=lambda s: None,
                     progreso=lambda s: None, cortar=lambda: motivo[0])
    assert llamadas == ["a"] and len(filas) == 1


def test_cortador_tope_parada_y_cierre():
    assert B.cortador(None)() == ""                                         # suelto (CLI, tests): nunca corta
    assert B.cortador(time.time() + 3600)() == ""
    assert B.cortador(time.time() + B.TIMEOUT - 5)() == "tope de tiempo del turno"   # no cabe otra llamada
    parada.pedir_cierre("paso su tope de 45 min")
    assert "cierre pedido" in B.cortador(time.time() + 3600)()
    parada.limpiar_cierre()
    parada.BANDERA.parent.mkdir(parents=True, exist_ok=True)
    parada.BANDERA.write_text(json.dumps({"motivo": "prueba"}), encoding="utf-8")   # sin activar(): no toca Ollama
    assert "PARADA" in B.cortador(time.time() + 3600)()


def _banco_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "CARPETA", tmp_path)
    monkeypatch.setattr(B, "RESULTADOS", tmp_path / "banco.jsonl")
    monkeypatch.setattr(B, "ROLES", tmp_path / "roles.json")
    monkeypatch.setattr(B, "candidatos_rol", lambda rol, por_rol, nuevos, inv: [("groq", "a")])


def test_turno_diario_con_el_tope_pasado_no_mide_y_lo_dice(tmp_path, monkeypatch):
    _banco_tmp(tmp_path, monkeypatch)
    vistos = []
    r = B.turno_diario(roles=("triaje", "revisar"), correr_fn=lambda *a, **k: vistos.append(k), inv={},
                       limite=time.time() - 1)
    assert vistos == [] and r["cortado"] == "tope de tiempo del turno" and r["medidos"] == {}


def test_turno_diario_pasa_el_corte_al_banco_y_para_entre_roles(tmp_path, monkeypatch):
    _banco_tmp(tmp_path, monkeypatch)
    roles_medidos = []

    def correr(cand, roles, progreso, cortar):
        roles_medidos.append(roles[0])
        parada.pedir_cierre("parado por Damian")                     # "Parar" mientras mide el primer rol
        return []
    r = B.turno_diario(roles=("triaje", "revisar", "redactar"), correr_fn=correr, inv={},
                       limite=time.time() + 3600, hoy="2026-10-19")
    assert len(roles_medidos) == 1 and "cierre pedido" in r["cortado"]


def test_turno_diario_empieza_cada_dia_por_un_rol_distinto(tmp_path, monkeypatch):
    _banco_tmp(tmp_path, monkeypatch)
    roles = ("programar", "revisar", "redactar", "triaje")
    primeros = set()
    for dia in ("2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22"):
        orden = []
        B.turno_diario(roles=roles, correr_fn=lambda c, roles, progreso, cortar: orden.append(roles[0]), inv={},
                       hoy=dia)
        assert sorted(orden) == sorted(roles)                         # sin corte, se miden todos
        primeros.add(orden[0])
    assert primeros == set(roles)


def test_el_turno_modelos_pasa_su_limite_al_banco(monkeypatch):
    import turno_nexo
    t = _turno(max_minutos=45)
    monkeypatch.setattr(turno_nexo, "ram_libre_gb", lambda: 32.0)
    monkeypatch.setattr(turno_nexo, "candidatas", lambda ctx: {"modelos": 1})
    vistos = {}

    def diario(**k):
        vistos.update(k)
        return {"dia": "2026-10-19"}
    monkeypatch.setattr(B, "turno_diario", diario)
    antes = time.time()
    reg = turno_nexo.turno(turno_id=t["id"], avisar=False)
    assert "modelos" in reg["pasos"] and antes + 45 * 60 - 5 <= vistos["limite"] <= time.time() + 45 * 60
