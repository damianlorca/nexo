# -*- coding: utf-8 -*-
"""T669, fase 2 del piloto: la serie la lleva el turno 'Implementador (piloto fase 2)' (nucleo/piloto_serie.py).

Todo con dobles: Aider (el `ejecutar` que escribe codigo), la suite, el revisor de la puerta y el repo de juguete de
test_t669_implementador. Sin red, sin modelos, sin tocar memoria/ de verdad.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from nucleo import aprobaciones as ap
from nucleo import avisos, implementador as I, parada, piloto_serie as S, puerta as P, turnos
from nucleo import tareas as T
from tests.test_t669_implementador import FIRMA, git, nueva, repo  # noqa: F401  (repo es una fixture)


def _serie(repo, monkeypatch, letras="ab"):
    (repo / "tests_dados").mkdir(exist_ok=True)
    for x in letras:
        (repo / "tests_dados" / f"test_{x}.py").write_text(
            f"from nucleo.cola import f_{x}\n\n\ndef test_{x}():\n    assert f_{x}()\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, *FIRMA, "commit", "-qm", "tests dados de la serie")

    def suite(cwd, archivos=None):
        if not archivos:
            return True, "verde"
        codigo = (Path(cwd) / "nucleo" / "cola.py").read_text(encoding="utf-8")
        return all(f"def f_{a.split('test_')[1][0]}" in codigo for a in archivos), "tests dados"
    monkeypatch.setattr(I, "_suite", suite)
    ids = [nueva(titulo=f"Anadir f_{x}", donde=f"nucleo/cola.py, tests/test_{x}.py", etiquetas=[I.TESTS_DADOS])["id"]
           for x in letras]
    I._editar_piloto(lambda p: p.update(fase=2, fase1=[], fase2=ids, casos={}))
    return ids


def aider(registro=None, ok=True):
    """Doble de Aider: anade f_x() al codigo de la tarea (x sale del nombre de su worktree)."""
    def ejecutar(worktree, modelo, archivos, mensaje, solo_lectura=()):
        if registro is not None:
            registro.append(Path(worktree).name)
        if not ok:
            return {"ok": False, "salida": "hit a token limit", "modelo": modelo.id}
        letra = "ab"[S.serie().index(Path(worktree).name)]
        f = Path(worktree) / "nucleo" / "cola.py"
        f.write_text(f.read_text(encoding="utf-8") + f"\n\ndef f_{letra}():\n    return True\n", encoding="utf-8")
        return {"ok": True, "salida": "hecho", "modelo": modelo.id}
    return ejecutar


def _caso(tid):
    return I._cargar_piloto()["casos"].get(tid) or {}


# ================================================================ la serie, una accion por tanda
def test_serie_completa_hasta_fusionar_y_sigue_con_la_siguiente(repo, monkeypatch):
    a, b = _serie(repo, monkeypatch)
    ej = aider()
    r = S.tanda(ejecutar=ej)
    assert (r["accion"], r["tarea"], r["puerta"]) == ("implementar", a, "espera_claude") and r["aviso"]
    assert not I.worktree_de(b).exists()                       # una tarea por tanda
    assert [t for t in I.piloto()["pendientes_claude"]] == [a]  # enciende el indicador del Centro

    r = S.tanda(ejecutar=ej)                                    # espera a Claude: no hace nada
    assert r["accion"] == "nada" and "Claude" in r["motivo"] and S.candidatas() == 0

    I.veredicto_claude(a, "FUSIONAR", "correcto", resumen="Anade f_a.\nSirve para la serie.\nNo cambia nada mas.")
    assert S.candidatas() == 1
    r = S.tanda(ejecutar=ej)
    assert r["accion"] == "puerta" and r["puerta"] == "espera_ok" and r["aviso"]
    sol = _caso(a)["solicitud"]
    assert "Anade f_a." in ap.ver(sol)["extra"]["resumen"]       # la tarjeta R2 lleva el resumen de 3 lineas

    llamadas = []
    original = P.pasar
    monkeypatch.setattr(P, "pasar", lambda *x, **k: llamadas.append(x) or original(*x, **k))
    r = S.tanda(ejecutar=ej)                                    # espera el OK de Damian: no hace nada (ni repasa la puerta)
    assert r["accion"] == "nada" and "Damian" in r["motivo"] and not llamadas and not I.worktree_de(b).exists()

    ap.aprobar(sol)
    r = S.tanda(ejecutar=ej)
    assert r["puerta"] == "fusionada" and "def f_a" in (repo / "nucleo" / "cola.py").read_text(encoding="utf-8")
    assert S.fase_de(a) == "terminal"

    r = S.tanda(ejecutar=ej)                                    # la siguiente tanda sigue la serie, desde principal actualizado
    assert (r["accion"], r["tarea"]) == ("implementar", b)
    assert "def f_a" in (I.worktree_de(b) / "nucleo" / "cola.py").read_text(encoding="utf-8")


def test_rechazar_de_claude_cierra_la_tarea_y_sigue_la_serie(repo, monkeypatch):
    a, b = _serie(repo, monkeypatch)
    S.tanda(ejecutar=aider())
    I.veredicto_claude(a, "RECHAZAR", "toca de mas", resumen="Anade f_a.\nSirve para la serie.\nNo cambia nada mas.")
    base = git(repo, "rev-parse", "principal").strip()
    r = S.tanda(ejecutar=aider())
    assert r["puerta"] == "rechazada_claude" and _caso(a)["final"] == "rechazada_claude"
    assert _caso(a).get("solicitud") is None and not ap.pendientes(incluir_matriz=True)   # solo historial, sin tarjeta
    assert git(repo, "rev-parse", "principal").strip() == base
    assert S.tanda(ejecutar=aider())["tarea"] == b


def test_si_la_puerta_no_pasa_el_veredicto_solo_mide_y_no_se_repite_la_puerta(repo, monkeypatch):
    a, b = _serie(repo, monkeypatch)
    monkeypatch.setattr(P, "_revisor", lambda t, d, x: {"veredicto": "RECHAZAR", "revisor": "doble", "familia": "g",
                                                       "motivo": "no"})
    r = S.tanda(ejecutar=aider())
    assert r["puerta"] == "rechazada" and S.fase_de(a) == "espera_claude"
    I.veredicto_claude(a, "FUSIONAR", "yo si lo fusionaria", resumen="x")
    monkeypatch.setattr(P, "pasar", lambda *x, **k: pytest.fail("no se vuelve a pasar la puerta"))
    assert S.tanda(ejecutar=aider())["accion"] == "puerta" and _caso(a)["final"] == "rechazada"


def test_una_tarea_fallida_no_bloquea_la_serie(repo, monkeypatch):
    a, b = _serie(repo, monkeypatch)
    r = S.tanda(ejecutar=aider(ok=False))
    assert r["estado"] == "fallido" and _caso(a)["final"] == "fallido" and _caso(a)["fallo"]
    assert S.tanda(ejecutar=aider())["tarea"] == b


def test_fusionar_sin_resumen_espera(repo, monkeypatch):
    a, _ = _serie(repo, monkeypatch)
    S.tanda(ejecutar=aider())
    I.veredicto_claude(a, "FUSIONAR", "ok")
    r = S.tanda()
    assert r["accion"] == "nada" and "resumen" in r["motivo"]


# ================================================================ cuando no hace nada
def test_parada_interruptor_y_arbol_sucio(repo, monkeypatch):
    a, _ = _serie(repo, monkeypatch)
    turnos.desactivar("de viaje")
    assert S.tanda(ejecutar=aider())["accion"] == "nada" and S.candidatas() == 0
    turnos.activar()
    monkeypatch.setattr(parada, "activa", lambda: "me voy")
    assert "PARADA" in S.tanda(ejecutar=aider())["motivo"]
    monkeypatch.setattr(parada, "activa", lambda: None)
    (repo / "README.md").write_text("# sucio sin commit\n", encoding="utf-8")
    r = S.tanda(ejecutar=aider())
    assert r["accion"] == "nada" and "sin commit" in r["motivo"] and not I.worktree_de(a).exists()
    git(repo, "checkout", "--", "README.md")
    (repo / "memoria" / "becas.md").write_text("cambio de memoria\n", encoding="utf-8")   # memoria/ no cuenta
    assert S.tanda(ejecutar=aider())["accion"] == "implementar"


# ================================================================ cierre automatico
def _turno_y_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(turnos, "CONFIG", tmp_path / "turnos_config.json")
    turnos.guardar_turno({"id": S.TURNO_ID, "nombre": S.NOMBRE_TURNO, "plantilla": "implementador",
                          "dias": list(turnos.DIAS), "horas": ["09:30"], "max_tareas": 1})
    plan = tmp_path / "plan.md"
    plan.write_bytes("# Plan\r\n\r\n### 5.4 Piloto\r\ntexto\r\n\r\n## 6. Reparto\r\nfila\r\n".encode("utf-8"))
    monkeypatch.setattr(S, "PLAN", plan)
    return plan


def _casos(**por_tarea):
    def f(p):
        p["casos"].update(por_tarea)
    I._editar_piloto(f)


def test_cierre_por_debajo_del_80_aparca_y_lo_anota_todo(repo, monkeypatch, tmp_path):
    plan = _turno_y_plan(tmp_path, monkeypatch)
    a, b = _serie(repo, monkeypatch)
    _casos(**{a: {"fase": 2, "puerta": True, "fallo": False, "claude": "FUSIONAR", "final": "fusionada"},
              b: {"fase": 2, "puerta": False, "fallo": True, "claude": None, "final": "fallido"}})
    r = S.tanda()
    assert r["accion"] == "cerrar" and r["cierre"]["exito"] == 0.5 and r["cierre"]["coincidencia"] == 1.0
    assert I._cargar_piloto()["aparcado"] and turnos.buscar(S.TURNO_ID)["activo"] is False
    tarea = T.buscar(r["cierre"]["tarea_reprobar"])
    assert "Reprobar el implementador" in tarea["titulo"] and "T320" in tarea["detalle"] and tarea["estado"] == "esperando"
    texto = plan.read_bytes().decode("utf-8")
    assert S.MARCA_PLAN in texto and "§3.3 bis" in texto and texto.index(S.MARCA_PLAN) < texto.index("## 6.")
    assert "\r\n" in texto and "\n" not in texto.replace("\r\n", "")          # conserva los finales de linea
    assert avisos.recientes()[0]["titulo"].startswith("Piloto del implementador: APARCADO")
    assert I.implementar(a)["estado"] == "no_autorizado"                     # aparcado de verdad
    assert S.tanda()["accion"] == "nada" and S.candidatas() == 0             # y no se repite el cierre
    assert plan.read_bytes().decode("utf-8").count(S.MARCA_PLAN) == 1


def test_cierre_con_80_o_mas_solo_avisa(repo, monkeypatch, tmp_path):
    plan = _turno_y_plan(tmp_path, monkeypatch)
    antes = plan.read_bytes()
    (a,) = _serie(repo, monkeypatch, "a")
    _casos(**{a: {"fase": 2, "puerta": True, "fallo": False, "claude": "FUSIONAR", "final": "fusionada"}})
    r = S.tanda()
    assert r["accion"] == "cerrar" and r["cierre"]["decision"].startswith("supera")
    p = I._cargar_piloto()
    assert not p.get("aparcado") and turnos.buscar(S.TURNO_ID)["activo"] is True and plan.read_bytes() == antes
    assert "supera el 80" in avisos.recientes()[0]["titulo"]
    assert not [t for t in T.cargar()["tareas"] if "Reprobar" in t["titulo"]]


def test_sin_coincidencia_medible_cuenta_como_por_debajo(repo, monkeypatch, tmp_path):
    _turno_y_plan(tmp_path, monkeypatch)
    (a,) = _serie(repo, monkeypatch, "a")
    _casos(**{a: {"fase": 2, "puerta": None, "fallo": True, "claude": None, "final": "fallido"}})
    assert S.tanda()["cierre"]["decision"].startswith("aparcado")


# ================================================================ el turno
def test_la_plantilla_existe_admite_horas_de_dia_y_no_es_generadora():
    from nucleo import freno
    assert "implementador" in turnos.PLANTILLAS and "implementador" not in freno.GENERADORAS
    horas = [f"{h:02d}:30" for h in range(24)]
    t = turnos.validar_turno({"nombre": "x", "plantilla": "implementador", "dias": list(turnos.DIAS), "horas": horas})
    assert t["horas"] == horas


def test_simulacion_en_seco_del_turno(repo, monkeypatch, tmp_path):
    import turno_nexo
    _turno_y_plan(tmp_path, monkeypatch)
    a, b = _serie(repo, monkeypatch)
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: None)
    monkeypatch.setattr(turno_nexo, "ram_libre_gb", lambda: 32.0)
    monkeypatch.setattr(I, "implementar", lambda *x, **k: pytest.fail("simular no implementa"))
    reg = turno_nexo.turno(turno_id=S.TURNO_ID, simular=True)
    paso = reg["pasos"]["implementador"]
    assert (paso["accion"], paso["tarea"], paso["simular"]) == ("implementar", a, True)
    assert reg["candidatas"] == {"implementador": 1} and not reg["aviso_push"]
    assert not I.worktree_de(a).exists()


def test_el_turno_sin_nada_que_hacer_no_se_despierta(repo, monkeypatch, tmp_path):
    import turno_nexo
    _turno_y_plan(tmp_path, monkeypatch)
    a, b = _serie(repo, monkeypatch)
    S.tanda(ejecutar=aider())                                   # a queda esperando a Claude
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: None)
    monkeypatch.setattr(turno_nexo, "_tomar_candado", lambda: pytest.fail("no debe tomar el candado"))
    reg = turno_nexo.turno(turno_id=S.TURNO_ID)
    assert "sin candidatas" in reg["abortado"] and "veredicto de Claude" in reg["explicacion"]


# ================================================================ sin modelo disponible no es un intento
def test_sin_modelo_no_cuenta_como_intento_ni_marca_la_tarea(repo, monkeypatch):
    a, b = _serie(repo, monkeypatch)
    caido = lambda worktree, modelo, archivos, mensaje, solo_lectura=(): {"ok": False, "no_disponible": True,
                                                                          "salida": "429", "modelo": modelo.id}
    r = S.tanda(ejecutar=caido)
    assert r["estado"] == "sin_modelo" and S.fase_de(a) == "por_hacer" and not _caso(a).get("fallo")
    assert "necesita:claude" not in T.buscar(a)["etiquetas"]
    assert S.tanda(ejecutar=aider())["puerta"] == "espera_claude"      # la siguiente tanda si lo hace


def test_tras_muchas_tandas_sin_modelo_se_da_por_fallida(repo, monkeypatch):
    monkeypatch.setattr(S, "MAX_VACIOS", 2)
    a, b = _serie(repo, monkeypatch)
    caido = lambda worktree, modelo, archivos, mensaje, solo_lectura=(): {"ok": False, "no_disponible": True,
                                                                          "salida": "429", "modelo": modelo.id}
    S.tanda(ejecutar=caido)
    r = S.tanda(ejecutar=caido)
    assert "fallida" in r["motivo"] and _caso(a)["final"] == "sin_informe"
    assert S.tanda(ejecutar=aider())["tarea"] == b


def test_un_fallo_de_git_de_aider_es_infraestructura_no_un_intento(repo, monkeypatch):
    import subprocess
    from nucleo import enfriamiento
    salida = "Unable to list files in git repo: BadObject: b'1e7e'\nIs your git repo corrupted?"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout="", stderr=salida))
    monkeypatch.setattr(I, "_clave", lambda m: "k")
    monkeypatch.setattr(enfriamiento, "enfriado", lambda p: None)
    r = I.ejecutar_aider(repo, I.MODELOS[0], ["nucleo/cola.py"], "x")
    assert not r["ok"] and r["no_disponible"]


# ================================================================ serie cortada (05/10: la web borro implpil2 a medias)
def _ronda(tid, estado="fallido"):
    import json
    d = I.INFORMES / "ronda1"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{tid}.json").write_text(json.dumps({"tarea": tid, "estado": estado, "motivo": "la suite falla",
                                               "intentos": [{"ok": False}, {"ok": False}]}), encoding="utf-8")


def test_serie_cortada_sin_turno_se_cierra_con_la_ronda_archivada(repo, monkeypatch, tmp_path):
    plan = _turno_y_plan(tmp_path, monkeypatch)
    a, b = _serie(repo, monkeypatch)
    _casos(**{a: {"fase": 2, "puerta": False, "fallo": True, "claude": None, "final": "fallido"}})
    _ronda(b)
    assert not S.cortada()                                      # con el turno vivo, la serie la lleva el turno
    assert S.cerrar_cortada(aplicar=True)["cortada"] is False and not I._cargar_piloto().get("cierre")
    turnos.poner_activo(S.TURNO_ID, False)
    assert S.cortada() and S.estado()["cortada"]
    seco = S.cerrar_cortada()
    assert list(seco["marcar"]) == [b] and not I._cargar_piloto().get("cierre")      # en seco no toca nada
    r = S.cerrar_cortada(aplicar=True)
    assert r["cierre"]["decision"].startswith("aparcado") and r["cierre"]["finales"] == {a: "fallido", b: "fallido"}
    assert I._cargar_piloto()["aparcado"] and S.MARCA_PLAN in plan.read_bytes().decode("utf-8")
    assert "ronda1" in _caso(b)["motivo_final"] and not S.cortada()


def test_serie_cortada_sin_ronda_fallida_no_cierra(repo, monkeypatch, tmp_path):
    _turno_y_plan(tmp_path, monkeypatch)
    a, b = _serie(repo, monkeypatch)
    turnos.poner_activo(S.TURNO_ID, False)
    _ronda(a, estado="listo")
    r = S.cerrar_cortada(aplicar=True)
    assert r["sin_datos"] == [a, b] and "cierre" not in r and not I._cargar_piloto().get("cierre")
