"""Prueba de manos/archivos.py: escritura atomica, respaldos que no se
pisan, y los frenos nuevos de archivar().

Monta un proyecto de mentira dentro de la raiz de verdad (para que
los permisos lo vean verde) y desvia el modulo hacia el. No toca
ningun archivo real.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

RAIZ_REAL = Path(__file__).resolve().parent

if str(RAIZ_REAL) not in sys.path:
    sys.path.insert(0, str(RAIZ_REAL))

import manos.archivos as arch  # noqa: E402
from nucleo.permisos import Bloqueado  # noqa: E402


fallos = 0


def comprobar(titulo: str, condicion: bool, detalle: str = "") -> None:
    global fallos

    if condicion:
        print(f"  VALE  {titulo}")
    else:
        fallos += 1
        print(f"  FALLA {titulo} {detalle}")


def bloquea(titulo: str, fn) -> None:
    """Comprueba que algo esta prohibido de verdad."""

    global fallos

    try:
        fn()
    except Bloqueado as e:
        print(f"  VALE  {titulo} -> {str(e)[:60]}...")
        return
    except Exception as e:
        fallos += 1
        print(f"  FALLA {titulo}: esperaba Bloqueado, salio {type(e).__name__}: {e}")
        return

    fallos += 1
    print(f"  FALLA {titulo}: NO lo ha frenado, lo ha hecho")


BANCO = RAIZ_REAL / "_pruebas_tmp_arch"

if BANCO.exists():
    shutil.rmtree(BANCO)

BANCO.mkdir(parents=True)

arch.RAIZ = BANCO


print("\n1. escribir() basico y atomico")

arch.escribir("notas/uno.txt", "primer contenido")

f = BANCO / "notas" / "uno.txt"

comprobar("crea el archivo", f.is_file())
comprobar("contenido correcto", f.read_text(encoding="utf-8") == "primer contenido")
comprobar("sin temporales", not list((BANCO / "notas").glob(".*.tmp")))


print("\n2. Al sobrescribir deja respaldo")

arch.escribir("notas/uno.txt", "segundo contenido")

comprobar("contenido nuevo", f.read_text(encoding="utf-8") == "segundo contenido")

respaldos = list((BANCO / "_respaldos").rglob("*.txt"))

comprobar("hay un respaldo", len(respaldos) == 1, str(respaldos))

if respaldos:
    comprobar(
        "el respaldo tiene el contenido VIEJO",
        respaldos[0].read_text(encoding="utf-8") == "primer contenido",
    )
    comprobar(
        "el nombre del respaldo lleva la carpeta",
        respaldos[0].name.startswith("notas__uno_"),
        respaldos[0].name,
    )


print("\n3. Dos archivos que se llaman igual ya no se pisan el respaldo (C3)")

arch.escribir("entrada/mismo.json", "soy el de entrada")
arch.escribir("salida/mismo.json", "soy el de salida")

# Y ahora los sobrescribimos los dos, uno detras de otro, en el
# mismo segundo: es justo el caso que antes perdia datos.
arch.escribir("entrada/mismo.json", "entrada v2")
arch.escribir("salida/mismo.json", "salida v2")

resp_json = sorted((BANCO / "_respaldos").rglob("*.json"))

comprobar("hay DOS respaldos, no uno", len(resp_json) == 2, str([r.name for r in resp_json]))

contenidos = {r.read_text(encoding="utf-8") for r in resp_json}

comprobar(
    "se conservan los dos originales distintos",
    contenidos == {"soy el de entrada", "soy el de salida"},
    str(contenidos),
)


print("\n4. Dos escrituras del MISMO archivo en el mismo segundo")

arch.escribir("notas/rapido.txt", "a")
arch.escribir("notas/rapido.txt", "b")
arch.escribir("notas/rapido.txt", "c")

rapidos = sorted((BANCO / "_respaldos").rglob("notas__rapido*"))

comprobar("guarda los dos estados previos", len(rapidos) == 2, str([r.name for r in rapidos]))

comprobar(
    "y son 'a' y 'b'",
    {r.read_text(encoding="utf-8") for r in rapidos} == {"a", "b"},
)


print("\n5. archivar() normal sigue funcionando")

destino = arch.archivar("notas/uno.txt", motivo="prueba")

comprobar("ya no esta donde estaba", not f.exists())
comprobar("esta en _archivo", "_archivo" in destino and Path(destino).is_file())
comprobar(
    "conserva el contenido",
    Path(destino).read_text(encoding="utf-8") == "segundo contenido",
)


print("\n6. archivar() dos veces algo con el mismo nombre no se pisa")

arch.escribir("notas/uno.txt", "otro uno distinto")

destino2 = arch.archivar("notas/uno.txt")

comprobar("el segundo va a otro nombre", destino2 != destino)
comprobar("los dos existen", Path(destino).is_file() and Path(destino2).is_file())
comprobar(
    "el primero no se ha alterado",
    Path(destino).read_text(encoding="utf-8") == "segundo contenido",
)


print("\n7. LOS FRENOS NUEVOS (hallazgo C4)")

bloquea("no archiva la raiz del proyecto", lambda: arch.archivar(BANCO))

bloquea("no archiva una carpeta que contiene la raiz", lambda: arch.archivar(BANCO.parent))

bloquea("no archiva _archivo entero", lambda: arch.archivar(BANCO / "_archivo"))

bloquea("no archiva _respaldos entero", lambda: arch.archivar(BANCO / "_respaldos"))

(BANCO / "memoria").mkdir(exist_ok=True)
(BANCO / "memoria" / "estado.json").write_text("{}", encoding="utf-8")

bloquea("no archiva memoria/ entera", lambda: arch.archivar(BANCO / "memoria"))

comprobar(
    "pero un archivo suelto de memoria/ SI se puede archivar",
    "_archivo" in arch.archivar("memoria/estado.json", motivo="suelto"),
)


print("\n8. La carpeta del dia dentro de _archivo tampoco se archiva a si misma")

import time as _t  # noqa: E402

hoy = BANCO / "_archivo" / _t.strftime("%Y%m%d")

bloquea("no archiva la carpeta destino de hoy", lambda: arch.archivar(hoy))


print("\n9. Lo que no existe da un error claro, no un desastre")

try:
    arch.archivar("no/existe/nada.txt")
    fallos += 1
    print("  FALLA deberia dar FileNotFoundError")
except FileNotFoundError:
    print("  VALE  FileNotFoundError para lo inexistente")
except Exception as e:
    fallos += 1
    print(f"  FALLA esperaba FileNotFoundError, salio {type(e).__name__}")


print("\n10. leer() y listar() siguen igual")

arch.escribir("notas/dos.txt", "contenido dos")

comprobar("leer devuelve lo escrito", arch.leer("notas/dos.txt") == "contenido dos")

lista = arch.listar("notas")

comprobar("listar encuentra el archivo", "dos.txt" in lista, str(lista))


shutil.rmtree(BANCO)

print("\n" + ("TODO VALE" if fallos == 0 else f"{fallos} FALLOS"))

sys.exit(1 if fallos else 0)
