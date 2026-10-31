# -*- coding: utf-8 -*-
"""T669 (F3 de la epica T664): implementador independiente de Claude y puerta de fusion.

Git REAL en tmp_path (un repo con rama `principal`); Aider, el revisor del diff y la suite son dobles. Nada toca el
repo de NEXO ni memoria/ real. Reglas de Damian del 04/10: worktree por tarea, tests primero en codigo, 2 intentos,
nunca R3, PARADA e interruptor de turnos lo paran, privacidad (.aiderignore + sparse-checkout), fusion y marcha
atras solo con el arbol de principal limpio, y en el piloto nada se fusiona solo."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from nucleo import aprobaciones as ap
from nucleo import avisos, implementador as I, parada, puerta as P, riesgo, turnos
from nucleo import tareas as T

RAIZ_NEXO = Path(__file__).resolve().parent.parent
FIRMA = ["-c", "user.name=t", "-c", "user.email=t@t"]


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Repo de juguete con la forma de NEXO (incluidos los archivos privados que SI estan en git)."""
    r = tmp_path / "agente"
    archivos = {
        "README.md": "# NEXO\n\nEstado: viejo.\n",
        "documentacion/00_INDICE.md": "# Indice\n",
        "nucleo/cola.py": "def tomar(c):\n    return c[0]\n",
        "tests/test_cola.py": "from nucleo.cola import tomar\n\ndef test_tomar():\n    assert tomar([1]) == 1\n",
        "nucleo/__init__.py": "",
        "tests/__init__.py": "",
        "memoria/becas.md": "PRIVADO becas\n",
        "memoria/historial_telegram.json": "{\"privado\": 1}\n",
        "canal/entrada/libre_1.json": "{\"privado\": 2}\n",
        "canal/estado_bot.json": "{\"privado\": 3}\n",
        "registros/r.jsonl": "{\"privado\": 4}\n",
        "manos/shell.py": "x = 1\n",
        ".aiderignore": (RAIZ_NEXO / ".aiderignore").read_text(encoding="utf-8"),
        ".gitignore": ".aider.*\n",
    }
    for ruta, texto in archivos.items():
        (r / ruta).parent.mkdir(parents=True, exist_ok=True)
        (r / ruta).write_text(texto, encoding="utf-8")
    git(r, "init", "-q", "-b", "principal")
    git(r, "add", "-A")
    git(r, *FIRMA, "commit", "-qm", "base")
    for mod, attr in ((ap, "ALMACEN"), (ap, "HISTORIAL"), (ap, "CANDADO")):
        monkeypatch.setattr(mod, attr, tmp_path / "ap" / Path(str(getattr(mod, attr))).name)
    (tmp_path / "ap").mkdir()
    monkeypatch.setattr(avisos, "CARPETA", tmp_path / "avisos")
    mem = tmp_path / "memoria_nexo"
    mem.mkdir()
    monkeypatch.setattr(T, "ALMACEN", mem / "tareas.json")
    monkeypatch.setattr(T, "VISTA", mem / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "tareas.md")
    monkeypatch.setattr(T, "CANDADO", mem / ".candado_tareas.lock")
    monkeypatch.setattr(parada, "BANDERA", mem / "PARADA")
    monkeypatch.setattr(turnos, "BANDERA", mem / "TURNOS_DESACTIVADOS")
    monkeypatch.setattr(I, "REPO", r)
    monkeypatch.setattr(I, "WORKTREES", tmp_path / "agente_impl")
    monkeypatch.setattr(I, "INFORMES", mem / "implementador")
    monkeypatch.setattr(I, "PILOTO", mem / "implementador" / "piloto.json")
    monkeypatch.setattr(I, "_suite", lambda cwd, archivos=None: (True, "1 passed"))
    # Los tests de la mecanica usan un README de ejemplo; las reglas de verdad (documentacion fuera) van aparte.
    monkeypatch.setattr(I, "DOCUMENTACION", True)
    monkeypatch.setattr(P, "DOCUMENTACION_SIN_CLAUDE", True)
    monkeypatch.setattr(P, "_salud_web", lambda: (True, "sin web"))
    monkeypatch.setattr(P, "_revisor", lambda tarea, diff, excluir: {"veredicto": "APROBAR", "revisor": "doble",
                                                                     "familia": "google", "motivo": "ok"})
    return r


def nueva(titulo="Actualizar el Estado del README", donde="README.md", etiquetas=()):
    return T.anadir(titulo, detalle=f"QUE: {titulo}\nDONDE: {donde}\nVALOR: 4 · ESFUERZO: 1\nRIESGO: bajo",
                    etiquetas=list(etiquetas))


def aider_que_escribe(cambios: dict, registro: list | None = None):
    """Doble de Aider: escribe `cambios` (ruta -> texto) en el worktree y apunta con que lo llamaron."""
    def ejecutar(worktree, modelo, archivos, mensaje, solo_lectura=()):
        if registro is not None:
            registro.append({"modelo": modelo, "archivos": list(archivos), "mensaje": mensaje,
                             "solo_lectura": list(solo_lectura)})
        for ruta, texto in (cambios(len(registro or [])) if callable(cambios) else cambios).items():
            (Path(worktree) / ruta).parent.mkdir(parents=True, exist_ok=True)
            (Path(worktree) / ruta).write_text(texto, encoding="utf-8")
        return {"ok": True, "salida": "hecho", "modelo": modelo.id}
    return ejecutar


# ================================================================ privacidad (decision a de Damian)
PRIVADAS = ["memoria/becas.md", "memoria/historial_telegram.json", "canal/entrada/", "canal/estado_bot.json",
            "secretos.toml", ".env", "registros/", "chrome-perfil/"]


def test_aiderignore_del_repo_excluye_todo_lo_privado():
    texto = (RAIZ_NEXO / ".aiderignore").read_text(encoding="utf-8")
    lineas = {l.strip() for l in texto.splitlines() if l.strip() and not l.startswith("#")}
    for p in PRIVADAS:
        assert p in lineas or "/" + p in lineas, p
    assert I.aiderignore() == texto


@pytest.mark.parametrize("ruta", ["memoria/becas.md", "memoria/historial_telegram.json", "canal/entrada/libre_9.json",
                                  "canal/estado_bot.json", "secretos.toml", "canal/secretos.toml", ".env", ".env.local",
                                  "registros/uso.jsonl", "chrome-perfil/Default/Cookies", "canal\\entrada\\x.json"])
def test_rutas_privadas(ruta):
    assert I.privada(ruta)


def test_no_privadas():
    for ruta in ("README.md", "memoria/tareas.json", "canal/bot.py", "documentacion/a.md"):
        assert not I.privada(ruta)


def test_el_worktree_no_saca_al_disco_lo_privado(repo):
    t = nueva()
    wt = I.crear_worktree(t["id"])
    en_disco = {p.relative_to(wt).as_posix() for p in wt.rglob("*") if p.is_file() and ".git" not in p.parts}
    assert "README.md" in en_disco and "nucleo/cola.py" in en_disco
    for p in en_disco:
        assert not I.privada(p), p
    assert git(wt, "rev-parse", "--abbrev-ref", "HEAD").strip() == f"impl/{t['id']}"
    # principal sigue entero
    assert (repo / "memoria" / "becas.md").is_file()


def test_comando_de_aider_seguro_y_sin_privados(repo):
    m = I.MODELOS[0]
    cmd = I.comando_aider(m, ["README.md", "memoria/becas.md", "canal/entrada/x.json"], "haz X", Path("h.md"),
                          solo_lectura=["registros/r.jsonl", "nucleo/cola.py"])
    for flag in ("--no-auto-commits", "--analytics-disable", "--yes-always", "--no-suggest-shell-commands",
                 "--no-check-update", "--no-gitignore", "--no-detect-urls"):
        assert flag in cmd, flag
    assert cmd[cmd.index("--env-file") + 1] == "NUL" and "--aiderignore" in cmd
    assert not any(I.privada(x) for x in cmd if not x.startswith("-")), cmd
    assert "README.md" in cmd and "nucleo/cola.py" in cmd


def test_aider_usa_formato_diff_para_codigo_y_el_de_siempre_para_documentacion(repo):
    m = I.MODELOS[0]
    assert I.comando_aider(m, ["nucleo/cola.py"], "x", Path("h.md"), formato=I.FORMATO_CODIGO)[
        I.comando_aider(m, ["nucleo/cola.py"], "x", Path("h.md"), formato="diff").index("--edit-format") + 1] == "diff"
    assert "--edit-format" not in I.comando_aider(m, ["README.md"], "x", Path("h.md"))


def test_nada_privado_llega_al_prompt(repo):
    """Ni el mensaje a Aider ni el prompt del revisor llevan contenido de archivos privados."""
    registro = []
    t = nueva(titulo="Actualizar el README y memoria/becas.md", donde="README.md, memoria/becas.md")
    I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}, registro))
    for llamada in registro:
        assert "PRIVADO" not in llamada["mensaje"]
        assert not any(I.privada(a) for a in llamada["archivos"] + llamada["solo_lectura"])
    diff = ("diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n+hola\n"
            "diff --git a/memoria/becas.md b/memoria/becas.md\n--- a/memoria/becas.md\n+++ b/memoria/becas.md\n"
            "@@ -1 +1 @@\n+PRIVADO becas\n")
    texto = P.prompt_revision(t, diff)
    assert "PRIVADO" not in texto and "+hola" in texto and "memoria/becas.md" in texto


# ================================================================ cuando NO trabaja
def test_parada_y_turnos_desactivados_lo_detienen(repo):
    t = nueva()
    parada.activar("prueba")
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "x"}))
    assert r["estado"] == "detenido" and not I.WORKTREES.exists()
    parada.desactivar()
    turnos.desactivar("prueba")
    assert I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "x"}))["estado"] == "detenido"


def test_nunca_r3(repo):
    t = nueva(titulo="Endurecer el shell", donde="manos/shell.py")
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"manos/shell.py": "x = 2\n"}))
    assert r["estado"] == "no_autorizado" and r["nivel"] == "R3" and not I.WORKTREES.exists()


def test_r1_espera_el_veto(repo):
    t = nueva(titulo="Test de la cola", donde="tests/test_cola.py")
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"tests/test_cola.py": "x"}))
    assert r["estado"] == "no_autorizado" and "veto" in r["motivo"]


# ================================================================ flujo
def test_documentacion_en_su_rama_con_marca_y_sin_tocar_principal(repo):
    t = nueva()
    base = git(repo, "rev-parse", "principal").strip()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}))
    assert r["estado"] == "listo", r
    wt = Path(r["worktree"])
    msg = git(wt, "log", "-1", "--format=%B")
    assert f"Implementador: {t['id']}" in msg and "Modelo:" in msg
    assert git(wt, "diff", "--name-only", f"{base}..HEAD").split() == ["README.md"]
    assert git(repo, "rev-parse", "principal").strip() == base


def test_dos_intentos_y_despues_necesita_claude(repo, monkeypatch):
    monkeypatch.setattr(I, "_suite", lambda cwd, archivos=None: (False, "1 failed: test_x"))
    registro = []
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "malo"}, registro))
    assert r["estado"] == "fallido" and len(registro) == 2
    assert "1 failed" in registro[1]["mensaje"]          # el 2.o intento sabe por que fallo el 1.o
    assert registro[0]["modelo"] != registro[1]["modelo"]  # y prueba con otro modelo
    tt = T.buscar(t["id"])
    assert "necesita:claude" in tt["etiquetas"] and "2 intentos" in tt["notas"][-1]["texto"]


def test_codigo_tests_primero_y_tienen_que_fallar_antes(repo, monkeypatch):
    llamadas = []

    def suite(cwd, archivos=None):
        llamadas.append(archivos)
        codigo = (Path(cwd) / "nucleo" / "cola.py").read_text(encoding="utf-8")
        if archivos:      # solo los tests nuevos: fallan mientras no exista vacia()
            return ("def vacia" in codigo, "test nuevo")
        return True, "todo verde"
    monkeypatch.setattr(I, "_suite", suite)

    def cambios(n):
        if n == 1:   # primer paso: SOLO tests
            return {"tests/test_cola_vacia.py": "from nucleo.cola import vacia\n\ndef test_v():\n    assert vacia([])\n"}
        return {"nucleo/cola.py": "def tomar(c):\n    return c[0]\n\ndef vacia(c):\n    return not c\n"}
    registro = []
    t = nueva(titulo="Anadir vacia() a la cola", donde="nucleo/cola.py")
    r = I.implementar(t["id"], ejecutar=aider_que_escribe(cambios, registro))
    assert r["estado"] == "listo", r
    assert r["tests_fallaban_antes"] is True and r["tests_nuevos"] == ["tests/test_cola_vacia.py"]
    assert all(a.startswith("tests/") for a in registro[0]["archivos"])
    assert "nucleo/cola.py" in registro[0]["solo_lectura"]
    log = git(Path(r["worktree"]), "log", "--format=%s", "principal..HEAD").splitlines()
    assert len(log) == 2 and "tests" in log[-1].lower()


def test_codigo_cuyos_tests_ya_pasan_no_vale(repo, monkeypatch):
    monkeypatch.setattr(I, "_suite", lambda cwd, archivos=None: (True, "verde"))
    t = nueva(titulo="Anadir vacia() a la cola", donde="nucleo/cola.py")
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"tests/test_cola_vacia.py": "def test_v():\n    pass\n"}))
    assert r["estado"] == "fallido" and "no fallan" in r["motivo"]


def test_el_paso_de_tests_no_puede_tocar_codigo(repo, monkeypatch):
    monkeypatch.setattr(I, "_suite", lambda cwd, archivos=None: (False, "rojo"))
    t = nueva(titulo="Anadir vacia() a la cola", donde="nucleo/cola.py")
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"tests/test_v.py": "x", "nucleo/cola.py": "roto"}))
    assert r["estado"] == "fallido" and "solo tests" in r["motivo"]


def test_si_el_modelo_toca_algo_privado_o_r3_se_aborta(repo):
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "x", "manos/shell.py": "x = 9\n"}))
    assert r["estado"] == "fallido" and "R3" in r["motivo"]


# ================================================================ puerta de fusion
def _diff(ruta, linea):
    return f"diff --git a/{ruta} b/{ruta}\n--- a/{ruta}\n+++ b/{ruta}\n@@ -1 +1 @@\n+{linea}\n"


@pytest.mark.parametrize("linea,palabra", [
    ("subprocess.run(cmd, shell=True)", "shell=True"),
    ("httpx.get(url, verify=False)", "verify=False"),
    ("resultado = eval(texto)", "eval"),
    ("datos = pickle.loads(b)", "pickle"),
    ("yaml.load(f)", "yaml.load"),
    ('app.run(host="0.0.0.0")', "0.0.0.0"),
    ("os.chmod(p, 0o777)", "777"),
])
def test_auditor_valores_inseguros_t226(linea, palabra):
    a = P.auditar(_diff("herramientas_nube/x.py", linea), "R1", {"etiquetas": []})
    assert not a["ok"] and any(palabra in f for f in a["fallos"])


def test_auditor_privados_r3_y_dependencias():
    assert not P.auditar(_diff("memoria/becas.md", "x"), "R2", {"etiquetas": []})["ok"]
    a = P.auditar(_diff("manos/shell.py", "x = 1"), "R2", {"etiquetas": []})
    assert not a["ok"] and a["nivel_real"] == "R3"
    d = P.auditar(_diff("requirements.txt", "requests==2.0"), "R2", {"etiquetas": []})
    assert d["ok"] and d["nivel_real"] == "R2" and any("dependencia" in m for m in d["avisos"])
    assert P.auditar(_diff("README.md", "hola"), "R0", {"etiquetas": []})["ok"]


def test_revisor_de_otra_familia(monkeypatch):
    llamados = []

    class Falso:
        def __init__(self, c):
            self.c = c

        def enviar(self, texto):
            llamados.append(self.c.familia)
            return type("R", (), {"estado": "OK", "texto": "VEREDICTO: APROBAR\nMOTIVO: hace lo pedido"})()
    monkeypatch.setattr(P, "_proveedor_de", lambda c: Falso(c))
    monkeypatch.setattr(P, "_disponible", lambda c: True)
    v = P._revisor_real({"id": "T1", "titulo": "x", "detalle": ""}, _diff("README.md", "x"), excluir={"openai"})
    assert v["veredicto"] == "APROBAR" and llamados and llamados[0] != "openai"


def test_piloto_no_fusiona_solo(repo):
    t = nueva()
    base = git(repo, "rev-parse", "principal").strip()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}))
    g = P.pasar(t["id"], r)
    assert g["estado"] == "espera_claude" and g["pasa"] is True
    assert git(repo, "rev-parse", "principal").strip() == base
    assert I.piloto()["pendientes_claude"] == [t["id"]]


def _sin_piloto(monkeypatch):
    monkeypatch.setattr(I, "en_piloto", lambda: False)


def test_fusiona_con_marca_si_todo_pasa_y_el_arbol_esta_limpio(repo, monkeypatch):
    _sin_piloto(monkeypatch)
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}))
    g = P.pasar(t["id"], r)
    assert g["estado"] == "fusionada", g
    assert "Estado: nuevo." in (repo / "README.md").read_text(encoding="utf-8")
    assert f"Implementador: {t['id']}" in git(repo, "log", "-1", "--format=%B")
    assert len(git(repo, "log", "-1", "--format=%P").split()) == 2       # --no-ff: se deshace de una vez


def test_arbol_sucio_espera_a_la_siguiente_tanda(repo, monkeypatch):
    _sin_piloto(monkeypatch)
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}))
    (repo / "nucleo" / "cola.py").write_text("# sin commit\n", encoding="utf-8")
    base = git(repo, "rev-parse", "principal").strip()
    g = P.pasar(t["id"], r)
    assert g["estado"] == "espera_arbol_limpio" and git(repo, "rev-parse", "principal").strip() == base
    git(repo, "checkout", "--", "nucleo/cola.py")
    assert P.pasar(t["id"], r)["estado"] == "fusionada"


def test_arbol_limpio_ignora_memoria_pero_no_el_resto(repo):
    (repo / "memoria").mkdir(exist_ok=True)
    (repo / "memoria" / "estado.json").write_text("{}", encoding="utf-8")
    git(repo, "add", "memoria/estado.json")
    git(repo, *I.FIRMA, "commit", "-qm", "memoria versionada")
    assert P.arbol_limpio(repo)
    (repo / "memoria" / "estado.json").write_text('{"x": 1}', encoding="utf-8")
    assert P.arbol_limpio(repo)                                  # solo memoria/ sucia: no bloquea
    (repo / "nucleo" / "cola.py").write_text("# sin commit\n", encoding="utf-8")
    assert not P.arbol_limpio(repo)                              # memoria/ + otra ruta: bloquea


def test_salud_falla_marcha_atras_automatica(repo, monkeypatch):
    _sin_piloto(monkeypatch)
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}))
    monkeypatch.setattr(P, "_salud_web", lambda: (False, "/salud 500"))
    g = P.pasar(t["id"], r)
    assert g["estado"] == "revertida"
    assert "Estado: viejo." in (repo / "README.md").read_text(encoding="utf-8")
    assert "Revert" in git(repo, "log", "-1", "--format=%s")
    assert any("marcha atrás" in a["titulo"].lower() for a in avisos.recientes(5))
    assert "/salud 500" in T.buscar(t["id"])["notas"][-1]["texto"]


def test_r2_espera_el_ok_de_damian_y_luego_fusiona(repo, monkeypatch):
    _sin_piloto(monkeypatch)
    t = nueva(titulo="Anadir vacia() a la cola", donde="nucleo/cola.py")

    def suite(cwd, archivos=None):
        return ("def vacia" in (Path(cwd) / "nucleo" / "cola.py").read_text(encoding="utf-8")) if archivos else True, "x"
    monkeypatch.setattr(I, "_suite", suite)

    def cambios(n):
        if n == 1:
            return {"tests/test_v.py": "def test_v():\n    pass\n"}
        return {"nucleo/cola.py": "def tomar(c):\n    return c[0]\n\ndef vacia(c):\n    return not c\n"}
    r = I.implementar(t["id"], ejecutar=aider_que_escribe(cambios, []))
    g = P.pasar(t["id"], r)
    assert g["estado"] == "espera_ok" and g["solicitud"]
    ap.aprobar(g["solicitud"])
    assert P.pasar(t["id"], r)["estado"] == "fusionada"
    assert ap.ver(g["solicitud"])["estado"] == "usada"


def test_revisor_rechaza_no_pasa(repo, monkeypatch):
    _sin_piloto(monkeypatch)
    monkeypatch.setattr(P, "_revisor", lambda tarea, diff, excluir: {"veredicto": "RECHAZAR", "revisor": "doble",
                                                                     "familia": "google", "motivo": "fuera de alcance"})
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}))
    g = P.pasar(t["id"], r)
    assert g["estado"] == "rechazada" and "fuera de alcance" in g["motivo"]


# ================================================================ piloto (dos fases)
def test_piloto_mide_exito_y_coincidencia_y_abre_la_fase_2(repo):
    I.iniciar_piloto(fase1=[f"T{i}" for i in range(1, 11)], fase2=["T20"])
    assert I.piloto()["fase"] == 1
    for i in range(1, 11):
        I.registrar_puerta(f"T{i}", pasa=True)
        I.veredicto_claude(f"T{i}", "FUSIONAR" if i <= 8 else "RECHAZAR", "motivo")
    p = I.piloto()
    assert p["exito"] == 0.8 and p["coincidencia"] == 0.8 and p["fase"] == 2


def test_piloto_no_abre_la_fase_2_por_debajo_del_80(repo):
    I.iniciar_piloto(fase1=[f"T{i}" for i in range(1, 11)], fase2=["T20"])
    for i in range(1, 11):
        I.registrar_puerta(f"T{i}", pasa=True)
        I.veredicto_claude(f"T{i}", "FUSIONAR" if i <= 7 else "RECHAZAR", "motivo")
    p = I.piloto()
    assert p["fase"] == 1 and p["cerrada_fase1"] and "regla de respaldo" in p["nota"]


def test_en_piloto_solo_entran_las_de_la_fase(repo):
    I.iniciar_piloto(fase1=["T999"], fase2=[])
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "x"}))
    assert r["estado"] == "no_autorizado" and "piloto" in r["motivo"]


# ================================================================ regresiones del primer caso real (T377, 04/10)
def test_lo_que_escribe_la_suite_no_entra_en_el_diff(repo, monkeypatch):
    def suite_que_ensucia(cwd, archivos=None):
        (Path(cwd) / "memoria").mkdir(exist_ok=True)
        (Path(cwd) / "memoria" / "modelos_estado.json").write_text("{}", encoding="utf-8")
        return True, "verde"
    monkeypatch.setattr(I, "_suite", suite_que_ensucia)
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}))
    assert r["estado"] == "listo" and r["nivel_diff"] == "R0"
    assert I.diff_rama(t["id"]).count("diff --git") == 1
    P.pasar(t["id"], r)
    assert not (Path(r["worktree"]) / "memoria" / "modelos_estado.json").exists()


def test_los_objetivos_nunca_son_r3(repo):
    (repo / "CLAUDE.md").write_text("reglas\n", encoding="utf-8")
    origen = T.anadir("Revision de archivos", detalle="PIEZAS: CLAUDE.md:1-55; README.md:1-47")
    t = nueva(etiquetas=[f"tarea_origen:{origen['id']}"])
    assert I.objetivos(T.buscar(t["id"])) == ["README.md"]


def test_documentacion_sin_mapa_del_repo_y_codigo_con_el():
    m = I.MODELOS[0]
    cmd = I.comando_aider(m, ["README.md"], "x", Path("h.md"))
    assert cmd[cmd.index("--map-tokens") + 1] == "0"
    cmd = I.comando_aider(m, ["nucleo/cola.py"], "x", Path("h.md"), mapa=1024)
    assert cmd[cmd.index("--map-tokens") + 1] == "1024"


def test_conserva_los_finales_de_linea_del_archivo(repo):
    """Piloto T377 (04/10): Aider escribio el README con CRLF y el diff parecia una reescritura entera."""
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\r\n\r\nEstado: nuevo.\r\n"}))
    assert r["estado"] == "listo"
    d = I.diff_rama(t["id"])
    assert d.count("\n+") == 2 and "\r" not in d   # +++ b/README.md y la linea cambiada; sin CR


# ================================================================ regresion de privacidad del piloto (T461, 04/10)
def test_aiderignore_por_tarea_es_lista_blanca():
    """Con --yes-always, Aider anadia al chat cualquier archivo que el modelo nombrara (memoria/tareas.json...)."""
    texto = I.aiderignore_tarea(["documentacion/00_INDICE.md"], solo_lectura=["nucleo/cola.py", "memoria/becas.md"])
    lineas = [l for l in texto.splitlines() if l and not l.startswith("#")]
    assert lineas[0] == "*"
    assert "!/documentacion/00_INDICE.md" in lineas and "!/nucleo/cola.py" in lineas
    assert "!/memoria/becas.md" not in lineas
    for p in PRIVADAS:                       # lo privado, ignorado al final (gana a cualquier excepcion)
        assert p in lineas[lineas.index("!/nucleo/cola.py"):]


def test_ejecutar_aider_usa_la_lista_blanca(repo, monkeypatch, tmp_path):
    vistos = {}

    def run(cmd, **kw):
        ruta = Path(cmd[cmd.index("--aiderignore") + 1])
        vistos["ignorar"] = ruta.read_text(encoding="utf-8")
        vistos["absoluta"] = ruta.is_absolute()
        return subprocess.CompletedProcess(cmd, 0, "ok", "")
    monkeypatch.setattr(I, "_clave", lambda m: "x")
    monkeypatch.setattr(I.subprocess, "run", run)
    I.ejecutar_aider(tmp_path / "T900", I.MODELOS[0], ["README.md"], "haz X")
    assert vistos["absoluta"] and "!/README.md" in vistos["ignorar"] and vistos["ignorar"].splitlines()[1] == "*"


def test_si_aider_toca_un_archivo_que_no_se_le_dio_falla(repo):
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n",
                                                          "documentacion/00_INDICE.md": "# Indice cambiado\n"}))
    assert r["estado"] == "fallido" and "fuera de alcance" in r["motivo"]


def test_lista_blanca_nunca_deja_ver_lo_r3():
    texto = I.aiderignore_tarea(["README.md"])
    for r in ("nucleo/permisos.py", "nucleo/instancia.py", "nucleo/config.py", "manos/", ".claude/", "CLAUDE.md"):
        assert r in texto.splitlines()


# ================================================================ nunca abre el navegador (Damian 04/10)
def test_comando_sin_avisos_que_ofrecen_abrir_urls():
    cmd = I.comando_aider(I.MODELOS[0], ["README.md"], "x", Path("h.md"))
    for flag in ("--no-show-model-warnings", "--no-check-update", "--no-show-release-notes"):
        assert flag in cmd, flag


def test_el_entorno_de_aider_bloquea_el_navegador(monkeypatch, tmp_path):
    """Piloto 04/10: Aider con --yes-always acepto 30 veces 'Open URL for more info?' y abrio el Chrome PERSONAL."""
    monkeypatch.setattr(I, "_clave", lambda m: "x")
    monkeypatch.setattr(I, "INFORMES", tmp_path)
    env = I.entorno_aider(I.MODELOS[0])
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(I.SIN_NAVEGADOR)
    assert env["BROWSER"] == "nexo-sin-navegador"
    # Prueba de verdad en un proceso aparte: SOLO llama a open() si el bloqueo esta puesto (si no, sale con 3 sin
    # abrir nada: un fallo de este test nunca abre el Chrome de Damian).
    codigo = ("import webbrowser, sys\n"
              "if not getattr(webbrowser, '_nexo_bloqueado', False): sys.exit(3)\n"
              "ok = webbrowser.open('https://console.groq.com/x') and webbrowser.open_new_tab('https://aider.chat/y')\n"
              "ok = ok and webbrowser.get().open('https://ai.google.dev/z')\n"
              "sys.exit(0 if ok else 4)\n")
    pythons = [Path(sys.executable)]
    if (I.RAIZ / ".venv-implementador" / "Scripts" / "python.exe").is_file():
        pythons.append(I.RAIZ / ".venv-implementador" / "Scripts" / "python.exe")   # el de Aider de verdad
    for py in pythons:
        r = subprocess.run([str(py), "-c", codigo], env=env, capture_output=True, text=True)
        assert r.returncode == 0, (py, r.returncode, r.stderr)
    urls = (tmp_path / "urls_bloqueadas.log").read_text(encoding="utf-8").split()
    assert urls.count("https://console.groq.com/x") == len(pythons) and "https://ai.google.dev/z" in urls


# ================================================================ nada de memoria/ ni del vault (Damian 04/10)
@pytest.mark.parametrize("ruta", ["memoria/tareas.json", "memoria/historial.md", "memoria/x/y.md",
                                  "contexto/proyectos/nexo/mapa-ideas-nexo.md", "../contexto/damian.md",
                                  "C:/Users/damia/Desktop/AI/contexto/LEEME.md", r"..\contexto\x.md", "/etc/x"])
def test_nunca_se_envia(ruta):
    assert I.no_enviable(ruta)


def test_memoria_y_vault_fuera_aunque_la_tarea_los_pida(repo):
    (repo / "memoria" / "historial.md").write_text("historia\n", encoding="utf-8")
    t = nueva(titulo="Actualizar memoria/historial.md y ../contexto/proyectos/nexo/x.md y README.md",
              donde="memoria/historial.md, ../contexto/proyectos/nexo/x.md, README.md")
    assert I.objetivos(T.buscar(t["id"])) == ["README.md"]
    solo = nueva(titulo="Ordenar memoria/historial.md", donde="memoria/historial.md")
    r = I.implementar(solo["id"], ejecutar=aider_que_escribe({"memoria/historial.md": "x"}))
    assert r["estado"] in ("fallido", "no_autorizado") and not (r.get("estado") == "listo")


def test_comando_y_lista_blanca_sin_memoria_ni_vault():
    cmd = I.comando_aider(I.MODELOS[0], ["README.md", "memoria/tareas.json", "../contexto/x.md"], "x", Path("h.md"),
                          solo_lectura=["memoria/historial.md", "nucleo/cola.py"])
    assert not any("memoria" in x or "contexto" in x for x in cmd)
    texto = I.aiderignore_tarea(["README.md", "memoria/tareas.json"], ["memoria/historial.md"])
    assert "!/memoria" not in texto and "memoria/" in texto.splitlines()


def test_la_puerta_no_manda_memoria_al_revisor_y_la_rechaza():
    diff = ("diff --git a/memoria/historial.md b/memoria/historial.md\n--- a/memoria/historial.md\n"
            "+++ b/memoria/historial.md\n@@ -1 +1 @@\n+SECRETO DE DAMIAN\n")
    assert "SECRETO DE DAMIAN" not in P.prompt_revision({"id": "T1", "titulo": "x"}, diff)
    a = P.auditar(diff, "R2", {"etiquetas": []})
    assert not a["ok"] and any("memoria" in f for f in a["fallos"])


# ================================================================ decision 5 de Damian (04/10)
def test_por_defecto_la_documentacion_se_queda_con_claude(repo, monkeypatch):
    monkeypatch.setattr(I, "DOCUMENTACION", False)
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "x"}))
    assert r["estado"] == "no_autorizado" and "Claude" in r["motivo"] and not I.WORKTREES.exists()


def test_la_puerta_no_fusiona_documentacion_sin_el_fusionar_de_claude(repo, monkeypatch):
    _sin_piloto(monkeypatch)
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}))
    monkeypatch.setattr(P, "DOCUMENTACION_SIN_CLAUDE", False)
    g = P.pasar(t["id"], r)
    assert g["estado"] == "espera_claude" and "hechos" in g["motivo"]
    I.veredicto_claude(t["id"], "FUSIONAR", "comprobado contra el repo")
    assert P.pasar(t["id"], r)["estado"] == "fusionada"


def test_fase_2_abierta_por_damian(repo):
    I.iniciar_piloto(fase1=["T1"], fase2=["T20"])
    I.registrar_puerta("T1", pasa=True)
    I.veredicto_claude("T1", "RECHAZAR", "x")
    assert I.piloto()["fase"] == 1
    p = I.abrir_fase2("Damian 04/10: solo codigo con tests y su OK en cada diff")
    assert p["fase"] == 2 and "Damian" in p["nota"]


def test_la_puerta_prueba_la_rama_al_dia_con_principal(repo, monkeypatch):
    """04/10 (T462): la rama partia de un principal viejo y su suite fallaba por algo ya arreglado en principal."""
    _sin_piloto(monkeypatch)
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}))
    (repo / "nucleo" / "cola.py").write_text("def tomar(c):\n    return c[0]  # arreglo en principal\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, *FIRMA, "commit", "-qm", "arreglo en principal")
    vistas = []
    monkeypatch.setattr(I, "_suite", lambda cwd, archivos=None: (vistas.append(
        "arreglo en principal" in (Path(cwd) / "nucleo" / "cola.py").read_text(encoding="utf-8")) or True, "ok"))
    g = P.pasar(t["id"], r)
    assert g["estado"] == "fusionada" and vistas[0] is True
    assert git(repo, "diff", "--name-only", "HEAD^1", "HEAD").split() == ["README.md"]   # solo el cambio de la tarea


def test_la_puerta_para_si_la_rama_choca_con_principal(repo, monkeypatch):
    _sin_piloto(monkeypatch)
    t = nueva()
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({"README.md": "# NEXO\n\nEstado: nuevo.\n"}))
    (repo / "README.md").write_text("# NEXO\n\nEstado: otro distinto.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, *FIRMA, "commit", "-qm", "choca")
    g = P.pasar(t["id"], r)
    assert g["estado"] == "conflicto" and not git(Path(r["worktree"]), "status", "--porcelain").strip()


# ================================================================ fase 2: tests escritos por Claude (tests:dados)
def _con_tests_dados(repo, monkeypatch, codigo_ya_hecho=False):
    codigo = "def tomar(c):\n    return c[0]\n" + ("\ndef vacia(c):\n    return not c\n" if codigo_ya_hecho else "")
    (repo / "nucleo" / "cola.py").write_text(codigo, encoding="utf-8")
    (repo / "tests_dados").mkdir(exist_ok=True)
    (repo / "tests_dados" / "test_vacia.py").write_text("from nucleo.cola import vacia\n\ndef test_v():\n    assert vacia([])\n",
                                                   encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, *FIRMA, "commit", "-qm", "tests dados")

    def suite(cwd, archivos=None):
        return ("def vacia" in (Path(cwd) / "nucleo" / "cola.py").read_text(encoding="utf-8")) if archivos else True, "x"
    monkeypatch.setattr(I, "_suite", suite)
    return nueva(titulo="Anadir vacia() a la cola", donde="nucleo/cola.py, tests/test_vacia.py",
                 etiquetas=[I.TESTS_DADOS])


NUEVO_CODIGO = {"nucleo/cola.py": "def tomar(c):\n    return c[0]\n\ndef vacia(c):\n    return not c\n"}


def test_tests_dados_no_se_reescriben_y_el_modelo_solo_hace_codigo(repo, monkeypatch):
    t = _con_tests_dados(repo, monkeypatch)
    registro = []
    r = I.implementar(t["id"], ejecutar=aider_que_escribe(NUEVO_CODIGO, registro))
    assert r["estado"] == "listo", r
    assert len(registro) == 1 and registro[0]["archivos"] == ["nucleo/cola.py"]
    assert registro[0]["solo_lectura"] == ["tests/test_vacia.py"]
    assert r["tests_nuevos"] == ["tests/test_vacia.py"] and r["tests_fallaban_antes"] is True
    assert not (repo / "tests" / "test_vacia.py").exists()          # principal sigue verde: el test viaja con la rama
    assert "tests/test_vacia.py" in I.diff_rama(t["id"]) and "def vacia" in I.diff_rama(t["id"])


def test_tests_dados_sin_archivo_en_tests_dados_falla(repo, monkeypatch):
    t = _con_tests_dados(repo, monkeypatch)
    git(repo, "rm", "-q", "tests_dados/test_vacia.py")
    git(repo, *FIRMA, "commit", "-qm", "quita")
    r = I.implementar(t["id"], ejecutar=aider_que_escribe(NUEVO_CODIGO, []))
    assert r["estado"] == "fallido" and "tests_dados" in r["motivo"]


def test_tests_dados_que_ya_pasan_no_valen(repo, monkeypatch):
    t = _con_tests_dados(repo, monkeypatch, codigo_ya_hecho=True)
    r = I.implementar(t["id"], ejecutar=aider_que_escribe(NUEVO_CODIGO, []))
    assert r["estado"] == "fallido" and "ya pasan" in r["motivo"]


def test_si_el_modelo_cambia_los_tests_dados_el_intento_falla(repo, monkeypatch):
    t = _con_tests_dados(repo, monkeypatch)
    r = I.implementar(t["id"], ejecutar=aider_que_escribe({**NUEVO_CODIGO, "tests/test_vacia.py": "def test_v():\n    pass\n"}))
    assert r["estado"] == "fallido" and "tests dados" in r["motivo"]


def test_piloto_fase_2_con_rechazar_no_hay_tarjeta_y_con_fusionar_si_con_resumen(repo, monkeypatch):
    t = _con_tests_dados(repo, monkeypatch)
    r = I.implementar(t["id"], ejecutar=aider_que_escribe(NUEVO_CODIGO, []))
    base = git(repo, "rev-parse", "principal").strip()
    assert P.pasar(t["id"], r)["estado"] == "espera_claude"           # sin veredicto aun: ni bandeja ni fusion
    I.veredicto_claude(t["id"], "RECHAZAR", "no maneja listas vacias", resumen="Anade vacia().\nSirve para saber si hay datos.\nNo cambia nada mas.")
    g = P.pasar(t["id"], r)
    assert g["estado"] == "rechazada_claude" and g["solicitud"] is None     # RECHAZAR: ni tarjeta ni contador para Damian
    assert not ap.pendientes(incluir_matriz=True)
    assert I.piloto()["historial_rechazados"] == [{"tarea": t["id"], "motivo": "no maneja listas vacias", "puerta": True}]
    assert git(repo, "rev-parse", "principal").strip() == base         # RECHAZAR: no se fusiona
    I.veredicto_claude(t["id"], "FUSIONAR", "ok", resumen="Anade vacia().")
    assert P.pasar(t["id"], r)["estado"] == "espera_ok"                # FUSIONAR de Claude + falta el OK de Damian


def test_aider_lee_un_repo_con_paquetes_loose_de_git_maintenance(tmp_path):
    """04/10: `git maintenance` crea paquetes loose-*.pack que GitDB (el lector de Aider) no ve: BadObject. El
    sitecustomize del implementador cambia a GitCmdObjectDB."""
    py = RAIZ_NEXO / ".venv-implementador" / "Scripts" / "python.exe"
    if not py.exists():
        pytest.skip("sin .venv-implementador")
    r = tmp_path / "r"
    r.mkdir()
    (r / "a.txt").write_text("hola\n", encoding="utf-8")
    git(r, "init", "-q", "-b", "principal")
    git(r, "add", "-A")
    git(r, *FIRMA, "commit", "-qm", "base")
    git(r, "repack", "-a", "-d", "-q")
    for f in (r / ".git" / "objects" / "pack").glob("pack-*"):
        f.rename(f.with_name("loose-" + f.name[5:]))
    codigo = "import git; r=git.Repo('.', odbt=git.GitDB); print([b.path for b in r.head.commit.tree.traverse()])"
    sin = subprocess.run([str(py), "-c", codigo], cwd=r, capture_output=True, text=True)
    assert sin.returncode != 0 and "BadObject" in sin.stderr          # el problema existe sin el parche
    env = dict(os.environ, PYTHONPATH=str(I.SIN_NAVEGADOR))
    con = subprocess.run([str(py), "-c", codigo], cwd=r, capture_output=True, text=True, env=env)
    assert con.returncode == 0 and "a.txt" in con.stdout, con.stderr


def test_t676_t713_el_prompt_lleva_las_reglas_de_karpathy_y_la_solucion_minima():
    """T676 (4 reglas de Karpathy, T167) y T713 (escalera de solucion minima, T176/T256) en el mensaje del implementador."""
    m = I._mensaje({"id": "T1", "titulo": "x", "detalle": "QUE: y"}, "codigo").lower()
    for clave in ("piensa antes", "supones", "solucion minima", "biblioteca estandar", "quirurgico",
                  "tests en verde", "sin recortar validaciones"):
        assert clave in m, clave


def test_puerta_resume_los_rojos_con_el_test_que_falla():
    """11/10: el motivo de 'suite en rojo' decia los avisos de pytest y no el test que fallaba (T422)."""
    from nucleo import puerta as P
    salida = ("....F..\n=== warnings summary ===\n<unknown>:2: DeprecationWarning: invalid escape\n"
              "=== short test summary info ===\nFAILED tests/test_t675_turnos.py::test_orden - AssertionError\n"
              "ERROR tests/test_x.py::test_y\n2 failed, 2016 passed in 299.07s")
    r = P.resumen_rojos(salida)
    assert r.startswith("FAILED tests/test_t675_turnos.py::test_orden") and "ERROR tests/test_x.py" in r
    assert "2 failed" in r and "DeprecationWarning" not in r
    assert P.resumen_rojos("la suite tardo mas de 900 s") == "la suite tardo mas de 900 s"


def test_un_modulo_nuevo_es_objetivo_de_codigo(repo):
    """12/10: las piezas de las epicas crean modulos nuevos (nucleo/orden_accion.py...). Antes objetivos() solo
    aceptaba rutas que ya existian y la tarea se tomaba por documentacion ("se queda con Claude")."""
    t = nueva(titulo="Crear el detector", donde="nucleo/detector_nuevo.py, tests/test_detector_nuevo.py, "
                                               "carpeta_que_no_existe/x.py, nucleo/nuevo.md")
    assert I.objetivos(T.buscar(t["id"])) == ["nucleo/detector_nuevo.py", "tests/test_detector_nuevo.py"]
