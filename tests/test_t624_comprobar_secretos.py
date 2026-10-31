# -*- coding: utf-8 -*-
"""T624/T625 (propuestas de T613): comprobar_secretos.py marca lo que no pudo auditar, mira listas y valores cortos,
y comprueba .gitignore, archivos versionados y exposicion historica. Todo con un repo de juguete y un secretos.toml
FALSO en tmp_path: nunca se toca el secretos.toml real. Nada imprime un valor."""
from __future__ import annotations

import subprocess
from pathlib import Path

import comprobar_secretos as C

FIRMA = ["-c", "user.name=t", "-c", "user.email=t@t"]
VALOR = "sk-FALSOXXXXXXXXXXXXXXXXXXXX"


def git(r, *a):
    x = subprocess.run(["git", *a], cwd=r, capture_output=True, text=True, encoding="utf-8")
    assert x.returncode == 0, x.stderr
    return x.stdout


def proyecto(tmp_path):
    r = tmp_path / "p"
    r.mkdir()
    (r / "secretos.toml").write_text(
        f'clave = "{VALOR}"\ncorto = "abc12345"\nlista = ["lista-secreta-9999", "otra-lista-8888"]\n'
        '[bot]\ntoken = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"\nactivo = true\npuerto = 8080\n', encoding="utf-8")
    (r / ".gitignore").write_text("secretos.toml\nprivado.txt\n", encoding="utf-8")
    git(r, "init", "-q", "-b", "principal")
    return r


def test_buscar_incluye_listas_y_valores_cortos_pero_no_booleanos_ni_numeros():
    d = {"clave": VALOR, "corto": "abc12345", "ocho": "1234567", "lista": ["lista-secreta-9999", 5, True],
         "bot": {"token": "tok-largo-xxxxxxxx", "activo": True, "puerto": 8080}}
    claves = {c for c, _ in C.buscar(d)}
    assert claves == {"clave", "corto", "lista[0]", "bot.token"}


def test_escanea_y_marca_como_no_auditado_lo_que_no_puede_leer(tmp_path, monkeypatch):
    r = proyecto(tmp_path)
    (r / "a.txt").write_text(f"x {VALOR}", encoding="utf-8")
    (r / "limpio.txt").write_text("nada", encoding="utf-8")
    (r / "sub").mkdir()
    (r / "sub" / "b.txt").write_text("hola", encoding="utf-8")
    original = Path.open

    def lee(self, *a, **k):
        if self.name == "b.txt":
            raise PermissionError("acceso denegado")
        return original(self, *a, **k)
    monkeypatch.setattr(Path, "open", lee)
    valores = C.cargar_valores(r / "secretos.toml")
    res = C.escanear(r, valores)
    assert res["encontrados"] == {"a.txt": ["clave"]}
    assert res["no_auditados"] == ["sub/b.txt"]


def test_un_subarbol_inaccesible_se_marca_entero(tmp_path, monkeypatch):
    r = proyecto(tmp_path)
    (r / "cerrada").mkdir()
    (r / "cerrada" / "c.txt").write_text(VALOR, encoding="utf-8")
    original = Path.iterdir

    def itera(self):
        if self.name == "cerrada":
            raise PermissionError("denegado")
        return original(self)
    monkeypatch.setattr(Path, "iterdir", itera)
    res = C.escanear(r, C.cargar_valores(r / "secretos.toml"))
    assert "cerrada/" in res["no_auditados"] and not res["encontrados"]


def test_versionado_y_gitignore(tmp_path):
    r = proyecto(tmp_path)
    (r / "privado.txt").write_text(VALOR, encoding="utf-8")        # ignorado: no es problema
    (r / "config.txt").write_text(f"k={VALOR}", encoding="utf-8")  # NO ignorado y versionado: problema
    (r / "suelto.txt").write_text(VALOR, encoding="utf-8")         # NO ignorado ni versionado: aviso
    git(r, "add", "config.txt")
    git(r, *FIRMA, "commit", "-qm", "c")
    valores = C.cargar_valores(r / "secretos.toml")
    enc = C.escanear(r, valores)["encontrados"]
    est = C.estado_git(r, enc)
    assert est["versionados"] == ["config.txt"]
    assert est["sin_ignorar"] == ["suelto.txt"]
    assert "privado.txt" not in est["versionados"] + est["sin_ignorar"]


def test_exposicion_historica_aunque_el_archivo_ya_no_este(tmp_path):
    r = proyecto(tmp_path)
    (r / "viejo.txt").write_text(f"k={VALOR}", encoding="utf-8")
    git(r, "add", "viejo.txt")
    git(r, *FIRMA, "commit", "-qm", "mal commit")
    git(r, "rm", "-q", "viejo.txt")
    git(r, *FIRMA, "commit", "-qm", "lo quito")
    h = C.historial(r, C.cargar_valores(r / "secretos.toml"))
    assert list(h) == ["clave"] and len(h["clave"]) >= 2          # lo anade y lo quita: dos commits lo tocan
    assert VALOR not in str(h)


def test_el_informe_no_imprime_valores(tmp_path, capsys):
    r = proyecto(tmp_path)
    (r / "a.txt").write_text(f"x {VALOR}", encoding="utf-8")
    C.informe(r)
    salida = capsys.readouterr().out
    assert "a.txt" in salida and "clave" in salida
    for v in (VALOR, "abc12345", "lista-secreta-9999", "AAAAAAAAAAAA"):
        assert v not in salida


# T709: read_text cargaba el archivo entero (MemoryError con un log de 280 GB). Ahora se lee por bloques con solape.
def test_t709_valor_y_token_cortados_por_la_frontera_de_bloque_se_encuentran(tmp_path, monkeypatch):
    r = proyecto(tmp_path)
    monkeypatch.setattr(C, "BLOQUE", 10)
    token = "987654321:" + "B" * 35
    (r / "grande.txt").write_text("z" * 7 + VALOR + "y" * 13 + " " + token + "q" * 9, encoding="utf-8")
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: (_ for _ in ()).throw(MemoryError()))
    res = C.escanear(r, C.cargar_valores(r / "secretos.toml"))
    assert res["encontrados"] == {"grande.txt": ["clave"]}
    assert res["telegram"] == ["grande.txt"]
    assert res["no_auditados"] == []


def test_t709_archivo_grande_simulado_se_lee_por_bloques(tmp_path):
    r = proyecto(tmp_path)
    with open(r / "enorme.log", "w", encoding="utf-8") as f:
        for _ in range(30):
            f.write("x" * (1 << 20))
        f.write(VALOR)
    res = C.escanear(r, C.cargar_valores(r / "secretos.toml"))
    assert res["encontrados"] == {"enorme.log": ["clave"]}


def test_t709_memoryerror_al_leer_sale_como_no_auditado(tmp_path, monkeypatch):
    r = proyecto(tmp_path)
    (r / "pesa.log").write_text("hola", encoding="utf-8")
    (r / "ok.txt").write_text("hola", encoding="utf-8")
    original = Path.open

    def abre(self, *a, **k):
        if self.name == "pesa.log":
            raise MemoryError()
        return original(self, *a, **k)

    monkeypatch.setattr(Path, "open", abre)
    res = C.escanear(r, C.cargar_valores(r / "secretos.toml"))
    assert res["no_auditados"] == ["pesa.log"]
    assert res["encontrados"] == {}
