"""Pruebas de nucleo/tareas.py.

Trabajan sobre una carpeta temporal: NO tocan memoria/tareas.json.
Si alguna vez esta prueba escribe en memoria/ es que algo se ha roto
en el desvio de rutas y hay que pararlo antes de seguir.
"""

from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

from nucleo import tareas as T


FALLOS: list[str] = []
PASADAS = 0


def comprobar(condicion: bool, que: str) -> None:
    global PASADAS

    if condicion:
        PASADAS += 1
    else:
        FALLOS.append(que)
        print(f"  FALLO: {que}")


def desviar(carpeta: Path) -> None:
    """Manda el almacen y la vista a una carpeta de usar y tirar."""

    T.ALMACEN = carpeta / "tareas.json"
    T.VISTA = carpeta / "tareas.md"


# ------------------------------------------------------- 1. lo basico

def prueba_alta_y_lectura() -> None:
    print("\n1. Alta, lectura y numeracion")

    t = T.anadir("Primera", importancia=5, urgencia=1, dificultad=1, coste=1)

    comprobar(t["id"] == "T001", "la primera tarea es T001")
    comprobar(t["estado"] == "pendiente", "nace pendiente")
    comprobar(t["depende"] == "ia", "por defecto la llevo yo")

    t2 = T.anadir("Segunda")

    comprobar(t2["id"] == "T002", "la segunda es T002")

    datos = T.cargar()

    comprobar(len(datos["tareas"]) == 2, "hay dos tareas en el almacen")
    comprobar(datos["siguiente_id"] == 3, "el contador va por 3")

    comprobar(T.ALMACEN.is_file(), "el json existe en disco")
    comprobar(T.VISTA.is_file(), "la vista .md se genero sola")

    crudo = json.loads(T.ALMACEN.read_text(encoding="utf-8"))

    comprobar(crudo["tareas"][0]["titulo"] == "Primera", "el json es legible")


def prueba_recorte_de_valores() -> None:
    print("\n2. Valores fuera de rango")

    t = T.anadir("Extrema", importancia=99, dificultad=-4, coste="tres")

    comprobar(t["importancia"] == 5, "importancia 99 se recorta a 5")
    comprobar(t["dificultad"] == 1, "dificultad -4 se recorta a 1")
    comprobar(t["coste"] == 2, "coste no numerico cae al valor por defecto")

    t2 = T.anadir("Rara", depende="el vecino", estado="inventado")

    comprobar(t2["depende"] == "ia", "una dependencia invalida cae en ia")
    comprobar(t2["estado"] == "pendiente", "un estado invalido cae en pendiente")


# ------------------------------------------------- 3. la puntuacion

def prueba_puntuacion() -> None:
    print("\n3. La puntuacion ordena como dice el docstring")

    facil = T.plantilla("f", importancia=3, urgencia=3, dificultad=1, coste=1)
    dificil = T.plantilla("d", importancia=3, urgencia=3, dificultad=5, coste=5)

    comprobar(
        T.puntuacion(facil) > T.puntuacion(dificil),
        "a igual valor, la facil y barata puntua mas",
    )

    comprobar(T.puntuacion(facil) == 15.0, "sin freno, 3*3+2*3 = 15")

    urgente = T.plantilla("u", importancia=1, urgencia=5, dificultad=1, coste=1)
    importante = T.plantilla(
        "i", importancia=5, urgencia=1, dificultad=1, coste=1
    )

    comprobar(
        T.puntuacion(urgente) > T.puntuacion(importante),
        "la urgencia pesa mas que la importancia",
    )

    caro = T.plantilla("c", importancia=3, urgencia=3, dificultad=1, coste=5)
    duro = T.plantilla("h", importancia=3, urgencia=3, dificultad=5, coste=1)

    comprobar(
        T.puntuacion(duro) < T.puntuacion(caro),
        "la dificultad frena mas que el coste",
    )


def prueba_urgencia_por_fecha() -> None:
    print("\n4. La fecha manda sobre la urgencia escrita a mano")

    hoy = date(2026, 9, 11)

    def con_limite(dias: int) -> dict:
        limite = (hoy + timedelta(days=dias)).isoformat()

        return T.plantilla("x", urgencia=1, limite=limite)

    comprobar(
        T.urgencia_efectiva(con_limite(2), hoy) == 5,
        "a 2 dias del limite la urgencia es 5 aunque este escrito 1",
    )
    comprobar(T.urgencia_efectiva(con_limite(5), hoy) == 4, "a 5 dias, 4")
    comprobar(T.urgencia_efectiva(con_limite(15), hoy) == 3, "a 15 dias, 3")
    comprobar(T.urgencia_efectiva(con_limite(40), hoy) == 2, "a 40 dias, 2")
    comprobar(T.urgencia_efectiva(con_limite(400), hoy) == 1, "a 400 dias, 1")
    comprobar(
        T.urgencia_efectiva(con_limite(-3), hoy) == 5,
        "vencida hace 3 dias sigue siendo 5",
    )

    sin_fecha = T.plantilla("y", urgencia=4)

    comprobar(
        T.urgencia_efectiva(sin_fecha, hoy) == 4,
        "sin fecha se respeta el numero a mano",
    )

    mala = T.plantilla("z", urgencia=2, limite="el martes que viene")

    comprobar(
        T.urgencia_efectiva(mala, hoy) == 2,
        "una fecha ilegible no rompe: se cae al valor a mano",
    )
    comprobar(T.dias_restantes(mala, hoy) is None, "fecha ilegible = sin dias")


# --------------------------------------------------- 5. el reparto

def prueba_reparto_y_siguiente() -> None:
    print("\n5. Reparto por dependencia y que toca ahora")

    suya = T.anadir("Decidir una cosa", depende="damian", importancia=5,
                    urgencia=5, dificultad=1, coste=1)
    mia = T.anadir("Currar una cosa", depende="ia", importancia=2,
                   urgencia=2, dificultad=1, coste=1)

    mias = T.listar(depende="ia")
    tuyas = T.listar(depende="damian")

    comprobar(all(t["depende"] == "ia" for t in mias), "mias son solo mias")
    comprobar(suya["id"] in [t["id"] for t in tuyas], "la suya esta en su lista")
    comprobar(
        suya["id"] not in [t["id"] for t in mias],
        "lo que depende de el NO aparece en mi cola aunque puntue mas",
    )

    sig = T.siguiente()

    comprobar(sig is not None, "hay algo que puedo hacer yo")
    comprobar(sig["depende"] == "ia", "lo siguiente es mio, no suyo")

    T.actualizar(mia["id"], estado="bloqueada")

    sig2 = T.siguiente()

    comprobar(
        sig2 is None or sig2["id"] != mia["id"],
        "una bloqueada ya no sale como siguiente",
    )


def prueba_ciclo_de_vida() -> None:
    print("\n6. Estados, notas y cierre")

    t = T.anadir("Ciclo completo")

    T.anotar(t["id"], "primera nota")
    T.anotar(t["id"], "segunda nota")

    leida = T.buscar(t["id"])

    comprobar(len(leida["notas"]) == 2, "las dos notas se guardaron")
    comprobar(
        leida["notas"][0]["texto"] == "primera nota", "en orden de llegada"
    )

    cerrada = T.completar(t["id"], "terminada y probada")

    comprobar(cerrada["estado"] == "hecha", "queda en hecha")
    comprobar(cerrada["cerrada"] is not None, "se sella la fecha de cierre")
    comprobar(len(cerrada["notas"]) == 3, "la nota de cierre tambien entra")

    comprobar(
        t["id"] not in [x["id"] for x in T.listar()],
        "una hecha desaparece de la lista viva",
    )

    reabierta = T.actualizar(t["id"], estado="pendiente")

    comprobar(
        reabierta["cerrada"] is None,
        "al reabrirla se borra la fecha de cierre",
    )

    comprobar(T.buscar("Ciclo comp") is not None, "se puede buscar por texto")
    comprobar(T.buscar("no existe eso") is None, "y no inventa resultados")

    comprobar(
        T.actualizar("T999", estado="hecha") is None,
        "actualizar un id que no existe devuelve None, no revienta",
    )


def prueba_id_inmutable() -> None:
    print("\n7. El id y la fecha de alta no se pueden pisar")

    t = T.anadir("Intocable")
    creada = t["creada"]

    T.actualizar(t["id"], id="T666", creada="1999-01-01", titulo="Nuevo titulo")

    leida = T.buscar(t["id"])

    comprobar(leida is not None, "la tarea sigue con su id original")
    comprobar(leida["creada"] == creada, "la fecha de alta no se toco")
    comprobar(leida["titulo"] == "Nuevo titulo", "pero el titulo si cambia")


# ------------------------------------------- 8. no perder la cola

def prueba_no_pisa_una_cola_rota() -> None:
    print("\n8. Una cola rota NO se convierte en una cola vacia")

    T.ALMACEN.write_text("{esto no es json", encoding="utf-8")

    reventado = False

    try:
        T.cargar()
    except json.JSONDecodeError:
        reventado = True

    comprobar(
        reventado,
        "cargar() revienta con un json roto en vez de devolver cola vacia",
    )

    texto = T.ALMACEN.read_text(encoding="utf-8")

    comprobar(
        texto == "{esto no es json",
        "y el archivo roto sigue intacto, sin sobrescribir",
    )


def prueba_vista_se_regenera() -> None:
    print("\n9. La vista .md sale del json")

    T.ALMACEN.unlink(missing_ok=True)

    T.anadir(
        "Sale en la vista",
        depende="damian",
        limite="2026-09-22",
        detalle="Un detalle cualquiera.",
    )

    md = T.VISTA.read_text(encoding="utf-8")

    comprobar("Sale en la vista" in md, "el titulo aparece")
    comprobar("Te toca a ti" in md, "esta la seccion de Damian")
    comprobar("Me toca a mi" in md, "esta mi seccion")
    comprobar("Un detalle cualquiera." in md, "el detalle se vuelca")
    comprobar("2026-09-22" in md, "la fecha limite sale")
    comprobar("No editar a mano" in md, "avisa de que es generada")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = Path(tmp)

        desviar(carpeta)

        print("=" * 62)
        print("PRUEBAS DE nucleo/tareas.py")
        print(f"almacen de prueba: {T.ALMACEN}")
        print("=" * 62)

        prueba_alta_y_lectura()
        prueba_recorte_de_valores()
        prueba_puntuacion()
        prueba_urgencia_por_fecha()
        prueba_reparto_y_siguiente()
        prueba_ciclo_de_vida()
        prueba_id_inmutable()
        prueba_no_pisa_una_cola_rota()
        prueba_vista_se_regenera()

    print("\n" + "=" * 62)
    print(f"{PASADAS} comprobaciones en verde, {len(FALLOS)} en rojo")

    if FALLOS:
        for f in FALLOS:
            print(f"  - {f}")

        return 1

    print("TODO EN VERDE")

    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(main())
