# -*- coding: utf-8 -*-
"""Fecha y hora de Madrid para los prompts de delegacion (T427).

Una IA externa no sabe en que dia esta: cada prompt que sale de NEXO (trabajo, tribunal, chat de tarea) lleva una
linea `Fecha y hora actuales (Madrid): ...`. Sin dependencias nuevas: este Python de Windows no trae tzdata, asi que
si `zoneinfo` no encuentra Europe/Madrid se aplica la regla europea (CEST de la ultima semana de marzo a la de
octubre, cambio a la 01:00 UTC).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
MARCA = "Fecha y hora actuales (Madrid):"


def _ultimo_domingo(anio: int, mes: int) -> date:
    d = date(anio, mes + 1, 1) - timedelta(days=1) if mes < 12 else date(anio, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def madrid(ahora_utc: datetime | None = None) -> datetime:
    """La hora de Madrid ahora (o la de `ahora_utc`, para tests) como datetime con zona."""
    utc = (ahora_utc or datetime.now(timezone.utc))
    utc = utc.replace(tzinfo=timezone.utc) if utc.tzinfo is None else utc.astimezone(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return utc.astimezone(ZoneInfo("Europe/Madrid"))
    except Exception:  # noqa: BLE001 - sin tzdata
        pass
    ini = datetime.combine(_ultimo_domingo(utc.year, 3), datetime.min.time(), timezone.utc) + timedelta(hours=1)
    fin = datetime.combine(_ultimo_domingo(utc.year, 10), datetime.min.time(), timezone.utc) + timedelta(hours=1)
    horas = 2 if ini <= utc < fin else 1
    return utc.astimezone(timezone(timedelta(hours=horas), "CEST" if horas == 2 else "CET"))


def linea(ahora_utc: datetime | None = None) -> str:
    m = madrid(ahora_utc)
    return f"{MARCA} {DIAS[m.weekday()]} {m:%d/%m/%Y %H:%M}."


def con_fecha(prompt: str, ahora_utc: datetime | None = None) -> str:
    """`prompt` precedido de la linea de fecha y hora (una sola vez: si ya la lleva, no se repite)."""
    if prompt.lstrip().startswith(MARCA):
        return prompt
    return f"{linea(ahora_utc)}\n{prompt}"
