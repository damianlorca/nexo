# -*- coding: utf-8 -*-
"""T667 (F1 de la epica T664): tribunal de revision sin Claude.

Escalera: tribunal (3 de 3, familias distintas, API gratuitas primero) -> apelacion (otras 3 IAs mas fuertes con
el desacuerdo resumido) -> bandeja de Damian. Claude solo recibe R3, lo que Damian le mande y la siembra de
calibracion (a ciegas). Todo con dobles: sin red, sin Chrome, sin memoria/ real (tareas a tmp_path por el
conftest de la raiz; tribunal y enfriamiento a tmp_path aqui).
"""
from __future__ import annotations

import json

import pytest

from nucleo import enfriamiento, investigacion, revision, tribunal
from nucleo import tareas as T

DOS = ("### PROPUESTAS IMPLEMENTABLES\n"
       "- QUE: Anadir las reglas al rol de programador | DONDE: roles y prompts | VALOR: 4 | ESFUERZO: 1 | "
       "RIESGO: bajo: solo texto\n"
       "- QUE: Cargar la politica solo en tareas de codigo | DONDE: router | VALOR: 3 | ESFUERZO: 3 | "
       "RIESGO: medio: puede no activarse\n")
R3 = ("### PROPUESTAS IMPLEMENTABLES\n"
      "- QUE: Relajar la lista roja de nucleo/permisos.py | DONDE: nucleo/permisos.py | VALOR: 3 | ESFUERZO: 2 | "
      "RIESGO: alto\n")


def dictamen(glob="APROBAR", props=("APROBAR", "APROBAR"), resultado=None, fallos=("- ninguno",), fin=True):
    lin = [f"GLOBAL: {glob} | motivo del global bastante claro"]
    lin += [f"P{i}: {v} | motivo de la propuesta {i}" for i, v in enumerate(props, 1)]
    if resultado:
        lin.append(f"RESULTADO: {resultado} | encaja con NEXO sin dependencias nuevas")
    lin += ["FALLOS:", *fallos]
    if fin:
        lin.append("FIN_DICTAMEN")
    return "\n".join(lin)


class Falso:
    """Proveedor de pega: cada candidato devuelve la siguiente respuesta de su lista (texto o Exception/None)."""

    def __init__(self, guion, cid, llamadas):
        self.guion, self.cid, self.llamadas = guion, cid, llamadas

    def disponible(self):
        return self.cid not in self.guion.get("_caidos", ())

    def enviar(self, prompt):
        from proveedores import Resultado
        self.llamadas.append((self.cid, prompt))
        cola = self.guion.get(self.cid) or self.guion.get("*") or []
        r = cola.pop(0) if len(cola) > 1 else (cola[0] if cola else None)
        if r is None:
            return Resultado("ERROR", detalle="HTTP 500")
        return Resultado("OK", texto=r)


@pytest.fixture
def entorno(tmp_path, monkeypatch, reloj_falso):
    monkeypatch.setattr(enfriamiento, "ALMACEN", tmp_path / "enfriamiento.json")
    monkeypatch.setattr(revision, "BORRADORES", tmp_path / "borradores")
    (tmp_path / "borradores").mkdir()
    reloj = reloj_falso(tribunal)
    guion: dict = {}
    llamadas: list = []
    monkeypatch.setattr(tribunal, "_proveedor", lambda c: Falso(guion, c.id, llamadas))
    monkeypatch.setattr(revision, "TOPE_INVESTIGACION", 99)   # T1007: aqui se prueba el tribunal, no el tope de propuestas
    monkeypatch.setattr(tribunal, "familias_autor", lambda prov: {"openai"} if prov == "chatgpt" else set())
    monkeypatch.setattr(tribunal, "_verificar_item", lambda texto: {"confirmado": None, "detalle": "sin url"})
    return {"guion": guion, "llamadas": llamadas, "reloj": reloj, "tmp": tmp_path}


def borrador(entorno, texto=DOS, etiquetas=("cat:investigacion",), autor="chatgpt", titulo="Investigar la herramienta X"):
    t = T.anadir(titulo, etiquetas=list(etiquetas), importancia=4)
    nombre = f"{t['id']}_20261003_1200.md"
    (entorno["tmp"] / "borradores" / nombre).write_text(
        f"<!-- OK | auditoria APROBADA | autor {autor} | revisores gemini -->\n# {t['id']} titulo\n\n"
        f"## Version final\nInforme con hallazgos.\n\n{texto}\n## Circuito de revision (T192)\n- nada\n",
        encoding="utf-8")
    revision.registrar_borrador(t["id"], nombre, auditoria="APROBADA")
    return t, nombre


def exp(nombre):
    return tribunal.expedientes()[nombre]


# ------------------------------------------------------------------ formato del dictamen
def test_parsear_dictamen_completo_y_quita_razonamiento():
    texto = "<think>pienso mucho</think>\n**GLOBAL:** APROBAR | bien\n" + dictamen(resultado="ADAPTAR").split("\n", 1)[1]
    d = tribunal.parsear("GLOBAL: APROBAR | bien\n" + texto, 2, es_inv=True)
    assert d["error"] == "" and d["global"] == "APROBAR" and [p[0] for p in d["propuestas"]] == ["APROBAR"] * 2
    assert d["resultado"][0] == "ADAPTAR"


def test_parsear_detecta_salida_truncada_y_huecos():
    assert "truncada" in tribunal.parsear(dictamen(fin=False), 2, es_inv=False)["error"]
    assert "P2" in tribunal.parsear(dictamen(props=("APROBAR",)), 2, es_inv=False)["error"]
    assert "RESULTADO" in tribunal.parsear(dictamen(), 2, es_inv=True)["error"]
    assert tribunal.parsear("hola", 0, es_inv=False)["error"]


def test_fallos_falso_y_no_verificable_se_leen():
    d = tribunal.parsear(dictamen(fallos=("- [FALSO: la doc dice 1991] Python salio en 1995",
                                          "- [NO VERIFICABLE] el modelo X de 2026")), 2, es_inv=False)
    assert [f[0] for f in d["fallos"]] == ["FALSO", "NO VERIFICABLE"]


# ------------------------------------------------------------------ eleccion de revisores
def test_tres_primeros_disponibles_de_familias_distintas_sin_la_del_autor(entorno):
    t, nombre = borrador(entorno, etiquetas=("cat:investigacion", "material:interno"))
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR")]
    tribunal.ciclo()
    usados = [c for c, _ in entorno["llamadas"]]
    fams = [tribunal.CANDIDATOS[c].familia for c in usados]
    assert len(usados) == 3 and len(set(fams)) == 3 and "openai" not in fams
    assert not any(tribunal.CANDIDATOS[c].web for c in usados)            # API gratuitas primero
    assert usados == [c.id for c in tribunal.TRIBUNAL if c.familia != "openai" and not c.web][:3]


def test_suplente_si_un_revisor_falla_o_trunca(entorno):
    # autor sin familia excluida: con las 4 familias de API vivas (04/10) caben 2 fallos y 3 dictamenes
    t, nombre = borrador(entorno, autor="nvidia")
    api = [c for c in tribunal.TRIBUNAL if not c.web]
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR")]
    entorno["guion"][api[0].id] = [None]                                   # cae
    entorno["guion"][api[1].id] = [dictamen(resultado="ADOPTAR", fin=False)]   # truncado (T675)
    tribunal.ciclo()
    e = exp(nombre)
    assert len(e["dictamenes"]["tribunal"]) == 3
    motivos = " ".join(f["motivo"] for f in e["fallos"])
    assert "HTTP 500" in motivos and "truncada" in motivos
    assert len({d["familia"] for d in e["dictamenes"]["tribunal"]}) == 3
    assert not {api[0].id, api[1].id} & {d["id"] for d in e["dictamenes"]["tribunal"]}


def test_suplente_si_un_revisor_acusa_en_falso(entorno, monkeypatch):
    t, nombre = borrador(entorno, autor="nvidia")
    api = [c for c in tribunal.TRIBUNAL if not c.web]
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR")]
    entorno["guion"][api[0].id] = [dictamen(resultado="ADOPTAR", fallos=(
        "- [FALSO: no existe] el repo https://github.com/a/b no existe",))]
    monkeypatch.setattr(tribunal, "_verificar_item", lambda texto: {"confirmado": True, "detalle": "existe"})
    tribunal.ciclo()
    e = exp(nombre)
    assert len(e["dictamenes"]["tribunal"]) == 3 and api[0].id not in {d["id"] for d in e["dictamenes"]["tribunal"]}
    assert "desmentida" in " ".join(f["motivo"] for f in e["fallos"])


def test_espera_si_no_hay_tres_familias_y_nunca_decide_con_dos(entorno, monkeypatch):
    t, nombre = borrador(entorno)
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR")]
    vivos = [c.id for c in tribunal.TRIBUNAL if c.familia in ("alibaba", "google")]
    entorno["guion"]["_caidos"] = [c.id for c in tribunal.CANDIDATOS.values() if c.id not in vivos]
    r = tribunal.ciclo()
    e = exp(nombre)
    assert e["fase"] == "tribunal" and len(e["dictamenes"]["tribunal"]) == 2 and "3 familias" in e["motivo"]
    assert T.buscar(t["id"])["estado"] not in T.CERRADOS and r["esperando"] == 1
    # al volver una tercera familia, sigue donde lo dejo: no repite las dos que ya dictaminaron
    entorno["guion"]["_caidos"] = []
    entorno["llamadas"].clear()
    tribunal.ciclo()
    assert len(entorno["llamadas"]) == 1 and exp(nombre)["fase"] == "resuelto"


def test_web_solo_como_extra_con_cupo_diario_medido_con_enfriamiento(entorno):
    t, nombre = borrador(entorno, autor="nvidia")
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR")]
    entorno["guion"]["_caidos"] = [c.id for c in tribunal.CANDIDATOS.values() if not c.web][:-1]
    tribunal.ciclo()
    web = [c for c, _ in entorno["llamadas"] if tribunal.CANDIDATOS[c].web]
    assert web                                                               # sin 3 familias API, entra la web
    prov = tribunal.CANDIDATOS[web[0]].proveedor
    assert tribunal.cupo_web()[prov]["usadas"] == 1
    for _ in range(tribunal.CUPO_WEB[prov] - 1):
        tribunal._contar_web(prov)
    assert enfriamiento.enfriado(f"tribunal:{prov}") is not None             # cupo agotado = enfriado hasta manana
    assert not tribunal._disponible(tribunal.CANDIDATOS[web[0]])


def test_sin_rafagas_espera_entre_llamadas_al_mismo_proveedor(entorno):
    for _ in range(2):
        borrador(entorno, autor="gemini")
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR")]
    tribunal.ciclo()
    assert entorno["reloj"].esperas and max(entorno["reloj"].esperas) <= tribunal.PAUSA_API


# ------------------------------------------------------------------ decision del tribunal
def test_unanimidad_aprueba_con_quien_tribunal_y_resultado_t674(entorno):
    t, nombre = borrador(entorno)
    entorno["guion"]["*"] = [dictamen(props=("APROBAR", "RECHAZAR"), resultado="ADAPTAR")]
    tribunal.ciclo()
    e = exp(nombre)
    assert e["fase"] == "resuelto" and e["decision"] == "APROBADO" and e["quien"] == "tribunal"
    props = [T.buscar(p) for p in e["propuestas"]]
    assert [p["estado"] for p in props] == ["pendiente", "descartada"]
    assert "Tribunal" in " ".join(n["texto"] for n in props[0]["notas"])
    o = T.buscar(t["id"])
    assert o["estado"] == "esperando" and o["resultado"]["decision"] == "ADAPTAR" and o["resultado"]["quien"] == "tribunal"


def test_unanimidad_rechaza_descarta_el_borrador_sin_cerrar_la_investigacion(entorno):
    t, nombre = borrador(entorno)
    entorno["guion"]["*"] = [dictamen("RECHAZAR", ("RECHAZAR", "RECHAZAR"), resultado="DESCARTAR")]
    tribunal.ciclo()
    assert exp(nombre)["decision"] == "DESCARTADO"
    assert T.buscar(t["id"])["estado"] == "pendiente"                        # T674: borrador malo, sigue viva


def test_falso_confirmado_impide_la_unanimidad(entorno, monkeypatch):
    t, nombre = borrador(entorno)
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR", fallos=("- [NO VERIFICABLE] https://x.org/doc",))]
    monkeypatch.setattr(tribunal, "_verificar_item", lambda texto: {"confirmado": False, "detalle": "404"})
    tribunal.ciclo()
    e = exp(nombre)
    assert e["fase"] in ("apelacion", "damian", "claude") and "404" in e["resumen"]


def test_no_verificable_nunca_castiga_un_dato_real_reciente(entorno):
    t, nombre = borrador(entorno)
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR", fallos=("- [NO VERIFICABLE] Gemini 3.6 salio en 2026",))]
    tribunal.ciclo()
    assert exp(nombre)["decision"] == "APROBADO"
    p = entorno["llamadas"][0][1]
    assert "2025-2026" in p and "NO VERIFICABLE" in p


# ------------------------------------------------------------------ apelacion y bandeja de Damian
def test_desacuerdo_va_a_apelacion_con_otras_ias_y_el_resumen(entorno):
    t, nombre = borrador(entorno)
    api = [c for c in tribunal.TRIBUNAL if not c.web and c.familia != "openai"]
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR")]
    entorno["guion"][api[1].id] = [dictamen("RECHAZAR", ("RECHAZAR", "RECHAZAR"), resultado="DESCARTAR")]
    tribunal.ciclo(max_expedientes=1)
    e = exp(nombre)
    assert e["fase"] == "resuelto" and e["decision"] == "APROBADO"           # la apelacion fue unanime
    trib = {d["id"] for d in e["dictamenes"]["tribunal"]}
    apel = {d["id"] for d in e["dictamenes"]["apelacion"]}
    assert len(apel) == 3 and not trib & apel
    prompt_apel = [p for c, p in entorno["llamadas"] if c in apel][0]
    assert "DESACUERDO" in prompt_apel and "RECHAZAR" in prompt_apel


def _a_bandeja(entorno, monkeypatch=None, **kw):
    """Desacuerdo que sobrevive a la apelacion. Desde el 13/10 va a CLAUDE (escalada); con monkeypatch, la bandeja
    de Claude se da por llena y llega a la de Damian (lo que se prueba de su bandeja)."""
    if monkeypatch is not None:
        monkeypatch.setattr(tribunal, "MAX_BANDEJA_CLAUDE", 0)
    t, nombre = borrador(entorno, **kw)
    entorno["guion"]["*"] = [dictamen(props=("APROBAR", "RECHAZAR"), resultado="ADAPTAR")]
    raro = [c for c in tribunal.CANDIDATOS.values() if not c.web][1]
    entorno["guion"][raro.id] = [dictamen("RECHAZAR", ("RECHAZAR", "RECHAZAR"), resultado="DESCARTAR")]
    for c in tribunal.APELACION[:1]:
        entorno["guion"][c.id] = [dictamen("DUDA", ("DUDA", "DUDA"), resultado="ADAPTAR")]
    tribunal.ciclo()
    return t, nombre


def test_si_persiste_tras_la_apelacion_lo_decide_claude(entorno):
    t, nombre = _a_bandeja(entorno)
    e = exp(nombre)
    assert e["fase"] == "claude" and "apelacion tampoco" in e["motivo"]
    assert [c["nombre"] for c in tribunal.bandeja_claude()["casos"]] == [nombre]
    assert T.buscar(t["id"])["estado"] not in T.CERRADOS


def test_con_la_bandeja_de_claude_llena_va_a_la_de_damian_con_resumen_de_tres_lineas(entorno, monkeypatch):
    t, nombre = _a_bandeja(entorno, monkeypatch)
    e = exp(nombre)
    assert e["fase"] == "damian"
    caso = next(c for c in tribunal.bandeja_damian() if c["nombre"] == nombre)
    assert len(caso["lineas"]) == 3 and t["id"] in caso["lineas"][0] and caso["resultado"] == "ADAPTAR"
    assert T.buscar(t["id"])["estado"] not in T.CERRADOS                    # nada aplicado sin Damian


def test_damian_aprueba_y_queda_la_coincidencia_por_revisor(entorno, monkeypatch):
    t, nombre = _a_bandeja(entorno, monkeypatch)
    tribunal.decidir_damian(nombre, "aprobar")
    e = exp(nombre)
    assert e["fase"] == "resuelto" and e["quien"] == "damian"
    assert T.buscar(t["id"])["resultado"]["quien"] == "damian"
    filas = tribunal._leer_calibracion()
    assert filas[-1]["fuente"] == "damian" and filas[-1]["referencia"] == "APROBADO"
    assert set(filas[-1]["revisores"].values()) == {True, False}


def test_damian_rechaza_o_manda_a_claude(entorno, monkeypatch):
    t, nombre = _a_bandeja(entorno, monkeypatch)
    monkeypatch.setattr(tribunal, "MAX_BANDEJA_CLAUDE", 20)
    tribunal.decidir_damian(nombre, "claude")
    assert exp(nombre)["fase"] == "claude"
    assert [c["nombre"] for c in tribunal.bandeja_claude()["casos"]] == [nombre]
    t2, n2 = _a_bandeja(entorno, monkeypatch, titulo="Investigar Y")
    tribunal.decidir_damian(n2, "rechazar")
    assert exp(n2)["decision"] == "DESCARTADO"


def test_bandeja_de_claude_maximo_veinte(entorno, monkeypatch):
    monkeypatch.setattr(tribunal, "MAX_BANDEJA_CLAUDE", 1)
    t, nombre = _a_bandeja(entorno)                       # escalada: ocupa el unico hueco de Claude
    assert exp(nombre)["fase"] == "claude"
    t2, n2 = _a_bandeja(entorno, titulo="Investigar Y")   # Claude lleno: a Damian
    assert exp(n2)["fase"] == "damian"
    with pytest.raises(tribunal.BandejaLlena):
        tribunal.decidir_damian(n2, "claude")
    assert exp(n2)["fase"] == "damian"


def test_r3_va_directo_a_claude_sin_gastar_revisores(entorno):
    t, nombre = borrador(entorno, texto=R3)
    tribunal.ciclo()
    assert exp(nombre)["fase"] == "claude" and "R3" in exp(nombre)["motivo"] and not entorno["llamadas"]


def test_veredicto_aplicado_fuera_del_tribunal_cierra_el_expediente(entorno):
    t, nombre = _a_bandeja(entorno)
    revision.veredicto(nombre, "DESCARTADO", "lo decide Claude por otra via")
    tribunal.ciclo()
    assert exp(nombre)["fase"] == "resuelto" and exp(nombre)["quien"] == "fuera"


# ------------------------------------------------------------------ calibracion
def test_siembra_a_ciegas_y_dictamen_de_claude(entorno):
    t = T.anadir("Investigar Z", etiquetas=["cat:investigacion"])
    (entorno["tmp"] / "borradores" / f"{t['id']}_20260926_1413.md").write_text(
        "<!-- autor groq -->\n## Version final\nInforme.\n" + DOS, encoding="utf-8")
    investigacion.decidir(t["id"], "DESCARTAR", "no aporta frente a lo que ya tiene NEXO")
    r = tribunal.sembrar([t["id"], "T999"], total=1)
    assert r["nuevos"] == [f"{t['id']}_20260926_1413.md"] and "T999" in r["sin_borrador"]
    nombre = r["nuevos"][0]
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR")]
    tribunal.ciclo()
    e = exp(nombre)
    assert e["fase"] == "calibracion" and e["decision_tribunal"] == "APROBADO"
    caso = tribunal.bandeja_claude()["casos"][0]
    assert caso["nombre"] == nombre and "APROBADO" not in json.dumps(caso)   # Claude no ve al tribunal
    tribunal.dictamen_claude(nombre, "DESCARTADO", "no encaja con NEXO, Damian no la quiere",
                             resultado=("DESCARTAR", "no aporta frente a lo que ya hay"))
    fila = tribunal._leer_calibracion()[-1]
    assert fila["fuente"] == "siembra" and fila["tribunal"] == "APROBADO" and fila["referencia"] == "DESCARTADO"
    assert exp(nombre)["fase"] == "resuelto" and T.buscar(t["id"])["estado"] == "hecha"   # cerrada: no se toca


def test_siembra_rellena_con_veredictos_historicos_de_claude(entorno):
    t, nombre = borrador(entorno, etiquetas=("cat:redaccion",), titulo="Redactar algo")
    revision.veredicto(nombre, "APROBADO", "esta bien hecho y sirve a NEXO")
    r = tribunal.sembrar([], total=5)
    assert r["historicos"] == [nombre]
    assert exp(nombre)["calibracion"] == {"fuente": "historico", "referencia": "APROBADO"}
    entorno["guion"]["*"] = [dictamen()]
    tribunal.ciclo()
    assert tribunal._leer_calibracion()[-1]["tribunal"] == "APROBADO"
    assert not tribunal.bandeja_claude()["casos"]                            # la referencia ya existia


def _filas(monkeypatch, filas):
    monkeypatch.setattr(tribunal, "_leer_calibracion", lambda: filas)


def test_revisor_bajo_70_en_20_casos_sale_de_la_lista(entorno, monkeypatch):
    malo = tribunal.TRIBUNAL[0].id
    filas = [{"tipo": "general", "tribunal": None, "referencia": "APROBADO",
              "revisores": {malo: i < 13}} for i in range(20)]                # 65 %
    _filas(monkeypatch, filas)
    tribunal._evaluar()
    assert malo in tribunal._estado()["excluidos"] and not tribunal._disponible(tribunal.TRIBUNAL[0])


def test_tipo_bajo_85_abre_tarea_t321_y_pasa_por_apelacion_y_damian(entorno, monkeypatch):
    filas = [{"tipo": "investigacion", "tribunal": "APROBADO", "referencia": "APROBADO" if i < 16 else "DESCARTADO",
              "revisores": {}} for i in range(20)]                              # 80 %
    _filas(monkeypatch, filas)
    tribunal._evaluar()
    assert "investigacion" in tribunal._estado()["vigilados"]
    hija = [x for x in T.cargar()["tareas"] if "tribunal:tipo:investigacion" in (x.get("etiquetas") or [])]
    assert len(hija) == 1 and "T321" in hija[0]["detalle"]
    tribunal._evaluar()
    assert len([x for x in T.cargar()["tareas"] if "tribunal:tipo:investigacion" in (x.get("etiquetas") or [])]) == 1
    t, nombre = borrador(entorno)
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR")]
    tribunal.ciclo()
    e = exp(nombre)
    assert e["fase"] == "damian" and e["decision_tribunal"] == "APROBADO" and len(e["dictamenes"]["apelacion"]) == 3


def test_resultados_posteriores_cuentan_para_la_calidad(entorno):
    t, nombre = borrador(entorno)
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR")]
    tribunal.ciclo()
    tribunal.registrar_resultado(nombre, "veto", correcto=False)
    fila = tribunal._leer_calibracion()[-1]
    assert fila["fuente"] == "veto" and fila["tribunal"] == "APROBADO" and fila["referencia"] == "DESCARTADO"
    assert not any(fila["revisores"].values())


# ------------------------------------------------------------------ piezas que toca el tribunal
def test_veredicto_con_quien_y_por_defecto_sigue_siendo_claude(entorno):
    t, nombre = borrador(entorno, etiquetas=("cat:redaccion",), titulo="Redactar algo")
    revision.veredicto(nombre, "APROBADO", "esta bien hecho y sirve a NEXO", quien="tribunal")
    p = T.buscar(revision.propuestas_de(nombre, estados=("pendiente",))[0]["id"])
    assert "APROBADA por el tribunal" in p["notas"][-1]["texto"]
    t2, n2 = borrador(entorno, etiquetas=("cat:redaccion",), titulo="Redactar otra")
    revision.veredicto(n2, "DESCARTADO", "no sirve para nada en NEXO")
    assert "Revision de Claude del borrador" in " ".join(n["texto"] for n in T.buscar(t2["id"])["notas"])


def test_enfriar_acepta_segundos_propios(entorno):
    enfriamiento.enfriar("tribunal:chatgpt", "cupo_diario", "cupo", segundos=3600)
    assert "cupo_diario" in enfriamiento.enfriado("tribunal:chatgpt")


def test_orden_de_la_bandeja_de_claude_es_autosuficiente():
    texto = tribunal.orden_claude()
    for clave in ("nucleo.tribunal bandeja_claude", "nucleo.revision veredicto", "--resultado",
                  "nucleo.tribunal dictamen", "pytest tests interfaz", "publicar_nube.py"):
        assert clave in texto


def test_simular_no_llama_a_nadie_ni_cambia_nada(entorno):
    t, nombre = borrador(entorno)
    r = tribunal.ciclo(simular=True)
    assert r["simulado"] and not entorno["llamadas"] and nombre not in tribunal.expedientes()


# ------------------------------------------------------------------ turno 'tribunal'
def test_turno_tribunal_lanza_el_ciclo_del_tribunal_y_no_trabajo(entorno, monkeypatch):
    import turno_nexo
    from nucleo import freno, trabajo, turnos
    assert "tribunal" in turnos.PLANTILLAS and "tribunal" not in freno.GENERADORAS   # el freno no lo para
    borrador(entorno)
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: None)
    monkeypatch.setattr(turno_nexo, "ram_libre_gb", lambda: 32.0)
    monkeypatch.setattr(trabajo, "ciclo", lambda **k: pytest.fail("el turno tribunal no usa trabajo.ciclo"))
    llamado = {}
    monkeypatch.setattr(tribunal, "ciclo", lambda **k: llamado.update(k) or {"hechos": [], "esperando": 0})
    t = turnos.guardar_turno({"nombre": "Tribunal", "plantilla": "tribunal", "dias": list(turnos.DIAS),
                              "horas": ["02:00"], "max_tareas": 4})
    reg = turno_nexo.turno(turno_id=t["id"])
    assert "tribunal" in reg["pasos"] and llamado["max_expedientes"] == 4 and llamado["limite"]


def test_turno_tribunal_sin_expedientes_no_arranca(entorno):
    from nucleo import plantillas_turno, turnos
    ctx = dict(turnos.contexto(), plantilla="tribunal")
    assert plantillas_turno.candidatas(ctx) == 0
    assert "tribunal" in plantillas_turno.por_que_nada(ctx)


def test_familia_del_autor_es_la_de_su_primer_modelo(monkeypatch):
    import proveedores
    falso = type("P", (), {"modelos": ("openai/gpt-oss-20b", "mistralai/mistral-nemotron", "z-ai/glm-5.3-flash")})
    monkeypatch.setattr(proveedores, "NvidiaProvider", falso)
    assert tribunal.familias_autor("nvidia") == {"openai"}       # excluir las 4 dejaba sin 3 familias
    assert tribunal.familias_autor("chatgpt") == {"openai"} and tribunal.familias_autor("gemini_api") == {"google"}


def test_tribunal_excluye_la_familia_real_del_modelo_del_autor(entorno):
    t, nombre = borrador(entorno, autor="groq | modelo qwen/qwen3-32b,mistralai/mistral-nemotron")
    assert exp_o_nuevo(nombre)["modelos_autor"] == ["qwen/qwen3-32b", "mistralai/mistral-nemotron"]
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR")]
    tribunal.ciclo()
    fams = {tribunal.CANDIDATOS[c].familia for c, _ in entorno["llamadas"]}
    assert not fams & {"alibaba", "mistral"}                    # la familia real, no la del primer modelo de Groq


def test_borrador_antiguo_sin_modelo_usa_la_familia_del_primer_modelo(entorno):
    t, nombre = borrador(entorno, autor="chatgpt")
    e = exp_o_nuevo(nombre)
    assert e["modelos_autor"] == [] and tribunal._familias_prohibidas(e) == {"openai"}


def exp_o_nuevo(nombre):
    tribunal._sincronizar()
    return tribunal.expedientes()[nombre]


# ------------------------------------------------------------------ 04/10: banco, R3 acotado y re-encolado
def test_parsear_acepta_el_voto_sin_barra_separadora():
    """Banco 04/10: qwen3.8-27b escribio 'GLOBAL: RECHAZAR El borrador...' (sin '|'): el dictamen es valido."""
    texto = ("GLOBAL: RECHAZAR El borrador tiene un error de fecha.\nP1: APROBAR Python ya esta instalado.\n"
             "FALLOS:\n- [FALSO: la 0.9.0 es de 1991] dice 1995\nFIN_DICTAMEN")
    d = tribunal.parsear(texto, 1, es_inv=False)
    assert d["error"] == "" and d["global"] == "RECHAZAR" and d["propuestas"][0][0] == "APROBAR"
    assert d["motivo"].startswith("El borrador") and d["fallos"][0][0] == "FALSO"
    assert tribunal.parsear("GLOBAL: QUIZAS | no se\nFIN_DICTAMEN", 0, es_inv=False)["error"]


def test_modelos_retirados_fuera_y_sustitutos_dentro():
    ids = {c.modelo for c in tribunal.CANDIDATOS.values()}
    assert not ids & {"mistralai/mistral-nemotron", "qwen/qwen3-32b", "z-ai/glm-5.3-flash"}
    assert "qwen/qwen3.8-27b" in ids
    assert not ids & {"moonshotai/kimi-k3", "deepseek-ai/deepseek-v4.1-flash"}   # no pasaron el banco


SEGURIDAD = ("### PROPUESTAS IMPLEMENTABLES\n"
             "- QUE: Desactivar la telemetria de consultas por defecto | DONDE: seguridad y permisos | VALOR: 5 | "
             "ESFUERZO: 2 | RIESGO: bajo\n"
             "- QUE: Anadir un resumen semanal | DONDE: documentacion | VALOR: 3 | ESFUERZO: 1 | RIESGO: bajo\n")


def test_r3_solo_blindados_secretos_o_dinero():
    assert tribunal.es_r3("QUE: Relajar la lista roja de nucleo/permisos.py | DONDE: seguridad y permisos")
    assert tribunal.es_r3("QUE: Guardar la clave en secretos.toml | DONDE: memoria")
    assert tribunal.es_r3("QUE: Autorizar antes cualquier gasto variable | DONDE: interfaz")
    assert not tribunal.es_r3(SEGURIDAD.splitlines()[1])                      # seguridad: la revisa el tribunal


def test_seguridad_la_revisa_el_tribunal_y_aprobada_lleva_marca_r3(entorno):
    t, nombre = borrador(entorno, texto=SEGURIDAD, etiquetas=("cat:redaccion",), titulo="Redactar mejoras")
    entorno["guion"]["*"] = [dictamen()]
    tribunal.ciclo()
    e = exp(nombre)
    assert e["fase"] == "resuelto" and e["decision"] == "APROBADO" and entorno["llamadas"]
    seg, otra = (T.buscar(p) for p in e["propuestas"])
    assert seg["estado"] == "pendiente" and "riesgo:R3" in seg["etiquetas"] and "F2" in seg["notas"][-1]["texto"]
    assert "riesgo:R3" not in otra["etiquetas"]


def test_reencolar_r3_que_ya_no_cumplen(entorno):
    t, nombre = borrador(entorno, texto=SEGURIDAD, etiquetas=("cat:redaccion",), titulo="Redactar mejoras")
    t2, n2 = borrador(entorno, texto=R3, etiquetas=("cat:redaccion",), titulo="Redactar otra")
    tribunal._sincronizar()
    with tribunal._editar() as d:          # como quedaron en el primer uso, con el criterio viejo
        d[nombre].update(fase="claude", motivo="R3: toca blindados, seguridad, secretos o dinero")
    r = tribunal.reencolar_r3()
    assert r == {"reencolados": [nombre], "siguen": [n2]}
    assert exp(nombre)["fase"] == "tribunal" and exp(n2)["fase"] == "claude"


def test_autor_chatgpt_reune_tres_familias_tambien_en_apelacion(entorno):
    """Un borrador de ChatGPT necesita en apelacion un NVIDIA distinto del del tribunal (T1039: el 2.o de la config)."""
    t, nombre = borrador(entorno)                                          # autor chatgpt: sin openai
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR")]
    entorno["guion"][tribunal.TRIBUNAL[0].id] = [dictamen("RECHAZAR", ("RECHAZAR", "RECHAZAR"), resultado="DESCARTAR")]
    tribunal.ciclo()
    e = exp(nombre)
    apel = [d["id"] for d in e["dictamenes"]["apelacion"]]
    assert len(apel) == 3 and tribunal._NVIDIA_B.id in apel and e["fase"] == "resuelto"
    assert tribunal._NVIDIA.id in [d["id"] for d in e["dictamenes"]["tribunal"]]


def test_parsear_dictamen_en_un_solo_parrafo_como_lo_pinta_gemini_web():
    """Ciclo 2 (04/10): Gemini web junta las lineas del dictamen en un parrafo y se daba por 'falta el voto de P1'."""
    texto = ("GLOBAL: APROBAR | Bien planteado. P1: APROBAR | separar buscar de instalar. P2: RECHAZAR | duplicada. "
             "RESULTADO: ADAPTAR | idea valida. FALLOS:\n\n- [NO VERIFICABLE] el issue 1874. FIN_DICTAMEN")
    d = tribunal.parsear(texto, 2, es_inv=True)
    assert d["error"] == "" and [p[0] for p in d["propuestas"]] == ["APROBAR", "RECHAZAR"]
    assert d["resultado"][0] == "ADAPTAR" and d["motivo"] == "Bien planteado." and d["fallos"][0][0] == "NO VERIFICABLE"


# ------------------------------------------------------------------ expediente parcial (Damian 04/10)
TRES = ("### PROPUESTAS IMPLEMENTABLES\n"
        "- QUE: Separar buscar de instalar | DONDE: navegador y herramientas | VALOR: 4 | ESFUERZO: 2 | RIESGO: bajo\n"
        "- QUE: Bloquear plugins no autorizados | DONDE: navegador y herramientas | VALOR: 3 | ESFUERZO: 2 | RIESGO: bajo\n"
        "- QUE: Traducir la documentacion al ingles | DONDE: documentacion/LEEME.md | VALOR: 1 | ESFUERZO: 3 | RIESGO: bajo\n")


def _parcial(entorno, apel_votos=("APROBAR",)):
    """Tribunal: global 3 APROBAR, P1 3 APROBAR, P3 3 RECHAZAR y P2 dividida (el primer revisor la rechaza)."""
    t, nombre = borrador(entorno, texto=TRES)
    api = [c for c in tribunal.TRIBUNAL if not c.web and c.familia != "openai"]
    entorno["guion"]["*"] = [dictamen(props=("APROBAR", "APROBAR", "RECHAZAR"), resultado="ADAPTAR")]
    entorno["guion"][api[0].id] = [dictamen(props=("APROBAR", "RECHAZAR", "RECHAZAR"), resultado="ADAPTAR")]
    for c, v in zip(tribunal.APELACION, apel_votos):
        entorno["guion"][c.id] = [dictamen(props=(v,), resultado="ADAPTAR")]
    return t, nombre


def test_parcial_aplica_las_unanimes_y_apela_solo_la_dividida(entorno):
    t, nombre = _parcial(entorno)
    ids = [p["id"] for p in revision.propuestas_de(nombre)]
    tribunal.ciclo(max_expedientes=1)
    e = exp(nombre)
    p1, p2, p3 = (T.buscar(i) for i in ids)
    assert p1["estado"] == "pendiente" and "parcial" in p1["notas"][-1]["texto"].lower()
    assert p3["estado"] == "descartada"
    assert e["parcial"]["aprobadas"] == [ids[0]] and e["parcial"]["descartadas"] == [ids[2]]
    # la apelacion solo ve la dividida y, unanime, cierra el borrador con el RESULTADO del tribunal
    prompts_apel = [p for c, p in entorno["llamadas"] if c in {d["id"] for d in e["dictamenes"]["apelacion"]}]
    bloques = [p.rsplit("PROPUESTAS:\n", 1)[1].split("\n\nResponde", 1)[0] for p in prompts_apel]
    assert bloques and all("Bloquear plugins" in b and "Separar buscar" not in b and "P2" not in b for b in bloques)
    assert all("EXPEDIENTE PARCIAL" in p for p in prompts_apel)
    assert e["fase"] == "resuelto" and p2["estado"] == "pendiente"
    assert T.buscar(t["id"])["resultado"]["decision"] == "ADAPTAR"


def test_parcial_sin_unanimidad_en_apelacion_llega_a_damian_solo_con_la_dividida(entorno, monkeypatch):
    monkeypatch.setattr(tribunal, "MAX_BANDEJA_CLAUDE", 0)       # sin hueco en Claude: a Damian
    t, nombre = _parcial(entorno, apel_votos=("DUDA",))
    ids = [p["id"] for p in revision.propuestas_de(nombre)]
    tribunal.ciclo(max_expedientes=1)
    e = exp(nombre)
    assert e["fase"] == "damian" and e["propuestas"] == [ids[1]]
    caso = tribunal.bandeja_damian()[0]
    assert "1 propuesta" in caso["lineas"][0] and "P1" in caso["lineas"][2]
    tribunal.decidir_damian(nombre, "rechazar")
    assert T.buscar(ids[1])["estado"] == "descartada" and T.buscar(ids[0])["estado"] == "pendiente"


def test_global_dividido_sigue_mandando_todo_el_expediente(entorno):
    t, nombre = borrador(entorno, texto=TRES)
    api = [c for c in tribunal.TRIBUNAL if not c.web and c.familia != "openai"]
    entorno["guion"]["*"] = [dictamen(props=("APROBAR", "APROBAR", "RECHAZAR"), resultado="ADAPTAR")]
    entorno["guion"][api[0].id] = [dictamen("RECHAZAR", ("APROBAR", "RECHAZAR", "RECHAZAR"), resultado="ADAPTAR")]
    for c in tribunal.APELACION[:1]:
        entorno["guion"][c.id] = [dictamen("DUDA", ("DUDA", "DUDA", "DUDA"), resultado="ADAPTAR")]
    tribunal.ciclo(max_expedientes=1)
    e = exp(nombre)
    assert not e.get("parcial") and len(e["propuestas"]) == 3
    assert all(T.buscar(i)["estado"] == "propuesta" for i in e["propuestas"])


# ------------------------------------------------------------------ turno nocturno del tribunal
def test_turno_tribunal_admite_cada_media_hora_y_los_demas_no(entorno):
    from nucleo import turnos
    horas = [f"{h:02d}:{m:02d}" for h in list(range(22, 24)) + list(range(0, 8)) for m in (0, 30)] + ["08:00"]
    t = turnos.guardar_turno({"nombre": "Tribunal de revision (sin Claude)", "plantilla": "tribunal",
                              "dias": list(turnos.DIAS), "horas": horas, "max_tareas": 3, "max_minutos": 25})
    assert len(t["horas"]) == 21
    with pytest.raises(turnos.ConfigInvalida):
        turnos.guardar_turno({"nombre": "Cola", "plantilla": "cola", "dias": list(turnos.DIAS), "horas": horas})


@pytest.mark.parametrize("ciclo, avisa", [({"hechos": [], "esperando": 0, "a_damian": [], "a_claude": []}, False),
                                          ({"hechos": [], "esperando": 0, "a_damian": ["T1_x.md"], "a_claude": []}, True),
                                          ({"hechos": [], "esperando": 0, "a_damian": [], "a_claude": ["T2_x.md"]}, True)])
def test_turno_tribunal_solo_avisa_si_algo_va_a_una_bandeja(entorno, monkeypatch, ciclo, avisa):
    import turno_nexo
    from nucleo import turnos
    borrador(entorno)
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: None)
    monkeypatch.setattr(turno_nexo, "ram_libre_gb", lambda: 32.0)
    monkeypatch.setattr(tribunal, "ciclo", lambda **k: dict(ciclo))
    avisos_ = []
    monkeypatch.setattr(turno_nexo, "_avisar_push", lambda *a: avisos_.append(a))
    t = turnos.guardar_turno({"nombre": "Tribunal", "plantilla": "tribunal", "dias": list(turnos.DIAS),
                              "horas": ["02:00"], "max_tareas": 3, "avisar": True})
    reg = turno_nexo.turno(turno_id=t["id"])
    assert reg["aviso_push"] is avisa and bool(avisos_) is avisa


def test_ciclo_dice_que_fue_a_las_bandejas(entorno):
    t, nombre = _a_bandeja(entorno)
    t2, n2 = borrador(entorno, texto=R3, titulo="Investigar Z")
    r = tribunal.ciclo()
    assert n2 in r["a_claude"]
    t3, n3 = borrador(entorno, titulo="Investigar W")
    entorno["guion"]["*"] = [dictamen("DUDA", ("DUDA", "DUDA"), resultado="ADAPTAR")]
    r = tribunal.ciclo()
    assert n3 in r["a_claude"]                    # 13/10: el desacuerdo tras la apelacion es de Claude


def test_turno_tribunal_sin_cambios_queda_silencioso(entorno, monkeypatch):
    """Noche 05/10: todo esperando revisores y nada nuevo -> registro silencioso, sin aviso (fuera del Centro)."""
    import turno_nexo
    from nucleo import planificador, turnos
    borrador(entorno)
    monkeypatch.setattr(turno_nexo.parada, "activa", lambda: None)
    monkeypatch.setattr(turno_nexo, "ram_libre_gb", lambda: 32.0)
    quieto = {"sincronizado": {"nuevos": [], "fuera": [], "a_claude": []}, "hechos": [{"nombre": "x", "fase": "espera"}],
              "esperando": 1, "a_damian": [], "a_claude": []}
    monkeypatch.setattr(tribunal, "ciclo", lambda **k: dict(quieto))
    t = turnos.guardar_turno({"nombre": "Tribunal", "plantilla": "tribunal", "dias": list(turnos.DIAS),
                              "horas": ["02:00"], "max_tareas": 3, "avisar": True})
    reg = turno_nexo.turno(turno_id=t["id"])
    assert reg["silencioso"] is True and reg["aviso_push"] is False
    assert planificador.ultimo_registro(ruidoso=True) is None
    monkeypatch.setattr(tribunal, "ciclo", lambda **k: dict(quieto, hechos=[{"nombre": "x", "fase": "resuelto"}]))
    reg = turno_nexo.turno(turno_id=t["id"])
    assert reg["silencioso"] is False and "1 resuelto" in planificador.resultado_corto(planificador.ultimo_registro(ruidoso=True))



# ------------------------------------------------------------------ 13/10: nada espera para siempre
def test_sin_quorum_posible_se_escala_sin_gastar_revisores(entorno, monkeypatch):
    """T699/T798/T820: autor openai -> gpt-oss y ChatGPT prohibidos; en apelacion no quedaban 3 familias."""
    t, nombre = borrador(entorno)
    monkeypatch.setattr(tribunal, "APELACION", tuple(c for c in tribunal.APELACION if c.familia in ("nvidia", "openai")))
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR")]
    api = [c for c in tribunal.TRIBUNAL if not c.web and c.familia != "openai"]
    entorno["guion"][api[1].id] = [dictamen("RECHAZAR", ("RECHAZAR", "RECHAZAR"), resultado="DESCARTAR")]
    tribunal.ciclo(max_expedientes=1)
    e = exp(nombre)
    assert e["fase"] == "claude" and "sin quorum" in e["motivo"] and not e["dictamenes"]["apelacion"]


def test_tres_pasadas_esperando_en_apelacion_se_escala_y_no_tapa_la_cola(entorno, monkeypatch):
    t, nombre = borrador(entorno)
    entorno["guion"]["*"] = [dictamen(resultado="ADOPTAR")]
    api = [c for c in tribunal.TRIBUNAL if not c.web and c.familia != "openai"]
    entorno["guion"][api[1].id] = [dictamen("RECHAZAR", ("RECHAZAR", "RECHAZAR"), resultado="DESCARTAR")]
    real = tribunal._reunir                     # en apelacion nunca hay revisores disponibles
    monkeypatch.setattr(tribunal, "_reunir", lambda e, fase, limite: fase == "tribunal" and real(e, fase, limite))
    tribunal.ciclo(max_expedientes=1)
    assert exp(nombre)["fase"] == "apelacion" and exp(nombre)["esperas"] == 1
    t2, n2 = borrador(entorno, titulo="Investigar Y")
    r = tribunal.ciclo(max_expedientes=1)
    assert r["hechos"][0]["nombre"] == n2          # el que espero va detras
    tribunal.ciclo(max_expedientes=3)
    tribunal.ciclo(max_expedientes=3)
    assert exp(nombre)["fase"] == "claude" and "3 pasadas" in exp(nombre)["motivo"]



def test_t860_la_bandeja_de_claude_se_entera_de_un_veredicto_dado_fuera(entorno):
    t, nombre = borrador(entorno, texto=R3, titulo="Investigar Z")
    tribunal.ciclo()
    assert [c["nombre"] for c in tribunal.bandeja_claude()["casos"]] == [nombre]
    revision.veredicto(nombre, "DESCARTADO", "lo reviso Claude a mano por la via de siempre")
    assert tribunal.bandeja_claude()["casos"] == []
    assert exp(nombre)["fase"] == "resuelto" and exp(nombre)["quien"] == "fuera"
