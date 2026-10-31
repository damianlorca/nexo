# -*- coding: utf-8 -*-
"""Datos de Tailscale para el acceso desde el movil (hito movil, interfaz/HITO_MOVIL.md).

La web sigue escuchando SOLO en 127.0.0.1; `tailscale serve` la publica por HTTPS dentro de la
tailnet (nunca `funnel`, que la abriria a internet). Aqui solo se LEE el estado de Tailscale:
- estado(): nombre del PC en la tailnet (DNSName) y login del dueno, sin escribirlos a mano.
- serve(): si el proxy https:443 -> 127.0.0.1:<puerto> esta puesto y si hay algun funnel.

Comprobado el 25/09 con un eco detras de Serve: Serve conserva el Host, conecta desde 127.0.0.1,
anade X-Forwarded-Proto: https y Tailscale-User-Login, y SUSTITUYE un Tailscale-User-Login
falsificado por el de verdad.

Sin Tailscale (apagado o no instalado) todo devuelve None: la web queda solo en local.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

RUTA_WINDOWS = Path(r"C:\Program Files\Tailscale\tailscale.exe")
TIMEOUT = 5


def ejecutable() -> str | None:
    encontrado = shutil.which("tailscale")
    if encontrado:
        return encontrado
    return str(RUTA_WINDOWS) if RUTA_WINDOWS.exists() else None


def _json(*args: str) -> dict | None:
    exe = ejecutable()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, *args, "--json"], capture_output=True, timeout=TIMEOUT,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            return None
        return json.loads(r.stdout.decode("utf-8") or "null")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def leer_estado(datos: dict | None) -> dict | None:
    """De `tailscale status --json` saca {"host", "dueno"}. None si no esta en marcha o sin HTTPS."""
    if not datos or datos.get("BackendState") != "Running":
        return None
    yo = datos.get("Self") or {}
    host = (yo.get("DNSName") or "").rstrip(".").lower()
    # Serve solo da HTTPS si el host tiene certificado (HTTPS activado en el panel de Tailscale).
    if not host or host not in [d.lower() for d in (datos.get("CertDomains") or [])]:
        return None
    usuario = (datos.get("User") or {}).get(str(yo.get("UserID"))) or {}
    return {"host": host, "dueno": usuario.get("LoginName") or None}


def estado() -> dict | None:
    return leer_estado(_json("status"))


def leer_serve(datos: dict | None, host: str, puerto: int) -> dict:
    """De `tailscale serve status --json`: {"activo": proxy 443 -> nuestra web, "funnel": algo publico}."""
    datos = datos or {}
    web = (datos.get("Web") or {}).get(f"{host}:443") or {}
    proxy = ((web.get("Handlers") or {}).get("/") or {}).get("Proxy", "")
    activo = proxy.rstrip("/") in (f"http://127.0.0.1:{puerto}", f"127.0.0.1:{puerto}")
    return {"activo": activo, "funnel": any((datos.get("AllowFunnel") or {}).values())}


def serve(host: str, puerto: int) -> dict | None:
    """None si no se pudo preguntar a Tailscale (distinto de 'no hay serve', que es {} -> inactivo)."""
    datos = _json("serve", "status")
    return None if datos is None else leer_serve(datos, host, puerto)
