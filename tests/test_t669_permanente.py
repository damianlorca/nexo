# -*- coding: utf-8 -*-
"""T669: implementador PERMANENTE (Damian 11/10, tras superar la fase 2 del piloto 4/4).

Cada tanda del turno hace UNA accion: repasar la puerta de una tarea ya implementada (tras el OK de Damian o con el
arbol limpio) o implementar la primera tarea de la cola con tests dados (`tests:dados` + su test en tests_dados/) y
riesgo R0-R2. Nunca R3 ni blindados; la puerta es la de siempre (R2 = OK de Damian sobre el diff real).
Todo con dobles (repo de juguete de test_t669_implementador).
"""
from __future__ import annotations

from nucleo import aprobaciones as ap
from nucleo import implementador as I, piloto_serie as S, puerta as P
from nucleo import tareas as T
from tests.test_t669_implementador import FIRMA, git, nueva, repo  # noqa: F401  (repo es una fixture)


def _permanente(repo, monkeypatch, letras="ab", etiquetas_extra=()):
    (repo / "tests_dados").mkdir(exist_ok=True)
    for x in letras:
        (repo / "tests_dados" / f"test_{x}.py").write_text(
            f"from nucleo.cola import f_{x}\n\n\ndef test_{x}():\n    assert f_{x}()\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, *FIRMA, "commit", "-qm", "tests dados")
    def suite(cwd, archivos=None):
        if not archivos:
            return True, "verde"
        codigo = (cwd / "nucleo" / "cola.py").read_text(encoding="utf-8")
        return all(f"def f_{a.split('test_')[1][0]}" in codigo for a in archivos), "tests dados"
    monkeypatch.setattr(I, "_suite", suite)
    ids = [nueva(titulo=f"Anadir f_{x}", donde=f"nucleo/cola.py, tests/test_{x}.py",
                 etiquetas=[I.TESTS_DADOS, *etiquetas_extra])["id"] for x in letras]
    I._editar_piloto(lambda p: p.update(activo=False, fase=2, fase1=[], fase2=[], casos={}, permanente=True))
    return ids


def aider():
    """Doble del modelo: anade f_x() (x sale del titulo de la tarea, 'Anadir f_x')."""
    def ejecutar(worktree, modelo, archivos, mensaje, solo_lectura=()):
        letra = T.buscar(worktree.name)["titulo"][-1]
        f = worktree / "nucleo" / "cola.py"
        f.write_text(f.read_text(encoding="utf-8") + f"\n\ndef f_{letra}():\n    return True\n", encoding="utf-8")
        return {"ok": True, "salida": "hecho", "modelo": modelo.id}
    return ejecutar


def test_candidatas_solo_con_tests_dados_y_sin_r3(repo, monkeypatch):
    a, b = _permanente(repo, monkeypatch)
    sin_tests = nueva(titulo="Anadir f_c", donde="nucleo/cola.py", etiquetas=[])["id"]
    blindado = nueva(titulo="Tocar permisos", donde="nucleo/permisos.py, tests/test_a.py", etiquetas=[I.TESTS_DADOS])["id"]
    r3 = nueva(titulo="Anadir f_d", donde="nucleo/cola.py, tests/test_a.py",
               etiquetas=[I.TESTS_DADOS, "riesgo:R3"])["id"]
    sin_archivo = nueva(titulo="Anadir f_e", donde="nucleo/cola.py, tests/test_e.py", etiquetas=[I.TESTS_DADOS])["id"]
    necesita = nueva(titulo="Anadir f_f", donde="nucleo/cola.py, tests/test_a.py",
                     etiquetas=[I.TESTS_DADOS, "necesita:claude"])["id"]
    ids = [t["id"] for t in S.cola()]
    assert ids == [a, b]
    for tid in (sin_tests, blindado, r3, sin_archivo, necesita):
        assert tid not in ids


def test_la_tanda_implementa_pasa_la_puerta_y_espera_el_ok_r2(repo, monkeypatch):
    a, b = _permanente(repo, monkeypatch)
    assert S.candidatas() == 1
    r = S.tanda(ejecutar=aider())
    assert (r["accion"], r["tarea"], r["puerta"]) == ("implementar", a, "espera_ok") and r["aviso"]
    sol = I._cargar_piloto()["cola"][a]["solicitud"]
    assert ap.ver(sol)["estado"] == "pendiente"
    # mientras a espera el OK de Damian, la siguiente tanda no se queda parada: sigue con b
    r = S.tanda(ejecutar=aider())
    assert (r["accion"], r["tarea"]) == ("implementar", b)
    ap.aprobar(sol)
    r = S.tanda(ejecutar=aider())
    assert (r["accion"], r["tarea"], r["puerta"]) == ("puerta", a, "fusionada")
    assert "def f_a" in (repo / "nucleo" / "cola.py").read_text(encoding="utf-8")
    t = T.buscar(a)
    assert t["estado"] == "hecha" and t["testeado"]                     # se cierra con evidencia (fusion + suite)
    assert a not in [x["id"] for x in S.cola()]


def test_r1_espera_el_veto_y_no_implementa(repo, monkeypatch):
    (a,) = _permanente(repo, monkeypatch, "a", etiquetas_extra=())
    monkeypatch.setattr(I.riesgo, "previsto", lambda t: {"nivel": "R1", "motivos": ["doble"], "rutas":
                                                          ["nucleo/cola.py", "tests/test_a.py"]})
    r = S.tanda(ejecutar=aider())
    assert r["estado"] == "no_autorizado" and not I.worktree_de(a).exists()


def test_sin_modo_permanente_sigue_la_serie_del_piloto(repo, monkeypatch):
    _permanente(repo, monkeypatch, "a")
    I._editar_piloto(lambda p: p.update(permanente=False, cierre={"decision": "x"}))
    assert S.candidatas() == 0 and "cerro" in S.por_que_nada()


def test_parada_lo_detiene(repo, monkeypatch):
    _permanente(repo, monkeypatch, "a")
    from nucleo import turnos
    turnos.desactivar("de viaje")
    assert S.tanda(ejecutar=aider())["accion"] == "nada" and S.candidatas() == 0


def test_cerrar_superado_deja_el_piloto_permanente(repo, monkeypatch, tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_bytes("# Plan\n\n### 5.4 Piloto\ntexto\n\n## 6. Reparto\n".encode("utf-8"))
    monkeypatch.setattr(S, "PLAN", plan)
    I._editar_piloto(lambda p: p.update(fase=2, fase2=["T1", "T2"], casos={
        "T1": {"puerta": True, "claude": "FUSIONAR", "final": "fusionada"},
        "T2": {"puerta": True, "claude": "FUSIONAR"}}))
    c = S.cerrar_superado("4/4")
    p = I._cargar_piloto()
    assert p["permanente"] and not p["activo"] and c["exito"] == 1.0 and c["coincidencia"] == 1.0
    assert "Fase 2 superada" in plan.read_text(encoding="utf-8") and "PERMANENTE" in plan.read_text(encoding="utf-8")
    assert not I.en_piloto()


# ================================================================ la puerta y los tests dados (11/10, T422)
def test_el_revisor_no_ve_los_tests_dados_como_cambio_del_implementador(repo, monkeypatch, tmp_path):
    (repo / "tests_dados").mkdir(exist_ok=True)
    (repo / "tests_dados" / "test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    rama = tmp_path / "rama"
    (rama / "tests").mkdir(parents=True)
    (rama / "tests" / "test_x.py").write_bytes(b"def test_x():\r\n    assert True\r\n")   # mismo texto, CRLF
    diff = ("diff --git a/tests/test_x.py b/tests/test_x.py\nnew file mode 100644\n--- /dev/null\n"
            "+++ b/tests/test_x.py\n@@ -0,0 +1,2 @@\n+def test_x():\n+    assert True\n")
    texto = P.prompt_revision({"id": "T1", "titulo": "x", "_repo": str(rama)}, diff)
    assert "copiados SIN CAMBIOS" in texto and "+def test_x" not in texto
    assert P.tests_dados_tocados(rama, diff) == []
    (rama / "tests" / "test_x.py").write_text("def test_x():\n    assert 1\n", encoding="utf-8")   # lo toco
    assert P.tests_dados_tocados(rama, diff) == ["tests/test_x.py"]
    assert "+def test_x" in P.prompt_revision({"id": "T1", "titulo": "x", "_repo": str(rama)}, diff)


def test_cerrar_superado_se_anota_aunque_el_plan_tenga_un_cierre_anterior(repo, monkeypatch, tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_bytes(f"### 5.4\n{S.MARCA_PLAN} (05/10):** aparcado.\n\n## 6. Reparto\n".encode("utf-8"))
    monkeypatch.setattr(S, "PLAN", plan)
    assert S.cerrar_superado("4/4")["plan"] is True
    texto = plan.read_text(encoding="utf-8")
    assert texto.index(S.MARCA_PLAN) < texto.index(S.MARCA_SUPERADA) < texto.index("## 6.")
    assert S.cerrar_superado("4/4")["plan"] is False                    # una sola vez


def test_bloqueada_por_otra_tarea_viva_no_entra_en_la_cola(repo, monkeypatch):
    """Piezas encadenadas (12/10): la que va DESPUES de otra (bloqueada_por) espera a que esa se cierre."""
    a, b = _permanente(repo, monkeypatch)
    T.actualizar(b, bloqueada_por=a)
    assert [t["id"] for t in S.cola()] == [a]
    assert "bloqueada" in S.apta(T.buscar(b))
    T.actualizar(a, estado="hecha")
    assert [t["id"] for t in S.cola()] == [b]


def test_devolver_vuelve_a_la_cola_sin_necesita_claude_ni_cierre_rancio(repo, monkeypatch):
    """Bloque 23 (29/10): T844/T851/T855/T559 quedaban fuera para siempre (su caso con final o necesita:claude)."""
    (a,) = _permanente(repo, monkeypatch, "a")
    T.actualizar(a, etiquetas=[I.TESTS_DADOS, "necesita:claude"],
                 cierre={"estado_real": "HECHO Y TESTEADO", "evidencia": "commit del Revert"})
    S._marcar_cola(a, final="damian_usada", motivo_final="ese visto bueno ya se uso")
    assert S.cola() == []
    r = S.devolver(a, "su fusion se deshizo", quitar_cierre=True)
    assert r["devuelta"] and r["apta"] is None and r["caso_anterior"]["final"] == "damian_usada"
    t = T.buscar(a)
    assert "necesita:claude" not in t["etiquetas"] and not t.get("cierre")
    assert "Vuelve a la cola" in str(t.get("notas"))
    p = I._cargar_piloto()
    assert a not in p["cola"] and p["historial_cola"][a][-1]["final"] == "damian_usada"
    assert [x["id"] for x in S.cola()] == [a]
    assert r["siguiente"] == "implementar"                               # sin implementacion lista: de cero
    assert S.devolver("T9999", "x")["devuelta"] is False


def test_devolver_con_implementacion_lista_vuelve_a_la_puerta(repo, monkeypatch):
    """T851/T855/T559 (infraestructura) y T854/T857 (revisor): su codigo esta listo; se repasa la puerta sobre el."""
    (a,) = _permanente(repo, monkeypatch, "a")
    S._marcar_cola(a, modelo="m", final="rechazada", motivo_final="la suite tardo mas de 1200 s", solicitud="A1")
    monkeypatch.setattr(I, "cargar_informe", lambda tid: {"estado": "listo"})
    monkeypatch.setattr(I, "worktree_de", lambda tid: repo)
    r = S.devolver(a, "fallo de infraestructura")
    assert r["siguiente"] == "puerta"
    c = I._cargar_piloto()["cola"][a]
    assert c == {"modelo": "m"} and S._en_puerta(I._cargar_piloto()) == [a]
    assert a not in [x["id"] for x in S.cola()]                          # no se implementa otra vez


def test_el_revisor_ve_el_contrato_del_test_dado_y_no_exige_main(repo, tmp_path):
    """Bloque 23 (K0027, 'contrato o solo lectura' 6 veces): el revisor rechazo T857 por hacer lo que pedia el contrato
    (que no veia: el test dado iba omitido) y T854 por no tener `if __name__` (el contrato de NEXO era ambiguo)."""
    contrato = "Contrato:\n- PERMITIDAS['web'] vale para cualquier canal con permiso."
    codigo = f'"""T145 pieza B.\n\n{contrato}\n"""\n\n\ndef test_x():\n    assert True\n'
    (repo / "tests_dados").mkdir(exist_ok=True)
    (repo / "tests_dados" / "test_x.py").write_text(codigo, encoding="utf-8")
    rama = tmp_path / "rama"
    (rama / "tests").mkdir(parents=True)
    (rama / "tests" / "test_x.py").write_text(codigo, encoding="utf-8")
    diff = ("diff --git a/tests/test_x.py b/tests/test_x.py\nnew file mode 100644\n--- /dev/null\n"
            "+++ b/tests/test_x.py\n@@ -0,0 +1,2 @@\n+def test_x():\n+    assert True\n")
    texto = P.prompt_revision({"id": "T1", "titulo": "x", "_repo": str(rama)}, diff)
    assert "CONTRATO de tests/test_x.py" in texto and "vale para cualquier canal con permiso" in texto
    assert "+def test_x" not in texto
    assert "SIN bloque `if __name__" in texto and "no hace falta anadirlo" in texto
    assert "su ausencia si es motivo de RECHAZAR" not in texto
    assert P.contrato_test_dado(rama, "tests/no_existe.py") == ""
