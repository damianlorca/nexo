# -*- coding: utf-8 -*-
"""T697: oyente del volumen del altavoz "Damián", el brief y la voz. Sin red ni altavoz: todo son dobles."""
from __future__ import annotations

import base64
import threading
import time
import urllib.error
import wave
from types import SimpleNamespace

import pytest

from extremidades import altavoz, voz_gemini
from nucleo import parada


class CastFalso:
    """Altavoz falso: set_volume avisa a los oyentes como haria pychromecast (en otro hilo)."""

    def __init__(self, volumen=0.30, confirma=True, falla=False):
        self.status = SimpleNamespace(volume_level=volumen)
        self.oyentes = []
        self.cambios = []
        self.confirma = confirma
        self.falla = falla
        self.desconectado = False

    def register_status_listener(self, o):
        self.oyentes.append(o)

    def register_connection_listener(self, o):
        pass

    def set_volume(self, v):
        if self.falla:
            raise OSError("sin conexion")
        self.cambios.append(v)
        if self.confirma:
            self.status = SimpleNamespace(volume_level=v)
            threading.Thread(target=lambda: [o.new_cast_status(self.status) for o in self.oyentes]).start()

    def voz(self, v):   # cambio hecho por Damian (rutina de Google Home)
        self.status = SimpleNamespace(volume_level=v)
        for o in self.oyentes:
            o.new_cast_status(self.status)

    def disconnect(self, timeout=None):
        self.desconectado = True


def _oyente(cc, guardados=None, avisos=None, contados=None, normal=None):
    guardados = [] if guardados is None else guardados
    avisos = [] if avisos is None else avisos
    contados = [] if contados is None else contados
    o = altavoz.Oyente(buscar_=lambda: (cc, None), contar_=lambda c: contados.append(c),
                       avisar_=lambda t, c: avisos.append((t, c)), leer_=lambda: normal,
                       guardar_=guardados.append, esperar_restaurar=2, buscar_cada=0.05)
    assert o.conectar()
    return o, guardados, avisos, contados


def _esperar(cond, segundos=3):
    fin = time.time() + segundos
    while time.time() < fin and not cond():
        time.sleep(0.01)
    return cond()


def test_guarda_el_volumen_normal_y_no_toca_nada():
    cc = CastFalso(0.30)
    o, guardados, avisos, contados = _oyente(cc)
    cc.voz(0.45)
    assert o.volumen_normal == 0.45 and guardados == [0.30, 0.45]
    assert cc.cambios == [] and not avisos and not contados


def test_al_13_restaura_y_cuenta():
    cc = CastFalso(0.30)
    o, guardados, avisos, contados = _oyente(cc)
    cc.voz(0.13)
    assert _esperar(lambda: contados)
    assert cc.cambios == [0.30] and contados == [cc] and not avisos
    assert o.volumen_normal == 0.30


def test_si_no_puede_restaurar_no_cuenta_y_avisa():
    for cc in (CastFalso(0.30, confirma=False), CastFalso(0.30, falla=True)):
        o, _, avisos, contados = _oyente(cc)
        cc.voz(0.13)
        assert _esperar(lambda: avisos)
        assert not contados and avisos[0][0] == "Brief no reproducido"


def test_sin_volumen_previo_no_toca_ni_cuenta():
    cc = CastFalso(0.13)          # arranca ya al 13 %: no es volumen normal ni disparo
    o, guardados, avisos, contados = _oyente(cc)
    assert guardados == [] and o.volumen_normal is None
    cc.voz(0.131)
    assert _esperar(lambda: avisos)
    assert cc.cambios == [] and not contados


def test_un_solo_disparo_aunque_lleguen_varios_estados():
    cc = CastFalso(0.30, confirma=False)
    hecho = threading.Event()
    o, _, avisos, contados = _oyente(cc)
    o._esperar = 0.3
    cc.voz(0.13)
    cc.voz(0.13)   # mismo estado repetido mientras restaura
    assert _esperar(lambda: avisos)
    time.sleep(0.4)
    assert len(cc.cambios) == 1 and len(avisos) == 1
    hecho.set()


def test_vuelve_a_buscar_si_desaparece():
    cc1, cc2 = CastFalso(0.3), CastFalso(0.3)
    buscados = [None, cc1, cc2]

    def buscar():
        c = buscados.pop(0) if buscados else cc2
        return (c, None)
    o = altavoz.Oyente(buscar_=buscar, contar_=lambda c: None, avisar_=lambda *a: None, leer_=lambda: None,
                       guardar_=lambda v: None, buscar_cada=0.05)
    h = o.arrancar()
    assert _esperar(lambda: o.cc is cc1)
    o.new_connection_status(SimpleNamespace(status="LOST"))
    assert _esperar(lambda: o.cc is cc2) and cc1.desconectado
    o.parar()
    h.join(2)
    assert not h.is_alive()


def test_nombre_exacto(monkeypatch):
    import pychromecast
    tele = SimpleNamespace(cast_info=SimpleNamespace(friendly_name="marina"))
    parecido = SimpleNamespace(cast_info=SimpleNamespace(friendly_name="Damián 2"))
    monkeypatch.setattr(pychromecast, "get_listed_chromecasts", lambda **k: ([tele, parecido], None))
    assert altavoz.buscar() == (None, None)


# ------------------------------------------------------------------ contar
@pytest.fixture
def sin_parada(monkeypatch, tmp_path):
    monkeypatch.setattr(parada, "activa", lambda: False)
    monkeypatch.setattr(altavoz, "carpeta", lambda: tmp_path)


def test_contar_usa_el_altavoz_y_respeta_un_brief_cada_vez(sin_parada, tmp_path):
    cc = CastFalso()
    sonados = []
    r = altavoz.contar(cc=cc, componer=lambda: "Hola Damián.", sintetizar_=lambda t, d: (d, "gemini"),
                       reproducir_=lambda c, w: sonados.append((c, w.name)) or "FINISHED")
    assert r == {"ok": True, "motor": "gemini", "fin": "FINISHED", "palabras": 2}
    assert sonados == [(cc, "brief.wav")] and not cc.desconectado
    altavoz._contando.acquire()
    try:
        assert altavoz.contar(cc=cc, componer=lambda: "x")["motivo"] == "ya está sonando"
    finally:
        altavoz._contando.release()


def test_contar_sin_altavoz_no_reproduce_y_con_parada_no_hace_nada(sin_parada, monkeypatch):
    r = altavoz.contar(componer=lambda: "x", sintetizar_=lambda t, d: (d, "piper"), buscar_=lambda: (None, None),
                       reproducir_=lambda c, w: pytest.fail("no debe reproducir"))
    assert not r["ok"] and "no encuentro" in r["motivo"]
    monkeypatch.setattr(parada, "activa", lambda: True)
    assert "PARADA" in altavoz.contar(componer=lambda: pytest.fail("no compone"))["motivo"]


def test_contar_en_hilo_avisa_si_falla(monkeypatch):
    avisos = []
    monkeypatch.setattr(altavoz, "avisar", lambda t, c: avisos.append(t))
    altavoz.contar_en_hilo(contar_=lambda cc: {"ok": False, "motivo": "no encuentro"})
    assert _esperar(lambda: avisos) and avisos == ["El brief no ha sonado"]


# ------------------------------------------------------------------ voz
@pytest.fixture
def con_clave(monkeypatch, tmp_path):
    monkeypatch.setattr(voz_gemini, "valor", lambda r, d=None: "CLAVE-FALSA" if r == "gemini.api_key" else d)
    monkeypatch.setattr(voz_gemini, "carpeta_cache", lambda: tmp_path / "voz_cache")   # nunca la cache real
    voz_gemini._usos.clear()
    yield
    voz_gemini._usos.clear()


def _pcm_ok(vistos=None, n=100):
    """Doble de la API: guarda el texto pedido y devuelve n muestras PCM."""
    def llamar(cuerpo, clave, timeout):
        if vistos is not None:
            vistos.append(cuerpo["input"][0]["content"][0]["text"] if "input" in cuerpo else
                          cuerpo["contents"][0]["parts"][0]["text"])
        return {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(b"\x01\x00" * n).decode()}}]}}]}
    return llamar


def test_gemini_bloom_estilo_y_wav(con_clave, tmp_path):
    vistos = []

    def llamar(cuerpo, clave, timeout):
        vistos.append(cuerpo)
        pcm = b"\x00\x01" * 2400
        return {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(pcm).decode()}}]}}]}
    wav = voz_gemini.narrar("Hola", tmp_path / "b.wav", llamar=llamar)
    with wave.open(str(wav)) as w:
        assert w.getframerate() == 24000 and w.getnframes() == 2400
    c = vistos[0]   # 05/10: Interactions API, el texto limpio y el estilo en su anotacion (antes se leia en voz alta)
    assert c["generation_config"]["speech_config"] == [{"voice": "Bloom"}]
    parte = c["input"][0]["content"][0]
    assert parte["text"] == "Hola"
    assert parte["annotations"][0]["type"] == "speech_metadata" and "no leas ninguna instrucción" in parte[
        "annotations"][0]["style"]


def test_gemini_respuesta_de_interactions(con_clave, tmp_path):
    pcm = bytes(200)
    resp = {"steps": [{"type": "thought"}, {"type": "model_output", "content": [
        {"type": "audio", "mime_type": "audio/L16;rate=24000", "data": base64.b64encode(pcm).decode()}]}]}
    wav = voz_gemini.narrar("Hola", tmp_path / "i.wav", llamar=lambda c, k, t: resp)
    with wave.open(str(wav)) as w:
        assert w.getnframes() == 100


def test_gemini_si_falla_interactions_va_a_generatecontent_sin_estilo(con_clave, tmp_path):
    vistos = []

    def llamar(cuerpo, clave, timeout):
        vistos.append(cuerpo)
        if "input" in cuerpo:
            raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        return {"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(bytes(2)).decode()}}]}}]}
    voz_gemini.narrar("Buenos días", tmp_path / "c.wav", llamar=llamar)
    assert vistos[1]["contents"][0]["parts"][0]["text"] == "Buenos días"   # nada de instrucciones delante
    assert vistos[1]["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Bloom"


def test_gemini_cupo_de_3_por_minuto_y_fallos(con_clave, tmp_path):
    ok = lambda c, k, t: {"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(b"\0\0").decode()}}]}}]}
    for i in range(3):     # textos distintos: el mismo texto ya saldria de la cache sin gastar cupo
        voz_gemini.narrar(f"x{i}", tmp_path / "a.wav", llamar=ok)
    with pytest.raises(voz_gemini.SinVoz, match="cupo"):
        voz_gemini.narrar("x3", tmp_path / "a.wav", llamar=ok)
    voz_gemini._usos.clear()

    def http429(c, k, t):
        raise urllib.error.HTTPError("u", 429, "Too Many", {}, None)
    with pytest.raises(voz_gemini.SinVoz, match="429") as e:
        voz_gemini.narrar("y", tmp_path / "a.wav", llamar=http429)
    assert "CLAVE-FALSA" not in str(e.value)


# ---------------------------------------------- T697 bloque 5: troceo y cache
def test_trocear_corta_por_frases_sin_pasar_el_maximo():
    frase = "Esta es una frase de prueba con unas cuantas palabras. "
    texto = (frase * 40).strip()
    trozos = voz_gemini.trocear(texto, maximo=300)
    assert len(trozos) > 1 and all(len(t) <= 300 for t in trozos)
    assert all(t.endswith(".") for t in trozos)                      # nunca a mitad de frase
    assert " ".join(trozos) == texto                                 # no se pierde ni se inventa nada


def test_trocear_texto_corto_un_solo_trozo_y_frase_enorme_por_comas_o_espacios():
    assert voz_gemini.trocear("Hola, Damián.") == ["Hola, Damián."]
    assert voz_gemini.trocear("   ") == []
    enorme = ", ".join(["palabra"] * 200) + "."
    trozos = voz_gemini.trocear(enorme, maximo=120)
    assert all(len(t) <= 120 for t in trozos) and " ".join(trozos) == enorme


def test_texto_largo_va_en_trozos_y_un_solo_wav(con_clave, tmp_path, monkeypatch):
    monkeypatch.setattr(voz_gemini, "TROZO_MAX", 200)
    monkeypatch.setattr(voz_gemini, "CUPO_MINUTO", 10)
    vistos = []
    texto = " ".join(f"Frase número {i} del brief de hoy." for i in range(20))
    wav = voz_gemini.narrar(texto, tmp_path / "largo.wav", llamar=_pcm_ok(vistos, n=50))
    assert len(vistos) > 1 and all(len(v) <= 200 for v in vistos)
    assert " ".join(vistos) == texto
    with wave.open(str(wav)) as w:
        assert w.getnframes() == 50 * len(vistos) and w.getframerate() == 24000


def test_cache_no_vuelve_a_pedir_ni_gasta_cupo(con_clave, tmp_path):
    vistos = []
    voz_gemini.narrar("Buenos días, Damián.", tmp_path / "1.wav", llamar=_pcm_ok(vistos))
    for i in range(5):     # mas que el cupo: todo sale de la cache
        voz_gemini.narrar("Buenos días, Damián.", tmp_path / f"{i}.wav", llamar=lambda *a: pytest.fail("pidio"))
    assert len(vistos) == 1 and len(voz_gemini._usos) == 1
    with wave.open(str(tmp_path / "4.wav")) as w:
        assert w.getnframes() == 100


def test_cache_depende_de_voz_y_estilo(con_clave, tmp_path):
    vistos = []
    voz_gemini.narrar("Hola.", tmp_path / "a.wav", llamar=_pcm_ok(vistos))
    voz_gemini.narrar("Hola.", tmp_path / "b.wav", llamar=_pcm_ok(vistos), voz="Otra")
    voz_gemini.narrar("Hola.", tmp_path / "c.wav", llamar=_pcm_ok(vistos), estilo="Más lento.")
    assert len(vistos) == 3


def test_fallo_a_mitad_da_sinvoz_y_lo_ya_hecho_queda_en_cache(con_clave, tmp_path, monkeypatch):
    monkeypatch.setattr(voz_gemini, "TROZO_MAX", 60)
    monkeypatch.setattr(voz_gemini, "CUPO_MINUTO", 10)
    texto = "Primera frase del brief de hoy. Segunda frase del brief de hoy. Tercera frase."

    def falla_la_segunda(c, k, t):       # falla por las dos APIs: no hay respaldo que la salve
        texto_pedido = c["input"][0]["content"][0]["text"] if "input" in c else c["contents"][0]["parts"][0]["text"]
        if texto_pedido.startswith("Segunda"):
            raise urllib.error.HTTPError("u", 500, "Error", {}, None)
        return _pcm_ok()(c, k, t)
    with pytest.raises(voz_gemini.SinVoz):
        voz_gemini.narrar(texto, tmp_path / "f.wav", llamar=falla_la_segunda)
    assert not (tmp_path / "f.wav").exists()
    vistos = []
    voz_gemini.narrar(texto, tmp_path / "f.wav", llamar=_pcm_ok(vistos))
    assert len(vistos) == len(voz_gemini.trocear(texto, 60)) - 1     # el primero ya estaba


def test_varios_trozos_esperan_cupo_en_vez_de_fallar(con_clave, tmp_path, monkeypatch):
    monkeypatch.setattr(voz_gemini, "TROZO_MAX", 40)
    esperas = []
    monkeypatch.setattr(voz_gemini, "_esperar_cupo", lambda: esperas.append(1) or voz_gemini._usos.clear() or True)
    texto = " ".join(f"Frase {i} con algo de texto." for i in range(6))     # distintas: sin aciertos de cache
    voz_gemini.narrar(texto, tmp_path / "e.wav", llamar=_pcm_ok())
    assert esperas      # con 6 trozos y cupo 3 tuvo que esperar al menos una vez


def test_sin_gemini_cae_a_piper(monkeypatch, tmp_path):
    from extremidades import voz

    def sin(texto, destino):
        raise voz_gemini.SinVoz("cupo")
    monkeypatch.setattr(voz_gemini, "narrar", sin)
    monkeypatch.setattr(voz, "narrar", lambda texto, destino: destino)
    assert altavoz.sintetizar("x", tmp_path / "b.wav") == (tmp_path / "b.wav", "piper")


# ------------------------------------------------------------------ 05/10: altavoz no visible
def test_buscar_usa_la_ultima_ip_buena_y_cuenta_los_dispositivos(monkeypatch, tmp_path, caplog):
    import logging
    import pychromecast
    monkeypatch.setattr(altavoz, "carpeta", lambda: tmp_path)
    monkeypatch.setattr(altavoz, "valor", lambda ruta, defecto=None: ["192.168.0.104"] if ruta == "altavoz.hosts" else defecto)
    pedidos = []
    damian = SimpleNamespace(cast_info=SimpleNamespace(friendly_name="Damián", host="192.168.0.120"),
                             wait=lambda timeout=None: None)
    respuestas = [([], SimpleNamespace(devices={"a": 1, "b": 2})), ([damian], SimpleNamespace(devices={"a": 1}))]

    def listar(**k):
        pedidos.append(k["known_hosts"])
        return respuestas.pop(0)
    monkeypatch.setattr(pychromecast, "get_listed_chromecasts", listar)
    monkeypatch.setattr(altavoz, "cerrar_busqueda", lambda b: None)
    with caplog.at_level(logging.INFO, logger="extremidades.altavoz"):
        assert altavoz.buscar() == (None, None)
    assert "veo 2 dispositivos Cast" in caplog.text and altavoz.ULTIMA_BUSQUEDA["vistos"] == 2
    cc, _ = altavoz.buscar()
    assert cc is damian and altavoz.ultima_ip() == "192.168.0.120"
    assert altavoz.hosts_conocidos() == ["192.168.0.104", "192.168.0.120"]
    assert pedidos == [["192.168.0.104"], ["192.168.0.104"]]


def test_la_ultima_ip_no_pisa_el_volumen_normal(monkeypatch, tmp_path):
    monkeypatch.setattr(altavoz, "carpeta", lambda: tmp_path)
    altavoz.guardar_volumen_normal(0.3)
    altavoz.guardar_ultima_ip("192.168.0.120")
    assert altavoz.leer_volumen_normal() == 0.3 and altavoz.ultima_ip() == "192.168.0.120"


def test_fuera_de_casa_por_la_red_del_pc(monkeypatch, tmp_path):
    monkeypatch.setattr(altavoz, "carpeta", lambda: tmp_path)
    assert altavoz.fuera_de_casa(["192.168.0.104"], ip_local_=lambda h: "10.236.23.121")
    assert not altavoz.fuera_de_casa(["192.168.0.104"], ip_local_=lambda h: "192.168.0.50")


def test_sin_altavoz_lo_dice_y_espacia_las_busquedas(monkeypatch):
    o = altavoz.Oyente(buscar_=lambda: (None, None), contar_=lambda c: None, avisar_=lambda *a: None,
                       leer_=lambda: None, guardar_=lambda v: None, buscar_cada=60, espera_max=900,
                       fuera_=lambda: True)
    esperas = []
    for _ in range(6):
        assert not o.conectar()
        esperas.append(o.espera())
    assert esperas == [60, 120, 240, 480, 900, 900]
    assert o.no_visible == altavoz.FUERA_DE_CASA == "altavoz no visible (¿el PC está fuera de casa?)"
    monkeypatch.setattr(altavoz, "_oyente", o)
    e = altavoz.estado_oyente()
    assert e["visible"] is False and e["texto"] == altavoz.FUERA_DE_CASA and e["fallos"] == 6


def test_en_casa_sin_damian_dice_cuantos_ve_y_al_volver_se_resetea(monkeypatch):
    cc = CastFalso(0.3)
    buscados = [(None, None), (cc, None)]
    monkeypatch.setitem(altavoz.ULTIMA_BUSQUEDA, "vistos", 3)
    o = altavoz.Oyente(buscar_=lambda: buscados.pop(0), contar_=lambda c: None, avisar_=lambda *a: None,
                       leer_=lambda: None, guardar_=lambda v: None, fuera_=lambda: False)
    assert not o.conectar() and "veo 3 dispositivos Cast" in o.no_visible
    assert o.conectar() and o.fallos == 0 and o.no_visible is None and o.espera() == altavoz.BUSCAR_CADA
    monkeypatch.setattr(altavoz, "_oyente", o)
    assert altavoz.estado_oyente()["visible"] is True


# ------------------------- Damian 05/10 (prueba real 22:16): vuelta a casa y 13 % ya puesto

def test_al_encontrarlo_ya_al_13_restaura_y_cuenta():
    cc = CastFalso(0.13)
    contados, avisos = [], []
    o = altavoz.Oyente(buscar_=lambda: (cc, None), contar_=contados.append, avisar_=lambda t, c: avisos.append(t),
                       leer_=lambda: 0.30, guardar_=lambda v: None, esperar_restaurar=2, hora_=lambda: 22)
    assert o.conectar()
    assert _esperar(lambda: contados)
    assert cc.cambios == [0.30] and contados == [cc] and not avisos


def test_al_encontrarlo_al_13_de_madrugada_solo_devuelve_el_volumen():
    cc = CastFalso(0.13)
    contados, avisos = [], []
    o = altavoz.Oyente(buscar_=lambda: (cc, None), contar_=contados.append, avisar_=lambda t, c: avisos.append(t),
                       leer_=lambda: 0.30, guardar_=lambda v: None, esperar_restaurar=2, hora_=lambda: 3)
    assert o.conectar()
    assert _esperar(lambda: avisos)
    assert cc.cambios == [0.30] and not contados and avisos == ["Brief no contado"]


def test_en_casa_busca_como_mucho_cada_45_s():
    o = altavoz.Oyente(buscar_=lambda: (None, None), contar_=lambda c: None, avisar_=lambda *a: None,
                       leer_=lambda: None, guardar_=lambda v: None, buscar_cada=60, espera_max=900,
                       fuera_=lambda: False)
    esperas = []
    for _ in range(6):
        assert not o.conectar()
        esperas.append(o.espera())
    assert esperas == [45, 45, 45, 45, 45, 45]


def test_espera_larga_se_corta_al_volver_a_casa():
    red = {"fuera": True}
    o = altavoz.Oyente(buscar_=lambda: (None, None), contar_=lambda c: None, avisar_=lambda *a: None,
                       leer_=lambda: None, guardar_=lambda v: None, buscar_cada=0.04, espera_max=0.9,
                       fuera_=lambda: red["fuera"], en_casa_cada=0.03, paso_espera=0.01)
    for _ in range(6):
        o.conectar()
    assert o.espera() == pytest.approx(0.9)
    red["fuera"] = False            # el PC vuelve a la red de casa a mitad de la espera
    t0 = time.time()
    esperado = o.esperar_busqueda()
    assert esperado < 0.1 and time.time() - t0 < 0.5


def test_fuera_de_casa_la_espera_no_se_corta():
    o = altavoz.Oyente(buscar_=lambda: (None, None), contar_=lambda c: None, avisar_=lambda *a: None,
                       leer_=lambda: None, guardar_=lambda v: None, buscar_cada=0.04, espera_max=0.2,
                       fuera_=lambda: True, en_casa_cada=0.03, paso_espera=0.01)
    for _ in range(5):
        o.conectar()
    assert o.esperar_busqueda() == pytest.approx(0.2)


# ------------------------------------------------------------------ T886: Piper ante CUALQUIER fallo de Gemini
@pytest.mark.parametrize("fallo", [OSError("sin red"), ValueError("json roto"), KeyError("candidates"),
                                   TimeoutError("lento"), wave.Error("wav raro")])
def test_cualquier_fallo_operativo_de_gemini_cae_a_piper_y_queda_en_el_log(monkeypatch, tmp_path, caplog, fallo):
    import logging
    from extremidades import voz

    def roto(texto, destino):
        raise fallo
    monkeypatch.setattr(voz_gemini, "narrar", roto)
    monkeypatch.setattr(voz, "narrar", lambda texto, destino: destino)
    with caplog.at_level(logging.INFO):
        assert altavoz.sintetizar("x", tmp_path / "b.wav") == (tmp_path / "b.wav", "piper")
    assert any(type(fallo).__name__ in r.getMessage() for r in caplog.records)


def test_un_error_de_codigo_en_gemini_tambien_cae_a_piper_pero_con_traza_de_error(monkeypatch, tmp_path, caplog):
    import logging
    from extremidades import voz

    def roto(texto, destino):
        return None.hablar()
    monkeypatch.setattr(voz_gemini, "narrar", roto)
    monkeypatch.setattr(voz, "narrar", lambda texto, destino: destino)
    with caplog.at_level(logging.INFO):
        assert altavoz.sintetizar("x", tmp_path / "b.wav") == (tmp_path / "b.wav", "piper")
    erroneos = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert erroneos and "ERROR DE CODIGO" in erroneos[0].getMessage() and erroneos[0].exc_info


def test_si_piper_tambien_falla_el_error_sube(monkeypatch, tmp_path):
    from extremidades import voz
    monkeypatch.setattr(voz_gemini, "narrar", lambda t, d: (_ for _ in ()).throw(OSError("x")))
    monkeypatch.setattr(voz, "narrar", lambda t, d: (_ for _ in ()).throw(RuntimeError("piper roto")))
    with pytest.raises(RuntimeError, match="piper roto"):
        altavoz.sintetizar("x", tmp_path / "b.wav")
