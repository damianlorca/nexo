# -*- coding: utf-8 -*-
"""extremidades/qwen.py y extremidades/triaje.py sin Ollama ni LM Studio.

prueba_qwen.py y prueba_triaje.py necesitan un runtime local vivo (en Linux fallan con
APIConnectionError). Aqui el runtime se sustituye por dobles: se prueba la logica propia
(reintento por 'length', limpieza de <think>, eleccion de categoria, fallback a LM Studio,
peticion nativa a Ollama, triaje sin marcar mensajes).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from extremidades import qwen, triaje


# ------------------------------------------------------------------ qwen

def test_sin_razonamiento_quita_think_cerrado_y_a_medias():
    assert qwen._sin_razonamiento("<think>bla\nbla</think>\n hola ") == "hola"
    assert qwen._sin_razonamiento("<THINK>x</THINK>a<think>sin cerrar") == "a"
    assert qwen._sin_razonamiento("sin nada") == "sin nada"


@pytest.mark.parametrize("dicho, esperado", [
    ("no urgente", "no urgente"),
    ("No urgente.", "no urgente"),
    ("urgente", "urgente"),
    ("No urgente - el plazo ya paso", "no urgente"),
    ("Diria que es no urgente", "no urgente"),
    ("", None),
    ("ninguna", None),
])
def test_elegir_categoria_no_invierte_urgente(dicho, esperado):
    assert qwen._elegir_categoria(dicho, ["urgente", "no urgente"]) == esperado


def test_elegir_categoria_respeta_limites_de_palabra():
    assert qwen._elegir_categoria("es inutil", ["util", "inutil"]) == "inutil"
    assert qwen._elegir_categoria("totalmente inutil", ["util"]) is None


def test_clasificar_sin_categorias_lanza():
    with pytest.raises(ValueError):
        qwen.clasificar("x", [])


def test_clasificar_devuelve_por_defecto_si_no_reconoce(monkeypatch):
    monkeypatch.setattr(qwen, "pedir", lambda *a, **k: "no se")
    assert qwen.clasificar("x", ["a", "b"], por_defecto="?") == "?"


@pytest.fixture
def cliente_falso(monkeypatch):
    """_cliente() devuelve un cliente de pega (via LM Studio salvo que se cambie la URL)."""
    cli = SimpleNamespace(base_url="http://localhost:1234/v1/", timeout=5.0)
    monkeypatch.setattr(qwen, "_cliente", lambda timeout=0: (cli, False))
    monkeypatch.setattr(qwen, "valor", lambda ruta, defecto=None: defecto)
    return cli


def test_pedir_sube_el_presupuesto_al_minimo(cliente_falso, monkeypatch):
    vistos = []
    monkeypatch.setattr(qwen, "_una_vuelta", lambda c, m, t, p: (vistos.append(p) or ("ok", "stop")))
    assert qwen.pedir("haz", "x", max_tokens=20) == "ok"
    assert vistos == [qwen.MINIMO_TOKENS]


def test_pedir_reintenta_con_triple_si_se_queda_pensando(cliente_falso, monkeypatch):
    respuestas = [("", "length"), ("por fin", "stop")]
    vistos = []

    def vuelta(c, m, t, p):
        vistos.append(p)
        return respuestas.pop(0)

    monkeypatch.setattr(qwen, "_una_vuelta", vuelta)
    assert qwen.pedir("haz", max_tokens=1000) == "por fin"
    assert vistos == [1000, 3000]


def test_pedir_no_pasa_del_techo(cliente_falso, monkeypatch):
    vistos = []
    monkeypatch.setattr(qwen, "_una_vuelta", lambda c, m, t, p: (vistos.append(p) or ("", "length")))
    assert qwen.pedir("haz", max_tokens=qwen.TECHO_TOKENS) == ""
    assert vistos == [qwen.TECHO_TOKENS]


def test_pedir_usa_el_modelo_de_reserva_si_va_por_lm_studio(monkeypatch):
    cli = SimpleNamespace(base_url="http://localhost:1234/v1/", timeout=5.0)
    monkeypatch.setattr(qwen, "_cliente", lambda timeout=0: (cli, True))
    claves = []
    monkeypatch.setattr(qwen, "valor", lambda ruta, defecto=None: claves.append(ruta) or defecto)
    monkeypatch.setattr(qwen, "_una_vuelta", lambda c, m, t, p: ("ok", "stop"))
    qwen.pedir("x", criterio=True)
    assert "qwen.modelo_criterio_reserva" in claves


def test_cliente_cae_a_lm_studio_si_ollama_no_responde(monkeypatch):
    abiertos = []

    class Falso:
        def __init__(self, url):
            self.url = url
            self.models = SimpleNamespace(list=self._listar)

        def _listar(self):
            if "11434" in self.url:
                raise ConnectionError("ollama parado")
            return []

    monkeypatch.setattr(qwen, "_abrir", lambda url, t: abiertos.append(url) or Falso(url))
    monkeypatch.setattr(qwen, "valor", lambda ruta, defecto=None: defecto)
    cli, reserva = qwen._cliente()
    assert reserva is True and "1234" in cli.url


def test_una_vuelta_por_openai_compatible(monkeypatch):
    llamadas = []

    def crear(**kw):
        llamadas.append(kw)
        msg = SimpleNamespace(content="<think>x</think>hola")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])

    cli = SimpleNamespace(base_url="http://localhost:1234/v1/",
                          chat=SimpleNamespace(completions=SimpleNamespace(create=crear)))
    assert qwen._una_vuelta(cli, "m", "texto", 700) == ("hola", "stop")
    assert llamadas[0]["max_tokens"] == 700 and llamadas[0]["messages"][0]["content"] == qwen.INSTRUCCION


@pytest.fixture
def ollama_nativo(monkeypatch):
    """Captura el cuerpo que _una_vuelta manda a /api/chat de Ollama."""
    import httpx
    enviados = []

    def post(url, json=None, timeout=None):
        enviados.append((url, json))
        return SimpleNamespace(json=lambda: {"message": {"content": "vale"}, "done_reason": "length"})

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(qwen, "valor", lambda ruta, defecto=None: defecto)
    cli = SimpleNamespace(base_url="http://localhost:11434/v1/", timeout=5.0)
    return cli, enviados


def test_una_vuelta_con_ollama_usa_api_nativa(ollama_nativo):
    cli, enviados = ollama_nativo
    assert qwen._una_vuelta(cli, "qwen3:4b", "hola", 600) == ("vale", "length")
    url, cuerpo = enviados[0]
    assert url == "http://localhost:11434/api/chat"
    assert cuerpo["options"]["num_predict"] == 600 and cuerpo["stream"] is False


# B2 de N02 (arreglado): antes el defecto era 8192 y config.toml no lo fijaba.
def test_num_ctx_por_defecto_respeta_claude_md(ollama_nativo):
    cli, enviados = ollama_nativo
    qwen._una_vuelta(cli, "qwen3:4b", "hola", 600)
    assert enviados[0][1]["options"]["num_ctx"] <= 4096


def test_config_toml_fija_num_ctx_4096():
    import tomllib
    from nucleo.config import ARCHIVO_CONFIG
    with ARCHIVO_CONFIG.open("rb") as f:
        assert tomllib.load(f)["qwen"]["num_ctx"] == 4096


def test_una_vuelta_ollama_con_error(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: SimpleNamespace(json=lambda: {"error": "model not found"}))
    monkeypatch.setattr(qwen, "valor", lambda ruta, defecto=None: defecto)
    cli = SimpleNamespace(base_url="http://localhost:11434/v1", timeout=5.0)
    with pytest.raises(RuntimeError, match="model not found"):
        qwen._una_vuelta(cli, "m", "x", 600)


def test_lote_convierte_excepciones_en_texto(monkeypatch):
    def pedir(instr, texto, criterio=False):
        if texto == "malo":
            raise RuntimeError("se cayo")
        return texto.upper()

    monkeypatch.setattr(qwen, "pedir", pedir)
    assert qwen.lote("x", ["a", "malo", "b"]) == ["A", "ERROR: se cayo", "B"]


# ---------------------------------------------------------------- triaje

@pytest.fixture
def buzon_falso(tmp_path, monkeypatch):
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    monkeypatch.setattr(triaje, "ENTRADA", entrada)
    monkeypatch.setattr(triaje, "INFORME", tmp_path / "triaje.json")
    return entrada


def test_triar_junta_categoria_urgencia_y_resumen(monkeypatch):
    respuestas = {tuple(triaje.CATEGORIAS): "tarea", tuple(triaje.URGENCIAS): "urgente"}
    monkeypatch.setattr(triaje.qwen, "clasificar", lambda t, cats, por_defecto="": respuestas[tuple(cats)])
    monkeypatch.setattr(triaje.qwen, "pedir", lambda *a, **k: " Pide comprar pan\ny leche " + "x" * 300)
    r = triaje.triar("compra pan")
    assert r["categoria"] == "tarea" and r["urgencia"] == "urgente"
    assert "\n" not in r["resumen"] and len(r["resumen"]) == 200


def test_pendientes_lee_libres_ordenados_y_salta_los_rotos(buzon_falso):
    (buzon_falso / "libre_2.json").write_text(json.dumps({"texto": "dos", "hora": "h2"}), encoding="utf-8")
    (buzon_falso / "libre_1.json").write_text(json.dumps({"texto": "uno", "hora": "h1"}), encoding="utf-8")
    (buzon_falso / "libre_3.json").write_text("{roto", encoding="utf-8")
    (buzon_falso / "Q1.json").write_text("{}", encoding="utf-8")  # respuesta a pregunta: no es libre
    assert [m["texto"] for m in triaje.mensajes_pendientes()] == ["uno", "dos"]


def test_pendientes_sin_carpeta(tmp_path, monkeypatch):
    monkeypatch.setattr(triaje, "ENTRADA", tmp_path / "no_existe")
    assert triaje.mensajes_pendientes() == []


def test_triar_pendientes_no_marca_nada_y_aisla_errores(buzon_falso, monkeypatch):
    (buzon_falso / "libre_1.json").write_text(json.dumps({"texto": "ok"}), encoding="utf-8")
    (buzon_falso / "libre_2.json").write_text(json.dumps({"texto": "boom"}), encoding="utf-8")

    def triar(texto):
        if texto == "boom":
            raise RuntimeError("qwen caido")
        return {"categoria": "dato"}

    monkeypatch.setattr(triaje, "triar", triar)
    inf = triaje.triar_pendientes(guardar=True)
    assert [m.get("categoria") or m.get("error") for m in inf["mensajes"]] == ["dato", "qwen caido"]
    assert sorted(p.name for p in buzon_falso.iterdir()) == ["libre_1.json", "libre_2.json"]
    assert json.loads(triaje.INFORME.read_text(encoding="utf-8"))["mensajes"][1]["error"] == "qwen caido"


def test_triar_pendientes_sin_guardar_no_escribe(buzon_falso, monkeypatch):
    monkeypatch.setattr(triaje, "triar", lambda t: {})
    triaje.triar_pendientes(guardar=False)
    assert not triaje.INFORME.exists()
