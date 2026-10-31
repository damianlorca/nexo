# -*- coding: utf-8 -*-
"""Hook PreToolUse de Claude Code (regla de Damián 05/10, reforzada 12/10): los comandos largos van en segundo plano.

CLAUDE.md ya lo pide, pero Code a veces lanza en primer plano la suite, el banco o esperas largas y Damián tiene
que pasarlos a mano a segundo plano. Este hook lo hace obligatorio: si un comando largo llega SIN
run_in_background, lo bloquea (exit 2) y le dice a Code que lo relance en segundo plano.

Falla en abierto: cualquier error propio -> exit 0 (nunca deja a Code sin poder ejecutar nada).
Solo stdlib. Pruebas: tests/test_hook_segundo_plano.py.
"""
import json
import re
import sys

LARGOS = [
    # 13/10: solo pytest como ORDEN (-m pytest o al empezar un comando), no un "import pytest" dentro de un heredoc
    (re.compile(r"(?m)(?:^|[;&|(]\s*|-m\s+)pytest\b(?![^\n;&|]*\.py\b)"), "la suite de tests completa"),
    (re.compile(r"\b(?:sleep|Start-Sleep)\s+(?:-s(?:econds)?\s+)?(\d+)", re.I), "una espera"),
    (re.compile(r"nucleo\.banco_modelos\s+correr"), "el banco de modelos"),
    (re.compile(r"\bturno_nexo(?:\.py)?\b"), "un turno de NEXO"),
    (re.compile(r"nucleo\.(?:piloto_serie|implementador)\s+(?:puerta|correr|serie)\b"), "el implementador"),
    (re.compile(r"\bollama\s+pull\b"), "una descarga de modelo"),
    (re.compile(r"\bpip\s+install\b"), "una instalación"),
]
UMBRAL_ESPERA = 30


def motivo(entrada: dict) -> str:
    """'' si se deja pasar; si no, qué comando largo es."""
    if entrada.get("tool_name") not in ("Bash", "PowerShell"):
        return ""
    ti = entrada.get("tool_input") or {}
    if ti.get("run_in_background"):
        return ""
    cmd = str(ti.get("command") or "")
    for rx, que in LARGOS:
        m = rx.search(cmd)
        if not m:
            continue
        if que == "una espera":
            try:
                if int(m.group(1)) <= UMBRAL_ESPERA:
                    continue
            except (IndexError, ValueError):
                continue
        return que
    return ""


def main() -> int:
    try:
        entrada = json.loads(sys.stdin.read() or "{}")
        que = motivo(entrada)
    except Exception:
        return 0
    if not que:
        return 0
    texto = (f"NEXO (regla de Damián, CLAUDE.md): esto es {que} y tarda. Relánzalo con run_in_background: true y "
             "sigue con lo siguiente que no dependa de ello; mira el resultado cuando te avise. Nada de esperar en "
             "primer plano.\n")
    sys.stderr.buffer.write(texto.encode("utf-8"))   # siempre UTF-8: en Windows stderr sale en cp1252
    sys.stderr.flush()
    return 2


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):   # solo stdlib: no importa nucleo.ayuda
        print(__doc__)
        raise SystemExit(0)
    raise SystemExit(main())
