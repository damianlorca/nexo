"""Prueba de canal/buzon.py despues del parche atomico.

IMPORTANTE: desvia SALIDA y ENTRADA a una carpeta de pruebas ANTES
de escribir nada. Si escribiera en canal/salida/ de verdad, el bot
que esta vivo se lo mandaria a Damian al movil a las cuatro de la
manana. No es una prueba: seria un despertador.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import canal.buzon as buzon  # noqa: E402


fallos = 0


def comprobar(titulo: str, condicion: bool, detalle: str = "") -> None:
    global fallos

    if condicion:
        print(f"  VALE  {titulo}")
    else:
        fallos += 1
        print(f"  FALLA {titulo} {detalle}")


BANCO = RAIZ / "_pruebas_tmp_buzon"

if BANCO.exists():
    shutil.rmtree(BANCO)

# Desvio ANTES de nada.
buzon.SALIDA = BANCO / "salida"
buzon.ENTRADA = BANCO / "entrada"

buzon.SALIDA.mkdir(parents=True)
buzon.ENTRADA.mkdir(parents=True)

comprobar(
    "el desvio esta hecho (no escribe en el canal real)",
    "_pruebas_tmp_buzon" in str(buzon.SALIDA),
)


print("\n1. avisar() deja un mensaje bien formado")

ident = buzon.avisar("mensaje de prueba, no sale de aqui")

archivo = buzon.SALIDA / f"{ident}.json"

comprobar("crea el archivo", archivo.is_file())

datos = json.loads(archivo.read_text(encoding="utf-8"))

comprobar("tipo aviso", datos["tipo"] == "aviso")
comprobar("texto correcto", datos["texto"] == "mensaje de prueba, no sale de aqui")
comprobar("lleva id", datos["id"] == ident)
comprobar("lleva fecha", bool(datos.get("creado")))


print("\n2. No quedan temporales que el bot pueda confundir")

sobrantes = list(buzon.SALIDA.glob("*"))

comprobar(
    "solo esta el .json, nada mas",
    len(sobrantes) == 1 and sobrantes[0].suffix == ".json",
    str([s.name for s in sobrantes]),
)

# El bot busca con glob("*.json"). Un temporal .tmp no debe colarse.
comprobar(
    "el glob del bot solo ve el mensaje bueno",
    len(list(buzon.SALIDA.glob("*.json"))) == 1,
)


print("\n3. preguntar() con botones")

idp = buzon.preguntar("Prueba con botones", ["Uno", "Dos", "Tres"])

dp = json.loads((buzon.SALIDA / f"{idp}.json").read_text(encoding="utf-8"))

comprobar("tipo pregunta", dp["tipo"] == "pregunta")
comprobar("conserva las opciones", dp["opciones"] == ["Uno", "Dos", "Tres"])

idp2 = buzon.preguntar("Sin opciones")

dp2 = json.loads((buzon.SALIDA / f"{idp2}.json").read_text(encoding="utf-8"))

comprobar("por defecto Si/No", dp2["opciones"] == ["Si", "No"])


print("\n4. Acentos y caracteres raros sobreviven")

ida = buzon.avisar("Mañana hay que revisar la señal — ¿vale? 100 €")

da = json.loads((buzon.SALIDA / f"{ida}.json").read_text(encoding="utf-8"))

comprobar("texto intacto", da["texto"] == "Mañana hay que revisar la señal — ¿vale? 100 €")


print("\n5. Muchos mensajes seguidos: ids distintos, ninguno perdido")

ids = [buzon.avisar(f"mensaje numero {i}") for i in range(30)]

comprobar("30 ids distintos", len(set(ids)) == 30)

archivos_json = list(buzon.SALIDA.glob("*.json"))

# 4 mensajes anteriores (1 aviso + 2 preguntas + 1 aviso) + estos 30.
comprobar("estan los 34 archivos", len(archivos_json) == 34, str(len(archivos_json)))

textos = set()

for a in archivos_json:
    textos.add(json.loads(a.read_text(encoding="utf-8"))["texto"])

comprobar(
    "todos parsean y todos los textos estan",
    all(f"mensaje numero {i}" in textos for i in range(30)),
)

comprobar("sigue sin temporales", not list(buzon.SALIDA.glob(".*.tmp")))


print("\n6. respuesta() y mensajes_nuevos() siguen funcionando")

(buzon.ENTRADA / f"{idp}.json").write_text(
    json.dumps({"id": idp, "respuesta": "Dos"}), encoding="utf-8"
)

comprobar("respuesta() la encuentra", buzon.respuesta(idp) == "Dos")
comprobar("respuesta() de algo sin contestar da None", buzon.respuesta("no_existe") is None)

(buzon.ENTRADA / "libre_010203.json").write_text(
    json.dumps({"id": "libre_010203", "texto": "algo que dijo el"}), encoding="utf-8"
)

nuevos = buzon.mensajes_nuevos()

comprobar("recoge el mensaje libre", len(nuevos) == 1 and nuevos[0]["texto"] == "algo que dijo el")
comprobar(
    "y lo marca como leido",
    (buzon.ENTRADA / "libre_010203.json.leido").is_file(),
)
comprobar("no lo devuelve dos veces", buzon.mensajes_nuevos() == [])


print("\n7. Una entrada corrupta no tumba la lectura")

(buzon.ENTRADA / "libre_999999.json").write_text("{esto no es json", encoding="utf-8")

try:
    n = buzon.mensajes_nuevos()
    comprobar("no revienta con basura", n == [])
except Exception as e:
    fallos += 1
    print(f"  FALLA revento: {type(e).__name__}: {e}")


shutil.rmtree(BANCO)


print("\n8. El canal REAL sigue sin tocar")

real = RAIZ / "canal" / "salida"

pendientes = list(real.glob("*.json"))

comprobar(
    "no he dejado ningun mensaje sin enviar en el canal de verdad",
    not pendientes,
    str([p.name for p in pendientes]),
)

comprobar("ni temporales", not list(real.glob(".*.tmp")))


print("\n" + ("TODO VALE" if fallos == 0 else f"{fallos} FALLOS"))

sys.exit(1 if fallos else 0)
