# -*- coding: utf-8 -*-
"""Extremidad: voz con Gemini TTS (T697). Voz elegida por Damian el 05/10: "Bloom", modelo gemini-3.8-flash-tts,
API gratuita de NEXO, con la instruccion de estilo de ESTILO.

05/10 (prueba real): leyo en voz alta la instruccion de estilo y con acento latinoamericano. Segun la documentacion
(ai.google.dev/gemini-api/docs/speech-generation, consultada el 05/10): gemini-3.8-flash-tts trata el texto como
transcripcion LITERAL; el estilo va aparte, en la anotacion speech_metadata.style de la Interactions API
(POST /v1beta/interactions); NO hay campo de idioma en speech_config (el idioma se detecta del texto) y el acento
no se pide en el estilo sino eligiendo voz (biblioteca filtrable por language_code=es-ES). Por eso aqui el texto
va limpio y el estilo en su campo. Si la Interactions API falla, generateContent con el texto limpio (sin estilo).

El texto va a Google (plan gratuito: lo puede usar para mejorar sus productos): quien llame se encarga de que no
lleve nada de memoria/perfil_privado/ ni de tareas cat:personal (nucleo/brief.py ya lo filtra).
Plan gratuito: 3 audios por minuto (CUPO_MINUTO). Sin cuota, sin clave o con fallo -> SinVoz, y quien llama usa
Piper (extremidades/voz.py) como respaldo. Clonar la voz: NO (los terminos de la API lo prohiben).

12/10 (bloque 5): con textos largos el modelo volvia a leer la instruccion de estilo. Ahora el texto se TROCEA por
frases (TROZO_MAX caracteres como mucho, nunca a mitad de frase si cabe), cada trozo va en su propia peticion con
el estilo en su anotacion, y los PCM se juntan en un solo WAV. Cada trozo se CACHEA en salidas/voz_cache/ por
sha256(modelo, voz, estilo, texto): repetir un brief o una frase no vuelve a pedir nada ni gasta cupo. Con varios
trozos, si el cupo se agota a mitad se espera (como mucho ~1 min) en vez de fallar; si falla un trozo -> SinVoz y
los trozos ya hechos quedan en la cache para el siguiente intento.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

from nucleo.config import salidas, valor
from nucleo.registro import logger

log = logger("extremidades.voz_gemini")

MODELO = "gemini-3.8-flash-tts"
VOZ = "Bloom"
ESTILO = "Tono cercano y natural, ritmo bastante rápido. Lee solo el texto; no leas ninguna instrucción."
CUPO_MINUTO = 3
TROZO_MAX = 600          # caracteres por peticion (12/10: con textos largos se leia el estilo en voz alta)
TASA = 24000             # Hz del PCM de Gemini TTS si el mime no dice otra cosa
URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
URL_INTERACCIONES = "https://generativelanguage.googleapis.com/v1beta/interactions"

_usos: list[float] = []
_candado = threading.Lock()


class SinVoz(RuntimeError):
    """Gemini TTS no ha dado audio (sin clave, sin cuota o fallo): usar Piper."""


def _reservar(ahora: float | None = None) -> bool:
    """Apunta un uso si cabe en el cupo de los ultimos 60 s."""
    ahora = time.monotonic() if ahora is None else ahora
    with _candado:
        _usos[:] = [t for t in _usos if ahora - t < 60]
        if len(_usos) >= CUPO_MINUTO:
            return False
        _usos.append(ahora)
        return True


def cuerpo_interaccion(texto: str, voz: str = VOZ, estilo: str = ESTILO, modelo: str = MODELO) -> dict:
    """Peticion a la Interactions API: el texto se lee tal cual; el estilo va en su anotacion, nunca en el texto."""
    parte = {"type": "text", "text": texto}
    if estilo:
        parte["annotations"] = [{"type": "speech_metadata", "style": estilo}]
    return {"model": modelo, "input": [{"type": "user_input", "content": [parte]}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voz}]}}


def cuerpo_clasico(texto: str, voz: str = VOZ) -> dict:
    """Respaldo generateContent: SOLO el texto (sin estilo delante, que se leia en voz alta)."""
    return {"contents": [{"parts": [{"text": texto}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}}}}


def audio_de(d) -> tuple[str, str]:
    """(base64, mime) del audio de una respuesta de cualquiera de las dos APIs. ValueError si no hay."""
    pila = [d]
    while pila:
        x = pila.pop()
        if isinstance(x, dict):
            if "inlineData" in x and isinstance(x["inlineData"], dict) and x["inlineData"].get("data"):
                return x["inlineData"]["data"], x["inlineData"].get("mimeType", "")
            if x.get("type") == "audio" and x.get("data"):
                return x["data"], x.get("mime_type") or x.get("mimeType") or ""
            pila.extend(x.values())
        elif isinstance(x, list):
            pila.extend(reversed(x))
    raise ValueError("respuesta sin audio")


def _llamar(cuerpo: dict, clave: str, timeout: float) -> dict:
    url = URL_INTERACCIONES if "input" in cuerpo else URL.format(modelo=MODELO)
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), method="POST",
                                 headers={"x-goog-api-key": clave, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 - URL fija
        return json.load(r)


def carpeta_cache() -> Path:
    return salidas() / "voz_cache"


def trocear(texto: str, maximo: int | None = None) -> list[str]:
    """Trozos de <= maximo caracteres cortando por frases; una frase mas larga, por comas y si no, por espacios.
    " ".join(trozos) == texto normalizado (espacios seguidos -> uno): no se pierde ni se anade nada."""
    maximo = maximo or TROZO_MAX
    texto = " ".join(texto.split())
    if not texto:
        return []
    trozos: list[str] = []
    for grupo in _cortar_lista(re.split(r"(?<=[.!?…])\s+", texto), maximo):
        if len(grupo) <= maximo:
            trozos.append(grupo)
            continue
        for sub in _cortar_lista(re.split(r"(?<=[,;:])\s+", grupo), maximo):
            trozos.extend([sub] if len(sub) <= maximo else _cortar_lista(sub.split(" "), maximo))
    return trozos


def _cortar_lista(frases: list[str], maximo: int) -> list[str]:
    """Junta piezas seguidas (separadas por un espacio) mientras quepan en `maximo`; una pieza enorme va sola."""
    trozos, actual = [], ""
    for f in frases:
        candidato = f"{actual} {f}" if actual else f
        if actual and len(candidato) > maximo:
            trozos.append(actual)
            actual = f
        else:
            actual = candidato
    if actual:
        trozos.append(actual)
    return trozos


def _clave_cache(trozo: str, voz: str, estilo: str) -> str:
    return hashlib.sha256("".join((MODELO, voz, estilo or "", trozo)).encode("utf-8")).hexdigest()[:32]


def _pcm_de(datos: bytes, mime: str) -> tuple[bytes, int]:
    """(PCM 16 bits mono, tasa) de lo que devuelva la API: WAV entero o PCM crudo con la tasa en el mime."""
    if datos[:4] == b"RIFF":
        import io
        with wave.open(io.BytesIO(datos)) as w:
            return w.readframes(w.getnframes()), w.getframerate()
    tasa = TASA
    if "rate=" in (mime or ""):
        tasa = int(mime.split("rate=")[1].split(";")[0])
    return datos, tasa


def _leer_cache(ruta: Path) -> tuple[bytes, int] | None:
    try:
        with wave.open(str(ruta)) as w:
            return w.readframes(w.getnframes()), w.getframerate()
    except (OSError, EOFError, wave.Error):
        return None


def _escribir_wav(destino: Path, pcm: bytes, tasa: int) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(tasa)
        w.writeframes(pcm)
    tmp.replace(destino)


def _esperar_cupo(maximo_s: float = 65) -> bool:
    """Espera a que quede hueco en el cupo por minuto (solo entre trozos de un mismo texto)."""
    fin = time.monotonic() + maximo_s
    while time.monotonic() < fin:
        if _reservar():
            return True
        time.sleep(1)
    return False


def _sintetizar(trozo: str, voz: str, estilo: str, clave: str, llamar, timeout: float) -> tuple[bytes, int]:
    try:
        try:
            d = llamar(cuerpo_interaccion(trozo, voz, estilo), clave, timeout)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 429):
                raise
            log.info("voz Gemini: Interactions API HTTP %s; pruebo generateContent sin estilo", e.code)
            d = llamar(cuerpo_clasico(trozo, voz), clave, timeout)
        datos, mime = audio_de(d)
        return _pcm_de(base64.b64decode(datos), mime)
    except urllib.error.HTTPError as e:
        raise SinVoz(f"Gemini TTS HTTP {e.code}") from None
    except Exception as e:   # noqa: BLE001 - red, JSON raro, sin audio...
        raise SinVoz(f"Gemini TTS fallo: {type(e).__name__}") from None


def narrar(texto: str, destino: Path, voz: str = VOZ, llamar=_llamar, timeout: float = 150,
           estilo: str = ESTILO) -> Path:
    """Texto -> WAV con la voz de Gemini, troceado y con cache. SinVoz si no se puede (el motivo va al log, nunca
    la clave). Lo que ya esta en cache no necesita clave ni cupo."""
    trozos = trocear(texto) or [texto]
    cache = carpeta_cache()
    clave: str | None = None
    partes: list[bytes] = []
    tasa_final: int | None = None
    pedidos = 0
    for trozo in trozos:
        ruta = cache / f"{_clave_cache(trozo, voz, estilo)}.wav"
        hit = _leer_cache(ruta)
        if hit is None:
            if clave is None:
                clave = valor("gemini.api_key", "") or ""
            if not clave:
                raise SinVoz("sin clave de Gemini")
            if not _reservar():
                if pedidos == 0 or not _esperar_cupo():
                    raise SinVoz(f"cupo de {CUPO_MINUTO} audios por minuto agotado")
            hit = _sintetizar(trozo, voz, estilo, clave, llamar, timeout)
            pedidos += 1
            try:
                _escribir_wav(ruta, *hit)
            except OSError as e:    # sin cache no se pierde el audio: solo se pedira otra vez
                log.info("voz Gemini: no pude guardar en cache (%s)", type(e).__name__)
        pcm, tasa = hit
        if tasa_final is None:
            tasa_final = tasa
        elif tasa != tasa_final:
            raise SinVoz(f"trozos con tasas distintas ({tasa_final} y {tasa} Hz)")
        partes.append(pcm)
    destino = Path(destino)
    pcm = b"".join(partes)
    _escribir_wav(destino, pcm, tasa_final or TASA)
    log.info("voz Gemini: %s (%.1f s, %d trozos, %d pedidos)", destino.name, len(pcm) / 2 / (tasa_final or TASA),
             len(trozos), pedidos)
    return destino
