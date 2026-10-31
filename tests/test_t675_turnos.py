# -*- coding: utf-8 -*-
"""T675 (Damian 03/10): primera fase de la mejora de los turnos y sus prompts, con datos de memoria/ y registros/.
(1) salida cortada a mitad (T671, groq); (2) investigacion sobre el PROPIO NEXO sin plantilla de herramienta externa;
(3) los turnos de revision no recorren el bot de Telegram (congelado desde el 27/09)."""
from __future__ import annotations

from nucleo import plantillas_turno as P, trabajo

LARGO = "Frase completa del informe. " * 30
PROP = "- QUE: cambio concreto | DONDE: documentacion | VALOR: 5 | ESFUERZO: 2 | RIESGO: bajo: solo texto"


def test_salida_cortada_a_mitad_de_frase_se_detecta():
    assert trabajo._truncado(LARGO + "y la conclusion es que el")
    assert trabajo._truncado(LARGO + "\n### PROPUESTAS IMPLEMENTABLES\n- QUE: cambio | DONDE: router | VALOR: 5")
    assert trabajo._truncado(LARGO + "\n" + PROP[:-30])               # el RIESGO quedo a medias


def test_salida_completa_no_se_marca_como_cortada():
    assert not trabajo._truncado(LARGO + "\n### PROPUESTAS IMPLEMENTABLES\n" + PROP)
    assert not trabajo._truncado(LARGO + "\nFuentes:\n- https://github.com/x/y")      # lista de fuentes sin punto
    assert not trabajo._truncado(LARGO.strip())
    assert not trabajo._truncado("BLOQUEO: falta el dato X")                        # respuestas cortas no se miran
    assert not trabajo._truncado("")


def test_el_autor_cortado_pasa_al_siguiente_proveedor(monkeypatch):
    class Prov:
        def __init__(self, nombre, texto):
            self.nombre, self.texto = nombre, texto
    cortada, buena = Prov("groq", LARGO + "y entonces"), Prov("gemini_api", LARGO + "\n" + PROP)
    monkeypatch.setattr(trabajo, "_generadores", lambda cat: [cortada, buena])

    class R:
        ok, detalle, meta = True, "", {}

        def __init__(self, texto):
            self.texto = texto

    d = trabajo.Delegacion.__new__(trabajo.Delegacion)
    d.t, d.cat, d.exp, d.version = {"id": "T1", "titulo": "x", "etiquetas": []}, "investigacion", {"llamadas": []}, ""
    d._en_conversacion = lambda prov, prompt, rol, tipo, buscar=False: R(prov.texto)
    d._entrega = lambda v: None
    assert d.trabajar() is buena
    assert d.exp["truncados"] == ["groq"]


def test_investigacion_interna_no_pide_url_oficial_ni_licencia():
    interna = {"id": "T1", "titulo": "t", "detalle": "material", "etiquetas": ["cat:investigacion", "material:interno"]}
    externa = {"id": "T2", "titulo": "t", "detalle": "x", "etiquetas": ["cat:investigacion"]}
    ti, te = trabajo._instruccion(interna, "investigacion"), trabajo._instruccion(externa, "investigacion")
    assert "SOLO el MATERIAL DEL PROPIO NEXO" in ti and "URL oficial SOLO si estas seguro" not in ti
    assert "ADOPTAR / ADAPTAR / DESCARTAR" in ti and "PROPUESTAS IMPLEMENTABLES" in ti
    assert "identidad exacta" in te and "PROPIO NEXO" not in te


def test_los_turnos_de_revision_no_recorren_telegram(tmp_path):
    for rel in ("canal/bot.py", "canal/buzon.py", "nucleo/tareas.py", "docs/TELEGRAM.md", "docs/ARRANQUE.md"):
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x = 1\n" if rel.endswith(".py") else "# t\n", encoding="utf-8")
    assert P.archivos("revisar_codigo", tmp_path) == ["nucleo/tareas.py"]
    assert P.archivos("revisar_archivos", tmp_path) == ["docs/ARRANQUE.md"]


def test_formatos_validos_que_acaban_sin_punto_no_son_cortes():
    assert not trabajo._truncado(LARGO + "\n### PROPUESTAS IMPLEMENTABLES\nNINGUNA: NEXO ya tiene reglas equivalentes")
    assert not trabajo._truncado(LARGO + "\n- **QUE:** cargar la politica | **DONDE:** router | **VALOR:** 3 | "
                                         "**ESFUERZO:** 3 | **RIESGO:** medio: puede no activarse cuando toca")
    assert not trabajo._truncado(LARGO + "\n| col a | col b |")


# ------------------------------------------------------------------ orden de autor (Damian 04/10: la calidad va primero)
def test_orden_de_autor_chatgpt_nvidia_gemini_api_gemini_web_groq(monkeypatch):
    monkeypatch.setattr(trabajo, "_web", lambda: True)
    monkeypatch.setattr("proveedores.NvidiaProvider.disponible", lambda self: True)
    monkeypatch.setattr("proveedores.GroqProvider.disponible", lambda self: True)
    monkeypatch.setattr("proveedores.GeminiAPIProvider.disponible", lambda self: True)
    monkeypatch.setattr("proveedores.ChatGPTProvider.disponible", lambda self: True)
    monkeypatch.setattr("proveedores.GeminiProvider.disponible", lambda self: True)
    monkeypatch.setattr("proveedores.QwenProvider.disponible", lambda self: True)
    orden = [p.nombre for p in trabajo._generadores("redaccion")]
    assert orden == ["chatgpt", "nvidia", "gemini_api", "gemini", "groq", "qwen"]
    assert "qwen" not in [p.nombre for p in trabajo._generadores("investigacion")]


def test_sin_web_quedan_las_api_en_su_orden(monkeypatch):
    monkeypatch.setattr(trabajo, "_web", lambda: False)
    for clase in ("NvidiaProvider", "GroqProvider", "GeminiAPIProvider", "ChatGPTProvider", "GeminiProvider"):
        monkeypatch.setattr(f"proveedores.{clase}.disponible", lambda self: True)
    assert [p.nombre for p in trabajo._generadores("investigacion")] == ["nvidia", "gemini_api", "groq"]


def test_tasa_de_aprobacion_por_proveedor_autor_antes_y_desde_el_cambio(tmp_path, monkeypatch):
    from nucleo import revision, tribunal
    from nucleo import tareas as T
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "x.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado")
    monkeypatch.setattr(revision, "BORRADORES", tmp_path / "borradores")
    (tmp_path / "borradores").mkdir()
    casos = [("a.md", "chatgpt", "2026-10-01", "APROBADO"), ("b.md", "chatgpt", "2026-10-02", "DESCARTADO"),
             ("c.md", "nvidia", "2026-10-05", "APROBADO"), ("d.md", "nvidia", "2026-10-06", "REHACER"),
             ("e.md", "nvidia", "2026-10-07", "APROBADO"), ("f.md", "groq", "2026-10-07", "SUPERADO")]
    for nombre, autor, dia, v in casos:
        (tmp_path / "borradores" / nombre).write_text(f"<!-- ESCALAR | autor {autor} | revisores x -->\n# T\n", encoding="utf-8")
        t = T.anadir(f"Revisar {nombre}", etiquetas=[revision.ET_REVISION])
        T.anotar(t["id"], f"Revision de Claude del borrador {nombre}: {v}. motivo")
        datos = T.cargar()
        for x in datos["tareas"]:
            if x["id"] == t["id"]:
                x["notas"][-1]["cuando"] = f"{dia} 10:00:00"
        T.guardar(datos)
    r = tribunal.tasa_por_autor("2026-10-04")["autores"]
    assert r["chatgpt"]["antes"] == {"n": 2, "aprobado": 1, "tasa": 0.5}
    assert r["nvidia"]["desde"] == {"n": 3, "aprobado": 2, "tasa": 0.667}
    assert "groq" not in r                                     # SUPERADO no cuenta
    assert r["nvidia"]["antes"]["tasa"] is None
