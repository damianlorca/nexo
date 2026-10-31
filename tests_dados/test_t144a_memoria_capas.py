# -*- coding: utf-8 -*-
"""T144 pieza A: memoria de NEXO por CAPAS con tope de tamano y control de quien escribe (patron Hermes).

Tests dados (los escribe Claude; el implementador SOLO crea nucleo/memoria_capas.py). Contrato:
- `CARPETA` = RAIZ / "memoria" / "capas" (los tests la cambian). Archivos UTF-8:
    capa "usuario"  -> CARPETA / "usuario.md"            tope 2000 caracteres
    capa "proyecto" -> CARPETA / "proyecto.md"           tope 4000
    capa "diaria"   -> CARPETA / "diaria" / "AAAA-MM-DD.md" (fecha de `ahora`), tope 3000
  `TOPES = {"usuario": 2000, "proyecto": 4000, "diaria": 3000}`. Archivo que no existe = capa vacia ("").
- `DIRECTOS = ("damian", "claude")`: solo ellos escriben directamente. Cualquier otro autor (qwen, gemini, turno...)
  NO escribe: su texto va a la bandeja (pieza B); en esta pieza `anadir` devuelve un dict con "estado": "pendiente"
  (la pieza B le anadira "id") y no toca
  la capa (la bandeja la hace la pieza B; aqui basta con no escribir).
- `anadir(capa, texto, autor, ahora=None) -> dict`. Precedencia:
    1. capa desconocida -> ValueError;  2. texto vacio tras strip -> ValueError;
    3. autor (strip + minusculas) no en DIRECTOS -> {"estado": "pendiente"};
    4. linea = f"- [{ahora:%Y-%m-%d %H:%M} {autor}] {texto}" con los saltos de linea del texto cambiados por " "
       (y strip). Si len(contenido_actual) + len(linea) + 1 > tope -> {"estado": "rechazada", "motivo": "tope"} sin
       escribir. Si no, se anade la linea + "\n" al final -> {"estado": "escrita", "linea": linea}.
- `leer(capa, ahora=None) -> str`: contenido de la capa ("diaria" = la del dia de `ahora`).
- `foto(ahora=None) -> str`: foto fija para el arranque de una sesion: "## usuario\n" + leer usuario + "\n## proyecto\n"
  + leer proyecto + "\n## diaria " + f"{ahora:%Y-%m-%d}" + "\n" + leer diaria. Nunca supera la suma de TOPES + 100.
- `borrar(capa, n, quien) -> bool`: quita la linea n (0 = primera) de la capa. Solo DIRECTOS (lo desatendido anade
  pero NUNCA borra): otro quien -> PermissionError. n fuera de rango -> False sin tocar nada.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from nucleo import memoria_capas as M

AHORA = datetime(2026, 10, 12, 9, 30)


@pytest.fixture(autouse=True)
def carpeta(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "CARPETA", tmp_path / "capas")
    return tmp_path / "capas"


def test_vacia_y_escribir(carpeta):
    assert M.leer("usuario") == ""
    r = M.anadir("usuario", "Prefiere\nrespuestas cortas ", "Damian", ahora=AHORA)
    assert r == {"estado": "escrita", "linea": "- [2026-10-12 09:30 damian] Prefiere respuestas cortas"}
    assert (carpeta / "usuario.md").read_text(encoding="utf-8") == r["linea"] + "\n"


def test_diaria_por_fecha(carpeta):
    M.anadir("diaria", "turno de noche sin incidencias", "claude", ahora=AHORA)
    assert (carpeta / "diaria" / "2026-10-12.md").exists()
    assert M.leer("diaria", ahora=datetime(2026, 10, 13, 8, 0)) == ""


def test_ia_local_no_escribe(carpeta):
    assert M.anadir("proyecto", "borra todo", "qwen", ahora=AHORA)["estado"] == "pendiente"   # la pieza B anade "id"
    assert M.leer("proyecto") == ""


@pytest.mark.parametrize("capa,texto", [("secreta", "x"), ("usuario", "   ")])
def test_errores(capa, texto):
    with pytest.raises(ValueError):
        M.anadir(capa, texto, "claude", ahora=AHORA)


def test_tope_rechaza_sin_escribir():
    largo = "x" * 1900
    assert M.anadir("usuario", largo, "claude", ahora=AHORA)["estado"] == "escrita"
    antes = M.leer("usuario")
    assert M.anadir("usuario", "y" * 100, "claude", ahora=AHORA) == {"estado": "rechazada", "motivo": "tope"}
    assert M.leer("usuario") == antes


def test_tope_justo():
    linea = "- [2026-10-12 09:30 claude] "
    texto = "z" * (M.TOPES["usuario"] - len(linea) - 1)
    assert M.anadir("usuario", texto, "claude", ahora=AHORA)["estado"] == "escrita"


def test_foto():
    M.anadir("usuario", "u1", "damian", ahora=AHORA)
    M.anadir("proyecto", "p1", "claude", ahora=AHORA)
    M.anadir("diaria", "d1", "claude", ahora=AHORA)
    f = M.foto(ahora=AHORA)
    assert f.startswith("## usuario\n- [2026-10-12 09:30 damian] u1\n")
    assert "\n## proyecto\n- [2026-10-12 09:30 claude] p1\n" in f
    assert "\n## diaria 2026-10-12\n- [2026-10-12 09:30 claude] d1\n" in f
    assert len(f) <= sum(M.TOPES.values()) + 100


def test_borrar_solo_directos():
    M.anadir("proyecto", "uno", "claude", ahora=AHORA)
    M.anadir("proyecto", "dos", "claude", ahora=AHORA)
    with pytest.raises(PermissionError):
        M.borrar("proyecto", 0, "gemini")
    assert M.borrar("proyecto", 5, "claude") is False
    assert M.borrar("proyecto", 0, "Damian") is True
    assert M.leer("proyecto") == "- [2026-10-12 09:30 claude] dos\n"
