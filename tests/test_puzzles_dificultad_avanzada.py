# -*- coding: utf-8 -*-
"""Resolvedor lógico avanzado y generador por nivel de sudokus (libro «Sudoku 1 · Cuadernos de Lógica»).

Los 8 casos de UsDoku son SOLO de prueba (no se publican). Cada técnica avanzada tiene un caso que la necesita: la
rejilla se atasca con las técnicas anteriores y la técnica se aplica al menos una vez. Nunca se escribe una cifra
incorrecta (se compara con la solución única).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from extremidades.puzzles import dificultad as D
from extremidades.puzzles import dificultad_avanzada as A
from extremidades.puzzles import lote
from extremidades.puzzles import sudoku as S

USDOKU = {
    "facil1": "300700004470001800029430500900000100000809000008000007003048710004900053500007009",
    "facil2": "060500000014690035009003610001206083070030040850904700042300100180069350000008090",
    "medio1": "030000900068400012900200040000506720000090000056701000010003006340007190005000070",
    "medio2": "048070530000000000300000004020000080005802400004060100070915060500608001800040003",
    "dificil1": "000451000000000000006000100002060800907805406100090003590706042070000080004000600",
    "dificil2": "009040000100006205702000800000308051000020000380607000001000409506900007000070500",
    "extremo1": "030001700080002369720800000590000200000060000008000031000003027264100050003200090",
    "extremo2": "107002058500000000002040609900701000003000800000304002704090500000000004350400206",
}
# nivel4 esperado (medio2 se resuelve con solo solitarios desnudos; dificil1 y los extremos necesitan técnicas avanzadas)
NIVEL_USDOKU = {"facil1": "facil", "facil2": "facil", "medio1": "medio", "medio2": "facil", "dificil1": "experto",
                "dificil2": "dificil", "extremo1": "experto", "extremo2": "experto"}

# Un caso por técnica avanzada: sudokus (de 6000 generados) en los que esa técnica es la más difícil y se usa una vez.
CASOS_TECNICA = {
    "tripleta_desnuda": "104500690900000000070000080400026708200070403000430002709250030050004000801000200",
    "tripleta_oculta": "600023800508009007900740000300807000000030040006000000700050004005600002009000710",
    "x_wing": "709028560000300201002000008000003040400090652506002000260030000905000820000000000",
    "swordfish": "062534100000020005007100000070010400008003701090040802000080007713059008580000010",
    "xy_wing": "700300082800902067029006000080000053003028000070103000107030809000401000300000571",
    "xyz_wing": "000004069000970350020000107001480006000090030500613020004800000053009084870000605",
    "w_wing": "000105020600020001092070000040009130906743080000000074470002010080630050001000290",
    "coloreado": "100000509005300087000000301023009000706020004900500670340810090060000100001290000",
    "xy_chain": "100030004630090200708050090900020400302500600800010002086003005007004100403000820",
    "aic": "400030950003004000090600000070005600905100073000040090010068009007400080040200010",
}


def _comprobar_correcto(rejilla: str, r: dict) -> None:
    solucion = S.resolver(rejilla)
    assert all(p == "0" or p == q for p, q in zip(rejilla, r["rejilla"]))          # respeta las pistas
    assert all(x == "0" or x == s for x, s in zip(r["rejilla"], solucion))         # nada incorrecto
    assert r["resuelto"] == (r["rejilla"] == solucion)


@pytest.mark.parametrize("nombre", sorted(USDOKU))
def test_usdoku_se_resuelven_enteros(nombre):
    rejilla = USDOKU[nombre]
    r = A.resolver_avanzado(rejilla)
    assert r["resuelto"], nombre
    _comprobar_correcto(rejilla, r)
    assert A.nivel4(rejilla) == NIVEL_USDOKU[nombre]
    assert set(r["tecnicas"]) == set(A.TECNICAS) and r["puntuacion"] > 0


def test_usdoku_coincide_con_pruebas_de_referencia():
    # Bloque 21: copia versionada de memoria/monetizacion/referencia/usdoku_pruebas.json (sin versionar, no existe en
    # los worktrees del implementador: alli este test fallaba siempre)
    ref = json.loads((Path(__file__).resolve().parent / "datos" / "puzzles" / "usdoku_pruebas.json")
                     .read_text(encoding="utf-8"))
    assert ref == USDOKU


def test_las_basicas_atascan_y_las_avanzadas_resuelven():
    for nombre in ("dificil1", "extremo1", "extremo2"):
        assert not D.resolver_logico(USDOKU[nombre])["resuelto"]
        r = A.resolver_avanzado(USDOKU[nombre])
        assert r["resuelto"] and r["maxima"] in A.TECNICAS[5:]


def test_puntuacion_ordena_los_niveles():
    p = {n: A.resolver_avanzado(r)["puntuacion"] for n, r in USDOKU.items()}
    assert p["facil1"] < p["dificil2"] < p["dificil1"] < p["extremo1"] < p["extremo2"]


@pytest.mark.parametrize("tecnica", sorted(CASOS_TECNICA, key=A.TECNICAS.index))
def test_cada_tecnica_avanzada_tiene_su_caso(tecnica, monkeypatch):
    rejilla = CASOS_TECNICA[tecnica]
    r = A.resolver_avanzado(rejilla)
    assert r["resuelto"] and r["maxima"] == tecnica and r["tecnicas"][tecnica] >= 1
    _comprobar_correcto(rejilla, r)
    assert A.nivel4(rejilla) == "experto"
    # sin esa técnica (solo las anteriores) la rejilla se atasca: de verdad la necesita
    monkeypatch.setattr(A, "TECNICAS", A.TECNICAS[:A.TECNICAS.index(tecnica)])
    assert not A.resolver_avanzado(rejilla)["resuelto"]


def test_orden_de_tecnicas_y_pesos():
    assert A.TECNICAS[:5] == D.TECNICAS and A.BASICAS == D.TECNICAS
    assert set(A.PESOS) == set(A.TECNICAS)
    assert all(A.PESOS[a] <= A.PESOS[b] for a, b in zip(A.TECNICAS, A.TECNICAS[1:]))


def test_rejilla_no_valida():
    with pytest.raises(ValueError):
        A.resolver_avanzado("55" + "0" * 79)
    with pytest.raises(ValueError):
        A.nivel4("123")


def test_sin_pistas_utiles_es_no_logico():
    assert A.nivel4("0" * 81) == "no_logico"


def test_nunca_escribe_mal_en_generados():
    for semilla in range(60):
        rng = random.Random(semilla)
        solucion = A._solucion_aleatoria(rng)
        celdas = A._quitar_pistas(solucion, rng, rng.choice([0, 0, 24, 28, 32]))
        rejilla = "".join(map(str, celdas))
        r = A.resolver_avanzado(rejilla)
        assert all(x == "0" or x == s for x, s in zip(r["rejilla"], solucion)), rejilla
        assert r["resuelto"] == (r["rejilla"] == solucion)


def test_contador_rapido_coincide_con_el_de_sudoku():
    assert A.contar_soluciones("0" * 81) == 2          # limite 2
    for semilla in range(3):
        p = S.generar(semilla, 36)["puzzle"]
        assert A.contar_soluciones(p) == S.contar_soluciones(p) == 1
        quitada = p.replace(next(c for c in p if c != "0"), "0", 3)
        assert A.contar_soluciones(quitada) == S.contar_soluciones(quitada)


def test_coincide_con_las_basicas_de_dificultad():
    for semilla in range(60):
        rng = random.Random(1000 + semilla)
        solucion = A._solucion_aleatoria(rng)
        rejilla = "".join(map(str, A._quitar_pistas(solucion, rng, rng.choice([26, 30, 34, 38]))))
        viejo, nuevo = D.nivel(rejilla), A.nivel4(rejilla)
        if viejo == "experto":
            assert nuevo in ("experto", "no_logico")
        else:
            assert nuevo == viejo


@pytest.mark.parametrize("nivel", ["facil", "medio", "dificil", "experto"])
def test_generar_por_nivel4(nivel):
    for semilla in (1, 2):
        p = A.generar_por_nivel4(semilla, nivel)
        assert p["nivel"] == nivel and A.nivel4(p["puzzle"]) == nivel and p["semilla"] == semilla
        assert A.contar_soluciones(p["puzzle"]) == 1
        assert S.resolver(p["puzzle"]) == p["solucion"]
        assert p["pistas"] == sum(c != "0" for c in p["puzzle"])
        assert p["puntuacion"] == A.resolver_avanzado(p["puzzle"])["puntuacion"] and p["tecnicas"]
        assert p == A.generar_por_nivel4(semilla, nivel)                       # determinista
    assert A.generar_por_nivel4(1, nivel) != A.generar_por_nivel4(2, nivel)


def test_unicidad_con_el_contador_lento_de_sudoku():
    p = A.generar_por_nivel4(3, "experto")
    assert S.contar_soluciones(p["puzzle"]) == 1


def test_expertos_estan_a_la_altura_de_los_extremos_de_usdoku():
    minimo = min(A.resolver_avanzado(USDOKU[n])["puntuacion"] for n in ("extremo1", "extremo2"))
    lote_ = [A.generar_por_nivel4(s, "experto") for s in range(1, 9)]
    assert all(22 <= p["pistas"] <= 28 for p in lote_)
    assert sum(p["puntuacion"] >= minimo for p in lote_) >= len(lote_) // 2
    assert all(A.UMBRAL_EXPERTO <= p["puntuacion"] <= A.PUNTUACION_MAX_EXPERTO for p in lote_)


def test_generar_por_nivel4_errores():
    for malo in ("no_logico", "imposible"):
        with pytest.raises(ValueError):
            A.generar_por_nivel4(1, malo)


def test_lote_reanudable(tmp_path):
    salida = tmp_path / "expertos.json"
    d1 = lote.generar_lote("experto", 3, salida, log=lambda *_: None)
    assert len(d1["puzzles"]) == 3
    primeros = {p["puzzle"] for p in d1["puzzles"]}
    d2 = lote.generar_lote("experto", 5, salida, log=lambda *_: None)          # reanuda: no repite ni pierde
    assert len(d2["puzzles"]) == 5 and primeros <= {p["puzzle"] for p in d2["puzzles"]}
    guardado = json.loads(salida.read_text(encoding="utf-8"))
    pts = [p["puntuacion"] for p in guardado["puzzles"]]
    assert pts == sorted(pts) and guardado["nivel"] == "experto"
    for p in guardado["puzzles"]:
        assert set(p) >= {"puzzle", "solucion", "pistas", "nivel", "puntuacion", "tecnicas", "semilla"}
        assert A.nivel4(p["puzzle"]) == "experto"
    assert len({p["semilla"] for p in guardado["puzzles"]}) == 5
    again = lote.generar_lote("experto", 5, salida, log=lambda *_: None)      # ya completo: no cambia nada
    assert again["puzzles"] == guardado["puzzles"]


def test_lote_no_mezcla_niveles(tmp_path):
    salida = tmp_path / "x.json"
    lote.generar_lote("facil", 2, salida, log=lambda *_: None)
    with pytest.raises(SystemExit):
        lote.generar_lote("medio", 2, salida, log=lambda *_: None)


def test_lote_en_paralelo_da_lo_mismo(tmp_path):
    a = lote.generar_lote("medio", 4, tmp_path / "a.json", procesos=1, tanda=4, log=lambda *_: None)
    b = lote.generar_lote("medio", 4, tmp_path / "b.json", procesos=2, tanda=4, log=lambda *_: None)
    assert a["puzzles"] == b["puzzles"]
