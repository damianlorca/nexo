# -*- coding: utf-8 -*-
"""T320: banco general de modelos gratuitos (nucleo/banco_modelos.py). Sin red: dobles de get/post/llamar."""
from __future__ import annotations

import json

import pytest

from nucleo import banco_modelos as B


@pytest.fixture(autouse=True)
def carpeta_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "CARPETA", tmp_path)
    monkeypatch.setattr(B, "RESULTADOS", tmp_path / "banco.jsonl")
    monkeypatch.setattr(B, "ROLES", tmp_path / "roles.json")
    monkeypatch.setattr(B, "INVENTARIO", tmp_path / "inventario.json")
    monkeypatch.setattr(B, "_clave", lambda nombre: "k-falsa")
    return tmp_path


# ---------------------------------------------------------------- inventario
def test_inventario_filtra_no_gratis_no_texto_y_grandes():
    respuestas = {
        "api.groq.com": {"data": [{"id": "openai/gpt-oss-120b"}, {"id": "whisper-large-v3"}]},
        "integrate.api.nvidia.com": {"data": [{"id": "nvidia/nemotron-3-super-120b-a12b"},
                                              {"id": "nvidia/modelo-de-pago"}]},
        "openrouter.ai": {"data": [{"id": "a/b:free"}, {"id": "a/b"}, {"id": "c/tts:free"}]},
        "generativelanguage": {"models": [
            {"name": "models/gemini-3.6-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-3.6-pro", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]}]},
        "localhost:11434": {"models": [{"name": "qwen2.5:7b", "details": {"parameter_size": "7.6B"}},
                                       {"name": "qwen3:14b", "details": {"parameter_size": "14.8B"}}]},
    }

    def get(url, cab):
        return next(v for k, v in respuestas.items() if k in url)
    inv = B.inventario(get=get)["proveedores"]
    ids = {p: [m["id"] for m in ms] for p, ms in inv.items()}
    assert ids == {"groq": ["openai/gpt-oss-120b"], "nvidia": ["nvidia/nemotron-3-super-120b-a12b"],
                   "openrouter": ["a/b:free"], "gemini_api": ["gemini-3.6-flash"], "ollama": ["qwen2.5:7b"]}


def test_inventario_sigue_si_un_proveedor_falla():
    def get(url, cab):
        if "groq" in url:
            raise RuntimeError("caido")
        return {"data": [], "models": []}
    inv = B.inventario(get=get)
    assert "groq" in inv["errores"] and "nvidia" in inv["proveedores"]


def test_inventario_saca_los_retirados(monkeypatch):
    from nucleo import modelos_estado
    monkeypatch.setattr(modelos_estado, "fuera_de_uso", lambda p, m: m == "openai/gpt-oss-20b")
    get = lambda url, cab: {"data": [{"id": "openai/gpt-oss-20b"}, {"id": "openai/gpt-oss-120b"}], "models": []}  # noqa: E731
    assert [m["id"] for m in B.inventario(get=get)["proveedores"]["groq"]] == ["openai/gpt-oss-120b"]


# ---------------------------------------------------------------- llamada: fail-closed
def test_llamar_no_llama_a_openrouter_sin_free_ni_a_nvidia_fuera_de_lista():
    def post(*a, **k):
        raise AssertionError("no debia llamar")
    assert "free" in B.llamar("openrouter", "a/b", "hola", post=post)["error"]
    assert "Free Endpoint" in B.llamar("nvidia", "nvidia/de-pago", "hola", post=post)["error"]


class _R:
    def __init__(self, codigo, j=None):
        self.status_code, self._j = codigo, j or {}

    def json(self):
        return self._j


def test_llamar_quita_think_y_anota_retirado(monkeypatch):
    from nucleo import modelos_estado
    anotados = []
    monkeypatch.setattr(modelos_estado, "anotar", lambda p, m, r: anotados.append(r))
    ok = B.llamar("groq", "m", "x", post=lambda *a, **k: _R(200, {"choices": [{"message": {
        "content": "<think>bla</think>respuesta"}}]}))
    assert ok["texto"] == "respuesta" and not ok["error"]
    mal = B.llamar("groq", "m", "x", post=lambda *a, **k: _R(410))
    assert mal["codigo"] == 410 and anotados == ["ok", 410]


# ---------------------------------------------------------------- programar
ORIGINAL = "def f(x):\n    return x\n\n\ndef g():\n    pass\n"


def test_aplicar_bloques_cambia_solo_lo_buscado():
    resp = "```\n<<<<<<< SEARCH\n    return x\n=======\n    return x + 1\n>>>>>>> REPLACE\n```"
    nuevo, motivo = B.aplicar_bloques(ORIGINAL, resp)
    assert motivo == "" and nuevo == ORIGINAL.replace("return x", "return x + 1")


def test_aplicar_bloques_rechaza_search_inexistente_o_sin_bloques():
    assert B.aplicar_bloques(ORIGINAL, "<<<<<<< SEARCH\nno existe\n=======\nx\n>>>>>>> REPLACE")[0] is None
    assert B.aplicar_bloques(ORIGINAL, "aqui tienes el codigo")[1] == "sin bloques SEARCH/REPLACE"


def test_evaluar_programar_usa_los_tests():
    caso = {"rol": "programar", "caso": "T421"}
    original = (B.RAIZ / B.OBJETIVO).read_text(encoding="utf-8")
    linea = original.splitlines()[0]
    resp = f"<<<<<<< SEARCH\n{linea}\n=======\n{linea}\n>>>>>>> REPLACE"
    vistos = []
    r = B.evaluar_programar(caso, resp, ejecutar=lambda tid, nuevo: vistos.append(tid) or
                            {"pasan": 3, "total": 4, "nota": 0.75, "verde": False})
    assert vistos == ["T421"] and r["nota"] == 0.75 and not r["verde"]


def test_los_casos_de_programar_son_los_cuatro_tests_dados():
    casos = B.casos_programar()
    assert [c["caso"] for c in casos] == ["T347", "T348", "T421", "T422"]
    assert all("def aplicar" in c["prompt"] and "import auto_etiquetado_router" in c["prompt"] for c in casos)


def test_ningun_prompt_lleva_material_de_memoria_ni_del_vault():
    """Programar solo envia el codigo del repo y el test dado (que nombran la ruta memoria/, sin su contenido)."""
    assert not B.OBJETIVO.startswith(("memoria", "registros", "canal"))
    for rol, fn in B.CASOS.items():
        for c in fn():
            assert "contexto/proyectos" not in c["prompt"] and '"tareas": [' not in c["prompt"], (rol, c["caso"])
            if rol != "programar":
                assert "memoria/" not in c["prompt"], (rol, c["caso"])


# ---------------------------------------------------------------- revisar, redactar, triaje
def test_evaluar_revisar():
    bug = next(c for c in B.CASOS_REVISAR if c["caso"] == "clave_en_log")
    limpio = next(c for c in B.CASOS_REVISAR if c["caso"] == "renombrar_limpio")
    assert B.evaluar_revisar(bug, "VEREDICTO: RECHAZAR\nMOTIVO: filtra la clave de la API en el detalle")["nota"] == 1
    assert B.evaluar_revisar(bug, "VEREDICTO: RECHAZAR\nMOTIVO: no me gusta")["nota"] == 0.5
    assert B.evaluar_revisar(bug, "**VEREDICTO:** APROBAR")["nota"] == 0
    assert B.evaluar_revisar(limpio, "VEREDICTO: APROBAR\nMOTIVO: solo renombra")["nota"] == 1
    assert B.evaluar_revisar(limpio, "todo bien")["nota"] == 0


def test_evaluar_redactar_detecta_cifras_inventadas_y_secciones():
    caso = B.CASOS_REDACTAR[2]
    bueno = ("## Que pasa\nGroq ha devuelto el error 429 porque se agoto la cuota y NEXO paso el trabajo a otro "
             "proveedor.\n## Que hacer\nNo hace falta hacer nada; si se repite a diario, repartir los turnos.")
    assert B.evaluar_redactar(caso, bueno)["nota"] == 1.0
    malo = bueno.replace("429", "429 a las 23:00")
    assert "inventadas" in B.evaluar_redactar(caso, malo)["motivo"]
    assert B.evaluar_redactar(caso, "Groq dio 429 y no pasa nada de la cuota")["nota"] < 1


def test_evaluar_triaje():
    perfecto = "\n".join(f"{i}: {c}" for i, (_, c) in enumerate(B.CASOS_TRIAJE, 1))
    assert B.evaluar_triaje({}, perfecto)["nota"] == 1.0
    n = len(B.CASOS_TRIAJE)
    uno_mal = perfecto.splitlines()
    uno_mal[4] = "5: codigo"           # el 5 es sospechosa
    assert B.evaluar_triaje({}, "\n".join(uno_mal))["nota"] == round((n - 1) / n, 3)
    assert B.evaluar_triaje({}, perfecto + "\nEspero que te sirva")["nota"] == 0.9     # v2: lineas de mas restan


# ---------------------------------------------------------------- pasada, puntuacion y asignacion
def test_correr_respeta_tope_salta_ollama_en_programar_y_abandona_con_429(monkeypatch):
    monkeypatch.setitem(B.TOPE_LLAMADAS, "openrouter", 2)
    llamadas = []

    def llamar(p, m, prompt):
        llamadas.append((p, m))
        if m == "cuota":
            return {"texto": "", "segundos": 1, "error": "HTTP 429", "codigo": 429}
        return {"texto": "VEREDICTO: APROBAR", "segundos": 1, "error": "", "codigo": 200}
    monkeypatch.setattr(B, "descargar_ollama", lambda m: None)
    filas = B.correr([("groq", "cuota"), ("openrouter", "a:free"), ("ollama", "q:7b")],
                     roles=("programar", "revisar"), llamar_fn=llamar, dormir=lambda s: None, progreso=lambda s: None,
                     evaluar={"programar": lambda c, t: {"nota": 0.0}, "revisar": B.evaluar_revisar})
    assert llamadas.count(("groq", "cuota")) == 2                    # 429: un reintento y deja el modelo
    assert llamadas.count(("openrouter", "a:free")) == 2               # tope por proveedor
    assert not any(f["rol"] == "programar" for f in filas if f["proveedor"] == "ollama")
    assert len(B.leer_resultados()) == len(filas)


def _fila(modelo, rol, caso, nota, seg=5, error=""):
    return {"version": B.VERSION_BANCO, "proveedor": "groq" if modelo != "otro" else "nvidia", "modelo": modelo,
            "rol": rol, "caso": caso, "nota": nota, "segundos": seg, "error": error, "codigo": 200}


def test_puntuar_y_asignar_mejor_y_reserva_de_otro_proveedor():
    filas = [_fila("a", "revisar", c, 1.0) for c in "xyz"] + [_fila("b", "revisar", c, 0.9) for c in "xyz"] + \
            [_fila("otro", "revisar", c, 0.8) for c in "xyz"] + [_fila("malo", "revisar", c, 0.2) for c in "xyz"]
    tabla = B.puntuar(filas)
    a = B.asignar(tabla)["revisar"]
    assert a["mejor"] == "groq:a" and a["reserva"] == "nvidia:otro"
    B.guardar_roles(B.asignar(tabla))
    assert B.modelo_para("revisar") == ("groq", "a") and B.modelo_para("revisar", reserva=True) == ("nvidia", "otro")
    assert B.modelo_para("inexistente") is None


def test_asignar_sin_minimo_de_calidad_no_asigna():
    tabla = B.puntuar([_fila("a", "programar", "T347", 0.25), _fila("a", "programar", "T348", 0.0)])
    assert B.asignar(tabla)["programar"]["mejor"] is None


def test_cada_caso_vale_la_media_de_sus_repeticiones_y_las_omitidas_no_cuentan():
    filas = [_fila("a", "triaje", "lote8", 0.0, error="timeout"), _fila("a", "triaje", "lote8", 1.0),
             _fila("a", "triaje", "lote8", 0.0, error="RAM libre < 6.0 GB")]
    v = B.puntuar(filas)["triaje"]["groq:a"]
    assert v["calidad"] == 0.5 and v["exito"] == 0.5 and v["pasadas"] == 2


def test_candidatos_con_cuota_escasa_primero_los_unicos():
    inv = {"proveedores": {"nvidia": [{"id": "nvidia/x"}], "openrouter": [{"id": "nvidia/x:free"}, {"id": "y/z:free"}]}}
    assert B._candidatos(inv, None, None, "openrouter") == [("openrouter", "y/z:free"), ("openrouter", "nvidia/x:free")]
    json.dumps(inv)


def test_dos_timeouts_seguidos_dejan_el_modelo():
    llamadas = []

    def llamar(p, m, prompt):
        llamadas.append(m)
        return {"texto": "", "segundos": 150, "error": "timeout", "codigo": "timeout"}
    B.correr([("nvidia", "lento")], roles=("revisar",), llamar_fn=llamar, dormir=lambda s: None,
             progreso=lambda s: None)
    assert llamadas == ["lento", "lento"]


def test_informe_lista_asignacion_y_tablas():
    filas = [_fila("a", "revisar", c, 1.0) for c in "xy"]
    tabla = B.puntuar(filas)
    md = B.informe(tabla, B.asignar(tabla), {"cuando": "hoy", "proveedores": {"groq": [{"id": "a"}]}})
    assert "| revisar | groq:a |" in md and "| programar | — (sin datos) |" in md and "groq 1" in md


def test_a_igualdad_de_puntos_gana_el_mas_rapido():
    filas = [_fila("lento", "triaje", "x", 1.0, seg=10), _fila("rapido", "triaje", "x", 1.0, seg=9)]
    assert B.asignar(B.puntuar(filas))["triaje"]["mejor"] == "groq:rapido"


# ---------------------------------------------------------------- 11/10: NEXO elige solo, con evidencia clara
def _filas_rol(rol, notas: dict, pasadas=2, casos="xy"):
    return [dict(_fila(m, rol, c, n), proveedor=m.split(":")[0], modelo=m.split(":")[1])
            for m, n in notas.items() for c in casos for _ in range(pasadas)]


def test_evidencia_clara_solo_si_los_casos_distinguen_y_se_repitieron():
    claro = B.asignar(B.puntuar(_filas_rol("programar", {"groq:q": 1.0, "nvidia:n": 0.95, "groq:m": 0.5})))
    assert claro["programar"]["aplicado"] is True
    empate = B.asignar(B.puntuar(_filas_rol("revisar", {"groq:a": 1.0, "nvidia:b": 1.0, "groq:c": 1.0})))
    assert empate["revisar"]["aplicado"] is False and "empatados" in empate["revisar"]["motivo"]
    una = B.asignar(B.puntuar(_filas_rol("triaje", {"groq:a": 1.0, "nvidia:b": 0.5}, pasadas=1)))
    assert una["triaje"]["aplicado"] is False and "pasadas" in una["triaje"]["motivo"]


def test_ordenar_pone_delante_mejor_y_reserva_solo_si_esta_aplicado():
    B.guardar_roles(B.asignar(B.puntuar(_filas_rol("programar", {"groq:q": 1.0, "nvidia:n": 0.95, "groq:m": 0.5}))))
    assert B.aplicado("programar")
    assert B.ordenar("programar", ["groq:m", "nvidia:n", "groq:q"], str) == ["groq:q", "nvidia:n", "groq:m"]
    assert B.ordenar("revisar", ["groq:m", "groq:q"], str) == ["groq:m", "groq:q"]     # sin asignar: orden a mano


def test_los_consumidores_leen_roles_json():
    from nucleo import implementador as I, tribunal
    B.guardar_roles({"programar": {"mejor": "groq:qwen/qwen3.8-27b", "reserva": "gemini_api:gemini-3.5-flash-lite",
                                   "aplicado": True},
                     "revisar": {"mejor": f"nvidia:{tribunal._NVIDIA.modelo}", "reserva": None,
                                 "aplicado": True}})
    assert [I.clave_banco(m) for m in I.modelos_programar()][:2] == ["groq:qwen/qwen3.8-27b",
                                                                     "gemini_api:gemini-3.5-flash-lite"]
    ordenados = B.ordenar("revisar", tribunal.TRIBUNAL, tribunal.clave_banco)
    assert ordenados[0].id == "nvidia:nemotron-3-ultra"      # T1039: el primero de config nvidia.modelos
    B.guardar_roles({"programar": {"mejor": "groq:qwen/qwen3.8-27b", "aplicado": False}})
    assert I.modelos_programar() == list(I.MODELOS)          # sin evidencia clara: el orden escrito a mano


def test_casos_endurecidos_distinguen():
    assert len(B.CASOS_REVISAR) >= 10 and sum(c["esperado"] == "APROBAR" for c in B.CASOS_REVISAR) >= 4
    assert len(B.CASOS_TRIAJE) == 30 and sum(c == "sospechosa" for _, c in B.CASOS_TRIAJE) == 7
    assert len(B.CASOS_REVISAR) == 23 and sum(c["esperado"] == "APROBAR" for c in B.CASOS_REVISAR) == 10
    vinetas = next(c for c in B.CASOS_REDACTAR if c["caso"] == "tres_vinetas")
    bueno = "## Pasos\n- Abrir la pagina /turnos de la web.\n- Marcar la casilla activo.\n- Esperar 2 minutos a que lo recoja."
    assert B.evaluar_redactar(vinetas, bueno)["nota"] == 1.0
    assert "vinetas" in B.evaluar_redactar(vinetas, bueno + "\n- Avisar a Claude.")["motivo"]
    ficha = next(c for c in B.CASOS_REDACTAR if c["caso"] == "cinco_datos_60")
    assert "prohibido" in B.evaluar_redactar(ficha, "## Resumen\nSe envia por Telegram el 11/10.\n## Datos\n3 20 8 4096")["motivo"]
    assert B.VERSION_ROL == {"programar": 1, "revisar": 5, "redactar": 2, "triaje": 5}   # v3-v5 (12/10): casos dificiles


def test_turno_diario_mide_poco_reasigna_y_avisa_si_cambia_el_mejor(monkeypatch):
    from nucleo import avisos
    vistos = []
    monkeypatch.setattr(avisos, "emitir", lambda *a, **k: vistos.append(a[1]))
    filas = _filas_rol("triaje", {"groq:a": 1.0, "nvidia:b": 0.9, "groq:c": 0.5, "nvidia:d": 0.4})
    for f in filas:
        f["version"] = B.VERSION_ROL["triaje"]
        B._anotar(f)
    B.guardar_roles({"triaje": {"mejor": "nvidia:b", "aplicado": True}})
    llamadas = []

    def correr_falso(cand, roles, progreso, cortar=None):
        llamadas.append((tuple(cand), roles))
        return []
    r = B.turno_diario(roles=("triaje",), por_rol=2, nuevos=0, correr_fn=correr_falso, inv={"proveedores": {}})
    assert llamadas == [((("groq", "a"), ("nvidia", "b")), ("triaje",))]           # poca cuota: los 2 mejores
    assert r["cambios"][0]["despues"] == "groq:a" and B.aplicado("triaje")
    assert vistos and "triaje" in vistos[0]
    assert B.hecho_hoy() and B.candidatas_diario() == 0                            # una vez al dia


def test_la_plantilla_modelos_esta_conectada():
    from nucleo import plantillas_turno, turnos
    assert "modelos" in turnos.PLANTILLAS and not turnos.PLANTILLAS["modelos"]["solo_lectura"]
    assert "modelos" in plantillas_turno.por_que_nada({"plantilla": "modelos", "tareas": []})
    assert 'ctx["plantilla"] == "modelos"' in (B.RAIZ / "turno_nexo.py").read_text(encoding="utf-8")
