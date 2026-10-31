# -*- coding: utf-8 -*-
"""Kuzushi fase 1 (T1011, Bloque 22): observadores sin IA, decisiones automaticas (a/b/c), filtro y presupuesto,
calibracion con Claude, resumen semanal y medicion de prompts (T1021). Todo con fuentes dadas: ni git, ni pytest,
ni memoria/ reales."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from nucleo import kuzushi as K
from nucleo import tareas as T

AHORA = datetime(2026, 10, 26, 4, 40)

# Los commits reales de principal alrededor de T844 (25-26/10), el mas reciente primero.
ASUNTO_T844 = "Fusiona impl/T844: T746 rehecha: fallback lexico de freno.pares_semanticos, tam"
COMMITS_T844 = [
    {"sha": "c517403606ecd0c52dca58bff4734b69a2dfad92", "fecha": "2026-10-26 16:21:53",
     "asunto": "cierre_auto: una fusion deshecha (git revert) ya no cierra la tarea",
     "archivos": ["nucleo/cierre_auto.py", "tests/test_cierre_auto.py"]},
    {"sha": "b15e46f493d79544e65d060502b3749253bebc36", "fecha": "2026-10-25 17:20:00",
     "asunto": "Bandeja de Claude (T667) vaciada: 13 casos dictaminados", "archivos": ["memoria/tribunal/x.json"]},
    {"sha": "7ecfc17598aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "fecha": "2026-10-25 15:37:00",
     "asunto": f'Revert "{ASUNTO_T844}"', "archivos": ["nucleo/freno.py"]},
    {"sha": "c1fdef7000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "fecha": "2026-10-25 15:17:00", "asunto": ASUNTO_T844,
     "archivos": ["nucleo/freno.py", "tests/test_t746_parecidas_fallback_lexico.py"]},
]
CIERRE_T844 = ("[test] Cierre automatico (nucleo.cierre_auto): el trabajo esta en principal, commit 7ecfc17598 "
               "'Revert \"Fusiona impl/T844: T746 rehecha: fallback lexico de freno.pares_semantic'; sus tests "
               "(interfaz/tests/test_t668_riesgo_web.py, tests/test_t669_permanente.py, tests/test_t890_deshacer_veto.py) "
               "ejecutados ahora: 25 passed in 19.29s")
EVIDENCIA_T844 = {"t": "2026-10-25 21:41:00", "tarea": "T844", "tipo": "test", "resultado": "ok",
                  "detalle": CIERRE_T844.replace("[test] ", ""), "comando": "pytest -q interfaz/tests/test_t668_riesgo_web.py"}


@pytest.fixture(autouse=True)
def carpeta(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "CARPETA", tmp_path / "kuzushi")
    return tmp_path / "kuzushi"


def _f(**kw):
    ahora = kw.pop("ahora", AHORA)
    base = dict(tareas=[], historial=[], evidencias=[], aprobaciones=[], guardian=[], implementador={},
                linea_base={}, turnos=[], uso=[], avisos=[], borradores=[], commits=[], disco={}, tamanos={},
                existe=lambda sha: True, existe_archivo=lambda r: True, ejecutar=lambda tests: (True, "ok"))
    base.update(kw)
    return K.Fuentes(ahora=ahora, **base)


def _t(tid, estado="pendiente", **kw):
    return dict({"id": tid, "titulo": f"tarea {tid}", "estado": estado, "notas": [], "etiquetas": [],
                 "actualizada": "2026-10-25 10:00:00"}, **kw)


def _tipos(hs):
    return {(h["fuente"], h["tipo"]) for h in hs}


# ================================================================ (a) cierres con evidencia que ya no vale
def test_T844_el_25_10_cerrada_con_su_propio_revert_es_un_hallazgo_grave_que_propone_reabrirla():
    t844 = _t("T844", "hecha", cerrada="2026-10-25 21:41:00",
              cierre={"estado_real": "HECHO Y TESTEADO", "evidencia": CIERRE_T844})
    hs = K.obs_decisiones(_f(tareas=[t844], evidencias=[EVIDENCIA_T844], commits=COMMITS_T844,
                             ahora=datetime(2026, 10, 25, 23, 0)))
    h = next(h for h in hs if h["tipo"] == "cierre_sin_evidencia_viva")
    assert h["gravedad"] == "grave" and h["propone"] == "reabrir T844" and "reabrir T844" in h["arreglo"]
    assert h["evidencia"]["cerrada_por"] == "cierre_auto" and h["evidencia"]["commit"] == "7ecfc17598"
    assert any("Revert" in p for p in h["evidencia"]["problemas"])
    assert h["huella"] == K.huella("decisiones", "cierre_sin_evidencia_viva", "T844:7ecfc17598")


def test_T844_reabierta_pero_con_el_cierre_viejo_es_cierre_rancio_y_sin_cierre_no_es_nada():
    rancia = _t("T844", "pendiente", cierre={"estado_real": "HECHO Y TESTEADO", "evidencia": CIERRE_T844})
    hs = K.obs_decisiones(_f(tareas=[rancia], evidencias=[EVIDENCIA_T844], commits=COMMITS_T844))
    assert [(h["tipo"], h["gravedad"]) for h in hs] == [("cierre_rancio", "media")]
    limpia = _t("T844", "pendiente")
    assert K.obs_decisiones(_f(tareas=[limpia], evidencias=[EVIDENCIA_T844], commits=COMMITS_T844)) == []


def test_un_commit_deshecho_despues_o_que_ya_no_existe_tambien_cuenta():
    cierre = {"estado_real": "HECHO Y TESTEADO", "evidencia": "fusion commit c1fdef7000 con sus tests"}
    t = _t("T844", "hecha", cerrada="2026-10-25 15:20:00", cierre=cierre)
    h = K.obs_decisiones(_f(tareas=[t], commits=COMMITS_T844))[0]
    assert h["gravedad"] == "grave" and "se deshizo despues en 7ecfc17598" in h["evidencia"]["problemas"][0]
    otro = _t("T900", "hecha", cerrada="2026-10-25 10:00:00",
              cierre={"estado_real": "HECHO Y TESTEADO", "evidencia": "commit abcdef1234 y tests"})
    hs = K.obs_decisiones(_f(tareas=[otro], commits=COMMITS_T844, existe=lambda sha: False))
    assert hs and "ya no existe" in hs[0]["evidencia"]["problemas"][0]
    assert K.obs_decisiones(_f(tareas=[otro], commits=COMMITS_T844, existe=lambda sha: True)) == []


def test_un_revert_del_revert_devuelve_la_fusion_a_la_vida():
    vuelta = {"sha": "d" * 40, "fecha": "2026-10-26 10:00:00", "asunto": f'Revert "Revert "{ASUNTO_T844}""',
              "archivos": ["nucleo/freno.py"]}
    t = _t("T844", "hecha", cerrada="2026-10-26 11:00:00",
           cierre={"estado_real": "HECHO Y TESTEADO", "evidencia": "commit c1fdef7000"})
    assert K.obs_decisiones(_f(tareas=[t], commits=[vuelta] + COMMITS_T844)) == []


def test_tests_citados_que_ya_no_existen_o_no_pasan_ahora():
    cierre = {"estado_real": "HECHO Y TESTEADO",
              "evidencia": "commit c1fdef7000; sus tests (tests/test_a.py, tests/test_b.py) pasan"}
    t = _t("T844", "hecha", cerrada="2026-10-25 15:20:00", cierre=cierre)
    vivos = [c for c in COMMITS_T844 if not c["asunto"].startswith("Revert")]
    pedidos = []

    def ejecutar(tests):
        pedidos.append(tests)
        return False, "1 failed, 3 passed"
    hs = K.obs_decisiones(_f(tareas=[t], commits=vivos, existe_archivo=lambda r: r != "tests/test_b.py",
                             ejecutar=ejecutar))
    problemas = hs[0]["evidencia"]["problemas"]
    assert pedidos == [["tests/test_a.py"]]                       # el que ya no existe no se ejecuta
    assert any("ya no existen: tests/test_b.py" in p for p in problemas)
    assert any("NO pasan ahora" in p and "1 failed" in p for p in problemas)
    assert K.obs_decisiones(_f(tareas=[t], commits=vivos)) == []   # verdes y presentes: nada


def test_cerrada_sin_sha_en_el_cierre_pero_cuyo_ultimo_commit_es_un_revert():
    t = _t("T844", "hecha", cerrada="2026-10-25 16:00:00", cierre={"estado_real": "HECHO SIN TESTEAR",
                                                                   "evidencia": "fusionada por la puerta"})
    h = next(h for h in K.obs_decisiones(_f(historial=[t], commits=COMMITS_T844))
             if h["tipo"] == "cerrada_con_fusion_deshecha")
    assert h["gravedad"] == "grave" and h["propone"] == "reabrir T844"


# ================================================================ (b) y (c)
def test_aprobacion_del_guardian_luego_denegada_sale_para_claude():
    s = {"id": "A0083", "accion": "ejecutar comando", "huella": "h1", "estado": "denegada", "creada": "2026-10-25 10:00:00",
         "eventos": [{"cuando": "2026-10-25 10:00:00", "tipo": "alta", "quien": "mcp"},
                     {"cuando": "2026-10-25 10:01:00", "tipo": "aprobada", "quien": "guardian"},
                     {"cuando": "2026-10-25 10:05:00", "tipo": "denegada", "quien": "damian"}]}
    h = K.obs_decisiones(_f(aprobaciones=[s]))[0]
    assert h["tipo"] == "aprobacion_automatica_deshecha" and h["zona"] == "guardian" and h["categoria"] == "seguridad"
    usada = dict(s, estado="usada", eventos=s["eventos"][:2])
    misma = {"id": "A0090", "huella": "h1", "estado": "denegada", "creada": "2026-10-26 09:00:00", "eventos": []}
    assert K.obs_decisiones(_f(aprobaciones=[usada])) == []
    assert K.obs_decisiones(_f(aprobaciones=[usada, misma]))[0]["evidencia"]["misma_accion_denegada"] == ["A0090"]


def test_rechazo_de_la_puerta_por_infra_y_la_explicacion_solo_vale_para_su_rechazo():
    notas = [{"cuando": "2026-10-21 10:12:16", "texto": "Puerta de fusion (T669): NO pasa. revisor groq: RECHAZAR: el "
                                                         "umbral no se ajusta"},
             {"cuando": "2026-10-25 15:37:45", "texto": "Implementador (T669): fusionada y DESHECHA (marcha atras "
                                                         "automatica). Salud: la suite tardo mas de 1200 s"},
             {"cuando": "2026-10-25 16:25:39", "texto": "Puerta de fusion (T669): NO pasa. suite en rojo en la rama: "
                                                         "FAILED tests/test_x.py::test_y"},
             {"cuando": "2026-10-25 17:13:25", "texto": "Coordinador: el rechazo es por la suite, no por este cambio."}]
    h = K.obs_decisiones(_f(tareas=[_t("T849", notas=notas)]))[0]
    assert h["tipo"] == "rechazo_puerta_infra" and h["zona"] == "puerta"
    assert [c["rechazo"] for c in h["evidencia"]["casos"]] == ["2026-10-25 15:37", "2026-10-25 16:25"]


# ================================================================ resto de fuentes
def test_tareas_rebotan_atascadas_duplicadas_y_cerradas_sin_cierre_desde_el_18_10():
    rech = [{"cuando": "2026-10-20 10:00:00", "texto": "Puerta de fusion (T669): NO pasa. x"},
            {"cuando": "2026-10-22 10:00:00", "texto": "Puerta de fusion (T669): NO pasa. y"}]
    tareas = [_t("T1", notas=rech), _t("T2", "esperando", actualizada="2026-10-10 10:00:00"),
              _t("T3", titulo="limpiar los avisos viejos del centro"), _t("T4", titulo="limpiar avisos viejos del centro")]
    hist = [_t("T5", "hecha", cerrada="2026-10-20 10:00:00"), _t("T6", "hecha", cerrada="2026-10-15 10:00:00"),
            _t("T7", "hecha", cerrada="2026-10-20 10:00:00", cierre={"estado_real": "HECHO Y TESTEADO", "evidencia": "x"})]
    hs = K.obs_tareas(_f(tareas=tareas, historial=hist))
    claves = {(h["tipo"], h["clave"]) for h in hs}
    assert claves == {("rebota", "T1"), ("atascada", "T2"), ("duplicada", "T3|T4"), ("cerrada_sin_evidencia", "T5")}


def test_tests_en_rojo_en_la_linea_base_intermitentes_y_los_que_tumban_la_puerta():
    lb = {"a": {"_orden": 1, "tests/test_x.py::test_1": True, "tests/test_z.py::test_9": True},
          "b": {"_orden": 2, "tests/test_x.py::test_1": True, "tests/test_z.py::test_9": False},
          "c": {"_orden": 3, "tests/test_x.py::test_1": True, "tests/test_z.py::test_9": True}}
    notas = [{"cuando": "2026-10-20 10:00:00", "texto": "FAILED tests/test_v.py::test_proceso (1 failed)"}]
    hs = K.obs_tests(_f(linea_base=lb, tareas=[_t("T1", notas=notas), _t("T2", notas=notas)]))
    por = {h["tipo"]: h for h in hs}
    assert por["rojo_en_linea_base"]["evidencia"]["commits_en_rojo"] == 3 and por["rojo_en_linea_base"]["arreglo"]
    assert por["intermitente"]["clave"] == "tests/test_z.py::test_9"
    assert por["tumba_a_la_puerta"]["evidencia"]["tareas"] == ["T1", "T2"]


def test_turnos_que_pasan_el_tope_con_su_margen_repiten_error_o_no_producen():
    def reg(dur, tope=25, **kw):
        return dict({"turno_id": "implpil2", "nombre_turno": "Implementador", "duracion_s": dur, "max_minutos": tope,
                     "pasos": {}, "_archivo": "registros/x.json"}, **kw)
    dentro = reg((25 + 15) * 60)                 # el planificador le da 15 min de margen: no es pasarse
    fuera = reg((25 + 15) * 60 + 600)
    err = [reg(60, pasos={"implementador": {"error": "RuntimeError: git reset"}}) for _ in range(2)]
    vacios = [dict(reg(60), turno_id="trib", silencioso=True) for _ in range(5)]
    hs = K.obs_turnos(_f(turnos=[dentro, fuera] + err + vacios))
    assert _tipos(hs) == {("turnos", "pasa_el_tope"), ("turnos", "error_repetido"), ("turnos", "no_produce")}
    assert next(h for h in hs if h["tipo"] == "pasa_el_tope")["evidencia"]["veces"] == 1


def test_proveedores_guardian_git_y_salud():
    uso = [{"proveedor": "gemini", "estado": "OK" if i % 2 else "ERROR", "entrada": 1000} for i in range(10)]
    g = [{"cuando": "2026-10-25 10:00:00", "id": f"A{i}", "accion": "ejecutar comando", "regla": "resto",
          "decision": "damian", "motivo": "instala"} for i in range(3)]
    commits = [{"sha": "1" * 40, "fecha": "2026-10-20 10:00:00", "asunto": 'Revert "Fusiona impl/T1: x"', "archivos": []}]
    commits += [{"sha": f"{i}" * 40, "fecha": "2026-10-2%d 10:00:00" % i, "asunto": "arregla el bug de trabajo",
                 "archivos": ["nucleo/trabajo.py"]} for i in range(3)]
    hs = (K.obs_proveedores(_f(uso=uso)) + K.obs_guardian(_f(guardian=g)) + K.obs_git(_f(commits=commits))
          + K.obs_salud(_f(disco={"libre_gb": 10, "total_gb": 500}, tamanos={"registros_mb": 2000})))
    assert _tipos(hs) == {("proveedores", "falla_mucho"), ("guardian", "a_damian_repetido"), ("git", "revert"),
                          ("git", "se_rompe_otra_vez"), ("salud", "disco_justo"), ("salud", "registros_grandes")}
    assert next(h for h in hs if h["fuente"] == "guardian")["zona"] == "guardian"


# ================================================================ T1021: medir prompts (sin cambiarlos)
def test_inventario_de_prompts_restricciones_y_frases_repetidas(tmp_path):
    (tmp_path / "nucleo").mkdir()
    comun = "Ayudas a un proyecto personal llamado NEXO, un asistente local-first que corre en un PC con Windows. "
    (tmp_path / "nucleo" / "a.py").write_text(
        '"""Docstring larga que no es un prompt: ' + "x " * 150 + '"""\n'
        f'PROMPT = ("{comun}" "Responde en maximo 600 palabras y explica cada punto con calma, sin inventar nada '
        'de lo que no tengas delante; ' + "con detalle " * 10 + '")\n', encoding="utf-8")
    (tmp_path / "nucleo" / "b.py").write_text(
        f'def f(x):\n    return f"{comun}Escribe un resumen de {{x}} para la ficha, ' + "bien " * 40 + '"\n',
        encoding="utf-8")
    uso = [{"proveedor": "chatgpt", "estado": "OK", "entrada": n} for n in (1000, 2000, 30000)]
    m = K.medir_prompts(_f(uso=uso), raiz=tmp_path)
    plantillas = sorted(m["plantillas"], key=lambda p: p["archivo"])
    assert [(p["archivo"], p["nombre"]) for p in plantillas] == [("nucleo/a.py", "PROMPT"), ("nucleo/b.py", "")]
    assert plantillas[0]["restricciones"] == ["maximo 600 palabras"] and plantillas[1]["restricciones"] == []
    assert m["repetidas"] and len(m["repetidas"][0]["sitios"]) == 2
    assert m["enviado_por_proveedor"]["chatgpt"] == {"envios": 3, "mediana": 2000, "p90": 30000, "maximo": 30000}
    hs = K.obs_prompts(_f(uso=uso), raiz=tmp_path)
    assert ("prompts", "restriccion_numerica") in _tipos(hs) and ("prompts", "contexto_repetido") in _tipos(hs)
    assert all(h["evidencia"]["tarea"] == "T1021" for h in hs)


# ================================================================ filtro, presupuesto, calibracion
def _obs(monkeypatch, hallazgos, ahora=AHORA, crear=None, tareas=None, **kw):
    monkeypatch.setattr(K, "OBSERVADORES", (("prueba", lambda f: [dict(h) for h in hallazgos]),))
    return K.observar(fuentes=_f(ahora=ahora, tareas=tareas or []), crear=crear, **kw)


def _h(n, **kw):
    return K.hallazgo("prueba", "tipo", f"clave{n}", f"hallazgo {n}", {"n": n}, **kw)


def test_la_primera_semana_todo_va_a_la_cola_de_calibracion_y_la_huella_no_se_repite(monkeypatch):
    r = _obs(monkeypatch, [_h(1, arreglo="x"), _h(2)])
    assert r["nuevos"] == ["K0001", "K0002"] and r["calibrando"] and r["tareas_creadas"] == []
    assert {h["estado"] for h in K.cargar()["hallazgos"]} == {"calibrar"}
    r2 = _obs(monkeypatch, [_h(1, arreglo="x"), _h(2)], ahora=AHORA + timedelta(days=1))
    assert r2["nuevos"] == [] and [h["veces"] for h in K.cargar()["hallazgos"]] == [2, 2]


def test_calibrado_util_pasa_a_tarea_tras_la_semana_con_tope_de_3_por_noche(monkeypatch):
    hs = [_h(i, arreglo=f"arreglo {i}") for i in range(5)]
    _obs(monkeypatch, hs)
    for h in K.cargar()["hallazgos"]:
        K.calibrar(h["id"], "util", "sirve")
    creadas = []
    despues = AHORA + timedelta(days=8)
    r = _obs(monkeypatch, hs, ahora=despues, crear=lambda h: creadas.append(h["id"]) or f"T9{len(creadas)}")
    assert r["tareas_creadas"] == ["T91", "T92", "T93"] and not r["calibrando"]
    estados = [h["estado"] for h in K.cargar()["hallazgos"]]
    assert estados.count("tarea") == 3 and estados.count("espera") == 2
    espera = [json.loads(x) for x in (K.CARPETA / "espera.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(espera) == 2 and "presupuesto" in espera[0]["historial"][-1]["motivo"]
    r = _obs(monkeypatch, hs, ahora=despues + timedelta(hours=1), crear=lambda h: "T99")
    assert r["tareas_creadas"] == []                               # misma noche: presupuesto gastado


def test_no_util_se_descarta_para_siempre_y_r3_va_a_claude_y_sin_arreglo_espera(monkeypatch):
    _obs(monkeypatch, [_h(1, arreglo="x"), _h(2, arreglo="x", zona="puerta"), _h(3)])
    K.calibrar("K0001", "no_util", "ruido: ya lo cubre el aviso")
    for hid in ("K0002", "K0003"):
        K.calibrar(hid, "util", "sirve")
    with pytest.raises(ValueError):
        K.calibrar("K0003", "util", "  ")
    _obs(monkeypatch, [_h(1, arreglo="x"), _h(2, arreglo="x", zona="puerta"), _h(3)], ahora=AHORA + timedelta(days=8),
         crear=lambda h: pytest.fail("no debe crear tareas"))
    est = {h["id"]: h["estado"] for h in K.cargar()["hallazgos"]}
    assert est == {"K0001": "descartado", "K0002": "claude", "K0003": "espera"}


def test_con_el_freno_puesto_no_crea_tareas(monkeypatch):
    _obs(monkeypatch, [_h(1, arreglo="x")])
    K.calibrar("K0001", "util", "sirve")
    propuestas = [_t(f"T{i}", "propuesta", titulo=f"propuesta numero {i} distinta") for i in range(40)]
    r = _obs(monkeypatch, [_h(1, arreglo="x")], ahora=AHORA + timedelta(days=8), tareas=propuestas,
             crear=lambda h: pytest.fail("freno puesto"))
    assert r["freno"] and K.cargar()["hallazgos"][0]["estado"] == "espera"


def test_lo_que_deja_de_verse_se_resuelve_y_si_vuelve_reaparece(monkeypatch):
    _obs(monkeypatch, [_h(1), _h(2)])
    _obs(monkeypatch, [_h(1)], ahora=AHORA + timedelta(days=1))
    assert [h["estado"] for h in K.cargar()["hallazgos"]] == ["calibrar", "resuelto"]
    r = _obs(monkeypatch, [_h(1), _h(2)], ahora=AHORA + timedelta(days=2))
    assert r["reaparecidos"] == ["K0002"] and K.cargar()["hallazgos"][1]["estado"] == "calibrar"


def test_un_observador_roto_no_resuelve_lo_suyo_ni_tapa_a_los_demas(monkeypatch):
    _obs(monkeypatch, [_h(1)])

    def roto(f):
        raise OSError("disco")
    monkeypatch.setattr(K, "OBSERVADORES", (("prueba", roto), ("otro", lambda f: [])))
    r = K.observar(fuentes=_f(ahora=AHORA + timedelta(days=1)))
    assert "prueba" in r["errores"] and K.cargar()["hallazgos"][0]["estado"] == "calibrar"


def test_la_tarea_real_lleva_origen_kuzushi_prioridad_media_y_metricas(monkeypatch):
    _obs(monkeypatch, [_h(1, arreglo="quitar el cierre viejo", donde="memoria/tareas.json"),
                       _h(2, arreglo="cerrar el agujero", categoria="seguridad")])
    for hid in ("K0001", "K0002"):
        K.calibrar(hid, "util", "sirve")
    r = _obs(monkeypatch, [_h(1, arreglo="quitar el cierre viejo", donde="memoria/tareas.json"),
                           _h(2, arreglo="cerrar el agujero", categoria="seguridad")], ahora=AHORA + timedelta(days=8))
    tareas = {t["id"]: t for t in T.cargar()["tareas"]}
    a, b = (tareas[x] for x in r["tareas_creadas"])
    assert a["origen"]["prov"] == "kuzushi" and a["origen"]["hallazgo"] == "K0001"
    assert a["prioridad"] == 3 and b["prioridad"] == 4 and a["quien"] == "claude"
    assert any(h.startswith("exito:") for h in a["hecho_cuando"]) and any(h.startswith("guarda:") for h in a["hecho_cuando"])


def test_lo_guardado_pasa_por_auditor_tapar(monkeypatch):
    _obs(monkeypatch, [K.hallazgo("prueba", "t", "c", "ruta", {"detalle": r"C:\Users\alguien\secreto\x.txt"})])
    assert "alguien" not in (K.CARPETA / "hallazgos.json").read_text(encoding="utf-8")


def test_simular_no_guarda_nada(monkeypatch):
    _obs(monkeypatch, [_h(1)], simular=True)
    assert not (K.CARPETA / "hallazgos.json").exists()


# ================================================================ resumen semanal, turno
def test_resumen_semanal_visto_arreglado_descartado_con_enlace(monkeypatch):
    _obs(monkeypatch, [_h(1), _h(2), _h(3)], ahora=datetime.now() - timedelta(days=2))
    K.calibrar("K0003", "no_util", "duplicado del aviso de disco")
    _obs(monkeypatch, [_h(2), _h(3)], ahora=datetime.now() - timedelta(days=1))
    r = K.resumen()
    assert [c["id"] for c in r["visto"]] == ["K0001", "K0002", "K0003"]
    assert [c["id"] for c in r["arreglado"]] == ["K0001"] and r["arreglado"][0]["url"] == "/kuzushi#K0001"
    assert r["descartado"][0]["motivo"] == "duplicado del aviso de disco"
    assert r["para_claude"] == 1 and r["calibrando"]


def test_el_turno_va_una_vez_al_dia(monkeypatch):
    assert K.candidatas() == 1
    _obs(monkeypatch, [_h(1)], ahora=datetime.now())
    assert K.candidatas() == 0
    assert "kuzushi: 1 hallazgos vistos" in K.texto_resumen({"observados": 1, "nuevos": ["K0001"]})


def test_la_tabla_real_tiene_el_turno_kuzushi_y_ya_no_los_que_absorbe():
    from nucleo import turnos
    from nucleo.config import RAIZ
    assert "No arranca" in turnos.PLANTILLAS["kuzushi"]["texto"]
    cfg = json.loads((RAIZ / "memoria" / "turnos_config.json").read_text(encoding="utf-8"))
    k = [t for t in cfg["turnos"] if t["plantilla"] == "kuzushi"]
    assert len(k) == 1 and k[0]["activo"] and k[0]["max_minutos"] <= 20 and not k[0]["avisar"]
    assert not [t for t in cfg["turnos"] if t["plantilla"] in ("vigia", "revisar_codigo", "revisar_archivos")]
    archivados = {t["plantilla"] for t in cfg["archivados"]}
    assert {"vigia", "revisar_codigo", "revisar_archivos"} <= archivados


def test_el_turno_de_la_tabla_ejecuta_kuzushi_con_su_limite_y_lo_resume(monkeypatch):
    import time
    import importlib
    from nucleo import turnos
    tn = importlib.import_module("turno_" + "nexo")
    t = turnos.guardar_turno({"nombre": "Kuzushi", "plantilla": "kuzushi", "dias": list(turnos.DIAS),
                              "horas": ["04:35"], "max_minutos": 15, "avisar": False})
    monkeypatch.setattr(tn, "ram_libre_gb", lambda: 32.0)
    vistos = {}

    def falso(**k):
        vistos.update(k)
        return {"observados": 4, "nuevos": ["K0001"], "tareas_creadas": [], "calibrando": True, "errores": {}}
    monkeypatch.setattr(K, "turno", falso)
    antes = time.time()
    reg = tn.turno(turno_id=t["id"], avisar=False)
    assert reg["pasos"]["kuzushi"]["observados"] == 4 and not vistos["simular"]
    assert antes + 15 * 60 - 5 <= vistos["limite"] <= time.time() + 15 * 60
    assert "kuzushi: 4 hallazgos vistos, 1 nuevos" in tn._resumen(reg)


def test_resuelto_por_claude_no_reaparece_con_la_misma_evidencia_y_si_con_otra(monkeypatch):
    """Bloque 23 (29/10): los hallazgos miran ventanas de 30 dias (rechazos, turnos, tests que tumban la puerta); uno
    que Claude arregla seguia observandose con la evidencia VIEJA y volvia a 'nuevo' en la siguiente pasada. Ahora
    `resolver` guarda la huella de la evidencia: solo reaparece si la evidencia cambia (un caso nuevo)."""
    _obs(monkeypatch, [_h(1, arreglo="x")])
    K.calibrar("K0001", "util", "sirve")
    with pytest.raises(ValueError):
        K.resolver("K0001", " ")
    h = K.resolver("K0001", "arreglado en el Bloque 23 (commit abc)")
    assert h["estado"] == "resuelto" and "Bloque 23" in h["historial"][-1]["motivo"]
    r = _obs(monkeypatch, [_h(1, arreglo="x")], ahora=AHORA + timedelta(days=8),
             crear=lambda h: pytest.fail("no debe crear tareas"))
    assert r["reaparecidos"] == [] and K.cargar()["hallazgos"][0]["estado"] == "resuelto"
    otro = K.hallazgo("prueba", "tipo", "clave1", "hallazgo 1", {"n": 1, "caso_nuevo": True}, arreglo="x")
    r = _obs(monkeypatch, [otro], ahora=AHORA + timedelta(days=9), crear=lambda h: "T77")
    assert r["reaparecidos"] == ["K0001"] and K.cargar()["hallazgos"][0]["estado"] == "tarea"
    with pytest.raises(KeyError):
        K.resolver("K9999", "x")


def test_la_nota_de_devolver_no_cuenta_como_rechazo():
    """Bloque 23: piloto_serie.devolver cita el motivo anterior ('... RECHAZAR: ...'); contarla reabria K0014/K0016."""
    from nucleo import piloto_serie
    import inspect
    assert f'"{K._DEVUELTA}: ' in inspect.getsource(piloto_serie.devolver)   # la misma frase que escribe devolver
    notas = [{"cuando": "2026-10-20 10:00", "texto": "revisor x: RECHAZAR: falta algo"},
             {"cuando": "2026-10-31 22:00",
              "texto": f"{K._DEVUELTA}: arreglado (antes: revisor x: RECHAZAR: falta algo)"}]
    hs = K.obs_tareas(_f(tareas=[_t("T1", notas=notas)]))
    assert not [h for h in hs if h["tipo"] == "rebota"]
