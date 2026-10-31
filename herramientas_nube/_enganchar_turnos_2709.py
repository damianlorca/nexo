"""Engancha nucleo.turnos en turno_nexo.py respetando sus finales de linea (27/09/2026)."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
f = RAIZ / "turno_nexo.py"
b = f.read_bytes()
nl = b"\r\n" if b"\r\n" in b else b"\n"
t = b.decode("utf-8")
n = nl.decode()

imp_viejo = "from nucleo import parada  # noqa: E402"
imp_nuevo = imp_viejo + n + "from nucleo import turnos  # noqa: E402"
cond_vieja = ("        reg[\"abortado\"] = f\"PARADA DE EMERGENCIA activa: {parada.activa()}\"" + n +
              "    elif not _tomar_candado():")
cond_nueva = ("        reg[\"abortado\"] = f\"PARADA DE EMERGENCIA activa: {parada.activa()}\"" + n +
              "    elif turnos.desactivados():" + n +
              "        reg[\"abortado\"] = f\"TURNOS DESACTIVADOS: {turnos.desactivados()}\"" + n +
              "    elif not _tomar_candado():")
if "from nucleo import turnos" in t:
    print("ya enganchado")
else:
    assert t.count(imp_viejo) == 1 and t.count(cond_vieja) == 1, "no encuentro los puntos de enganche"
    t = t.replace(imp_viejo, imp_nuevo).replace(cond_vieja, cond_nueva)
    f.write_bytes(t.encode("utf-8"))
    print("enganchado; fin de linea", repr(nl))

gi = RAIZ / ".gitignore"
g = gi.read_bytes()
gnl = b"\r\n" if b"\r\n" in g else b"\n"
if b"/memoria/TURNOS_DESACTIVADOS" not in g:
    if not g.endswith(gnl):
        g += gnl
    g += b"/memoria/TURNOS_DESACTIVADOS" + gnl
    gi.write_bytes(g)
    print(".gitignore actualizado")
