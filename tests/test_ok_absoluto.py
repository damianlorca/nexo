# -*- coding: utf-8 -*-
"""T183 + T189: protocolo OK absoluto en nucleo/trabajo.py y auditor de delegaciones. Sin red ni Chrome."""
from __future__ import annotations

import json

import pytest

from nucleo import auditor, avisos, trabajo
from nucleo import tareas as T
from proveedores import Resultado

# T192: toda investigacion termina con PROPUESTAS IMPLEMENTABLES (punto h del auditor).
PROP = ("\n### PROPUESTAS IMPLEMENTABLES\n- QUE: usar X en los roles | DONDE: roles y prompts | VALOR: 4 | "
        "ESFUERZO: 2 | RIESGO: bajo: solo texto\n")
V0 = "ENTENDIMIENTO:\nSe pide un informe de X.\n### INFORME\n" + "1) Que es: X es una libreria. " * 20 + PROP
V1 = "1) Que es: X es una libreria corregida. " * 20 + PROP
CIERRE_OK = ("\n### AUTOAUDITORIA\nCAMBIOS:\n- corregida la licencia\nRECHAZADO:\n- ninguno\nCIERRE: OK ABSOLUTO\n"
             "COMPROBADO:\n- la licencia MIT contra el README del repo\n- la URL oficial abre el repositorio correcto\n"
             "- las cinco secciones pedidas estan y en orden\n")
# Mensaje N (resultado mejorado): CAMBIOS sin cierre. El OK va en el mensaje N+1 (Damian 27/09).
CAMBIOS = "\n### AUTOAUDITORIA\nCAMBIOS:\n- corregida la licencia\nRECHAZADO:\n- ninguno\n"
CIERRE_SIN_JUSTIFICAR = "\n### AUTOAUDITORIA\nCIERRE: OK ABSOLUTO\n"
REV_CAMBIOS = ("FALLOS:\n- \"licencia GPL\" es MIT\nOMISIONES:\n- falta el coste\nMEJORAS:\n- ninguno\n"
               "AÑADIR:\n- Anadir un tutorial Hello World paso a paso\n- comparativa con LangChain y AutoGPT\n"
               "GRAVEDAD: MEDIA\nVEREDICTO: CAMBIOS_NECESARIOS")
REV_OK = "FALLOS:\n- ninguno\nOMISIONES:\n- ninguno\nMEJORAS:\n- ninguno\nAÑADIR:\n- ninguno\nGRAVEDAD: BAJA\nVEREDICTO: APROBADO"
REV_ALTA = REV_CAMBIOS.replace("GRAVEDAD: MEDIA", "GRAVEDAD: ALTA")
MODO_OK = {"modo_pedido": "ampliado", "modo_antes": "chatgpt: Pensar ACTIVO", "modo_tras_enviar": "chatgpt: Pensar ACTIVO",
           "metodo": "dom"}


class Web:
    """ChatGPT/Gemini web de pega: respuestas por turnos, conversacion con URL, continuar(url)."""
    contador = 0

    def __init__(self, nombre, *respuestas, falla_url=None, error="RespuestaNoVerificada: la conversacion no carga"):
        self.nombre, self.respuestas, self.llamadas = nombre, list(respuestas), []
        self.url, self.falla_url, self.modo_preferido, self.error = None, falla_url, True, error

    def disponible(self):
        return True

    def enviar(self, prompt, buscar=False, _url=None):
        self.llamadas.append({"prompt": prompt, "url": _url})
        if _url and _url == self.falla_url:
            return Resultado("ERROR", detalle=self.error)
        if _url:
            self.url = _url
        else:
            Web.contador += 1
            self.url = f"https://{self.nombre}.test/c/{Web.contador}"
        texto = self.respuestas.pop(0) if self.respuestas else ""
        meta = dict(MODO_OK, url=self.url)
        return Resultado("OK", texto=texto, meta=meta) if texto else Resultado("ERROR", detalle="vacio", meta=meta)

    def continuar(self, prompt, url=None):
        return self.enviar(prompt, _url=url or self.url)


class Api(Web):
    def enviar(self, prompt, buscar=False, _url=None):
        self.llamadas.append({"prompt": prompt, "url": None})
        texto = self.respuestas.pop(0) if self.respuestas else ""
        return Resultado("OK", texto=texto) if texto else Resultado("ERROR", detalle="vacio")


@pytest.fixture
def cola(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ALMACEN", tmp_path / "tareas.json")
    monkeypatch.setattr(T, "VISTA", tmp_path / "tareas.md")
    monkeypatch.setattr(T, "VISTA_VAULT", tmp_path / "vault" / "x.md")
    monkeypatch.setattr(T, "CANDADO", tmp_path / ".candado")
    monkeypatch.setattr(trabajo, "BORRADORES", tmp_path / "borradores")
    monkeypatch.setattr(trabajo, "_web", lambda: True)
    t = T.anadir("Investigar la libreria X", depende="ia", etiquetas=["cat:investigacion"],
                 detalle="Damian 24/09: ver T123 y herramientas.md. Evaluar X.")
    return t


def _correr(monkeypatch, autor, revisores):
    monkeypatch.setattr(trabajo, "_generadores", lambda cat: [autor])
    monkeypatch.setattr(trabajo, "_revisores", lambda nombre: [r for r in revisores
                                                              if auditor.familia(r.nombre) != auditor.familia(nombre)])
    return trabajo.ciclo(max_tareas=1)


def _auditoria():
    return json.loads(sorted(auditor.CARPETA.glob("*.json"))[-1].read_text(encoding="utf-8"))


# ------------------------------------------------------------------ pipeline
def test_camino_feliz_ok_absoluto_y_auditoria_aprobada(cola, monkeypatch):
    autor = Web("chatgpt", V0, V1 + CAMBIOS, CIERRE_OK)
    rev = Api("gemini_api", REV_CAMBIOS, REV_OK)
    [fila] = _correr(monkeypatch, autor, [rev])
    assert fila["veredicto"] == "OK_ABSOLUTO" and fila["auditoria"] == "APROBADA", fila
    # misma conversacion: la mejora va a la URL de la primera respuesta
    assert autor.llamadas[1]["url"] == autor.llamadas[2]["url"] == "https://chatgpt.test/c/%d" % Web.contador
    assert "NO escribas CIERRE" in autor.llamadas[1]["prompt"]          # el resultado va sin OK
    assert "de forma critica" in autor.llamadas[2]["prompt"]            # el OK se pide en el mensaje siguiente
    # revisiones resumidas y filtradas: ni tutorial ni comparativa llegan al autor
    mejora = autor.llamadas[1]["prompt"]
    assert "Hello World" not in mejora and "LangChain" not in mejora and "licencia GPL" in mejora
    a = _auditoria()
    assert a["resultado"] == "APROBADA" and len(a["expediente"]["descartes"]) == 2
    t = T.buscar(cola["id"])
    assert T.conversacion(t["id"], "chatgpt:autor")["url"] == autor.url
    assert "ok_absoluto" in t["etiquetas"] and trabajo.HECHO in t["etiquetas"]
    borrador = (trabajo.BORRADORES / fila["archivo"].rsplit("/", 1)[-1]).read_text(encoding="utf-8")
    assert "## Version final" in borrador and "COMPROBADO" in borrador and "CIERRE" not in borrador.split("## Version final")[1].split("##")[0]


def test_el_prompt_no_lleva_relleno_interno(cola, monkeypatch):
    autor = Web("chatgpt", V0, V1 + CIERRE_OK)
    _correr(monkeypatch, autor, [Api("gemini_api", REV_OK, REV_OK)])
    p = autor.llamadas[0]["prompt"]
    assert "T123" not in p and "herramientas.md" not in p and "Damian" not in p and "Evaluar X" in p
    assert "ENTENDIMIENTO" in p and "BLOQUEO" in p


def test_sin_revisor_independiente_queda_bloqueada_con_aviso(cola, monkeypatch):
    autor = Web("gemini", V0)
    [fila] = _correr(monkeypatch, autor, [Api("gemini_api", REV_OK)])   # misma familia: no vale
    assert fila["veredicto"] == "PENDIENTE_REVISION" and fila["auditoria"] == "BLOQUEADA"
    assert "d_revision" in fila["fallos_auditoria"]
    assert "auditoria:bloqueada" in T.buscar(cola["id"])["etiquetas"]
    [aviso] = avisos.recientes()
    assert aviso["tipo"] == "auditoria" and "BLOQUEADA" in aviso["titulo"]


def test_ok_absoluto_sin_justificar_no_cierra_y_para_en_el_tope(cola, monkeypatch):
    autor = Web("chatgpt", V0, *[V1 + CIERRE_SIN_JUSTIFICAR] * 5)
    rev = Api("groq", *[REV_OK] * 6)
    [fila] = _correr(monkeypatch, autor, [rev])
    assert fila["veredicto"] == "TOPE_SIN_OK" and fila["auditoria"] == "BLOQUEADA"
    assert len(autor.llamadas) == 1 + auditor.TOPE_MEJORAS          # nunca da vueltas infinitas
    assert "e_ok_absoluto" in fila["fallos_auditoria"]


def test_revisor_aprueba_y_autor_justifica_sin_repetir_el_trabajo(cola, monkeypatch):
    autor = Web("chatgpt", V0, CIERRE_OK)
    [fila] = _correr(monkeypatch, autor, [Api("gemini_api", REV_OK)])
    assert fila["veredicto"] == "OK_ABSOLUTO" and fila["auditoria"] == "APROBADA"
    assert "da por buena" in autor.llamadas[1]["prompt"]


def test_fallos_graves_tras_mejorar_escalan(cola, monkeypatch):
    autor = Web("chatgpt", V0, V1 + CIERRE_OK)
    [fila] = _correr(monkeypatch, autor, [Api("gemini_api", REV_CAMBIOS, REV_ALTA)])
    assert fila["veredicto"] == "ESCALAR" and fila["auditoria"] == "BLOQUEADA"


def test_bloqueo_pide_decision_de_damian(cola, monkeypatch):
    autor = Web("chatgpt", "BLOQUEO: ¿X es la libreria de Python o la de Rust?")
    [fila] = _correr(monkeypatch, autor, [Api("gemini_api", REV_OK)])
    assert fila["veredicto"] == "USER_DECISION_REQUIRED" and fila["auditoria"] == "ESPERA_DECISION"
    assert "user_decision_required" in T.buscar(cola["id"])["etiquetas"]
    assert avisos.recientes()[0]["titulo"].endswith("decisión tuya")


# ------------------------------------------------------------------ conversacion por tarea
def test_retoma_la_conversacion_guardada_del_mismo_tema(cola, monkeypatch):
    tema = trabajo._tema(cola, "investigacion")
    T.fijar_conversacion(cola["id"], "chatgpt:autor", url="https://chatgpt.test/c/vieja", tema=tema, estado="ok")
    autor = Web("chatgpt", V0, CIERRE_OK)
    [fila] = _correr(monkeypatch, autor, [Api("gemini_api", REV_OK, REV_OK)])
    assert [ll["url"] for ll in autor.llamadas] == ["https://chatgpt.test/c/vieja"] * 2
    assert fila["auditoria"] == "APROBADA"


def test_tema_distinto_abre_conversacion_nueva(cola, monkeypatch):
    T.fijar_conversacion(cola["id"], "chatgpt:autor", url="https://chatgpt.test/c/vieja", tema="otro", estado="ok")
    autor = Web("chatgpt", V0, CIERRE_OK)
    _correr(monkeypatch, autor, [Api("gemini_api", REV_OK)])
    assert autor.llamadas[0]["url"] is None
    assert T.conversacion(cola["id"], "chatgpt:autor")["url"] != "https://chatgpt.test/c/vieja"


def test_conversacion_estropeada_se_sustituye_y_queda_anotada(cola, monkeypatch):
    tema = trabajo._tema(cola, "investigacion")
    T.fijar_conversacion(cola["id"], "chatgpt:autor", url="https://chatgpt.test/c/rota", tema=tema, estado="ok")
    autor = Web("chatgpt", V0, CIERRE_OK, falla_url="https://chatgpt.test/c/rota")
    [fila] = _correr(monkeypatch, autor, [Api("gemini_api", REV_OK)])
    assert fila["auditoria"] == "APROBADA", _auditoria()["puntos"]
    conv = _auditoria()["expediente"]["conversacion"]["chatgpt:autor"]
    assert conv["estropeadas"][0]["url"] == "https://chatgpt.test/c/rota"
    assert T.conversacion(cola["id"], "chatgpt:autor")["url"] != "https://chatgpt.test/c/rota"


def test_dos_conversaciones_sin_motivo_fallan_el_punto_b():
    exp = {"autor": "chatgpt", "conversacion_autor": "chatgpt:autor",
           "conversacion": {"chatgpt:autor": {"estropeadas": [], "url_guardada": "u2"}},
           "llamadas": [{"rol": "autor", "proveedor": "chatgpt", "ok": True, "url": "u1", "meta": MODO_OK},
                        {"rol": "mejora", "proveedor": "chatgpt", "ok": True, "url": "u2", "meta": MODO_OK}]}
    assert not auditor.auditar(exp)["puntos"]["b_conversacion"]["ok"]


# ------------------------------------------------------------------ checklist suelto
def test_modo_sin_comprobar_falla_el_punto_a():
    exp = {"autor": "chatgpt", "llamadas": [{"rol": "autor", "proveedor": "chatgpt", "ok": True, "url": "u",
                                             "meta": {"modo_pedido": "ampliado", "modo_tras_enviar": "chatgpt: Pensar apagado"}}]}
    assert not auditor.auditar(exp)["puntos"]["a_modo"]["ok"]


def test_autor_degradado_a_api_por_fallo_de_modo_falla_el_punto_a():
    exp = {"autor": "gemini_api", "web_disponible": True,
           "llamadas": [{"rol": "autor", "proveedor": "chatgpt", "ok": False, "detalle": "ModoNoActivo: Pensar apagado"},
                        {"rol": "autor", "proveedor": "gemini_api", "ok": True}]}
    assert not auditor.auditar(exp)["puntos"]["a_modo"]["ok"]


def test_basura_de_la_interfaz_se_detecta():
    sucio = "Mostrar más\nChatGPT dijo:\nInforme\nGitHub\n+1\nfin"
    assert set(auditor.basura_interfaz(sucio)) >= {"boton de la web", "etiqueta de turno de la web",
                                                   "contador de cita ('+1')"}
    assert auditor.basura_interfaz("Un informe normal con C++ 17 y +1 votos.") == []


def test_prompt_con_datos_privados_no_se_envia(cola, monkeypatch):
    T.actualizar(cola["id"], detalle="escribe a persona@ejemplo.com con el resultado")
    autor = Web("chatgpt", V0)
    [fila] = _correr(monkeypatch, autor, [])
    assert autor.llamadas == [] and "no enviado" in fila["intentos"][0]["error"]


def test_las_rutas_del_pc_se_limpian_antes_de_enviar():
    assert "secretos.toml" not in trabajo._limpiar_interno("la clave esta en C:\\Users\\damia\\secretos.toml")


def test_resumen_de_revisiones_acotado_y_sin_repetidos():
    revs = [{"revisor": "a", "texto": REV_CAMBIOS}, {"revisor": "b", "texto": REV_CAMBIOS.replace("coste", "coste ")}]
    resumen, descartes = auditor.resumir_revisiones(revs)
    assert resumen.count("falta el coste") == 1 and "Hello World" not in resumen
    assert {d["motivo"] for d in descartes} == {"tutorial o guia de instalacion", "comparativa o benchmark no pedido"}
    largo = [{"revisor": "c", "texto": "OMISIONES:\n" + "\n".join(f"- punto {i} " + "x" * 400 for i in range(20))}]
    r, _ = auditor.resumir_revisiones(largo)
    assert len(r) <= auditor.LIMITE_RESUMEN and r.count("\n- ") <= auditor.MAX_ITEMS_SECCION


def test_en_fallos_no_se_filtra_el_alcance():
    rev = [{"revisor": "a", "texto": "FALLOS:\n- \"una comparativa con LangChain\" no es cierta\nOMISIONES:\n- ninguno\n"
                                     "MEJORAS:\n- ninguno\nAÑADIR:\n- ninguno\nGRAVEDAD: ALTA"}]
    resumen, descartes = auditor.resumir_revisiones(rev)
    assert "LangChain" in resumen and not descartes


@pytest.mark.parametrize("bloque,ok", [
    (CIERRE_OK, True),
    (CIERRE_SIN_JUSTIFICAR, False),
    ("### AUTOAUDITORIA\nCIERRE: PENDIENTE\nQUEDA:\n- falta el coste", False),
    ("CIERRE: OK ABSOLUTO\nCOMPROBADO:\n- si\n- ok\n- vale", False),     # puntos vacios no justifican
])
def test_leer_cierre(bloque, ok):
    assert auditor.leer_cierre(bloque)["ok"] is ok


def test_partir_cierre_separa_version_y_autoauditoria():
    version, bloque = auditor.partir_cierre(V1 + CIERRE_OK)
    assert version == V1.strip() and bloque.startswith("### AUTOAUDITORIA")
    assert auditor.partir_cierre("solo texto") == ("solo texto", "")


# ------------------------------------------------------------------ avisos
def test_aviso_cuando_ningun_proveedor_consigue_el_modo():
    assert avisos.modo_fallido("chatgpt", "Pensar apagado", ahora=1000) is None
    f = avisos.modo_fallido("gemini", "sin Pro", ahora=1100)
    assert f is not None and json.loads(f.read_text(encoding="utf-8"))["tipo"] == "modo"
    assert avisos.modo_fallido("gemini", "sin Pro", ahora=1200) is None        # anti-repeticion


def test_un_exito_con_modo_borra_el_fallo_pendiente():
    avisos.modo_fallido("chatgpt", "x", ahora=1000)
    avisos.modo_ok("chatgpt")
    assert avisos.modo_fallido("gemini", "y", ahora=1100) is None


def test_fallos_de_modo_separados_en_el_tiempo_no_avisan():
    avisos.modo_fallido("chatgpt", "x", ahora=1000)
    assert avisos.modo_fallido("gemini", "y", ahora=1000 + avisos.VENTANA_MODO + 1) is None


def test_el_proveedor_web_avisa_del_modo(monkeypatch):
    import proveedores
    from extremidades import navegador
    monkeypatch.setattr(navegador, "activo", lambda: True)

    def falla(*a, **k):
        raise navegador.ModoNoActivo("no se confirma el modo")
    monkeypatch.setattr(navegador, "preguntar", falla)
    assert proveedores.ChatGPTProvider().enviar("hola").estado == "ERROR"
    assert proveedores.GeminiProvider().enviar("hola").estado == "ERROR"
    assert [a["tipo"] for a in avisos.recientes()] == ["modo"]


def test_la_version_mejorada_sin_entendimiento_y_con_sus_fuentes(cola, monkeypatch):
    # Prueba real 27/09 (T167): el autor repitio 'ENTENDIMIENTO... INFORME' y las fuentes quedaron tras el cierre.
    from extremidades.navegador import CABECERA_FUENTES
    mejora = ("ENTENDIMIENTO: lo mismo.\n\nINFORME\n\n" + V1 + CAMBIOS
              + "\n" + CABECERA_FUENTES + "\n- https://github.com/x/y")
    autor = Web("chatgpt", V0, mejora, CIERRE_OK)
    _correr(monkeypatch, autor, [Api("gemini_api", REV_CAMBIOS, REV_OK)])
    a = _auditoria()
    assert a["resultado"] == "APROBADA"
    borrador = next(trabajo.BORRADORES.glob("*.md")).read_text(encoding="utf-8")
    final = borrador.split("## Version final")[1].split("\n## ")[0]
    assert "ENTENDIMIENTO" not in final and final.strip().startswith("1) Que es")
    assert CABECERA_FUENTES in final and "https://github.com/x/y" in final
    cierre = borrador.split("## Autoauditoria y cierre del autor")[1].split("\n## ")[0]
    assert CABECERA_FUENTES not in cierre and "COMPROBADO" in cierre
    assert a["puntos"]["b_conversacion"]["detalle"].startswith("una conversacion (nueva)")


def test_un_titulo_informe_sin_entendimiento_no_se_corta():
    texto = "Resumen previo importante.\n### INFORME\n1) Que es"
    assert trabajo._partir_entendimiento(texto) == ("", texto)



def test_revisor_que_pierde_el_modo_al_retomar_se_anota_y_abre_otra(cola, monkeypatch):
    # Prueba real 27/09 (segunda pasada de T167): Gemini volvio a Flash al reabrir su conversacion guardada.
    tema = trabajo._tema(cola, "investigacion")
    vieja = "https://gemini.test/c/vieja"
    T.fijar_conversacion(cola["id"], "gemini:revisor", url=vieja, tema=tema, estado="ok")
    autor = Web("chatgpt", V0, CIERRE_OK)
    gemini = Web("gemini", REV_OK, falla_url=vieja, error="ModoNoActivo: tras enviar la pantalla no confirma el modo")
    [fila] = _correr(monkeypatch, autor, [gemini])
    a = _auditoria()
    assert fila["auditoria"] == "APROBADA", a["puntos"]
    assert a["expediente"]["conversacion"]["gemini:revisor"]["estropeadas"][0]["url"] == vieja
    assert T.conversacion(cola["id"], "gemini:revisor")["url"] != vieja



def test_navegador_cerrado_no_estropea_la_conversacion(cola, monkeypatch):
    # Prueba real 27/09 (tercera pasada de T167): el Chrome se cerro a mitad de envio.
    tema = trabajo._tema(cola, "investigacion")
    url = "https://chatgpt.test/c/buena"
    T.fijar_conversacion(cola["id"], "chatgpt:autor", url=url, tema=tema, estado="ok")
    autor = Web("chatgpt", falla_url=url, error="Page.wait_for_timeout: Target page, context or browser has been closed")
    respaldo = Api("groq", V0)
    monkeypatch.setattr(trabajo, "_generadores", lambda cat: [autor, respaldo])
    monkeypatch.setattr(trabajo, "_revisores", lambda nombre: [])
    [fila] = trabajo.ciclo(max_tareas=1)
    assert fila["autor"] == "groq" and fila["auditoria"] == "BLOQUEADA"
    conv = T.conversacion(cola["id"], "chatgpt:autor")
    assert conv["url"] == url and conv["estado"] == "ok"      # se retomara cuando vuelva el navegador


# ------------------------------------------------------------------ OK en DOS mensajes (Damian 27/09)
def test_ok_en_el_mismo_mensaje_que_el_resultado_no_vale(cola, monkeypatch):
    # Error visto por Damian: la IA entrega el resultado y dice OK ABSOLUTO en el MISMO mensaje.
    autor = Web("chatgpt", V0, V1 + CIERRE_OK, CIERRE_OK)
    [fila] = _correr(monkeypatch, autor, [Api("gemini_api", REV_CAMBIOS, REV_OK)])
    a = _auditoria()
    assert fila["veredicto"] == "OK_ABSOLUTO" and a["resultado"] == "APROBADA", a["puntos"]
    assert len(autor.llamadas) == 3                                   # hizo falta el mensaje N+1
    exp = a["expediente"]
    assert exp["ok_mismo_mensaje"] == 1
    assert exp["ok_mensaje"]["llamada"] > exp["entregas"][-1]["llamada"]
    assert "posterior al resultado" in a["puntos"]["e_ok_absoluto"]["detalle"]


def test_siempre_ok_junto_al_resultado_no_cierra_nunca(cola, monkeypatch):
    autor = Web("chatgpt", V0, *[V1 + CIERRE_OK] * 5)
    [fila] = _correr(monkeypatch, autor, [Api("gemini_api", REV_CAMBIOS, *[REV_OK] * 5)])
    assert fila["veredicto"] == "TOPE_SIN_OK" and fila["auditoria"] == "BLOQUEADA"
    assert len(autor.llamadas) == 1 + auditor.TOPE_MEJORAS
    assert "junto al resultado" in _auditoria()["puntos"]["e_ok_absoluto"]["detalle"]


def _exp_ok(respuesta_ok, final=V1, llamada_ok=3):
    """Expediente minimo que dice OK_ABSOLUTO; lo que cambia es la evidencia del mensaje del OK."""
    ll = [{"rol": "autor", "proveedor": "groq", "ok": True, "respuesta": V0},
          {"rol": "mejora", "proveedor": "groq", "ok": True, "respuesta": V1 + CAMBIOS},
          {"rol": "revisor", "proveedor": "gemini_api", "ok": True, "respuesta": REV_OK},
          {"rol": "mejora", "proveedor": "groq", "ok": True, "respuesta": respuesta_ok}]
    return {"autor": "groq", "estado": "OK_ABSOLUTO", "cat": "resumen", "mejoras": 2, "final": final,
            "cierre": auditor.leer_cierre(auditor.partir_cierre(respuesta_ok)[1]), "llamadas": ll,
            "rondas": [[{"revisor": "gemini_api", "veredicto": "APROBADO"}]],
            "entregas": [{"llamada": 0, "huella": auditor.huella(V0)}, {"llamada": 1, "huella": auditor.huella(V1)}],
            "ok_mensaje": {"llamada": llamada_ok, "huella": auditor.huella(V1)}}


def test_auditor_acepta_el_ok_en_mensaje_posterior_y_sin_cambios():
    assert auditor.auditar(_exp_ok(CIERRE_OK))["puntos"]["e_ok_absoluto"]["ok"]


@pytest.mark.parametrize("exp,motivo", [
    (_exp_ok(V1 + CIERRE_OK), "mismo mensaje"),                        # el mensaje del OK trae resultado
    (_exp_ok(CIERRE_OK, llamada_ok=1), "no es posterior"),             # el OK apunta al mensaje del resultado
    (_exp_ok(CIERRE_OK, final=V1 + " retocado"), "cambio despues"),    # el resultado cambio tras el OK
    (dict(_exp_ok(CIERRE_OK), ok_mensaje=None), "ningun OK"),
])
def test_auditor_rechaza_el_ok_mal_colocado(exp, motivo):
    if motivo == "no es posterior":
        exp["llamadas"][1]["respuesta"] = CIERRE_OK
    e = auditor.auditar(exp)["puntos"]["e_ok_absoluto"]
    assert not e["ok"] and motivo in e["detalle"], e


# ------------------------------------------------------------------ FONDO / MENORES y tope 5 (Damian 28/09)
V0_RETOCADA = V0.split("### INFORME\n", 1)[1].replace("X es una libreria. ", "X es una biblioteca. ", 1)
SOLO_MENORES = ("\n### AUTOAUDITORIA\nFONDO:\n- ninguno\nMENORES:\n- 'libreria' por 'biblioteca' en la primera "
                "frase\nCIERRE: PENDIENTE\n")
CON_FONDO = ("\n### AUTOAUDITORIA\nFONDO:\n- la URL oficial no estaba confirmada\nMENORES:\n- ninguno\n"
             "CIERRE: PENDIENTE\n")
REV_OK_MEDIA = REV_OK.replace("GRAVEDAD: BAJA", "GRAVEDAD: MEDIA")


def test_el_tope_es_de_5_pasadas():
    assert auditor.TOPE_MEJORAS == 5


def test_solo_retoques_menores_se_aplican_y_el_ok_llega_en_el_mensaje_siguiente(cola, monkeypatch):
    autor = Web("chatgpt", V0, V0_RETOCADA + SOLO_MENORES, CIERRE_OK)
    rev = Api("gemini_api", REV_OK, REV_OK)
    [fila] = _correr(monkeypatch, autor, [rev])
    a = _auditoria()
    assert fila["veredicto"] == "OK_ABSOLUTO" and a["resultado"] == "APROBADA", a["puntos"]
    assert len(rev.llamadas) == 1                                   # sin otra ronda de revisores
    assert "FONDO" in autor.llamadas[1]["prompt"] and "MENORES" in autor.llamadas[1]["prompt"]
    assert "retoques menores" in autor.llamadas[2]["prompt"]        # se pide confirmar, aparte del resultado
    exp = a["expediente"]
    assert exp["menores"][0]["parecido"] >= auditor.PARECIDO_MENORES
    assert exp["ok_mensaje"]["llamada"] > exp["entregas"][-1]["llamada"]
    assert "retoque(s) menor(es)" in a["puntos"]["e_ok_absoluto"]["detalle"]
    assert "biblioteca" in next(trabajo.BORRADORES.glob("*.md")).read_text(encoding="utf-8").split("## Version final")[1]


def test_un_fallo_de_fondo_vuelve_a_los_revisores(cola, monkeypatch):
    autor = Web("chatgpt", V0, V0_RETOCADA + CON_FONDO, CIERRE_OK)
    rev = Api("gemini_api", REV_OK, REV_OK)
    [fila] = _correr(monkeypatch, autor, [rev])
    assert fila["veredicto"] == "OK_ABSOLUTO" and len(rev.llamadas) == 2
    assert "menores" not in _auditoria()["expediente"]


def test_menores_sin_todo_en_baja_vuelve_a_los_revisores(cola, monkeypatch):
    autor = Web("chatgpt", V0, V0_RETOCADA + SOLO_MENORES, CIERRE_OK)
    rev = Api("gemini_api", REV_OK_MEDIA, REV_OK)       # APROBADO pero con gravedad MEDIA
    _correr(monkeypatch, autor, [rev])
    assert len(rev.llamadas) == 2


def test_menores_de_etiqueta_pero_cambio_grande_vuelve_a_los_revisores(cola, monkeypatch):
    autor = Web("chatgpt", V0, V1 + SOLO_MENORES, CIERRE_OK)        # reescritura entera, dice 'menores'
    rev = Api("gemini_api", REV_OK, REV_OK)
    [fila] = _correr(monkeypatch, autor, [rev])
    assert len(rev.llamadas) == 2 and fila["auditoria"] == "APROBADA"


def test_ok_con_fallos_de_fondo_declarados_no_es_ok():
    bloque = CIERRE_OK.replace("CIERRE: OK ABSOLUTO", "FONDO:\n- la fecha de la version es dudosa\nCIERRE: OK ABSOLUTO")
    c = auditor.leer_cierre(bloque)
    assert not c["ok"] and c["fondo"] == ["la fecha de la version es dudosa"]
    assert auditor.leer_cierre(CIERRE_OK.replace("CIERRE:", "FONDO:\n- ninguno\nCIERRE:"))["ok"]


def test_auditor_rechaza_un_cambio_sin_revisar_que_no_es_menor():
    exp = _exp_ok(CIERRE_OK, final=V0_RETOCADA)
    exp["entregas"].append({"llamada": 3, "huella": auditor.huella(V0_RETOCADA)})
    exp["llamadas"].insert(3, {"rol": "mejora", "proveedor": "groq", "ok": True, "respuesta": V0_RETOCADA + CON_FONDO})
    exp["ok_mensaje"] = {"llamada": 4, "huella": auditor.huella(V0_RETOCADA)}
    e = auditor.auditar(exp)["puntos"]["e_ok_absoluto"]
    assert not e["ok"] and "sin ser retoque menor" in e["detalle"], e
    exp["menores"] = [{"llamada": 3, "parecido": 0.97, "menores": ["x"]}]
    assert auditor.auditar(exp)["puntos"]["e_ok_absoluto"]["ok"]


# ------------------------------------------------------------------ T667: modelo exacto del autor en el borrador
class ApiModelos(Web):
    """API de pega que, como Groq o NVIDIA, deja en ultimo_modelo el modelo que respondio."""

    def __init__(self, nombre, modelos, *respuestas):
        super().__init__(nombre, *respuestas)
        self.modelos, self.ultimo_modelo = list(modelos), ""

    def enviar(self, prompt, buscar=False, _url=None):
        self.ultimo_modelo = self.modelos.pop(0) if len(self.modelos) > 1 else self.modelos[0]
        return super().enviar(prompt, buscar, _url)


def _cabecera():
    return next(trabajo.BORRADORES.glob("*.md")).read_text(encoding="utf-8").splitlines()[0]


def test_t667_el_borrador_guarda_cada_modelo_exacto_del_autor(cola, monkeypatch):
    autor = ApiModelos("groq", ["openai/gpt-oss-120b", "qwen/qwen3-32b"], V0, V1 + CAMBIOS, CIERRE_OK)
    _correr(monkeypatch, autor, [Web("gemini", REV_CAMBIOS, REV_OK)])
    assert "| autor groq | modelo openai/gpt-oss-120b,qwen/qwen3-32b |" in _cabecera()


def test_t667_autor_web_guarda_su_sitio_como_modelo(cola, monkeypatch):
    _correr(monkeypatch, Web("chatgpt", V0, V1 + CAMBIOS, CIERRE_OK), [Api("gemini_api", REV_CAMBIOS, REV_OK)])
    assert "| autor chatgpt | modelo chatgpt |" in _cabecera()
