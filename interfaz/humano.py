# -*- coding: utf-8 -*-
"""T230 (boceto): traduce lo que NEXO guarda para las IAs a palabras que entiende Damian.

Solo presenta: no cambia ningun dato. Lo crudo (ids, etiquetas cat:/prov:/tema:, estados del
core) sigue disponible en el "Detalle tecnico" de cada pantalla.
"""
from __future__ import annotations

import re
from datetime import datetime

# estado_real del core -> (nombre corto, que significa en una frase, clase CSS, grupo del filtro)
ESTADOS = {
    "PLANIFICADO": ("Por hacer", "Está en la cola; nadie la ha empezado todavía.", "por-hacer", "por_hacer"),
    "EN PROCESO": ("En marcha", "Alguien está trabajando en ella ahora.", "en-marcha", "en_marcha"),
    "ESPERANDO": ("Esperando", "Está parada hasta que llegue algo (una respuesta, un dato, una fecha).", "esperando", "atascadas"),
    "BLOQUEADO": ("Atascada", "No puede avanzar hasta que se resuelva otra cosa.", "atascada", "atascadas"),
    "APARCADA": ("Aparcada", "Se dejó para más adelante a propósito.", "aparcada", "aparcadas"),
    "PROPUESTA (sin revisar)": ("Idea sin revisar", "La propuso NEXO u otra IA; Claude tiene que decidir si vale.", "propuesta", "propuestas"),
    "HECHO SIN TESTEAR": ("Hecha, falta comprobarla", "Se hizo, pero nadie ha demostrado todavía que funciona.", "sin-comprobar", "sin_comprobar"),
    "HECHO Y TESTEADO": ("Hecha y comprobada", "Hecha y con prueba de que funciona.", "comprobada", "hechas"),
    "DESCARTADA": ("Descartada", "Se decidió no hacerla.", "descartada", "descartadas"),
}

# Grupos del filtro "Estado", en el orden en que se leen
GRUPOS = [
    ("vivas", "Pendientes (sin aparcadas)"),
    ("por_hacer", "Por hacer"),
    ("en_marcha", "En marcha"),
    ("atascadas", "Atascadas o esperando"),
    ("propuestas", "Ideas sin revisar"),
    ("aparcadas", "Aparcadas (vuelven solas)"),
    ("sin_comprobar", "Hechas, falta comprobarlas"),
    ("hechas", "Hechas y comprobadas"),
    ("descartadas", "Descartadas"),
    ("todas", "Todas, también cerradas"),
]
# Las aparcadas NO cuentan como pendientes: salen de la lista y vuelven solas su dia (boceto, punto 4)
GRUPOS_VIVOS = {"por_hacer", "en_marcha", "atascadas", "propuestas"}

QUIEN = {"ia": "Lo hace NEXO", "damian": "Te toca a ti", "externo": "Depende de otros", "claude": "Espera a Claude"}
QUIEN_CORTO = {"ia": "NEXO", "damian": "Tú", "externo": "Otros", "claude": "Claude"}

CATEGORIAS = {
    "codigo": "Programación", "investigacion": "Investigación", "propuesta": "Propuesta de mejora",
    "revision": "Revisión de un trabajo", "arquitectura": "Diseño del sistema", "personal": "Personal",
    "operacion_pc": "Manejo del PC", "seguridad": "Seguridad", "redaccion": "Redacción",
    "monetizacion": "Ganar dinero", "prueba": "Prueba", "resumen": "Resumen",
}
PROVEEDORES = {
    "claude": "Claude", "claude_web": "Claude (web de NEXO)", "gemini": "Gemini (web)", "gemini_api": "Gemini (API)", "chatgpt": "ChatGPT",
    "qwen": "Qwen (local)", "groq": "Groq", "nvidia": "NVIDIA", "nexo": "NEXO", "damian": "Tú",
}
TEMAS = {
    "interfaz_app_voz": "Web, app y voz", "modelos_proveedores_roles": "Modelos e IAs",
    "orquestacion": "Cómo se reparte el trabajo", "ahorro_claude_dev": "Ahorrar uso de Claude",
    "contenido_personal": "Contenido personal", "infraestructura": "Infraestructura",
    "memoria_contexto": "Memoria de NEXO", "recursos_por_identificar": "Recursos por identificar",
    "seguridad": "Seguridad", "seguridad_permisos": "Seguridad y permisos",
    "navegador": "Navegador", "navegador_pc": "Navegador y PC",
}
ORIGENES = {
    "damian_chat": "Tú, hablando con Claude", "orden_web": "Tú, desde la web", "orden_telegram": "Tú, por Telegram",
    "orden_claude": "Claude", "telegram_libre": "Tú, mensaje suelto de Telegram",
    "auditoria-v61": "Auditoría del sistema", "investigacion-t081": "Una investigación",
    "revision_claude_2709": "Revisión de Claude",
}
# Prefijos de etiquetas que son solo para las IAs: nunca en la vista principal
TECNICAS = ("de_borrador:", "tarea_origen:", "auditoria_id:", "bloque:", "junto_a:", "router:", "revision:",
            "borrador:", "rehacer:", "revisado:", "escalado:", "propuesta:")

# IAs: nombre visible y monograma. El color de marca va en boceto.css (.bc-marca-<clave>): la CSP no deja
# estilos en linea ni logos de fuera. Bloquear y ordenar cada IA desde la web llegara con T195.
IAS = {"qwen": ("Qwen", "Q"), "gemini_api": ("Gemini API", "G"), "groq": ("Groq", "g"), "nvidia": ("NVIDIA", "N"),
       "gemini": ("Gemini", "G"), "chatgpt": ("ChatGPT", "C"), "claude": ("Claude", "C"),
       "claude_web": ("Claude web", "C")}   # T667: cuenta propia de NEXO, solo apelacion del tribunal  # Damian 28/09: C, no A
SALUD_IA = {"disponible": ("verde", "lista"), "enfriamiento": ("ambar", "descansando por límite de uso"),
            "no_disponible": ("rojo", "no disponible"), "error": ("rojo", "no se pudo comprobar"),
            "apagado": ("rojo", "apagada a mano")}   # T549


def ia(clave: str, salud: str) -> dict:
    nombre, letra = IAS.get(clave, (clave.capitalize(), clave[:1].upper()))
    punto, texto = SALUD_IA.get(salud, ("rojo", salud))
    return {"clave": clave if clave in IAS else "otra", "nombre": nombre, "letra": letra, "punto": punto, "texto": texto}


VEREDICTOS = {
    "APROBADO": "Claude lo revisó y lo dio por bueno",
    "REHACER": "Claude lo revisó: hay que rehacerlo",
    "DESCARTADO": "Claude lo revisó y lo descartó",
    "SUPERADO": "Ya no hace falta: se resolvió por otro camino",
}

# Puntos del checklist del auditor (nucleo/auditor.py) cuando FALLAN, en palabras normales
FALLOS_AUDITOR = {
    "a_modo": "no se comprobó en pantalla que la IA web estaba en el modo correcto",
    "b_conversacion": "el trabajo se repartió en varias conversaciones en vez de una",
    "c_prompt": "el encargo a la otra IA llevaba jerga interna o datos que no debía salir de casa",
    "d_revision": "nadie de otra marca de IA revisó el resultado",
    "e_ok_absoluto": "la IA no llegó a dar su trabajo por terminado y comprobado",
    "f_alcance": "se le pidieron a la IA cosas fuera del encargo",
    "g_lectura": "la respuesta se leyó mal (traía texto de la propia página web)",
    "h_propuestas": "las propuestas venían incompletas",
}


# ---------------------------------------------------------------------- fechas
def _fecha(texto: str | None) -> datetime | None:
    if not texto:
        return None
    try:
        return datetime.strptime(str(texto)[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(str(texto)[:10], "%Y-%m-%d")
        except ValueError:
            return None


def hace(texto: str | None, ahora: datetime | None = None) -> str:
    """'hace 5 min', 'hoy a las 08:32', 'ayer a las 23:10', 'hace 3 días', 'el 12/09'."""
    f = _fecha(texto)
    if f is None:
        return "—"
    ahora = ahora or datetime.now()
    seg = (ahora - f).total_seconds()
    if seg < 0:
        return f"el {f:%d/%m}"
    if seg < 60:
        return "hace un momento"
    if seg < 3600:
        return f"hace {int(seg // 60)} min"
    dias = (ahora.date() - f.date()).days
    if dias == 0:
        return f"hoy a las {f:%H:%M}"
    if dias == 1:
        return f"ayer a las {f:%H:%M}"
    if dias < 14:
        return f"hace {dias} días"
    return f"el {f:%d/%m}"


def plazo(dias: int | None) -> str:
    if dias is None:
        return ""
    if dias < 0:
        return f"venció hace {-dias} día{'s' if dias != -1 else ''}"
    if dias == 0:
        return "vence hoy"
    if dias == 1:
        return "vence mañana"
    return f"vence en {dias} días"


# ---------------------------------------------------------------------- tareas
def estado(estado_real: str) -> dict:
    nombre, frase, clase, grupo = ESTADOS.get(estado_real, (estado_real.capitalize(), "", "otro", "otros"))
    return {"nombre": nombre, "frase": frase, "clase": clase, "grupo": grupo, "crudo": estado_real}


def etiquetas(lista: list[str] | None) -> dict:
    """Separa las etiquetas en lo que se muestra (categoria, tema, proveedor, origen) y lo tecnico."""
    salida = {"categoria": "", "tema": "", "proveedor": "", "origen": "", "otras": [], "tecnicas": []}
    for e in lista or []:
        pre, _, valor = e.partition(":")
        if pre == "cat" and not salida["categoria"]:
            salida["categoria"] = CATEGORIAS.get(valor, valor.replace("_", " ").capitalize())
        elif pre == "tema" and not salida["tema"]:
            salida["tema"] = TEMAS.get(valor, valor.replace("_", " ").capitalize())
        elif pre == "prov" and not salida["proveedor"]:
            salida["proveedor"] = PROVEEDORES.get(valor, valor.capitalize())
        elif pre == "origen" and not salida["origen"]:
            salida["origen"] = ORIGENES.get(valor, valor.replace("_", " ").replace("-", " "))
        elif e.startswith(TECNICAS) or ":" in e:
            salida["tecnicas"].append(e)
        else:
            salida["otras"].append(e.replace("_", " ").replace("-", " "))
    return salida


_PREFIJO = re.compile(r"^\s*(Damian|Damián|Claude|NEXO)\s*\d{1,2}/\d{1,2}\s*:\s*", re.I)
_REFERENCIAS = re.compile(r"\s*\((?:ver |de |como )?T\d{3,}\b[^)]*\)")


def resumen(t: dict, max_car: int = 260) -> dict:
    """Resumen humano de 1-2 frases. Si la tarea tiene `resumen_humano` (lo generara Qwen, T230 punto 4)
    se usa tal cual; si no, se saca provisionalmente del detalle y se marca como provisional."""
    propio = (t.get("resumen_humano") or "").strip()
    if propio:
        return {"texto": propio, "provisional": False}
    texto = _PREFIJO.sub("", (t.get("detalle") or "").strip())
    texto = _REFERENCIAS.sub("", texto)
    texto = re.split(r"\n\s*(?:1\)|\d\.|-)\s", texto)[0]       # antes de la primera lista numerada
    texto = " ".join(texto.split())
    frases = re.split(r"(?<=[.!?])\s+", texto)
    corto = " ".join(frases[:2]).strip()
    corto = corto[:1].upper() + corto[1:]
    if len(corto) > max_car:
        corto = corto[:max_car].rsplit(" ", 1)[0] + "…"
    return {"texto": corto, "provisional": True}


def prioridad(puntuacion: float) -> tuple[str, str]:
    """Puntuacion del core -> (palabras, clase). Umbrales mirando la cola real (vivas: mediana ~9, maximo ~19)."""
    if puntuacion >= 13:
        return "Muy importante", "prio-alta"
    if puntuacion >= 8:
        return "Importante", "prio-media"
    return "Cuando se pueda", "prio-baja"


# ---------------------------------------------------------------------- avisos
def aviso_auditoria(a: dict) -> dict:
    """Una delegacion auditada contada para Damian: que paso, por que y que pasa ahora."""
    fallos = [FALLOS_AUDITOR.get(k, k) for k in a.get("fallos") or []]
    rev = a.get("revisado")
    if rev:
        v = str(rev.get("veredicto") or "").upper()
        que_pasa = VEREDICTOS.get(v, f"Claude lo revisó ({v.lower()})")
        return {"resuelto": True, "titulo": a.get("titulo") or a.get("tarea"), "tarea": a.get("tarea"),
                "cuando": a.get("cuando"), "que_paso": "Una IA externa hizo un encargo y el control de calidad lo frenó.",
                "por_que": fallos, "que_pasa": que_pasa, "motivo": rev.get("motivo") or "", "borrador": a.get("borrador")}
    if a.get("resultado") == "APROBADA":
        return {"resuelto": True, "titulo": a.get("titulo") or a.get("tarea"), "tarea": a.get("tarea"),
                "cuando": a.get("cuando"), "que_paso": "Una IA externa hizo un encargo y pasó el control de calidad.",
                "por_que": [], "que_pasa": "No hace falta nada", "motivo": "", "borrador": a.get("borrador")}
    espera = a.get("resultado") == "ESPERA_DECISION"
    return {"resuelto": False, "titulo": a.get("titulo") or a.get("tarea"), "tarea": a.get("tarea"),
            "cuando": a.get("cuando"),
            "que_paso": ("Una IA externa terminó un encargo, pero falta decidir qué hacer con él." if espera else
                         "Una IA externa terminó un encargo y el control de calidad NO lo da por bueno."),
            "por_que": fallos,
            "que_pasa": "No se usa hasta que Claude lo revise en su próxima sesión. Tú no tienes que hacer nada.",
            "motivo": "", "borrador": a.get("borrador")}
