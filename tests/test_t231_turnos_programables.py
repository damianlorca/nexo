# -*- coding: utf-8 -*-
"""T231: turnos programables (plantillas, horario en Windows, lanzar ya, solo lectura) y vigia de novedades (T272).

Sin red, sin Chrome y sin PowerShell real: el Programador de tareas es un doble que guarda los disparadores
que le mandan y los devuelve al leer (asi se comprueba que el horario cambiado "se refleja en la tarea").
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime

import pytest

from nucleo import auditor, avisos, plantillas_turno, trabajo, turnos, vigia
from nucleo import tareas as T
from tests.test_ok_absoluto import CAMBIOS, CIERRE_OK, PROP, REV_CAMBIOS, REV_OK, Api, Web


@pytest.fixture
def cola(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "x.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado")
    monkeypatch.setattr(trabajo, "BORRADORES", tmp_path / "borradores")
    from nucleo import revision
    monkeypatch.setattr(revision, "BORRADORES", tmp_path / "borradores")
    monkeypatch.setattr(trabajo, "_web", lambda: True)
    return tmp_path


@pytest.fixture
def proyecto(tmp_path, monkeypatch):
    """Un proyecto de juguete (sin .git: recorrido por carpetas) como RAIZ de las plantillas."""
    raiz = tmp_path / "proyecto"
    (raiz / "nucleo").mkdir(parents=True)
    (raiz / "memoria").mkdir()
    (raiz / ".venv" / "lib").mkdir(parents=True)
    (raiz / "nucleo" / "a.py").write_text("def a():\n    return 1  # correo: x@y.com\n", encoding="utf-8")
    (raiz / "nucleo" / "b.py").write_text("\n".join(f"x{i} = {i}" for i in range(4000)) + "\n", encoding="utf-8")
    (raiz / "principal.py").write_text("import nucleo\nprint('ruta C:\\\\Users\\\\alguien')\n", encoding="utf-8")
    (raiz / ".venv" / "lib" / "fuera.py").write_text("no\n", encoding="utf-8")
    (raiz / "README.md").write_text("# Proyecto\nUsa secretos.toml para las claves.\n", encoding="utf-8")
    (raiz / "memoria" / "notas.md").write_text("nota\n", encoding="utf-8")
    (raiz / "memoria" / "tareas.md").write_text("privado\n", encoding="utf-8")
    (raiz / "memoria" / "becas.md").write_text("privado\n", encoding="utf-8")
    monkeypatch.setattr(plantillas_turno, "RAIZ", raiz)
    return raiz


# ------------------------------------------------------------------ plantillas
def test_siete_plantillas_y_textos_editables():
    # T667: + tribunal de revision
    assert set(turnos.PLANTILLAS) == {"cola", "revisar_codigo", "revisar_archivos", "investigacion", "correcciones",
                                      "vigia", "tribunal", "implementador", "radar",   # T693: + radar
                                      "modelos",                                     # T320: + banco diario
                                      "reels",                                       # T859: + lote de reels
                                      "kuzushi"}                                     # T1011: + Kuzushi (sin IA)
    assert [p["id"] for p in turnos.plantillas() if p["solo_lectura"]] == ["revisar_codigo", "revisar_archivos", "vigia"]
    turnos.editar_texto("vigia", "Solo modelos gratis nuevos.")
    assert turnos.texto_plantilla("vigia") == "Solo modelos gratis nuevos."
    turnos.editar_texto("vigia", "")
    assert turnos.texto_plantilla("vigia") == turnos.PLANTILLAS["vigia"]["texto"]


def _turno(**campos):
    base = {"nombre": "Prueba", "plantilla": "cola", "dias": list(turnos.DIAS), "horas": ["03:30"]}
    return turnos.guardar_turno(dict(base, **campos))


# ------------------------------------------------------------------ la plantilla elegida llega al turno
def test_plantilla_elegida_llega_al_prompt(cola, monkeypatch):
    T.anadir("Investigar la libreria X", depende="ia", etiquetas=["cat:investigacion"], detalle="Evaluar X.")
    t = _turno(plantilla="investigacion", instrucciones="Prioriza fuentes oficiales y fechas de 2026.")
    lista = plantillas_turno.preparar(turnos.contexto(t))
    autor = Web("chatgpt", "ENTENDIMIENTO:\nx\n### INFORME\n" + "Informe de X. " * 30 + PROP, CIERRE_OK)
    monkeypatch.setattr(trabajo, "_generadores", lambda cat: [autor])
    monkeypatch.setattr(trabajo, "_revisores", lambda n: [Api("gemini_api", REV_OK)])
    [fila] = trabajo.ciclo(max_tareas=1, lista=lista)
    assert "INDICACIONES DE ESTE TURNO: Prioriza fuentes oficiales y fechas de 2026." in autor.llamadas[0]["prompt"]
    assert fila["veredicto"] == "OK_ABSOLUTO" and fila["auditoria"] == "APROBADA" and fila["revision_claude"]


def test_turno_entero_usa_la_plantilla_y_avisa_por_push(cola, monkeypatch):
    import turno_nexo
    T.anadir("Investigar la libreria X", depende="ia", etiquetas=["cat:investigacion"], detalle="Evaluar X.")
    T.anadir("Redactar el README", depende="ia", etiquetas=["cat:redaccion"], detalle="Texto corto.")
    t = _turno(nombre="Investigar de noche", plantilla="investigacion")
    vistos = []
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: None)
    monkeypatch.setattr(turno_nexo, "ram_libre_gb", lambda: 32.0)
    monkeypatch.setattr(trabajo, "ciclo", lambda **k: vistos.append(k) or [
        {"tarea": t["id"], "titulo": t["titulo"], "veredicto": "OK_ABSOLUTO", "auditoria": "APROBADA",
         "propuestas": ["T900"], "intentos": []} for t in k["lista"]])
    reg = turno_nexo.turno(turno_id=t["id"])
    assert reg["plantilla"] == "investigacion" and reg["turno_id"] == t["id"] and not reg.get("abortado")
    assert [t["titulo"] for t in vistos[0]["lista"]] == ["Investigar la libreria X"]   # la redaccion no entra
    assert vistos[0]["lista"][0]["_indicaciones"] == turnos.PLANTILLAS["investigacion"]["texto"]
    [aviso] = avisos.recientes()
    assert aviso["titulo"] == "Turno terminado: Investigar de noche" and aviso["ruta"] == "/turnos" and "1 propuesta" in aviso["cuerpo"]
    datos = json.loads(open(reg["registro"], encoding="utf-8").read())
    assert datos["aviso_push"] is True and datos["instrucciones"]


def test_tareas_concretas_y_no_delegables(cola):
    a = T.anadir("Arreglar el error de la cola al guardar", depende="ia", etiquetas=["cat:codigo"],
                 detalle="Falla nucleo/tareas.py al guardar.")
    b = T.anadir("Disenar el router v3", depende="ia", etiquetas=["cat:arquitectura"], detalle="Plan.")
    c = T.anadir("Investigar Y", depende="ia", etiquetas=["cat:investigacion"], detalle="Y.")
    ctx = dict(turnos.contexto(), tareas=[b["id"], a["id"], c["id"], "T999"])
    lista = plantillas_turno.preparar(ctx)
    assert [(t["id"], t["_cat"], t.get("_formato")) for t in lista] == [
        (b["id"], "investigacion", "analisis"), (a["id"], "investigacion", "correccion")]   # tope 2, en su orden
    assert "material:interno" in lista[0]["etiquetas"] and "material:interno" not in T.buscar(b["id"])["etiquetas"]
    inst = trabajo._instruccion(lista[1], "investigacion")
    assert "Diagnostico" in inst and "NO modifiques ni apliques nada" in inst and "PROPUESTAS IMPLEMENTABLES" in inst


def test_correcciones_solo_coge_errores_de_codigo(cola):
    T.anadir("Investigar Z", depende="ia", etiquetas=["cat:investigacion"])
    T.anadir("Nueva pantalla de ajustes", depende="ia", etiquetas=["cat:codigo"])
    err = T.anadir("Bug: el turno no respeta la parada", depende="ia", etiquetas=["cat:codigo"])
    ctx = dict(turnos.contexto(), plantilla="correcciones", texto=turnos.texto_plantilla("correcciones"))
    assert [t["id"] for t in plantillas_turno.preparar(ctx)] == [err["id"]]


# ------------------------------------------------------------------ revisar codigo y archivos
def test_lotes_de_codigo_recorren_el_proyecto_con_cursor(cola, proyecto):
    assert plantillas_turno.archivos("revisar_codigo") == ["nucleo/a.py", "nucleo/b.py", "principal.py"]
    assert plantillas_turno.archivos("revisar_archivos") == ["README.md", "memoria/notas.md"]
    piezas = plantillas_turno.piezas("revisar_codigo")
    assert len([p for p in piezas if p[0] == "nucleo/b.py"]) >= 2          # archivo grande partido
    vistos = []
    for _ in range(len(piezas) + 1):
        vistos += plantillas_turno.siguiente_lote("revisar_codigo")
    assert {p[0] for p in vistos} == {"nucleo/a.py", "nucleo/b.py", "principal.py"}
    assert json.loads(plantillas_turno.ESTADO.read_text(encoding="utf-8"))["vueltas"]["revisar_codigo"] >= 1


def test_lote_de_revision_instruccion_y_material_sin_datos_privados(cola, proyecto):
    ctx = dict(turnos.contexto(), plantilla="revisar_codigo", texto=turnos.texto_plantilla("revisar_codigo"),
               max_tareas=1)
    [t] = plantillas_turno.preparar(ctx)
    guardada = T.buscar(t["id"])
    assert "plantilla:revisar_codigo" in guardada["etiquetas"] and "material:interno" in guardada["etiquetas"]
    assert "PIEZAS: nucleo/a.py:1-2" in guardada["detalle"] and "def a()" not in guardada["detalle"]
    prompt = trabajo._prompt_gen(t, "investigacion")
    assert "1| def a():" in prompt and "x@y.com" not in prompt and "[omitido]" in prompt
    assert turnos.PLANTILLAS["revisar_codigo"]["texto"][:40] in prompt and "PROPUESTAS IMPLEMENTABLES" in prompt
    assert auditor.revisar_prompt(prompt, "generar", interno=True) == []    # el auditor lo deja salir


def test_lote_fallido_se_reintenta_antes_de_crear_otro(cola, proyecto):
    ctx = dict(turnos.contexto(), plantilla="revisar_archivos", texto="x", max_tareas=1)
    [t1] = plantillas_turno.preparar(ctx)
    [t2] = plantillas_turno.preparar(ctx)
    assert t1["id"] == t2["id"]


def _turno_revisar(monkeypatch, ciclo):
    import turno_nexo
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: None)
    monkeypatch.setattr(turno_nexo, "ram_libre_gb", lambda: 32.0)
    monkeypatch.setattr(trabajo, "ciclo", ciclo)
    t = _turno(plantilla="revisar_codigo", max_tareas=1)
    return turno_nexo.turno(turno_id=t["id"])


# T675 fase 2: los turnos de revision solo crean propuestas con archivo:linea y TEST.
PROP_EVIDENCIA = ("\n### PROPUESTAS IMPLEMENTABLES\n- QUE: arreglar a() | DONDE: nucleo/a.py:2 | "
                  "TEST: tests/test_a.py::test_a | VALOR: 4 | ESFUERZO: 1 | RIESGO: bajo: una linea\n")


def test_turno_de_solo_lectura_no_modifica_archivos(cola, proyecto, monkeypatch):
    """Turno de revision de punta a punta con el OK absoluto REAL (dobles de proveedor): el proyecto queda igual."""
    antes = plantillas_turno.foto(proyecto)
    informe = ("ENTENDIMIENTO:\nrevisar\n### INFORME\n1) Revisado nucleo/a.py.\n2) Hallazgos: a.py linea 2 "
               "devuelve siempre 1. " * 5 + PROP_EVIDENCIA)
    autor = Web("chatgpt", informe, informe.split("### INFORME\n")[1] + CAMBIOS, CIERRE_OK)
    monkeypatch.setattr(trabajo, "_generadores", lambda cat: [autor])
    monkeypatch.setattr(trabajo, "_revisores", lambda n: [Api("gemini_api", REV_CAMBIOS, REV_OK)])
    reg = _turno_revisar(monkeypatch, trabajo.ciclo)
    assert plantillas_turno.foto(proyecto) == antes
    assert reg["solo_lectura"] == {"ok": True, "cambiados": [], "metodo": "escrituras del propio turno"}
    [fila] = reg["pasos"]["trabajo"]["filas"]
    assert fila["veredicto"] == "OK_ABSOLUTO" and fila["auditoria"] == "APROBADA" and fila["propuestas"]
    assert all(T.buscar(p)["estado"] == "propuesta" for p in fila["propuestas"])        # circuito T192


def test_si_algo_cambia_en_un_turno_de_solo_lectura_avisa_fuerte(cola, proyecto, monkeypatch):
    def ciclo_que_escribe(**k):
        (proyecto / "nucleo" / "a.py").write_text("roto\n", encoding="utf-8")
        return []
    reg = _turno_revisar(monkeypatch, ciclo_que_escribe)
    assert reg["solo_lectura"] == {"ok": False, "cambiados": ["nucleo/a.py"], "metodo": "escrituras del propio turno"}
    [aviso] = avisos.recientes()
    assert "ALGO CAMBIO" in aviso["titulo"] and aviso["urgencia"] == "high"


# ------------------------------------------------------------------ guardas
def test_parada_aborta_antes_de_preparar(cola, monkeypatch):
    import turno_nexo
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: "me voy")
    monkeypatch.setattr(plantillas_turno, "preparar", lambda *a, **k: pytest.fail("no debe preparar"))
    reg = turno_nexo.turno()
    assert "PARADA" in reg["abortado"] and reg["pasos"] == {}


def test_desactivados_no_avisa_salvo_lanzado_a_mano(cola, monkeypatch):
    import turno_nexo
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: None)
    turnos.desactivar("de viaje")
    t = _turno()
    assert turno_nexo.turno(turno_id=t["id"])["aviso_push"] is False and avisos.recientes() == []
    reg = turno_nexo.turno(turno_id=t["id"], manual=True)
    assert "DESACTIVADOS" in reg["abortado"] and reg["aviso_push"] is True
    assert avisos.recientes()[0]["titulo"] == "Prueba: no hizo nada"
    assert reg["explicacion"] == "todos los turnos estaban en pausa (de viaje)"


def test_sin_candidatas_de_la_plantilla_no_arranca(cola, monkeypatch):
    import turno_nexo
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: None)
    monkeypatch.setattr(turno_nexo, "_tomar_candado", lambda: pytest.fail("no debe tomar el candado"))
    reg = turno_nexo.turno()
    assert "sin candidatas" in reg["abortado"] and reg["candidatas"] == {"cola": 0} and not reg["aviso_push"]


# ------------------------------------------------------------------ vigia de novedades (T272)
AHORA = datetime(2026, 9, 28, 3, 30)


def _fuentes(github=None, nvidia=None):
    return {"github": lambda ahora: github if github is not None else [
                {"fuente": "github", "id": "org/agente-nuevo", "nombre": "org/agente-nuevo",
                 "url": "https://github.com/org/agente-nuevo", "fecha": "2026-09-25", "descripcion": "agentes"},
                {"fuente": "github", "id": "org/langgraph", "nombre": "org/langgraph",
                 "url": "https://github.com/org/langgraph", "fecha": "2026-09-26", "descripcion": "ya conocido"}],
            "nvidia": lambda ahora: nvidia if nvidia is not None else [
                {"fuente": "nvidia", "id": "openai/gpt-oss-20b", "nombre": "openai/gpt-oss-20b",
                 "url": "https://build.nvidia.com/openai/gpt-oss-20b", "fecha": "", "descripcion": ""}],
            "ollama": lambda ahora: (_ for _ in ()).throw(RuntimeError("503"))}


def test_vigia_deduplica_linea_base_y_fuentes_caidas(cola):
    T.anadir("Evaluar LangGraph para el router", depende="ia", etiquetas=["cat:investigacion"])
    r = vigia.recoger(AHORA, _fuentes())
    assert [c["id"] for c in r["candidatos"]] == ["org/agente-nuevo"]       # langgraph ya esta en tareas
    assert r["linea_base"] == ["nvidia"] and "ollama" in r["errores"]
    nuevo = {"fuente": "nvidia", "id": "qwen/qwen4-30b", "nombre": "qwen/qwen4-30b",
             "url": "https://build.nvidia.com/qwen/qwen4-30b", "fecha": "", "descripcion": ""}
    r2 = vigia.recoger(AHORA, _fuentes(github=[], nvidia=[nuevo, _fuentes()["nvidia"](AHORA)[0]]))
    assert [c["id"] for c in r2["candidatos"]] == ["qwen/qwen4-30b"]         # lo ya visto no se repite


def test_vigia_crea_un_lote_al_dia_y_su_material(cola, monkeypatch):
    t = vigia.crear_lote(AHORA, _fuentes())
    assert vigia.hecho_hoy(AHORA) and "plantilla:vigia" in t["etiquetas"]
    material = plantillas_turno.material(t)
    assert "https://github.com/org/agente-nuevo" in material and "CONTENIDO_EXTERNO" in material
    inst = trabajo._instruccion(t, "investigacion")
    assert "como mucho 5" in inst and "PROPUESTAS IMPLEMENTABLES" in inst
    monkeypatch.setattr(vigia, "datetime", type("D", (), {"now": staticmethod(lambda: AHORA)}))
    ctx = dict(turnos.contexto(), plantilla="vigia")
    assert plantillas_turno.candidatas(ctx) == 1          # el lote de hoy, sin borrador: se reintenta
    T.actualizar(t["id"], etiquetas=t["etiquetas"] + ["borrador:revisar_claude"])
    assert plantillas_turno.candidatas(ctx) == 0          # hecho hoy y con borrador: nada mas hoy


def test_vigia_sin_novedades_no_crea_tarea(cola):
    assert vigia.crear_lote(AHORA, {"github": lambda a: []}) is None and vigia.hecho_hoy(AHORA)


def test_vigia_resumen_semanal_con_propuestas(cola):
    from nucleo import revision
    t = vigia.crear_lote(datetime.now(), _fuentes())
    p = T.anadir("[Propuesta] investigar org/agente-nuevo", estado="propuesta", depende="ia",
                 etiquetas=[revision.ET_PROPUESTA, f"{revision.PRE_ORIGEN}{t['id']}"])
    [lote] = vigia.resumen_semanal()["lotes"]
    assert lote["id"] == t["id"] and lote["propuestas"][0]["id"] == p["id"]


@pytest.mark.parametrize("titulo, es", [
    ("Triaje de ordenes a prueba de fallos: acciones directas", False),     # caso real 28/09 (T186)
    ("Failover robusto: tabla de tipos de error -> accion", False),          # caso real 28/09 (T157)
    ("BUG pequeno: NvidiaProvider.enviar no prueba el siguiente modelo", True),
    ("Arreglar el guardado de la cola", True),
    ("El bot falla al arrancar", True),
    ("Error al leer tareas.json con BOM", True),
])
def test_filtro_de_errores(titulo, es):
    assert plantillas_turno._es_error({"titulo": titulo, "etiquetas": ["cat:codigo"]}) is es


def test_github_sigue_si_cae_una_consulta(monkeypatch):
    class R:
        def __init__(self, n):
            self.n = n

        def raise_for_status(self):
            if self.n == 2:
                raise RuntimeError("403 rate limit")

        def json(self):
            return {"items": [{"full_name": f"org/repo{self.n}", "html_url": f"https://github.com/org/repo{self.n}",
                               "created_at": "2026-09-27T00:00:00Z", "description": "x", "stargazers_count": 5}]}
    llamadas = []
    monkeypatch.setattr(vigia, "_get", lambda url, cab=None, params=None: llamadas.append(1) or R(len(llamadas)))
    monkeypatch.setattr(vigia, "PAUSA_GITHUB", 0)
    r = vigia.fuente_github(AHORA)
    assert len(r) == len(vigia.CONSULTAS_GITHUB) - 1 and "org/repo2" not in {x["id"] for x in r}


@pytest.mark.parametrize("titulo", ["Push de error cuando el turno nocturno muere sin dejar registro",
                                    "Rotacion de proveedores y evaluacion cruzada"])   # casos reales 28/09
def test_filtro_de_errores_no_confunde_mejoras(titulo):
    assert not plantillas_turno._es_error({"titulo": titulo, "etiquetas": ["cat:codigo"]})
    assert plantillas_turno._es_error({"titulo": titulo, "etiquetas": ["cat:codigo", "tipo:bug"]})


# ------------------------------------------------------------------ a) lotes pequenos (28/09)
def test_lotes_de_como_mucho_9500_caracteres_reales(cola, proyecto):
    assert plantillas_turno.LOTE_MAX <= 10000 and plantillas_turno.PIEZA_MAX <= plantillas_turno.LOTE_MAX
    for _ in range(12):
        lote = plantillas_turno.siguiente_lote("revisar_codigo")
        assert plantillas_turno._tam_lote(lote) <= plantillas_turno.LOTE_MAX + 200   # + cabeceras de archivo


def test_cursor_compara_lineas_como_numeros(cola, proyecto):
    """28/09: como texto, 'b.py:95' iba despues de 'b.py:180' y se saltaban trozos."""
    vistos = []
    for _ in range(len(plantillas_turno.piezas("revisar_codigo"))):
        vistos += plantillas_turno.siguiente_lote("revisar_codigo")
    todas = plantillas_turno.piezas("revisar_codigo")
    assert set(todas) <= set(vistos)                                   # ninguna pieza se queda sin revisar
    trozos_b = [p for p in todas if p[0] == "nucleo/b.py"]
    assert len(trozos_b) >= 6 and [p[1] for p in trozos_b] == sorted(p[1] for p in trozos_b)


def test_lote_viejo_demasiado_grande_se_rehace_en_pequenos(cola, proyecto):
    viejo = plantillas_turno._crear_lote("revisar_codigo", [("nucleo/b.py", 1, 4000)], 1)
    ctx = dict(turnos.contexto(), plantilla="revisar_codigo", texto="x", max_tareas=5)
    lista = plantillas_turno.preparar(ctx)
    assert T.buscar(viejo["id"])["estado"] == "descartada" and "rehecho en" in T.buscar(viejo["id"])["notas"][-1]["texto"]
    assert len(lista) == 5 and all(t["id"] != viejo["id"] for t in lista)
    for t in lista:
        assert plantillas_turno._tam_lote(plantillas_turno._lote_de_detalle(t["detalle"])) <= plantillas_turno.LOTE_MAX


# ------------------------------------------------------------------ d) por que no hizo nada (28/09)
def test_explicacion_sin_candidatas_y_vigia_ya_pasado(cola, monkeypatch):
    import turno_nexo
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: None)
    t = _turno(plantilla="investigacion")
    reg = turno_nexo.turno(turno_id=t["id"])
    assert reg["explicacion"] == "no había investigación pendiente sin borrador esperando revisión"
    vigia._escribir("estado.json", {"ultimo_dia": datetime.now().strftime("%Y-%m-%d")})
    v = _turno(plantilla="vigia")
    reg = turno_nexo.turno(turno_id=v["id"], manual=True)
    assert "ya pasó hoy (va una vez al día)" in reg["explicacion"]
    assert "Por qué: el vigía de novedades ya pasó hoy" in avisos.recientes()[0]["cuerpo"]


def test_explicacion_cuando_ningun_proveedor_puede(cola, monkeypatch):
    import turno_nexo
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: None)
    monkeypatch.setattr(turno_nexo, "ram_libre_gb", lambda: 32.0)
    T.anadir("Investigar X", depende="ia", etiquetas=["cat:investigacion"])
    monkeypatch.setattr(trabajo, "ciclo", lambda **k: [{"tarea": "T001", "titulo": "Investigar X",
                                                        "intentos": [{"error": "groq: 413 Payload Too Large"}]}])
    reg = turno_nexo.turno(turno_id=_turno(plantilla="investigacion")["id"])
    assert reg["explicacion"] == "ningún proveedor pudo hacer el trabajo (último fallo: groq: 413 Payload Too Large)"


# ------------------------------------------------------------------ e) solo lectura: solo lo del propio turno
def test_otra_sesion_editando_a_la_vez_no_es_culpa_del_turno(cola, proyecto, monkeypatch):
    """28/09 18:17: la foto antes/despues culpo al turno de lo que Claude editaba en otra sesion."""
    import subprocess
    import sys

    def ciclo_con_otra_sesion(**k):
        # otra sesion (OTRO proceso) edita un archivo del proyecto mientras el turno trabaja
        subprocess.run([sys.executable, "-c", f"open(r'{proyecto / 'nucleo' / 'a.py'}', 'w').write('editado por otra sesion')"],
                       check=True)
        # y el turno escribe en memoria/ (permitido: tareas, borradores...)
        (proyecto / "memoria" / "borrador_de_prueba.md").write_text("x", encoding="utf-8")
        return []
    reg = _turno_revisar(monkeypatch, ciclo_con_otra_sesion)
    assert (proyecto / "nucleo" / "a.py").read_text() == "editado por otra sesion"      # el cambio existe...
    assert reg["solo_lectura"]["ok"] and reg["solo_lectura"]["cambiados"] == []       # ...pero no es del turno
    assert not [a for a in avisos.recientes() if "ALGO CAMBIO" in a["titulo"]]


def test_guardia_solo_cuenta_mientras_esta_activa(proyecto):
    with plantillas_turno.GuardiaEscritura() as g:
        (proyecto / "principal.py").write_text("x", encoding="utf-8")
        (proyecto / "nucleo" / "__pycache__").mkdir(exist_ok=True)
        (proyecto / "nucleo" / "__pycache__" / "a.pyc").write_bytes(b"x")          # cache de Python: no cuenta
        (proyecto / "nucleo" / "a.py").read_text(encoding="utf-8")                  # leer no cuenta
    assert g.escritos == ["principal.py"]
    (proyecto / "README.md").write_text("fuera de la guardia", encoding="utf-8")
    with plantillas_turno.GuardiaEscritura() as g2:
        pass
    assert g2.escritos == []


# ------------------------------------------------------------------ b) el vigia puntua de verdad (28/09)
def test_vigia_da_las_necesidades_de_nexo_y_la_escala(cola):
    T.anadir("Memoria a largo plazo para los chats", depende="ia", etiquetas=["cat:investigacion"])
    T.anadir("Cita con el medico", depende="damian", etiquetas=["cat:personal"])
    t = vigia.crear_lote(AHORA, _fuentes())
    material = plantillas_turno.material(t)
    assert "NECESIDADES DE NEXO" in material and "Memoria a largo plazo" in material and "medico" not in material
    inst = trabajo._instruccion(t, "investigacion")
    assert "5 = resuelve un problema ABIERTO" in inst and "como mucho en 3" in inst


def test_vigia_sin_necesidad_citada_no_pasa_de_3(cola):
    necesidad = T.anadir("Memoria a largo plazo", depende="ia", etiquetas=["cat:investigacion"])
    lote = vigia.crear_lote(AHORA, _fuentes())
    inflada = T.anadir("[Propuesta] investigar org/agente-nuevo", estado="propuesta", importancia=5,
                       detalle="QUE: investigar org/agente-nuevo (https://github.com/org/agente-nuevo): agentes\nDONDE: x")
    buena = T.anadir("[Propuesta] investigar org/memoria", estado="propuesta", importancia=5,
                     detalle=f"QUE: investigar org/memoria: resuelve {necesidad['id']}\nDONDE: memoria")
    inventada = T.anadir("[Propuesta] investigar org/otra", estado="propuesta", importancia=4,
                         detalle="QUE: investigar org/otra: resuelve T999\nDONDE: x")          # T999 no existe
    rebajadas = plantillas_turno.calibrar_propuestas(lote, [inflada, buena, inventada])
    assert rebajadas == [inflada["id"], inventada["id"]]
    assert T.buscar(inflada["id"])["importancia"] == 3 and T.buscar(buena["id"])["importancia"] == 5
    assert "rebajado a 3" in T.buscar(inflada["id"])["notas"][-1]["texto"]


def test_calibrar_no_toca_otras_plantillas(cola):
    normal = T.anadir("Investigar X", depende="ia", etiquetas=["cat:investigacion"])
    p = T.anadir("[Propuesta] algo", estado="propuesta", importancia=5, detalle="QUE: algo\n")
    assert plantillas_turno.calibrar_propuestas(normal, [p]) == [] and T.buscar(p["id"])["importancia"] == 5


def test_tramo_de_archivo_no_pide_bloqueo(cola, proyecto):
    """28/09, prueba real: con lotes pequenos un archivo se parte y el modelo pidio BLOQUEO por el resto."""
    lote = plantillas_turno._crear_lote("revisar_codigo", [("nucleo/b.py", 300, 500)], 1)
    inst = trabajo._instruccion(lote, "investigacion")
    assert "revisa solo ese tramo" in inst and "No respondas BLOQUEO" in inst
    assert "(lineas 300-500 de 4000)" in plantillas_turno.material(lote)
