# -*- coding: utf-8 -*-
"""Dificultad real de un sudoku por las técnicas humanas que necesita (T943, pieza P0c de T689)."""
from __future__ import annotations

from extremidades.puzzles import sudoku

TECNICAS = ("solitario_desnudo", "solitario_oculto", "bloqueo", "pareja_desnuda", "pareja_oculta")
_PISTAS = {"facil": 40, "medio": 32, "dificil": 26}

_FILAS = [[f * 9 + c for c in range(9)] for f in range(9)]
_COLS = [[f * 9 + c for f in range(9)] for c in range(9)]
_CAJAS = [[(bf * 3 + i) * 9 + bc * 3 + j for i in range(3) for j in range(3)] for bf in range(3) for bc in range(3)]
_UNIDADES = _FILAS + _COLS + _CAJAS
_VECINOS = [set().union(*(u for u in _UNIDADES if i in u)) - {i} for i in range(81)]


def _candidatos(celdas):
    return [set() if celdas[i] else {d for d in range(1, 10)} - {celdas[j] for j in _VECINOS[i]} for i in range(81)]


def _poner(celdas, cand, i, d):
    celdas[i] = d
    cand[i] = set()
    for j in _VECINOS[i]:
        cand[j].discard(d)


def _solitario_desnudo(celdas, cand):
    for i in range(81):
        if len(cand[i]) == 1:
            _poner(celdas, cand, i, next(iter(cand[i])))
            return True
    return False


def _solitario_oculto(celdas, cand):
    for u in _UNIDADES:
        for d in range(1, 10):
            sitios = [i for i in u if d in cand[i]]
            if len(sitios) == 1:
                _poner(celdas, cand, sitios[0], d)
                return True
    return False


def _bloqueo(celdas, cand):
    for caja in _CAJAS:
        for linea in _FILAS + _COLS:
            comun = set(caja) & set(linea)
            if not comun:
                continue
            for d in range(1, 10):
                en_caja = {i for i in caja if d in cand[i]}
                en_linea = {i for i in linea if d in cand[i]}
                for dentro, fuera in ((en_caja, en_linea), (en_linea, en_caja)):
                    if dentro and dentro <= comun:
                        quitar = fuera - comun
                        if quitar:
                            for i in quitar:
                                cand[i].discard(d)
                            return True
    return False


def _pareja_desnuda(celdas, cand):
    for u in _UNIDADES:
        pares = [i for i in u if len(cand[i]) == 2]
        for a in range(len(pares)):
            for b in range(a + 1, len(pares)):
                i, j = pares[a], pares[b]
                if cand[i] == cand[j]:
                    quitar = [(k, d) for k in u if k not in (i, j) for d in cand[i] if d in cand[k]]
                    if quitar:
                        for k, d in quitar:
                            cand[k].discard(d)
                        return True
    return False


def _pareja_oculta(celdas, cand):
    for u in _UNIDADES:
        sitios = {d: frozenset(i for i in u if d in cand[i]) for d in range(1, 10)}
        dobles = [d for d in range(1, 10) if len(sitios[d]) == 2]
        for a in range(len(dobles)):
            for b in range(a + 1, len(dobles)):
                d1, d2 = dobles[a], dobles[b]
                if sitios[d1] == sitios[d2]:
                    cambio = False
                    for i in sitios[d1]:
                        if cand[i] - {d1, d2}:
                            cand[i] &= {d1, d2}
                            cambio = True
                    if cambio:
                        return True
    return False


_PASOS = {"solitario_desnudo": _solitario_desnudo, "solitario_oculto": _solitario_oculto, "bloqueo": _bloqueo,
          "pareja_desnuda": _pareja_desnuda, "pareja_oculta": _pareja_oculta}


def resolver_logico(rejilla: str) -> dict:
    if not sudoku.valida(rejilla):
        raise ValueError("rejilla no válida")
    celdas = [int(c) for c in rejilla]
    cand = _candidatos(celdas)
    usadas = {t: 0 for t in TECNICAS}
    while True:
        for t in TECNICAS:
            if _PASOS[t](celdas, cand):
                usadas[t] += 1
                break
        else:
            break
    resuelto = all(celdas)
    hechas = [t for t in TECNICAS if usadas[t]]
    return {"resuelto": resuelto, "rejilla": "".join(map(str, celdas)), "tecnicas": usadas,
            "maxima": hechas[-1] if hechas else None}


def nivel(rejilla: str) -> str:
    r = resolver_logico(rejilla)
    if not r["resuelto"]:
        return "experto"
    if r["maxima"] in (None, "solitario_desnudo"):
        return "facil"
    if r["maxima"] == "solitario_oculto":
        return "medio"
    return "dificil"


def generar_por_nivel(semilla: int, nivel_pedido: str, intentos: int = 300) -> dict:
    if nivel_pedido not in _PISTAS:
        raise ValueError(f"nivel no generable: {nivel_pedido}")
    for k in range(intentos):
        p = sudoku.generar(semilla * 1000 + k, _PISTAS[nivel_pedido])
        if nivel(p["puzzle"]) == nivel_pedido:
            return {**p, "nivel": nivel_pedido}
    raise RuntimeError(f"sin puzzle de nivel {nivel_pedido} en {intentos} intentos")
