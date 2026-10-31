"""T1010 paso 2, punto 2: tareas.json solo con las vivas, historial de cerradas y detalle aparte.

Almacen en tmp_path (fixture autouse `turnos_aislados`); nunca se toca memoria/ real.
"""
import json

import pytest

from nucleo import tareas as T
from nucleo import tareas_almacen as AL

CIERRE = {"estado_real": "HECHO SIN TESTEAR", "evidencia": "hecho a mano, sin prueba automatica"}


def _cerrar(tid):
    return T.completar(tid, despues="nada: sin continuacion", cierre=CIERRE)


def _hot():
    return json.loads(T.ALMACEN.read_text(encoding="utf-8"))


def test_un_almacen_nuevo_nace_en_version_2():
    assert T.cargar()["version"] == 2
    T.anadir("Primera")
    assert _hot()["version"] == 2 and _hot()["version_historial"] == 0
    assert not AL.ruta_historial(T.ALMACEN).exists()                       # sin cerradas, no hay historial


def test_las_cerradas_salen_de_tareas_json_y_van_al_historial_con_resumen():
    a, b = T.anadir("Se queda"), T.anadir("Se cierra")
    _cerrar(b["id"])
    assert [r["id"] for r in _hot()["tareas"]] == [a["id"]]
    version, regs = AL.leer_historial(T.ALMACEN)
    assert version == 1 and [r["id"] for r in regs] == [b["id"]]
    assert regs[0]["estado"] == "hecha" and regs[0]["resumen"].startswith(f"{b['id']} [hecha] Se cierra")
    assert "hecho a mano" in regs[0]["resumen"] and "\n" not in regs[0]["resumen"]
    # y la API sigue viendolas todas, cerradas incluidas
    assert [t["id"] for t in T.cargar()["tareas"]] == [a["id"], b["id"]]
    assert T.buscar(b["id"])["estado"] == "hecha" and T.buscar("se cierra")["id"] == b["id"]
    assert T.listar(estado="hecha")[0]["id"] == b["id"] and [t["id"] for t in T.listar()] == [a["id"]]


def test_reabrir_una_cerrada_la_devuelve_a_tareas_json():
    t = T.anadir("Vuelve")
    _cerrar(t["id"])
    T.actualizar(t["id"], estado="pendiente")
    assert [r["id"] for r in _hot()["tareas"]] == [t["id"]]
    assert AL.leer_historial(T.ALMACEN)[1] == []
    assert T.cargar()["tareas"][0]["cerrada"] is None


def test_descartada_tambien_va_al_historial():
    t = T.anadir("Mala idea")
    T.actualizar(t["id"], estado="descartada")
    assert _hot()["tareas"] == [] and AL.leer_historial(T.ALMACEN)[1][0]["id"] == t["id"]


def test_el_historial_no_se_reescribe_si_no_cambian_las_cerradas():
    a, b = T.anadir("Viva"), T.anadir("Cerrada")
    _cerrar(b["id"])
    antes = AL.ruta_historial(T.ALMACEN).read_bytes()
    T.anotar(a["id"], "una nota en una viva")
    T.actualizar(a["id"], estado="en_curso")
    assert AL.ruta_historial(T.ALMACEN).read_bytes() == antes
    assert _hot()["version_historial"] == 1


def test_el_orden_de_cargar_es_por_id_numerico():
    ids = [T.anadir(f"t{i}")["id"] for i in range(4)]
    _cerrar(ids[1])
    assert [t["id"] for t in T.cargar()["tareas"]] == ids


# ------------------------------------------------------------------ detalle

def test_notas_antiguas_van_al_detalle_y_quedan_cinco():
    t = T.anadir("Muchas notas")
    for i in range(8):
        T.anotar(t["id"], f"nota {i}")
    g = T.cargar()["tareas"][0]
    assert [n["texto"] for n in g["notas"]] == [f"nota {i}" for i in range(3, 8)]
    det = AL.leer_detalle(T.ALMACEN, t["id"])
    assert [n["texto"] for n in det["notas_antiguas"]] == ["nota 0", "nota 1", "nota 2"]
    completo = T.cargar(detalle=True)["tareas"][0]
    assert [n["texto"] for n in completo["notas_antiguas"]] == ["nota 0", "nota 1", "nota 2"]
    assert "notas_antiguas" not in g


def test_las_notas_antiguas_no_se_duplican_ni_se_pierden_al_seguir_anotando():
    t = T.anadir("Sigue")
    for i in range(12):
        T.anotar(t["id"], f"n{i}")
    det = AL.leer_detalle(T.ALMACEN, t["id"])["notas_antiguas"]
    assert [n["texto"] for n in det] == [f"n{i}" for i in range(7)]


def test_conversaciones_viven_en_el_detalle():
    t = T.anadir("Con chat")
    T.fijar_conversacion(t["id"], "chatgpt:autor", url="https://x/c/1", tema="foco", estado="ok")
    assert T.conversacion(t["id"], "chatgpt:autor")["url"] == "https://x/c/1"
    assert "conversaciones" not in _hot()["tareas"][0]
    assert "conversaciones" not in T.cargar()["tareas"][0]
    assert T.cargar(detalle=True)["tareas"][0]["conversaciones"]["chatgpt:autor"]["usos"] == 1
    T.fijar_conversacion(t["id"], "chatgpt:autor", url="https://x/c/1")
    assert T.conversacion(t["id"], "chatgpt:autor")["usos"] == 2


def test_fallos_de_turno_viven_en_el_detalle_y_reabrir_los_pone_a_cero():
    t = T.anadir("Se atasca")
    for _ in range(3):
        g = T.fallo_turno(t["id"], "sin proveedor")
    assert g["estado"] == "bloqueada" and g["fallos_turno"] == 3
    assert AL.leer_detalle(T.ALMACEN, t["id"])["fallos_turno"] == 3
    T.actualizar(t["id"], estado="pendiente")
    assert "fallos_turno" not in AL.leer_detalle(T.ALMACEN, t["id"])
    T.fallo_turno(t["id"], "otra vez")
    T.exito_turno(t["id"])
    assert "fallos_turno" not in AL.leer_detalle(T.ALMACEN, t["id"])


def test_descarte_de_propuesta_va_al_detalle():
    t = T.anadir("Idea", etiquetas=["cat:propuesta"], estado="propuesta")
    T.actualizar(t["id"], estado="descartada", causa="idea", motivo="no aporta nada al foco actual")
    d = AL.leer_detalle(T.ALMACEN, t["id"])["descarte"]
    assert d["causa"] == "idea" and "foco" in d["motivo"]
    assert "descarte" not in T.cargar()["tareas"][0] and T.cargar(detalle=True)["tareas"][0]["descarte"]["causa"] == "idea"


def test_guardar_un_dict_con_campos_de_detalle_los_manda_al_detalle():
    t = T.anadir("A mano")
    datos = T.cargar()
    datos["tareas"][0]["conversaciones"] = {"gemini:revisor": {"usos": 1}}
    T.guardar(datos)
    assert AL.leer_detalle(T.ALMACEN, t["id"])["conversaciones"]["gemini:revisor"]["usos"] == 1
    assert "conversaciones" not in _hot()["tareas"][0]


def test_cargar_y_guardar_sin_detalle_no_borra_el_detalle():
    t = T.anadir("Con chat")
    T.fijar_conversacion(t["id"], "chatgpt:autor", url="https://x/c/1", estado="ok")
    T.guardar(T.cargar())                       # sin hidratar: no sabe del detalle y no debe tocarlo
    assert T.conversacion(t["id"], "chatgpt:autor")["url"] == "https://x/c/1"


def test_cargar_con_detalle_y_quitar_un_campo_lo_quita():
    t = T.anadir("Con chat")
    T.fijar_conversacion(t["id"], "chatgpt:autor", url="https://x/c/1", estado="ok")
    datos = T.cargar(detalle=True)
    del datos["tareas"][0]["conversaciones"]
    T.guardar(datos)
    assert T.conversacion(t["id"], "chatgpt:autor") is None


# ------------------------------------------------------------------ roto, coherencia, version 1

def test_tareas_json_roto_revienta_como_siempre():
    T.anadir("Algo")
    T.ALMACEN.write_text("{roto", encoding="utf-8")
    with pytest.raises(ValueError):
        T.cargar()


def test_si_historial_y_tareas_json_no_casan_se_sigue_con_lo_que_hay(monkeypatch):
    monkeypatch.setattr(AL, "ESPERA_LECTURA_S", 0)
    a, b = T.anadir("Viva"), T.anadir("Cerrada")
    _cerrar(b["id"])
    datos = _hot()
    datos["version_historial"] = 99                                       # otro proceso estaba a medias
    T.ALMACEN.write_text(json.dumps(datos), encoding="utf-8")
    assert sorted(t["id"] for t in T.cargar()["tareas"]) == [a["id"], b["id"]]


def test_una_linea_rota_del_historial_no_pierde_el_resto():
    a, b = T.anadir("Una"), T.anadir("Dos")
    _cerrar(a["id"])
    _cerrar(b["id"])
    ruta = AL.ruta_historial(T.ALMACEN)
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    ruta.write_text("\n".join([lineas[0], "{basura", lineas[2]]) + "\n", encoding="utf-8")
    assert [r["id"] for r in AL.leer_historial(T.ALMACEN)[1]] == [b["id"]]


def _almacen_viejo(*tareas):
    base = {"importancia": 3, "urgencia": 3, "dificultad": 3, "coste": 2, "depende": "ia", "estado": "pendiente",
            "limite": None, "etiquetas": [], "bloqueada_por": "", "pregunta_id": "", "testeado": False, "notas": [],
            "creada": "2026-09-01 10:00:00", "actualizada": "2026-09-01 10:00:00", "cerrada": None, "detalle": ""}
    lista = [{**base, **t} for t in tareas]
    T.ALMACEN.parent.mkdir(parents=True, exist_ok=True)
    T.ALMACEN.write_text(json.dumps({"version": 1, "siguiente_id": len(lista) + 1, "tareas": lista}), encoding="utf-8")


def test_un_almacen_version_1_se_lee_y_se_guarda_en_formato_viejo():
    _almacen_viejo({"id": "T001", "titulo": "Vieja", "importancia": 5, "urgencia": 2, "coste": 4, "depende": "claude",
                    "etiquetas": ["cat:codigo", "prov:claude", "tarea_origen:T9"], "conversaciones": {"chatgpt:autor": {"usos": 3}}},
                   {"id": "T002", "titulo": "Cerrada vieja", "estado": "hecha", "testeado": True, "cerrada": "2026-09-02 10:00:00"})
    d = T.cargar()
    assert d["version"] == 1 and [t["id"] for t in d["tareas"]] == ["T001", "T002"]
    t = d["tareas"][0]
    assert (t["quien"], t["tipo"], t["prioridad"]) == ("claude", "codigo", 3) and t["conversaciones"]["chatgpt:autor"]["usos"] == 3
    T.anotar("T001", "tocada")
    crudo = _hot()
    assert crudo["version"] == 1 and "version_historial" not in crudo
    assert not AL.ruta_historial(T.ALMACEN).exists() and not AL.dir_detalle(T.ALMACEN).exists()
    r = crudo["tareas"][0]
    assert r["importancia"] == 5 and r["urgencia"] == 2 and r["coste"] == 4 and r["depende"] == "claude"
    assert r["etiquetas"] == ["cat:codigo", "prov:claude", "tarea_origen:T9"]        # las etiquetas no se mueven en v1
    assert "prioridad" not in r and "origen" not in r and "quien" not in r and "objetivo" not in r
    assert r["conversaciones"]["chatgpt:autor"]["usos"] == 3                          # y el detalle sigue dentro
    assert len(crudo["tareas"]) == 2                                                  # la cerrada tambien, como siempre


def test_en_version_1_las_funciones_de_detalle_trabajan_dentro_de_la_tarea():
    _almacen_viejo({"id": "T001", "titulo": "Vieja"})
    T.fijar_conversacion("T001", "gemini:autor", url="https://g/1", estado="ok")
    for _ in range(3):
        T.fallo_turno("T001", "sin proveedor")
    r = _hot()["tareas"][0]
    assert r["conversaciones"]["gemini:autor"]["url"] == "https://g/1" and r["fallos_turno"] == 3
    assert T.conversacion("T001", "gemini:autor")["usos"] == 1


def test_ida_y_vuelta_a_v2_conserva_todo_lo_que_la_cola_usa():
    t = T.anadir("Completa", importancia=5, urgencia=2, dificultad=4, coste=3, depende="claude", limite="2031-05-05",
                 etiquetas=["cat:propuesta", "prov:gemini", "tema:foco", "epica:T664"], bloqueada_por="T001: esperando",
                 detalle="texto largo del detalle", pregunta_id="q1")
    g = T.cargar()["tareas"][0]
    for k in ("importancia", "urgencia", "dificultad", "coste", "depende", "limite", "bloqueada_por", "detalle",
              "pregunta_id", "testeado", "estado", "creada"):
        assert g[k] == t[k], k
    assert sorted(g["etiquetas"]) == sorted(t["etiquetas"])
    assert T.puntuacion(g) == T.puntuacion(t)
