# -*- coding: utf-8 -*-
"""T751: la web avisa (push) de cada aprobacion AMBAR nueva y deja decidirla en Bandejas; antes solo lo hacia
Telegram. Todo a tmp_path (conftest de interfaz)."""
from __future__ import annotations

from interfaz import presentar
from interfaz.push import Almacen, Notificador
from interfaz.vigilancia import Vigilante
from nucleo import aprobaciones as ap

CLAVE = "sk-" + "b" * 30


def _post(cliente, csrf, url, **datos):
    return cliente.post(url, data=datos, headers={"X-CSRF-Token": csrf})


def test_vigilancia_solo_avisa_de_ambar_nuevas(tmp_path):
    vieja = ap.solicitar("instalar_paquete", "de antes de arrancar", origen="mcp")
    v = Vigilante(bus=None)
    assert v._revisar_aprobaciones() == []          # foto inicial: lo de antes no se reenvia
    v._iniciado = True
    assert v._revisar_aprobaciones() == []          # sin cambios en el fichero: ni se relee
    nueva = ap.solicitar("instalar_paquete", f"pip install x con {CLAVE}", origen="mcp")
    ap.solicitar("implementar T1", "diff", nivel="R2", origen="riesgo")   # la matriz va por su bandeja
    eventos = v._revisar_aprobaciones()
    assert [(t, d["id"]) for t, d in eventos] == [("aprobacion", nueva["id"])]
    assert CLAVE not in eventos[0][1]["frase"] and eventos[0][1]["origen"] == "mcp"
    assert v._revisar_aprobaciones() == []
    assert vieja["id"] != nueva["id"]


def test_push_de_aprobacion_una_vez_y_sin_secretos(tmp_path):
    n = Notificador(Almacen(tmp_path / "push"))
    datos = {"id": "A0012", "origen": "mcp", "frase": f"instalar: pip install x {CLAVE}", "vence": "x"}
    aviso = n.aviso_de("aprobacion", datos)
    assert aviso["titulo"] == "Aprobación A0012 (mcp)" and aviso["ruta"] == "/bandejas#bandeja-ambar"
    assert aviso["urgencia"] == "high" and CLAVE not in aviso["cuerpo"]
    assert n.aviso_de("aprobacion", datos) is None
    n.cerrar()


def test_bandeja_ambar_aprobar_y_denegar(cliente, csrf):
    a = ap.solicitar("instalar_paquete", "pip install x", origen="mcp")
    b = ap.solicitar("borrar_carpeta", "tmp", origen="mcp")
    html = cliente.get("/bandejas").text
    assert 'id="bandeja-ambar"' in html and 'hx-get="/centro/ambar"' in html
    panel = cliente.get("/centro/ambar").text
    assert a["id"] in panel and "Aprobar" in panel
    r = _post(cliente, csrf, "/ambar/decidir", id=a["id"], accion="aprobar")
    assert f"Aprobada: {a['id']}" in r.text and ap.ver(a["id"])["estado"] == "aprobada"
    assert ap.ver(a["id"])["eventos"][-1]["quien"] == "damian:web"
    r = _post(cliente, csrf, "/ambar/decidir", id=b["id"], accion="denegar")
    assert f"Denegada: {b['id']}" in r.text and ap.ver(b["id"])["estado"] == "denegada"


def test_bandeja_ambar_no_decide_la_matriz_ni_sin_csrf(cliente, csrf):
    r2 = ap.solicitar("implementar T1", "diff", nivel="R2", origen="riesgo")
    r = _post(cliente, csrf, "/ambar/decidir", id=r2["id"], accion="aprobar")
    assert "matriz de riesgo" in r.text and ap.ver(r2["id"])["estado"] == "pendiente"
    a = ap.solicitar("instalar_paquete", "pip install y", origen="mcp")
    assert cliente.post("/ambar/decidir", data={"id": a["id"], "accion": "aprobar"}).status_code == 403
    assert ap.ver(a["id"])["estado"] == "pendiente"


def test_te_toca_muestra_ambar_sin_duplicar_las_del_chat():
    a = ap.solicitar("instalar_paquete", "pip install z", origen="mcp")
    ap.solicitar("ok_chat", "T5", origen="chat_tarea")
    chips = [t for t in presentar.te_toca(None)["tarjetas"] if t["chip"].startswith("Aprobación ámbar")]
    assert [t["titulo"].split(" · ")[0] for t in chips] == [a["id"]]


# ------------------------------- Damian 05/10: lo que le llega, explicado en lenguaje claro

def test_bandeja_ambar_explica_que_para_que_quien_riesgo_y_si_no(cliente, csrf):
    a = ap.solicitar("ejecutar comando", "git checkout HEAD -- nucleo/guardia_python.py; git apply "
                     "documentacion/propuestas/guardia_ayuda_0510.patch", origen="mcp")
    panel = cliente.get("/centro/ambar").text
    # T1020: la ficha es la del guardian; un parche que toca un archivo de control es riesgo ALTO (antes MEDIO)
    for texto in ("Aplicar un parche", "Para qué", "Quién lo pide", "coordinador", "Riesgo", "ALTO",
                  "Si dices que no", "cuenta como NO", "Ver la orden exacta", a["id"]):
        assert texto in panel, texto


def test_push_de_aprobacion_dice_que_es_y_quien_lo_pide():
    ap.solicitar("ejecutar comando", "de antes", origen="mcp")
    v = Vigilante(bus=None)
    v._revisar_aprobaciones()
    v._iniciado = True
    ap.solicitar("ejecutar comando", "winget install algo", origen="mcp")
    (_, datos), = v._revisar_aprobaciones()
    # T1020: la frase sale de la ficha del guardian (instalar o cambiar el sistema es riesgo ALTO)
    assert datos["frase"].startswith("Instalar programas") and "Lo pide Claude." in datos["frase"]
    assert "Riesgo: ALTO" in datos["frase"]
