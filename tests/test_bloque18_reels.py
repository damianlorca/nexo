# -*- coding: utf-8 -*-
"""Bloque 18 (24/10): reels mas rapido sin pagar (prioridad por coleccion, respaldos gratuitos) y cada ficha a su sitio
(nucleo/reels_destino.py). Todo con dobles: sin red, sin modelos, sin tocar memoria/ ni el catalogo reales."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from extremidades import reels
from nucleo import reels_destino as D


# ------------------------------------------------------------------ pieza 1: cola y proveedores
def test_cola_del_lote_va_por_coleccion_ai_y_cursos_vende_resto_china(tmp_path, monkeypatch):
    monkeypatch.setattr(reels, "CARPETA", tmp_path / "reels")
    (tmp_path / "reels").mkdir()
    col = tmp_path / "col.json"
    filas = [("C1", ["China comunista"]), ("V1", ["vende"]), ("S1", []), ("A1", ["ai"]), ("K1", ["cursos"]),
             ("C2", ["China comunista", "ai"]), ("A2", ["ai"]), ("H1", ["hacking"])]
    col.write_text(json.dumps({"reels": [{"codigo": c, "url": c, "colecciones": cs} for c, cs in filas]}),
                   encoding="utf-8")
    # C2 tambien es "ai": cuenta su mejor coleccion. Dentro de cada prioridad, el orden de la coleccion.
    assert reels.cola_lote(col) == ["A1", "K1", "C2", "A2", "V1", "S1", "H1", "C1"]


def test_los_respaldos_gratuitos_son_nvidia_groq_y_openrouter_con_ultra_delante():
    import proveedores as P
    libres = reels.proveedores_libres()
    assert [p.nombre for p in libres] == ["nvidia", "groq", "openrouter"]
    assert set(libres[0].prov.modelos) <= set(P.MODELOS_NVIDIA_GRATIS)     # nunca uno fuera de la lista blanca
    assert reels.PREFERIDOS_LIBRES[0] == "nvidia/nemotron-3-ultra-550b-a55b"
    assert "thinkingmachines/inkling:free" not in P.MODELOS_OPENROUTER_FREE   # solo dentro de herramientas de codigo
    assert P.MODELO_NVIDIA_VISION in P.MODELOS_NVIDIA_GRATIS


def test_openrouter_nunca_llama_a_un_modelo_de_pago(monkeypatch):
    llamados = []

    def cascada(nombre, modelos, rondas, espera, pedir, leer):
        llamados.extend(modelos)
        return SimpleNamespace(ok=False, meta={})
    import nucleo.fallos as fallos
    monkeypatch.setattr(fallos, "cascada", cascada)
    prov = SimpleNamespace(nombre="openrouter", rondas=1, espera=0, timeout=5, _clave=lambda: "K",
                           _vivos=lambda: ("caro/modelo", "bueno/modelo:free"), disponible=lambda: True)
    reels.ProveedorLibre(prov, "http://u").enviar("hola")
    assert llamados == ["bueno/modelo:free"]


# ------------------------------------------------------------------ pieza 2: reglas y limpieza
def _e(tipo="herramienta", nombre="Herramienta X", **kw):
    base = {"tipo": tipo, "nombre": nombre, "dueno": None, "url": None, "que_es": f"que es {nombre}",
            "para_que": f"para {nombre}", "categorias": ["herramientas"], "origen": "modelo",
            "resolucion": {"existe": None}}
    base.update(kw)
    return base


def test_lo_publico_no_lleva_redes_ni_cuentas_ni_codigos():
    t = D.publico("Mira https://www.instagram.com/reel/AbC123xyz/ de @creador_ia | gratis AbC123xyz reel",
                  {"AbC123xyz"})
    assert "instagram" not in t and "@" not in t and "AbC123xyz" not in t and "|" not in t
    assert "reel" not in t.lower()


def test_el_enlace_sale_de_la_resolucion_nunca_de_una_red():
    assert D.enlace(_e("repo", "x", resolucion={"existe": True, "canonico": "dueno/x"})) == "https://github.com/dueno/x"
    assert D.enlace(_e("web", "y", url="https://www.instagram.com/p/1", resolucion={})) == ""
    assert D.enlace(_e("web", "z", url="https://z.dev", resolucion={"existe": True, "url": "https://z.dev"})) == \
        "https://z.dev"
    assert D.enlace(_e("repo", "w", resolucion={"existe": False, "canonico": "a/w"})) == ""


def test_reglas_sin_ia(monkeypatch):
    peligro = _e(seguridad={"nivel": "peligro", "motivo": "salta permisos"})
    assert D.regla(peligro, [], [], "")["destino"] == "descartado"
    falso = _e("repo", "falso", dueno="nadie", origen="citas", resolucion={"existe": False})
    assert D.regla(falso, [], [], "")["motivo"] == "citado pero no existe en GitHub"
    # ya en el catalogo escrito a mano
    assert D.regla(_e(nombre="Graft"), [], [], "| Buscar código | Graft (MCP) |")["destino"] == "ya_existe"
    # ya en una tarea viva (indice de reels_tareas)
    from nucleo import reels_tareas as RT
    idx = RT.indice([], [{"id": "T42", "titulo": "Investigar Herramienta Xyzzy para NEXO", "estado": "pendiente"}])
    r = D.regla(_e(nombre="Herramienta Xyzzy"), idx, [], "")
    assert r["destino"] == "ya_existe" and r["ref"] == "T42"
    # una tecnica no la decide la regla
    assert D.regla(_e("tecnica", "Prompt de auditoria"), [], [], "") is None


# ------------------------------------------------------------------ pieza 2: clasificar con el modelo (doble)
def _ficha(codigo="R1", colecciones=("ai",), elementos=None, tema="Herramientas de IA"):
    return {"codigo": codigo, "colecciones": list(colecciones), "tema": tema, "resumen": "resumen",
            "elementos": elementos if elementos is not None else
            [_e("repo", "toolkit", dueno="ana", resolucion={"existe": True, "canonico": "ana/toolkit"}),
             _e("tecnica", "Prompt en tres pasos"), _e("dato", "Dato de relleno"),
             _e("idea_negocio", "Vender webs a bares")]}


def _pedir(respuesta, vistos=None):
    def pedir(cuerpo):
        if vistos is not None:
            vistos.append(cuerpo["contents"][0]["parts"][0]["text"])
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta, "groq:openai/gpt-oss-120b"
    return pedir


def test_clasificar_valida_lo_del_modelo_y_rellena_lo_que_falta():
    resp = {"elementos": [
        {"i": 0, "destino": "catalogo", "para_que": "kit de agentes", "coste": "GRATIS?", "quiero": "Quiero agentes"},
        {"i": 1, "destino": "guia", "tema": "prompts", "consejo": "pide primero el plan"},
        {"i": 2, "destino": "inventado"},
    ]}
    vistos = []
    dec = D.clasificar(_ficha(), [], [], "", pedir=_pedir(resp, vistos))
    assert dec[0]["destino"] == "catalogo" and dec[0]["coste"] == "desconocido"
    assert dec[1] == {"destino": "guia", "motivo": "", "tema": "prompts", "consejo": "pide primero el plan",
                      "por": "modelo:groq:openai/gpt-oss-120b"}
    assert dec[2]["destino"] == "descartado" and dec[2]["por"] == "respaldo"      # destino invalido -> respaldo
    assert dec[3]["destino"] == "monetizacion" and dec[3]["por"] == "respaldo"    # el modelo se lo dejo
    assert "NO confiable" in vistos[0] and "toolkit" in vistos[0]


def test_viajes_solo_si_la_ficha_va_de_china():
    resp = {"elementos": [{"i": 0, "destino": "viajes", "ciudad": "Pekin", "tipo": "comida", "nota": "x"}]}
    f = _ficha(elementos=[_e("tecnica", "algo")])
    assert D.clasificar(f, [], [], "", pedir=_pedir(resp))[0]["destino"] == "guia"          # respaldo
    china = _ficha(colecciones=["China comunista"], elementos=[_e("dato", "Pato laqueado en Siji Minfu")])
    d = D.clasificar(china, [], [], "", pedir=_pedir(resp))[0]
    assert (d["destino"], d["ciudad"], d["tipo"]) == ("viajes", "Pekín", "comida")


def test_sin_modelo_la_ficha_no_se_clasifica_a_ciegas():
    assert D.clasificar(_ficha(), [], [], "", pedir=_pedir(RuntimeError("sin cuota"))) is None


# ------------------------------------------------------------------ pieza 2: tanda completa en tmp
@pytest.fixture
def entorno(tmp_path, monkeypatch):
    carpeta = tmp_path / "reels"
    carpeta.mkdir()
    cat = tmp_path / "CATALOGO.md"
    cat.write_text("# Catálogo\n\n## 1. Para hacer X, usa Y\n\n| Graft | x |\n", encoding="utf-8")
    monkeypatch.setattr(D, "CARPETA", carpeta)
    monkeypatch.setattr(D, "ALMACEN", carpeta / "destinos.json")
    monkeypatch.setattr(D, "CATALOGO_MD", cat)
    monkeypatch.setattr(D, "GUIAS", tmp_path / "guias")
    monkeypatch.setattr(D, "CHINA_MD", tmp_path / "viajes" / "china.md")
    monkeypatch.setattr(D, "MONETIZACION_MD", tmp_path / "monet" / "peticiones-monetizacion.md")
    (carpeta / "reels_coleccion.json").write_text(json.dumps({"reels": [{"codigo": "CodAI0001"},
                                                                        {"codigo": "CodCH0002"}]}), encoding="utf-8")
    return SimpleNamespace(carpeta=carpeta, cat=cat, tmp=tmp_path)


def _guardar_ficha(carpeta, f):
    (carpeta / f"{f['codigo']}.ficha.json").write_text(json.dumps(f, ensure_ascii=False), encoding="utf-8")


def _pedir_por_ficha(llamadas):
    def pedir(cuerpo):
        texto = cuerpo["contents"][0]["parts"][0]["text"]
        llamadas.append(texto)
        if "Moverse por China" in texto:
            return {"elementos": [{"i": 0, "destino": "viajes", "ciudad": "Shanghái", "tipo": "transporte",
                                   "nota": "metro con Alipay"}]}, "nvidia:x"
        return {"elementos": [
            {"i": 0, "destino": "catalogo", "para_que": "kit de agentes CodAI0001 de @alguien", "coste": "gratis",
             "quiero": "Quiero montar agentes"},
            {"i": 1, "destino": "guia", "tema": "prompts", "consejo": "pide primero el plan"},
            {"i": 2, "destino": "descartado", "motivo": "relleno"},
            {"i": 3, "destino": "monetizacion", "nota": "webs para bares sin web"}]}, "nvidia:x"
    return pedir


def test_repartir_lleva_cada_cosa_a_su_sitio_y_nada_privado_a_git(entorno):
    _guardar_ficha(entorno.carpeta, _ficha("CodAI0001"))
    _guardar_ficha(entorno.carpeta, _ficha("CodCH0002", ["China comunista"], [_e("dato", "Metro de Shanghái")],
                                           tema="Moverse por China"))
    llamadas = []
    r = D.repartir(pedir=_pedir_por_ficha(llamadas), catalogo_items=[], tareas=[], reg=[], crear=False,
                   parada=lambda: False)
    assert r["hechos"] == 2 and len(llamadas) == 2
    rec = r["recuento"]["elementos"]
    assert (rec["catalogo"], rec["guia"], rec["descartado"], rec["monetizacion"], rec["viajes"]) == (1, 1, 1, 1, 1)
    cat = entorno.cat.read_text(encoding="utf-8")
    assert "## 6. Por probar" in cat and "ana/toolkit" in cat and "https://github.com/ana/toolkit" in cat
    assert "Quiero montar agentes → ana/toolkit" in cat
    assert "## 7. Guías prácticas" in cat and "guias/prompts.md" in cat
    publico = cat + (entorno.tmp / "guias" / "prompts.md").read_text(encoding="utf-8")
    for prohibido in ("CodAI0001", "CodCH0002", "@alguien", "instagram", "Vender webs", "Metro de Shanghái"):
        assert prohibido not in publico
    china = (entorno.tmp / "viajes" / "china.md").read_text(encoding="utf-8")
    assert "## Shanghái" in china and "### Transporte" in china and "metro con Alipay" in china
    assert "webs para bares" in (entorno.tmp / "monet" / "peticiones-monetizacion.md").read_text(encoding="utf-8")
    alm = D.cargar()
    assert {x["destino"] for x in alm["reels"]["CodAI0001"]["elementos"]} == {"catalogo", "guia", "descartado",
                                                                             "monetizacion"}
    # reanudable: lo repartido no se vuelve a pedir; el catalogo a mano sigue intacto
    r2 = D.repartir(pedir=_pedir_por_ficha(llamadas), catalogo_items=[], tareas=[], reg=[], crear=False,
                    parada=lambda: False)
    assert r2["hechos"] == 0 and len(llamadas) == 2
    assert "| Graft | x |" in entorno.cat.read_text(encoding="utf-8")


def test_misma_herramienta_en_dos_reels_es_una_entrada(entorno):
    _guardar_ficha(entorno.carpeta, _ficha("CodAI0001"))
    _guardar_ficha(entorno.carpeta, _ficha("CodAI0003"))
    D.repartir(pedir=_pedir_por_ficha([]), catalogo_items=[], tareas=[], reg=[], crear=False, parada=lambda: False)
    alm = D.cargar()
    assert list(alm["por_probar"]) == ["ana/toolkit"] and alm["por_probar"]["ana/toolkit"]["veces"] == 2
    assert entorno.cat.read_text(encoding="utf-8").count("| ana/toolkit |") == 1


def test_sin_modelo_no_se_marca_y_se_reintenta(entorno):
    for c in ("CodAI0001", "CodAI0003", "CodAI0004"):
        _guardar_ficha(entorno.carpeta, _ficha(c))
    r = D.repartir(pedir=_pedir(RuntimeError("nadie")), catalogo_items=[], tareas=[], reg=[], crear=False,
                   parada=lambda: False)
    assert r["hechos"] == 0 and len(r["sin_modelo"]) == 3 and "otra tanda" in r["motivo_fin"]
    assert D.cargar()["reels"] == {}


def test_la_herramienta_ya_catalogada_a_mano_no_se_duplica(entorno):
    _guardar_ficha(entorno.carpeta, _ficha("CodAI0001", elementos=[_e("herramienta", "Graft")]))
    r = D.repartir(pedir=_pedir(RuntimeError("no hace falta")), catalogo_items=[], tareas=[], reg=[], crear=False,
                   parada=lambda: False)
    assert r["hechos"] == 1 and r["recuento"]["elementos"]["ya_existe"] == 1


# ------------------------------------------------------------------ pieza 2: investigaciones con freno
class TareasFalsas:
    def __init__(self):
        self.creadas, self.notas = [], []

    def anadir(self, titulo, **campos):
        t = {"id": f"T9{len(self.creadas):02d}", "titulo": titulo, **campos}
        self.creadas.append(t)
        return t

    def anotar(self, tid, texto):
        self.notas.append((tid, texto))


def _freno(propuestas=0, parecidas=None):
    return SimpleNamespace(LIMITE_PROPUESTAS=30, estado_cola=lambda: {"propuestas": propuestas},
                           parecidas_a_existentes=lambda textos: (parecidas or [None] * len(textos))[:len(textos)])


def test_investigaciones_con_tope_freno_parecidas_y_las_grandes_a_t1006():
    alm = D._vacio()
    for i in range(7):
        alm["investigaciones"][f"k{i}"] = {"nombre": f"Cosa {i}", "pregunta": "sirve?", "enlace": "", "grande": False,
                                           "tarea": None}
    alm["investigaciones"]["gr"] = {"nombre": "Sistema Entero", "pregunta": "", "enlace": "", "grande": True,
                                    "tarea": None}
    T = TareasFalsas()
    r = D.crear_investigaciones(alm, tareas_mod=T, freno_mod=_freno(parecidas=[{"id": "T7"}, None, None, None, None]))
    assert r["t1006"] == ["Sistema Entero"] and T.notas[0][0] == "T1006"
    assert r["parecidas"] == ["T7"] and ("T7", T.notas[1][1]) == T.notas[1]
    assert len(r["creadas"]) == 4                                         # tope 5 por tanda, 1 era parecida
    t = T.creadas[0]
    assert t["tipo"] == "investigacion" and t["estado"] == "propuesta" and t["titulo"].startswith("Investigar: ")
    assert sum(1 for v in alm["investigaciones"].values() if not v["tarea"]) == 2      # esperan a otra tanda
    # con la cola de propuestas llena, no se crea nada
    T2 = TareasFalsas()
    assert D.crear_investigaciones(alm, tareas_mod=T2, freno_mod=_freno(propuestas=30))["creadas"] == []


def test_las_llamadas_de_reels_llevan_user_agent_propio(monkeypatch):
    """Sin el, Cloudflare (Groq, OpenRouter) da 403 al 'Python-urllib' y el 403 enfriaba a Groq para todo NEXO."""
    import io
    import urllib.request
    vistas = {}

    class Resp(io.BytesIO):
        status, headers = 200, {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(peticion, timeout=None):
        vistas.update({k.lower(): v for k, v in peticion.header_items()})
        return Resp(b'{"choices": []}')
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    reels._post_respuesta("https://api.groq.com/x", {"a": 1}, {"Authorization": "Bearer K"}, 5)
    assert vistas["user-agent"] == reels.USER_AGENT and "urllib" not in vistas["user-agent"].lower()
    assert vistas["authorization"] == "Bearer K"


def test_hasta_pasada_medianoche_es_manana():
    from datetime import datetime
    noche = datetime(2026, 10, 24, 23, 30)
    assert reels.leer_hasta("02:24", noche) == datetime(2026, 10, 25, 2, 24)
    assert reels.leer_hasta("23:55", noche) == datetime(2026, 10, 24, 23, 55)


def _sin_datos_privados(monkeypatch, tmp_path):
    """Bloque 21: reels.turno leia la coleccion y el estado del lote REALES (memoria/perfil_privado/reels/), que no
    existen en los worktrees del implementador: alli estos tests fallaban siempre (linea base en rojo)."""
    monkeypatch.setattr(reels, "CONFIG", tmp_path / "config.json")
    monkeypatch.setattr(reels, "LOTE", tmp_path / "lote.json")
    monkeypatch.setattr(reels, "cola_rehacer", lambda *a, **k: [])


def test_el_turno_pasa_hasta_al_lote_y_con_un_doble_no_reparte_de_verdad(monkeypatch, tmp_path):
    """Con un `correr` de prueba el reparto real (catalogo, almacen) nunca se toca; el doble de reparto si se llama."""
    from nucleo import reels_destino, reels_huecos, reels_tareas
    _sin_datos_privados(monkeypatch, tmp_path)
    monkeypatch.setattr(reels, "cola_lote", lambda *a, **k: ["R1"])
    monkeypatch.setattr(reels_tareas, "cargar_fichas", lambda c: [{"codigo": "R1", "elementos": []}])
    monkeypatch.setattr(reels_tareas, "plan", lambda f: {"tareas": []})
    monkeypatch.setattr(reels_tareas, "crear", lambda p: {"creadas": []})
    monkeypatch.setattr(reels_huecos, "registrar", lambda f: {"tarjeta": {}})
    monkeypatch.setattr(reels_destino, "repartir", lambda *a, **k: pytest.fail("reparto real desde un test"))
    ordenes = []

    def correr(args, **k):
        ordenes.append(args)
        return SimpleNamespace(stdout='{"hechos": ["R1"], "fallos": []}', returncode=0, stderr="")
    r = reels.turno(correr=correr, minutos=30)
    assert "--hasta" in ordenes[0] and "destinos" not in r
    r = reels.turno(correr=correr, minutos=30, repartir=lambda c: {"recuento": {"reels": len(c)}})
    assert r["destinos"] == {"reels": 1}


def test_el_tope_del_lote_sale_de_los_minutos_del_turno(monkeypatch, tmp_path):
    """T1037: la noche (180 min) ya no se corta a 30 con hora y media libre; la ventana de dia sigue en 30."""
    _sin_datos_privados(monkeypatch, tmp_path)
    monkeypatch.setattr(reels, "cola_lote", lambda *a, **k: ["R1"])
    ordenes = []

    def correr(args, **k):
        ordenes.append(args)
        return SimpleNamespace(stdout='{"hechos": [], "fallos": []}', returncode=0, stderr="")
    for minutos in (180, 30):
        reels.turno(correr=correr, minutos=minutos)
    reels.turno(maximo=5, correr=correr, minutos=180)
    assert [o[o.index("--max") + 1] for o in ordenes] == ["60", "30", "5"]


def test_un_solo_reparto_a_la_vez(entorno):
    from nucleo import candado
    with candado.exclusivo(D.ALMACEN.with_suffix(".lock"), espera_maxima=1):
        with pytest.raises(candado.Ocupado):
            D.repartir(pedir=_pedir(RuntimeError("x")), catalogo_items=[], tareas=[], reg=[], crear=False,
                       parada=lambda: False, espera=0.5)


def test_lo_que_nexo_ya_tiene_gana_a_un_descarte_viejo_que_lo_nombra():
    reg = [{"id": "T303", "texto": "Ollama", "motivo": "repos flojos"}]     # forma de descartes.registro
    assert D.regla(_e("herramienta", "Ollama"), [], reg, "")["destino"] == "descartado"
    r = D.regla(_e("herramienta", "Ollama"), [], reg, "| Modelos locales | Ollama (qwen) |")
    assert (r["destino"], r["ref"]) == ("ya_existe", "CATALOGO")


def test_investigacion_solo_para_lo_que_mejora_nexo_y_trading_a_su_seccion():
    """T1040: lo de trading va a su seccion aunque el modelo lo mande a investigacion, guia o descartado."""
    trading = _e("tecnica", "Arbitraje estadistico", categorias=["trading"])
    resp = {"elementos": [{"i": 0, "destino": "investigacion", "pregunta": "?"},
                          {"i": 1, "destino": "investigacion", "pregunta": "cuanto ahorra"},
                          {"i": 2, "destino": "guia", "tema": "otros", "consejo": "ordenes limitadas"},
                          {"i": 3, "destino": "descartado", "motivo": "trading: cultura general"},
                          {"i": 4, "destino": "descartado", "motivo": "duplicado de 0"}]}
    f = _ficha(elementos=[trading, _e("repo", "kit", categorias=["nexo"]),
                          _e("consejo", "Usa ordenes limitadas", categorias=["trading"]),
                          _e("web", "Datos de bolsa", categorias=["trading"]),
                          _e("tecnica", "Arbitraje estadistico bis", categorias=["trading"])])
    dec = D.clasificar(f, [], [], "", pedir=_pedir(resp))
    assert (dec[0]["destino"], dec[0]["investigar"], dec[0]["pregunta"]) == ("trading", True, "?")
    assert dec[1]["destino"] == "investigacion"
    assert (dec[2]["destino"], dec[2]["nota"], dec[2]["investigar"]) == ("trading", "ordenes limitadas", False)
    assert dec[3]["destino"] == "trading"
    assert dec[4]["destino"] == "descartado"                      # un duplicado sigue fuera
    # sin modelo para ese elemento: respaldo a trading (no a monetizacion ni a descartado)
    f2 = _ficha(elementos=[_e("idea_negocio", "Bot de copytrading", categorias=["trading"]),
                           _e("curso_oferta", "Curso de bolsa", categorias=["trading"])])
    dec2 = D.clasificar(f2, [], [], "", pedir=_pedir({"elementos": []}))
    assert [d["destino"] for d in dec2.values()] == ["trading", "monetizacion"]


def test_trading_no_vuelve_a_descartado_por_un_descarte_viejo_y_lo_de_nexo_sigue_en_el_catalogo():
    reg = [{"id": "T303", "texto": "Bot RSI", "motivo": "ajeno a NEXO"}]
    assert D.regla(_e("idea_proyecto", "Bot RSI", categorias=["trading"]), [], reg, "") is None
    assert D.regla(_e("idea_proyecto", "Bot RSI", categorias=["nexo"]), [], reg, "")["destino"] == "descartado"
    assert D.regla(_e("cuenta", "trader_x", categorias=["trading"]), [], [], "")["destino"] == "descartado"
    assert D.es_trading(_e("idea_proyecto", "Bot", categorias=["trading", "nexo"]))
    assert not D.es_trading(_e("herramienta", "Suite", categorias=["herramientas", "trading", "nexo"]))


def test_aplicar_y_pintar_la_seccion_de_trading(entorno):
    f = _ficha("CodAI0001", elementos=[
        _e("web", "Datos de bolsa", categorias=["trading"], resolucion={"existe": True, "url": "https://datos.example"}),
        _e("idea_proyecto", "Bot RSI de @alguien", categorias=["trading"]),
        _e("tecnica", "Kelly", categorias=["trading"])])
    alm = D._vacio()
    dec = {0: {"destino": "trading", "nota": "API gratis de precios CodAI0001", "investigar": False},
           1: {"destino": "trading", "nota": "compra con RSI bajo", "investigar": True, "pregunta": "¿funciona?"},
           2: {"destino": "trading", "nota": "tamano de posicion"}}
    vinculo = D.aplicar(f, dec, alm)
    assert [x["destino"] for x in vinculo] == ["trading"] * 3
    assert {v["clase"] for v in alm["trading"].values()} == {"herramienta", "bot", "estrategia"}
    inv = alm["investigaciones"]
    assert len(inv) == 1 and next(iter(inv.values()))["tema"] == "trading"
    alm["guias"]["trading"] = {"viejo": {"nombre": "Ordenes limitadas", "consejo": "fija el precio", "fuente": ""}}
    tareas = [{"id": "T1032", "titulo": "Investigar: 60 Minutes", "estado": "hecha", "etiquetas": ["tema:trading"],
               "resultado": {"decision": "DESCARTAR", "motivo": "no aporta datos nuevos"}},
              {"id": "T5", "titulo": "Otra", "estado": "pendiente", "etiquetas": []}]
    D.pintar(alm, tareas=tareas)
    md = (entorno.tmp / "guias" / "trading.md").read_text(encoding="utf-8")
    assert "### Herramientas, datos y plataformas" in md and "### Bots e ideas de bots" in md
    assert "### Estrategias y técnicas" in md and "https://datos.example" in md and "Ordenes limitadas" in md
    assert "## Investigaciones" in md and "**T1032**" in md and "RESULTADO DESCARTAR" in md and "T5" not in md
    for prohibido in ("CodAI0001", "@alguien"):
        assert prohibido not in md
    cat = entorno.cat.read_text(encoding="utf-8")
    assert "guias/trading.md): 4 entradas" in cat
    D.pintar(alm, tareas=tareas)                                   # repintar no duplica bloques
    assert (entorno.tmp / "guias" / "trading.md").read_text(encoding="utf-8").count("## Investigaciones") == 1


def test_investigaciones_de_trading_con_su_etiqueta_y_nunca_a_t1006():
    alm = D._vacio()
    alm["investigaciones"]["bot"] = {"nombre": "Bot RSI", "pregunta": "?", "enlace": "", "grande": True,
                                     "tema": "trading", "tarea": None}
    alm["investigaciones"]["kit"] = {"nombre": "Kit", "pregunta": "?", "enlace": "", "grande": False, "tarea": None}
    T = TareasFalsas()
    r = D.crear_investigaciones(alm, tareas_mod=T, freno_mod=_freno())
    assert r["t1006"] == [] and not T.notas and len(r["creadas"]) == 2
    bot, kit = T.creadas
    assert "tema:trading" in bot["etiquetas"] and "guias/trading.md" in bot["donde"] and "T1006" in bot["origen"]
    assert "tema:trading" not in kit["etiquetas"] and "CATALOGO" in kit["donde"]


class _LibreRitmo:
    """Gratuito que falla `fallos` veces (429 por minuto) y luego responde."""

    def __init__(self, fallos):
        self.nombre, self.fallos, self.llamadas = "groq", fallos, 0

    def disponible(self):
        return True

    def enviar(self, prompt):
        self.llamadas += 1
        ok = self.llamadas > self.fallos
        return SimpleNamespace(ok=ok, texto='{"ok": 1}' if ok else "", meta={"modelo": "m"})


def test_antes_de_gastar_gemini_se_espera_a_los_gratuitos(monkeypatch):
    monkeypatch.setattr(reels, "gemini_respaldo", lambda *a, **k: pytest.fail("gasto Gemini por un 429 de un minuto"))
    esperas = []
    libre = _LibreRitmo(fallos=2)
    j, modelo = reels.pedir_modelo({"contents": [{"parts": [{"text": "p"}]}]}, libres=[libre], rondas=4,
                                   dormir=esperas.append)
    assert j == {"ok": 1} and libre.llamadas == 3 and esperas == [reels.ESPERA_LIBRES] * 2


def test_si_los_gratuitos_no_vuelven_se_usa_gemini_tras_las_rondas(monkeypatch):
    monkeypatch.setattr(reels, "gemini_respaldo", lambda c, post, dormir, pres: ('{"g": 1}', "gemini"))
    esperas = []
    libre = _LibreRitmo(fallos=99)
    assert reels.pedir_modelo({"contents": [{"parts": [{"text": "p"}]}]}, libres=[libre], rondas=3,
                              dormir=esperas.append, presupuesto=False)[0] == {"g": 1}
    assert libre.llamadas == 3 and len(esperas) == 2


def test_nada_que_pida_saltarse_permisos_llega_a_una_guia_y_el_catalogo_es_solo_de_herramientas():
    # sin marca de seguridad en la ficha (fichas viejas): la regla la calcula
    assert D.regla(_e("tecnica", "Modo yolo", que_es="usar --dangerously-skip-permissions"), [], [], "")[
        "destino"] == "descartado"
    assert D.regla(_e("modelo", "Claude Opus 4.7"), [], [], "")["motivo"].startswith("obsoleto")
    resp = {"elementos": [
        {"i": 0, "destino": "guia", "tema": "agentes", "consejo": "configura skipPermissions para bucles sin pausas"},
        {"i": 1, "destino": "catalogo", "para_que": "x", "coste": "gratis", "quiero": "Quiero x"}]}
    f = _ficha(elementos=[_e("tecnica", "Bucles autonomos"), _e("dato", "El video presenta una herramienta")])
    dec = D.clasificar(f, [], [], "", pedir=_pedir(resp))
    assert dec[0]["destino"] == "descartado" and "seguridad" in dec[0]["motivo"]
    assert dec[1]["destino"] == "descartado" and dec[1]["por"] == "respaldo"


def test_la_vision_de_nvidia_lee_antes_que_gemini_lo_que_el_ocr_no_entiende(tmp_path):
    fotos = []
    for i in range(3):
        f = tmp_path / f"d{i}.jpg"
        f.write_bytes(b"jpg")
        fotos.append(f)
    usados = []
    ocr = lambda fs: ["texto ocr" if f.name == "d0.jpg" else "" for f in fs]
    vision = lambda fs: (usados.append(("vision", [f.name for f in fs])) or ["### lista" if f.name == "d1.jpg" else ""
                                                                            for f in fs], "nv-vl")
    gemini = lambda fs: (usados.append(("gemini", [f.name for f in fs])) or ["de gemini" for _ in fs], "g")
    r = reels.leer_fotogramas(fotos, gemini=gemini, ocr=ocr, vision=vision, medir=lambda f: 1.0)
    assert [x["lector"] for x in r["lecturas"]] == ["ocr", "nvidia:nv-vl", "gemini:g"]
    assert usados == [("vision", ["d1.jpg", "d2.jpg"]), ("gemini", ["d2.jpg"])]
    # vision_primero: la vision lee todo y el OCR solo lo que ella deja
    usados.clear()
    r = reels.leer_fotogramas(fotos, gemini=gemini, ocr=ocr, vision=vision, medir=lambda f: 1.0, vision_primero=True)
    assert usados[0] == ("vision", ["d0.jpg", "d1.jpg", "d2.jpg"])
    assert [x["lector"] for x in r["lecturas"]] == ["ocr", "nvidia:nv-vl", "gemini:g"]


def test_vision_de_nvidia_manda_las_imagenes_y_parte_los_bloques(tmp_path, monkeypatch):
    import proveedores as P
    from nucleo import enfriamiento, modelos_estado
    monkeypatch.setattr(P.NvidiaProvider, "_clave", lambda self: "K")
    monkeypatch.setattr(enfriamiento, "enfriado", lambda p: None)
    monkeypatch.setattr(modelos_estado, "en_uso", lambda prov, ms: tuple(ms))
    f1, f2 = tmp_path / "a.jpg", tmp_path / "b.jpg"
    f1.write_bytes(b"a"), f2.write_bytes(b"b")
    vistos = {}

    def post(url, cuerpo, cab, timeout):
        vistos.update(url=url, cuerpo=cuerpo, cab=cab)
        return reels._Respuesta(200, json.dumps({"choices": [{"message": {"content": "### 1\nhola\n### 2\nVACIO"}}]}), {})
    textos, modelo = reels.nvidia_bloques([f1, f2], post=post)
    assert textos == ["hola", "VACIO"] and modelo == P.MODELO_NVIDIA_VISION
    partes = vistos["cuerpo"]["messages"][0]["content"]
    assert partes[0]["type"] == "text" and [p["type"] for p in partes[1:]] == ["image_url", "image_url"]
    assert vistos["cab"] == {"Authorization": "Bearer K"} and vistos["cuerpo"]["model"] == P.MODELO_NVIDIA_VISION
    with pytest.raises(RuntimeError):
        reels.nvidia_bloques([f1], post=lambda *a: reels._Respuesta(503, "", {}))


def test_depurar_saca_cuentas_y_lleva_trading_a_su_seccion_sin_ia(entorno):
    f = _ficha("CodAI0001", elementos=[_e("cuenta", "creador_x"), _e("idea_proyecto", "Bot RSI", categorias=["trading", "nexo"]),
                                       _e("repo", "kit", dueno="ana", categorias=["nexo"]),
                                       _e("idea_proyecto", "Bot Kelly", categorias=["trading"]),
                                       _e("web", "Datos de bolsa", categorias=["trading"]),
                                       _e("tecnica", "Medias moviles", categorias=["trading"]),
                                       _e("dato", "Relleno de bolsa", categorias=["trading"])])
    _guardar_ficha(entorno.carpeta, f)
    alm = D._vacio()
    alm["reels"]["CodAI0001"] = {"elementos": [
        {"i": 0, "clave": "creadorx", "destino": "guia", "motivo": "", "por": "modelo"},
        {"i": 1, "clave": "botrsi", "destino": "investigacion", "motivo": "", "por": "modelo"},
        {"i": 2, "clave": "ana/kit", "destino": "catalogo", "motivo": "", "por": "modelo"},
        {"i": 3, "clave": "botkelly", "destino": "descartado", "motivo": "no es para NEXO (trading o ajeno)",
         "por": "depurar"},
        {"i": 4, "clave": "datosdebolsa", "destino": "catalogo", "motivo": "", "por": "modelo"},
        {"i": 5, "clave": "mediasmoviles", "destino": "guia", "motivo": "", "por": "modelo"},
        {"i": 6, "clave": "rellenodebolsa", "destino": "descartado", "motivo": "duplicado de 3", "por": "modelo"}]}
    alm["guias"]["agentes"] = {"creadorx": {"nombre": "creador_x", "consejo": "siguelo"}}
    alm["guias"]["trading"] = {"mediasmoviles": {"nombre": "Medias moviles", "consejo": "cruce de 50 y 200",
                                                 "fuente": ""}}
    alm["investigaciones"]["botrsi"] = {"nombre": "Bot RSI", "pregunta": "¿rinde?", "tarea": "T1006"}
    alm["por_probar"]["ana/kit"] = {"nombre": "ana/kit"}
    alm["por_probar"]["datosdebolsa"] = {"nombre": "Datos de bolsa", "para_que": "precios gratis"}
    alm["t1006"] = ["Bot RSI"]
    r = D.depurar(alm)
    assert r["cambiados"] == 1 and r["a_trading"] == 4 and r["t1006_fuera"] == ["Bot RSI"] and alm["t1006"] == []
    assert alm["guias"]["agentes"] == {} and "ana/kit" in alm["por_probar"] and "datosdebolsa" not in alm["por_probar"]
    assert "trading" not in alm["guias"]
    assert [x["destino"] for x in alm["reels"]["CodAI0001"]["elementos"]] == [
        "descartado", "trading", "catalogo", "trading", "trading", "trading", "descartado"]
    assert set(alm["trading"]) == {"botrsi", "botkelly", "datosdebolsa", "mediasmoviles"}
    assert alm["trading"]["mediasmoviles"]["nota"] == "cruce de 50 y 200"
    assert alm["trading"]["datosdebolsa"]["nota"] == "precios gratis"
    # las que pedian investigacion vuelven como investigacion de trading, sin tarea (T1006 ya no cuenta)
    assert {k: (v["tema"], v["tarea"]) for k, v in alm["investigaciones"].items()} == {
        "botrsi": ("trading", None), "botkelly": ("trading", None)}
    assert D.depurar(alm)["a_trading"] == 0                        # idempotente

