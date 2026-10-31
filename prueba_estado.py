"""Prueba de nucleo/estado.py: guardado atomico y carga a prueba de rotos.

Trabaja sobre una carpeta temporal. Lo unico que toca del estado de
verdad es LEERLO, al final, para confirmar que sigue cargando bien.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import nucleo.estado as est  # noqa: E402


fallos = 0


def comprobar(titulo: str, condicion: bool, detalle: str = "") -> None:
    global fallos

    if condicion:
        print(f"  VALE  {titulo}")
    else:
        fallos += 1
        print(f"  FALLA {titulo} {detalle}")


BANCO = RAIZ / "_pruebas_tmp_estado"

if BANCO.exists():
    shutil.rmtree(BANCO)

BANCO.mkdir(parents=True)

# Desviamos el modulo entero al banco de pruebas.
est.RAIZ = BANCO
est.ARCHIVO = BANCO / "memoria" / "estado.json"


def limpiar():
    for sub in ("memoria", "_archivo", "_respaldos"):
        d = BANCO / sub
        if d.exists():
            shutil.rmtree(d)


print("\n1. Guardar y volver a cargar")

limpiar()

e = est.Estado(mision="probar", paso=7)
e.hechos = ["un hecho"]
e.siguiente_turno = ["seguir por aqui"]
e.guardar()

comprobar("crea el archivo", est.ARCHIVO.is_file())

v = est.cargar()

comprobar("mision vuelve", v.mision == "probar")
comprobar("paso vuelve", v.paso == 7)
comprobar("hechos vuelven", v.hechos == ["un hecho"])
comprobar("siguiente_turno SOBREVIVE", v.siguiente_turno == ["seguir por aqui"])


print("\n2. siguiente_turno ya no se pierde al guardar (era el fallo D3)")

v.anotar("hice algo", "salio bien")

w = est.cargar()

comprobar("sigue ahi tras anotar()", w.siguiente_turno == ["seguir por aqui"])
comprobar("paso incrementado", w.paso == 8)


print("\n3. Guardado atomico: no deja temporales")

comprobar(
    "sin .tmp en memoria/",
    not list((BANCO / "memoria").glob(".*.tmp")),
)


print("\n4. Estado ROTO sin respaldo: aparta el roto y avisa, no finge")

limpiar()

est.ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
est.ARCHIVO.write_text('{"mision": "algo", "hech', encoding="utf-8")

r = est.cargar()

comprobar("no revienta", isinstance(r, est.Estado))
comprobar("marca fallo", r.estado == "fallo", r.estado)
comprobar("cuenta el error", r.errores >= 1)
comprobar("explica que paso", "ESTADO PERDIDO" in r.ultimo_resultado, r.ultimo_resultado[:80])

apartados = list((BANCO / "_archivo").glob("*/estado_roto_*.json"))

comprobar("el roto esta guardado, no borrado", len(apartados) == 1, str(apartados))

if apartados:
    comprobar(
        "el roto conserva su contenido",
        apartados[0].read_text(encoding="utf-8") == '{"mision": "algo", "hech',
    )

comprobar("y el estado.json roto ya no esta en medio", not est.ARCHIVO.exists())


print("\n5. Estado ROTO CON respaldo: recupera y lo dice")

limpiar()

resp = BANCO / "_respaldos" / "20260910"
resp.mkdir(parents=True)

(resp / "estado_235959.json").write_text(
    json.dumps({"mision": "la buena", "paso": 42, "hechos": ["hecho salvado"]}),
    encoding="utf-8",
)

est.ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
est.ARCHIVO.write_text("esto no es json ni de lejos", encoding="utf-8")

r = est.cargar()

comprobar("recupera la mision del respaldo", r.mision == "la buena", r.mision)
comprobar("recupera el paso", r.paso == 42)
comprobar("recupera los hechos", r.hechos == ["hecho salvado"])
comprobar("avisa de que viene de respaldo", "RECUPERADO DE RESPALDO" in r.ultimo_resultado)
comprobar("marca fallo igualmente", r.estado == "fallo")


print("\n6. Coge el respaldo MAS NUEVO, no uno cualquiera")

limpiar()

import time as _t  # noqa: E402

r1 = BANCO / "_respaldos" / "20260909"
r1.mkdir(parents=True)
(r1 / "estado_120000.json").write_text(json.dumps({"mision": "viejo"}), encoding="utf-8")

_t.sleep(1.1)

r2 = BANCO / "_respaldos" / "20260910"
r2.mkdir(parents=True)
(r2 / "estado_120000.json").write_text(json.dumps({"mision": "nuevo"}), encoding="utf-8")

est.ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
est.ARCHIVO.write_text("{roto", encoding="utf-8")

r = est.cargar()

comprobar("elige el respaldo mas reciente", r.mision == "nuevo", r.mision)


print("\n7. Campos desconocidos: se avisa en vez de perderlos en silencio")

limpiar()

est.ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
est.ARCHIVO.write_text(
    json.dumps({"mision": "ok", "campo_inventado": "valor", "otro_mas": 1}),
    encoding="utf-8",
)

r = est.cargar()

comprobar("carga lo que entiende", r.mision == "ok")

avisos = [h for h in r.hechos if "[aviso]" in h]

comprobar("deja aviso de lo descartado", len(avisos) == 1, str(r.hechos))

if avisos:
    comprobar("nombra los campos perdidos", "campo_inventado" in avisos[0] and "otro_mas" in avisos[0])


print("\n8. Archivo inexistente: estado limpio, sin dramas")

limpiar()

r = est.cargar()

comprobar("estado inicial", r.estado == "inactivo" and r.paso == 0)


print("\n9. JSON valido pero que no es un objeto")

limpiar()

est.ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
est.ARCHIVO.write_text("[1, 2, 3]", encoding="utf-8")

r = est.cargar()

comprobar("no revienta con una lista", isinstance(r, est.Estado))
comprobar("lo marca como fallo", r.estado == "fallo")


shutil.rmtree(BANCO)


print("\n10. El estado.json DE VERDAD sigue cargando bien")

import importlib  # noqa: E402

importlib.reload(est)

real = est.cargar()

comprobar("carga sin fallo", real.estado != "fallo", real.estado)
comprobar("tiene mision", bool(real.mision), repr(real.mision))
comprobar("conserva hechos", len(real.hechos) > 5, str(len(real.hechos)))
comprobar("lee siguiente_turno del disco", len(real.siguiente_turno) > 0, str(real.siguiente_turno))

sin_avisos = [h for h in real.hechos if "[aviso]" in h]

comprobar("no descarta ningun campo del archivo real", not sin_avisos, str(sin_avisos))


print("\n" + ("TODO VALE" if fallos == 0 else f"{fallos} FALLOS"))

sys.exit(1 if fallos else 0)
