"""T1010 paso 2, punto 3: migracion de la cola al formato v2 (herramientas_nube/migrar_tareas_v2.py) y espejo.

Todo en tmp_path: el almacen lo redirige el fixture autouse `turnos_aislados`; nunca se toca memoria/ real.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from nucleo import tareas as T
from nucleo import tareas_almacen as AL

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("migrar_tareas_v2", RAIZ / "herramientas_nube" / "migrar_tareas_v2.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)
_spec2 = importlib.util.spec_from_file_location("publicar_nube", RAIZ / "herramientas_nube" / "publicar_nube.py")
PN = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(PN)

BASE = {"importancia": 3, "urgencia": 3, "dificultad": 3, "coste": 2, "depende": "ia", "estado": "pendiente",
        "limite": None, "etiquetas": [], "bloqueada_por": "", "pregunta_id": "", "testeado": False, "notas": [],
        "creada": "2026-09-01 10:00:00", "actualizada": "2026-09-01 10:00:00", "cerrada": None, "detalle": ""}


def _notas(n):
    return [{"cuando": f"2026-09-0{1 + i % 9} 10:00:0{i % 10}", "texto": f"nota {i}"} for i in range(n)]


def _almacen_v1():
    tareas = [
        {**BASE, "id": "T001", "titulo": "Viva con notas", "importancia": 5, "urgencia": 1, "coste": 5, "depende": "claude",
         "etiquetas": ["cat:codigo", "prov:claude", "tarea_origen:T9", "de_borrador:a.md", "tema:foco"],
         "notas": _notas(9), "conversaciones": {"chatgpt:autor": {"url": "https://x/1", "usos": 2}},
         "detalle": "texto largo " * 50, "limite": "2030-01-01", "bloqueada_por": "T002"},
        {**BASE, "id": "T002", "titulo": "Cerrada", "estado": "hecha", "testeado": True, "cerrada": "2026-09-02 10:00:00",
         "notas": _notas(2), "etiquetas": ["cat:propuesta", "revisado:aprobado"]},
        {**BASE, "id": "T003", "titulo": "Descartada", "estado": "descartada", "cerrada": "2026-09-03 10:00:00",
         "descarte": {"causa": "idea", "motivo": "no aporta nada", "cuando": "2026-09-03 10:00:00"}},
        {**BASE, "id": "T004", "titulo": "Externa", "depende": "externo", "estado": "esperando", "fallos_turno": 2,
         "resultado": {"decision": "ADAPTAR"}},
        {**BASE, "id": "T005", "titulo": "Aparcada", "estado": "aparcada", "aparcada_hasta": "2030-05-05",
         "estado_antes_de_aparcar": "pendiente"},
    ]
    T.ALMACEN.parent.mkdir(parents=True, exist_ok=True)
    T.ALMACEN.write_text(json.dumps({"version": 1, "siguiente_id": 6, "tareas": tareas}, indent=2), encoding="utf-8")
    return tareas


def test_la_migracion_no_pierde_nada_y_deja_el_formato_nuevo():
    crudas = _almacen_v1()
    antes = T.ALMACEN.stat().st_size
    informe = M.migrar(T.ALMACEN.parent)
    assert informe["estado"] == "ok" and informe["fallos"] == [], informe["fallos"]
    assert (informe["tareas"], informe["vivas"], informe["cerradas"]) == (5, 3, 2)
    hot = json.loads(T.ALMACEN.read_text(encoding="utf-8"))
    assert hot["version"] == 2 and [r["id"] for r in hot["tareas"]] == ["T001", "T004", "T005"]
    assert M.comparar(crudas, T.cargar(detalle=True)["tareas"]) == []
    # mapeo
    t1 = hot["tareas"][0]
    assert (t1["quien"], t1["tipo"], t1["prioridad"], t1["esfuerzo"], t1["fecha_limite"], t1["depende_de"]) == \
        ("claude", "codigo", 3, 3, "2030-01-01", ["T002"])
    assert "importancia" not in t1 and "urgencia" not in t1 and "coste" not in t1 and "coste_eur" not in t1
    assert t1["origen"] == {"prov": "claude", "tarea_origen": "T9", "de_borrador": "a.md"}
    assert t1["etiquetas"] == ["tema:foco"] and len(t1["notas"]) == 5 and "conversaciones" not in t1
    assert hot["tareas"][1]["quien"] == "damian" and hot["tareas"][1]["motivo_quien"].startswith("externo")
    # el viejo coste 1-5 no pasa a euros: queda vacio y la tarea sigue funcionando
    g = T.cargar()["tareas"][0]
    assert g["coste"] == 2 and g["coste_eur"] is None and g["depende"] == "claude"
    assert AL.leer_detalle(T.ALMACEN, "T001")["conversaciones"]["chatgpt:autor"]["usos"] == 2
    assert AL.leer_detalle(T.ALMACEN, "T003")["descarte"]["causa"] == "idea"
    assert AL.leer_detalle(T.ALMACEN, "T004")["fallos_turno"] == 2
    assert informe["despues"]["tareas.json"] < informe["antes"]["tareas.json"] <= antes


def test_migrar_dos_veces_no_hace_nada_la_segunda():
    _almacen_v1()
    assert M.migrar(T.ALMACEN.parent)["estado"] == "ok"
    contenido = T.ALMACEN.read_bytes()
    assert M.migrar(T.ALMACEN.parent)["estado"] == "ya_migrado" and T.ALMACEN.read_bytes() == contenido


def test_comparar_detecta_una_perdida():
    crudas = _almacen_v1()
    M.migrar(T.ALMACEN.parent)
    despues = T.cargar(detalle=True)["tareas"]
    despues[0]["titulo"] = "otro"
    despues[0]["etiquetas"].remove("tema:foco")
    despues[1]["notas"] = []
    fallos = M.comparar(crudas, despues)
    assert any("T001.titulo" in f for f in fallos) and any("T001.etiquetas" in f for f in fallos)


def test_simular_no_toca_el_almacen_y_cuenta(capsys):
    _almacen_v1()
    antes = T.ALMACEN.read_bytes()
    assert M.simular() == 0
    assert T.ALMACEN.read_bytes() == antes and not AL.ruta_historial(T.ALMACEN).exists()
    salida = capsys.readouterr().out
    assert "SIMULACION" in salida and "TODO CUADRA" in salida and "KB" in salida


def test_aplicar_hace_copia_previa_y_se_niega_con_un_turno_en_marcha(tmp_path, capsys):
    _almacen_v1()
    raiz = tmp_path / "raiz"
    (raiz / "memoria").mkdir(parents=True)
    (raiz / "memoria" / "turno_en_marcha.json").write_text("{}", encoding="utf-8")
    original = T.ALMACEN.read_bytes()
    assert M.aplicar(False, raiz) == 2 and T.ALMACEN.read_bytes() == original
    assert "TURNO EN MARCHA" in capsys.readouterr().out
    assert M.aplicar(True, raiz) == 0
    copias = list((raiz / "_archivo").glob("*/migracion_tareas_v2"))
    assert len(copias) == 1 and (copias[0] / "tareas.json").read_bytes() == original
    assert (copias[0] / "NOTA.md").is_file() and "TODO CUADRA" in (copias[0] / "INFORME.md").read_text(encoding="utf-8")
    assert json.loads(T.ALMACEN.read_text(encoding="utf-8"))["version"] == 2


def test_si_la_comprobacion_falla_restaura_la_copia_y_aparta_lo_creado(tmp_path, monkeypatch, capsys):
    _almacen_v1()
    raiz = tmp_path / "raiz"
    (raiz / "memoria").mkdir(parents=True)
    monkeypatch.setattr(M, "comparar", lambda a, d: ["T001.titulo: 'a' -> 'b'"])
    assert M.aplicar(False, raiz) == 1
    restaurado = json.loads(T.ALMACEN.read_text(encoding="utf-8"))
    assert restaurado["version"] == 1 and [t["id"] for t in restaurado["tareas"]] == \
        ["T001", "T002", "T003", "T004", "T005"]
    assert not AL.ruta_historial(T.ALMACEN).exists() and not AL.dir_detalle(T.ALMACEN).exists()
    apartado = list((raiz / "_archivo").glob("*/migracion_tareas_v2/creado_por_el_intento_fallido"))[0]
    assert (apartado / "tareas_historial.jsonl").is_file() and (apartado / "tareas_detalle").is_dir()
    assert "FALLIDA" in capsys.readouterr().out


def test_el_script_responde_a_help_sin_hacer_nada():
    p = subprocess.run([sys.executable, str(RAIZ / "herramientas_nube" / "migrar_tareas_v2.py"), "--help"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0 and "--simular" in p.stdout and "--aplicar" in p.stdout


# ------------------------------------------------------------------ espejo

def test_el_espejo_no_lleva_lo_privado_pero_si_los_archivos_nuevos_de_la_cola():
    assert PN.excluida("memoria/perfil_privado/tareas/T123.md")
    assert not PN.excluida("memoria/tareas.json")
    assert not PN.excluida("memoria/tareas_historial.jsonl")
    assert not PN.excluida("memoria/tareas_detalle/T123.json")


def test_el_espejo_redacta_tokens_tambien_en_el_historial_y_el_detalle():
    falso = b'{"nota": "clave sk-' + b"a" * 30 + b'"}'
    for ruta in ("memoria/tareas_historial.jsonl", "memoria/tareas_detalle/T1.json"):
        datos, n = PN.redactar(ruta, falso)
        assert n == 1 and b"a" * 30 not in datos
