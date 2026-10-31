# -*- coding: utf-8 -*-
"""T290: chat dentro de cada tarea (nucleo/chat_tarea.py). Todo en tmp_path y con dobles:
sin Ollama, sin NVIDIA/Groq/Gemini de verdad."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from nucleo import aprobaciones as ap
from nucleo import chat_tarea as C
from nucleo import parada
from nucleo import tareas as T
from proveedores import Resultado

HOY = date(2026, 9, 28)   # lunes


class Prov:
    """Proveedor de pega: apunta cada prompt que recibe."""

    def __init__(self, nombre, estado="OK", texto="respuesta", disponible=True):
        self.nombre, self._estado, self._texto, self._disp = nombre, estado, texto, disponible
        self.prompts = []
        self.ultimo_modelo = ""

    def disponible(self):
        return self._disp

    def enviar(self, prompt):
        self.prompts.append(prompt)
        return Resultado(self._estado, texto=self._texto if self._estado == "OK" else "", detalle="x")


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "t.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado_tareas.lock")
    monkeypatch.setattr(C, "CARPETA", tmp_path / "chats_tareas")
    monkeypatch.setattr(C, "CANDADO", tmp_path / "chats_tareas" / ".candado.lock")
    monkeypatch.setattr(ap, "ALMACEN", tmp_path / "aprobaciones.json")
    monkeypatch.setattr(ap, "HISTORIAL", tmp_path / "aprobaciones_historial.jsonl")
    monkeypatch.setattr(ap, "CANDADO", tmp_path / ".candado_ap.lock")
    monkeypatch.setattr(parada, "BANDERA", tmp_path / "PARADA_NEXO")
    # Nada de modelos de verdad: Qwen no esta salvo que el test lo ponga.
    monkeypatch.setattr(C, "_qwen_interpretar", lambda prompt: None)
    monkeypatch.setattr(C, "redactar_resumen", lambda t: "Resumen de Qwen.")
    return tmp_path


@pytest.fixture
def dudas(monkeypatch):
    provs = {"nvidia": Prov("nvidia", texto="Falta el paso 2."), "groq": Prov("groq"),
             "gemini_api": Prov("gemini_api"), "qwen": Prov("qwen", texto="Local.")}
    monkeypatch.setattr(C, "proveedores_dudas", lambda: [provs["nvidia"], provs["groq"], provs["gemini_api"]])
    monkeypatch.setattr(C, "_qwen_proveedor", lambda: provs["qwen"])
    return provs


def tarea(**campos):
    return T.anadir(campos.pop("titulo", "Arreglar la web"), detalle=campos.pop("detalle", "Paso 1 hecho. Falta el paso 2."),
                    **campos)


def charla(tid, texto, escalar=False):
    m = C.enviar(tid, texto, escalar)
    return C.procesar(tid, m["n"])


# ------------------------------------------------------------------ interpretar
@pytest.mark.parametrize("texto,accion,valor", [
    ("¿Qué falta?", "pregunta", ""),
    ("Explícamela fácil", "pregunta", ""),
    ("Súbele la prioridad", "prioridad", "subir"),
    ("bájale la prioridad", "prioridad", "bajar"),
    ("prioridad alta", "prioridad", "alta"),
    ("Apárcala una semana", "aparcar", (HOY + timedelta(days=7)).isoformat()),
    ("aparca hasta mañana", "aparcar", (HOY + timedelta(days=1)).isoformat()),
    ("aparcala hasta el 5/10", "aparcar", "2026-10-05"),
    ("aparcala hasta el viernes", "aparcar", "2026-10-02"),
    ("Anota: llamar al técnico", "anotar", "llamar al técnico"),
    ("ponla en marcha", "estado", "en_curso"),
    ("por hacer", "estado", "pendiente"),
    ("esperando", "estado", "esperando"),
    ("redacta el resumen", "resumen", ""),
    ("Cambia el título a Web nueva", "titulo", "Web nueva"),
    ("añade al detalle que falta el logo", "detalle", "falta el logo"),
    ("Crea una tarea para revisar el móvil", "crear", "revisar el móvil"),
    ("ciérrala", "cerrar", ""),
    ("descártala", "descartar", ""),
    ("verifícala con: pytest 12 passed", "verificar", "pytest 12 passed"),
])
def test_reglas(texto, accion, valor):
    r = C.validar(C.reglas(texto, HOY), HOY)
    assert (r["accion"], r["valor"]) == (accion, valor)


def test_pregunta_que_habla_de_prioridad_no_la_cambia_sola():
    # "¿por que tiene mas prioridad...?" lleva "mas": no puede subirla por reglas
    assert C.reglas("¿Por qué tiene más prioridad que la otra?", HOY) is None
    t = tarea()
    charla(t["id"], "¿Por qué tiene más prioridad que la otra?")   # Qwen no esta -> pregunta
    assert T.buscar(t["id"])["importancia"] == t["importancia"]


def test_sin_reglas_decide_qwen_y_lo_raro_es_pregunta(monkeypatch):
    t = tarea()
    monkeypatch.setattr(C, "_qwen_interpretar", lambda p: 'Claro: {"accion": "prioridad", "valor": "alta"}')
    assert C.interpretar("dale caña a esto", t, HOY) == {"accion": "prioridad", "valor": "alta", "quien": "qwen"}
    monkeypatch.setattr(C, "_qwen_interpretar", lambda p: '{"accion": "borrar_todo", "valor": "x"}')
    assert C.interpretar("dale caña", t, HOY)["accion"] == "pregunta"
    monkeypatch.setattr(C, "_qwen_interpretar", lambda p: "no se")
    assert C.interpretar("dale caña", t, HOY)["accion"] == "pregunta"
    monkeypatch.setattr(C, "_qwen_interpretar", lambda p: '{"accion": "aparcar", "valor": "cuando sea"}')
    assert C.interpretar("dale caña", t, HOY)["accion"] == "pregunta"   # sin fecha valida no se aparca


def test_qwen_estado_fuera_de_los_tres_pasa_a_pedir_ok(monkeypatch):
    t = tarea()
    monkeypatch.setattr(C, "_qwen_interpretar", lambda p: '{"accion": "estado", "valor": "bloqueada"}')
    r = charla(t["id"], "esto esta atascado")
    assert r[0]["tipo"] == "propuesta" and r[0]["accion"] == "estado_ok"
    assert T.buscar(t["id"])["estado"] == "pendiente"


# ------------------------------------------------------------ historial y envio
def test_historial_jsonl_una_linea_por_suceso(aislado):
    t = tarea()
    charla(t["id"], "Súbele la prioridad")
    lineas = (aislado / "chats_tareas" / f"{t['id']}.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["tipo"] for x in lineas] == ["mensaje", "accion"]
    assert json.loads(lineas[1])["ref"] == 1


def test_enviar_valida():
    t = tarea()
    with pytest.raises(C.ChatRechazado):
        C.enviar(t["id"], "   ")
    with pytest.raises(C.ChatRechazado):
        C.enviar(t["id"], "x" * (C.MAX_MENSAJE + 1))
    with pytest.raises(C.ChatRechazado):
        C.enviar("T999", "hola")
    with pytest.raises(C.ChatRechazado):
        C.enviar("../../secretos", "hola")


def test_parada_no_acepta_mensajes(aislado):
    t = tarea()
    parada.BANDERA.write_text("prueba", encoding="utf-8")
    with pytest.raises(C.ChatRechazado, match="PARADA"):
        C.enviar(t["id"], "Súbele la prioridad")


def test_parada_activada_despues_no_actua(aislado):
    t = tarea()
    m = C.enviar(t["id"], "Súbele la prioridad")
    parada.BANDERA.write_text("prueba", encoding="utf-8")
    r = C.procesar(t["id"], m["n"])
    assert "PARADA" in r[0]["texto"]
    assert T.buscar(t["id"])["importancia"] == t["importancia"]


# ------------------------------------------------------------- acciones solas
def test_prioridad_sola_anotada_y_deshacer():
    t = tarea(importancia=3, urgencia=3)
    r = charla(t["id"], "Súbele la prioridad")[0]
    assert r["tipo"] == "accion" and r["despues"] == {"importancia": 4, "urgencia": 4}
    x = T.buscar(t["id"])
    assert (x["importancia"], x["urgencia"]) == (4, 4)
    assert "prioridad subida" in x["notas"][-1]["texto"]
    C.deshacer(t["id"], r["n"])
    x = T.buscar(t["id"])
    assert (x["importancia"], x["urgencia"]) == (3, 3)
    assert "deshecho" in x["notas"][-1]["texto"]
    conv = C.conversacion(t["id"])
    assert conv[-1]["deshecha"] is True
    with pytest.raises(C.ChatRechazado, match="Ya estaba"):
        C.deshacer(t["id"], r["n"])


def test_deshacer_no_pisa_un_cambio_posterior():
    t = tarea(importancia=3, urgencia=3)
    r = charla(t["id"], "Súbele la prioridad")[0]
    T.actualizar(t["id"], importancia=5)          # Damian o NEXO la cambian despues
    with pytest.raises(C.ChatRechazado, match="ha cambiado"):
        C.deshacer(t["id"], r["n"])
    assert T.buscar(t["id"])["importancia"] == 5


def test_anotar_y_deshacer_quita_solo_esa_nota():
    t = tarea()
    T.anotar(t["id"], "nota de antes")
    r = charla(t["id"], "anota: llamar al técnico")[0]
    assert T.buscar(t["id"])["notas"][-1]["texto"] == "Chat (Damián): llamar al técnico"
    C.deshacer(t["id"], r["n"])
    assert [n["texto"] for n in T.buscar(t["id"])["notas"]] == ["nota de antes"]


def test_estado_solo_entre_los_tres():
    t = tarea()
    r = charla(t["id"], "ponla en marcha")[0]
    assert r["tipo"] == "accion" and T.buscar(t["id"])["estado"] == "en_curso"
    C.deshacer(t["id"], r["n"])
    assert T.buscar(t["id"])["estado"] == "pendiente"
    T.actualizar(t["id"], estado="bloqueada")
    r = charla(t["id"], "ponla en marcha")[0]
    assert r["tipo"] == "propuesta"                 # desde bloqueada, con OK
    assert T.buscar(t["id"])["estado"] == "bloqueada"


def test_aparcar_y_deshacer(monkeypatch):
    t = tarea()
    r = charla(t["id"], "Apárcala una semana")[0]
    x = T.buscar(t["id"])
    assert r["tipo"] == "accion" and x["estado"] == "aparcada"
    assert x["aparcada_hasta"] == (date.today() + timedelta(days=7)).isoformat()
    C.deshacer(t["id"], r["n"])
    x = T.buscar(t["id"])
    assert x["estado"] == "pendiente" and "aparcada_hasta" not in x


def test_aparcar_cerrada_no_se_hace():
    t = tarea()
    T.actualizar(t["id"], estado="hecha")
    r = charla(t["id"], "Apárcala una semana")[0]
    assert r["tipo"] == "respuesta" and "No lo he hecho" in r["texto"]


def test_resumen_con_qwen_y_deshacer():
    t = tarea()
    r = charla(t["id"], "redacta el resumen")[0]
    assert T.buscar(t["id"])["resumen_humano"] == "Resumen de Qwen."
    assert T.buscar(t["id"])["detalle"] == t["detalle"]      # nunca pisa el detalle
    C.deshacer(t["id"], r["n"])
    assert "resumen_humano" not in T.buscar(t["id"])


# ------------------------------------------------------------- con aprobacion
@pytest.mark.parametrize("texto,accion", [("Cambia el título a Web nueva", "titulo"), ("ciérrala", "cerrar"),
                                          ("descártala", "descartar"), ("Crea una tarea para X", "crear")])
def test_lo_grande_pide_ok_y_no_toca_nada(texto, accion):
    t = tarea()
    antes = T.buscar(t["id"])
    r = charla(t["id"], texto)[0]
    assert r["tipo"] == "propuesta" and r["accion"] == accion
    assert ap.ver(r["aprobacion"])["estado"] == "pendiente"
    assert ap.ver(r["aprobacion"])["origen"] == "chat_tarea"
    assert T.buscar(t["id"]) == antes
    assert len(T.cargar()["tareas"]) == 1
    assert C.conversacion(t["id"])[-1]["estado"] == "pendiente"


def test_aprobar_ejecuta_una_vez_y_anota():
    t = tarea()
    r = charla(t["id"], "Cambia el título a Web nueva")[0]
    d = C.decidir(t["id"], r["n"], True)
    assert d["decision"] == "aprobada"
    x = T.buscar(t["id"])
    assert x["titulo"] == "Web nueva" and "aprobado" in x["notas"][-1]["texto"]
    assert ap.ver(r["aprobacion"])["estado"] == "usada"
    with pytest.raises(C.ChatRechazado, match="ya estaba decidida"):
        C.decidir(t["id"], r["n"], True)
    assert C.conversacion(t["id"])[-1]["estado"] == "aprobada"


def test_denegar_no_hace_nada():
    t = tarea()
    r = charla(t["id"], "descártala")[0]
    C.decidir(t["id"], r["n"], False)
    assert T.buscar(t["id"])["estado"] == "pendiente"
    assert ap.ver(r["aprobacion"])["estado"] == "denegada"
    assert C.conversacion(t["id"])[-1]["estado"] == "denegada"


def test_caducada_no_se_ejecuta(monkeypatch):
    t = tarea()
    r = charla(t["id"], "descártala")[0]
    datos = ap.cargar()
    datos["solicitudes"][0]["vence"] = "2000-01-01 00:00:00"
    ap._guardar(datos)
    assert C.conversacion(t["id"])[-1]["estado"] == "caducada"
    d = C.decidir(t["id"], r["n"], True)
    assert d["decision"] == "caducada"
    assert T.buscar(t["id"])["estado"] == "pendiente"


def test_ejecutar_codigo_nunca_se_ejecuta_queda_como_tarea(monkeypatch):
    t = tarea()
    monkeypatch.setattr(C, "_qwen_interpretar", lambda p: '{"accion": "ejecutar", "valor": "instalar ffmpeg"}')
    r = charla(t["id"], "instala ffmpeg en el pc")[0]
    assert r["tipo"] == "propuesta" and r["accion"] == "ejecutar"
    d = C.decidir(t["id"], r["n"], True)
    assert "no lo ejecuta" in d["texto"]
    nueva = T.cargar()["tareas"][-1]
    assert nueva["id"] != t["id"] and f"tarea_origen:{t['id']}" in nueva["etiquetas"]


def test_verificar_exige_evidencia_y_tarea_hecha():
    t = tarea()
    r = charla(t["id"], "verifícala con: pytest tests -q dio 12 passed en 3 s")[0]
    d = C.decidir(t["id"], r["n"], True)
    assert d["decision"] == "error" and "ciérrala primero" in d["texto"]
    assert T.buscar(t["id"])["testeado"] is False


def test_cerrar_respeta_revision_pendiente():
    t = tarea(etiquetas=["revision_claude:T001_x.md"])
    r = charla(t["id"], "ciérrala")[0]
    d = C.decidir(t["id"], r["n"], True)
    assert d["decision"] == "error"
    assert T.buscar(t["id"])["estado"] == "pendiente"


# ------------------------------------------------------------------- dudas
def test_duda_la_contesta_nvidia_con_solo_esa_tarea(dudas):
    otra = tarea(titulo="Tarea secreta de otra cosa", detalle="no debe salir")
    t = tarea(bloqueada_por=otra["id"])
    for i in range(12):
        C._anadir(t["id"], tipo="mensaje", quien="damian", texto=f"mensaje viejo {i}")
    r = charla(t["id"], "¿Qué falta?")[0]
    assert r["tipo"] == "respuesta" and r["quien"] == "nvidia" and r["texto"] == "Falta el paso 2."
    prompt = dudas["nvidia"].prompts[0]
    assert "Arreglar la web" in prompt and "Falta el paso 2" in prompt
    assert "Tarea secreta de otra cosa" in prompt       # relacionada: solo su titulo
    assert "no debe salir" not in prompt                # ...nunca su detalle
    assert "mensaje viejo 1\n" not in prompt and "mensaje viejo 11" in prompt   # solo los ultimos 10
    assert not dudas["groq"].prompts and not dudas["qwen"].prompts


def test_nvidia_caido_pasa_a_groq_luego_gemini(dudas):
    dudas["nvidia"]._estado = "ERROR"
    dudas["groq"]._disp = False
    t = tarea()
    r = charla(t["id"], "¿Qué falta?")[0]
    assert r["quien"] == "gemini_api"


def test_nada_disponible_lo_dice(dudas):
    for p in dudas.values():
        p._disp = False
    t = tarea()
    r = charla(t["id"], "¿Qué falta?")[0]
    assert r["quien"] == "nexo" and r["error"] and "Escalar" in r["texto"]


def test_tarea_personal_no_sale_del_pc(dudas):
    t = tarea(etiquetas=["cat:personal"])
    r = charla(t["id"], "¿Qué falta?")[0]
    assert r["quien"] == "qwen" and "tarea personal" in r["solo_local"]
    assert not dudas["nvidia"].prompts and not dudas["groq"].prompts


def test_dato_privado_no_sale_del_pc(dudas):
    t = tarea(detalle="Mirar C:\\Users\\damia\\Desktop\\algo")
    r = charla(t["id"], "¿Qué falta?")[0]
    assert r["quien"] == "qwen" and not dudas["nvidia"].prompts


# ------------------------------------------------------------------ escalar
def test_escalar_no_llama_a_nadie_y_queda_para_claude(dudas):
    t = tarea()
    r = charla(t["id"], "¿Esto rompe algo?", escalar=True)[0]
    assert r["tipo"] == "escalado"
    assert not any(p.prompts for p in dudas.values())
    pend = C.escalados()
    assert [(e["tarea"], e["pregunta"]) for e in pend] == [(t["id"], "¿Esto rompe algo?")]
    C.responder_claude(t["id"], r["n"], "No rompe nada.")
    assert C.escalados() == []
    assert C.conversacion(t["id"])[-1]["quien_nombre"] == "Claude"


def test_sin_contestar():
    t = tarea()
    m = C.enviar(t["id"], "hola")
    assert C.sin_contestar(t["id"])["n"] == m["n"]
    C.procesar(t["id"], m["n"])
    assert C.sin_contestar(t["id"]) is None
