# -*- coding: utf-8 -*-
"""T859 (piloto de reels): todo con dobles. Sin red, sin yt-dlp, sin ffmpeg, sin whisper, sin Ollama ni Gemini."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from extremidades import reels


@pytest.fixture
def carpeta(tmp_path, monkeypatch):
    monkeypatch.setattr(reels, "CARPETA", tmp_path / "reels")
    monkeypatch.setattr(reels, "CONFIG", tmp_path / "reels" / "config.json")   # nunca el config.json real
    return tmp_path / "reels"


@pytest.fixture
def fotos(tmp_path):
    lista = []
    for i in range(3):
        f = tmp_path / f"f{i:02d}.jpg"
        f.write_bytes(b"\xff\xd8jpg" + bytes([i]))
        lista.append(f)
    return lista


def test_descarga_sin_cookies_ni_navegador(tmp_path):
    vistas = {}

    class YDL:
        def __init__(self, opts):
            vistas.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download):
            (tmp_path / "abc.mp4").write_bytes(b"v")
            return {"id": "abc", "ext": "mp4", "title": "t", "duration": 30, "upload_date": "20261001"}

        def prepare_filename(self, info):
            return str(tmp_path / "abc.mp4")
    r = reels.descargar("https://www.instagram.com/reel/abc/", tmp_path, ydl_cls=YDL)
    assert r["video"].name == "abc.mp4" and r["duracion"] == 30
    assert vistas["cookiefile"] is None and vistas["cookiesfrombrowser"] is None and vistas["noplaylist"]


def test_descarga_que_falla_es_no_descargable(tmp_path):
    class Roto:
        def __init__(self, opts):
            pass

        def __enter__(self):
            raise RuntimeError("login required")

        def __exit__(self, *a):
            return False
    with pytest.raises(reels.NoDescargable, match="login required"):
        reels.descargar("u", tmp_path, ydl_cls=Roto)


def test_fotogramas_por_escena_y_si_no_hay_cortes_cada_3_s(tmp_path):
    ordenes = []
    carpeta = tmp_path / "fg"

    def correr(args, **k):
        ordenes.append(args)
        n = 1 if len(ordenes) == 1 else 5            # 1.a pasada: un solo fotograma (sin cortes)
        for i in range(n):
            (carpeta / f"f{i + 1:02d}.jpg").write_bytes(b"x")
    fotos = reels.fotogramas(tmp_path / "v.mp4", carpeta, correr=correr)
    assert "gt(scene" in " ".join(ordenes[0]) and "eq(n" in " ".join(ordenes[0])
    assert str(reels.MAX_FOTOGRAMAS) in ordenes[0]
    assert "-fps_mode" in ordenes[0] and "-vsync" not in ordenes[0]     # ffmpeg 9 ya no tiene -vsync (piloto 12/10)
    assert "fps=1/3" in " ".join(ordenes[1]) and len(fotos) == 5


def test_transcribir_cpu_int8():
    vistos = {}

    class Modelo:
        def __init__(self, nombre, device, compute_type):
            vistos.update(nombre=nombre, device=device, compute_type=compute_type)

        def transcribe(self, ruta, **k):
            segs = [SimpleNamespace(start=0.0, end=1.24, text=" Hola "), SimpleNamespace(start=1.3, end=2, text="repo")]
            return iter(segs), SimpleNamespace(language="es")
    r = reels.transcribir("v.mp4", modelo_cls=Modelo)
    assert vistos == {"nombre": "small", "device": "cpu", "compute_type": "int8"}
    assert r["texto"] == "Hola repo" and r["idioma"] == "es" and r["segmentos"][0]["fin"] == 1.2


def test_vision_local_acotada_y_descarga_el_modelo_al_final(fotos):
    cuerpos = []
    r = reels.pantalla_local(fotos, post=lambda url, c, *a, **k: cuerpos.append((url, c)) or {"response": " owner/repo "})
    assert r == ["owner/repo"] * 3
    assert all(u.endswith("/api/generate") for u, _ in cuerpos)
    assert all(c["options"]["num_ctx"] == 4096 and c["options"]["num_predict"] <= 512 for _, c in cuerpos)
    assert [c["keep_alive"] for _, c in cuerpos] == ["5m", "5m", 0]
    assert all(len(c["images"]) == 1 for _, c in cuerpos)


def test_vision_local_nunca_mas_de_8b(fotos):
    for modelo in ("qwen2.5vl:32b", "llava", "qwen2.5vl:72b"):
        with pytest.raises(ValueError, match="8B"):
            reels.pantalla_local(fotos, modelo=modelo, post=lambda *a, **k: pytest.fail("pidio"))


def test_gemini_solo_lleva_los_fotogramas_y_reparte_por_imagen(fotos, monkeypatch):
    monkeypatch.setattr(reels, "valor", lambda r, d=None: "CLAVE-FALSA" if r == "gemini.api_key" else d)
    vistos = {}

    def post(url, cuerpo, cab=None, **k):
        vistos.update(url=url, cuerpo=cuerpo, cab=cab)
        return {"candidates": [{"content": {"parts": [{"text": "1: github.com/a/b\n2: VACIO\n3: Comenta REPO\ny mas"}]}}]}
    r = reels.pantalla_gemini(fotos, post=post)
    assert r == ["github.com/a/b", "VACIO", "Comenta REPO y mas"]
    partes = vistos["cuerpo"]["contents"][0]["parts"]
    assert [list(p) for p in partes] == [["text"], ["inline_data"], ["inline_data"], ["inline_data"]]
    assert base64.b64decode(partes[1]["inline_data"]["data"]) == fotos[0].read_bytes()
    assert "CLAVE-FALSA" not in vistos["url"] and vistos["cab"] == {"x-goog-api-key": "CLAVE-FALSA"}


def test_gemini_cortada_por_tope_no_pasa_por_vacia(fotos, monkeypatch):
    """Piloto 12/10: con 12 fotogramas el pensamiento se comia el tope y todo salia vacio sin error."""
    monkeypatch.setattr(reels, "valor", lambda r, d=None: "CLAVE-FALSA" if r == "gemini.api_key" else d)
    corta = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "1: github.com/"}]}}]}
    with pytest.raises(RuntimeError, match="MAX_TOKENS"):
        reels.pantalla_gemini(fotos, post=lambda *a, **k: corta)
    assert reels.cuerpo_gemini(fotos)["generationConfig"]["maxOutputTokens"] >= 8192


def test_gemini_saturado_prueba_el_siguiente_modelo(fotos, monkeypatch):
    import urllib.error
    monkeypatch.setattr(reels, "valor", lambda r, d=None: "CLAVE-FALSA" if r == "gemini.api_key" else d)
    urls = []

    def post(url, cuerpo, cab=None, **k):
        urls.append(url)
        if "3.6" in url:
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)
        return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "1: a\n2: b\n3: c"}]}}]}
    textos, modelo = reels.pantalla_gemini_respaldo(fotos, post=post)
    assert textos == ["a", "b", "c"] and modelo == "gemini-3.7-flash" and len(urls) == 2


def test_releer_gemini_actualiza_solo_esa_lectura(carpeta, fotos, monkeypatch):
    monkeypatch.setattr(reels, "valor", lambda r, d=None: "CLAVE-FALSA" if r == "gemini.api_key" else d)
    fg = carpeta / "media" / "R1" / "fotogramas"
    fg.mkdir(parents=True)
    for f in fotos:
        (fg / f.name).write_bytes(f.read_bytes())
    reels.guardar_bruto("R1", {"pie": "", "transcripcion": {"texto": ""}, "fotogramas": [f.name for f in fotos],
                               "pantalla": {"local": {"modelo": "m", "textos": ["github.com/a/b", "", ""]},
                                            "gemini": {"modelo": "g", "textos": ["", "", ""]}},
                               "errores": {}, "tiempos_s": {"pantalla_local": 9.0}})
    ok = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "1: github.com/a/b\n2: x\n3: y"}]}}]}
    d = reels.releer_gemini("R1", post=lambda *a, **k: ok)
    assert d["pantalla"]["gemini"]["textos"][0] == "github.com/a/b" and d["citas_por_lector"]["gemini"]["repos"] == ["a/b"]
    assert d["pantalla"]["local"]["textos"][0] == "github.com/a/b" and d["tiempos_s"]["pantalla_local"] == 9.0
    guardado = json.loads((carpeta / "R1.json").read_text(encoding="utf-8"))
    assert guardado["anteriores"][0]["pantalla"]["gemini"]["textos"] == ["", "", ""]   # lo de antes no se pierde


def test_citas_repos_urls_y_llamadas_a_la_accion():
    c = reels.extraer_citas("Mira https://github.com/iamlukethedev/hermes3d.", "Comment “DECODE” and I'll send it",
                            "openai/codex en pantalla, 24/7 y 1/2", "web: https://recordly.app")
    assert c["repos"] == ["iamlukethedev/hermes3d"]
    assert "openai/codex" in c["repos_posibles"] and "24/7" not in c["repos_posibles"]
    assert "https://recordly.app" in c["urls"] and not any("github.com" in u for u in c["urls"])
    assert c["llamadas_accion"] == ["DECODE"]


def test_capa_bruta_nunca_se_borra(carpeta):
    reels.guardar_bruto("X1", {"estado": "no_descargable"})
    reels.guardar_bruto("X1", {"estado": "analizado", "transcripcion": {"texto": "hola"}})
    d = json.loads((carpeta / "X1.json").read_text(encoding="utf-8"))
    assert d["estado"] == "analizado" and d["anteriores"][0]["estado"] == "no_descargable"
    reels.guardar_bruto("X1", {"estado": "analizado"})
    d = json.loads((carpeta / "X1.json").read_text(encoding="utf-8"))
    assert [a["estado"] for a in d["anteriores"]] == ["no_descargable", "analizado"]


def test_analizar_no_descargable_guarda_el_pie_y_su_estado(carpeta, tmp_path, monkeypatch):
    col = tmp_path / "col.json"
    col.write_text(json.dumps({"reels": [{"codigo": "C1", "url": "u", "autor": "a", "pie": "Comenta GRATIS",
                                          "colecciones": ["ai"], "categorias_preliminares": ["nexo"]}]}),
                   encoding="utf-8")

    def no(*a, **k):
        raise reels.NoDescargable("privado")
    monkeypatch.setattr(reels, "descargar", no)
    d = reels.analizar("C1", coleccion=col)
    assert d["estado"] == "no_descargable" and "privado" in d["errores"]["descarga"]
    assert d["citas"]["llamadas_accion"] == ["GRATIS"]
    assert (carpeta / "C1.json").exists()


def test_los_datos_privados_no_van_a_git():
    from nucleo.config import RAIZ
    gi = (RAIZ / ".gitignore").read_text(encoding="utf-8")
    assert "/memoria/perfil_privado/" in gi and ".venv-reels/" in gi
    assert reels.CARPETA.relative_to(RAIZ).as_posix().startswith("memoria/perfil_privado/")


# ------------------------------------------------------------------ bloque 6: lectura densa
def test_fotogramas_densos_1_por_segundo_sin_repetidos_y_con_su_segundo(tmp_path):
    carpeta = tmp_path / "fg"
    ordenes = []

    def correr(args, **k):
        ordenes.append(args)
        for n in (0, 3, 7):                        # mpdecimate dejo los fotogramas de los segundos 0, 3 y 7
            (carpeta / f"d{n:05d}.jpg").write_bytes(b"x")
    carpeta.mkdir()
    (carpeta / "d00099.jpg").write_bytes(b"viejo")  # de una pasada anterior: se sustituye
    r = reels.fotogramas_densos(tmp_path / "v.mp4", carpeta, correr=correr)
    orden = " ".join(ordenes[0])
    assert "fps=1" in orden and "mpdecimate" in orden and "-frame_pts" in orden and "-fps_mode" in orden
    assert [x["t"] for x in r] == [0.0, 3.0, 7.0] and not (carpeta / "d00099.jpg").exists()


def test_relectura_a_2_por_segundo_desde_un_tramo(tmp_path):
    carpeta = tmp_path / "fg"

    def correr(args, **k):
        (carpeta / "r00004.jpg").write_bytes(b"x")
    r = reels.fotogramas_densos(tmp_path / "v.mp4", carpeta, fps=2, prefijo="r", desde=10, correr=correr)
    assert r[0]["t"] == 12.0                           # 10 s + 4 medios segundos


def test_recortes_ampliados_tres_franjas_con_solape(tmp_path):
    ordenes = []
    r = reels.recortes(tmp_path / "d00001.jpg", tmp_path / "rec", correr=lambda a, **k: ordenes.append(a))
    assert [p.name for p in r] == ["d00001_r1.jpg", "d00001_r2.jpg", "d00001_r3.jpg"]
    assert all("scale=iw*2" in " ".join(o) for o in ordenes)


def test_gemini_bloques_conserva_las_lineas_de_cada_imagen(fotos, monkeypatch):
    monkeypatch.setattr(reels, "valor", lambda r, d=None: "CLAVE-FALSA" if r == "gemini.api_key" else d)
    resp = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": "### 1\n20 repos\n1.rtk\n2.caveman\n### 2\nVACIO\n### 3\nmorluto / rea"}]}}]}
    textos, modelo = reels.gemini_bloques(fotos, post=lambda *a, **k: resp)
    assert textos == ["20 repos\n1.rtk\n2.caveman", "VACIO", "morluto / rea"] and modelo == reels.MODELOS_GEMINI[0]


def test_cascada_ocr_primero_gemini_solo_para_lo_nitido_que_el_ocr_no_lee(fotos):
    """Bloque 6b: el OCR local lee todo; Gemini solo ve los fotogramas NITIDOS sin texto (los borrosos sin texto no
    gastan cuota); si nadie lee un nitido, queda 'revisar' (nunca vacio en silencio)."""
    ocr_vio = []

    def ocr(fs):
        ocr_vio.extend(f.name for f in fs)
        return ["texto uno", "", ""]
    gemini_vio = []

    def gemini(trozo):
        gemini_vio.extend(f.name for f in trozo)
        return [""] * len(trozo), "gemini-x"
    borrosidad = {fotos[1].name: 14.0, fotos[2].name: 4.0}      # el 2.o borroso, el 3.o nitido
    r = reels.leer_fotogramas(fotos, gemini=gemini, ocr=ocr, medir=lambda f: borrosidad.get(f.name))
    assert ocr_vio == [f.name for f in fotos] and gemini_vio == [fotos[2].name]
    assert [x["estado"] for x in r["lecturas"]] == ["texto", "sin_texto", "revisar"]
    assert r["lecturas"][0]["lector"] == "ocr"


def test_cascada_lo_que_lee_gemini_se_marca_y_si_cae_se_anota(fotos):
    r = reels.leer_fotogramas(fotos, gemini=lambda t: (["rea"] * len(t), "gemini-x"), ocr=lambda fs: [""] * len(fs),
                              medir=lambda f: 3.0)
    assert [x["lector"] for x in r["lecturas"]] == ["gemini:gemini-x"] * 3
    def cae(trozo):
        raise RuntimeError("503")
    r = reels.leer_fotogramas(fotos, gemini=cae, ocr=lambda fs: [""] * len(fs), medir=lambda f: 14.0)
    assert [x["estado"] for x in r["lecturas"]] == ["sin_texto"] * 3 and r["errores"] == []   # borrosos: ni se intenta
    r = reels.leer_fotogramas(fotos, gemini=cae, ocr=lambda fs: [""] * len(fs), medir=lambda f: 3.0)
    assert [x["estado"] for x in r["lecturas"]] == ["revisar"] * 3 and "503" in r["errores"][0]


def test_ocr_ordena_por_filas_y_quita_lo_dudoso():
    caja = lambda x, y: [[x, y], [x + 50, y], [x + 50, y + 20], [x, y + 20]]   # noqa: E731
    res = [(caja(200, 100), "rea", 0.9), (caja(10, 102), "morluto /", 0.95), (caja(10, 300), "ruido", 0.2),
           (caja(10, 200), "74.7k stars", 0.8)]
    motor = lambda ruta: (res, 0.1)   # noqa: E731
    assert reels.ocr_local([__import__("pathlib").Path("x.jpg")], motor=motor) == ["morluto / rea\n74.7k stars"]


def test_citas_dueno_barra_repo_con_espacios():
    c = reels.extraer_citas("morluto / rea\nReverse engineer anything")
    assert "morluto/rea" in c["repos_posibles"]


def test_vision_local_nunca_qwen25vl_7b_que_mide_8_3b(fotos):
    with pytest.raises(ValueError, match="8,3B"):
        reels.pantalla_local(fotos, modelo="qwen2.5vl:7b", post=lambda *a, **k: pytest.fail("pidio"))
    assert reels.MODELO_VISION == "qwen2.5vl:3b"


def test_procesar_ficha_completa_con_relectura_si_faltan(carpeta, tmp_path, monkeypatch):
    """Ficha de un reel con dobles: reutiliza video y transcripcion, lee 1/s, monta la ficha, ve que faltan elementos,
    relee a 2/s el tramo de la lista con recortes y vuelve a montar. Guarda bruto y ficha con historial."""
    monkeypatch.setattr(reels, "valor", lambda r, d=None: "CLAVE-FALSA" if r == "gemini.api_key" else d)
    col = tmp_path / "col.json"
    col.write_text(json.dumps({"reels": [{"codigo": "C1", "url": "https://www.instagram.com/reel/C1/", "autor": "a",
                                          "pie": "Comment TOKENS", "colecciones": ["ai"]}]}), encoding="utf-8")
    media = carpeta / "media" / "C1"
    media.mkdir(parents=True)
    (media / "C1.mp4").write_bytes(b"v")
    reels.guardar_bruto("C1", {"transcripcion": {"texto": "rtk caveman", "segmentos": [{"ini": 0, "texto": "rtk caveman"}]}})

    def correr(args, **k):
        destino = Path(args[-1])
        if "%05d" in destino.name:
            pref = destino.name[0]
            for n in (0, 1):
                (destino.parent / f"{pref}{n:05d}.jpg").write_bytes(b"x")
        else:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(b"x")
    pasadas = []

    def gemini(fs):
        pasadas.append([f.name for f in fs])
        if fs[0].name.startswith("r") or "_r" in fs[0].name:
            return ["3 repos\n1.rtk\n2.caveman\n3.headroom\n4.x"] * len(fs), "g"
        return ["3 repos\n1.rtk\n2.caveman\n3.\n4."] * len(fs), "g"
    fichas = []

    def post(url, cuerpo, cab=None, **k):
        mat = cuerpo["contents"][0]["parts"][0]["text"]
        elems = [{"tipo": "repo", "nombre": n, "en_promesa": True,      # T966: con 'para que' propio no hay reintento
                  "para_que": f"NEXO puede usar {n} para recortar los tokens de sus turnos"}
                 for n in ("rtk", "caveman", "headroom") if n in mat]
        fichas.append(len(elems))
        return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(
            {"tema": "tokens", "promesa": {"texto": "3 repos", "n": 3}, "elementos": elems})}]}}]}
    f = reels.procesar("C1", coleccion=col, post=post, correr=correr, resolver=lambda ficha, cache: {},
                       lectores={"gemini": gemini, "ocr": None, "local": None, "medir": lambda p: 5.0})
    assert fichas == [2, 2, 3] and f["relectura"] and f["estado"] == "completa"   # ficha, 2.a pasada, relectura
    assert [e["nombre"] for e in f["elementos"]] == ["rtk", "caveman", "headroom"]
    assert f["llamada"]["palabra"] == "TOKENS" and f["url"].endswith("/C1/")
    assert any(n.endswith("_r1.jpg") for p in pasadas for n in p)          # se leyeron recortes ampliados
    bruto = json.loads((carpeta / "C1.json").read_text(encoding="utf-8"))
    assert bruto["transcripcion"]["texto"] == "rtk caveman" and len(bruto["lectura_densa"]) == 2
    assert bruto["anteriores"]                                             # lo de antes no se pierde
    assert (carpeta / "C1.ficha.json").exists()


def test_gemini_todos_saturados_espera_y_reintenta(monkeypatch):
    import urllib.error
    monkeypatch.setattr(reels, "valor", lambda r, d=None: "CLAVE-FALSA" if r == "gemini.api_key" else d)
    llamadas, esperas = [], []

    def post(url, cuerpo, cab=None, **k):
        llamadas.append(url)
        if len(llamadas) <= len(reels.MODELOS_GEMINI):
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "ok"}]}}]}
    texto, modelo = reels.gemini_respaldo({}, post=post, dormir=esperas.append)
    assert texto == "ok" and esperas == [reels.ESPERAS_SATURADO[0]] and modelo == reels.MODELOS_GEMINI[0]
    with pytest.raises(urllib.error.HTTPError):
        reels.gemini_respaldo({}, post=lambda *a, **k: (_ for _ in ()).throw(
            urllib.error.HTTPError("u", 503, "x", {}, None)), dormir=esperas.append)


def test_cuota_diaria_agotada_se_salta_el_modelo_y_si_no_queda_ninguno_para(monkeypatch):
    import io
    import urllib.error
    monkeypatch.setattr(reels, "valor", lambda r, d=None: "CLAVE-FALSA" if r == "gemini.api_key" else d)
    monkeypatch.setattr(reels, "_AGOTADOS", {})
    diaria = b'{"error": {"details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}'
    urls = []

    def post(url, cuerpo, cab=None, **k):
        urls.append(url)
        if "lite" in url:
            return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "ok"}]}}]}
        raise urllib.error.HTTPError(url, 429, "quota", {}, io.BytesIO(diaria))
    assert reels.gemini_respaldo({}, post=post, dormir=lambda s: pytest.fail("no se espera"))[1] == "gemini-3.5-flash-lite"
    urls.clear()
    reels.gemini_respaldo({}, post=post, dormir=lambda s: None)
    assert len(urls) == 1                                   # los agotados ya ni se prueban
    reels.agotados_hoy().add("gemini-3.5-flash-lite")
    with pytest.raises(reels.SinCuotaGemini):
        reels.gemini_respaldo({}, post=post, dormir=lambda s: pytest.fail("no se espera"))


# ------------------------------------------------------------------ bloque 6: lote nocturno (preparado, no se lanza)
@pytest.fixture
def coleccion(tmp_path, carpeta):
    col = tmp_path / "col.json"
    col.write_text(json.dumps({"reels": [{"codigo": f"R{i}", "url": f"u{i}"} for i in range(6)]}), encoding="utf-8")
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "R0.ficha.json").write_text("{}", encoding="utf-8")              # ya hecho
    reels.guardar_bruto("R5", {"reprocesar": True}, carpeta=carpeta)            # Damian pego algo: va primero
    (carpeta / "R5.ficha.json").write_text("{}", encoding="utf-8")
    return col


def test_cola_del_lote_reprocesar_primero_y_sin_lo_hecho(coleccion):
    assert reels.cola_lote(coleccion) == ["R5", "R1", "R2", "R3", "R4"]
    assert reels.cola_lote(coleccion, estado={"fallos": {"R2": {"n": 3}}}) == ["R5", "R1", "R3", "R4"]


def test_lote_reanudable_con_tope_y_fallos_que_no_paran(coleccion, tmp_path):
    ruta = tmp_path / "lote.json"
    vistos = []

    def proc(codigo, coleccion=None):
        vistos.append(codigo)
        if codigo == "R1":
            raise RuntimeError("video roto")
        return {"estado": "completa", "elementos": [1, 2]}
    n = reels.lote(maximo=2, coleccion=coleccion, procesar_fn=proc, ram=lambda: 8000, parada=lambda: None, ruta=ruta)
    assert n["hechos"] == ["R5", "R2"] and n["fallos"][0]["codigo"] == "R1" and "tope" in n["motivo_fin"]
    estado = json.loads(ruta.read_text(encoding="utf-8"))
    assert estado["fallos"]["R1"]["n"] == 1 and "R2" in estado["hechos"]


def test_lote_para_por_ram_parada_cuota_y_saturacion(coleccion, tmp_path):
    import urllib.error
    ok = lambda c, coleccion=None: {"estado": "completa", "elementos": []}   # noqa: E731
    r = reels.lote(coleccion=coleccion, procesar_fn=ok, ram=lambda: 900, parada=lambda: None, ruta=tmp_path / "a.json")
    assert "poca RAM" in r["motivo_fin"] and not r["hechos"]
    r = reels.lote(coleccion=coleccion, procesar_fn=ok, ram=lambda: None, parada=lambda: "PARADA", ruta=tmp_path / "b.json")
    assert r["motivo_fin"] == "parada de NEXO"

    def sin_cuota(c, coleccion=None):
        raise reels.SinCuotaGemini("todos agotados")
    r = reels.lote(coleccion=coleccion, procesar_fn=sin_cuota, ram=lambda: 8000, parada=lambda: None, ruta=tmp_path / "c.json")
    assert r["motivo_fin"].startswith("Gemini sin cuota diaria") and not r["fallos"]
    esperas = []

    def saturado(c, coleccion=None):
        raise urllib.error.HTTPError("u", 503, "x", {}, None)
    r = reels.lote(coleccion=coleccion, procesar_fn=saturado, ram=lambda: 8000, parada=lambda: None,
                   dormir=esperas.append, ruta=tmp_path / "d.json")
    assert r["motivo_fin"] == "Gemini saturado 3 veces seguidas" and esperas == [reels.PAUSA_SATURADO] * 2
    est = json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))
    assert est["fallos"] == {}                         # la saturacion no cuenta como fallo del reel


def test_turno_lanza_el_lote_con_venv_reels_y_crea_propuestas_y_tarjeta(coleccion, carpeta, monkeypatch):
    from nucleo import reels_huecos, reels_tareas
    monkeypatch.setattr(reels, "COLECCION", coleccion)
    monkeypatch.setattr(reels, "LOTE", carpeta / "lote.json")
    assert reels.turno(simular=True) == {"simulado": True, "pendientes": 5, "rehacer_pendientes": 1}
    ordenes = []

    def correr(args, **k):
        ordenes.append(args)
        return SimpleNamespace(stdout='log\n{"hechos": ["R1"], "fallos": [], "motivo_fin": "cola vacia"}', returncode=0,
                               stderr="")
    monkeypatch.setattr(reels_tareas, "cargar_fichas", lambda c: [{"codigo": c[0], "elementos": []}])
    monkeypatch.setattr(reels_tareas, "plan", lambda f: {"tareas": []})
    monkeypatch.setattr(reels_tareas, "crear", lambda p: {"creadas": []})
    monkeypatch.setattr(reels_huecos, "registrar", lambda f: {"tarjeta": {"id": "H1", "reels": []}})
    r = reels.turno(correr=correr)
    assert ordenes[0][0].endswith("python.exe") and ".venv-reels" in ordenes[0][0] and ordenes[0][3:5] == ["lote", "--max"]
    assert r["noche"]["hechos"] == ["R1"] and r["tareas"] == {"creadas": []} and r["huecos"]["id"] == "H1"
    assert reels.turno(correr=lambda a, **k: SimpleNamespace(stdout="", returncode=1, stderr="boom"))["error"]


def test_plantilla_reels_existe_e_inactiva_por_defecto():
    from nucleo import turnos
    assert "reels" in turnos.PLANTILLAS
    assert not any(t.get("plantilla") == "reels" and t.get("activo") for t in turnos.cargar()["turnos"])


def test_rehacer_ficha_usa_las_lecturas_guardadas_sin_descargar(carpeta, tmp_path, monkeypatch):
    monkeypatch.setattr(reels, "valor", lambda r, d=None: "CLAVE-FALSA" if r == "gemini.api_key" else d)
    monkeypatch.setattr(reels, "descargar", lambda *a, **k: pytest.fail("no descarga"))
    monkeypatch.setattr(reels, "leer_fotogramas", lambda *a, **k: pytest.fail("no lee fotogramas"))
    col = tmp_path / "col.json"
    col.write_text(json.dumps({"reels": [{"codigo": "C1", "url": "u", "autor": "a", "pie": "Comenta REPO"}]}),
                   encoding="utf-8")
    reels.guardar_bruto("C1", {"pie": "Comenta REPO", "reprocesar": True,
                               "lectura_densa": [{"foto": "d00000.jpg", "t": 0, "texto": "morluto / rea", "estado": "texto"}],
                               "pegado": [{"texto": "y tambien rtk-ai/rtk", "confiable": False}]})
    (carpeta / "C1.ficha.json").write_text('{"relectura": true}', encoding="utf-8")
    vistos = []

    def post(url, cuerpo, cab=None, **k):
        vistos.append(cuerpo["contents"][0]["parts"][0]["text"])
        return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(
            {"elementos": [{"tipo": "Repositorio", "nombre": "rea", "dueno": "morluto"}]})}]}}]}
    assert reels._solo_rehacer("C1")
    f = reels.rehacer_ficha("C1", coleccion=col, post=post, resolver=lambda ficha, cache: {})
    assert "PEGADO POR DAMIAN" in vistos[0] and "morluto / rea" in vistos[0]
    assert [e["nombre"] for e in f["elementos"]] == ["rea", "rtk"] and f["elementos"][0]["tipo"] == "repo"
    assert f["crudo_modelo"]["elementos"][0]["tipo"] == "Repositorio" and f["relectura"]
    bruto = json.loads((carpeta / "C1.json").read_text(encoding="utf-8"))
    assert "reprocesar" not in bruto and bruto["lectura_densa"] and not reels._solo_rehacer("C1")


def test_lote_rehace_solo_la_ficha_si_hay_algo_pegado(coleccion, carpeta, tmp_path):
    reels.guardar_bruto("R5", {"reprocesar": True, "lectura_densa": [{"foto": "d", "t": 0, "texto": "x"}]}, carpeta=carpeta)
    usados = []
    n = reels.lote(maximo=2, coleccion=coleccion, ram=lambda: 8000, parada=lambda: None, ruta=tmp_path / "l.json",
                   procesar_fn=lambda c, coleccion=None: usados.append(("procesar", c)) or {"estado": "completa", "elementos": []},
                   rehacer_fn=lambda c, coleccion=None: usados.append(("rehacer", c)) or {"estado": "completa", "elementos": []})
    assert usados == [("rehacer", "R5"), ("procesar", "R1")] and n["hechos"] == ["R5", "R1"]


def test_segunda_pasada_del_modelo_pide_solo_lo_que_falta(monkeypatch):
    monkeypatch.setattr(reels, "valor", lambda r, d=None: "CLAVE-FALSA" if r == "gemini.api_key" else d)
    pedidos = []

    def post(url, cuerpo, cab=None, **k):
        texto = cuerpo["contents"][0]["parts"][0]["text"]
        pedidos.append(texto)
        if "ya se han sacado" in texto:
            elems = [{"tipo": "repo", "nombre": "headroom", "en_promesa": True}]
        else:
            elems = [{"tipo": "repo", "nombre": n, "en_promesa": True} for n in ("rtk", "caveman")]
        return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(
            {"promesa": {"texto": "3 repos", "n": 3}, "elementos": elems})}]}}]}
    bruto = {"pie": "3 repos", "transcripcion": {"segmentos": [{"ini": 0, "texto": "rtk caveman headroom"}]}}
    f, modelo, res = reels._montar(bruto, [], [], post, None, {})
    assert [e["nombre"] for e in f["elementos"]] == ["rtk", "caveman", "headroom"] and f["segunda_pasada"] == 1
    assert f["completitud"]["estado"] == "completa" and "rtk, caveman" in pedidos[1]
    assert len(f["crudo_modelo"]["elementos"]) == 3


def test_rehacer_con_la_respuesta_guardada_no_pide_nada(carpeta, tmp_path):
    col = tmp_path / "col.json"
    col.write_text(json.dumps({"reels": [{"codigo": "C1", "url": "u", "autor": "a", "pie": "2 repos"}]}), encoding="utf-8")
    reels.guardar_bruto("C1", {"pie": "2 repos", "lectura_densa": [{"foto": "d", "t": 0, "texto": "rtk caveman", "estado": "texto"}]})
    crudo = {"promesa": {"n": 2}, "elementos": [{"tipo": "Repositorio", "nombre": "rtk", "en_promesa": True},
                                                 {"tipo": "fuente", "nombre": "caveman", "en_promesa": True}]}
    (carpeta / "C1.ficha.json").write_text(json.dumps({"crudo_modelo": crudo, "modelo_ficha": "g"}), encoding="utf-8")
    f = reels.rehacer_ficha("C1", coleccion=col, usar_crudo=True, resolver=lambda ficha, cache: {},
                            post=lambda *a, **k: pytest.fail("no se pide nada"))
    assert [e["tipo"] for e in f["elementos"]] == ["repo", "dato"] and f["modelo_ficha"] == "g"
    (carpeta / "C1.ficha.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="no guarda"):
        reels.rehacer_ficha("C1", coleccion=col, usar_crudo=True)


# ---- bloque 6b: presupuesto de Gemini del lote y proveedores gratuitos primero
class _Libre:
    def __init__(self, nombre, texto, ok=True):
        self.nombre, self.texto, self.ok, self.llamadas, self.ultimo_modelo = nombre, texto, ok, 0, "m1"

    def disponible(self):
        return True

    def enviar(self, tarea):
        from proveedores import Resultado
        self.llamadas += 1
        return Resultado("OK", texto=self.texto) if self.ok else Resultado("ERROR", detalle="x")


def _cuerpo_ficha():
    return {"contents": [{"parts": [{"text": "p"}]}]}


def test_ficha_con_proveedor_gratuito_no_toca_gemini(monkeypatch):
    monkeypatch.setattr(reels, "gemini_respaldo", lambda *a, **k: pytest.fail("gasto Gemini"))
    nv = _Libre("nvidia", '{"elementos": []}')
    j, modelo = reels.pedir_modelo(_cuerpo_ficha(), libres=[nv, _Libre("groq", "{}")])
    assert j == {"elementos": []} and modelo == "nvidia:m1" and nv.llamadas == 1


def test_ficha_pasa_al_siguiente_si_el_json_es_roto_y_a_gemini_si_ninguno_vale(monkeypatch):
    vio = []
    monkeypatch.setattr(reels, "gemini_respaldo", lambda c, post, dormir, pres: (vio.append(pres) or '{"a": 1}', "g"))
    roto, bueno = _Libre("nvidia", "esto no es json"), _Libre("groq", '{"b": 2}')
    assert reels.pedir_modelo(_cuerpo_ficha(), libres=[roto, bueno])[0] == {"b": 2} and not vio
    caido = _Libre("groq", "", ok=False)
    assert reels.pedir_modelo(_cuerpo_ficha(), libres=[roto, caido], presupuesto=False)[0] == {"a": 1} and vio == [None]


def test_gemini_del_lote_respeta_su_tope_diario(monkeypatch):
    from nucleo import cuota
    monkeypatch.setattr(reels, "valor", lambda r, d=None: "CLAVE-FALSA" if r == "gemini.api_key" else d)
    monkeypatch.setattr(reels, "agotados_hoy", lambda: set())
    pres = reels.PresupuestoGemini(fraccion=0.25, total=8)          # 2 peticiones al dia
    resp = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}]}
    llamadas = []
    post = lambda *a, **k: llamadas.append(1) or resp              # noqa: E731
    reels.gemini_respaldo({"x": 1}, post, presupuesto=pres)
    reels.gemini_respaldo({"x": 1}, post, presupuesto=pres)
    with pytest.raises(reels.SinCuotaGemini, match="presupuesto"):
        reels.gemini_respaldo({"x": 1}, post, presupuesto=pres)
    assert len(llamadas) == 2 and pres.resumen() == {"gastadas_hoy": 2, "tope_dia": 2}
    assert cuota.permite("gemini_api", "tribunal", 100, 1.0)         # el tribunal no pierde la suya


def test_config_del_lote_por_defecto_es_el_20_por_ciento(tmp_path):
    assert reels.config_lote(tmp_path / "no.json")["gemini_fraccion_diaria"] == 0.20
    (tmp_path / "c.json").write_text('{"gemini_fraccion_diaria": 0.5, "otra": 1}', encoding="utf-8")
    c = reels.config_lote(tmp_path / "c.json")
    assert c["gemini_fraccion_diaria"] == 0.5 and "otra" not in c


def test_primera_noche_deja_muestra_sin_crear_nada_y_apaga_el_turno(coleccion, carpeta, monkeypatch):
    """6b: con crear_propuestas=false y una_noche=true el turno no crea tareas ni tarjeta, escribe la muestra de 10
    fichas con lo que saldria y se apaga solo."""
    from nucleo import reels_huecos, reels_tareas, turnos
    (carpeta / "config.json").write_text('{"crear_propuestas": false, "una_noche": true}', encoding="utf-8")
    monkeypatch.setattr(reels, "CONFIG", carpeta / "config.json")
    monkeypatch.setattr(reels, "COLECCION", coleccion)
    monkeypatch.setattr(reels, "LOTE", carpeta / "lote.json")
    monkeypatch.setattr(reels, "CARPETA", carpeta)
    hechos = [f"R{i}" for i in range(1, 15)]
    fichas = [{"codigo": c, "autor": "a", "tema": f"tema {c}", "resumen": "r", "elementos": [],
               "completitud": {}, "promesa": {}, "llamada": {}, "hueco": {"hay": False}, "lectores": [],
               "colecciones": []} for c in hechos]
    monkeypatch.setattr(reels_tareas, "cargar_fichas", lambda c: fichas)
    monkeypatch.setattr(reels_tareas, "plan", lambda f: {"tareas": [], "conocimiento": {}, "anotaciones": [],
                                                         "excluidos": [], "fuentes": {}})
    monkeypatch.setattr(reels_tareas, "crear", lambda p: pytest.fail("creo tareas en la primera noche"))
    monkeypatch.setattr(reels_huecos, "registrar",
                        lambda f, **k: pytest.fail("escribio") if k.get("escribir", True)
                        else {"tarjeta": {"id": "H1", "reels": [], "fuera_de_tanda": 0}})
    apagados = []
    monkeypatch.setattr(turnos, "cargar", lambda: {"turnos": [{"id": "u1", "plantilla": "reels", "activo": True},
                                                                {"id": "u2", "plantilla": "cola", "activo": True}]})
    monkeypatch.setattr(turnos, "poner_activo", lambda i, a: apagados.append((i, a)))
    resumen = '{"hechos": %s, "fallos": [], "motivo_fin": "cola vacia"}' % json.dumps(hechos)
    r = reels.turno(correr=lambda a, **k: SimpleNamespace(stdout=resumen, returncode=0, stderr=""))
    assert "tareas" not in r and r["apagado"] == ["u1"] and apagados == [("u1", False)]
    texto = open(r["muestra"], encoding="utf-8").read()
    assert texto.count("tema R") >= 10 and "No se ha creado ninguna tarea" in texto


def test_proveedor_libre_por_urllib_usa_la_tabla_de_fallos_y_prefiere_los_grandes(monkeypatch):
    """.venv-reels no tiene httpx: NVIDIA/Groq se piden por urllib con la misma cascada de fallos."""
    peticiones = []

    def post(url, cuerpo, cab, timeout):
        peticiones.append((cuerpo["model"], cab["Authorization"], cuerpo.get("max_tokens")))
        if cuerpo["model"] == "openai/gpt-oss-120b":
            return reels._Respuesta(500, "caido", {})
        return reels._Respuesta(200, json.dumps({"choices": [{"message": {"content": '{"ok": 1}'}}]}), {})
    monkeypatch.setattr(reels, "_post_respuesta", post)
    prov = SimpleNamespace(nombre="nvidia", rondas=1, espera=0, timeout=5, _clave=lambda: "K",
                           _vivos=lambda: ("openai/gpt-oss-20b", "openai/gpt-oss-120b", "x/otro"), disponible=lambda: True)
    libre = reels.ProveedorLibre(prov, "http://u", 777)
    r = libre.enviar("hola")
    assert r.ok and r.texto == '{"ok": 1}' and libre.ultimo_modelo == "openai/gpt-oss-20b"
    assert [p[0] for p in peticiones] == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]    # el grande primero; cae al siguiente
    assert peticiones[0][1:] == ("Bearer K", 777)


def test_nvidia_de_las_fichas_espera_420_s_y_el_resto_de_roles_120():
    from extremidades import reels as R
    import proveedores as P
    nv = R.proveedores_libres()[0]
    assert nv.prov.timeout == R.TIMEOUT_NVIDIA_REELS == 420
    assert P.NvidiaProvider().timeout == 120.0
