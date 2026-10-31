# -*- coding: utf-8 -*-
"""T1020: guardian de aprobaciones (nucleo/guardian.py). Casos reales del 18/10 y una regla por caso."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from nucleo import aprobaciones as ap
from nucleo import guardian as G
from nucleo import revisor

RAIZ = G.RAIZ
EXTERNAS = G.EXTERNAS

# Las tres de Damian del 18/10 (17:14), literales: las denego porque no las entendia; son lecturas.
A0064 = (".venv\\Scripts\\python.exe -c \"import json; d=json.load(open('memoria/aprobaciones.json',encoding='utf-8')); "
         "it=d if isinstance(d,list) else d.get('solicitudes',d.get('items',list(d.values()))); "
         "[print(json.dumps({k:(str(v)[:300]) for k,v in s.items() if k in ('id','estado','creada','accion','detalle',"
         "'motivo','origen','resuelta','tipo')},ensure_ascii=False)) for s in it if isinstance(s,dict) and "
         "('MiroFish' in json.dumps(s,ensure_ascii=False) or s.get('id')=='A0062')]\"")
A0065 = ("Select-String -Path memoria\\aprobaciones.json -Pattern 'MiroFish' -Context 6,6 | Select-Object -First 3 | "
         "ForEach-Object { ($_.Context.PreContext + $_.Line + $_.Context.PostContext) -join \"`n\" } | "
         "ForEach-Object { $_.Substring(0,[Math]::Min(2500,$_.Length)) }")
A0066 = str(EXTERNAS / "MiroFish" / ".env.example")


@pytest.fixture
def cola(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "ALMACEN", tmp_path / "aprobaciones.json")
    monkeypatch.setattr(ap, "HISTORIAL", tmp_path / "aprobaciones_historial.jsonl")
    monkeypatch.setattr(ap, "CANDADO", tmp_path / ".candado_aprobaciones.lock")
    monkeypatch.setattr(revisor, "ESTADO", tmp_path / "revisor_estado.json")
    monkeypatch.setattr(revisor, "CANDADO", tmp_path / ".candado_revisor.lock")
    monkeypatch.setattr(G, "GANCHO", True)
    return tmp_path


def _pedir(accion, detalle, **kw):
    return ap.solicitar(accion, detalle, origen=kw.pop("origen", "mcp"), **kw)


# ------------------------------------------------------------------ regla 2: aprueba solo (casos reales)
@pytest.mark.parametrize("accion, detalle", [("ejecutar comando", A0064), ("ejecutar comando", A0065),
                                             ("leer", A0066)], ids=["A0064", "A0065", "A0066"])
def test_casos_reales_18_10_se_aprueban_solos(cola, accion, detalle):
    s = _pedir(accion, detalle)
    assert s["estado"] == "aprobada" and s["decidida_por"] == "guardian"
    ex = s["extra"]["explicacion"]
    assert ex["regla"] == "solo" and ex["tipo"] == "lee" and ex["decision_guardian"] == "aprobada"
    assert "sin clasificar" not in str(ex).lower()
    ultimo = [h for h in ap.historial() if h["id"] == s["id"]][-1]
    assert ultimo["tipo"] == "aprobada" and ultimo["quien"] == "guardian" and ultimo["motivo"]
    assert G.decisiones()[-1]["decision"] == "aprobada"
    # quien pide puede gastarla (lo que hara manos/servidor_mcp.py con el diff de la pieza 4)
    assert ap.consumir(s["id"], accion, detalle)["estado"] == "usada"


def test_env_example_es_plantilla_y_env_real_es_secreto(cola):
    ex = G.ficha(ap.ver(_pedir("leer", A0066)["id"]))
    assert ex["sobre"][0]["papel"].startswith("plantilla")
    s = _pedir("leer", str(EXTERNAS / "MiroFish" / ".env"))
    assert s["estado"] == "pendiente" and s["extra"]["explicacion"]["regla"] == "siempre"


# ------------------------------------------------------------------ regla 1: siempre Damian
@pytest.mark.parametrize("detalle", [
    "Get-Content secretos.toml",
    "Get-Content memoria\\perfil_privado\\perfil.md | Select-Object -First 5",
    "Select-String -Path *.toml -Pattern clave",                              # el comodin abarca secretos.toml
    ".venv\\Scripts\\python.exe -c \"print(open('memoria/perfil_privado/x.md').read())\"",
])
def test_lecturas_de_secretos_o_privado_van_a_damian(cola, detalle):
    s = _pedir("ejecutar comando", detalle)
    assert s["estado"] == "pendiente"
    assert s["extra"]["explicacion"]["regla"] == "siempre"
    assert "NO" in s["extra"]["explicacion"]["recomendacion"] or "privad" in s["extra"]["explicacion"]["recomendacion"]


def test_remove_item_de_contenido_va_a_damian(cola):
    s = _pedir("ejecutar comando", "Remove-Item documentacion\\notas_viejas.md")
    ex = s["extra"]["explicacion"]
    assert s["estado"] == "pendiente" and ex["regla"] == "siempre" and ex["tipo"] == "borra"
    assert ex["deshacer"].startswith("No") and "copia" in ex["recomendacion"]


def test_git_apply_sobre_un_blindado_va_a_damian(cola):
    parche = RAIZ / "documentacion" / "diffs" / "guardia_T830_T832_T841.patch"   # el real del 18/10 (permisos.py)
    assert parche.is_file()
    s = _pedir("ejecutar comando", "git apply documentacion/diffs/guardia_T830_T832_T841.patch")
    ex = s["extra"]["explicacion"]
    assert s["estado"] == "pendiente" and ex["regla"] == "siempre" and "nucleo/permisos.py" in ex["motivo_regla"]


def test_git_apply_de_un_parche_ilegible_va_a_damian(cola):
    s = _pedir("ejecutar comando", "git apply documentacion/diffs/no_existe.patch")
    assert s["extra"]["explicacion"]["regla"] == "siempre"


@pytest.mark.parametrize("accion, detalle", [
    ("ejecutar comando", "git push origin principal"),
    ("ejecutar comando", ".venv\\Scripts\\python.exe -m nucleo.aprobaciones aprobar A0001"),   # aprobarse a si mismo
    ("escribir", str(RAIZ / "nucleo" / "permisos.py") + " sha256:abc"),
    ("escribir", str(RAIZ / "nucleo" / "guardian.py") + " sha256:abc"),
])
def test_controles_y_git_push_van_a_damian(cola, accion, detalle):
    assert _pedir(accion, detalle)["extra"]["explicacion"]["regla"] == "siempre"


# ------------------------------------------------------------------ regla 3: tribunal
@pytest.mark.parametrize("accion, detalle", [
    ("archivar", str(RAIZ / "herramientas_nube" / "_aparcar_T697.py")),
    ("escribir", str(RAIZ / "documentacion" / "nota.md") + " sha256:abc"),
    ("ejecutar comando", "Remove-Item -Recurse nucleo\\__pycache__"),
    ("ejecutar comando", "git add documentacion/x.md; git commit -m \"doc\""),
    ("lanzar proceso", ".venv\\Scripts\\python.exe " + str(RAIZ / "nucleo" / "guardia_python.py")
     + " herramientas_nube\\publicar_nube.py"),
])
def test_reversibles_van_al_tribunal_y_no_a_damian(cola, accion, detalle):
    s = _pedir(accion, detalle)
    assert s["estado"] == "pendiente" and s["tribunal"] == {**s["tribunal"], "estado": "pendiente", "via": "guardian"}
    assert s["extra"]["explicacion"]["regla"] == "tribunal"
    assert G.para_damian(ap.pendientes()) == []          # mientras el tribunal mira, no sale en Te toca
    assert [x["id"] for x in G.tribunal_pendientes()] == [s["id"]]


def _dictamenes(*votos):
    fams = ("alibaba", "google", "nvidia")
    return [{"id": f"x{i}", "familia": fams[i], "voto": v, "motivo": "m", "cuando": ""} for i, v in enumerate(votos)]


def test_tribunal_unanime_aprueba_y_solo_usa_api(cola, monkeypatch):
    from nucleo import tribunal_r1
    llamadas = []

    def reunir(tarea, limite, texto=None, web=True):
        llamadas.append((texto, web))
        return _dictamenes("APROBAR", "APROBAR", "APROBAR"), []
    monkeypatch.setattr(tribunal_r1, "_reunir", reunir)
    s = _pedir("archivar", str(RAIZ / "herramientas_nube" / "_aparcar_T697.py"), extra={"motivo": "limpieza"})
    r = G.trabajar(limite_s=30)
    assert r["tribunal"] == {s["id"]: "aprobar"}
    final = ap.ver(s["id"])
    assert final["estado"] == "aprobada" and final["decidida_por"] == "tribunal"
    texto, web = llamadas[0]
    assert web is False and "limpieza" in texto and "VOTO: APROBAR|VETAR" in texto
    assert "users" not in texto.lower() and "[privado]" in texto   # auditor.tapar: la ruta del usuario no sale del PC


def test_tribunal_dividido_llega_a_damian_explicado(cola, monkeypatch):
    from nucleo import tribunal_r1
    monkeypatch.setattr(tribunal_r1, "_reunir", lambda *a, **k: (_dictamenes("APROBAR", "VETAR", "APROBAR"), []))
    s = _pedir("archivar", str(RAIZ / "herramientas_nube" / "_aparcar_T697.py"))
    G.trabajar(limite_s=30)
    final = ap.ver(s["id"])
    assert final["estado"] == "pendiente" and final["tribunal"]["estado"] == "bandeja"
    assert final["vence"] == s["vence"]                  # lo ambar no cambia de plazo (eso es solo de los vetos R1)
    ex = G.explicacion(final)
    assert "Decides tú" in ex["recomendacion"] and len(ex["dictamenes"]) == 3
    assert [x["id"] for x in G.para_damian(ap.pendientes())] == [s["id"]]


def test_tribunal_que_no_contesta_pasa_a_damian(cola):
    s = _pedir("archivar", str(RAIZ / "herramientas_nube" / "_aparcar_T697.py"))
    hechos = G.barrer(datetime.now() + G.ESPERA_TRIBUNAL + timedelta(minutes=1))
    assert hechos["a_damian"] == [s["id"]]
    assert ap.ver(s["id"])["tribunal"]["estado"] == "bandeja"


def test_r2_solo_va_al_tribunal_con_la_puerta_en_verde(cola):
    extra = {"tarea": "T1", "titulo": "x", "motivos": ["nucleo/x.py: codigo o ruta no clasificada"]}
    sin = ap.solicitar("fusionar T1", "R2 sha256:a", nivel="R2", origen="riesgo", extra=extra)
    con = ap.solicitar("fusionar T1", "R2 sha256:b", nivel="R2", origen="riesgo", extra={**extra, "puerta_ok": True})
    assert "tribunal" not in sin and sin["extra"]["explicacion"]["regla"] == "resto"
    assert con["tribunal"]["estado"] == "pendiente" and con["extra"]["explicacion"]["regla"] == "tribunal"


def test_r1_solo_se_explica(cola):
    s = ap.solicitar("implementar T1", "x", nivel="R1", origen="riesgo", tipo="veto", extra={"tarea": "T1"},
                     espera_tribunal=ap.ESPERA_TRIBUNAL)
    assert s["estado"] == "pendiente" and s["tribunal"] == {"estado": "pendiente"}   # sigue siendo de tribunal_r1
    assert s["extra"]["explicacion"]["regla"] == "r1"


# ------------------------------------------------------------------ interruptor y revisor
def test_apagado_todo_a_damian_con_ficha_y_al_encender_se_rehace(cola):
    G.poner_activo(False, quien="test")
    s = _pedir("ejecutar comando", A0065)
    assert s["estado"] == "pendiente" and s["extra"]["explicacion"]["decision_guardian"] == "apagado"
    assert revisor.procesar(ap.ver(s["id"])).decision == "preguntar"   # el revisor tampoco aprueba
    G.poner_activo(True, quien="test")
    G.barrer()
    assert ap.ver(s["id"])["estado"] == "aprobada"


def test_archivo_del_interruptor_roto_cuenta_como_apagado(cola):
    G.ESTADO.write_text("{roto", encoding="utf-8")
    assert G.activo() is False


def test_el_revisor_ya_no_aprueba_lecturas_de_lo_privado(cola, monkeypatch):
    monkeypatch.setattr(G, "GANCHO", False)
    s = _pedir("ejecutar comando", "Get-Content memoria\\perfil_privado\\perfil.md")
    assert revisor.procesar(s).decision == "preguntar"
    assert ap.ver(s["id"])["estado"] == "pendiente"
    s2 = _pedir("ejecutar comando", "Get-Content nucleo\\permisos.py | Select-Object -First 5")
    assert revisor.procesar(s2).decision == "permitir"   # leer un blindado sigue pasando (Damian 05/10)


def test_un_guardian_roto_no_impide_pedir(cola, monkeypatch):
    def roto(s):
        raise RuntimeError("x")
    monkeypatch.setattr(G, "al_solicitar", roto)
    assert _pedir("ejecutar comando", A0065)["estado"] == "pendiente"


# ------------------------------------------------------------------ analisis de python -c y PowerShell
@pytest.mark.parametrize("codigo, motivo", [
    ("import os; os.remove('x')", "importa os"),
    ("f = open('x.txt', 'w')", "escribir"), ("open('x.txt').write('a')", "write"),
    ("print(open('secre'+'tos.toml').read())", "se calcula"),
    ("().__class__.__base__", "internos"),
    ("from pathlib import Path; [p.read_text() for p in Path('.').rglob('*')]", ""),
    ("import json; json.load(open('memoria/x.json', encoding='utf-8'))", None),
    ("from pathlib import Path; print(Path('memoria/x.json').read_text()[:10].replace('a', 'b'))", None),
])
def test_python_c_solo_lee(codigo, motivo):
    r = G.python_solo_lee(codigo)
    if motivo is None:
        assert r is None
    else:
        assert r is not None and motivo in r


@pytest.mark.parametrize("cmd", [
    "Get-ChildItem -Recurse memoria | Select-String clave",          # recorre lo privado tambien
    "$p = 'memoria\\x'; Get-Content $p",                               # ruta calculada
    "Get-Content memoria\\x.json | Out-File y.txt",
])
def test_powershell_dudoso_no_es_lectura(cmd):
    assert G.comando_solo_lee(cmd) is not None


# ------------------------------------------------------------------ fichas, Qwen, barrido y Centro
@pytest.mark.parametrize("accion, detalle, nivel", [
    ("ejecutar comando", "algo-raro --x", "ambar"), ("lanzar proceso", "notepad.exe", "ambar"),
    ("cwd", "Z:\\otra", "ambar"), ("chat_tarea:titulo:T1", "{}", "ambar"), ("otra cosa", "x", "ambar"),
    ("fusionar T1", "R2 sha256:x", "R2"),
])
def test_ninguna_ficha_dice_sin_clasificar(accion, detalle, nivel):
    ex = G.ficha({"id": "A0001", "accion": accion, "detalle": detalle, "nivel": nivel, "origen": "mcp",
                  "extra": {"tarea": "T1", "titulo": "t"}})
    assert "sin clasificar" not in str(ex).lower()
    assert ex["que"] and ex["tipo_llano"] and ex["deshacer"] and ex["recomendacion"] and ex["riesgo"].split(":")[0] in (
        "BAJO", "MEDIO", "ALTO")
    assert ex["para_que"] == "No lo ha dicho."


def test_ficha_lleva_el_motivo_de_quien_lo_pide(cola):
    s = _pedir("ejecutar comando", "Remove-Item documentacion\\x.md", extra={"motivo": "limpiar notas"})
    assert G.explicacion(s)["para_que"] == "limpiar notas"


def test_qwen_redacta_y_se_guarda_fuera_de_la_huella(cola, monkeypatch):
    prompts = []
    monkeypatch.setattr(G, "_qwen", lambda p: prompts.append(p) or "Borrar una nota vieja de la documentación")
    s = _pedir("ejecutar comando", "Remove-Item " + str(RAIZ / "documentacion" / "x.md"))
    assert G.trabajar(limite_s=30)["frases"] == 1
    final = ap.ver(s["id"])
    assert final["huella"] == s["huella"] and final["extra"]["explicacion"]["frase_llana"].startswith("Borrar una nota")
    assert G.explicacion(final)["que"].startswith("Borrar una nota")
    assert "users" not in prompts[0].lower()
    assert (G.MODELO_QWEN, G.NUM_CTX, G.NUM_PREDICT) == ("qwen2.5:7b", 4096, 120)
    assert G.trabajar(limite_s=30)["frases"] == 0          # no se reintenta en bucle


def test_barrido_cada_minuto_y_lanza_el_trabajo_de_fondo(cola, monkeypatch):
    lanzados = []
    monkeypatch.setattr(G, "LANZADOR", lambda: lanzados.append(1) or 4321)
    monkeypatch.setattr(G, "_vivo", lambda pid: False)
    monkeypatch.setattr(G, "GANCHO", False)                # el gancho fallo: lo recoge el barrido
    s = _pedir("archivar", str(RAIZ / "herramientas_nube" / "_aparcar_T697.py"))
    assert "explicacion" not in (s.get("extra") or {})
    ahora = datetime.now().replace(microsecond=0)
    assert "lanzado" in G.barrido_si_toca(ahora)
    assert ap.ver(s["id"])["tribunal"]["estado"] == "pendiente" and lanzados == [1]
    assert G.barrido_si_toca(ahora + timedelta(seconds=30)) is None
    monkeypatch.setattr(G, "_vivo", lambda pid: pid == 4321)
    assert "en marcha" in G.barrido_si_toca(ahora + timedelta(seconds=61)) and lanzados == [1]


def test_resueltos_desde_para_hecho_desde_tu_visita(cola):
    antes = datetime.now() - timedelta(minutes=1)
    s = _pedir("ejecutar comando", A0065)
    _pedir("ejecutar comando", "Remove-Item documentacion\\x.md")
    r = G.resueltos_desde(antes)
    assert [x["id"] for x in r] == [s["id"]] and r[0]["aprobada"] and r[0]["quien"] == "NEXO solo"
    assert r[0]["enlace"] == f"/aprobacion/{s['id']}"


def test_git_checkout_no_es_dinero():
    a = G.analizar({"accion": "ejecutar comando", "nivel": "ambar",
                    "detalle": "git checkout HEAD -- documentacion/x.md"})
    assert "dinero" not in a["motivo"] and a["regla"] == "resto"
