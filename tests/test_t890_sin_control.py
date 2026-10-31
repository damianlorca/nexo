# -*- coding: utf-8 -*-
"""T890 (6): un retroceso (0x08) en lugar de \b dentro de una expresion regular se colo tres veces al editar
(reels, brief, trabajo): la expresion deja de casar y nadie se entera. Ningun .py del codigo lleva ese caracter."""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def test_ningun_py_del_codigo_lleva_un_caracter_de_retroceso():
    ficheros = [p for carpeta in ("nucleo", "extremidades", "interfaz", "canal", "manos", "tests", "tests_dados")
                for p in (RAIZ / carpeta).rglob("*.py") if "__pycache__" not in p.parts] + list(RAIZ.glob("*.py"))
    assert ficheros
    malos = [str(p.relative_to(RAIZ)) for p in ficheros if bytes([8]) in p.read_bytes()]
    assert malos == []


def test_las_expresiones_de_brief_y_trabajo_casan_con_su_limite_de_palabra():
    from nucleo import brief, trabajo
    # brief: "(ver T123)" se quita del resumen; con el retroceso literal nunca casaba
    t = {"detalle": "Arreglar la cola (ver T123) y seguir. DONDE: nucleo/tareas.py"}
    assert "T123" not in brief._resumen_corto(t) and brief._resumen_corto(t).startswith("Arreglar la cola")
    # trabajo: pruebas debiles ("fecha futura", "no existe") se reconocen; "futurismo" o "no existente" no son la frase
    assert trabajo._prueba_debil("es una fecha futura") and trabajo._prueba_debil("la pagina no existe.")
    assert trabajo._prueba_debil("no se encuentra en ningun sitio")
    assert not trabajo._prueba_debil("el changelog oficial lista v22.1 sin ese flag, ver https://nodejs.org/x")
