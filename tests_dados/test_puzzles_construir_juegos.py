# -*- coding: utf-8 -*-
"""Fábrica de puzzles (T689): montar con una orden un libro de Takuzu o de Star Battle por niveles (como P1c).

Tests dados (los escribe Claude; el implementador SOLO crea extremidades/puzzles/construir_juegos.py). Usa los
módulos ya fusionados nivel_juegos.py, pdf_juegos.py y kdp.py. Nada nuevo que instalar.

Contrato:
- ORDEN = ("facil", "medio", "dificil").
- seleccionar_juego(tipo, n, n_por_nivel, semilla_base=0) -> list[dict]: tipo "takuzu" o "estrellas"; puzzles en
  orden fácil -> medio -> difícil (los niveles con 0 no salen), cada uno con
  nivel_juegos.generar_takuzu_por_nivel(semilla, n, nivel) o nivel_juegos.generar_estrellas_por_nivel(semilla, n,
  nivel) llamados A TRAVÉS DEL MÓDULO (`from extremidades.puzzles import nivel_juegos`), para que los tests puedan
  sustituirlos. Semilla = semilla_base + 1000 * (posición del nivel en ORDEN) + i. ValueError si el tipo no es uno
  de esos dos, si hay un nivel desconocido, si una cantidad no es un entero de 0 a 999 (bool no vale) o si el total
  es 0.
- construir_libro_juego(tipo, ruta, titulo, n, n_por_nivel, subtitulo="", autor="", instrucciones=(), semilla_base=0,
  por_pagina=2, soluciones_por_pagina=6, ancho=8.5, alto=11) -> {"paginas", "ruta" (str), "puzzles", "por_nivel"
  ({nivel: cantidad} solo con > 0), "coste_es", "coste_com"}: PDF con pdf_juegos.generar_interior_juego; costes con
  kdp.coste_impresion si 24 <= paginas <= 828, y None si no.
- main(argv=None) -> int: CLI con argparse (--help sale sin hacer nada más): `construir_juegos.py SALIDA
  --juego takuzu|estrellas --tamano N --titulo T [--subtitulo S] [--autor A] [--facil N] [--medio N] [--dificil N]
  [--semilla K] [--instrucciones ARCHIVO]` (un párrafo por línea no vacía). Monta el libro, imprime el resumen y
  devuelve 0.
Contrato comun (T1027): si el modulo tiene bloque `if __name__ == "__main__":`, su PRIMERA linea es
`from nucleo import ayuda; ayuda.atender(__doc__)` (o el modulo usa argparse): --help/-h no ejecuta nada. Lo exige
tests/test_ayuda_entradas.py en la suite completa (T938 cayo por eso).
"""
from __future__ import annotations

import pytest

from extremidades.puzzles import construir_juegos as C
from extremidades.puzzles import nivel_juegos as N


@pytest.mark.parametrize("tipo,funcion", [("takuzu", "generar_takuzu_por_nivel"),
                                          ("estrellas", "generar_estrellas_por_nivel")])
def test_seleccionar_orden_y_semillas(monkeypatch, tipo, funcion):
    llamadas = []

    def falso(semilla, n, nivel):
        llamadas.append((semilla, n, nivel))
        return {"nivel": nivel, "n": n}

    monkeypatch.setattr(N, funcion, falso)
    res = C.seleccionar_juego(tipo, 8, {"dificil": 1, "facil": 2, "medio": 0}, semilla_base=3)
    assert llamadas == [(3, 8, "facil"), (4, 8, "facil"), (2003, 8, "dificil")]
    assert [p["nivel"] for p in res] == ["facil", "facil", "dificil"]


@pytest.mark.parametrize("tipo,malo", [("sopa", {"facil": 1}), ("takuzu", {"imposible": 1}), ("takuzu", {"facil": -1}),
                                       ("takuzu", {"facil": True}), ("estrellas", {"facil": 0}), ("estrellas", {})])
def test_errores(tipo, malo):
    with pytest.raises(ValueError):
        C.seleccionar_juego(tipo, 6, malo)


@pytest.mark.parametrize("tipo,n", [("takuzu", 6), ("estrellas", 6)])
def test_libro_de_prueba(tmp_path, tipo, n):
    ruta = tmp_path / f"{tipo}.pdf"
    res = C.construir_libro_juego(tipo, ruta, "Prueba", n, {"facil": 2, "medio": 1, "dificil": 1})
    assert res["paginas"] == 6 and res["puzzles"] == 4 and res["ruta"] == str(ruta)
    assert res["por_nivel"] == {"facil": 2, "medio": 1, "dificil": 1}
    assert res["coste_es"] is None and ruta.read_bytes().startswith(b"%PDF-")


def test_cli_y_ayuda(tmp_path):
    salida = tmp_path / "e.pdf"
    assert C.main([str(salida), "--juego", "estrellas", "--tamano", "6", "--titulo", "E", "--facil", "2"]) == 0
    assert salida.read_bytes().startswith(b"%PDF-")
    with pytest.raises(SystemExit) as e:
        C.main(["--help"])
    assert e.value.code == 0
    assert [p.name for p in tmp_path.iterdir()] == ["e.pdf"]
