# -*- coding: utf-8 -*-
"""T859 bloque 6: deduplicado y propuestas POR TEMA a partir de fichas de reels (sin red ni modelos)."""
from __future__ import annotations

import json

from nucleo import reels_tareas as RT

CATALOGO = [{"id": "H050", "nombre": "caveman", "identidad": "https://github.com/JuliusBrussee/caveman", "veredicto": "ADOPTAR"}]
TAREAS = [{"id": "T300", "titulo": "Investigar Graphify para el mapa del codigo", "estado": "hecha", "etiquetas": []},
          {"id": "T301", "titulo": "Revisar borrador de algo", "estado": "pendiente", "etiquetas": ["cat:revision"]}]
REG = [{"id": "T178", "texto": "Investigar Blkit", "causa": "resultado", "motivo": "no aporta: es de pago", "quien": "claude",
        "cuando": "2026-10-01", "informe": "", "origen": ""}]


def _e(nombre, tipo="repo", cats=("nexo",), dueno=None, **kw):
    return {"tipo": tipo, "nombre": nombre, "dueno": dueno, "categorias": list(cats), "que_es": f"que es {nombre}",
            "para_que": "ahorra tokens", "verificado": True, "origen": "modelo", **kw}


def _ficha(*elems, tema="ahorrar tokens", codigo="C1"):
    return {"codigo": codigo, "tema": tema, "resumen": "r", "elementos": list(elems),
            "completitud": {"estado": "completa", "faltan": 0}}


def test_deduplica_contra_catalogo_tareas_y_descartes():
    idx = RT.indice(CATALOGO, TAREAS)
    assert RT.deduplicar(_e("caveman", dueno="JuliusBrussee"), idx, REG)["id"] == "H050"
    assert RT.deduplicar(_e("graphify", dueno="Graphify-Labs"), idx, REG) == {"donde": "tarea", "id": "T300", "estado": "hecha"}
    d = RT.deduplicar(_e("Blkit"), idx, REG)
    assert d["donde"] == "descarte" and "de pago" in d["motivo"]
    assert RT.deduplicar(_e("headroom"), idx, REG) is None
    assert RT.deduplicar(_e("rtk"), idx, REG) is None                       # nombre corto: no se confunde


def test_un_reel_de_20_repos_es_una_sola_investigacion_con_todos_dentro():
    elems = [_e(f"repo-{i:02d}", dueno="o", resolucion={"existe": True, "canonico": f"o/repo-{i:02d}", "estrellas": i})
             for i in range(18)]
    elems += [_e("caveman", dueno="JuliusBrussee"), _e("Blkit")]
    p = RT.plan([_ficha(*elems)], CATALOGO, TAREAS, REG)
    assert len(p["tareas"]) == 1
    t = p["tareas"][0]
    assert t["titulo"].startswith("Investigar (comparativa): ahorrar tokens — 18 elementos")
    assert all(f"o/repo-{i:02d}" in t["detalle"] for i in range(18))
    assert "Ya en NEXO" in t["detalle"] and "H050" in t["detalle"] and "T178" in t["detalle"]
    assert "cat:investigacion" in t["etiquetas"] and "T674" in t["detalle"]
    assert p["anotaciones"] == [{"donde": "catalogo", "id": "H050", "elemento": "JuliusBrussee/caveman", "reel": "C1",
                                 "tema": "ahorrar tokens"}]


def test_destinos_conocimiento_personal_e_investigacion_suelta():
    f = _ficha(_e("FRED", tipo="dato", cats=("trading",)), _e("Alpha Vantage", tipo="web", cats=("trading",)),
               _e("GitHub Student Pack", tipo="curso_oferta", cats=("carrera",)),
               _e("MongoDB students", tipo="curso_oferta", cats=("carrera",)),
               _e("rea", dueno="morluto"), _e("duerme bien", tipo="consejo", cats=("sin_clasificar",)))
    p = RT.plan([f], CATALOGO, TAREAS, REG)
    tipos = {t["tipo"]: t for t in p["tareas"]}
    assert tipos["personal"]["titulo"].startswith("Para Damian:") and "cat:personal" in tipos["personal"]["etiquetas"]
    assert tipos["personal"]["depende"] == "damian"
    assert tipos["investigacion"]["titulo"].startswith("Investigar morluto/rea")
    assert [x["nombre"] for x in p["conocimiento"]["trading"]] == ["FRED", "Alpha Vantage"]
    assert "sin_clasificar" in p["conocimiento"]


def test_lo_citado_que_no_existe_no_entra_y_lo_ya_cubierto_no_crea_tarea():
    f = _ficha(_e("Win", dueno="Mac", origen="citas", resolucion={"existe": False}), _e("caveman", dueno="JuliusBrussee"))
    p = RT.plan([f], CATALOGO, TAREAS, REG)
    assert p["tareas"] == [] and len(p["excluidos"]) == 2


def test_privacidad_ni_url_ni_codigo_del_reel_en_la_tarea():
    f = _ficha(_e("rea", dueno="morluto", url="https://www.instagram.com/reel/SECRETO/"), codigo="SECRETO")
    t = RT.plan([f], CATALOGO, TAREAS, REG)["tareas"][0]
    assert "SECRETO" not in t["titulo"] + t["detalle"] and "instagram" not in t["detalle"]


def test_borrador_lo_entiende_el_circuito_de_revision():
    from nucleo import revision
    p = RT.plan([_ficha(_e("rea", dueno="morluto")), _ficha(_e("Cursor Pro", tipo="curso_oferta", cats=("carrera",)), codigo="C2")],
                CATALOGO, TAREAS, REG)
    ext = revision.extraer_propuestas(RT.borrador_md(p["tareas"], "12/10/2026"))
    assert len(ext["propuestas"]) == 2 and not ext["problemas"]


def test_crear_respeta_el_freno_y_guarda_lo_privado_aparte(tmp_path, monkeypatch):
    from nucleo import freno, revision
    from nucleo import tareas as T
    monkeypatch.setattr(freno, "estado_cola", lambda *a, **k: {"propuestas": freno.LIMITE_PROPUESTAS - 1})
    monkeypatch.setattr(revision, "BORRADORES", tmp_path / "borradores")
    vistos = {}

    def registrar(tid, ruta, texto=None):
        vistos.update(tid=tid, texto=texto)
        return {"revision": {"id": "T900"}, "propuestas": [{"id": "T901", "etiquetas": ["propuesta"], "detalle": "d"}]}
    monkeypatch.setattr(revision, "registrar_borrador", registrar)
    cambios, notas = [], []
    monkeypatch.setattr(T, "actualizar", lambda tid, **c: cambios.append((tid, c)))
    monkeypatch.setattr(T, "anotar", lambda tid, n: notas.append((tid, n)))
    f1 = _ficha(_e("rea", dueno="morluto"), _e("graphify", dueno="Graphify-Labs"), codigo="C1")
    f2 = _ficha(_e("headroom", dueno="x"), _e("FRED", tipo="dato", cats=("trading",)), tema="otro", codigo="C2")
    p = RT.plan([f1, f2], CATALOGO, TAREAS, REG)
    r = RT.crear(p, carpeta=tmp_path / "reels", conocimiento=tmp_path / "con")
    assert r["creadas"] == ["T901"] and r["aplazadas"] == 1 and vistos["tid"] == "T859"
    assert "cat:investigacion" in cambios[0][1]["etiquetas"] and "propuesta" in cambios[0][1]["etiquetas"]
    assert notas[0][0] == "T300" and "C1" not in notas[0][1]
    pend = json.loads((tmp_path / "reels" / "plan_pendiente.json").read_text(encoding="utf-8"))
    assert len(pend["tareas"]) == 1
    assert json.loads((tmp_path / "con" / "trading.json").read_text(encoding="utf-8"))[0]["nombre"] == "FRED"
    assert json.loads((tmp_path / "reels" / "fuentes.json").read_text(encoding="utf-8"))["morluto/rea"] == ["C1"]


def test_plan_md_lo_ensena_todo():
    p = RT.plan([_ficha(_e("rea", dueno="morluto"), _e("FRED", tipo="dato", cats=("trading",)))], CATALOGO, TAREAS, REG)
    md = RT.plan_md(p)
    assert "Investigar morluto/rea" in md and "**trading** (1): FRED" in md


def test_lo_que_no_es_de_la_promesa_no_crea_tarea_sino_contexto():
    """Bloque 6, reel de rea: la pagina 'trending' tenia otros 2 repos de fondo y el pie un anuncio."""
    f = _ficha(_e("rea", dueno="morluto", en_promesa=True), _e("AnyPS5", dueno="boykopovar", cats=("herramientas",)),
               _e("easymachineai", tipo="web", cats=("contenido",)))
    p = RT.plan([f], CATALOGO, TAREAS, REG)
    assert [t["titulo"].split(":")[0] for t in p["tareas"]] == ["Investigar morluto/rea"]
    assert [x["nombre"] for x in p["conocimiento"]["herramientas"]] == ["boykopovar/AnyPS5"]
    assert p["conocimiento"]["contenido"][0]["nombre"] == "easymachineai"


def test_reel_sobre_todo_personal_va_junto_a_la_tarea_de_damian():
    f = _ficha(_e("Google Cloud", tipo="web", cats=("carrera",)), _e("AWS Educate", tipo="web", cats=("carrera",)),
               _e("Azure", tipo="web", cats=("herramientas",)), _e("unrepo", dueno="o", cats=("nexo",)),
               tema="descuentos .edu")
    p = RT.plan([f], CATALOGO, TAREAS, REG)
    tipos = {t["tipo"]: t for t in p["tareas"]}
    assert set(tipos) == {"personal", "investigacion"}
    assert set(tipos["personal"]["elementos"]) == {"Google Cloud", "AWS Educate", "Azure"}
    assert tipos["investigacion"]["elementos"] == ["o/unrepo"]


def test_reel_de_descuentos_de_estudiante_va_entero_a_damian_aunque_el_modelo_lo_llame_herramienta():
    f = _ficha(_e("MongoDB", tipo="web", cats=("herramientas",)), _e("Azure", tipo="web", cats=("nexo",)),
               _e("Google Cloud", tipo="web", cats=("carrera",)), tema="Descuentos para estudiantes con email .EDU")
    p = RT.plan([f], CATALOGO, TAREAS, REG)
    assert [t["tipo"] for t in p["tareas"]] == ["personal"] and len(p["tareas"][0]["elementos"]) == 3


def test_sin_caracteres_de_control_en_las_expresiones_de_reels():
    """Dos veces se colo un retroceso (\x08) en vez de \b al editar: el test pasaba por otras palabras."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    for rel in ("nucleo/reels_tareas.py", "nucleo/reels_ficha.py", "nucleo/reels_huecos.py",
                "nucleo/reels_resolver.py", "extremidades/reels.py"):
        assert b"\x08" not in (raiz / rel).read_bytes(), rel
    assert RT._PERSONAL.search("Student discounts") and not RT._PERSONAL.search("mystudentlike")


def test_oferta_descartada_antes_pero_que_el_reel_ensena_pide_a_damian_comprobar_su_correo(tmp_path, monkeypatch):
    """6b: Cursor estaba descartado (T178) por ser un IDE de pago; el reel ensena su pagina de estudiantes."""
    (tmp_path / "config.json").write_text('{"correo_estudiante": ".uni.example"}', encoding="utf-8")
    monkeypatch.setattr(RT, "CARPETA", tmp_path)
    ficha = _ficha(_e("Blkit", tipo="web", cats=("carrera",), url="https://blkit.example/students"),
                   _e("Beca X", tipo="curso_oferta", cats=("carrera",)),
                   tema="descuentos de estudiante")
    t = RT.plan([ficha], CATALOGO, TAREAS, REG)["tareas"][0]
    assert t["tipo"] == "personal" and "https://blkit.example/students" in t["detalle"]
    assert "(.uni.example)" in t["detalle"] and "reabre T178" in t["detalle"]
