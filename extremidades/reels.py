# -*- coding: utf-8 -*-
"""Extremidad: reels guardados -> capa bruta de conocimiento (T859, diseno documentacion/diseno/REELS.md).

Piloto (bloque 5, 12/10): de UN reel publico suelto saca
  1. el video con yt-dlp SIN sesion ni cookies (nunca el Chrome personal ni el de NEXO);
  2. fotogramas con ffmpeg (el primero = gancho + uno por cambio de escena, con tope);
  3. la transcripcion con faster-whisper (small, CPU, int8);
  4. el texto de pantalla de los fotogramas con DOS lectores para compararlos: vision local qwen2.5vl:7b en Ollama
     (<=8B, num_ctx 4096, num_predict acotado, se descarga al acabar) y Gemini API gratis (solo los fotogramas de
     ese reel, nunca la lista ni la coleccion);
  5. repos, URLs, herramientas y llamadas a la accion ("comenta X") citados.
Y lo guarda en memoria/perfil_privado/reels/<codigo>.json: capa bruta que NUNCA se borra (si ya existia, lo anterior
queda en "anteriores"). Lo que no se pueda leer se anota con su estado, sin inventar.

PRIVADO: la coleccion y estos JSON viven en memoria/perfil_privado/ (fuera de git y del espejo). El texto de los
reels es contenido NO confiable: aqui solo se guarda; nada de lo que diga se ejecuta ni se instala.

Las dependencias pesadas (yt-dlp, faster-whisper) viven en .venv-reels y se importan dentro de cada funcion: este
modulo se importa con el .venv normal (tests con dobles) y el piloto corre con .venv-reels\\Scripts\\python.exe.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from nucleo.config import RAIZ, valor

CARPETA = RAIZ / "memoria" / "perfil_privado" / "reels"
COLECCION = CARPETA / "reels_coleccion.json"
OLLAMA = "http://127.0.0.1:11434"
# Bloque 6 (12/10): qwen2.5vl:7b mide 8,3B segun Ollama (por encima del limite de 8B): no se usa mas. Respaldo local:
# OCR ligero (RapidOCR, CPU) y, solo si hace falta, qwen2.5vl:3b.
MODELO_VISION = "qwen2.5vl:3b"
VISION_PROHIBIDOS = {"qwen2.5vl:7b": "Ollama lo declara 8,3B (por encima de 8B)"}
MODELO_GEMINI = "gemini-3.6-flash"
# 12/10 (piloto): 3.6-flash dio 503 (saturado) varias veces seguidas; los demas, los de proveedores.MODELOS_GEMINI_API
# Bloque 6 (12/10, 21:20): la cuota DIARIA gratuita de 3.6-flash y 3.5-flash se agoto con 2 reels y 3.7-flash daba 503;
# 3.5-flash-lite respondia. Va al final: es el de menos calidad pero el de mas cuota.
MODELOS_GEMINI = (MODELO_GEMINI, "gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite")
MODELO_WHISPER = "small"
MAX_FOTOGRAMAS = 12
UMBRAL_ESCENA = 0.30
NUM_CTX = 4096
NUM_PREDICT = 400
MAX_SALIDA_GEMINI = 16384
PROMPT_PANTALLA = (
    "Transcribe EXACTAMENTE todo el texto visible en la imagen, tal cual (respeta mayusculas, guiones, barras y "
    "puntos; es importante para nombres de repositorios de GitHub, usuarios y URLs). No traduzcas, no resumas, no "
    "describas la imagen. Si no hay texto, responde solo: VACIO")


class NoDescargable(RuntimeError):
    """El reel no se ha podido bajar sin sesion (privado, borrado, bloqueado...)."""


def _tam_param(modelo: str) -> float | None:
    m = re.search(r":(\d+(?:\.\d+)?)b\b", modelo.lower())
    return float(m.group(1)) if m else None


# ------------------------------------------------------------------ 1. descarga
def opciones_ytdlp(destino: Path) -> dict:
    """Opciones de yt-dlp: sin cookies ni navegador, un solo video, nombre fijo."""
    return {"outtmpl": str(destino / "%(id)s.%(ext)s"), "format": "mp4/best", "noplaylist": True, "quiet": True,
            "no_warnings": True, "cookiefile": None, "cookiesfrombrowser": None, "writeinfojson": False,
            "retries": 2, "socket_timeout": 30}


def descargar(url: str, destino: Path, ydl_cls=None) -> dict:
    """Baja el video. Devuelve {"video", "titulo", "duracion", "subido"}. NoDescargable si no se puede."""
    if ydl_cls is None:
        from yt_dlp import YoutubeDL as ydl_cls   # noqa: N813 - solo existe en .venv-reels
    destino.mkdir(parents=True, exist_ok=True)
    opts = opciones_ytdlp(destino)
    assert not opts["cookiefile"] and not opts["cookiesfrombrowser"], "nunca con sesion"
    try:
        with ydl_cls(opts) as y:
            info = y.extract_info(url, download=True)
            ruta = Path(y.prepare_filename(info))
    except Exception as e:   # noqa: BLE001 - DownloadError, red, login requerido...
        raise NoDescargable(f"{type(e).__name__}: {str(e)[:200]}") from None
    if not ruta.exists():
        raise NoDescargable("yt-dlp no dejo el archivo")
    return {"video": ruta, "titulo": info.get("title") or "", "duracion": info.get("duration"),
            "subido": info.get("upload_date") or ""}


# ------------------------------------------------------------------ 2. fotogramas
def orden_fotogramas(video: Path, carpeta: Path, umbral: float = UMBRAL_ESCENA, maximo: int = MAX_FOTOGRAMAS) -> list[str]:
    """ffmpeg: el primer fotograma (gancho) y uno por cambio de escena, a 720 px de ancho, como mucho `maximo`."""
    filtro = f"select='eq(n\\,0)+gt(scene\\,{umbral})',scale=720:-2"
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vf", filtro,
            "-fps_mode", "vfr", "-frames:v", str(maximo), "-q:v", "3", str(carpeta / "f%02d.jpg")]


def fotogramas(video: Path, carpeta: Path, correr=subprocess.run) -> list[Path]:
    carpeta.mkdir(parents=True, exist_ok=True)
    correr(orden_fotogramas(video, carpeta), check=True, capture_output=True, timeout=300)
    fotos = sorted(carpeta.glob("f*.jpg"))
    if len(fotos) < 3:   # video sin cortes: uno cada 3 s
        for f in fotos:
            f.unlink()
        correr(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vf",
                "fps=1/3,scale=720:-2", "-frames:v", str(MAX_FOTOGRAMAS), "-q:v", "3", str(carpeta / "f%02d.jpg")],
               check=True, capture_output=True, timeout=300)
        fotos = sorted(carpeta.glob("f*.jpg"))
    return fotos


# ------------------------------------------------------------------ 3. transcripcion
def transcribir(video: Path, modelo_cls=None, modelo: str = MODELO_WHISPER) -> dict:
    if modelo_cls is None:
        from faster_whisper import WhisperModel as modelo_cls   # noqa: N813 - solo en .venv-reels
    m = modelo_cls(modelo, device="cpu", compute_type="int8")
    segs, info = m.transcribe(str(video), vad_filter=True, beam_size=5)
    lista = [{"ini": round(s.start, 1), "fin": round(s.end, 1), "texto": s.text.strip()} for s in segs]
    return {"idioma": getattr(info, "language", ""), "texto": " ".join(s["texto"] for s in lista), "segmentos": lista}


# ------------------------------------------------------------------ 4. texto de pantalla
def _post(url: str, cuerpo: dict, cabeceras: dict | None = None, timeout: float = 300) -> dict:
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **(cabeceras or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 - URLs fijas
        return json.load(r)


def _b64(p: Path) -> str:
    return base64.b64encode(Path(p).read_bytes()).decode()


def cuerpo_ollama(foto: Path, modelo: str = MODELO_VISION, ultimo: bool = False) -> dict:
    return {"model": modelo, "prompt": PROMPT_PANTALLA, "images": [_b64(foto)], "stream": False,
            "options": {"num_ctx": NUM_CTX, "num_predict": NUM_PREDICT, "temperature": 0},
            "keep_alive": 0 if ultimo else "5m"}


def pantalla_local(fotos: list[Path], modelo: str = MODELO_VISION, post=_post) -> list[str]:
    """Un fotograma por peticion (num_ctx 4096 no da para varios). Nunca un modelo de mas de 8B."""
    tam = _tam_param(modelo)
    if modelo in VISION_PROHIBIDOS:
        raise ValueError(f"{modelo}: {VISION_PROHIBIDOS[modelo]}; en Ollama solo modelos de 8B o menos sin Damian delante")
    if tam is None or tam > 8:
        raise ValueError(f"{modelo}: en Ollama solo modelos de 8B o menos sin Damian delante")
    salida = []
    for i, f in enumerate(fotos):
        r = post(f"{OLLAMA}/api/generate", cuerpo_ollama(f, modelo, ultimo=i == len(fotos) - 1))
        salida.append((r.get("response") or "").strip())
    return salida


def cuerpo_gemini(fotos: list[Path]) -> dict:
    """Solo los fotogramas de UN reel y la instruccion: nada de la coleccion, del autor ni del pie de foto."""
    partes = [{"text": PROMPT_PANTALLA + "\nHay varias imagenes: responde con una linea por imagen, en orden, con "
                                         "el formato 'N: texto' (N empieza en 1)."}]
    partes += [{"inline_data": {"mime_type": "image/jpeg", "data": _b64(f)}} for f in fotos]
    # 12/10 (piloto): con 12 imagenes y tope 2048 el modelo gastaba ~2000 tokens en pensar y respondia VACIO
    # (finishReason MAX_TOKENS). El tope cubre el pensamiento y la respuesta.
    return {"contents": [{"parts": partes}], "generationConfig": {"temperature": 0, "maxOutputTokens": MAX_SALIDA_GEMINI}}


def pantalla_gemini(fotos: list[Path], modelo: str = MODELO_GEMINI, post=_post) -> list[str]:
    clave = valor("gemini.api_key", "") or ""
    if not clave:
        raise RuntimeError("sin clave de Gemini")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    r = post(url, cuerpo_gemini(fotos), {"x-goog-api-key": clave})
    texto = "".join(p.get("text", "") for c in r.get("candidates", []) for p in c.get("content", {}).get("parts", []))
    fin = [c.get("finishReason") for c in r.get("candidates", [])]
    if fin and fin[0] not in ("STOP", None):      # cortada: no se devuelve un vacio como si no hubiera texto
        raise RuntimeError(f"Gemini corto la respuesta ({fin[0]}, {len(texto)} caracteres)")
    por_n: dict[int, list[str]] = {}
    actual = None
    for linea in texto.splitlines():
        m = re.match(r"\s*(\d+)\s*[:.)-]\s*(.*)", linea)
        if m and 1 <= int(m.group(1)) <= len(fotos):
            actual = int(m.group(1))
            por_n.setdefault(actual, []).append(m.group(2))
        elif actual is not None and linea.strip():
            por_n[actual].append(linea.strip())
    return [" ".join(por_n.get(i + 1, [])).strip() for i in range(len(fotos))]


def pantalla_gemini_respaldo(fotos: list[Path], post=_post) -> tuple[list[str], str]:
    """Prueba los modelos de MODELOS_GEMINI en orden si uno esta saturado o sin cuota (429/500/503).
    Devuelve (textos, modelo que respondio)."""
    import urllib.error
    ultimo: Exception | None = None
    for modelo in MODELOS_GEMINI:
        try:
            return pantalla_gemini(fotos, modelo=modelo, post=post), modelo
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 503):
                raise
            ultimo = e
    raise ultimo or RuntimeError("sin modelos de Gemini")


# ------------------------------------------------------------------ 4 bis. lectura densa (bloque 6, ficha completa)
# Muestreo denso: 1 fotograma por segundo y fuera los casi repetidos (mpdecimate), con el indice en el nombre
# (-frame_pts). Si la ficha sale incompleta, re-muestreo a 2/s y recortes ampliados (x2) para la letra pequena de
# las listas. Un fotograma nitido en el que nadie lee texto queda "revisar", nunca vacio.
FPS_DENSO = 1
FPS_RELECTURA = 2
MAX_DENSOS = 120
TROZO_GEMINI = 16          # menos peticiones por reel: la cuota diaria es lo que limita
UMBRAL_BORROSO = 9.0          # lavfi.blur de ffmpeg (piloto 12/10: nitidos 3,8-8; movidos 10-16)
CONFIANZA_OCR = 0.5
RECORTES = ((0.0, 0.40), (0.30, 0.40), (0.60, 0.40))   # (y inicial, alto) en fraccion del alto, con solape
PROMPT_BLOQUES = (
    "Transcribe EXACTAMENTE todo el texto visible en cada imagen, tal cual (respeta mayusculas, guiones, barras, "
    "puntos y saltos de linea; es importante para nombres de repositorios de GitHub, usuarios, URLs y listas "
    "numeradas). No traduzcas, no resumas, no describas. Formato: para cada imagen una linea '### N' (N empieza en 1) "
    "y debajo su texto linea a linea. Si una imagen no tiene texto, debajo de su '### N' escribe solo: VACIO")


def es_vacio(texto: str | None) -> bool:
    return not texto or texto.strip().strip(".").upper() in ("VACIO", "VACÍO", "EMPTY", "")


def orden_densos(video: Path, carpeta: Path, fps: int = FPS_DENSO, prefijo: str = "d", desde: float | None = None,
                 hasta: float | None = None, maximo: int = MAX_DENSOS) -> list[str]:
    """ffmpeg: `fps` fotogramas por segundo sin los casi repetidos; el nombre lleva el indice (pts) del fotograma."""
    corte = (["-ss", f"{desde:.2f}"] if desde else []) + (["-to", f"{hasta:.2f}"] if hasta else [])
    filtro = f"fps={fps},mpdecimate=hi=64*12:lo=64*5:frac=0.33,scale=720:-2"
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *corte, "-i", str(video), "-vf", filtro,
            "-fps_mode", "vfr", "-frame_pts", "1", "-frames:v", str(maximo), "-q:v", "3",
            str(carpeta / f"{prefijo}%05d.jpg")]


def fotogramas_densos(video: Path, carpeta: Path, fps: int = FPS_DENSO, prefijo: str = "d", desde: float | None = None,
                      hasta: float | None = None, correr=subprocess.run) -> list[dict]:
    """[{"foto": Path, "t": segundos}] en orden. Lo de una pasada anterior con el mismo prefijo se sustituye."""
    carpeta.mkdir(parents=True, exist_ok=True)
    for f in carpeta.glob(f"{prefijo}[0-9]*.jpg"):
        f.unlink()
    correr(orden_densos(video, carpeta, fps, prefijo, desde, hasta), check=True, capture_output=True, timeout=600)
    salida = []
    for f in sorted(carpeta.glob(f"{prefijo}[0-9]*.jpg")):
        n = int(re.sub(r"\D", "", f.stem) or 0)
        salida.append({"foto": f, "t": round((desde or 0) + n / fps, 1)})
    return salida


def orden_recorte(foto: Path, destino: Path, y: float, alto: float) -> list[str]:
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(foto), "-vf",
            f"crop=iw:ih*{alto}:0:ih*{y},scale=iw*2:-2", "-q:v", "2", str(destino)]


def recortes(foto: Path, carpeta: Path, correr=subprocess.run) -> list[Path]:
    """Tres franjas horizontales con solape, ampliadas x2 (letra pequena de listas y tarjetas)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    salida = []
    for i, (y, alto) in enumerate(RECORTES, 1):
        destino = carpeta / f"{foto.stem}_r{i}.jpg"
        correr(orden_recorte(foto, destino, y, alto), check=True, capture_output=True, timeout=60)
        salida.append(destino)
    return salida


def borrosidad(foto: Path, correr=subprocess.run) -> float | None:
    """lavfi.blur de ffmpeg (mas alto = mas borroso). None si no se puede medir."""
    try:
        r = correr(["ffmpeg", "-hide_banner", "-i", str(foto), "-vf", "blurdetect,metadata=print:file=-", "-f",
                    "null", "-"], capture_output=True, text=True, timeout=60)
        m = re.search(r"lavfi\.blur=([\d.]+)", (r.stdout or "") + (r.stderr or ""))
        return float(m.group(1)) if m else None
    except Exception:   # noqa: BLE001 - sin medida, el fotograma se trata como nitido (revisar)
        return None


def cuerpo_gemini_bloques(fotos: list[Path]) -> dict:
    """Solo las imagenes de UN reel y la instruccion: nada de la coleccion, del autor ni del pie de foto."""
    partes = [{"text": PROMPT_BLOQUES}] + [{"inline_data": {"mime_type": "image/jpeg", "data": _b64(f)}} for f in fotos]
    return {"contents": [{"parts": partes}], "generationConfig": {"temperature": 0, "maxOutputTokens": MAX_SALIDA_GEMINI}}


def partir_bloques(texto: str, n: int) -> list[str]:
    por_n: dict[int, list[str]] = {}
    actual = None
    for linea in (texto or "").splitlines():
        m = re.match(r"\s*#{2,4}\s*(\d+)\s*$", linea)
        if m and 1 <= int(m.group(1)) <= n:
            actual = int(m.group(1))
            por_n.setdefault(actual, [])
        elif actual is not None:
            por_n[actual].append(linea.rstrip())
    return ["\n".join(por_n.get(i + 1, [])).strip() for i in range(n)]


ESPERAS_SATURADO = (30, 75)   # s de espera antes de cada nueva ronda si TODOS los modelos dan 429/500/503


class SinCuotaGemini(RuntimeError):
    """Todos los modelos de Gemini tienen la cuota del dia agotada: no se espera, se sigue otro dia."""


_AGOTADOS: dict[str, set[str]] = {}   # dia -> modelos con la cuota diaria agotada (en este proceso)

# Bloque 6b (12/10): Gemini API no da cuota legible y el tribunal la usa. El lote de reels solo gasta una FRACCION
# del dia (nucleo/cuota.py lleva la cuenta). Configurable en memoria/perfil_privado/reels/config.json.
CONFIG = CARPETA / "config.json"
CONFIG_DEFECTO = {"gemini_fraccion_diaria": 0.20,   # parte de la cuota diaria de Gemini API que puede gastar el lote
                  "gemini_peticiones_dia": 200,     # ESTIMACION del total diario (Google no lo da): se ajusta aqui
                  "una_noche": False,               # si True, tras una noche el turno se apaga y deja la muestra
                  "crear_propuestas": True,         # si False, las propuestas se calculan pero no se crean
                  "rehacer_todas": True,            # Bloque 10: sin reels nuevos, el turno rehace las fichas viejas (sin propuestas)
                  "vision_primero": False}          # Bloque 18: True = la vision de NVIDIA lee TODOS los fotogramas antes que el OCR
CONSUMIDOR = "reels"


def config_lote(ruta: Path | None = None) -> dict:
    try:
        datos = json.loads((ruta or CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        datos = {}
    return {**CONFIG_DEFECTO, **{k: v for k, v in datos.items() if k in CONFIG_DEFECTO}}


class PresupuestoGemini:
    """Tope diario del lote de reels sobre Gemini API (cuenta propia en nucleo/cuota.py)."""

    def __init__(self, fraccion: float | None = None, total: int | None = None):
        c = config_lote()
        self.fraccion = c["gemini_fraccion_diaria"] if fraccion is None else fraccion
        self.total = c["gemini_peticiones_dia"] if total is None else total

    def permite(self) -> bool:
        from nucleo import cuota
        return cuota.permite("gemini_api", CONSUMIDOR, self.total, self.fraccion)

    def gastar(self) -> None:
        from nucleo import cuota
        cuota.gastar("gemini_api", CONSUMIDOR)

    def resumen(self) -> dict:
        from nucleo import cuota
        return {"gastadas_hoy": cuota.gastado_hoy("gemini_api", CONSUMIDOR),
                "tope_dia": cuota.tope_diario(self.total, self.fraccion)}


def _presupuesto(post, presupuesto):
    """El indicado; por defecto el real solo en la ruta real (con un `post` de prueba, sin tope)."""
    if presupuesto is not None:
        return presupuesto or None
    return PresupuestoGemini() if post is _post else None


def _cuota_diaria(e) -> bool:
    """429 por cuota DIARIA (quotaId ...PerDay...), no por minuto."""
    try:
        cuerpo = e.read() if getattr(e, "fp", None) else b""
        return b"PerDay" in (cuerpo or b"")
    except Exception:   # noqa: BLE001
        return False


def agotados_hoy() -> set[str]:
    return _AGOTADOS.setdefault(datetime.now().strftime("%Y-%m-%d"), set())


def gemini_respaldo(cuerpo: dict, post=_post, dormir=time.sleep, presupuesto=None) -> tuple[str, str]:
    """Texto de Gemini con respaldo entre modelos y, si todos estan saturados (429 por minuto, 500, 503), rondas con
    espera (backoff). Un modelo con la cuota DIARIA agotada se salta el resto del dia; si estan todos, SinCuotaGemini
    sin esperar. Con `presupuesto` (tope diario del lote), cada peticion se cuenta y, agotado, SinCuotaGemini.
    Devuelve (texto, modelo)."""
    import urllib.error
    clave = valor("gemini.api_key", "") or ""
    if not clave:
        raise RuntimeError("sin clave de Gemini")
    ultimo: Exception | None = None
    for ronda, espera in enumerate((0, *ESPERAS_SATURADO)):
        vivos = [m for m in MODELOS_GEMINI if m not in agotados_hoy()]
        if not vivos:
            raise SinCuotaGemini("cuota diaria de Gemini agotada en todos los modelos")
        if espera:
            dormir(espera)
        for modelo in vivos:
            if presupuesto is not None and not presupuesto.permite():
                raise SinCuotaGemini("presupuesto diario de Gemini del lote de reels agotado")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
            try:
                if presupuesto is not None:
                    presupuesto.gastar()
                r = post(url, cuerpo, {"x-goog-api-key": clave})
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 503):
                    raise
                if e.code == 429 and _cuota_diaria(e):
                    agotados_hoy().add(modelo)
                ultimo = e
                continue
            texto = "".join(p.get("text", "") for c in r.get("candidates", [])
                            for p in c.get("content", {}).get("parts", []))
            fin = [c.get("finishReason") for c in r.get("candidates", [])]
            if fin and fin[0] not in ("STOP", None):
                raise RuntimeError(f"Gemini corto la respuesta ({fin[0]}, {len(texto)} caracteres)")
            return texto, modelo
    if not [m for m in MODELOS_GEMINI if m not in agotados_hoy()]:
        raise SinCuotaGemini("cuota diaria de Gemini agotada en todos los modelos")
    raise ultimo or RuntimeError("sin modelos de Gemini")


def gemini_bloques(fotos: list[Path], post=_post, dormir=time.sleep, presupuesto=None) -> tuple[list[str], str]:
    """Lee hasta TROZO_GEMINI imagenes conservando los saltos de linea."""
    texto, modelo = gemini_respaldo(cuerpo_gemini_bloques(fotos), post, dormir, presupuesto)
    return partir_bloques(texto, len(fotos)), modelo


def _filas_ocr(resultado) -> str:
    """Cajas de RapidOCR -> texto por filas (arriba a abajo, izquierda a derecha)."""
    cajas = []
    for caja, texto, conf in resultado or []:
        if float(conf) < CONFIANZA_OCR or not str(texto).strip():
            continue
        ys = [p[1] for p in caja]
        xs = [p[0] for p in caja]
        cajas.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), str(texto).strip()))
    cajas.sort()
    filas: list[list] = []
    for c in cajas:
        if filas and abs(c[0] - filas[-1][0][0]) <= max(4.0, c[1] / 2):
            filas[-1].append(c)
        else:
            filas.append([c])
    return "\n".join(" ".join(x[3] for x in sorted(f, key=lambda x: x[2])) for f in filas)


def ocr_local(fotos: list[Path], motor=None) -> list[str]:
    """OCR ligero en CPU (RapidOCR sobre onnxruntime), sin GPU ni modelo grande."""
    if motor is None:
        from rapidocr_onnxruntime import RapidOCR   # noqa: N813 - solo en .venv-reels (A0044)
        motor = RapidOCR()
    return [_filas_ocr(motor(str(f))[0]) for f in fotos]


def modelo_ollama_disponible(modelo: str = MODELO_VISION, get=None) -> bool:
    try:
        if get is None:
            with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5) as r:   # noqa: S310 - URL fija local
                datos = json.load(r)
        else:
            datos = get(f"{OLLAMA}/api/tags")
        return any(m.get("name") == modelo for m in datos.get("models", []))
    except Exception:   # noqa: BLE001
        return False


TROZO_NVIDIA = 8              # imagenes por peticion a la vision de NVIDIA (medido 24/10: 8 fotogramas = ~48 s)
TIMEOUT_NVIDIA_VISION = 240


def nvidia_bloques(fotos: list[Path], post=None) -> tuple[list[str], str]:
    """Texto de hasta TROZO_NVIDIA fotogramas con la vision gratuita de NVIDIA (nemotron-3.5-super-vl, "Free Endpoint";
    bloque 18). Mismo formato '### N' que Gemini. Solo las imagenes de UN reel y la instruccion. RuntimeError si no
    responde bien (la cascada sigue con el siguiente lector)."""
    import proveedores as P
    from nucleo.enfriamiento import enfriado
    from nucleo import modelos_estado
    modelo = P.MODELO_NVIDIA_VISION
    prov = P.NvidiaProvider(modelos=(modelo,))
    clave = prov._clave()
    if not clave or enfriado("nvidia") or not modelos_estado.en_uso("nvidia", (modelo,)):
        raise RuntimeError("vision de NVIDIA no disponible (sin clave, enfriada o fuera de uso)")
    contenido = [{"type": "text", "text": PROMPT_BLOQUES}] + [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + _b64(f)}} for f in fotos]
    cuerpo = {"model": modelo, "messages": [{"role": "user", "content": contenido}], "max_tokens": 4096, "temperature": 0}
    r = (post or _post_respuesta)(P.NvidiaProvider.URL, cuerpo, {"Authorization": f"Bearer {clave}"},
                                  TIMEOUT_NVIDIA_VISION)
    if r.status_code != 200:
        raise RuntimeError(f"vision de NVIDIA: HTTP {r.status_code}")
    texto = (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    return partir_bloques(texto, len(fotos)), modelo


def leer_fotogramas(fotos: list[Path], gemini=gemini_bloques, ocr=ocr_local, local=None,
                    medir=borrosidad, vision=None, vision_primero: bool = False) -> dict:
    """Cascada de lectores (bloque 6b: la cuota de Gemini se gasta solo donde hace falta): OCR local primero para
    todos los fotogramas; Gemini SOLO para los nitidos que el OCR no lea (por trozos); si se pasa `local`
    (qwen2.5vl:3b), vision local para lo que quede. Devuelve {"lecturas": [{foto, texto, lector, estado}],
    "errores": [...]}; estado = texto | sin_texto (borroso y sin texto) | revisar (nitido y nadie lee nada)."""
    lect = [{"foto": f.name, "texto": "", "lector": None, "estado": None} for f in fotos]
    errores: list[str] = []

    def leer_con(nombre: str, lector, indices: list[int]) -> None:
        try:
            textos = lector([fotos[i] for i in indices])
        except Exception as e:   # noqa: BLE001
            errores.append(f"{nombre}: {type(e).__name__}: {str(e)[:160]}")
            return
        for i, t in zip(indices, textos):
            if not es_vacio(t):
                lect[i].update(texto=t.strip(), lector="ocr" if nombre == "ocr" else f"local:{MODELO_VISION}")

    def por_trozos(nombre: str, lector, indices: list[int], trozo: int) -> None:
        for k in range(0, len(indices), trozo):
            parte = indices[k:k + trozo]
            try:
                textos, modelo = lector([fotos[i] for i in parte])
            except Exception as e:   # noqa: BLE001 - lo no leido pasa al siguiente lector
                errores.append(f"{nombre} {k + 1}-{k + len(parte)}: {type(e).__name__}: {str(e)[:160]}")
                continue
            for i, t in zip(parte, textos):
                if not es_vacio(t):
                    lect[i].update(texto=t.strip(), lector=f"{nombre}:{modelo}")

    if vision is not None and vision_primero:
        por_trozos("nvidia", vision, list(range(len(fotos))), TROZO_NVIDIA)
    if ocr is not None:
        leer_con("ocr", ocr, [i for i, x in enumerate(lect) if not x["texto"]])
    sin = [i for i, x in enumerate(lect) if not x["texto"]]
    borroso = {i: medir(fotos[i]) for i in sin}                 # una medida por fotograma sin texto
    if vision is not None and not vision_primero:   # bloque 18: la vision gratuita de NVIDIA antes que Gemini
        por_trozos("nvidia", vision, [i for i in sin if borroso[i] is None or borroso[i] <= UMBRAL_BORROSO],
                   TROZO_NVIDIA)
        sin = [i for i in sin if not lect[i]["texto"]]
    if gemini is not None:
        nitidos = [i for i in sin if borroso[i] is None or borroso[i] <= UMBRAL_BORROSO]
        for k in range(0, len(nitidos), TROZO_GEMINI):
            indices = nitidos[k:k + TROZO_GEMINI]
            try:
                textos, modelo = gemini([fotos[i] for i in indices])
            except Exception as e:   # noqa: BLE001 - lo no leido pasa al respaldo local
                errores.append(f"gemini {k + 1}-{k + len(indices)}: {type(e).__name__}: {str(e)[:160]}")
                continue
            for i, t in zip(indices, textos):
                if not es_vacio(t):
                    lect[i].update(texto=t.strip(), lector=f"gemini:{modelo}")
    faltan = [i for i, x in enumerate(lect) if not x["texto"]]
    if faltan and local is not None:
        leer_con("local", local, faltan)
    for i, x in enumerate(lect):
        if x["texto"]:
            x["estado"] = "texto"
        else:
            b = borroso.get(i)
            x["borrosidad"] = b
            x["estado"] = "sin_texto" if b is not None and b > UMBRAL_BORROSO else "revisar"
    return {"lecturas": lect, "errores": errores}


# ------------------------------------------------------------------ 5. citas
_GITHUB = re.compile(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", re.I)
_URL = re.compile(r"\bhttps?://[^\s)\]>\"']+|\b(?:www\.)[^\s)\]>\"']+", re.I)
_OWNER_REPO = re.compile(r"(?<![\w/.@-])([A-Za-z0-9][A-Za-z0-9-]{1,38}/[A-Za-z0-9_.-]{2,100})(?![\w/])")
# GitHub escribe "dueño / repo" con espacios en la cabecera del repo (piloto 12/10: morluto / rea se perdia).
_OWNER_REPO_ESP = re.compile(r"(?<![\w/.@-])([A-Za-z0-9][A-Za-z0-9-]{1,38}) / ([A-Za-z0-9_.-]{2,100})(?![\w/])")
_CTA = re.compile(r"\b(?:comenta|comment|escr[ií]beme|dm me|type)\s+[\"“'‘«]?([A-Za-z0-9áéíóúñ]+)", re.I)


def extraer_citas(*textos: str) -> dict:
    """Repos (owner/repo), URLs y llamadas a la accion citados en pie, transcripcion o pantalla. Sin inventar: solo
    lo que aparece escrito. Los owner/repo sueltos se marcan como 'posibles' (no se ha comprobado que existan)."""
    todo = "\n".join(t for t in textos if t)
    todo = _OWNER_REPO_ESP.sub(lambda m: f"{m.group(1)}/{m.group(2)}", todo)
    repos = sorted({m.rstrip(".") for m in _GITHUB.findall(todo)}, key=str.lower)
    urls = sorted({u.rstrip(".,") for u in _URL.findall(todo)} - {f"https://github.com/{r}" for r in repos})
    posibles = sorted({m.rstrip(".") for m in _OWNER_REPO.findall(todo)
                       if m.rstrip(".") not in repos and not re.match(r"^\d+/\d+", m) and "." not in m.split("/")[0]},
                      key=str.lower)
    ctas = sorted({c.upper() for c in _CTA.findall(todo)})
    return {"repos": repos, "repos_posibles": posibles, "urls": urls, "llamadas_accion": ctas}


# ------------------------------------------------------------------ guardar
def guardar_bruto(codigo: str, datos: dict, carpeta: Path | None = None, sufijo: str = ".json") -> Path:
    """Capa bruta: nunca se borra. Si ya habia un JSON del reel, el anterior entero queda en 'anteriores'.
    Con sufijo ".ficha.json" guarda la ficha con la misma regla."""
    carpeta = carpeta or CARPETA
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{codigo}{sufijo}"
    previo = None
    if ruta.exists():
        previo = json.loads(ruta.read_text(encoding="utf-8"))
    nuevo = dict(datos, codigo=codigo, guardado=datetime.now().isoformat(timespec="seconds"))
    if previo:
        anteriores = previo.pop("anteriores", [])
        nuevo["anteriores"] = anteriores + [previo]
    tmp = ruta.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(nuevo, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ruta)
    return ruta


# ------------------------------------------------------------------ piloto
def reel_de_coleccion(codigo: str, coleccion: Path | None = None) -> dict:
    datos = json.loads((coleccion or COLECCION).read_text(encoding="utf-8"))
    for r in datos["reels"]:
        if r["codigo"] == codigo:
            return r
    raise KeyError(codigo)


def analizar(codigo: str, lectores=("local", "gemini"), coleccion: Path | None = None) -> dict:
    """Todo el proceso para UN reel, con el tiempo de cada paso. Guarda la capa bruta y la devuelve."""
    r = reel_de_coleccion(codigo, coleccion)
    media = CARPETA / "media" / codigo
    d = {"url": r["url"], "autor": r.get("autor"), "pie": r.get("pie"), "colecciones": r.get("colecciones"),
         "categorias_preliminares": r.get("categorias_preliminares"), "tiempos_s": {}, "errores": {}}

    def paso(nombre, fn):
        t0 = time.perf_counter()
        try:
            return fn()
        except Exception as e:   # noqa: BLE001 - se anota y se sigue con lo que se pueda
            d["errores"][nombre] = f"{type(e).__name__}: {str(e)[:300]}"
            return None
        finally:
            d["tiempos_s"][nombre] = round(time.perf_counter() - t0, 1)

    v = paso("descarga", lambda: descargar(r["url"], media))
    if not v:
        d["estado"] = "no_descargable"
        d["citas"] = extraer_citas(r.get("pie") or "")
        guardar_bruto(codigo, d)
        return d
    d.update(titulo=v["titulo"], duracion_s=v["duracion"], subido=v["subido"])
    fotos = paso("fotogramas", lambda: fotogramas(v["video"], media / "fotogramas")) or []
    d["fotogramas"] = [f.name for f in fotos]
    d["transcripcion"] = paso("transcripcion", lambda: transcribir(v["video"])) or {}
    d["pantalla"] = {}
    if "local" in lectores and fotos:
        d["pantalla"]["local"] = {"modelo": MODELO_VISION, "textos": paso("pantalla_local", lambda: pantalla_local(fotos))}
    if "gemini" in lectores and fotos:
        r = paso("pantalla_gemini", lambda: pantalla_gemini_respaldo(fotos))
        d["pantalla"]["gemini"] = {"modelo": r[1] if r else None, "textos": r[0] if r else None}
    textos = [r.get("pie") or "", d["transcripcion"].get("texto", "")]
    d["citas_por_lector"] = {k: extraer_citas(*textos, *(x["textos"] or [])) for k, x in d["pantalla"].items()}
    d["citas"] = extraer_citas(*textos, *[t for x in d["pantalla"].values() for t in (x["textos"] or [])])
    d["estado"] = "analizado" if fotos and d["transcripcion"] else "parcial"
    guardar_bruto(codigo, d)
    return d


def releer_gemini(codigo: str, post=_post) -> dict:
    """Vuelve a leer con Gemini los fotogramas ya guardados de un reel y actualiza su capa bruta (lo anterior queda en
    'anteriores'). No descarga nada ni vuelve a pasar el lector local."""
    d = json.loads((CARPETA / f"{codigo}.json").read_text(encoding="utf-8"))
    d.pop("anteriores", None)
    fotos = [CARPETA / "media" / codigo / "fotogramas" / n for n in d.get("fotogramas") or []]
    t0 = time.perf_counter()
    d.setdefault("errores", {}).pop("pantalla_gemini", None)
    try:
        textos, modelo = pantalla_gemini_respaldo(fotos, post=post)
    except Exception as e:   # noqa: BLE001
        textos, modelo = None, None
        d["errores"]["pantalla_gemini"] = f"{type(e).__name__}: {str(e)[:300]}"
    d.setdefault("tiempos_s", {})["pantalla_gemini"] = round(time.perf_counter() - t0, 1)
    d.setdefault("pantalla", {})["gemini"] = {"modelo": modelo, "textos": textos}
    base = [d.get("pie") or "", (d.get("transcripcion") or {}).get("texto", "")]
    d["citas_por_lector"] = {k: extraer_citas(*base, *(x["textos"] or [])) for k, x in d["pantalla"].items()}
    d["citas"] = extraer_citas(*base, *[t for x in d["pantalla"].values() for t in (x["textos"] or [])])
    guardar_bruto(codigo, d)
    return d


# ------------------------------------------------------------------ bloque 6: ficha completa de un reel
PAUSA_GEMINI = 4.0            # s entre peticiones (piloto 12/10: 429 tras ~10 seguidas)
MAX_RECORTADOS = 3            # fotogramas de lista que se recortan y amplian en la relectura


def _con_pausa(fn, pausa: float = PAUSA_GEMINI, dormir=time.sleep):
    primera = [True]

    def envuelta(*a, **k):
        if not primera[0]:
            dormir(pausa)
        primera[0] = False
        return fn(*a, **k)
    return envuelta


TIMEOUT_NVIDIA_REELS = 420   # s: el modelo de razonamiento tarda en la ficha larga; el resto de roles sigue en 120 s
MAX_TOKENS_LIBRES = 12000     # la ficha de 20 elementos es larga; el modelo de razonamiento gasta parte pensando


class _Respuesta:
    """Lo minimo de httpx.Response que lee nucleo.fallos.cascada (aqui no hay httpx: .venv-reels solo trae urllib)."""

    def __init__(self, status: int, texto: str, cabeceras):
        self.status_code, self.text, self.headers = status, texto, dict(cabeceras or {})

    def json(self):
        return json.loads(self.text)


USER_AGENT = "NEXO-reels/1.0 (+local)"


def _post_respuesta(url: str, cuerpo: dict, cabeceras: dict, timeout: float) -> _Respuesta:
    import urllib.error
    # Bloque 18 (24/10): sin User-Agent propio, Cloudflare (Groq, OpenRouter) responde 403 al "Python-urllib" por defecto;
    # ese 403 se leia como clave mala y ENFRIABA a Groq para todo NEXO (tribunal incluido). proveedores.py va con httpx.
    peticion = urllib.request.Request(url, data=json.dumps(cuerpo).encode("utf-8"), method="POST",
                                      headers={"Content-Type": "application/json", "User-Agent": USER_AGENT,
                                               **cabeceras})
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as r:
            return _Respuesta(r.status, r.read().decode("utf-8", "replace"), r.headers)
    except urllib.error.HTTPError as e:
        return _Respuesta(e.code, e.read().decode("utf-8", "replace"), e.headers)


# los mejores de cada API para estructurar texto (banco T320): primero estos, luego el resto de los vivos
PREFERIDOS_LIBRES = ("nvidia/nemotron-3-ultra-550b-a55b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b",
                     "nvidia/nemotron-3.5-lightning-30b-a3b", "minimaxai/minimax-m3.1-flash")


class ProveedorLibre:
    """NVIDIA o Groq por urllib (mismas claves, modelos vivos, enfriamientos y tabla de fallos que proveedores.py)."""

    def __init__(self, prov, url: str, max_tokens: int | None = None):
        self.prov, self.url, self.max_tokens = prov, url, max_tokens
        self.nombre, self.ultimo_modelo = prov.nombre, ""

    def disponible(self) -> bool:
        return self.prov.disponible()

    def enviar(self, tarea: str):
        from nucleo import fallos
        from proveedores import Resultado
        clave = self.prov._clave()
        modelos = sorted(self.prov._vivos(), key=lambda m: PREFERIDOS_LIBRES.index(m) if m in PREFERIDOS_LIBRES else 99)
        if self.nombre == "openrouter":       # fail-closed como OpenRouterProvider: nunca un modelo de pago
            from proveedores import es_modelo_free
            modelos = [m for m in modelos if es_modelo_free(m)]
        if not clave or not modelos:
            return Resultado("NOT_AVAILABLE", detalle="sin clave o sin modelos vivos")
        cuerpo = {"messages": [{"role": "user", "content": tarea}]}
        if self.max_tokens:
            cuerpo["max_tokens"] = self.max_tokens
        r = fallos.cascada(self.nombre, modelos, self.prov.rondas, self.prov.espera,
                           pedir=lambda m: _post_respuesta(self.url, dict(cuerpo, model=m),
                                                           {"Authorization": f"Bearer {clave}"}, self.prov.timeout),
                           leer=lambda j: j["choices"][0]["message"]["content"])
        if r.ok:
            self.ultimo_modelo = r.meta.get("modelo", "")
        return r


def proveedores_libres() -> list:
    """NVIDIA, Groq y OpenRouter (solo `:free`): API gratuitas, sin tocar la cuota de Gemini, para la ficha de un reel.
    Bloque 18 (24/10): las 13 fichas del 22/10 las hizo Gemini (40 peticiones = el tope del dia) porque los tres modelos
    de NVIDIA de la config estaban retirados o sin servicio y Groq enfriado (User-Agent de urllib: 403). NVIDIA usa la
    lista de config.toml (24/10: ultra primero, todos con "Free Endpoint") y OpenRouter :free queda de tercer
    respaldo antes de Gemini."""
    import proveedores as P
    return [ProveedorLibre(P.NvidiaProvider(max_tokens=MAX_TOKENS_LIBRES, timeout=TIMEOUT_NVIDIA_REELS),
                           P.NvidiaProvider.URL, MAX_TOKENS_LIBRES),
            ProveedorLibre(P.GroqProvider(), P.GroqProvider.URL),
            ProveedorLibre(P.OpenRouterProvider(), P.OpenRouterProvider.URL)]


RONDAS_LIBRES = 4             # Bloque 18: rondas sobre los gratuitos antes de gastar Gemini (solo en la ruta real)
ESPERA_LIBRES = 110           # s entre rondas: un 429 en todos los modelos enfria Groq 5 min ("saturado")


def _merece_esperar(libres: list, probados: list) -> bool:
    """Esperar a los gratuitos solo si alguno fallo en esta ronda o esta enfriado por saturacion (pasa en minutos);
    con cuota diaria, clave mala o sin modelos, esperar no sirve: a Gemini."""
    from nucleo import enfriamiento
    if probados:
        return True
    enfriados = enfriamiento._leer()
    return any((enfriados.get(p.nombre) or {}).get("tipo") == "saturado" for p in libres)


def pedir_modelo(cuerpo: dict, post=_post, dormir=time.sleep, libres=None, presupuesto=None,
                 rondas: int | None = None) -> tuple[dict, str]:
    """Respuesta JSON del modelo para el prompt de `cuerpo` (formato Gemini): primero los proveedores gratuitos
    (NVIDIA, Groq, OpenRouter; el primero que devuelva un JSON valido), y solo si ninguno vale, Gemini API dentro del
    presupuesto diario del lote (SinCuotaGemini si se agota). Bloque 18: en la ruta real, si los gratuitos fallan por
    ritmo (Groq limita tokens por minuto) se espera y se reintenta hasta RONDAS_LIBRES rondas antes de gastar Gemini:
    el cupo de 40 peticiones se iba en los 429 de un minuto. Devuelve (json, "proveedor:modelo"). Con un `post` de
    prueba (o con `libres` dados) no se llama a nadie salvo a esos y hay una sola ronda."""
    from nucleo import reels_ficha as F
    reales = libres is None and post is _post
    if libres is None:
        libres = proveedores_libres() if post is _post else []
    if rondas is None:
        rondas = RONDAS_LIBRES if reales else 1
    prompt = cuerpo["contents"][0]["parts"][0]["text"]
    for ronda in range(max(1, rondas)):
        probados = []
        for p in libres:
            try:
                if not p.disponible():
                    continue
                probados.append(p.nombre)
                r = p.enviar(prompt)
                if r.ok:
                    return F.leer_json(r.texto), f"{p.nombre}:{getattr(p, 'ultimo_modelo', '') or r.meta.get('modelo', '')}"
            except Exception:   # noqa: BLE001 - sin servicio o JSON roto: siguiente proveedor
                continue
        if ronda + 1 < rondas and libres and _merece_esperar(libres, probados):
            dormir(ESPERA_LIBRES)
        else:
            break
    texto, modelo = gemini_respaldo(cuerpo, post, dormir, _presupuesto(post, presupuesto))
    return F.leer_json(texto), modelo


def pedir_ficha(mat: str, post=_post, dormir=time.sleep, libres=None, presupuesto=None) -> tuple[dict, str]:
    """Ficha propuesta (JSON) de UN reel: proveedores gratuitos primero, Gemini API con tope diario de respaldo."""
    from nucleo import reels_ficha as F
    return pedir_modelo(F.cuerpo(mat), post, dormir, libres, presupuesto)


def _es_lista(texto: str) -> bool:
    lineas = [x for x in (texto or "").splitlines() if x.strip()]
    return len(lineas) >= 4 or len(re.findall(r"(?m)^\s*\d{1,2}\s*[.)-]", texto or "")) >= 2


def tramo_lista(lecturas: list[dict]) -> tuple[float, float] | None:
    """Primer y ultimo segundo con fotogramas de lista (o con texto, si no hay listas)."""
    con = [x for x in lecturas if x.get("estado") == "texto" and _es_lista(x.get("texto", ""))] or \
          [x for x in lecturas if x.get("estado") == "texto"]
    if not con:
        return None
    return min(x["t"] for x in con), max(x["t"] for x in con) + 1


def _leer(fotos_t: list[dict], lectores: dict) -> tuple[list[dict], list[str]]:
    r = leer_fotogramas([x["foto"] for x in fotos_t], **lectores)
    for x, lec in zip(fotos_t, r["lecturas"]):
        lec["t"] = x["t"]
    return r["lecturas"], r["errores"]


def _citas_de(bruto: dict, lecturas: list[dict], pegado: list[dict]) -> dict:
    return extraer_citas(bruto.get("pie") or "", (bruto.get("transcripcion") or {}).get("texto", ""),
                         *[x.get("texto") or "" for x in lecturas], *[p.get("texto") or "" for p in pegado])


def _montar(bruto: dict, lecturas: list[dict], pegado: list[dict], post, resolver, cache,
            previa: dict | None = None, crudo: dict | None = None, modelo: str = "",
            libres=None, presupuesto=None, publico=None) -> tuple[dict, str, dict]:
    """Ficha comprobada: modelo -> normalizacion sin IA -> (lo verificado de la ficha previa) -> resolucion ->
    completitud; si faltan elementos, UNA pasada mas del modelo pidiendo solo lo que falta."""
    from nucleo import reels_ficha as F
    mat = F.material(bruto, lecturas, pegado)
    citas = _citas_de(bruto, lecturas, pegado)
    sin_red = crudo is not None                       # renormalizar con la respuesta ya guardada: nada sale del PC
    if not sin_red:
        crudo, modelo = pedir_ficha(mat, post=post, libres=libres, presupuesto=presupuesto)
    ficha = F.normalizar(crudo, mat, citas)
    F.fijar_promesa(ficha, F.promesa_texto(*F.gancho(bruto, lecturas)))
    F.conservar_anteriores(ficha, previa)
    res = resolver(ficha, cache=cache) if resolver else {}
    F.apartar_inexistentes(ficha)
    ficha["completitud"] = F.completitud(ficha)
    if ficha["completitud"]["faltan"] and not sin_red:
        try:
            mas = pedir_modelo(F.cuerpo_faltan(mat, ficha), post, libres=libres,
                               presupuesto=presupuesto)[0].get("elementos") or []
        except Exception:   # noqa: BLE001 - (tambien sin presupuesto) sin la segunda pasada la ficha queda incompleta (y lo dice)
            mas = []
        if mas:
            anterior = ficha
            crudo = dict(crudo, elementos=list(crudo.get("elementos") or []) + list(mas))
            ficha = F.normalizar(crudo, mat, citas)
            ficha["promesa"] = anterior["promesa"]
            F.conservar_anteriores(ficha, anterior)
            res = resolver(ficha, cache=cache) if resolver else {}
            F.apartar_inexistentes(ficha)
            ficha["completitud"] = F.completitud(ficha)
            ficha["segunda_pasada"] = len(mas)
    # T966: idioma (espanol, alfabeto latino) y 'para que' concreto y sin repetir: UN reintento al modelo con los fallos
    if not sin_red:
        problemas = F.revisar_calidad(ficha)
        if F.hay_problemas(problemas):
            try:
                arreglo = pedir_modelo(F.cuerpo_correccion(mat, ficha, problemas), post, libres=libres,
                                       presupuesto=presupuesto)[0]
                if F.aplicar_correccion(ficha, arreglo):
                    ficha["correccion_modelo"] = arreglo
            except Exception:   # noqa: BLE001 - sin el reintento, cerrar_calidad deja los fallos marcados
                pass
    elif (previa or {}).get("correccion_modelo"):           # --crudo: se repite el arreglo ya pedido, sin red
        ficha["correccion_modelo"] = previa["correccion_modelo"]
        F.aplicar_correccion(ficha, previa["correccion_modelo"])
    F.cerrar_calidad(ficha)
    # T890: lo prometido ("te mando el paper") se intenta resolver en publico antes de darlo por hueco
    if publico is None and post is _post:
        from nucleo import reels_publico
        publico = reels_publico.buscar_prometido
    from nucleo import reels_publico as RP
    previa_busq = (previa or {}).get("busqueda_publica")
    if sin_red and (previa_busq or {}).get("aceptado"):
        RP.aplicar(ficha, previa_busq)             # lo aceptado antes se conserva sin volver a preguntar
    elif publico:                                  # (sin_red solo evita al MODELO; la busqueda publica se repite)
        try:
            RP.aplicar(ficha, publico(ficha))
        except Exception:   # noqa: BLE001 - sin busqueda la ficha sigue igual (el hueco queda para Damian)
            pass
    ficha["crudo_modelo"] = crudo                     # para rehacer la normalizacion sin volver a pedir nada
    return ficha, modelo, res


def procesar(codigo: str, coleccion: Path | None = None, post=_post, lectores: dict | None = None, resolver=None,
             transcriptor=None, relectura: bool = True, correr=subprocess.run, libres=None, presupuesto=None) -> dict:
    """Ficha completa de UN reel (REELS.md, "Ficha completa por reel y tareas"): reutiliza el video y la transcripcion
    de la capa bruta si ya estan; lectura densa (1/s) con la cascada de lectores; ficha con Gemini comprobada sin IA;
    resolucion (GitHub); completitud contra la promesa y, si faltan, relectura a 2/s del tramo de la lista + recortes
    ampliados. Guarda la capa bruta (con las lecturas) y <codigo>.ficha.json; las dos guardan su historial."""
    from nucleo import reels_ficha as F
    from nucleo import reels_resolver as RR
    t_ini = time.perf_counter()
    r = reel_de_coleccion(codigo, coleccion)
    ruta_bruto = CARPETA / f"{codigo}.json"
    bruto = json.loads(ruta_bruto.read_text(encoding="utf-8")) if ruta_bruto.exists() else {}
    bruto.pop("anteriores", None)
    bruto.update(url=r["url"], autor=r.get("autor"), pie=r.get("pie"), colecciones=r.get("colecciones"),
                 categorias_preliminares=r.get("categorias_preliminares"))
    errores: dict[str, str] = {}
    media = CARPETA / "media" / codigo
    video = next(iter(sorted(media.glob(f"{codigo}.mp4"))), None) if media.exists() else None
    if video is None:
        try:
            v = descargar(r["url"], media)
            video = v["video"]
            bruto.update(titulo=v["titulo"], duracion_s=v["duracion"], subido=v["subido"])
        except NoDescargable as e:
            errores["descarga"] = str(e)
            bruto["estado"] = "no_descargable"
    if video is not None and not (bruto.get("transcripcion") or {}).get("segmentos"):
        try:
            bruto["transcripcion"] = (transcriptor or transcribir)(video)
        except Exception as e:   # noqa: BLE001
            errores["transcripcion"] = f"{type(e).__name__}: {str(e)[:200]}"
    if lectores is None:
        local = (lambda fs: pantalla_local(fs, post=post)) if modelo_ollama_disponible() else None
        tope = _presupuesto(post, presupuesto)
        lectores = {"gemini": _con_pausa(lambda fs: gemini_bloques(fs, post=post, presupuesto=tope)),
                    "ocr": ocr_local, "local": local,
                    "vision": nvidia_bloques if post is _post else None,
                    "vision_primero": bool(config_lote().get("vision_primero"))}
    if resolver is None:
        cache = RR.cargar_cache()
        resolver = RR.resolver_ficha
    else:
        cache = {}
    pegado = bruto.get("pegado") or []
    lecturas: list[dict] = []
    if video is not None:
        densos = fotogramas_densos(video, media / "densos", correr=correr)
        lecturas, errs = _leer(densos, lectores)
        if errs:
            errores["lectura"] = "; ".join(errs)[:600]
    ficha, modelo, res = _montar(bruto, lecturas, pegado, post, resolver, cache, libres=libres, presupuesto=presupuesto)
    hubo_relectura = False
    if relectura and video is not None and ficha["completitud"]["faltan"]:
        tramo = tramo_lista(lecturas)
        if tramo:
            hubo_relectura = True
            extra = fotogramas_densos(video, media / "densos", fps=FPS_RELECTURA, prefijo="r", desde=tramo[0],
                                      hasta=tramo[1], correr=correr)
            mas, errs = _leer(extra, lectores)
            listas = sorted((x for x in lecturas if x.get("estado") == "texto"), key=lambda x: -len(x["texto"]))
            trozos = []
            for x in listas[:MAX_RECORTADOS]:
                for p in recortes(media / "densos" / x["foto"], media / "densos" / "recortes", correr=correr):
                    trozos.append({"foto": p, "t": x["t"]})
            rec, errs2 = _leer(trozos, lectores) if trozos else ([], [])
            if errs or errs2:
                errores["relectura"] = "; ".join(errs + errs2)[:600]
            todas = sorted(lecturas + mas + rec, key=lambda x: (x["t"], x["foto"]))
            ficha, modelo, res = _montar(bruto, todas, pegado, post, resolver, cache, libres=libres,
                                         presupuesto=presupuesto)
            bruto["lectura_relectura"] = mas + rec
    if resolver is RR.resolver_ficha:
        RR.guardar_cache(cache)
    bruto["lectura_densa"] = lecturas
    bruto["estado"] = bruto.get("estado") if video is None else ("analizado" if lecturas else "parcial")
    return _terminar(codigo, r, bruto, ficha, modelo, res, lecturas, errores, hubo_relectura, t_ini)


def _terminar(codigo: str, r: dict, bruto: dict, ficha: dict, modelo: str, res: dict, lecturas: list[dict],
              errores: dict, hubo_relectura: bool, t_ini: float) -> dict:
    """Llamada a la accion, hueco, y guardado de bruto y ficha (con historial)."""
    from nucleo import reels_ficha as F
    from nucleo import reels_huecos
    llamada_txt = F.llamada_texto(bruto.get("pie") or "", (bruto.get("transcripcion") or {}).get("texto", ""),
                                  *[x.get("texto") or "" for x in lecturas])
    F.verificar_llamada(ficha, llamada_txt, F.material(bruto, lecturas, bruto.get("pegado") or []))
    ficha["hueco"] = reels_huecos.evaluar(ficha)
    bruto.pop("reprocesar", None)                     # lo pegado por Damian ya entro en esta ficha
    bruto.pop("codigo", None)
    bruto.pop("guardado", None)
    bruto["errores_ficha"] = errores
    guardar_bruto(codigo, bruto)
    ficha.update(codigo=codigo, url=r["url"], autor=r.get("autor"), colecciones=r.get("colecciones"),
                 estado=ficha["completitud"]["estado"], revisar=F.revisar_fotogramas(lecturas),
                 modelo_ficha=modelo, resolucion=res, relectura=hubo_relectura, errores=errores,
                 lectores=sorted({x["lector"] for x in lecturas if x.get("lector")}),
                 fotogramas=len(lecturas), segundos=round(time.perf_counter() - t_ini, 1))
    guardar_bruto(codigo, ficha, sufijo=".ficha.json")
    return ficha


def rehacer_ficha(codigo: str, coleccion: Path | None = None, post=_post, resolver=None,
                  usar_crudo: bool = False, libres=None, presupuesto=None, publico=None) -> dict:
    """Rehace SOLO la ficha con las lecturas ya guardadas en la capa bruta (una peticion a Gemini, sin descargar ni
    leer fotogramas otra vez). Para lo pegado por Damian y para repasar fichas tras mejorar la normalizacion."""
    from nucleo import reels_resolver as RR
    t_ini = time.perf_counter()
    r = reel_de_coleccion(codigo, coleccion)
    bruto = json.loads((CARPETA / f"{codigo}.json").read_text(encoding="utf-8"))
    bruto.pop("anteriores", None)
    previa = CARPETA / f"{codigo}.ficha.json"
    previa = json.loads(previa.read_text(encoding="utf-8")) if previa.exists() else {}
    # lo verificado de TODAS las versiones anteriores de la ficha (el modelo omite cosas de forma variable)
    previa["_n_ficha"] = max([len(previa.get("elementos") or [])] + [len(v.get("elementos") or [])
                                                                    for v in previa.get("anteriores") or []])
    previa["elementos"] = list(previa.get("elementos") or []) + [
        e for v in previa.get("anteriores") or [] for e in v.get("elementos") or []]
    lecturas = sorted((bruto.get("lectura_densa") or []) + (bruto.get("lectura_relectura") or []),
                      key=lambda x: (x.get("t") or 0, x.get("foto") or ""))
    cache = RR.cargar_cache() if resolver is None else {}
    crudo = previa.get("crudo_modelo") if usar_crudo else None
    if usar_crudo and crudo is None:
        raise ValueError(f"{codigo}: la ficha no guarda la respuesta del modelo; hace falta 'rehacer' sin --crudo")
    ficha, modelo, res = _montar(bruto, lecturas, bruto.get("pegado") or [], post, resolver or RR.resolver_ficha, cache,
                                 previa=previa, crudo=crudo, modelo=previa.get("modelo_ficha") or "",
                                 libres=libres, presupuesto=presupuesto, publico=publico)
    if resolver is None:
        RR.guardar_cache(cache)
    return _terminar(codigo, r, bruto, ficha, modelo, res, bruto.get("lectura_densa") or [], {},
                     bool(previa.get("relectura")), t_ini)


# ------------------------------------------------------------------ lote (turno nocturno; PREPARADO, no se lanza solo)
LOTE = CARPETA / "lote.json"
POR_NOCHE = 30
# T1037 (25/10): el lote de un turno ya no se corta a 30 si le queda tiempo (la noche del 24 hizo 30 en 84 min y
# paro con 96 min libres). Tope = minutos del turno / MIN_POR_REEL (medido: 2,8 min por reel con NVIDIA vivo); el
# presupuesto diario de Gemini del lote (config gemini_fraccion_diaria) sigue parando el lote si se agota.
MIN_POR_REEL = 3
# Bloque 23 (29/10, K0062): un reel solo empieza si quedan RESERVA_REEL min hasta la hora limite. Antes se miraba solo
# "ya paso la hora" y un reel empezado en el ultimo minuto (p90 4,3 min, max 32 medidos al rehacer) se comia el margen:
# el turno de dia (30 min) acabo 3 veces en TimeoutExpired (24 y 27/10) y el timeout solo mata al lanzador del venv.
RESERVA_REEL = 5
RAM_MIN_MB = 2500             # whisper small + OCR caben de sobra; por debajo, se para (piloto: 0,4 GB libres con Ollama)
MAX_FALLOS = 3                # un reel que falla 3 veces se aparta (queda en el estado, no se pierde)
PAUSA_SATURADO = 300          # s de espera si un reel cae por saturacion (no por cuota diaria); a la 3.a seguida, se para


def ram_libre_mb() -> int | None:
    """RAM libre en MB (Windows, sin dependencias). None si no se puede medir."""
    try:
        import ctypes

        class MEM(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MEM()
        m.dwLength = ctypes.sizeof(MEM)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return int(m.ullAvailPhys // (1024 * 1024))
    except Exception:   # noqa: BLE001
        return None


def _leer_estado_lote(ruta: Path) -> dict:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"hechos": {}, "fallos": {}, "noches": []}


def _guardar_estado_lote(estado: dict, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ruta)


# Bloque 18 (24/10, Damian): ai y cursos primero, despues vende, lo demas (sin coleccion o de otra), y China al final.
PRIORIDAD_COLECCIONES = {"ai": 0, "cursos": 0, "vende": 1, "china comunista": 3}
PRIORIDAD_OTRAS = 2


def prioridad_coleccion(reel: dict) -> int:
    """La mejor (la mas baja) de las colecciones del reel; sin coleccion conocida, PRIORIDAD_OTRAS."""
    return min((PRIORIDAD_COLECCIONES.get(str(c).strip().lower(), PRIORIDAD_OTRAS) for c in reel.get("colecciones") or []),
               default=PRIORIDAD_OTRAS)


def cola_lote(coleccion: Path | None = None, carpeta: Path | None = None, estado: dict | None = None) -> list[str]:
    """Lo que falta, en orden: primero los reels con algo pegado por Damian (reprocesar), luego los que no tienen
    ficha, por prioridad de coleccion (PRIORIDAD_COLECCIONES) y, dentro de cada una, en el orden de la coleccion.
    Fuera los apartados por fallar MAX_FALLOS veces."""
    carpeta = carpeta or CARPETA
    estado = estado or {"fallos": {}}
    datos = json.loads((coleccion or COLECCION).read_text(encoding="utf-8"))
    primero, despues = [], []
    for r in datos["reels"]:
        c = r["codigo"]
        if (estado.get("fallos", {}).get(c) or {}).get("n", 0) >= MAX_FALLOS:
            continue
        bruto = carpeta / f"{c}.json"
        if bruto.exists() and json.loads(bruto.read_text(encoding="utf-8")).get("reprocesar"):
            primero.append(c)
        elif not (carpeta / f"{c}.ficha.json").exists():
            despues.append((prioridad_coleccion(r), len(despues), c))
    return primero + [c for _, _, c in sorted(despues)]


def _solo_rehacer(codigo: str, carpeta: Path | None = None) -> bool:
    """Reel con algo pegado por Damian y lecturas ya guardadas: basta rehacer la ficha (sin descargar ni leer)."""
    carpeta = carpeta or CARPETA
    ruta = carpeta / f"{codigo}.json"
    if not ruta.exists() or not (carpeta / f"{codigo}.ficha.json").exists():
        return False
    b = json.loads(ruta.read_text(encoding="utf-8"))
    return bool(b.get("reprocesar") and b.get("lectura_densa"))


def lote(maximo: int = POR_NOCHE, coleccion: Path | None = None, procesar_fn=None, ram=ram_libre_mb,
         dormir=time.sleep, parada=None, hasta: datetime | None = None, ruta: Path | None = None,
         rehacer_fn=None) -> dict:
    """Una noche: hasta `maximo` reels, de uno en uno, guardando el estado tras cada uno (reanudable: lo hecho no se
    repite). Para antes si: PARADA de NEXO, poca RAM, pasa la hora `hasta`, Gemini sin cuota diaria en ningun
    modelo, o 3 saturaciones seguidas. Un reel que falla por otra cosa suma un fallo y se sigue con el siguiente."""
    import urllib.error
    ruta = ruta or LOTE
    procesar_fn = procesar_fn or procesar
    rehacer_fn = rehacer_fn or rehacer_ficha
    if parada is None:
        from nucleo import parada as P
        parada = P.activa
    estado = _leer_estado_lote(ruta)
    noche = {"inicio": datetime.now().isoformat(timespec="seconds"), "hechos": [], "fallos": [], "motivo_fin": ""}
    saturados = 0
    for codigo in cola_lote(coleccion, estado=estado):
        if len(noche["hechos"]) >= maximo:
            noche["motivo_fin"] = f"tope de {maximo} por noche"
            break
        if parada():
            noche["motivo_fin"] = "parada de NEXO"
            break
        libre = ram()
        if libre is not None and libre < RAM_MIN_MB:
            noche["motivo_fin"] = f"poca RAM libre ({libre} MB < {RAM_MIN_MB})"
            break
        if hasta and datetime.now() + timedelta(minutes=RESERVA_REEL) >= hasta:   # Bloque 23 (K0062)
            noche["motivo_fin"] = "hora limite"
            break
        try:
            fn = rehacer_fn if _solo_rehacer(codigo) else procesar_fn
            f = fn(codigo, coleccion=coleccion) if coleccion else fn(codigo)
        except SinCuotaGemini as e:
            noche["motivo_fin"] = f"Gemini sin cuota diaria: {e}"
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503):
                saturados += 1
                noche["fallos"].append({"codigo": codigo, "error": f"HTTP {e.code} (saturado)"})
                if saturados >= 3:
                    noche["motivo_fin"] = "Gemini saturado 3 veces seguidas"
                    break
                dormir(PAUSA_SATURADO)
                continue
            f = None
            err = f"HTTP {e.code}"
        except Exception as e:   # noqa: BLE001 - un reel roto no para la noche
            f = None
            err = f"{type(e).__name__}: {str(e)[:200]}"
        if f is None:
            prev = estado["fallos"].get(codigo) or {"n": 0}
            estado["fallos"][codigo] = {"n": prev["n"] + 1, "ultimo": err}
            noche["fallos"].append({"codigo": codigo, "error": err})
        else:
            saturados = 0
            estado["hechos"][codigo] = {"cuando": datetime.now().isoformat(timespec="seconds"), "estado": f["estado"],
                                        "elementos": len(f["elementos"])}
            estado["fallos"].pop(codigo, None)
            noche["hechos"].append(codigo)
        _guardar_estado_lote(estado, ruta)
    else:
        noche["motivo_fin"] = noche["motivo_fin"] or "cola vacia"
    noche["fin"] = datetime.now().isoformat(timespec="seconds")
    estado["noches"] = (estado.get("noches") or [])[-30:] + [noche]
    _guardar_estado_lote(estado, ruta)
    return noche


# ------------------------------------------------------------------ rehacer TODAS (Bloque 10, 17/10)
# Las fichas hechas antes de los remates de calidad se rehacen de una en una con las lecturas ya guardadas (sin descargar
# ni leer fotogramas): reanudable, con las mismas paradas que el lote y SIN crear propuestas ni tarjeta de huecos.
# Cuando no queda ninguna, un aviso en el Centro: las revisa Claude y luego Damian decide si se enciende crear_propuestas.
REHACER = CARPETA / "rehacer_todas.json"
VERSION_REHECHO = "b10-2026-10-17"      # al cambiar las reglas de calidad otra vez, se sube y se vuelve a empezar
AVISO_LISTAS = "Fichas de reels listas para revisar"


def _leer_rehechas(ruta: Path | None = None) -> dict:
    e = _leer_estado_lote(ruta or REHACER)
    if e.get("version") != VERSION_REHECHO:
        return {"version": VERSION_REHECHO, "hechos": {}, "fallos": {}, "noches": []}
    return e


def cola_rehacer(coleccion: Path | None = None, carpeta: Path | None = None, estado: dict | None = None) -> list[str]:
    """Reels con ficha y capa bruta que aun no se han rehecho en esta version, en el orden de la coleccion. Fuera los
    apartados por fallar MAX_FALLOS veces."""
    carpeta = carpeta or CARPETA
    estado = estado if estado is not None else _leer_rehechas()
    datos = json.loads((coleccion or COLECCION).read_text(encoding="utf-8"))
    cola = []
    for r in datos["reels"]:
        c = r["codigo"]
        if c in (estado.get("hechos") or {}) or ((estado.get("fallos") or {}).get(c) or {}).get("n", 0) >= MAX_FALLOS:
            continue
        if (carpeta / f"{c}.ficha.json").exists() and (carpeta / f"{c}.json").exists():
            cola.append(c)
    return cola


def _marca_rehacer(ruta: Path | None = None) -> tuple[int, int]:
    e = _leer_rehechas(ruta or REHACER)
    return len(e.get("hechos") or {}), sum(int(f.get("n", 0)) for f in (e.get("fallos") or {}).values())


def _n_elementos(codigo: str, carpeta: Path | None = None) -> int | None:
    try:
        return len(json.loads(((carpeta or CARPETA) / f"{codigo}.ficha.json").read_text(encoding="utf-8")).get("elementos") or [])
    except (OSError, ValueError):
        return None


def _avisar_listas(estado: dict) -> None:
    from nucleo import avisos
    apartadas = sum(1 for f in (estado.get("fallos") or {}).values() if f.get("n", 0) >= MAX_FALLOS)
    avisos.emitir("reels", AVISO_LISTAS,
                  f"NEXO ha rehecho {len(estado.get('hechos') or {})} fichas de reels con las reglas de calidad nuevas"
                  + (f" ({apartadas} apartadas por fallar {MAX_FALLOS} veces)" if apartadas else "")
                  + ". No se ha creado ninguna propuesta: crear_propuestas sigue en false hasta que Claude las revise y tu lo digas.",
                  ruta="/", clave=f"reels_fichas_listas:{VERSION_REHECHO}", urgencia="normal")


def rehacer_todas(maximo: int = POR_NOCHE, coleccion: Path | None = None, rehacer_fn=None, ram=ram_libre_mb,
                  dormir=time.sleep, parada=None, hasta: datetime | None = None, ruta: Path | None = None,
                  carpeta: Path | None = None, avisar=None) -> dict:
    """Rehace hasta `maximo` fichas, de una en una y guardando el estado tras cada una (reanudable). Para antes si:
    PARADA de NEXO, poca RAM, pasa la hora `hasta`, Gemini sin cuota diaria o 3 saturaciones seguidas. Un reel que falla
    suma un fallo y se sigue. Cuando la cola queda vacia deja UN aviso en el Centro (`avisar`)."""
    import urllib.error
    ruta = ruta or REHACER
    rehacer_fn = rehacer_fn or rehacer_ficha
    avisar = avisar or _avisar_listas
    if parada is None:
        from nucleo import parada as P
        parada = P.activa
    estado = _leer_rehechas(ruta)
    noche = {"inicio": datetime.now().isoformat(timespec="seconds"), "hechos": [], "fallos": [], "motivo_fin": ""}
    saturados = 0
    for codigo in cola_rehacer(coleccion, carpeta, estado):
        if len(noche["hechos"]) >= maximo:
            noche["motivo_fin"] = f"tope de {maximo} por tanda"
            break
        if parada():
            noche["motivo_fin"] = "parada de NEXO"
            break
        libre = ram()
        if libre is not None and libre < RAM_MIN_MB:
            noche["motivo_fin"] = f"poca RAM libre ({libre} MB < {RAM_MIN_MB})"
            break
        if hasta and datetime.now() + timedelta(minutes=RESERVA_REEL) >= hasta:   # Bloque 23 (K0062)
            noche["motivo_fin"] = "hora limite"
            break
        antes = _n_elementos(codigo, carpeta)
        try:
            f = rehacer_fn(codigo, coleccion=coleccion) if coleccion else rehacer_fn(codigo)
        except SinCuotaGemini as e:
            noche["motivo_fin"] = f"Gemini sin cuota diaria: {e}"
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503):
                saturados += 1
                noche["fallos"].append({"codigo": codigo, "error": f"HTTP {e.code} (saturado)"})
                if saturados >= 3:
                    noche["motivo_fin"] = "saturado 3 veces seguidas"
                    break
                dormir(PAUSA_SATURADO)
                continue
            f, err = None, f"HTTP {e.code}"
        except Exception as e:   # noqa: BLE001 - una ficha rota no para la tanda
            f, err = None, f"{type(e).__name__}: {str(e)[:200]}"
        if f is None:
            prev = estado["fallos"].get(codigo) or {"n": 0}
            estado["fallos"][codigo] = {"n": prev["n"] + 1, "ultimo": err}
            noche["fallos"].append({"codigo": codigo, "error": err})
        else:
            saturados = 0
            estado["hechos"][codigo] = {"cuando": datetime.now().isoformat(timespec="seconds"),
                                        "antes": antes, "despues": len(f["elementos"]),
                                        "fusion": (f.get("fusion_anterior") or {}).get("anadidos", 0)}
            estado["fallos"].pop(codigo, None)
            noche["hechos"].append(codigo)
        _guardar_estado_lote(estado, ruta)
    noche["motivo_fin"] = noche["motivo_fin"] or "cola vacia"
    quedan = len(cola_rehacer(coleccion, carpeta, estado))
    noche["quedan"] = quedan
    if not quedan and not estado.get("aviso"):
        try:
            avisar(estado)
            estado["aviso"] = datetime.now().isoformat(timespec="seconds")
        except OSError:
            pass                                      # sin aviso se reintenta en la siguiente vuelta
    noche["fin"] = datetime.now().isoformat(timespec="seconds")
    estado["noches"] = (estado.get("noches") or [])[-30:] + [noche]
    _guardar_estado_lote(estado, ruta)
    return noche


PY_REELS = RAIZ / ".venv-reels" / "Scripts" / "python.exe"
MARGEN_HASTA = 6              # min antes del tope en que el lote deja de empezar reels (uno tarda ~2-3 min)
PROGRESO_CADA = 30.0          # s entre miradas al estado del lote para decir "el turno avanza"


def _marca_lote(ruta: Path | None = None) -> tuple[int, int]:
    """(reels hechos, fallos acumulados) del estado del lote: cambia cada vez que un reel termina (bien o mal)."""
    e = _leer_estado_lote(ruta or LOTE)
    return len(e.get("hechos") or {}), sum(int(f.get("n", 0)) for f in (e.get("fallos") or {}).values())


def _avisar_progreso(marca: tuple[int, int]) -> None:
    from nucleo import planificador
    planificador.progreso_si_turno(paso="reels", tarea=f"reels: {marca[0]} hechos, {marca[1]} fallos")


def vigilar_progreso_lote(parar, avisar=_avisar_progreso, ruta: Path | None = None, cada: float = PROGRESO_CADA,
                          marca=_marca_lote) -> None:
    """T890 (turno_colgado con 30/30 reels bien): el lote corre en un subproceso y el turno no llamaba a progreso()
    hasta el final (30 min sin cambiar de paso = aviso). Aqui el progreso se mide POR REEL: cada vez que el estado
    del lote cambia (un reel terminado) se le dice al planificador que el turno avanza. `parar` = threading.Event."""
    ultima = None
    while not parar.is_set():
        try:
            m = marca(ruta)
            if m != ultima:
                ultima = m
                avisar(m)
        except Exception:   # noqa: BLE001 - vigilar nunca tumba el lote
            pass
        parar.wait(cada)


def _por_tramos(orden, maximo: int, minutos: int, margen: int, correr, ceder, ahora) -> tuple[dict | None, dict]:
    """T1069: corre el lote (o el rehacer) en tramos que acaban a la hora en punto; cada tramo corta limpio con su hora
    limite y deja su progreso guardado. Tras un tramo que acabo por la hora, si quedan tiempo y reels, pregunta a
    `ceder()`: con alguien esperando que va antes (el planificador ya ha vuelto a encolar este turno detras), acaba.
    `orden(maximo, hasta)` -> argumentos del subproceso. Devuelve (resumen de la noche o None, extra para la salida)."""
    fin = ahora() + timedelta(minutes=max(1, minutos - margen))
    noche, extra, quedan = None, {}, maximo
    while True:
        hasta = min(fin, proxima_hora(ahora())) if ceder else fin
        r = correr(orden(quedan, hasta), cwd=str(RAIZ), capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=max(60, int((fin - ahora()).total_seconds()) + margen * 60))
        try:
            tramo = json.loads((r.stdout or "").strip().splitlines()[-1])
        except (IndexError, ValueError):
            extra["error"] = f"no devolvio resumen (codigo {r.returncode}): {(r.stderr or '')[-300:]}"
            return noche, extra
        if noche is None:
            noche = tramo
        else:
            for k in ("hechos", "fallos"):
                noche[k] = (noche.get(k) or []) + (tramo.get(k) or [])
            noche.update({k: tramo[k] for k in ("motivo_fin", "fin", "quedan") if k in tramo})
            noche["tramos"] = noche.get("tramos", 1) + 1
        quedan -= len(tramo.get("hechos") or [])
        if (tramo.get("motivo_fin") != "hora limite" or quedan <= 0 or ceder is None
                or fin - ahora() < timedelta(minutes=MIN_TRAMO)):
            return noche, extra
        cedido = ceder()
        if cedido:
            noche["motivo_fin"] = "cede el turno a " + ", ".join(cedido)
            extra["cedido"] = cedido
            return noche, extra


MIN_TRAMO = 5                    # min: tramo mas corto que se empieza (y el minimo de ventana para otro)


def proxima_hora(t: datetime) -> datetime:
    """La siguiente hora en punto que queda al menos MIN_TRAMO por delante (02:57 -> 04:00, 02:30 -> 03:00)."""
    return (t + timedelta(minutes=MIN_TRAMO)).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def turno(maximo: int | None = None, simular: bool = False, correr=subprocess.run, minutos: int = 300,
          repartir=None, ceder=None, ahora=datetime.now) -> dict:
    """Paso del turno 'reels' (planificador, .venv normal): lanza UNA noche del lote con .venv-reels (alli estan
    yt-dlp, whisper y el OCR) y, con las fichas nuevas, las propuestas por tema (tribunal + freno) y UNA tarjeta de
    huecos para Damian. simular = solo cuenta lo pendiente. Sin `maximo`, el que quepa en `minutos` (T1037).
    T1069: con `ceder` (lo pasa turno_nexo), el lote va por tramos que acaban a cada hora en punto y entre tramos cede el
    sitio si en la cola espera alguien que va antes (implementador, tribunal...)."""
    maximo = maximo or max(POR_NOCHE, minutos // MIN_POR_REEL)
    pendientes = len(cola_lote(estado=_leer_estado_lote(LOTE)))
    rehacer = len(cola_rehacer()) if config_lote().get("rehacer_todas", True) else 0
    if simular or not (pendientes or rehacer):
        return {"simulado": simular, "pendientes": pendientes, **({"rehacer_pendientes": rehacer} if rehacer else {})}
    if not pendientes:                                # Bloque 10: sin reels nuevos, se rehacen las fichas viejas
        return _turno_rehacer(maximo, correr, minutos, ceder, ahora)
    import threading
    parar = threading.Event()
    vigia = threading.Thread(target=vigilar_progreso_lote, args=(parar,), name="progreso-reels", daemon=True)
    vigia.start()
    try:
        # Bloque 18: el lote para SOLO antes del tope del turno (ventanas de dia de 30 min): sin --hasta, el timeout
        # mataba solo al lanzador del venv y el interprete real seguia suelto.
        noche, extra = _por_tramos(
            lambda n, hasta: [str(PY_REELS), "-m", "extremidades.reels", "lote", "--max", str(n),
                              "--hasta", hasta.strftime("%H:%M")],
            maximo, minutos, MARGEN_HASTA, correr, ceder, ahora)
    finally:
        parar.set()
    if noche is None:
        return {"error": f"el lote {extra['error']}"}
    salida = {"noche": noche, "pendientes": pendientes - len(noche.get("hechos", [])), **extra}
    cfg = config_lote()
    if noche.get("hechos"):
        from nucleo import reels_huecos, reels_tareas
        fichas = reels_tareas.cargar_fichas(noche["hechos"])
        if cfg["crear_propuestas"]:
            salida["tareas"] = reels_tareas.crear(reels_tareas.plan(fichas))
            salida["huecos"] = reels_huecos.registrar(fichas)["tarjeta"]
        else:     # primera noche (6b): no se crea nada; se deja la muestra y lo que saldria para que Damian lo vea
            salida["muestra"] = str(escribir_muestra(fichas, noche))
        if repartir is None and correr is subprocess.run:   # solo con el lote real (nunca con el doble de los tests)
            from nucleo import reels_destino
            repartir = reels_destino.repartir
        if repartir is not None:
            try:  # Bloque 18: cada ficha nueva a su sitio (catalogo, guias, investigacion, monetizacion, viajes)
                salida["destinos"] = repartir(noche["hechos"])["recuento"]
            except Exception as e:   # noqa: BLE001 - el reparto nunca tumba el turno: se reintenta con `repartir`
                salida["destinos"] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    if cfg["una_noche"]:
        salida["apagado"] = _apagar_turno()
    return salida


def _turno_rehacer(maximo: int, correr, minutos: int, ceder=None, ahora=datetime.now) -> dict:
    """Una tanda de `rehacer --todas` con .venv-reels, dentro del tope de minutos (la tanda se corta sola MARGEN_HASTA
    min antes y no empieza un reel a menos de RESERVA_REEL min de su hora limite).
    No crea propuestas ni tarjeta de huecos. T1069: por tramos y cediendo el sitio, como el lote."""
    import threading
    parar = threading.Event()
    vigia = threading.Thread(target=vigilar_progreso_lote, args=(parar,), kwargs={"marca": _marca_rehacer},
                             name="progreso-rehacer-reels", daemon=True)
    vigia.start()
    try:
        noche, extra = _por_tramos(
            lambda n, hasta: [str(PY_REELS), "-m", "extremidades.reels", "rehacer", "--todas", "--max", str(n),
                              "--minutos", str(max(1, round((hasta - ahora()).total_seconds() / 60)))],
            maximo, minutos, MARGEN_HASTA, correr, ceder, ahora)   # Bloque 23: era 3, el mismo margen que el lote
    finally:
        parar.set()
    if noche is None:
        return {"error": f"rehacer --todas {extra['error']}"}
    return {"rehecho": noche, "rehacer_pendientes": noche.get("quedan"), **extra}


def escribir_muestra(fichas: list[dict], noche: dict, carpeta: Path | None = None, tam: int = 10,
                     ahora: datetime | None = None) -> Path:
    """Muestra para Damian tras la primera noche: `tam` fichas repartidas por la noche + las propuestas y la tarjeta de
    huecos que saldrian de TODAS las de la noche. No crea tareas ni tarjetas. PRIVADO (perfil_privado)."""
    from nucleo import reels_ficha as F
    from nucleo import reels_huecos, reels_tareas
    ahora = ahora or datetime.now()
    carpeta = carpeta or CARPETA
    paso = max(1, len(fichas) // tam) if fichas else 1
    elegidas = fichas[::paso][:tam]
    gemini = PresupuestoGemini().resumen() if carpeta == CARPETA else {}
    partes = [f"# Muestra de la primera noche de reels ({ahora:%d/%m/%Y %H:%M}) — PRIVADO", "",
              f"Reels hechos: {len(noche.get('hechos', []))} · fallos: {len(noche.get('fallos', []))} · "
              f"motivo de fin: {noche.get('motivo_fin')} · Gemini del lote hoy: {gemini or 'n/d'}", "",
              "No se ha creado ninguna tarea ni tarjeta: esto es lo que saldria.", "",
              f"## {len(elegidas)} fichas de muestra", ""]
    partes += [F.ficha_md(f) + "\n" for f in elegidas]
    partes += ["## Propuestas que saldrian (de todas las fichas de la noche)", "",
               reels_tareas.plan_md(reels_tareas.plan(fichas)), "", "## Tarjeta de huecos que saldria", ""]
    t = reels_huecos.registrar(fichas, escribir=False)["tarjeta"]
    partes.append(f"Tarjeta {t['id']}: {len(t['reels'])} reel(s) ({', '.join(t['reels']) or 'ninguno'}), "
                  f"{t['fuera_de_tanda']} fuera de tanda.")
    ruta = carpeta / f"MUESTRA_{ahora:%Y-%m-%d}.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(partes) + "\n", encoding="utf-8")
    return ruta


def _apagar_turno() -> list[str]:
    """Pone inactivo el/los turnos con plantilla 'reels' (la segunda noche no arranca sin Damian)."""
    from nucleo import turnos
    apagados = []
    for t in turnos.cargar().get("turnos", []):
        if t.get("plantilla") == "reels" and t.get("activo"):
            turnos.poner_activo(t["id"], False)
            apagados.append(t["id"])
    return apagados


def leer_hasta(hhmm: str, ahora: datetime | None = None) -> datetime:
    """'HH:MM' -> la proxima vez que llega esa hora (un lote de las 23:30 con --hasta 02:24 acaba MANANA a las 02:24)."""
    ahora = ahora or datetime.now()
    hh, mm = hhmm.split(":")
    t = ahora.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    return t if t > ahora else t + timedelta(days=1)


def _cli(argv: list[str]) -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) >= 2 and argv[0] == "gemini":       # repite SOLO la lectura de Gemini con los fotogramas ya sacados
        for codigo in argv[1:]:
            d = releer_gemini(codigo)
            print(json.dumps({"codigo": codigo, "tiempo_s": d["tiempos_s"].get("pantalla_gemini"),
                              "error": d["errores"].get("pantalla_gemini"), "citas": d["citas_por_lector"].get("gemini")},
                             ensure_ascii=False))
        return 0
    if len(argv) >= 2 and argv[0] == "ficha":        # bloque 6: ficha completa (A0045 Gemini, A0046 GitHub)
        from nucleo import reels_ficha as F
        for codigo in argv[1:]:
            f = procesar(codigo)
            print(json.dumps({"codigo": codigo, "estado": f["estado"], "elementos": len(f["elementos"]),
                              "revisar": f["revisar"], "errores": f["errores"], "segundos": f["segundos"]},
                             ensure_ascii=False))
            print(F.ficha_md(f))
        return 0
    if argv[:2] == ["rehacer", "--todas"]:           # Bloque 10: todas las fichas viejas, de una en una, reanudable
        maximo, hasta = POR_NOCHE, None
        if "--max" in argv:
            maximo = int(argv[argv.index("--max") + 1])
        if "--minutos" in argv:
            hasta = datetime.now() + timedelta(minutes=int(argv[argv.index("--minutos") + 1]))
        print(json.dumps(rehacer_todas(maximo=maximo, hasta=hasta), ensure_ascii=False))
        return 0
    if len(argv) >= 2 and argv[0] == "rehacer":      # solo la ficha, con las lecturas guardadas (1 peticion)
        from nucleo import reels_ficha as F     # --crudo: con la respuesta del modelo ya guardada (0 peticiones)
        crudo = "--crudo" in argv
        for codigo in [a for a in argv[1:] if a != "--crudo"]:
            f = rehacer_ficha(codigo, usar_crudo=crudo)
            print(json.dumps({"codigo": codigo, "estado": f["estado"], "elementos": len(f["elementos"])},
                             ensure_ascii=False))
            print(F.ficha_md(f))
        return 0
    if argv[:1] == ["cola"]:                          # solo cuenta lo que falta; no procesa nada
        estado = _leer_estado_lote(LOTE)
        cola = cola_lote(estado=estado)
        print(json.dumps({"pendientes": len(cola), "hechos": len(estado.get("hechos", {})),
                          "apartados": sum(1 for f in estado.get("fallos", {}).values() if f.get("n", 0) >= MAX_FALLOS)},
                         ensure_ascii=False))
        return 0
    if argv[:1] == ["lote"]:                          # una noche del lote (lo lanza el turno 'reels'; no se lanza solo)
        maximo, hasta = POR_NOCHE, None
        if "--max" in argv:
            maximo = int(argv[argv.index("--max") + 1])
        if "--hasta" in argv:
            hasta = leer_hasta(argv[argv.index("--hasta") + 1])
        print(json.dumps(lote(maximo=maximo, hasta=hasta), ensure_ascii=False))
        return 0
    if len(argv) >= 2 and argv[0] == "analizar":
        for codigo in argv[1:]:
            d = analizar(codigo)
            print(json.dumps({"codigo": codigo, "estado": d["estado"], "tiempos_s": d["tiempos_s"],
                              "errores": d["errores"], "citas": d["citas"]}, ensure_ascii=False))
        return 0
    print(__doc__)
    print("Uso: .venv-reels\\Scripts\\python.exe -m extremidades.reels analizar|ficha|gemini CODIGO [CODIGO...]  |  cola  |  lote [--max 30] [--hasta 07:00]  |  rehacer CODIGO [--crudo]  |  rehacer --todas [--max 30] [--minutos 120]")
    return 0 if argv[:1] in ([], ["-h"], ["--help"]) else 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    import sys
    sys.exit(_cli(sys.argv[1:]))
