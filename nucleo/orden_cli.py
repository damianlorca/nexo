# -*- coding: utf-8 -*-
"""Lanzado por /orden del bot o por la web local: procesa la orden y avisa por Telegram (silencioso)."""
import sys

from canal import buzon
from nucleo import ordenes

args = sys.argv[1:]
canal = "telegram"
if args and args[0].startswith("--canal="):
    canal = args.pop(0).split("=", 1)[1]
r = ordenes.procesar(" ".join(args), canal=canal)
buzon.avisar(f"[{canal}] " + r.get("respuesta", str(r)), silencioso=True)
print(r)
