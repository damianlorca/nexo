# -*- coding: utf-8 -*-
"""Oculta lo que PAREZCA un secreto antes de mandar una linea de log al navegador.

Dos capas: (1) en un dict, el valor de texto de una clave con nombre sensible (api_key, token,
password, clave...) se sustituye entero; (2) en cualquier texto, los patrones tipicos de claves
(sk-..., AIza..., gsk_..., ghp_..., token de bot de Telegram, JWT, "Bearer ...", "clave=valor",
el ?t= del token de esta web) y cualquier cadena larga que mezcle mayusculas, minusculas y
digitos. Prefiere pasarse de prudente: un hash o un id raro oculto es un mal menor.
Los numeros se respetan ("tokens": 1234 es un contador, no un secreto).
"""
from __future__ import annotations

import re

OCULTO = "«oculto»"

CLAVE_SENSIBLE = re.compile(
    r"api[_-]?key|apikey|token|secret|secreto|passw|pwd|contrase|clave|authorization|cookie|"
    r"bearer|credencial|private[_-]?key|session|(?:^|[_-])key$", re.I)

# Nombre sensible al principio de una palabra o tras _ / - (GEMINI_API_KEY, SECRET_TOKEN...), pero no
# en mitad de otra (monkey=..., keyboard=... no cuentan). "key" solo como sufijo (SECRET_KEY,
# AWS_SECRET_ACCESS_KEY): suelto es codigo corriente (sort(key=lambda ...)).
_NOMBRES = (r"(?:(?<=[_-])key|(?:(?<=[_-])|(?<![A-Za-z0-9]))"
            r"(?:api[_-]?key|apikey|access[_-]?token|token|secret|secreto|password|passwd|pwd|clave|"
            r"contrase(?:ñ|n)a))")
_ASIGNA = r"[\"']?\s*[:=]\s*"
PATRONES = [
    # nombre="valor con espacios" / nombre: 'valor'  -> el entrecomillado entero
    (re.compile(r"(?i)(" + _NOMBRES + _ASIGNA + r")([\"'])[^\"'\n]+\2"), r"\1\2" + OCULTO + r"\2"),
    # nombre=valor / nombre: valor (sin comillas)  -> se conserva el nombre
    (re.compile(r"(?i)(" + _NOMBRES + _ASIGNA + r")(?![\"'«])[^\s\"'&,;}]{4,}"), r"\1" + OCULTO),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1" + OCULTO),
    (re.compile(r"([?&]t=)[A-Za-z0-9_-]{16,}"), r"\1" + OCULTO),                 # token de esta web
    (re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{16,}"), OCULTO),             # OpenAI / Anthropic
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), OCULTO),                            # Google
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), OCULTO),                              # Groq
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), OCULTO),                        # GitHub
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), OCULTO),                      # Slack
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), OCULTO),                      # bot de Telegram
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), OCULTO),  # JWT
]


# Generico: 32+ caracteres seguidos del alfabeto base64 (tambien + / =) que mezclan minuscula,
# mayuscula y digito, con 2 separadores (_ -) como mucho: asi no caen nombres de fichero como
# NEXO_HANDOFF_2026-09-24_t12_.... Con + o / (base64 estandar, p. ej. claves de AWS) no puede llevar
# _ ni - (ese alfabeto no los tiene): asi no caen rutas como memoria/borradores/T153_20260924_0017.
LARGA = re.compile(r"(?<![A-Za-z0-9_+/=-])[A-Za-z0-9_+/=-]{32,}")


def _generica(m: re.Match) -> str:
    s = m.group(0)
    separadores = s.count("_") + s.count("-")
    base64_estandar = "/" in s or "+" in s
    parece = (any(c.islower() for c in s) and any(c.isupper() for c in s) and any(c.isdigit() for c in s)
              and separadores <= (0 if base64_estandar else 2))
    return OCULTO if parece else s


def texto(s: str) -> str:
    for patron, cambio in PATRONES:
        s = patron.sub(cambio, s)
    return LARGA.sub(_generica, s)


def valor(v, clave: str = ""):
    """Copia de v (dict/list/str/...) con lo que parezca secreto oculto."""
    if isinstance(v, dict):
        return {k: valor(x, str(k)) for k, x in v.items()}
    if isinstance(v, list):
        return [valor(x, clave) for x in v]
    if isinstance(v, str):
        if v and clave and CLAVE_SENSIBLE.search(clave):
            return OCULTO
        return texto(v)
    return v
