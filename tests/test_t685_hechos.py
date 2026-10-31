# -*- coding: utf-8 -*-
"""T685 (F3 de T664): el revisor de diffs de la puerta comprueba contra el repo lo que afirma.

Caso real (04/10, T347): el revisor rechazo diciendo que `evaluar_candidatas` "no existe en el diff"; la funcion SI
existia en el archivo, el revisor solo veia las lineas del diff. Git real en tmp_path; el revisor es un doble."""
from __future__ import annotations

from nucleo import hechos, implementador as I, puerta as P
from tests.test_t669_implementador import aider_que_escribe, git, nueva, repo, _sin_piloto  # noqa: F401


def _diff_cola():
    return ("diff --git a/nucleo/cola.py b/nucleo/cola.py\n--- a/nucleo/cola.py\n+++ b/nucleo/cola.py\n@@ -1,2 +1,3 @@\n"
            " def tomar(c):\n     return c[0]\n+# nota\n")


def test_simbolo_existe_busca_en_el_repo(repo):
    donde = hechos.simbolo_existe(repo, "tomar")
    assert donde and donde.startswith("nucleo/cola.py:")
    assert hechos.simbolo_existe(repo, "no_la_hay_en_ningun_sitio") is None
    assert hechos.simbolo_existe(repo, "nucleo/cola.py") == "nucleo/cola.py"


def test_no_devuelve_evidencia_de_lo_privado(repo):
    assert hechos.simbolo_existe(repo, "PRIVADO") is None


def test_acusacion_falsa_de_no_existe_se_anula(repo):
    rev = {"veredicto": "RECHAZAR", "revisor": "x", "familia": "g",
           "motivo": "La funcion `tomar` no existe en el diff."}
    r = hechos.verificar_rechazo(rev, repo)
    assert r["veredicto"] == "APROBAR"
    assert r["anuladas"] == [{"simbolo": "tomar", "donde": "nucleo/cola.py:1"}]
    assert "anulad" in r["motivo"].lower()


def test_acusacion_verdadera_se_mantiene(repo):
    rev = {"veredicto": "RECHAZAR", "motivo": "`inventada_por_el_modelo` no existe, la tarea pedia crearla."}
    r = hechos.verificar_rechazo(rev, repo)
    assert r["veredicto"] == "RECHAZAR" and not r.get("anuladas")


def test_otro_motivo_distinto_de_existencia_mantiene_el_rechazo(repo):
    rev = {"veredicto": "RECHAZAR",
           "motivo": "`tomar` no existe. Ademas el cambio toca archivos fuera de alcance."}
    r = hechos.verificar_rechazo(rev, repo)
    assert r["veredicto"] == "RECHAZAR"
    assert [a["simbolo"] for a in r["anuladas"]] == ["tomar"]


def test_aprobar_y_sin_revisor_no_se_tocan(repo):
    for v in ("APROBAR", "SIN_REVISOR"):
        rev = {"veredicto": v, "motivo": "`tomar` no existe"}
        assert hechos.verificar_rechazo(rev, repo) == rev


def test_el_prompt_lleva_los_simbolos_de_los_archivos_tocados(repo):
    texto = P.prompt_revision({"id": "T1", "titulo": "x", "_repo": str(repo)}, _diff_cola())
    assert "SIMBOLOS" in texto and "tomar" in texto


def test_el_prompt_sin_repo_sigue_igual(repo):
    assert "SIMBOLOS" not in P.prompt_revision({"id": "T1", "titulo": "x"}, _diff_cola())


def test_la_puerta_anula_el_rechazo_falso_del_revisor(repo, monkeypatch):
    _sin_piloto(monkeypatch)
    monkeypatch.setattr(P, "_revisor", lambda tarea, diff, excluir: {
        "veredicto": "RECHAZAR", "revisor": "doble", "familia": "google",
        "motivo": "`tomar` no existe en el diff"})
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}))
    g = P.pasar(t["id"], r)
    assert g["estado"] != "rechazada", g
    assert g["revisor"]["veredicto"] == "APROBAR" and g["revisor"]["anuladas"]


def test_bloque18_el_prompt_del_revisor_lleva_los_contratos_de_nexo(repo):
    texto = P.prompt_revision({"id": "T1", "titulo": "x", "_repo": str(repo)}, _diff_cola())
    assert "CONTRATOS DE NEXO" in texto
    assert "from nucleo import ayuda; ayuda.atender(__doc__)" in texto


def test_bloque18_rechazo_por_importar_nucleo_se_anula_si_el_paquete_existe(repo):
    """Caso real T939 (24/10): el revisor dijo que `nucleo` 'probablemente no exista' (subjuntivo, paquete)."""
    rev = {"veredicto": "RECHAZAR", "revisor": "groq:gpt-oss-120b", "familia": "openai",
           "motivo": "La implementación añade una importación de `nucleo` que probablemente no exista, introduciendo "
                     "un error de importación y riesgo innecesario."}
    r = hechos.verificar_rechazo(rev, repo)
    assert r["veredicto"] == "APROBAR"
    assert r["anuladas"][0]["simbolo"] == "nucleo"


def test_bloque18_un_modulo_que_no_esta_en_el_repo_sigue_sin_existir(repo):
    assert hechos.simbolo_existe(repo, "paquete_inventado") is None
    assert hechos.simbolo_existe(repo, "nucleo.cola") == "nucleo/cola.py"
