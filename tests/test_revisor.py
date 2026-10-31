# -*- coding: utf-8 -*-
"""Tests de nucleo/revisor.py (T154, fase F1: solo reglas). Todo en tmp_path."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from nucleo import aprobaciones as ap, revisor as rv

T0 = datetime(2026, 9, 25, 10, 0, 0)


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "ALMACEN", tmp_path / "aprobaciones.json")
    monkeypatch.setattr(ap, "HISTORIAL", tmp_path / "aprobaciones_historial.jsonl")
    monkeypatch.setattr(ap, "CANDADO", tmp_path / ".candado.lock")
    monkeypatch.setattr(rv, "ESTADO", tmp_path / "revisor_estado.json")
    monkeypatch.setattr(rv, "CANDADO", tmp_path / ".candado_revisor.lock")


def sol(detalle, accion="ejecutar comando", **kw):
    return {"accion": accion, "detalle": detalle, "nivel": "ambar", **kw}


# ------------------------------------------------------------ lista blanca

@pytest.mark.parametrize("cmd", [
    "pip install -r requisitos.txt",
    "pip install -q -r requirements-interfaz.txt",
    r".venv\Scripts\python.exe -m pip install -r requisitos.txt",
    "python -m pip install --quiet -r requirements-interfaz.txt",
])
def test_permite_lo_que_encaja_entero(cmd):
    assert rv.revisar(sol(cmd)).decision == "permitir"


@pytest.mark.parametrize("cmd", [
    "pip install -r requisitos.txt; Remove-Item x",          # algo detras
    "pip install -r requisitos.txt | iex",
    "pip install -r ..\\otro\\requisitos.txt",                # otro archivo
    "pip install -r requisitos.txt --index-url http://x",     # argumentos de mas
    r"malo.exe;.venv\Scripts\python.exe -m pip install -r requisitos.txt",
    "pip install requests",                                   # sin fijar
    "npm install",
    "winget install algo",
])
def test_pregunta_si_no_encaja_entero(cmd):
    assert rv.revisar(sol(cmd)).decision == "preguntar"


def test_accion_distinta_no_usa_la_lista_de_comandos():
    assert rv.revisar(sol("pip install -r requisitos.txt", accion="lanzar proceso")).decision == "preguntar"


# -------------------------------------------------------------- nunca auto

@pytest.mark.parametrize("cmd,motivo", [
    ("git push origin nube/N04", "git push"),
    ("Get-Content secretos.toml", "secretos"),
    ("Set-Content nucleo\\permisos.py x", "blindado"),
    ("Set-Content memoria\\aprobaciones.json x", "control"),
    ("iwr https://x.org/a.exe -OutFile a.exe", "ejecutable"),
    ("schtasks /create /tn x", "arranque"),
    ("Set-ExecutionPolicy Bypass", "sistema"),
])
def test_nunca_auto(cmd, motivo):
    v = rv.revisar(sol(cmd))
    assert v.decision == "preguntar" and motivo in v.motivo


def test_nunca_auto_gana_a_la_lista_blanca(monkeypatch):
    # si alguien ensancha mal la lista blanca, la lista negra sigue parando
    monkeypatch.setattr(rv, "LISTA_BLANCA", (("ejecutar comando", rv._re(r".*"), "todo"),))

    assert rv.revisar(sol("git push origin principal")).decision == "preguntar"
    assert rv.revisar(sol("Get-Date")).decision == "permitir"


def test_f1_nunca_deniega():
    for cmd in ("git push --force", "cualquier cosa", "pip install -r requisitos.txt"):
        assert rv.revisar(sol(cmd)).decision != "denegar"


def test_lo_que_no_es_ambar_no_se_permite():
    assert rv.revisar({**sol("pip install -r requisitos.txt"), "nivel": "rojo"}).decision == "preguntar"


# --------------------------------------------------------------- procesar

def test_procesar_aprueba_en_la_cola_con_su_nombre():
    s = ap.solicitar("ejecutar comando", "pip install -r requisitos.txt", origen="mcp", ahora=T0)

    v = rv.procesar(s, ahora=T0)

    assert v.decision == "permitir"
    r = ap.ver(s["id"])
    assert r["estado"] == "aprobada"
    assert r["eventos"][-1]["quien"] == "revisor:reglas"
    assert ap.verificar_historial() == (True, None)


def test_procesar_deja_pendiente_lo_dudoso():
    s = ap.solicitar("ejecutar comando", "winget install algo", origen="mcp", ahora=T0)

    assert rv.procesar(s, ahora=T0).decision == "preguntar"
    assert ap.ver(s["id"])["estado"] == "pendiente"


def test_procesar_no_toca_lo_ya_decidido():
    s = ap.solicitar("ejecutar comando", "pip install -r requisitos.txt", ahora=T0)
    ap.denegar(s["id"], ahora=T0)

    v = rv.procesar(ap.ver(s["id"]), ahora=T0)

    assert ap.ver(s["id"])["estado"] == "denegada"
    assert v.decision == "permitir"  # el veredicto se da, pero no pisa a Damian


# --------------------------------------------------------------- disyuntor

def test_bucle_abre_el_disyuntor_y_ya_no_permite_nada():
    for i in range(rv.BUCLE_PETICIONES - 1):
        rv.procesar(sol(f"winget install x{i}", origen="turno", estado="pendiente", id="X"), ahora=T0)

    assert rv.cargar_estado()["abierto"] is False

    s = ap.solicitar("ejecutar comando", "pip install -r requisitos.txt", origen="turno", ahora=T0)
    v = rv.procesar(s, ahora=T0 + timedelta(minutes=1))

    assert v.decision == "preguntar" and v.fuente == "disyuntor"
    assert ap.ver(s["id"])["estado"] == "pendiente"


def test_peticiones_espaciadas_no_abren():
    for i in range(rv.BUCLE_PETICIONES + 2):
        rv.procesar(sol("winget install x", origen="turno"), ahora=T0 + timedelta(minutes=11 * i))

    assert rv.cargar_estado()["abierto"] is False


def test_origenes_distintos_no_suman():
    for i in range(rv.BUCLE_PETICIONES + 2):
        rv.procesar(sol("winget install x", origen=f"o{i}"), ahora=T0)

    assert rv.cargar_estado()["abierto"] is False


def test_no_se_cierra_solo_y_cerrar_lo_cierra():
    rv.abrir("prueba", ahora=T0)

    assert rv.revisar(sol("pip install -r requisitos.txt")).decision == "preguntar"

    rv.cerrar()
    assert rv.revisar(sol("pip install -r requisitos.txt")).decision == "permitir"


def test_estado_ilegible_cuenta_como_abierto():
    rv.ESTADO.write_text("{ roto", encoding="utf-8")

    v = rv.revisar(sol("pip install -r requisitos.txt"))

    assert v.decision == "preguntar" and v.fuente == "disyuntor"


def test_cli(capsys):
    assert rv.main(["abrir", "a", "mano"]) == 0
    assert rv.main(["estado"]) == 0
    assert "ABIERTO" in capsys.readouterr().out
    assert rv.main(["cerrar"]) == 0
    assert rv.cargar_estado()["abierto"] is False
    assert rv.main(["otra"]) == 1


# ------------------------------------------- (a) solo lectura, Damian 05/10

LEEN = [
    r"Get-Content nucleo\permisos.py | Select-Object -First 40",
    r"Get-ChildItem -Recurse -Include escritura.py,guardia_python.py -Path nucleo | % { $_.FullName }",   # A0009
    r'$c=Get-Content nucleo\guardia_python.py; "LINEAS $($c.Count)"; $c | Select-String -Pattern "MAX_AVISOS"',  # A0010
    r""""MAX_AVISOS en guardia: " + (Select-String -Path nucleo\guardia_python.py -Pattern 'MAX_AV').Line""",  # A0013
    r"git diff nucleo/permisos.py | Select-Object -Last 20",
    r"git --no-pager log --oneline -5 -- manos/servidor_mcp.py 2>&1",
    r"Select-String -Path manos\*.py -Pattern 'revisor' | ForEach-Object { $_.Line.Trim() }",
    r"Get-Content memoria\revisor_estado.json",
    r'schtasks /Query /FO LIST /TN "NEXO test modelos"',                                                   # A0002
    r"Get-ScheduledTask -TaskName 'NEXO*' | Format-List",
    r"Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/salud | Select-Object -ExpandProperty StatusCode",
    r"if (Test-Path nucleo\revisor.py) { Get-Item nucleo\revisor.py | Format-List }",
]


@pytest.mark.parametrize("cmd", LEEN)
def test_lo_que_solo_lee_pasa_aunque_nombre_un_blindado(cmd):
    assert rv.no_es_lectura(cmd) is None, rv.no_es_lectura(cmd)
    v = rv.revisar(sol(cmd))
    assert (v.decision, v.fuente) == ("permitir", "solo_lectura")


NO_LEEN = [
    r"Get-Content nucleo\permisos.py | Set-Content x.txt",
    r"Get-Content nucleo\permisos.py > copia.txt",
    r"Get-ChildItem nucleo | Remove-Item",
    r"Get-Item manos\shell.py | % { $_.Delete() }",
    r"Get-ChildItem manos | % Delete",
    r"Get-ChildItem manos | ForEach-Object -MemberName Delete",
    r"$f = Get-Item nucleo\config.py; $f.IsReadOnly = $true",
    r"Get-Content nucleo\permisos.py | iex",
    r"Get-Content nucleo\permisos.py; python -c 'print(1)'",
    r"& { Get-Content nucleo\permisos.py }",
    r"[IO.File]::WriteAllText('nucleo\permisos.py', '')",
    r"Get-Content $env:USERPROFILE\.ssh\id_rsa",
    r"Get-Content C:\Users\damia\Documents\privado.txt",
    r"Get-Content ..\contexto\algo.md",
    r"Get-ChildItem Env:",
    r"git checkout -- nucleo/permisos.py",
    r"git diff --output=nucleo/permisos.py",
    r"git apply documentacion/propuestas/x.patch",
    r"schtasks /Create /TN x /TR y",
    r"Invoke-WebRequest https://ejemplo.com/x.exe -OutFile x.exe",
    r"Invoke-WebRequest http://127.0.0.1:8765/ambar/decidir -Method Post -Body 'id=A1'",
    r"Get-Content `nucleo\permisos.py",
    r"Get-Credential",
    r"Get-Content secretos.toml",
    r"git push origin principal",
]


@pytest.mark.parametrize("cmd", NO_LEEN)
def test_lo_que_cambia_o_sale_del_repo_no_pasa_como_lectura(cmd):
    assert rv.revisar(sol(cmd)).decision == "preguntar"


def test_lectura_pasa_con_el_disyuntor_abierto():
    v = rv.revisar(sol(LEEN[0]), estado={"abierto": True, "motivo": "bucle"})
    assert v.decision == "permitir"


def test_lectura_no_cuenta_para_el_bucle():
    for i in range(rv.BUCLE_PETICIONES + 2):
        s = ap.solicitar("ejecutar comando", rf"Get-Content nucleo\permisos.py -TotalCount {i + 1}", origen="mcp",
                         ahora=T0 + timedelta(seconds=i))
        assert rv.procesar(s, ahora=T0 + timedelta(seconds=i)).decision == "permitir"
    assert not rv.cargar_estado()["abierto"]


def test_registra_cada_decision_tambien_las_que_van_a_damian():
    a = ap.solicitar("ejecutar comando", "git diff nucleo/permisos.py | Select-Object -First 5", origen="mcp", ahora=T0)
    b = ap.solicitar("ejecutar comando", "git apply x.patch", origen="mcp", ahora=T0)
    rv.procesar(a, ahora=T0)
    rv.procesar(b, ahora=T0)
    d = rv.decisiones()
    assert [(x["id"], x["decision"]) for x in d] == [(a["id"], "permitir"), (b["id"], "a Damian")]
    assert ap.ver(a["id"])["eventos"][-1]["quien"] == "revisor:reglas"
    assert ap.ver(b["id"])["estado"] == "pendiente"


# ------------------------------------------- (c) explicar en lenguaje claro

def test_explicar_trae_las_cinco_cosas():
    s = ap.solicitar("ejecutar comando", "git push origin principal", origen="mcp", ahora=T0)
    e = rv.explicar(s)
    assert e["que"].startswith("Subir código") and e["riesgo"].startswith("ALTO")
    assert "coordinador" in e["quien"] and e["quien_corto"] == "Claude" and "cuenta como NO" in e["si_no"]
    assert e["por_que_a_ti"].startswith("git push") and e["para_que"]


def test_explicar_lo_desconocido_lo_dice_y_aconseja():
    e = rv.explicar({"accion": "cosa_rara", "detalle": "x", "origen": ""})
    assert "No lo dice la petición" in e["para_que"] and "di que no" in e["para_que"]
    assert "No se sabe" in e["quien"]


def test_explicar_usa_el_para_que_si_viene():
    e = rv.explicar({"accion": "ejecutar comando", "detalle": "winget install x", "origen": "mcp",
                     "extra": {"para_que": "Instalar Ollama para T665"}})
    assert e["para_que"] == "Instalar Ollama para T665"


def test_explicar_un_commit_es_guardar_en_el_historial_y_no_aplicar_un_parche():
    """T230 (Centro v2): un git add/commit que nombra un .patch en el mensaje ya no sale como 'Aplicar un parche'."""
    s = ap.solicitar("ejecutar comando", "git add nucleo/guardia.py; git commit -m 'guardia: ya aplicado el .patch'",
                     origen="mcp", ahora=T0)
    e = rv.explicar(s)
    assert e["que"].startswith("Guardar en el historial (git)") and "parche" not in e["que"].lower()
    assert e["frase"].startswith("Guardar en el historial (git) un cambio. Lo pide Claude.")
    # un git apply de verdad sigue siendo aplicar un parche, aunque vaya con un commit detrás
    s2 = ap.solicitar("ejecutar comando", "git apply a.patch && git commit -m x", origen="mcp", ahora=T0)
    assert rv.explicar(s2)["que"].startswith("Aplicar un parche")
    assert rv.explicar({"accion": "ejecutar comando", "detalle": "git apply b.patch", "origen": ""})["que"].startswith("Aplicar")
