# -*- coding: utf-8 -*-
"""Chat dentro de cada tarea (T290; diseno aprobado por Damian el 28/09 en el boceto de T230).

Quien contesta (minimo recurso suficiente)
------------------------------------------
- Ordenes claras ("subele la prioridad", "aparcala una semana"): reglas fijas, sin modelo.
- El resto lo interpreta Qwen local (gratis): si es una accion, la hace o la propone.
- Las dudas las contesta NVIDIA, el primer modelo vivo de config nvidia.modelos (T1039; lista blanca gratuita);
  de reserva Groq y Gemini API; si ninguno esta, Qwen local.
- Claude solo si Damian pulsa "Escalar": la pregunta queda en cola para la proxima sesion de Code
  (`python -m nucleo.chat_tarea escalados` / `responder`). No gasta nada hasta entonces.
- Si el contexto lleva algo privado (tarea cat:personal, rutas del PC, correos, claves) NO sale
  del PC: contesta Qwen local.

Contexto: solo esa tarea (titulo, resumen, detalle, notas, estado, relacionadas por titulo) y los
ultimos 10 mensajes. Nada de otras tareas ni secretos.

Acciones
--------
Solas (anotadas en la tarea y con deshacer): anotar, prioridad, estado entre pendiente / en marcha /
esperando, aparcar hasta una fecha, redactar el resumen humano.
Con el OK de Damian (cola de nucleo.aprobaciones, se aprueba en la propia conversacion): titulo,
anadir al detalle, cerrar, descartar, verificar, crear tarea, cualquier cosa que ejecute codigo o
salga del PC (esto ultimo el chat no lo ejecuta nunca: al aprobarlo queda como tarea nueva).

Historial
---------
memoria/chats_tareas/<id>.jsonl, solo-anadir: una linea por mensaje o suceso. Deshacer, aprobar o
denegar no reescriben lineas: anaden otra que apunta a la original (`ref`); `conversacion()` las
junta para pintar. Cada cambio en la tarea deja ademas una nota en la propia tarea.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

from nucleo import ahora as reloj
from nucleo import tareas as T
from nucleo.candado import bloqueo

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "memoria" / "chats_tareas"
CANDADO = CARPETA / ".candado_chats.lock"

MAX_MENSAJE = 2000
CONTEXTO_MENSAJES = 10

AUTO = ("anotar", "prioridad", "estado", "aparcar", "resumen")
CON_OK = ("titulo", "detalle", "estado_ok", "cerrar", "descartar", "verificar", "crear", "ejecutar")
ACCIONES = AUTO + CON_OK
ESTADOS_CHAT = {"pendiente": "por hacer", "en_curso": "en marcha", "esperando": "esperando"}
NIVELES_PRIO = {"alta": (5, 4), "media": (3, 3), "baja": (2, 2)}

NOMBRE_ACCION = {
    "anotar": "añadir una nota", "prioridad": "cambiar la prioridad", "estado": "cambiar el estado",
    "aparcar": "aparcarla", "resumen": "escribir el resumen", "titulo": "cambiar el título",
    "detalle": "añadir al detalle", "estado_ok": "cambiar el estado", "cerrar": "cerrarla como hecha",
    "descartar": "descartarla", "verificar": "verificarla con evidencia", "crear": "crear una tarea nueva",
    "ejecutar": "algo que ejecuta código o sale del PC",
}
QUIEN = {"damian": "Tú", "qwen": "Qwen", "nvidia": "NVIDIA", "groq": "Groq", "gemini_api": "Gemini",
         "reglas": "NEXO", "nexo": "NEXO", "claude": "Claude"}


CONTESTAN = ("respuesta", "accion", "propuesta", "escalado")   # lineas que responden a un mensaje (ref)


class ChatRechazado(ValueError):
    """El mensaje o la accion no se aceptan. El texto es para Damian."""


# ------------------------------------------------------------------ disco
def _ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _id_valido(tarea_id: str) -> str:
    tarea_id = (tarea_id or "").strip().upper()
    if not re.fullmatch(r"T\d{3,}", tarea_id):
        raise ChatRechazado("Identificador de tarea no válido.")
    return tarea_id


def ruta(tarea_id: str) -> Path:
    return CARPETA / f"{_id_valido(tarea_id)}.jsonl"


def historial(tarea_id: str) -> list[dict]:
    """Lineas crudas del chat (una por suceso). Una linea rota se salta, no tumba el chat."""
    p = ruta(tarea_id)
    if not p.is_file():
        return []
    lineas = []
    for bruta in p.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(bruta)
        except ValueError:
            continue
        if isinstance(d, dict) and isinstance(d.get("n"), int):
            lineas.append(d)
    return lineas


def _anadir(tarea_id: str, **linea) -> dict:
    CARPETA.mkdir(parents=True, exist_ok=True)
    with bloqueo(CANDADO):
        previas = historial(tarea_id)
        linea = {"n": (previas[-1]["n"] + 1) if previas else 1, "cuando": _ahora(), **linea}
        with ruta(tarea_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")
    return linea


def _linea(tarea_id: str, n: int) -> dict | None:
    return next((x for x in historial(tarea_id) if x["n"] == n), None)


# ------------------------------------------------------------ conversacion
def conversacion(tarea_id: str) -> list[dict]:
    """Lo que se pinta: cada mensaje con su estado ya resuelto (deshecha, aprobada, respondida...)."""
    lineas = historial(tarea_id)
    deshechas = {x["ref"] for x in lineas if x.get("tipo") == "deshecho"}
    decisiones = {x["ref"]: x for x in lineas if x.get("tipo") == "decision"}
    respondidas = {x["ref"] for x in lineas if x.get("tipo") in CONTESTAN and x.get("ref")}
    vivas = _estado_aprobaciones([x.get("aprobacion") for x in lineas if x.get("tipo") == "propuesta"])
    salida = []
    for x in lineas:
        x = dict(x, quien_nombre=QUIEN.get(x.get("quien", ""), x.get("quien", "")))
        if x.get("tipo") == "accion":
            x["deshecha"] = x["n"] in deshechas
        elif x.get("tipo") == "propuesta":
            d = decisiones.get(x["n"])
            x["estado"] = d["decision"] if d else ("caducada" if vivas.get(x.get("aprobacion")) == "caducada"
                                                  else "pendiente")
            x["resultado"] = d.get("texto", "") if d else ""
        elif x.get("tipo") == "mensaje":
            x["respondido"] = x["n"] in respondidas
        elif x.get("tipo") in ("deshecho", "decision"):
            continue          # se ve dentro de la linea a la que apuntan
        salida.append(x)
    return salida


def _estado_aprobaciones(ids: list) -> dict:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    # Solo lectura (pintar no escribe): una pendiente fuera de plazo se ve ya como caducada.
    try:
        from nucleo import aprobaciones
        ahora = _ahora()
        return {s["id"]: ("caducada" if s["estado"] == "pendiente" and (s.get("vence") or "9") < ahora else s["estado"])
                for s in aprobaciones.cargar()["solicitudes"] if s["id"] in ids}
    except Exception:
        return {}


def sin_contestar(tarea_id: str) -> dict | None:
    """El ultimo mensaje de Damian si todavia no tiene respuesta (para "Pensando..." o reintentar)."""
    lineas = historial(tarea_id)
    respondidas = {x.get("ref") for x in lineas if x.get("tipo") in CONTESTAN}
    for x in reversed(lineas):
        if x.get("tipo") == "mensaje":
            return None if x["n"] in respondidas else x
    return None


# ------------------------------------------------------------------ enviar
def enviar(tarea_id: str, texto: str, escalar: bool = False) -> dict:
    """Guarda el mensaje de Damian. El trabajo (interpretar, actuar, contestar) lo hace procesar()."""
    tarea_id = _id_valido(tarea_id)
    texto = (texto or "").strip()
    if not texto:
        raise ChatRechazado("Escribe algo antes de enviar.")
    if len(texto) > MAX_MENSAJE:
        raise ChatRechazado(f"El mensaje no puede pasar de {MAX_MENSAJE} caracteres.")
    from nucleo import parada
    motivo = parada.activa()
    if motivo is not None:
        raise ChatRechazado(f"PARADA de emergencia activa ({motivo}): el chat no hace nada hasta pulsar «Seguir».")
    if T.buscar(tarea_id) is None or T.buscar(tarea_id)["id"] != tarea_id:
        raise ChatRechazado(f"La tarea {tarea_id} no existe.")
    return _anadir(tarea_id, tipo="mensaje", quien="damian", texto=texto, escalar=bool(escalar))


def procesar(tarea_id: str, n: int) -> list[dict]:
    """Contesta al mensaje n: escalado, accion sola, propuesta con OK o respuesta a una duda."""
    tarea_id = _id_valido(tarea_id)
    msg = _linea(tarea_id, n)
    if msg is None or msg.get("tipo") != "mensaje":
        return []
    from nucleo import parada
    if parada.activa() is not None:
        return [_anadir(tarea_id, tipo="respuesta", quien="nexo", ref=n,
                        texto="PARADA activa: no hago nada con este mensaje. Cuando pulses «Seguir», vuelve a enviarlo.")]
    t = _tarea(tarea_id)
    if t is None:
        return [_anadir(tarea_id, tipo="respuesta", quien="nexo", ref=n, texto="Esta tarea ya no existe.")]
    if msg.get("escalar"):
        return [_escalar(t, msg)]
    intencion = interpretar(msg["texto"], t)
    accion = intencion["accion"]
    if accion in AUTO:
        return _hacer(t, msg, intencion)
    if accion in CON_OK:
        return [_proponer(t, msg, intencion)]
    return [_contestar(t, msg)]


def _tarea(tarea_id: str) -> dict | None:
    t = T.buscar(tarea_id)
    return t if t is not None and t["id"] == tarea_id else None


# ------------------------------------------------------------- interpretar
def _plano(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


DIAS_SEMANA = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
_NUMEROS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
            "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "quince": 15}


def fecha_de(texto: str, hoy: date | None = None) -> date | None:
    """'manana', 'una semana', '3 dias', 'un mes', 'el lunes', '5/10', '2026-10-05' -> fecha, o None."""
    hoy = hoy or date.today()
    s = _plano(texto)
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", s)
    if m:
        anio = int(m[3]) if m[3] else hoy.year
        anio += 2000 if anio < 100 else 0
        try:
            d = date(anio, int(m[2]), int(m[1]))
        except ValueError:
            return None
        return d if m[3] or d > hoy else date(anio + 1, d.month, d.day)
    if "pasado manana" in s:
        return hoy + timedelta(days=2)
    if re.search(r"\bmanana\b", s):
        return hoy + timedelta(days=1)
    for i, nombre in enumerate(DIAS_SEMANA):
        if re.search(rf"\b{nombre}\b", s):
            dias = (i - hoy.weekday()) % 7 or 7
            return hoy + timedelta(days=dias)
    m = re.search(r"\b(\d{1,3}|" + "|".join(_NUMEROS) + r")\s+(dia|semana|mes)(?:s|es)?\b", s)
    if m:
        k = int(m[1]) if m[1].isdigit() else _NUMEROS[m[1]]
        return hoy + timedelta(days=k * {"dia": 1, "semana": 7, "mes": 30}[m[2]])
    if re.search(r"\b(la|una) semana que viene\b|\bproxima semana\b", s):
        return hoy + timedelta(days=7)
    if re.search(r"\b(el|un) mes que viene\b|\bproximo mes\b", s):
        return hoy + timedelta(days=30)
    return None


_PREGUNTA = re.compile(r"^\s*(¿|que\b|como\b|por que\b|porque\b|cuando\b|cual|quien|donde|cuanto|explica|"
                       r"resume(me)?\b|dime\b|hay\b|es\b|esta\b|puedes explicar)")


_VERBOS_ACCION = re.compile(r"prioridad|aparca|anota|apunta|titulo|detalle|estado|en marcha|cierra|descarta|"
                            r"verifica|crea|resumen")


def reglas(texto: str, hoy: date | None = None) -> dict | None:
    """Ordenes claras que no necesitan modelo. None si no esta claro (lo mira Qwen)."""
    crudo = texto.strip()
    s = _plano(crudo)
    if "?" in s:
        # Una pregunta que habla de cambios ("¿me la aparcas?") la decide Qwen; las demas son dudas.
        return None if _VERBOS_ACCION.search(s) else {"accion": "pregunta", "valor": ""}
    m = re.match(r"^(?:anota|apunta|anade (?:una )?nota|nota)\s*[:,]?\s+(.+)$", s, re.S)
    if m:
        return {"accion": "anotar", "valor": crudo[len(crudo) - len(m[1]):].strip()}
    if "prioridad" in s:
        if re.search(r"\b(sube|subele|subir|aumenta|mas)\b", s):
            return {"accion": "prioridad", "valor": "subir"}
        if re.search(r"\b(baja|bajale|bajar|reduce|menos)\b", s) and not re.search(r"prioridad\s+baja", s):
            return {"accion": "prioridad", "valor": "bajar"}
        m = re.search(r"prioridad\s+(?:a\s+|en\s+)?(alta|media|baja)", s)
        if m:
            return {"accion": "prioridad", "valor": m[1]}
    if re.match(r"^(aparca|aparcala|aparcar|dejala|posponla|pospon)\b", s):
        d = fecha_de(s, hoy)
        if d:
            return {"accion": "aparcar", "valor": d.isoformat()}
    m = re.match(r"^(?:ponla|pasala|marcala|cambiala|dejala)?\s*(?:a|en|como)?\s*"
                 r"(por hacer|pendiente|en marcha|en curso|esperando)\s*\.?$", s)
    if m:
        return {"accion": "estado", "valor": {"por hacer": "pendiente", "pendiente": "pendiente", "en marcha": "en_curso",
                                              "en curso": "en_curso", "esperando": "esperando"}[m[1]]}
    if re.search(r"\b(haz|hazle|redacta|escribe|genera|actualiza)\b.*\bresumen\b", s):
        return {"accion": "resumen", "valor": ""}
    m = re.match(r"^(?:cambia|pon|renombra)\s+(?:el\s+)?titulo\s*(?:a|por|:)\s*(.+)$", s, re.S)
    if m:
        return {"accion": "titulo", "valor": crudo[len(crudo) - len(m[1]):].strip().strip('"«»')}
    m = re.match(r"^(?:anade|agrega|pon)\s+(?:en|al)\s+(?:el\s+)?detalle\s*(?:que\s+|:\s*)?(.+)$", s, re.S)
    if m:
        return {"accion": "detalle", "valor": crudo[len(crudo) - len(m[1]):].strip()}
    m = re.match(r"^(?:crea|abre|nueva)\s+(?:una\s+)?(?:nueva\s+)?tarea\s*(?:para\s+|:\s*)?(.+)$", s, re.S)
    if m:
        return {"accion": "crear", "valor": crudo[len(crudo) - len(m[1]):].strip()}
    if re.match(r"^(cierrala|cierra la tarea|cerrarla|marcala (como )?hecha|esta hecha|ya esta hecha)\b", s):
        return {"accion": "cerrar", "valor": ""}
    if re.match(r"^(descartala|descarta la tarea|descartar)\b", s):
        return {"accion": "descartar", "valor": ""}
    m = re.match(r"^(?:verificala|verifica la tarea|verificar)\s*(?:con\b)?\s*:?\s*(.*)$", s, re.S)
    if m:
        return {"accion": "verificar", "valor": crudo[len(crudo) - len(m[1]):].strip() if m[1] else ""}
    if _PREGUNTA.match(s):
        return {"accion": "pregunta", "valor": ""}
    return None


def _prompt_interpretar(texto: str, t: dict, hoy: date) -> str:
    return reloj.con_fecha(
        "Eres el interprete del chat de una tarea. Decide que quiere Damian con su mensaje y contesta "
        "SOLO un JSON en una linea: {\"accion\": \"...\", \"valor\": \"...\"}.\n"
        "Acciones posibles:\n"
        "- pregunta: una duda o conversacion (valor vacio). ANTE LA DUDA, pregunta.\n"
        "- anotar: guardar una nota (valor = texto de la nota).\n"
        "- prioridad: valor = subir | bajar | alta | media | baja.\n"
        "- estado: valor = pendiente | en_curso | esperando.\n"
        f"- aparcar: dejarla para mas tarde (valor = fecha AAAA-MM-DD; hoy es {hoy.isoformat()}).\n"
        "- resumen: escribir el resumen corto de la tarea (valor vacio).\n"
        "- titulo: cambiar el titulo (valor = titulo nuevo).\n"
        "- detalle: anadir algo al detalle (valor = texto a anadir).\n"
        "- cerrar: darla por hecha (valor = como quedo). descartar: abandonarla (valor = motivo).\n"
        "- verificar: comprobada con evidencia (valor = que se probo y que salio).\n"
        "- crear: crear otra tarea (valor = titulo).\n"
        "- ejecutar: ejecutar codigo, instalar, enviar, publicar o cualquier cosa fuera del PC (valor = que).\n"
        f"Tarea: {t['titulo']}\n"
        f"Mensaje de Damian: {texto}\n"
        "JSON:"
    )


def _qwen_interpretar(prompt: str) -> str | None:
    """Qwen local, respuesta corta. None si no esta (entonces se trata como pregunta)."""
    try:
        from extremidades import qwen
        if not qwen.disponible():
            return None
        return qwen.pedir(prompt, max_tokens=200, timeout=120.0)
    except Exception:
        return None


def validar(bruto: dict | None, hoy: date | None = None) -> dict:
    """Intencion saneada. Lo que no encaja se trata como pregunta: nunca se inventa una accion."""
    pregunta = {"accion": "pregunta", "valor": ""}
    if not isinstance(bruto, dict):
        return pregunta
    accion = str(bruto.get("accion") or "").strip().lower()
    valor = bruto.get("valor")
    valor = "" if valor is None else str(valor).strip()
    if accion not in ACCIONES and accion != "pregunta":
        return pregunta
    if accion == "prioridad" and valor not in ("subir", "bajar", *NIVELES_PRIO):
        return pregunta
    if accion == "estado":
        valor = {"por hacer": "pendiente", "en marcha": "en_curso", "en curso": "en_curso"}.get(valor, valor)
        if valor not in ESTADOS_CHAT:
            return {"accion": "estado_ok", "valor": valor} if valor in T.ESTADOS else pregunta
    if accion == "aparcar":
        d = fecha_de(valor, hoy)
        if d is None:
            return pregunta
        valor = d.isoformat()
    if accion in ("anotar", "titulo", "detalle", "crear", "ejecutar") and not valor:
        return pregunta
    if accion == "titulo" and len(valor) > 200:
        return pregunta
    return {"accion": accion, "valor": valor[:MAX_MENSAJE]}


def interpretar(texto: str, t: dict, hoy: date | None = None) -> dict:
    hoy = hoy or date.today()
    r = reglas(texto, hoy)
    if r is not None:
        return {**validar(r, hoy), "quien": "reglas"}
    bruto = _qwen_interpretar(_prompt_interpretar(texto, t, hoy))
    if not bruto:
        return {"accion": "pregunta", "valor": "", "quien": "reglas"}
    m = re.search(r"\{.*?\}", bruto, re.S)
    try:
        datos = json.loads(m.group(0)) if m else None
    except ValueError:
        datos = None
    return {**validar(datos, hoy), "quien": "qwen"}


# ----------------------------------------------------------- acciones solas
def _nota_chat(quien: str, texto: str) -> str:
    return f"Chat ({ {**QUIEN, 'damian': 'Damián'}.get(quien, quien)}): {texto}"


def _hacer(t: dict, msg: dict, it: dict) -> list[dict]:
    tid, accion, valor, quien = t["id"], it["accion"], it["valor"], it.get("quien", "reglas")
    if accion == "estado" and t["estado"] not in ESTADOS_CHAT:
        # Solo se mueve sola entre por hacer / en marcha / esperando; desde otro estado, con OK.
        return [_proponer(t, msg, {**it, "accion": "estado_ok"})]
    try:
        hecho = HACER[accion](t, valor, quien, msg)
    except (ChatRechazado, T.NoSePuedeAparcar) as e:
        return [_anadir(tid, tipo="respuesta", quien="nexo", ref=msg["n"], texto=f"No lo he hecho: {e}")]
    if hecho is None:
        return [_anadir(tid, tipo="respuesta", quien="nexo", ref=msg["n"], texto="No lo he hecho: la tarea ya no existe.")]
    return [_anadir(tid, tipo="accion", quien=quien, ref=msg["n"], accion=accion, **hecho)]


def _hacer_anotar(t, valor, quien, msg):
    texto = _nota_chat("damian", valor)
    r = T.anotar(t["id"], texto)
    if r is None:
        return None
    nota = r["notas"][-1]
    return {"texto": f"Nota añadida: «{valor}»", "antes": {}, "despues": {"nota": nota}}


def _prio_nueva(t: dict, valor: str) -> tuple[int, int]:
    imp, urg = int(t.get("importancia", 3)), int(t.get("urgencia", 3))
    if valor == "subir":
        return min(imp + 1, 5), min(urg + 1, 5)
    if valor == "bajar":
        return max(imp - 1, 1), max(urg - 1, 1)
    return NIVELES_PRIO[valor]


def _hacer_prioridad(t, valor, quien, msg):
    antes = {"importancia": int(t.get("importancia", 3)), "urgencia": int(t.get("urgencia", 3))}
    imp, urg = _prio_nueva(t, valor)
    despues = {"importancia": imp, "urgencia": urg}
    if despues == antes:
        raise ChatRechazado("la prioridad ya está en ese punto")
    palabra = {"subir": "subida", "bajar": "bajada"}.get(valor, f"puesta en {valor}")
    detalle = f"importancia {antes['importancia']}→{imp}, urgencia {antes['urgencia']}→{urg}"
    if T.actualizar(t["id"], **despues) is None:
        return None
    T.anotar(t["id"], _nota_chat(quien, f"prioridad {palabra} ({detalle}), pedido por Damián en el chat."))
    return {"texto": f"Prioridad {palabra} ({detalle})", "antes": antes, "despues": despues}


def _hacer_estado(t, valor, quien, msg):
    antes = {"estado": t["estado"]}
    if antes["estado"] == valor:
        raise ChatRechazado(f"ya está «{ESTADOS_CHAT[valor]}»")
    if T.actualizar(t["id"], estado=valor) is None:
        return None
    texto = f"estado de «{ESTADOS_CHAT[antes['estado']]}» a «{ESTADOS_CHAT[valor]}»"
    T.anotar(t["id"], _nota_chat(quien, f"{texto}, pedido por Damián en el chat."))
    return {"texto": texto[:1].upper() + texto[1:], "antes": antes, "despues": {"estado": valor}}


def _hacer_aparcar(t, valor, quien, msg):
    antes = {"estado": t["estado"], "aparcada_hasta": t.get("aparcada_hasta")}
    r = T.aparcar(t["id"], valor, nota=_nota_chat(quien, "pedido por Damián en el chat."))
    if r is None:
        return None
    return {"texto": f"Aparcada hasta el {date.fromisoformat(valor):%d/%m}: ese día vuelve sola",
            "antes": antes, "despues": {"estado": "aparcada", "aparcada_hasta": valor}}


def _hacer_resumen(t, valor, quien, msg):
    texto = valor or redactar_resumen(t)
    if not texto:
        raise ChatRechazado("Qwen no está disponible ahora para redactar el resumen")
    antes = {"resumen_humano": t.get("resumen_humano") or ""}
    if T.fijar_resumen_humano(t["id"], texto) is None:
        return None
    T.anotar(t["id"], _nota_chat("qwen" if not valor else quien, "resumen para Damián actualizado."))
    return {"texto": f"Resumen nuevo: «{texto}»", "antes": antes, "despues": {"resumen_humano": texto}}


HACER = {"anotar": _hacer_anotar, "prioridad": _hacer_prioridad, "estado": _hacer_estado,
         "aparcar": _hacer_aparcar, "resumen": _hacer_resumen}


def redactar_resumen(t: dict) -> str:
    """Resumen humano de 1-2 frases con Qwen local (gratis; el detalle puede ser privado)."""
    prompt = ("Escribe en espanol claro, en 1 o 2 frases (maximo 45 palabras), de que va esta tarea y que falta. "
              "Sin identificadores tipo T123, sin jerga, sin comillas. Solo el resumen.\n\n"
              f"Titulo: {t['titulo']}\nDetalle: {(t.get('detalle') or '')[:2500]}\n"
              f"Ultima nota: {((t.get('notas') or [{}])[-1].get('texto') or '')[:500]}")
    try:
        from extremidades import qwen
        if not qwen.disponible():
            return ""
        texto = qwen.pedir(prompt, max_tokens=300, timeout=180.0) or ""
    except Exception:
        return ""
    return " ".join(texto.split()).strip().strip('"«»')[:400]


# ------------------------------------------------------------------ deshacer
def deshacer(tarea_id: str, n: int) -> dict:
    """Deshace la accion n si la tarea sigue como la dejo el chat. ChatRechazado si no se puede."""
    tarea_id = _id_valido(tarea_id)
    x = _linea(tarea_id, n)
    if x is None or x.get("tipo") != "accion":
        raise ChatRechazado("Esa acción no existe.")
    if any(y.get("tipo") == "deshecho" and y.get("ref") == n for y in historial(tarea_id)):
        raise ChatRechazado("Ya estaba deshecha.")
    t = _tarea(tarea_id)
    if t is None:
        raise ChatRechazado("La tarea ya no existe.")
    accion, antes, despues = x["accion"], x.get("antes") or {}, x.get("despues") or {}
    if accion == "anotar":
        nota = despues.get("nota") or {}
        if T.quitar_nota(tarea_id, nota.get("cuando", ""), nota.get("texto", "")) is None:
            raise ChatRechazado("La nota ya no está en la tarea.")
        texto = "Nota quitada"
    else:
        actual = {k: t.get(k) for k in despues}
        if accion == "resumen":
            actual = {"resumen_humano": t.get("resumen_humano") or ""}
        if actual != despues:
            raise ChatRechazado("La tarea ha cambiado después (a mano o por NEXO): no lo deshago para no pisar ese cambio.")
        if accion == "aparcar":
            if antes.get("estado") == "aparcada" and antes.get("aparcada_hasta"):
                try:
                    T.aparcar(tarea_id, antes["aparcada_hasta"], nota="Chat: deshecho el cambio de fecha.")
                except T.NoSePuedeAparcar:
                    T.recuperar(tarea_id, "Chat: deshecho el aparcamiento (la fecha anterior ya pasó).")
            else:
                T.recuperar(tarea_id, "Chat: deshecho el aparcamiento.")
        elif accion == "resumen":
            T.fijar_resumen_humano(tarea_id, antes.get("resumen_humano") or "")
            T.anotar(tarea_id, "Chat: deshecho el cambio de resumen.")
        else:
            T.actualizar(tarea_id, **antes)
            T.anotar(tarea_id, f"Chat: deshecho por Damián: {x.get('texto', accion)}.")
        texto = "Deshecho"
    return _anadir(tarea_id, tipo="deshecho", quien="damian", ref=n, texto=texto)


# ----------------------------------------------------------- con aprobacion
def _accion_aprobacion(tarea_id: str, accion: str) -> str:
    return f"chat_tarea:{accion}:{tarea_id}"


def _proponer(t: dict, msg: dict, it: dict) -> dict:
    from nucleo import aprobaciones
    accion, valor = it["accion"], it["valor"]
    if accion == "estado_ok":
        valor = valor if valor in T.ESTADOS else "pendiente"
    detalle = json.dumps({"tarea": t["id"], "accion": accion, "valor": valor, "mensaje": msg["n"]},
                         ensure_ascii=False, sort_keys=True)
    s = aprobaciones.solicitar(_accion_aprobacion(t["id"], accion), detalle, nivel="ambar", origen="chat_tarea")
    return _anadir(t["id"], tipo="propuesta", quien=it.get("quien", "reglas"), ref=msg["n"], accion=accion,
                   valor=valor, aprobacion=s["id"], texto=describir_propuesta(t, accion, valor))


def describir_propuesta(t: dict, accion: str, valor: str) -> str:
    if accion == "titulo":
        return f"Cambiar el título a «{valor}»"
    if accion == "detalle":
        return f"Añadir al detalle: «{valor}»"
    if accion == "estado_ok":
        return f"Cambiar el estado a «{ESTADOS_CHAT.get(valor, valor)}»"
    if accion == "cerrar":
        return "Cerrarla como hecha (quedará SIN TESTEAR hasta verificarla)" + (f": «{valor}»" if valor else "")
    if accion == "descartar":
        return "Descartarla" + (f" («{valor}»)" if valor else "")
    if accion == "verificar":
        return f"Verificarla con esta evidencia: «{valor}»" if valor else "Verificarla (falta escribir la evidencia)"
    if accion == "crear":
        return f"Crear una tarea nueva: «{valor}»"
    return (f"«{valor}». El chat nunca ejecuta código ni sale del PC: si lo apruebas, queda como tarea nueva "
            "para que lo haga un turno o Claude")


def decidir(tarea_id: str, n: int, aprobar: bool) -> dict:
    """Damian aprueba o deniega la propuesta n. Si aprueba, se ejecuta ahora (una sola vez)."""
    from nucleo import aprobaciones
    tarea_id = _id_valido(tarea_id)
    x = _linea(tarea_id, n)
    if x is None or x.get("tipo") != "propuesta":
        raise ChatRechazado("Esa propuesta no existe.")
    if any(y.get("tipo") == "decision" and y.get("ref") == n for y in historial(tarea_id)):
        raise ChatRechazado("Esa propuesta ya estaba decidida.")
    aid = x["aprobacion"]
    detalle = json.dumps({"tarea": tarea_id, "accion": x["accion"], "valor": x["valor"], "mensaje": x["ref"]},
                         ensure_ascii=False, sort_keys=True)
    try:
        if not aprobar:
            aprobaciones.denegar(aid, quien="damian", motivo="web: chat de la tarea")
            T.anotar(tarea_id, _nota_chat("damian", f"NO aprobado: {x['texto']}."))
            return _anadir(tarea_id, tipo="decision", quien="damian", ref=n, decision="denegada", texto="No aprobado.")
        aprobaciones.aprobar(aid, quien="damian", motivo="web: chat de la tarea")
        aprobaciones.consumir(aid, _accion_aprobacion(tarea_id, x["accion"]), detalle)
    except aprobaciones.EstadoInvalido as e:
        caducada = "caducad" in str(e)
        texto = ("Caducó sin respuesta (el silencio cuenta como no). Si aún lo quieres, pídelo otra vez."
                 if caducada else f"No se puede decidir: {e}")
        return _anadir(tarea_id, tipo="decision", quien="nexo", ref=n, decision="caducada" if caducada else "error",
                       texto=texto)
    except (aprobaciones.NoEncontrada, aprobaciones.NoCoincide) as e:
        return _anadir(tarea_id, tipo="decision", quien="nexo", ref=n, decision="error", texto=f"No se ha hecho: {e}")
    try:
        resultado = _ejecutar(tarea_id, x["accion"], x["valor"])
        decision = "aprobada"
    except (ChatRechazado, T.RevisionPendiente) as e:
        resultado, decision = f"Aprobada, pero no se ha podido hacer: {e}", "error"
    T.anotar(tarea_id, _nota_chat("damian", f"aprobado «{x['texto']}» → {resultado}"))
    return _anadir(tarea_id, tipo="decision", quien="damian", ref=n, decision=decision, texto=resultado)


def _ejecutar(tarea_id: str, accion: str, valor: str) -> str:
    t = _tarea(tarea_id)
    if t is None:
        raise ChatRechazado("la tarea ya no existe")
    if accion == "titulo":
        T.actualizar(tarea_id, titulo=valor)
        return f"Título cambiado (antes: «{t['titulo']}»)."
    if accion == "detalle":
        T.actualizar(tarea_id, detalle=((t.get("detalle") or "").rstrip() + f"\n\n[chat {_ahora()[:10]}] {valor}").strip())
        return "Añadido al detalle."
    if accion == "estado_ok":
        if valor not in T.ESTADOS:
            raise ChatRechazado("estado no válido")
        campos = {"estado": valor}
        if t["estado"] == "hecha" and valor != "hecha":
            campos["testeado"] = False       # reabrir quita el testeado (Principio de Verdad)
        T.actualizar(tarea_id, **campos)
        return f"Estado cambiado de «{t['estado']}» a «{valor}»."
    if accion == "cerrar":
        if t["estado"] == "hecha":
            raise ChatRechazado("ya estaba cerrada")
        T.completar(tarea_id, _nota_chat("damian", valor) if valor else "",   # T1010: cierre a mano de Damian
                    despues="nada: cerrada a mano por Damian desde el chat de la tarea",
                    cierre=T.cierre_ok(evidencia=f"Cerrada a mano por Damian desde el chat de la tarea. {valor}".strip()))
        return "Cerrada como HECHO SIN TESTEAR: falta verificarla con evidencia."
    if accion == "descartar":
        # T688 pieza 4: en una propuesta, lo que Damian escribe es el motivo (idea: lo decide el, no un borrador)
        T.actualizar(tarea_id, estado="descartada", causa="idea", motivo=valor)
        return "Descartada."
    if accion == "verificar":
        if t["estado"] != "hecha":
            raise ChatRechazado("solo se verifica una tarea hecha: ciérrala primero")
        from nucleo import evidencias
        vale, motivo = evidencias.evaluar(valor)
        if not vale:
            raise ChatRechazado(f"no vale como evidencia ({motivo}); di qué se probó y qué salida dio")
        r = T.verificar(tarea_id, valor)
        if r is None or not r.get("testeado"):
            raise ChatRechazado("no se pudo verificar")
        return "Verificada con evidencia: HECHO Y TESTEADO."
    if accion in ("crear", "ejecutar"):
        titulo = valor if accion == "crear" else f"Hacer (pedido en el chat de {tarea_id}): {valor}"
        nueva = T.anadir(titulo[:200], detalle=f"Creada desde el chat de {tarea_id} · {t['titulo']}.\nPetición: {valor}",
                         depende="ia", etiquetas=["origen:chat_tarea", f"tarea_origen:{tarea_id}"])
        if accion == "crear":
            return f"Creada {nueva['id']} · {nueva['titulo']}."
        return f"El chat no lo ejecuta: queda como {nueva['id']} para un turno o para Claude."
    raise ChatRechazado("acción desconocida")


# ------------------------------------------------------------------- dudas
def contexto(t: dict, tarea_id: str | None = None) -> str:
    """Solo esa tarea y los ultimos 10 mensajes. Nada de otras tareas (las relacionadas, solo por titulo)."""
    notas = t.get("notas") or []
    rel = []
    for e in (t.get("bloqueada_por") or "",) + tuple(x.split(":", 1)[1] for x in t.get("etiquetas") or []
                                                      if x.startswith("tarea_origen:")):
        if e:
            r = T.buscar(e)
            if r is not None and r["id"] == e.upper() and not T.es_personal(r):
                rel.append(f"- {r['titulo']} ({r['estado']})")
    lineas = [f"Titulo: {t['titulo']}",
              f"Estado: {t['estado']}" + (f" (aparcada hasta {t['aparcada_hasta']})" if t.get("aparcada_hasta") else ""),
              f"Importancia {t.get('importancia')}/5, urgencia {t.get('urgencia')}/5, depende de: {t.get('depende')}"]
    if t.get("resumen_humano"):
        lineas.append(f"Resumen: {t['resumen_humano']}")
    lineas.append(f"Detalle: {(t.get('detalle') or '(sin detalle)')[:3000]}")
    if notas:
        lineas.append("Notas (de la mas antigua a la mas reciente):")
        lineas += [f"- {n.get('cuando', '')[:10]}: {(n.get('texto') or '')[:500]}" for n in notas[-8:]]
    if rel:
        lineas.append("Tareas relacionadas (solo titulo):")
        lineas += rel
    previos = [x for x in historial(tarea_id or t["id"]) if x.get("tipo") in ("mensaje", "respuesta", "accion", "propuesta")]
    if previos:
        lineas.append("Conversacion reciente:")
        for x in previos[-CONTEXTO_MENSAJES:]:
            quien = "Damian" if x.get("quien") == "damian" else "Asistente"
            lineas.append(f"{quien}: {(x.get('texto') or '')[:600]}")
    return "\n".join(lineas)


def _prompt_duda(t: dict, pregunta: str) -> str:
    return reloj.con_fecha("Eres el asistente del chat de UNA tarea del proyecto personal de Damian. Contesta en espanol claro, "
            "breve (maximo 120 palabras), sin jerga ni identificadores internos, usando SOLO la informacion de "
            "abajo. Si no esta ahi, dilo. No digas que has hecho cambios: tu solo contestas. Si Damian quiere "
            "un cambio, dile que lo pida en una frase (por ejemplo: 'subele la prioridad', 'aparcala una semana', "
            "'anota: ...').\n\n"
            f"{contexto(t)}\n\nPregunta de Damian: {pregunta}\nRespuesta:")


def privado(t: dict, prompt: str) -> list[str]:
    """Motivos por los que este prompt NO puede salir del PC (vacio = puede)."""
    from nucleo import auditor
    motivos = auditor.motivos_privados(prompt)   # T750: tambien el texto del perfil privado
    if T.es_personal(t):
        motivos.append("tarea personal")
    return motivos


def proveedores_dudas() -> list:
    """Orden de quien contesta: NVIDIA (primer vivo de config, T1039), Groq, Gemini API. (Qwen local va aparte.)"""
    import proveedores as P
    return [P.NvidiaProvider(modelos=(P.modelo_nvidia_principal(),), timeout=90.0, max_tokens=1500),
            P.GroqProvider(rondas=1, timeout=60.0), P.GeminiAPIProvider(rondas=1, timeout=60.0)]


def _qwen_proveedor():
    import proveedores as P
    return P.QwenProvider()


def _contestar(t: dict, msg: dict) -> dict:
    prompt = _prompt_duda(t, msg["texto"])
    motivos = privado(t, prompt)
    fallos = []
    candidatos = [] if motivos else proveedores_dudas()
    for prov in candidatos + [_qwen_proveedor()]:
        try:
            if not prov.disponible():
                fallos.append(f"{prov.nombre}: no disponible")
                continue
            r = prov.enviar(prompt)
        except Exception as e:
            fallos.append(f"{prov.nombre}: {type(e).__name__}")
            continue
        if r.ok and r.texto.strip():
            extra = {"modelo": getattr(prov, "ultimo_modelo", "") or r.meta.get("modelo", "")}
            if motivos:
                extra["solo_local"] = "; ".join(motivos)
            return _anadir(t["id"], tipo="respuesta", quien=prov.nombre, ref=msg["n"], texto=r.texto.strip()[:4000],
                           **extra)
        fallos.append(f"{prov.nombre}: {r.estado}")
    return _anadir(t["id"], tipo="respuesta", quien="nexo", ref=msg["n"], error=True,
                   texto="Ahora mismo no me contesta ninguna IA (ni NVIDIA, ni Groq, ni Gemini, ni Qwen en tu PC). "
                         "Vuelve a intentarlo en un rato o pulsa «Escalar» para que lo vea Claude.",
                   fallos=fallos)


# ------------------------------------------------------------------ escalar
def _escalar(t: dict, msg: dict) -> dict:
    T.anotar(t["id"], _nota_chat("damian", f"pregunta escalada a Claude: «{msg['texto'][:300]}»"))
    return _anadir(t["id"], tipo="escalado", quien="nexo", ref=msg["n"],
                   texto="Guardada para Claude: la verá en la próxima sesión de Code y contestará aquí. "
                         "No gasta nada hasta entonces.")


def escalados() -> list[dict]:
    """Preguntas escaladas a Claude sin contestar, de todos los chats (las mas antiguas primero)."""
    salida = []
    if not CARPETA.is_dir():
        return salida
    for p in sorted(CARPETA.glob("T*.jsonl")):
        lineas = historial(p.stem)
        contestadas = {x.get("ref") for x in lineas if x.get("tipo") == "respuesta" and x.get("quien") == "claude"}
        mensajes = {x["n"]: x for x in lineas if x.get("tipo") == "mensaje"}
        for x in lineas:
            if x.get("tipo") == "escalado" and x["n"] not in contestadas:
                m = mensajes.get(x.get("ref"), {})
                salida.append({"tarea": p.stem, "n": x["n"], "cuando": x["cuando"], "pregunta": m.get("texto", "")})
    return sorted(salida, key=lambda e: e["cuando"])


def responder_claude(tarea_id: str, n: int, texto: str) -> dict:
    """Claude contesta a la pregunta escalada n (desde una sesion de Code)."""
    tarea_id = _id_valido(tarea_id)
    x = _linea(tarea_id, n)
    if x is None or x.get("tipo") != "escalado":
        raise ChatRechazado(f"No hay pregunta escalada {n} en {tarea_id}.")
    if not texto.strip():
        raise ChatRechazado("Respuesta vacía.")
    T.anotar(tarea_id, _nota_chat("claude", "contestada la pregunta escalada del chat."))
    return _anadir(tarea_id, tipo="respuesta", quien="claude", ref=n, texto=texto.strip()[:8000])


def esperan_ok() -> list[dict]:
    """Propuestas del chat que esperan el OK de Damian, de todas las tareas (para el Centro)."""
    salida = []
    if not CARPETA.is_dir():
        return salida
    for p in sorted(CARPETA.glob("T*.jsonl")):
        for x in conversacion(p.stem):
            if x.get("tipo") == "propuesta" and x.get("estado") == "pendiente":
                salida.append({"tarea": p.stem, "n": x["n"], "cuando": x["cuando"], "texto": x.get("texto", "")})
    return sorted(salida, key=lambda e: e["cuando"])


# ---------------------------------------------------------------------- CLI
def _cli(argv: list[str]) -> int:
    uso = ("uso: python -m nucleo.chat_tarea escalados\n"
           "     python -m nucleo.chat_tarea ver Txxx\n"
           "     python -m nucleo.chat_tarea responder Txxx N \"respuesta\"")
    if not argv:
        print(uso)
        return 2
    try:
        if argv[0] == "escalados":
            lista = escalados()
            if not lista:
                print("Ninguna pregunta escalada pendiente.")
            for e in lista:
                t = T.buscar(e["tarea"]) or {}
                print(f"{e['tarea']} #{e['n']} ({e['cuando']}) · {t.get('titulo', '')}\n    {e['pregunta']}")
            return 0
        if argv[0] == "ver" and len(argv) == 2:
            for x in conversacion(argv[1]):
                print(f"#{x['n']} {x['cuando']} {x['quien_nombre']} [{x.get('tipo')}]: {x.get('texto', '')}")
            return 0
        if argv[0] == "responder" and len(argv) == 4:
            r = responder_claude(argv[1], int(argv[2]), argv[3])
            print(f"Respondida: {argv[1]} #{r['ref']} -> linea {r['n']}")
            return 0
    except ChatRechazado as e:
        print(f"ERROR: {e}")
        return 1
    print(uso)
    return 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    from nucleo import consola
    consola.preparar()   # consola cp1252 de Windows: '?' en lo que no cabe, tildes intactas
    sys.exit(_cli(sys.argv[1:]))
