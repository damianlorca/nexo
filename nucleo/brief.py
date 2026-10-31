# -*- coding: utf-8 -*-
"""T697: el brief hablado de NEXO (texto). Lo lee extremidades/altavoz.py por el altavoz "Damián".

Orden fijado por Damian (05/10): 1) la hora; 2) el tiempo de hoy y de manana en Valencia y, si va a llover, de que
hora a que hora (Open-Meteo: gratis, sin clave, uso personal no comercial, < 10.000 llamadas/dia, CC BY 4.0);
3) lo destacable del Google Calendar de hoy y de la semana (direccion privada iCal de secretos.toml, procesada en
local; la direccion NUNCA se imprime: ni en logs, ni en tareas, ni en prompts); 4) el resumen de NEXO (lo
importante hecho y lo que le toca a Damian). Como mucho ~90 s hablado (MAX_PALABRAS).

El texto va a Gemini TTS (plan gratuito: Google puede usarlo), asi que NUNCA entra memoria/perfil_privado/ ni una
tarea cat:personal; los datos privados que se cuelen en un titulo se tapan como en tareas.lista_para_ia_externa.
Cada seccion que falle se salta con una frase corta: el brief no se cae por una fuente.

CLI (solo texto, no reproduce nada): .venv\\Scripts\\python.exe -m nucleo.brief texto
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

from nucleo.config import valor
from nucleo.registro import logger

log = logger("nucleo.brief")

LAT, LON = 39.4699, -0.3763          # Valencia (config: brief.lat / brief.lon)
MAX_PALABRAS = 230                    # ~90 s a ritmo rapido
DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")
LLUVIA_MM = 0.2                       # mm en una hora
LLUVIA_PROB = 50                      # % de probabilidad en una hora
MAX_EVENTOS_SEMANA = 5
MAX_TITULOS_NEXO = 3

# Codigos WMO de Open-Meteo -> palabras (https://open-meteo.com/en/docs, "WMO Weather interpretation codes").
CIELO = {0: "despejado", 1: "casi despejado", 2: "con nubes y claros", 3: "nublado", 45: "con niebla", 48: "con niebla",
         51: "con llovizna", 53: "con llovizna", 55: "con llovizna", 56: "con llovizna helada", 57: "con llovizna helada",
         61: "con lluvia débil", 63: "con lluvia", 65: "con lluvia fuerte", 66: "con lluvia helada",
         67: "con lluvia helada", 71: "con nieve", 73: "con nieve", 75: "con nieve", 77: "con nieve",
         80: "con chubascos", 81: "con chubascos", 82: "con chubascos fuertes", 85: "con chubascos de nieve",
         86: "con chubascos de nieve", 95: "con tormenta", 96: "con tormenta y granizo", 99: "con tormenta y granizo"}


def _http(url: str, timeout: float = 15) -> bytes:
    """GET sin cabeceras propias. Los errores de urllib no llevan la URL en su texto (importa para el iCal)."""
    req = urllib.request.Request(url, headers={"User-Agent": "NEXO-brief/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 - URL fija o de secretos.toml
        return r.read()


def _fallo(e: Exception) -> str:
    """Descripcion de un fallo de red SIN la URL (la del calendario es secreta)."""
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    return type(e).__name__


# ------------------------------------------------------------------ 1) la hora
def frase_hora(ahora: datetime) -> str:
    return (f"Son las {ahora.hour}:{ahora.minute:02d} del {DIAS_SEMANA[ahora.weekday()]} {ahora.day} de "
            f"{MESES[ahora.month - 1]}.")


# ------------------------------------------------------------------ 2) el tiempo
def url_tiempo(lat: float, lon: float) -> str:
    return ("https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&timezone=Europe%2FMadrid&forecast_days=2"
            "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            "&hourly=precipitation,precipitation_probability")


def tramos_lluvia(horas: list[datetime], mm: list, prob: list, dia: date, desde: datetime | None = None) -> list[tuple[int, int]]:
    """Horas de `dia` con lluvia (>= LLUVIA_MM o >= LLUVIA_PROB %), agrupadas en tramos (inicio, fin) en horas."""
    marcadas = []
    for h, m, p in zip(horas, mm, prob):
        if h.date() != dia or (desde is not None and h < desde.replace(minute=0, second=0, microsecond=0)):
            continue
        if (m or 0) >= LLUVIA_MM or (p or 0) >= LLUVIA_PROB:
            marcadas.append(h.hour)
    tramos: list[tuple[int, int]] = []
    for h in marcadas:
        if tramos and tramos[-1][1] == h:
            tramos[-1] = (tramos[-1][0], h + 1)
        else:
            tramos.append((h, h + 1))
    return tramos


# Codigos WMO de lluvia (llovizna, lluvia, chubascos, tormenta)
CODIGOS_LLUVIA = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
FRANJA_HORAS = 3


def franja_probable(horas: list[datetime], mm: list, prob: list, dia: date, desde: datetime | None = None,
                    ancho: int = FRANJA_HORAS) -> tuple[int, int] | None:
    """Las `ancho` horas seguidas de `dia` con mas probabilidad de lluvia (desempate: mas mm), o None si todo es 0.
    Sirve cuando el dia sale "con lluvia debil" pero ninguna hora llega a los umbrales (Damian, 05/10)."""
    serie = [(h.hour, p or 0, m or 0) for h, m, p in zip(horas, mm, prob) if h.date() == dia
             and (desde is None or h >= desde.replace(minute=0, second=0, microsecond=0))]
    mejor = None
    for i in range(len(serie)):
        trozo = serie[i:i + ancho]
        clave = (sum(x[1] for x in trozo), sum(x[2] for x in trozo))
        if clave > (0, 0) and (mejor is None or clave > mejor[0]):
            mejor = (clave, (trozo[0][0], trozo[-1][0] + 1))
    return mejor[1] if mejor else None


def _tramos_texto(tramos: list[tuple[int, int]]) -> str:
    return ", y ".join(f"de {a} a {b}" for a, b in tramos)


def frase_tiempo(datos: dict, ahora: datetime) -> str:
    d, h = datos["daily"], datos["hourly"]
    horas = [datetime.fromisoformat(x) for x in h["time"]]
    partes = []
    for i, nombre in ((0, "Hoy"), (1, "Mañana")):
        if i >= len(d["time"]):
            continue
        dia = date.fromisoformat(d["time"][i])
        cielo = CIELO.get(int(d["weather_code"][i] or 0), "variable")
        frase = (f"{nombre}, {cielo}, entre {round(d['temperature_2m_min'][i])} y "
                 f"{round(d['temperature_2m_max'][i])} grados")
        tramos = tramos_lluvia(horas, h["precipitation"], h["precipitation_probability"], dia,
                               desde=ahora if i == 0 else None)
        if tramos:
            frase += f"; puede llover {_tramos_texto(tramos)}"
        elif int(d["weather_code"][i] or 0) in CODIGOS_LLUVIA:
            franja = franja_probable(horas, h["precipitation"], h["precipitation_probability"], dia,
                                     desde=ahora if i == 0 else None)
            if franja:
                frase += f"; posible lluvia débil hacia las {franja[0]}-{franja[1]} h"
        elif i == 0 and (d.get("precipitation_probability_max") or [0])[0] and d["precipitation_probability_max"][0] >= LLUVIA_PROB:
            frase += "; la lluvia ya ha pasado"
        partes.append(frase + ".")
    return " ".join(partes)


def tiempo(ahora: datetime, obtener=_http) -> str:
    lat, lon = valor("brief.lat", LAT), valor("brief.lon", LON)
    try:
        datos = json.loads(obtener(url_tiempo(lat, lon)))
        return frase_tiempo(datos, ahora)
    except Exception as e:   # noqa: BLE001 - una fuente caida no tumba el brief
        log.warning("brief: el tiempo fallo (%s)", _fallo(e))
        return "No he podido mirar el tiempo."


# ------------------------------------------------------------------ 3) el calendario (iCal, en local)
def _desplegar(texto: str) -> list[str]:
    """RFC 5545: una linea que empieza por espacio o tabulador continua la anterior."""
    lineas: list[str] = []
    for linea in texto.replace("\r\n", "\n").split("\n"):
        if linea[:1] in (" ", "\t") and lineas:
            lineas[-1] += linea[1:]
        elif linea:
            lineas.append(linea)
    return lineas


def _propiedad(linea: str) -> tuple[str, dict, str]:
    cabeza, _, valor_ = linea.partition(":")
    nombre, *params = cabeza.split(";")
    return nombre.upper(), dict(p.split("=", 1) for p in params if "=" in p), valor_


def _fecha(valor_: str, params: dict) -> datetime | date:
    """DATE -> date (todo el dia); ...Z -> hora local del PC; con TZID o flotante -> se toma tal cual (Madrid)."""
    valor_ = valor_.strip()
    if params.get("VALUE") == "DATE" or len(valor_) == 8:
        return datetime.strptime(valor_, "%Y%m%d").date()
    if valor_.endswith("Z"):
        return datetime.strptime(valor_, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    return datetime.strptime(valor_[:15], "%Y%m%dT%H%M%S")


def _texto_ical(s: str) -> str:
    return s.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\").strip()


def leer_ical(texto: str) -> list[dict]:
    """VEVENTs con inicio, fin, resumen, uid, rrule, exdates, recurrence_id y estado."""
    eventos, actual = [], None
    for linea in _desplegar(texto):
        nombre, params, v = _propiedad(linea)
        if nombre == "BEGIN" and v.upper() == "VEVENT":
            actual = {"exdates": set(), "rrule": None, "recurrence_id": None, "estado": "", "fin": None}
        elif nombre == "END" and v.upper() == "VEVENT" and actual is not None:
            if "inicio" in actual:
                eventos.append(actual)
            actual = None
        elif actual is None:
            continue
        elif nombre == "DTSTART":
            actual["inicio"] = _fecha(v, params)
        elif nombre == "DTEND":
            actual["fin"] = _fecha(v, params)
        elif nombre == "SUMMARY":
            actual["resumen"] = _texto_ical(v)
        elif nombre == "UID":
            actual["uid"] = v.strip()
        elif nombre == "RRULE":
            actual["rrule"] = dict(p.split("=", 1) for p in v.split(";") if "=" in p)
        elif nombre == "EXDATE":
            for x in v.split(","):
                actual["exdates"].add(_fecha(x, params))
        elif nombre == "RECURRENCE-ID":
            actual["recurrence_id"] = _fecha(v, params)
        elif nombre == "STATUS":
            actual["estado"] = v.strip().upper()
    return eventos


_DIAS_RRULE = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _sumar_meses(d, meses: int):
    m = d.month - 1 + meses
    anio, mes = d.year + m // 12, m % 12 + 1
    try:
        return d.replace(year=anio, month=mes)
    except ValueError:   # 31 de un mes que no lo tiene: RFC 5545 lo salta
        return None


def _nth_dia_semana(anio: int, mes: int, dia_sem: int, n: int) -> date | None:
    primero = date(anio, mes, 1)
    if n > 0:
        d = primero + timedelta(days=(dia_sem - primero.weekday()) % 7 + 7 * (n - 1))
    else:
        siguiente = date(anio + mes // 12, mes % 12 + 1, 1)
        ultimo = siguiente - timedelta(days=1)
        d = ultimo - timedelta(days=(ultimo.weekday() - dia_sem) % 7 + 7 * (-n - 1))
    return d if d.month == mes else None


def ocurrencias(ev: dict, desde: datetime, hasta: datetime, tope: int = 2000) -> list:
    """Inicios del evento dentro de [desde, hasta). RRULE: DAILY/WEEKLY/MONTHLY/YEARLY con INTERVAL, COUNT, UNTIL,
    BYDAY (WEEKLY; y MONTHLY con ordinal tipo 2TU o -1FR) y BYMONTHDAY; respeta EXDATE."""
    inicio = ev["inicio"]
    todo_dia = not isinstance(inicio, datetime)

    def dentro(x) -> bool:
        xd = datetime.combine(x, datetime.min.time()) if todo_dia else x
        return desde <= xd < hasta

    def igual_a_exdate(x) -> bool:
        return x in ev["exdates"] or (not todo_dia and x.date() in ev["exdates"])

    regla = ev.get("rrule")
    if not regla:
        if todo_dia and ev.get("fin") and isinstance(ev["fin"], date):   # varios dias: cuenta si cubre el rango
            fin = datetime.combine(ev["fin"], datetime.min.time())
            ini = datetime.combine(inicio, datetime.min.time())
            if ini < hasta and fin > desde:
                return [max(inicio, desde.date())]
            return []
        return [inicio] if dentro(inicio) else []
    frec = regla.get("FREQ", "").upper()
    intervalo = int(regla.get("INTERVAL", "1") or 1)
    cuenta = int(regla["COUNT"]) if regla.get("COUNT") else None
    hasta_regla = _fecha(regla["UNTIL"], {}) if regla.get("UNTIL") else None
    if hasta_regla is not None and todo_dia and isinstance(hasta_regla, datetime):
        hasta_regla = hasta_regla.date()
    if hasta_regla is not None and not todo_dia and not isinstance(hasta_regla, datetime):
        hasta_regla = datetime.combine(hasta_regla, datetime.max.time())
    por_dia = [b.strip() for b in regla.get("BYDAY", "").split(",") if b.strip()]
    por_dia_mes = [int(x) for x in regla.get("BYMONTHDAY", "").split(",") if x.strip()]
    hora = inicio.time() if not todo_dia else None

    def con_hora(d: date):
        return datetime.combine(d, hora) if hora is not None else d

    salida, emitidas, paso = [], 0, 0
    base_dia = inicio.date() if not todo_dia else inicio
    while paso < tope:
        candidatos: list = []
        if frec == "DAILY":
            candidatos = [con_hora(base_dia + timedelta(days=paso * intervalo))]
        elif frec == "WEEKLY":
            lunes = base_dia - timedelta(days=base_dia.weekday()) + timedelta(weeks=paso * intervalo)
            dias = [_DIAS_RRULE[b[-2:]] for b in por_dia] if por_dia else [base_dia.weekday()]
            candidatos = [con_hora(lunes + timedelta(days=d)) for d in sorted(set(dias))]
        elif frec == "MONTHLY":
            ref = _sumar_meses(base_dia.replace(day=1), paso * intervalo)
            if por_dia:
                for b in por_dia:
                    n = int(b[:-2] or 1)
                    d = _nth_dia_semana(ref.year, ref.month, _DIAS_RRULE[b[-2:]], n)
                    if d:
                        candidatos.append(con_hora(d))
            else:
                for dm in por_dia_mes or [base_dia.day]:
                    try:
                        candidatos.append(con_hora(ref.replace(day=dm)))
                    except ValueError:
                        pass
        elif frec == "YEARLY":
            try:
                candidatos = [con_hora(base_dia.replace(year=base_dia.year + paso * intervalo))]
            except ValueError:
                candidatos = []
        else:
            return [inicio] if dentro(inicio) else []
        paso += 1
        for c in sorted(candidatos):
            if c < inicio:
                continue
            if hasta_regla is not None and c > hasta_regla:
                return salida
            emitidas += 1
            if cuenta is not None and emitidas > cuenta:
                return salida
            if dentro(c) and not igual_a_exdate(c):
                salida.append(c)
        ultimo = max(candidatos) if candidatos else None
        if ultimo is not None and (datetime.combine(ultimo, datetime.min.time()) if todo_dia else ultimo) >= hasta:
            return salida
    return salida


def eventos_en(texto: str, desde: datetime, hasta: datetime) -> list[tuple]:
    """(inicio, resumen) de cada evento en el rango, ordenados; aplica las excepciones (RECURRENCE-ID) y cancelados."""
    eventos = leer_ical(texto)
    cambiadas: dict[str, set] = {}
    for ev in eventos:
        if ev["recurrence_id"] is not None and ev.get("uid"):
            cambiadas.setdefault(ev["uid"], set()).add(ev["recurrence_id"])
    salida = []
    for ev in eventos:
        if ev["estado"] == "CANCELLED":
            continue
        quitar = cambiadas.get(ev.get("uid"), set()) if ev["recurrence_id"] is None else set()
        for x in ocurrencias(ev, desde, hasta):
            if x in quitar:
                continue
            salida.append((x, ev.get("resumen") or "un evento sin título"))

    def clave(par):
        x = par[0]
        return datetime.combine(x, datetime.min.time()) if not isinstance(x, datetime) else x
    return sorted(salida, key=clave)


def _cuando(x, hoy: date) -> str:
    d = x.date() if isinstance(x, datetime) else x
    dia = "hoy" if d == hoy else ("mañana" if d == hoy + timedelta(days=1) else f"el {DIAS_SEMANA[d.weekday()]}")
    return f"{dia} a las {x.hour}:{x.minute:02d}" if isinstance(x, datetime) else f"{dia}, todo el día"


def frase_calendario(eventos: list[tuple], ahora: datetime) -> str:
    hoy = ahora.date()
    de_hoy = [e for e in eventos if (e[0].date() if isinstance(e[0], datetime) else e[0]) == hoy]
    resto = [e for e in eventos if e not in de_hoy]
    partes = []
    if de_hoy:
        partes.append("Hoy en tu calendario: " + "; ".join(
            (f"a las {x.hour}:{x.minute:02d}, {r}" if isinstance(x, datetime) else f"todo el día, {r}") for x, r in de_hoy)
            + ".")
    else:
        partes.append("Hoy no tienes nada en el calendario.")
    if resto:
        extra = len(resto) - MAX_EVENTOS_SEMANA
        partes.append("Esta semana: " + "; ".join(f"{_cuando(x, hoy)}, {r}" for x, r in resto[:MAX_EVENTOS_SEMANA])
                      + (f"; y {extra} más" if extra > 0 else "") + ".")
    return " ".join(partes)


def calendario(ahora: datetime, obtener=_http) -> str:
    url = valor("calendario.ical_url", "") or ""
    if not url:
        return ""
    try:
        texto = obtener(url).decode("utf-8", "replace")
        inicio = datetime.combine(ahora.date(), datetime.min.time())
        return frase_calendario(eventos_en(texto, inicio, inicio + timedelta(days=7)), ahora)
    except Exception as e:   # noqa: BLE001 - nunca se registra la URL: solo el tipo de fallo
        log.warning("brief: el calendario fallo (%s)", _fallo(e))
        return "No he podido leer el calendario."


# ------------------------------------------------------------------ 4) NEXO
def _tapar(texto: str) -> str:
    from nucleo import auditor
    return auditor.tapar(texto)


def _titulo_hablado(t: dict) -> str:
    """Sin el prefijo [Propuesta de Txxx] ni corchetes: se lee mejor y no dice ids."""
    titulo = re.sub(r"^\[[^\]]*\]\s*", "", str(t.get("titulo") or "")).strip()
    primera = re.split(r"[:;]\s", titulo)[0]
    titulo = re.sub(r"\s*\([^)]*\)?\s*$", "", primera if len(primera) >= 20 else titulo).strip()   # sin "(de T261..."
    if len(titulo) > 70:
        palabras = titulo[:70].split()[:-1]
        while palabras and palabras[-1].lower() in _VACIAS:   # que no acabe en "por", "de", "o"...
            palabras.pop()
        titulo = " ".join(palabras)
    return _tapar(titulo.rstrip(" .:;,"))


_VACIAS = {"de", "del", "la", "el", "los", "las", "por", "para", "o", "y", "a", "en", "que", "con", "si", "un", "una", "al"}


# Cierres que no son trabajo nuevo (Damian, 05/10): revisiones de borradores, integraciones que ya estaban hechas,
# investigaciones que se cierran solas al verificar su integracion, y tareas viejas que solo se han verificado.
_NO_NUEVO = ("ya hecha antes", "la investigacion queda cerrada", "la investigación queda cerrada")
VIEJA_DIAS = 7


def es_trabajo_nuevo(t: dict, corte: str) -> bool:
    titulo = str(t.get("titulo") or "")
    if titulo.lower().startswith("revisar borrador") or "revision" in (t.get("etiquetas") or []):
        return False
    notas = [str(n.get("texto") or "") for n in t.get("notas") or []]
    if any(x in n.lower() for n in notas for x in _NO_NUEVO):
        return False
    recientes = [str(n.get("texto") or "") for n in t.get("notas") or [] if str(n.get("cuando") or "") >= corte]
    trabajo = [n for n in recientes if not n.startswith("[verificado]") and "verificad" not in n.lower()[:80]]
    vieja = bool(t.get("creada")) and str(t["creada"]) < (datetime.fromisoformat(corte) - timedelta(days=VIEJA_DIAS)).strftime("%Y-%m-%d")
    return not (vieja and not trabajo)


def _resumen_corto(t: dict, max_palabras: int = 22) -> str:
    """El resumen humano de la tarea (o, si no tiene, la primera frase del detalle), corto y tapado."""
    texto = (t.get("resumen_humano") or "").strip()
    if not texto:
        texto = re.sub(r"^\s*(Damian|Damián|Claude|NEXO)\s*\d{1,2}/\d{1,2}\s*:\s*", "", str(t.get("detalle") or ""), flags=re.I)
        texto = re.sub(r"\s*\((?:ver |de |como )?T\d{3,}\b[^)]*\)", "", texto)
        texto = " ".join(texto.split())
        texto = re.split(r"\s(?:DONDE|VALOR|ESFUERZO|RIESGO|POR QU[EÉ]|C[OÓ]MO):", re.sub(r"^QU[EÉ]:\s*", "", texto))[0]
    if not texto:
        return ""
    frase = re.split(r"(?<=[.!?])\s+", texto)[0]
    palabras = frase.split()
    if len(palabras) > max_palabras:
        palabras = palabras[:max_palabras]
        while palabras and palabras[-1].lower() in _VACIAS:
            palabras.pop()
    return _tapar(" ".join(palabras).rstrip(" .:;,"))


def _titulo_claro(t: dict) -> str:
    """Para "Te toca": su resumen humano si lo tiene (lenguaje claro); si no, el titulo hablado sin "Opcional:"."""
    if (t.get("resumen_humano") or "").strip():
        return _resumen_corto(t, 16)
    return re.sub(r"^(opcional|pendiente|urgente)\s*:\s*", "", _titulo_hablado(t), flags=re.I)


def frase_nexo(ahora: datetime, tareas: list[dict] | None = None, decisiones: int | None = None) -> str:
    """Lo importante cerrado en las ultimas 24 h y lo que espera a Damian. Nunca una tarea cat:personal."""
    from nucleo import tareas as T
    tareas = T.cargar()["tareas"] if tareas is None else tareas
    visibles = [t for t in tareas if not T.es_personal(t)]
    corte = (ahora - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    hechas = [t for t in visibles if t.get("estado") == "hecha" and str(t.get("cerrada") or "") >= corte]
    hechas.sort(key=lambda t: (t.get("importancia") or 0, str(t.get("cerrada") or "")), reverse=True)
    nuevas = [t for t in hechas if es_trabajo_nuevo(t, corte)]
    from nucleo import responsables      # guardia de responsables: solo lo que de verdad es suyo
    todas_suyas = [t for t in tareas if t.get("estado") in T.VIVOS and t.get("estado") != "aparcada"
                   and responsables.es_suya(t)]
    suyas = T.ordenadas([t for t in todas_suyas if not T.es_personal(t)])   # titulos: nunca uno personal
    if decisiones is None:
        decisiones = _decisiones_pendientes()
    partes = []
    if hechas:
        frase = (f"En las últimas 24 horas NEXO ha cerrado {len(hechas)} {'tarea' if len(hechas) == 1 else 'tareas'}"
                 + (f", {len(nuevas)} de trabajo nuevo" if nuevas and len(nuevas) < len(hechas) else "") + ".")
        if nuevas:
            items = []
            for t in nuevas[:2]:
                titulo, r = _titulo_hablado(t), _resumen_corto(t)
                repetido = not r or r.lower().startswith(titulo.lower()[:30]) or titulo.lower().startswith(r.lower()[:30])
                items.append(titulo if repetido else f"{titulo}: {r[:1].lower() + r[1:]}")
            frase += " Lo más importante: " + ". ".join(items) + "."
        else:
            frase += " Han sido revisiones y comprobaciones; nada nuevo que contar."
        partes.append(frase)
    else:
        partes.append("En las últimas 24 horas NEXO no ha cerrado tareas.")
    if decisiones:
        partes.append(f"Tienes {decisiones} {'decisión' if decisiones == 1 else 'decisiones'} esperando en Bandejas.")
    if todas_suyas:
        n = len(todas_suyas)
        frase = f"Te {'toca una tarea' if n == 1 else f'tocan {n} tareas'}"
        if suyas:
            nombres = "; ".join(_titulo_claro(t) for t in suyas[:2])
            frase += f"; {'la primera' if len(suyas) == 1 or n == 1 else 'las primeras'}: {nombres}"
        partes.append(frase + ".")
    if not decisiones and not todas_suyas:
        partes.append("No hay nada esperándote.")
    return " ".join(partes)


def _decisiones_pendientes() -> int:
    """Lo mismo que cuenta "Te toca" del Centro (riesgo R1/R2 y tribunal), cada fuente por su lado."""
    n = 0
    try:
        from nucleo import riesgo
        m = riesgo.bandeja()
        n += len(m["r2"]) + len(m["r1"])
    except Exception:   # noqa: BLE001
        pass
    try:
        from nucleo import tribunal
        n += len(tribunal.bandeja_damian())
    except Exception:   # noqa: BLE001
        pass
    return n


def nexo(ahora: datetime) -> str:
    try:
        return frase_nexo(ahora)
    except Exception as e:   # noqa: BLE001
        log.warning("brief: el resumen de NEXO fallo (%s)", type(e).__name__)
        return "No he podido leer el resumen de NEXO."


# ------------------------------------------------------------------ el brief entero
def recortar(texto: str, maximo: int = MAX_PALABRAS) -> str:
    palabras = texto.split()
    if len(palabras) <= maximo:
        return texto
    corto = " ".join(palabras[:maximo])
    punto = corto.rfind(". ")
    return (corto[:punto + 1] if punto > len(corto) // 2 else corto.rstrip(",;:") + ".")


def componer(ahora: datetime | None = None, obtener=_http) -> str:
    ahora = ahora or datetime.now()
    partes = ["Hola Damián.", frase_hora(ahora), tiempo(ahora, obtener), calendario(ahora, obtener), nexo(ahora)]
    return recortar(" ".join(p for p in partes if p))


def _cli(argv: list[str]) -> int:
    if argv[:1] != ["texto"]:
        print("uso: python -m nucleo.brief texto   (solo genera el texto; no reproduce nada)")
        return 2
    texto = componer()
    print(texto)
    print(f"\n[{len(texto.split())} palabras]")
    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(_cli(sys.argv[1:]))
