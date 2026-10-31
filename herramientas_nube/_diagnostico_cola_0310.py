"""03/10/2026: foto del estado de la cola para planificar revision -> aprobacion -> implementacion. Solo lectura."""
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from nucleo import tareas as T  # noqa: E402

ts = T.cargar()["tareas"]
print("total tareas:", len(ts))
print("por estado:", dict(Counter(t.get("estado") for t in ts)))
hace7 = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
nuevas = [t for t in ts if str(t.get("creada", "")) >= hace7]
print("creadas ultimos 7 dias:", len(nuevas), "por estado:", dict(Counter(t.get("estado") for t in nuevas)))


def et(t):
    return " ".join(t.get("etiquetas") or [])


rev = [t for t in ts if "revision" in et(t).lower() or str(t.get("titulo", "")).lower().startswith("revis")]
prop = [t for t in ts if t.get("estado") == "propuesta"]
print("propuestas (estado propuesta):", len(prop))
abiertas_rev = [t for t in ts if t.get("estado") not in ("hecha", "descartada", "superada")
                and ("revision_claude" in et(t) or "circuito:revision" in et(t) or "tipo:revision" in et(t))]
print("revisiones de Claude abiertas (por etiqueta):", len(abiertas_rev))
cats = Counter()
for t in nuevas:
    c = [e for e in (t.get("etiquetas") or []) if e.startswith("cat:")]
    cats[c[0] if c else "sin_cat"] += 1
print("nuevas por categoria:", dict(cats))
orig = Counter()
for t in nuevas:
    o = [e for e in (t.get("etiquetas") or []) if e.startswith(("origen:", "turno:", "plantilla:"))]
    orig[o[0] if o else "sin_origen"] += 1
print("nuevas por origen:", dict(orig.most_common(8)))

try:
    from nucleo import revision as R
    c = R.cola() if hasattr(R, "cola") else None
    print("cola de revision (nucleo.revision.cola):", len(c) if c is not None else "n/d")
except Exception as e:  # noqa: BLE001
    print("cola revision error:", e)

aud = RAIZ / "memoria" / "auditoria"
if aud.exists():
    res = Counter()
    pend = 0
    for f in aud.glob("*.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if str(j.get("cuando", ""))[:10] >= hace7:
            res[j.get("resultado")] += 1
            if not j.get("revisado"):
                pend += 1
    print("auditorias ultimos 7 dias:", dict(res), "sin revisar:", pend)

t251 = T.buscar("T251")
print("T251:", t251.get("estado"), "| notas:", len(t251.get("notas") or []))
for n in (t251.get("notas") or [])[-3:]:
    print("   -", (n.get("texto") if isinstance(n, dict) else str(n))[:220])

turnos = sorted((RAIZ / "registros").glob("turno_nexo_202610*.json")) + sorted((RAIZ / "registros").glob("turno_nexo_2026093*.json"))
print("turnos registrados (29/09-03/10):", len(turnos))
uso = RAIZ / "registros" / "uso_claude.jsonl"
if uso.exists():
    print("lineas uso_claude:", sum(1 for _ in uso.open(encoding="utf-8")))
r = subprocess.run(["git", "log", "--since=7 days ago", "--oneline"], cwd=RAIZ, capture_output=True, text=True)
print("commits ultimos 7 dias:", len(r.stdout.splitlines()))
r = subprocess.run(["git", "status", "--short"], cwd=RAIZ, capture_output=True, text=True)
print("git status lineas:", len(r.stdout.splitlines()))
