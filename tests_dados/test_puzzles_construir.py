# -*- coding: utf-8 -*-
"""Piloto de monetización (T689), pieza P1c: montar el libro final (puzzles y PDF) con una sola orden.

Tests dados (los escribe Claude; el implementador SOLO crea extremidades/puzzles/construir.py). Usa los módulos ya
fusionados sudoku.py (P0a), dificultad.py (P0c), kdp.py (P0b) y pdf.py (P1b). Nada nuevo que instalar.

Contrato:
- ORDEN = ("facil", "medio", "dificil").
- seleccionar(n_por_nivel: dict, semilla_base=0) -> list[dict]: los puzzles del libro en orden fácil -> medio ->
  difícil (los niveles con 0 no salen). Cada uno es dificultad.generar_por_nivel(semilla, nivel) (nivel REAL por
  técnicas, P0c) llamado A TRAVÉS DEL MÓDULO (`from extremidades.puzzles import dificultad` y luego
  `dificultad.generar_por_nivel(...)`), para que los tests puedan sustituirlo. Semilla = semilla_base + 1000 *
  (posición del nivel en ORDEN) + i, con i = 0..n-1: así no se repiten
  soluciones entre niveles. ValueError si hay un nivel desconocido, si una cantidad no es un entero de 0 a 999 (un
  bool no vale) o si el total es 0.
- construir_libro(ruta, titulo, n_por_nivel, subtitulo="", autor="", instrucciones=(), semilla_base=0, por_pagina=2,
  soluciones_por_pagina=6, ancho=8.5, alto=11) -> dict: puzzles con seleccionar() y PDF con pdf.generar_interior().
  Devuelve {"paginas", "ruta" (str), "puzzles" (cuántos), "por_nivel" ({nivel: n} solo con n > 0), "coste_es",
  "coste_com"}. Los costes son kdp.coste_impresion(paginas, "es" o "com", ancho, alto) si 24 <= paginas <= 828, y
  None si no (libro de prueba).
- main(argv=None) -> int: CLI con argparse (--help sale sin hacer nada más):
  `construir.py SALIDA --titulo T [--subtitulo S] [--autor A] [--facil N] [--medio N] [--dificil N] [--semilla K]
  [--instrucciones ARCHIVO]`. ARCHIVO es texto UTF-8 con un párrafo por línea no vacía. Monta el libro, imprime el
  resumen y devuelve 0.
Contrato comun (T1027): si el modulo tiene bloque `if __name__ == "__main__":`, su PRIMERA linea es
`from nucleo import ayuda; ayuda.atender(__doc__)` (o el modulo usa argparse): --help/-h no ejecuta nada. Lo exige
tests/test_ayuda_entradas.py en la suite completa (T938 cayo por eso).
"""
from __future__ import annotations

import pytest

from extremidades.puzzles import construir as C
from extremidades.puzzles import dificultad as D


def test_seleccionar_orden_y_semillas(monkeypatch):
    llamadas = []

    def falso(semilla, nivel):
        llamadas.append((semilla, nivel))
        return {"puzzle": "0" * 81, "solucion": "1" * 81, "pistas": 0, "nivel": nivel}

    monkeypatch.setattr(D, "generar_por_nivel", falso)
    res = C.seleccionar({"dificil": 1, "facil": 2, "medio": 0}, semilla_base=5)
    assert llamadas == [(5, "facil"), (6, "facil"), (2005, "dificil")]
    assert [p["nivel"] for p in res] == ["facil", "facil", "dificil"]


@pytest.mark.parametrize("malo", [{"imposible": 1}, {"facil": -1}, {"facil": 1000}, {"facil": 1.5},
                                  {"facil": True}, {"facil": 0}, {}])
def test_seleccionar_errores(malo):
    with pytest.raises(ValueError):
        C.seleccionar(malo)


def test_construir_libro_de_prueba(tmp_path):
    ruta = tmp_path / "libro.pdf"
    res = C.construir_libro(ruta, "Prueba", {"facil": 2, "medio": 1, "dificil": 1})
    assert res["paginas"] == 6 and res["puzzles"] == 4      # 2 + 2 de puzzles + 1 de soluciones = 5 -> blanca
    assert res["ruta"] == str(ruta) and ruta.read_bytes().startswith(b"%PDF-")
    assert res["por_nivel"] == {"facil": 2, "medio": 1, "dificil": 1}
    assert res["coste_es"] is None and res["coste_com"] is None


def test_soluciones_distintas_orden_y_costes(tmp_path):
    puzzles = C.seleccionar({"facil": 3, "medio": 3, "dificil": 3})
    assert len({p["solucion"] for p in puzzles}) == 9
    assert [p["nivel"] for p in puzzles] == ["facil"] * 3 + ["medio"] * 3 + ["dificil"] * 3
    res = C.construir_libro(tmp_path / "l.pdf", "Prueba", {"facil": 33})
    assert res["paginas"] == 26                             # 2 + 17 + 6 = 25 -> blanca
    assert (res["coste_es"], res["coste_com"]) == (2.48, 2.84)


def test_determinista(tmp_path):
    C.construir_libro(tmp_path / "a.pdf", "P", {"medio": 2}, semilla_base=7)
    C.construir_libro(tmp_path / "b.pdf", "P", {"medio": 2}, semilla_base=7)
    assert (tmp_path / "a.pdf").read_bytes() == (tmp_path / "b.pdf").read_bytes()


def test_cli(tmp_path):
    instrucciones = tmp_path / "instrucciones.txt"
    instrucciones.write_text("Regla uno.\n\nRegla dos.\n", encoding="utf-8")
    salida = tmp_path / "cli.pdf"
    assert C.main([str(salida), "--titulo", "Prueba", "--facil", "2", "--instrucciones", str(instrucciones)]) == 0
    assert salida.read_bytes().startswith(b"%PDF-")
    with pytest.raises(SystemExit) as e:
        C.main(["--help"])
    assert e.value.code == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cli.pdf", "instrucciones.txt"]
